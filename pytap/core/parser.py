"""Core protocol parser for pytap.

Collapses the entire TapTap protocol stack (link layer, transport,
PV application, and observer) into a single Parser class with a
feed(bytes) -> list[Event] interface.
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from .barcode import barcode_from_address
from .crc import crc
from .events import (
    Event, PowerReportEvent, InfrastructureEvent,
    TopologyEvent, StringEvent,
)
from .state import SlotClock, NodeTableBuilder, PersistentState
from .types import (
    Address, FrameType, Frame, GatewayID,
    NodeAddress, LongAddress, SlotCounter,
    PacketType, ReceivedPacketHeader, PowerReport,
    iter_received_packets,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Frame State Machine
# ---------------------------------------------------------------------------

class _FrameState(Enum):
    IDLE = auto()
    NOISE = auto()
    START_OF_FRAME = auto()
    FRAME = auto()
    FRAME_ESCAPE = auto()
    GIANT = auto()
    GIANT_ESCAPE = auto()


MAX_FRAME_SIZE = 256

# Byte unescaping map: 0x7E followed by key -> value
_UNESCAPE_MAP: dict[int, int] = {
    0x00: 0x7E,
    0x01: 0x24,
    0x02: 0x23,
    0x03: 0x25,
    0x04: 0xA4,
    0x05: 0xA3,
    0x06: 0xA5,
}


# ---------------------------------------------------------------------------
#  Counters
# ---------------------------------------------------------------------------

@dataclass
class _Counters:
    frames_received: int = 0
    crc_errors: int = 0
    runts: int = 0
    giants: int = 0
    noise_bytes: int = 0


# ---------------------------------------------------------------------------
#  Enumeration State
# ---------------------------------------------------------------------------

@dataclass
class _EnumerationState:
    enumeration_gateway_id: int
    gateway_identities: dict[int, LongAddress]
    gateway_versions: dict[int, str]


# ---------------------------------------------------------------------------
#  Helper Functions
# ---------------------------------------------------------------------------

def _interpret_packet_number_lo(new_lo: int, old: int) -> int:
    """Expand a 1-byte packet number using the previous full number."""
    old_hi = (old >> 8) & 0xFF
    old_lo = old & 0xFF
    new_hi = old_hi if new_lo >= old_lo else (old_hi + 1) & 0xFF
    return (new_hi << 8) | new_lo


# ---------------------------------------------------------------------------
#  Parser
# ---------------------------------------------------------------------------

class Parser:
    """Core protocol parser.

    Maintains internal state for frame assembly, transport correlation,
    slot clock synchronization, and infrastructure tracking across
    incremental feed() calls.
    """

    def __init__(self, state_file: str | Path | None = None):
        # Frame accumulator state
        self._state: _FrameState = _FrameState.IDLE
        self._buffer: bytearray = bytearray()

        # Transport state
        self._rx_packet_numbers: dict[int, int] = {}
        self._commands_awaiting: dict[tuple[int, int], tuple[int, bytes]] = {}
        self._command_sequence_numbers: dict[int, int] = {}

        # Slot clocks (one per gateway)
        self._slot_clocks: dict[int, SlotClock] = {}
        self._captured_slot_times: dict[int, datetime] = {}

        # Enumeration state
        self._enum_state: Optional[_EnumerationState] = None

        # Infrastructure
        self._persistent_state: PersistentState
        self._state_file: Optional[Path] = None
        self._node_table_builders: dict[int, NodeTableBuilder] = {}

        # Counters
        self._counters: _Counters = _Counters()

        # Load persistent state
        if state_file is not None:
            self._state_file = Path(state_file)
            self._persistent_state = PersistentState.load(self._state_file)
        else:
            self._persistent_state = PersistentState()

    # -------------------------------------------------------------------
    #  Public Interface
    # -------------------------------------------------------------------

    def feed(self, data: bytes) -> list[Event]:
        """Feed raw bytes into the parser. Returns parsed events."""
        events: list[Event] = []
        for byte in data:
            frame = self._accumulate(byte)
            if frame is not None:
                self._counters.frames_received += 1
                events.extend(self._dispatch_frame(frame))
        return events

    def reset(self):
        """Reset frame accumulation state (not infrastructure)."""
        self._state = _FrameState.IDLE
        self._buffer.clear()

    @property
    def infrastructure(self) -> dict:
        """Current infrastructure snapshot."""
        gateways = {}
        for gw in set(self._persistent_state.gateway_identities) | set(self._persistent_state.gateway_versions):
            addr = self._persistent_state.gateway_identities.get(gw)
            gateways[gw] = {
                'address': str(addr) if addr else None,
                'version': self._persistent_state.gateway_versions.get(gw),
            }
        nodes = {}
        for gw_table in self._persistent_state.gateway_node_tables.values():
            for nid, addr in gw_table.items():
                nodes[nid] = {
                    'address': str(addr),
                    'barcode': barcode_from_address(addr.data),
                }
        return {'gateways': gateways, 'nodes': nodes}

    @property
    def counters(self) -> dict:
        """Parse statistics."""
        return asdict(self._counters)

    # -------------------------------------------------------------------
    #  Frame Accumulation State Machine
    # -------------------------------------------------------------------

    def _accumulate(self, byte: int) -> Optional[Frame]:
        """Process a single byte. Returns a Frame when a complete valid frame is found."""
        old_state = self._state

        if self._state == _FrameState.IDLE:
            if byte in (0x00, 0xFF):
                next_state = _FrameState.IDLE
            elif byte == 0x7E:
                next_state = _FrameState.START_OF_FRAME
            else:
                next_state = _FrameState.NOISE

        elif self._state == _FrameState.NOISE:
            if byte in (0x00, 0xFF):
                next_state = _FrameState.IDLE
            elif byte == 0x7E:
                next_state = _FrameState.START_OF_FRAME
            else:
                next_state = _FrameState.NOISE

        elif self._state == _FrameState.START_OF_FRAME:
            if byte == 0x07:
                self._buffer.clear()
                next_state = _FrameState.FRAME
            else:
                next_state = _FrameState.NOISE

        elif self._state == _FrameState.FRAME:
            if byte == 0x7E:
                next_state = _FrameState.FRAME_ESCAPE
            elif len(self._buffer) < MAX_FRAME_SIZE:
                self._buffer.append(byte)
                next_state = _FrameState.FRAME
            else:
                next_state = _FrameState.GIANT

        elif self._state == _FrameState.FRAME_ESCAPE:
            if byte == 0x08:
                # End of frame
                frame = self._decode_frame(self._buffer)
                self._buffer.clear()
                self._state = _FrameState.IDLE
                return frame
            elif byte == 0x07:
                # Restart frame
                self._buffer.clear()
                next_state = _FrameState.FRAME
            else:
                unescaped = _UNESCAPE_MAP.get(byte)
                if unescaped is not None:
                    if len(self._buffer) < MAX_FRAME_SIZE:
                        self._buffer.append(unescaped)
                        next_state = _FrameState.FRAME
                    else:
                        self._buffer.clear()
                        next_state = _FrameState.GIANT
                else:
                    self._buffer.clear()
                    next_state = _FrameState.NOISE

        elif self._state == _FrameState.GIANT:
            if byte == 0x7E:
                next_state = _FrameState.GIANT_ESCAPE
            else:
                next_state = _FrameState.GIANT

        elif self._state == _FrameState.GIANT_ESCAPE:
            if byte == 0x07:
                self._buffer.clear()
                next_state = _FrameState.FRAME
            elif byte == 0x08:
                next_state = _FrameState.IDLE
            else:
                next_state = _FrameState.GIANT

        else:
            next_state = self._state

        # Track noise and giant transitions
        if next_state == _FrameState.NOISE and old_state != _FrameState.NOISE:
            self._counters.noise_bytes += 1
        if next_state == _FrameState.GIANT and old_state not in (_FrameState.GIANT, _FrameState.GIANT_ESCAPE):
            self._buffer.clear()
            self._counters.giants += 1

        self._state = next_state
        return None

    def _decode_frame(self, buffer: bytearray) -> Optional[Frame]:
        """Decode a completed frame from the buffer."""
        if len(buffer) < 6:
            self._counters.runts += 1
            return None

        body = bytes(buffer[:-2])
        expected_crc = int.from_bytes(buffer[-2:], 'little')
        if crc(body) != expected_crc:
            self._counters.crc_errors += 1
            return None

        address = Address.from_bytes(bytes(buffer[0:2]))
        frame_type = int.from_bytes(bytes(buffer[2:4]), 'big')
        payload = bytes(buffer[4:-2])
        return Frame(address, frame_type, payload)

    # -------------------------------------------------------------------
    #  Frame Dispatch
    # -------------------------------------------------------------------

    def _dispatch_frame(self, frame: Frame) -> list[Event]:
        """Route frame to appropriate handler by frame type."""
        try:
            ft = FrameType(frame.frame_type)
        except ValueError:
            return []

        match ft:
            case FrameType.RECEIVE_REQUEST:
                return self._handle_receive_request(frame)
            case FrameType.RECEIVE_RESPONSE:
                return self._handle_receive_response(frame)
            case FrameType.COMMAND_REQUEST:
                return self._handle_command_request(frame)
            case FrameType.COMMAND_RESPONSE:
                return self._handle_command_response(frame)
            case FrameType.ENUMERATION_START_REQUEST:
                return self._handle_enumeration_start(frame)
            case FrameType.ENUMERATION_RESPONSE:
                return self._handle_enumeration_response(frame)
            case FrameType.IDENTIFY_RESPONSE:
                return self._handle_identify_response(frame)
            case FrameType.VERSION_RESPONSE:
                return self._handle_version_response(frame)
            case FrameType.ENUMERATION_END_RESPONSE:
                return self._handle_enumeration_end(frame)
            case _:
                return []

    # -------------------------------------------------------------------
    #  Transport Handlers
    # -------------------------------------------------------------------

    def _handle_receive_request(self, frame: Frame) -> list[Event]:
        """Handle RECEIVE_REQUEST: capture slot time and store packet number."""
        if frame.address.is_from:
            return []
        payload = frame.payload
        if len(payload) < 5:
            return []
        gw_id = frame.address.gateway_id.value
        packet_number = int.from_bytes(payload[2:4], 'big')
        self._rx_packet_numbers[gw_id] = packet_number
        self._captured_slot_times[gw_id] = datetime.now()
        return []

    def _handle_receive_response(self, frame: Frame) -> list[Event]:
        """Handle RECEIVE_RESPONSE: parse variable header, extract PV packets."""
        if not frame.address.is_from:
            return []
        gw_id = frame.address.gateway_id.value
        old_packet_number = self._rx_packet_numbers.get(gw_id)
        if old_packet_number is None:
            return []

        payload = frame.payload
        if len(payload) < 4:
            return []

        # Parse variable-length receive response header
        status_type = int.from_bytes(payload[0:2], 'big')
        if (status_type & 0x00E0) != 0x00E0:
            return []

        offset = 2
        if not (status_type & 0x0001):
            offset += 1  # rx_buffers_used
        if not (status_type & 0x0002):
            offset += 1  # tx_buffers_free
        if not (status_type & 0x0004):
            offset += 2  # unknown_a
        if not (status_type & 0x0008):
            offset += 2  # unknown_b

        if offset >= len(payload):
            return []

        if not (status_type & 0x0010):
            # Full packet number (2 bytes)
            if offset + 2 > len(payload):
                return []
            packet_number = int.from_bytes(payload[offset:offset + 2], 'big')
            offset += 2
        else:
            # Abbreviated packet number (1 byte)
            if offset + 1 > len(payload):
                return []
            lo = payload[offset]
            offset += 1
            packet_number = _interpret_packet_number_lo(lo, old_packet_number)

        if offset + 2 > len(payload):
            return []
        slot_counter = SlotCounter.from_bytes(payload[offset:offset + 2])
        offset += 2

        # Update stored packet number
        self._rx_packet_numbers[gw_id] = packet_number

        # Update slot clock
        capture_time = self._captured_slot_times.pop(gw_id, None)
        if capture_time is not None:
            if gw_id in self._slot_clocks:
                self._slot_clocks[gw_id].set(slot_counter, capture_time)
            else:
                self._slot_clocks[gw_id] = SlotClock(slot_counter, capture_time)

        # Parse received packets
        received_data = payload[offset:]
        events: list[Event] = []
        for header_bytes, pkt_data in iter_received_packets(received_data):
            try:
                header = ReceivedPacketHeader.from_bytes(header_bytes)
                events.extend(self._parse_pv_packet(gw_id, header, pkt_data))
            except (ValueError, IndexError):
                pass
        return events

    def _handle_command_request(self, frame: Frame) -> list[Event]:
        """Handle COMMAND_REQUEST: store awaiting command for correlation."""
        if frame.address.is_from:
            return []
        if len(frame.payload) < 5:
            return []
        gw_id = frame.address.gateway_id.value
        packet_type = frame.payload[3]
        sequence_number = frame.payload[4]

        # Check for retransmit
        old_seq = self._command_sequence_numbers.get(gw_id)
        if old_seq is not None and old_seq == sequence_number:
            pass  # retransmit, update anyway
        self._command_sequence_numbers[gw_id] = sequence_number

        key = (gw_id, sequence_number)
        self._commands_awaiting[key] = (packet_type, frame.payload[5:])
        return []

    def _handle_command_response(self, frame: Frame) -> list[Event]:
        """Handle COMMAND_RESPONSE: correlate with stored request."""
        if not frame.address.is_from:
            return []
        if len(frame.payload) < 5:
            return []
        gw_id = frame.address.gateway_id.value
        resp_packet_type = frame.payload[3]
        resp_seq = frame.payload[4]

        key = (gw_id, resp_seq)
        request_data = self._commands_awaiting.pop(key, None)
        if request_data is None:
            return []
        req_type, req_payload = request_data
        resp_payload = frame.payload[5:]

        return self._handle_command_pair(
            gw_id, req_type, req_payload, resp_packet_type, resp_payload
        )

    def _handle_command_pair(
        self, gw_id: int, req_type: int, req_payload: bytes,
        resp_type: int, resp_payload: bytes,
    ) -> list[Event]:
        """Handle a correlated command request/response pair."""
        if req_type == PacketType.NODE_TABLE_REQUEST and resp_type == PacketType.NODE_TABLE_RESPONSE:
            return self._handle_node_table_command(gw_id, req_payload, resp_payload)
        elif req_type == PacketType.STRING_REQUEST and resp_type == PacketType.STRING_RESPONSE:
            return self._handle_string_command(gw_id, req_payload, resp_payload)
        return []

    # -------------------------------------------------------------------
    #  Enumeration Handlers
    # -------------------------------------------------------------------

    def _handle_enumeration_start(self, frame: Frame) -> list[Event]:
        """Handle ENUMERATION_START_REQUEST."""
        if frame.address.is_from:
            return []
        if frame.address.gateway_id.value != 0:
            return []
        if len(frame.payload) < 6:
            return []
        enum_addr = Address.from_bytes(frame.payload[4:6])
        self._enum_state = _EnumerationState(
            enumeration_gateway_id=enum_addr.gateway_id.value,
            gateway_identities={},
            gateway_versions={},
        )
        return []

    def _handle_enumeration_response(self, frame: Frame) -> list[Event]:
        """Handle ENUMERATION_RESPONSE: observe gateway identity."""
        if not frame.address.is_from:
            return []
        if len(frame.payload) < 8:
            return []
        long_address = LongAddress(frame.payload[0:8])
        gw_id = frame.address.gateway_id.value

        if self._enum_state is not None:
            if gw_id != self._enum_state.enumeration_gateway_id:
                self._enum_state.gateway_identities[gw_id] = long_address
        else:
            self._persistent_state.gateway_identities[gw_id] = long_address
            return self._emit_infrastructure_event()
        return []

    def _handle_identify_response(self, frame: Frame) -> list[Event]:
        """Handle IDENTIFY_RESPONSE: observe gateway identity."""
        if not frame.address.is_from:
            return []
        if len(frame.payload) < 8:
            return []
        long_address = LongAddress(frame.payload[0:8])
        gw_id = frame.address.gateway_id.value

        if self._enum_state is not None:
            if gw_id != self._enum_state.enumeration_gateway_id:
                self._enum_state.gateway_identities[gw_id] = long_address
        else:
            self._persistent_state.gateway_identities[gw_id] = long_address
            return self._emit_infrastructure_event()
        return []

    def _handle_version_response(self, frame: Frame) -> list[Event]:
        """Handle VERSION_RESPONSE: observe gateway version string."""
        if not frame.address.is_from:
            return []
        try:
            version = frame.payload.decode('utf-8', errors='replace')
        except Exception:
            return []
        if not version:
            return []
        gw_id = frame.address.gateway_id.value

        if self._enum_state is not None:
            self._enum_state.gateway_versions[gw_id] = version
        else:
            self._persistent_state.gateway_versions[gw_id] = version
            return self._emit_infrastructure_event()
        return []

    def _handle_enumeration_end(self, frame: Frame) -> list[Event]:
        """Handle ENUMERATION_END_RESPONSE: apply enumeration atomically."""
        if not frame.address.is_from:
            return []
        if self._enum_state is not None:
            self._persistent_state.gateway_identities = dict(
                self._enum_state.gateway_identities
            )
            self._persistent_state.gateway_versions = dict(
                self._enum_state.gateway_versions
            )
            self._enum_state = None
            return self._emit_infrastructure_event()
        return []

    # -------------------------------------------------------------------
    #  PV Packet Parsing
    # -------------------------------------------------------------------

    def _parse_pv_packet(
        self, gw_id: int, header: ReceivedPacketHeader, data: bytes,
    ) -> list[Event]:
        """Parse a PV application packet and generate events."""
        node_addr = header.node_address
        if node_addr == 0:
            return []  # broadcast, skip

        try:
            pkt_type = header.packet_type
        except ValueError:
            return []

        if pkt_type == PacketType.POWER_REPORT:
            return self._handle_power_report(gw_id, node_addr, data)
        elif pkt_type == PacketType.STRING_RESPONSE:
            return self._handle_string_response(gw_id, node_addr, data)
        elif pkt_type == PacketType.TOPOLOGY_REPORT:
            return self._handle_topology_report(gw_id, node_addr, data)
        return []

    def _handle_power_report(
        self, gw_id: int, node_id: int, data: bytes,
    ) -> list[Event]:
        """Parse a power report and generate PowerReportEvent."""
        try:
            if len(data) == 15:
                # Extended 15-byte format: first 13 bytes are standard
                report = PowerReport.from_bytes(data[:13])
            elif len(data) >= 13:
                report = PowerReport.from_bytes(data[:13])
            else:
                return []
        except (ValueError, IndexError):
            return []

        slot_clock = self._slot_clocks.get(gw_id)
        if slot_clock is None:
            logger.warning(
                "No slot clock for gateway %d, discarding power report", gw_id
            )
            return []

        timestamp = slot_clock.get(report.slot_counter)

        # Look up barcode from persistent state
        barcode = None
        gw_table = self._persistent_state.gateway_node_tables.get(gw_id)
        if gw_table is not None:
            long_addr = gw_table.get(node_id)
            if long_addr is not None:
                barcode = barcode_from_address(long_addr.data)

        event = PowerReportEvent(
            gateway_id=gw_id,
            node_id=node_id,
            barcode=barcode,
            voltage_in=report.voltage_in,
            voltage_out=report.voltage_out,
            current=report.current,
            temperature=report.temperature,
            dc_dc_duty_cycle=report.duty_cycle,
            rssi=report.rssi,
            timestamp=timestamp,
        )
        return [event]

    def _handle_string_response(
        self, gw_id: int, node_id: int, data: bytes,
    ) -> list[Event]:
        """Parse string response from a PV node."""
        content = data.decode('utf-8', errors='replace')
        return [StringEvent(
            gateway_id=gw_id, node_id=node_id,
            direction='response', content=content,
            timestamp=datetime.now(),
        )]

    def _handle_topology_report(
        self, gw_id: int, node_id: int, data: bytes,
    ) -> list[Event]:
        """Generate TopologyEvent from raw topology report."""
        return [TopologyEvent(
            gateway_id=gw_id, node_id=node_id, data=data,
            timestamp=datetime.now(),
        )]

    def _handle_node_table_command(
        self, gw_id: int, req_payload: bytes, resp_payload: bytes,
    ) -> list[Event]:
        """Handle NODE_TABLE command pair: accumulate pages."""
        if len(req_payload) < 2:
            return []
        start_address = NodeAddress.from_bytes(req_payload[0:2])
        if len(resp_payload) < 1:
            return []
        entries_count = resp_payload[0]
        entries_data = resp_payload[1:]
        if len(entries_data) != entries_count * 10:
            return []  # corrupt
        entries = []
        for i in range(entries_count):
            off = i * 10
            node_addr = NodeAddress.from_bytes(entries_data[off:off + 2])
            long_addr = LongAddress(entries_data[off + 2:off + 10])
            entries.append((node_addr, long_addr))

        builder = self._node_table_builders.setdefault(
            gw_id, NodeTableBuilder()
        )
        result = builder.push(start_address, entries)
        if result is not None:
            self._persistent_state.gateway_node_tables[gw_id] = result
            self._save_persistent_state()
            return self._emit_infrastructure_event()
        return []

    def _handle_string_command(
        self, gw_id: int, req_payload: bytes, resp_payload: bytes,
    ) -> list[Event]:
        """Handle STRING command pair: emit StringEvent for request."""
        if len(req_payload) < 2:
            return []
        node_addr = NodeAddress.from_bytes(req_payload[0:2])
        request_str = req_payload[2:].decode('utf-8', errors='replace')
        return [StringEvent(
            gateway_id=gw_id, node_id=node_addr.value,
            direction='request', content=request_str,
            timestamp=datetime.now(),
        )]

    # -------------------------------------------------------------------
    #  Infrastructure Event Helper
    # -------------------------------------------------------------------

    def _emit_infrastructure_event(self) -> list[Event]:
        """Build an InfrastructureEvent from current persistent state."""
        gateways: dict = {}
        for gw_id, addr in self._persistent_state.gateway_identities.items():
            gateways[gw_id] = {
                'address': str(addr),
                'version': self._persistent_state.gateway_versions.get(gw_id),
            }
        for gw_id, ver in self._persistent_state.gateway_versions.items():
            if gw_id not in gateways:
                gateways[gw_id] = {'address': None, 'version': ver}

        nodes: dict = {}
        for gw_id_key, table in self._persistent_state.gateway_node_tables.items():
            for node_id_val, long_addr in table.items():
                barcode = barcode_from_address(long_addr.data)
                nodes[node_id_val] = {
                    'address': str(long_addr),
                    'barcode': barcode,
                }

        self._save_persistent_state()
        return [InfrastructureEvent(
            gateways=gateways, nodes=nodes, timestamp=datetime.now(),
        )]

    def _save_persistent_state(self):
        """Save persistent state if a state file is configured."""
        if self._state_file is not None:
            try:
                self._persistent_state.save(self._state_file)
            except OSError as e:
                logger.error("Failed to save persistent state: %s", e)
