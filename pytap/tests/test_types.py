"""Tests for protocol types."""

import struct
import pytest
from pytap.core.types import (
    GatewayID, Address, FrameType, Frame,
    NodeID, NodeAddress, LongAddress, RSSI, SlotCounter,
    PacketType, ReceivedPacketHeader, U12Pair, PowerReport,
    SLOTS_PER_EPOCH, MAX_SLOT_NUMBER,
    iter_received_packets,
)


# ---- GatewayID ----

def test_gateway_id_valid():
    assert GatewayID(0).value == 0
    assert GatewayID(32767).value == 32767


def test_gateway_id_invalid():
    with pytest.raises(ValueError):
        GatewayID(-1)
    with pytest.raises(ValueError):
        GatewayID(32768)


# ---- Address ----

def test_address_from_bytes_controller_to_gateway():
    """Bit 15 = 0 → is_from = False (controller→gateway)."""
    data = struct.pack('>H', 0x1201)  # 0001 0010 0000 0001
    addr = Address.from_bytes(data)
    assert addr.is_from is False
    assert addr.gateway_id.value == 0x1201


def test_address_from_bytes_gateway_to_controller():
    """Bit 15 = 1 → is_from = True (gateway→controller)."""
    data = struct.pack('>H', 0x9201)  # 1001 0010 0000 0001
    addr = Address.from_bytes(data)
    assert addr.is_from is True
    assert addr.gateway_id.value == 0x1201


# ---- FrameType ----

def test_frame_type_values():
    """Verify key FrameType enum values."""
    assert FrameType.PING_REQUEST == 0x0B00
    assert FrameType.PING_RESPONSE == 0x0B01
    assert FrameType.RECEIVE_REQUEST == 0x0148
    assert FrameType.RECEIVE_RESPONSE == 0x0149
    assert FrameType.ENUMERATION_REQUEST == 0x0038
    assert FrameType.ENUMERATION_RESPONSE == 0x0039
    assert FrameType.VERSION_REQUEST == 0x000A
    assert FrameType.VERSION_RESPONSE == 0x000B
    assert len(FrameType) == 18


# ---- SlotCounter ----

def test_slot_counter_epoch():
    # epoch=2, slot_number=1000
    raw = (2 << 14) | 1000
    sc = SlotCounter(raw)
    assert sc.epoch == 2
    assert sc.slot_number == 1000


def test_slot_counter_slots_since_same_epoch():
    past = SlotCounter((1 << 14) | 1000)
    current = SlotCounter((1 << 14) | 2000)
    assert current.slots_since(past) == 1000


def test_slot_counter_slots_since_crossing_epoch():
    past = SlotCounter((0 << 14) | 11000)
    current = SlotCounter((1 << 14) | 500)
    # Should be (11999 - 11000 + 1) + 500 = 1500
    assert current.slots_since(past) == 1500


def test_slot_counter_slots_since_wrapping():
    past = SlotCounter((3 << 14) | 5000)
    current = SlotCounter((0 << 14) | 1000)
    # epoch_diff = (0 - 3) % 4 = 1
    # (11999 - 5000 + 1) + 1000 = 8000
    assert current.slots_since(past) == 8000


# ---- U12Pair ----

def test_u12_pair_from_bytes():
    data = bytes([0xAB, 0xCD, 0xEF])
    pair = U12Pair.from_bytes(data)
    assert pair.first == 0xABC
    assert pair.second == 0xDEF


# ---- ReceivedPacketHeader ----

def test_received_packet_header_from_bytes():
    data = bytes([0x31, 0x00, 0x10, 0x00, 0x20, 0x05, 0x0D])
    hdr = ReceivedPacketHeader.from_bytes(data)
    assert hdr.packet_type == 0x31  # POWER_REPORT
    assert hdr.node_address == 0x0010
    assert hdr.short_address == 0x0020
    assert hdr.dsn == 5
    assert hdr.data_length == 13


def test_received_packet_header_too_short():
    with pytest.raises(ValueError):
        ReceivedPacketHeader.from_bytes(b'\x00\x01\x02')


