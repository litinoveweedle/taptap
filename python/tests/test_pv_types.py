"""Tests for PV network types."""

import pytest
from taptap.pv.network.types import (
    NodeID,
    NodeAddress,
    ShortAddress,
    LongAddress,
    DSN,
    RSSI,
    ReceivedPacketHeader,
)


def test_node_id_valid():
    """Test NodeID with valid values."""
    node = NodeID(116)
    assert node.value == 116
    assert int(node) == 116
    assert str(node) == "116"


def test_node_id_invalid():
    """Test NodeID rejects invalid values."""
    with pytest.raises(ValueError, match="must be 1-65535"):
        NodeID(0)
    
    with pytest.raises(ValueError):
        NodeID(0x10000)


def test_node_id_constants():
    """Test NodeID constants."""
    assert NodeID.GATEWAY == 1
    assert NodeID.MAX == 0xFFFF


def test_node_id_successor():
    """Test NodeID successor."""
    node = NodeID(100)
    next_node = node.successor()
    assert next_node is not None
    assert next_node.value == 101
    
    # At MAX
    max_node = NodeID(NodeID.MAX)
    assert max_node.successor() is None


def test_node_address_broadcast():
    """Test NodeAddress broadcast."""
    addr = NodeAddress(0)
    assert addr.value == 0
    assert addr.to_node_id() is None
    assert str(addr) == "Broadcast"


def test_node_address_node():
    """Test NodeAddress with node ID."""
    addr = NodeAddress(116)
    node_id = addr.to_node_id()
    assert node_id is not None
    assert node_id.value == 116


def test_node_address_from_node_id():
    """Test creating NodeAddress from NodeID."""
    addr = NodeAddress.from_node_id(NodeID(116))
    assert addr.value == 116
    
    broadcast = NodeAddress.from_node_id(None)
    assert broadcast.value == 0


def test_short_address():
    """Test ShortAddress."""
    addr = ShortAddress(0x1234)
    assert addr.value == 0x1234
    assert str(addr) == "0x1234"
    
    # Roundtrip
    data = addr.to_bytes()
    assert len(data) == 2
    decoded = ShortAddress.from_bytes(data)
    assert decoded == addr


def test_long_address():
    """Test LongAddress."""
    data = bytes.fromhex('04C05B40009A57A2')
    addr = LongAddress(data)
    assert addr.address == data
    assert str(addr) == "04:C0:5B:40:00:9A:57:A2"
    
    # Roundtrip
    encoded = addr.to_bytes()
    decoded = LongAddress.from_bytes(encoded)
    assert decoded == addr


def test_long_address_barcode():
    """Test LongAddress to Barcode conversion."""
    data = bytes.fromhex('04C05B40009A57A2')
    addr = LongAddress(data)
    barcode = addr.barcode()
    assert str(barcode) == "4-9A57A2L"


def test_dsn():
    """Test DSN."""
    dsn = DSN(42)
    assert dsn.value == 42
    assert int(dsn) == 42
    assert str(dsn) == "42"


def test_dsn_wrapping_add():
    """Test DSN wrapping addition."""
    dsn = DSN(250)
    new_dsn = dsn + 10
    assert new_dsn.value == 4  # (250 + 10) & 0xFF = 4


def test_rssi():
    """Test RSSI."""
    rssi = RSSI(132)
    assert rssi.value == 132
    assert int(rssi) == 132
    assert str(rssi) == "132"


def test_rssi_invalid():
    """Test RSSI rejects invalid values."""
    with pytest.raises(ValueError, match="must be 0-255"):
        RSSI(256)
    
    with pytest.raises(ValueError):
        RSSI(-1)


def test_received_packet_header():
    """Test ReceivedPacketHeader parsing."""
    # Create test data: packet_type, node_addr, short_addr, dsn, data_length
    data = bytes([
        0x31,  # POWER_REPORT
        0x00, 0x74,  # Node 116
        0x12, 0x34,  # Short address
        0x42,  # DSN 66
        0x0D,  # Data length 13
    ])
    
    header = ReceivedPacketHeader.from_bytes(data)
    assert header.packet_type == 0x31
    assert header.node_address.value == 116
    assert header.short_address.value == 0x1234
    assert header.dsn.value == 0x42
    assert header.data_length == 0x0D


def test_received_packet_header_roundtrip():
    """Test ReceivedPacketHeader encoding/decoding."""
    header = ReceivedPacketHeader(
        packet_type=0x31,
        node_address=NodeAddress(116),
        short_address=ShortAddress(0x1234),
        dsn=DSN(0x42),
        data_length=13
    )
    
    data = header.to_bytes()
    assert len(data) == 7  # 1 + 2 + 2 + 1 + 1 = 7 bytes total
    
    decoded = ReceivedPacketHeader.from_bytes(data)
    assert decoded == header
