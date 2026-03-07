"""Live protocol capture and analysis for Tigo CCA.

Captures all frames, logs unknown/interesting patterns, and outputs
structured data for protocol reverse engineering.
"""

import sys
import os
import json
import struct
import time
import signal
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Add pytap to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pytap.core.source import TcpSource
from pytap.core.crc import crc
from pytap.core.types import (
    Address, FrameType, Frame, GatewayID,
    SlotCounter, PacketType, ReceivedPacketHeader,
    iter_received_packets,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HOST = "192.168.2.94"
PORT = 4196

TAP_NAMES = {0x1201: "TAP1", 0x1202: "TAP2", 0x1203: "TAP3"}

FRAME_TYPE_NAMES = {
    0x0148: "RECEIVE_REQUEST", 0x0149: "RECEIVE_RESPONSE",
    0x0B0F: "COMMAND_REQUEST", 0x0B10: "COMMAND_RESPONSE",
    0x0B00: "PING_REQUEST", 0x0B01: "PING_RESPONSE",
    0x0014: "ENUM_START_REQ", 0x0015: "ENUM_START_RESP",
    0x0038: "ENUM_REQ", 0x0039: "ENUM_RESP",
    0x003C: "ASSIGN_GW_ID_REQ", 0x003D: "ASSIGN_GW_ID_RESP",
    0x003A: "IDENTIFY_REQ", 0x003B: "IDENTIFY_RESP",
    0x000A: "VERSION_REQ", 0x000B: "VERSION_RESP",
    0x0E02: "ENUM_END_REQ", 0x0006: "ENUM_END_RESP",
    0x0010: "UNKNOWN_0010", 0x0011: "UNKNOWN_0011",
}

PV_TYPE_NAMES = {
    0x06: "STRING_REQ", 0x07: "STRING_RESP", 0x09: "TOPOLOGY",
    0x0D: "RADIO_CFG_REQ", 0x0E: "RADIO_CFG_RESP",
    0x13: "PV_CFG_REQ", 0x17: "UNKNOWN_0x17", 0x18: "PV_CFG_RESP",
    0x22: "BROADCAST", 0x23: "BCAST_ACK",
    0x26: "NODE_TBL_REQ", 0x27: "NODE_TBL_RESP",
    0x2D: "LONG_NET_STAT_REQ", 0x2E: "NET_STAT_REQ", 0x2F: "NET_STAT_RESP",
    0x31: "POWER_REPORT", 0x41: "UNKNOWN_0x41",
}


# ---------------------------------------------------------------------------
# Frame Assembly
# ---------------------------------------------------------------------------

UNESCAPE_MAP = {0x00: 0x7E, 0x01: 0x24, 0x02: 0x23, 0x03: 0x25,
                0x04: 0xA4, 0x05: 0xA3, 0x06: 0xA5}

class FrameAssembler:
    """Minimal frame assembler — yields (address, frame_type, payload) tuples."""
    IDLE, SOF, FRAME, ESCAPE, GIANT, GIANT_ESC = range(6)

    def __init__(self):
        self.state = self.IDLE
        self.buf = bytearray()

    def feed(self, data: bytes):
        for b in data:
            frame = self._step(b)
            if frame is not None:
                yield frame

    def _step(self, b):
        if self.state == self.IDLE:
            if b == 0x7E:
                self.state = self.SOF
        elif self.state == self.SOF:
            if b == 0x07:
                self.buf.clear()
                self.state = self.FRAME
            else:
                self.state = self.IDLE if b in (0x00, 0xFF) else self.IDLE
        elif self.state == self.FRAME:
            if b == 0x7E:
                self.state = self.ESCAPE
            elif len(self.buf) < 256:
                self.buf.append(b)
            else:
                self.buf.clear()
                self.state = self.GIANT
        elif self.state == self.ESCAPE:
            if b == 0x08:  # end of frame
                result = self._decode()
                self.buf.clear()
                self.state = self.IDLE
                return result
            elif b == 0x07:  # restart
                self.buf.clear()
                self.state = self.FRAME
            elif b in UNESCAPE_MAP:
                self.buf.append(UNESCAPE_MAP[b])
                self.state = self.FRAME
            else:
                self.buf.clear()
                self.state = self.IDLE
        elif self.state == self.GIANT:
            if b == 0x7E:
                self.state = self.GIANT_ESC
        elif self.state == self.GIANT_ESC:
            if b == 0x07:
                self.buf.clear()
                self.state = self.FRAME
            elif b == 0x08:
                self.state = self.IDLE
            else:
                self.state = self.GIANT
        return None

    def _decode(self):
        if len(self.buf) < 6:
            return None
        body = bytes(self.buf[:-2])
        exp_crc = int.from_bytes(self.buf[-2:], 'little')
        if crc(body) != exp_crc:
            return None
        addr_raw = int.from_bytes(self.buf[0:2], 'big')
        is_from = bool(addr_raw & 0x8000)
        gw_id = addr_raw & 0x7FFF
        ft = int.from_bytes(self.buf[2:4], 'big')
        payload = bytes(self.buf[4:-2])
        return (is_from, gw_id, ft, payload)


# ---------------------------------------------------------------------------
# RECEIVE_RESPONSE Parsing (relaxed — accepts H-firmware)
# ---------------------------------------------------------------------------

def parse_receive_response(payload, old_pkt_num=0):
    """Parse RECEIVE_RESPONSE with relaxed status_type check.
    Returns (status_info, pv_packets_bytes) or None.
    """
    if len(payload) < 4:
        return None
    st = int.from_bytes(payload[0:2], 'big')
    off = 2
    info = {"status_raw": f"0x{st:04X}", "byte0": payload[0], "byte1": payload[1]}

    # Parse using bits 0-4 only
    if not (st & 0x0001):
        if off >= len(payload): return None
        info["rx_buffers_used"] = payload[off]; off += 1
    if not (st & 0x0002):
        if off >= len(payload): return None
        info["tx_buffers_free"] = payload[off]; off += 1
    if not (st & 0x0004):
        if off + 1 >= len(payload): return None
        info["unknown_a"] = f"{payload[off]:02X} {payload[off+1]:02X}"; off += 2
    if not (st & 0x0008):
        if off + 1 >= len(payload): return None
        info["unknown_b"] = f"{payload[off]:02X} {payload[off+1]:02X}"; off += 2
    if not (st & 0x0010):
        if off + 1 >= len(payload): return None
        info["packet_num"] = int.from_bytes(payload[off:off+2], 'big'); off += 2
    else:
        if off >= len(payload): return None
        lo = payload[off]; off += 1
        old_hi = (old_pkt_num >> 8) & 0xFF
        old_lo = old_pkt_num & 0xFF
        new_hi = old_hi if lo >= old_lo else (old_hi + 1) & 0xFF
        info["packet_num"] = (new_hi << 8) | lo

    if off + 1 >= len(payload):
        return None
    info["slot_counter"] = int.from_bytes(payload[off:off+2], 'big'); off += 2
    return (info, payload[off:])


# ---------------------------------------------------------------------------
# PV Packet Iterator
# ---------------------------------------------------------------------------

def iter_pv_packets(data):
    """Iterate PV packets from RECEIVE_RESPONSE trailing data."""
    pos = 0
    while pos + 7 <= len(data):
        pkt_type = data[pos]
        node_addr = int.from_bytes(data[pos+1:pos+3], 'big')
        short_addr = int.from_bytes(data[pos+3:pos+5], 'big')
        dsn = data[pos+5]
        data_len = data[pos+6]
        if pos + 7 + data_len > len(data):
            break
        pkt_data = data[pos+7:pos+7+data_len]
        yield (pkt_type, node_addr, short_addr, dsn, pkt_data)
        pos += 7 + data_len


# ---------------------------------------------------------------------------
# Main Capture Loop
# ---------------------------------------------------------------------------

def hexdump(data, max_bytes=60):
    s = ' '.join(f'{b:02X}' for b in data[:max_bytes])
    if len(data) > max_bytes:
        s += f' ... (+{len(data)-max_bytes})'
    return s

def main():
    print(f"[{datetime.now():%H:%M:%S}] Connecting to {HOST}:{PORT}...", flush=True)
    source = TcpSource(HOST, PORT)
    source.connect()
    print(f"[{datetime.now():%H:%M:%S}] Connected! Listening...", flush=True)

    asm = FrameAssembler()
    pkt_nums = {}  # gw_id -> last packet number
    cmd_pending = {}  # (gw_id, seq) -> (pkt_type, req_payload)
    
    # Counters
    frame_counts = defaultdict(lambda: defaultdict(int))
    pv_pkt_counts = defaultdict(lambda: defaultdict(int))
    unknown_frames = []
    unknown_pv_pkts = []
    interesting_events = []
    
    start_time = time.time()
    total_frames = 0
    
    # Output file
    outf = open("capture_live.jsonl", "a", buffering=1)

    def tap_name(gw_id):
        return TAP_NAMES.get(gw_id, f"GW_{gw_id:#06X}")

    def ft_name(ft):
        return FRAME_TYPE_NAMES.get(ft, f"0x{ft:04X}")
    
    def pv_name(pt):
        return PV_TYPE_NAMES.get(pt, f"0x{pt:02X}")

    def log_event(evt):
        evt["_ts"] = datetime.now().isoformat()
        outf.write(json.dumps(evt) + "\n")
        interesting_events.append(evt)

    def print_summary():
        elapsed = time.time() - start_time
        print(f"\n{'='*70}")
        print(f"CAPTURE SUMMARY — {elapsed:.0f}s, {total_frames} frames")
        print(f"{'='*70}")
        for tap in sorted(frame_counts):
            print(f"\n  {tap}:")
            for ft in sorted(frame_counts[tap]):
                print(f"    {ft}: {frame_counts[tap][ft]}")
        if pv_pkt_counts:
            print(f"\n  PV packets:")
            for tap in sorted(pv_pkt_counts):
                print(f"    {tap}:")
                for pt in sorted(pv_pkt_counts[tap]):
                    print(f"      {pt}: {pv_pkt_counts[tap][pt]}")
        if unknown_frames:
            print(f"\n  Unknown frame types: {len(unknown_frames)}")
            for uf in unknown_frames[:20]:
                print(f"    {uf}")
        if unknown_pv_pkts:
            print(f"\n  Unknown PV packet types: {len(unknown_pv_pkts)}")
            for up in unknown_pv_pkts[:20]:
                print(f"    {up}")
        if interesting_events:
            print(f"\n  Interesting events: {len(interesting_events)}")
            for ie in interesting_events[-20:]:
                print(f"    {ie.get('type','?')}: {ie.get('summary','')}")
        print(flush=True)

    # Periodic summary
    last_summary = time.time()
    last_progress = time.time()

    try:
        while True:
            data = source.read(1024)
            if not data:
                time.sleep(0.01)
                continue
            
            for is_from, gw_id, ft, payload in asm.feed(data):
                total_frames += 1
                tap = tap_name(gw_id)
                direction = "FROM" if is_from else "TO"
                ft_str = ft_name(ft)
                
                frame_counts[tap][f"{direction}:{ft_str}"] += 1

                # Progress indicator every 10 seconds
                now = time.time()
                if now - last_progress > 10:
                    elapsed = now - start_time
                    print(f"[{datetime.now():%H:%M:%S}] {total_frames} frames in {elapsed:.0f}s ...", flush=True)
                    last_progress = now

                # --- Detect unknown frame types ---
                if ft not in FRAME_TYPE_NAMES:
                    msg = f"{tap} {direction} frame_type=0x{ft:04X} len={len(payload)} data={hexdump(payload)}"
                    unknown_frames.append(msg)
                    log_event({"type": "unknown_frame", "tap": tap, "dir": direction,
                               "frame_type": f"0x{ft:04X}", "payload": hexdump(payload),
                               "summary": msg})
                    print(f"[{datetime.now():%H:%M:%S}] *** UNKNOWN FRAME: {msg}", flush=True)

                # --- RECEIVE_REQUEST: track packet numbers ---
                if ft == 0x0148 and not is_from and len(payload) >= 5:
                    pkt_num = int.from_bytes(payload[2:4], 'big')
                    pkt_nums[gw_id] = pkt_num

                # --- RECEIVE_RESPONSE: parse with relaxed check ---
                if ft == 0x0149 and is_from:
                    old_num = pkt_nums.get(gw_id, 0)
                    parsed = parse_receive_response(payload, old_num)
                    if parsed:
                        info, pv_data = parsed
                        pkt_nums[gw_id] = info.get("packet_num", old_num)
                        
                        # Log full-status (0xE0) responses for unknown_a/b tracking
                        if "unknown_a" in info or "unknown_b" in info:
                            log_event({"type": "full_status", "tap": tap,
                                       "info": info, "summary": f"full_status {tap}"})

                        # Parse embedded PV packets
                        for pkt_type, node, short, dsn, pkt_data in iter_pv_packets(pv_data):
                            pt_str = pv_name(pkt_type)
                            pv_pkt_counts[tap][pt_str] += 1
                            
                            # Unknown PV packet types
                            if pkt_type not in PV_TYPE_NAMES:
                                msg = f"{tap} node={node} pv_type=0x{pkt_type:02X} len={len(pkt_data)} data={hexdump(pkt_data)}"
                                unknown_pv_pkts.append(msg)
                                log_event({"type": "unknown_pv", "tap": tap, "node": node,
                                           "pv_type": f"0x{pkt_type:02X}",
                                           "data": hexdump(pkt_data), "summary": msg})
                                print(f"[{datetime.now():%H:%M:%S}] *** UNKNOWN PV: {msg}", flush=True)
                            
                            # Log non-power-report packets
                            if pkt_type != 0x31:
                                log_event({"type": "pv_packet", "tap": tap, "node": node,
                                           "pv_type": f"0x{pkt_type:02X}", "pv_name": pt_str,
                                           "dsn": dsn, "short_addr": f"0x{short:04X}",
                                           "data_hex": hexdump(pkt_data),
                                           "summary": f"{pt_str} {tap} node={node}"})
                                print(f"[{datetime.now():%H:%M:%S}] PV {pt_str}: {tap} node={node} data={hexdump(pkt_data, 40)}", flush=True)

                # --- COMMAND_REQUEST: store for correlation ---
                if ft == 0x0B0F and not is_from and len(payload) >= 5:
                    pkt_type = payload[3]
                    seq = payload[4]
                    req_data = payload[5:]
                    cmd_pending[(gw_id, seq)] = (pkt_type, bytes(req_data))
                    pt_str = pv_name(pkt_type)
                    
                    # Log all commands
                    log_event({"type": "command_req", "tap": tap, "pv_type": f"0x{pkt_type:02X}",
                               "pv_name": pt_str, "seq": seq,
                               "data_hex": hexdump(req_data),
                               "summary": f"CMD {pt_str} {tap} seq={seq}"})
                    print(f"[{datetime.now():%H:%M:%S}] CMD_REQ {pt_str}: {tap} seq={seq} data={hexdump(req_data, 40)}", flush=True)

                # --- COMMAND_RESPONSE: correlate ---
                if ft == 0x0B10 and is_from and len(payload) >= 5:
                    resp_pkt_type = payload[3]
                    resp_seq = payload[4]
                    resp_data = payload[5:]
                    
                    req_info = cmd_pending.pop((gw_id, resp_seq), None)
                    req_type_str = pv_name(req_info[0]) if req_info else "?"
                    resp_type_str = pv_name(resp_pkt_type)
                    
                    log_event({"type": "command_resp", "tap": tap,
                               "req_type": f"0x{req_info[0]:02X}" if req_info else "?",
                               "resp_type": f"0x{resp_pkt_type:02X}",
                               "resp_name": resp_type_str,
                               "seq": resp_seq,
                               "data_hex": hexdump(resp_data),
                               "summary": f"CMD_RESP {req_type_str}->{resp_type_str} {tap}"})
                    print(f"[{datetime.now():%H:%M:%S}] CMD_RESP {req_type_str}->{resp_type_str}: {tap} seq={resp_seq} data={hexdump(resp_data, 40)}", flush=True)

                # --- VERSION_RESPONSE ---
                if ft == 0x000B and is_from:
                    ver = bytes(payload).decode('ascii', errors='replace')
                    log_event({"type": "version", "tap": tap, "version": ver,
                               "summary": f"VERSION {tap}: {ver!r}"})
                    print(f"[{datetime.now():%H:%M:%S}] VERSION {tap}: {ver!r}", flush=True)

                # --- IDENTIFY_RESPONSE ---
                if ft == 0x003B and is_from and len(payload) >= 10:
                    long_addr = ':'.join(f'{b:02X}' for b in payload[:8])
                    log_event({"type": "identify", "tap": tap, "long_addr": long_addr,
                               "summary": f"IDENTIFY {tap}: {long_addr}"})

                # --- PING ---
                if ft in (0x0B00, 0x0B01):
                    log_event({"type": "ping", "tap": tap, "dir": direction,
                               "data_hex": hexdump(payload),
                               "summary": f"PING {direction} {tap}"})

                # --- Any non-standard frame types ---
                if ft in (0x0010, 0x0011):
                    log_event({"type": "unknown_broadcast", "tap": tap, "dir": direction,
                               "frame_type": f"0x{ft:04X}",
                               "data_hex": hexdump(payload),
                               "summary": f"BCAST 0x{ft:04X} {direction} {tap}"})
                    print(f"[{datetime.now():%H:%M:%S}] BCAST 0x{ft:04X} {direction} {tap}: {hexdump(payload)}", flush=True)

            # Periodic summary
            now = time.time()
            if now - last_summary > 60:
                print_summary()
                last_summary = now

    except KeyboardInterrupt:
        pass
    finally:
        print_summary()
        outf.close()
        source.close()
        print(f"\nCapture saved to capture_live.jsonl")

if __name__ == "__main__":
    main()