# ---- PowerReport ----

def test_power_report_from_bytes():
    """Test power report with known values."""
    # voltage_in_out: first=0x320 (800), second=0x190 (400)
    # → voltage_in=40.0V, voltage_out=40.0V
    b0, b1, b2 = 0x32, 0x01, 0x90
    # duty_cycle raw=128 → 128/255
    b3 = 128
    # current_temp: first=0x1F4 (500), second=0x19B (411)
    # → current=2.5A, temp=41.1°C
    b4, b5, b6 = 0x1F, 0x41, 0x9B
    # unknown
    b7, b8, b9 = 0x00, 0x00, 0x00
    # slot_counter
    b10, b11 = 0x40, 0x00
    # rssi
    b12 = 0x80

    data = bytes([b0, b1, b2, b3, b4, b5, b6, b7, b8, b9, b10, b11, b12])
    pr = PowerReport.from_bytes(data)
    assert pr.voltage_in == pytest.approx(40.0)
    assert pr.voltage_out == pytest.approx(40.0)
    assert pr.current == pytest.approx(2.5)
    assert pr.duty_cycle == pytest.approx(128 / 255)
    assert pr.rssi == 0x80


def test_power_report_negative_temp():
    """Test sign extension for negative temperature."""
    # current_temp second = 0xFFF → sign extend → -1 → -0.1°C
    # bytes: first=0 → b4=0x00, b5 combined: (0 << 4 | 0xF) = 0x0F, b6=0xFF
    data = bytes([
        0x00, 0x00, 0x00,  # voltage_in_out
        0x00,               # duty cycle
        0x00, 0x0F, 0xFF,  # current_temp: first=0, second=0xFFF
        0x00, 0x00, 0x00,  # unknown
        0x00, 0x00,          # slot_counter
        0x00,               # rssi
    ])
    pr = PowerReport.from_bytes(data)
    assert pr.temperature == pytest.approx(-0.1)


# ---- LongAddress ----

def test_long_address_str():
    addr = LongAddress(bytes([0x04, 0xC0, 0x5B, 0x30, 0x00, 0x02, 0xBE, 0x16]))
    assert str(addr) == '04:C0:5B:30:00:02:BE:16'


def test_long_address_from_str():
    addr = LongAddress.from_str('04:C0:5B:30:00:02:BE:16')
    assert addr.data == bytes([0x04, 0xC0, 0x5B, 0x30, 0x00, 0x02, 0xBE, 0x16])


# ---- NodeID ----

def test_node_id_valid():
    assert NodeID(1).value == 1
    assert NodeID(65535).value == 65535


def test_node_id_invalid():
    with pytest.raises(ValueError):
        NodeID(0)
    with pytest.raises(ValueError):
        NodeID(65536)


# ---- iter_received_packets ----

def test_iter_received_packets():
    """Pack two packets and iterate over them."""
    pkt1_hdr = bytes([0x31, 0x00, 0x01, 0x00, 0x02, 0x01, 0x03])  # data_length=3
    pkt1_data = bytes([0xAA, 0xBB, 0xCC])
    pkt2_hdr = bytes([0x07, 0x00, 0x03, 0x00, 0x04, 0x02, 0x02])  # data_length=2
    pkt2_data = bytes([0xDD, 0xEE])

    data = pkt1_hdr + pkt1_data + pkt2_hdr + pkt2_data
    pkts = list(iter_received_packets(data))
    assert len(pkts) == 2
    assert pkts[0] == (pkt1_hdr, pkt1_data)
    assert pkts[1] == (pkt2_hdr, pkt2_data)


def test_iter_received_packets_truncated():
    """Truncated data stops iteration gracefully."""
    data = bytes([0x31, 0x00, 0x01, 0x00, 0x02, 0x01, 0x05, 0xAA, 0xBB])
    pkts = list(iter_received_packets(data))
    assert len(pkts) == 0  # data_length=5 but only 2 data bytes available
