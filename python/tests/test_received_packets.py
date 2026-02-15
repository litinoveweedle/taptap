"""Tests for PV network received packets iterator (TEST-3)."""

import pytest
from taptap.pv.network.received_packets import ReceivedPackets, PacketTooShortError


def test_empty_buffer():
    """Empty buffer yields no packets."""
    packets = ReceivedPackets(b"")
    result = list(packets)
    assert result == []


def test_single_packet_zero_data():
    """Single 7-byte header with data_length=0."""
    header = bytes([0x07, 0x00, 0x0A, 0xFF, 0xFF, 0x01, 0x00])  # data_length=0
    packets = ReceivedPackets(header)
    result = list(packets)

    assert len(result) == 1
    hdr, data = result[0]
    assert hdr == header
    assert data == b""


def test_single_packet_with_data():
    """Single packet with 3 bytes of data."""
    header = bytes([0x07, 0x00, 0x0A, 0x01, 0x14, 0x63, 0x03])  # data_length=3
    payload = bytes([0xAA, 0xBB, 0xCC])
    packets = ReceivedPackets(header + payload)
    result = list(packets)

    assert len(result) == 1
    hdr, data = result[0]
    assert hdr == header
    assert data == payload


def test_multiple_packets():
    """Two packets in one buffer."""
    pkt1_hdr = bytes([0x07, 0x00, 0x01, 0xFF, 0xFF, 0x00, 0x02])  # 2 bytes data
    pkt1_data = bytes([0x11, 0x22])
    pkt2_hdr = bytes([0x08, 0x00, 0x02, 0xFF, 0xFF, 0x01, 0x01])  # 1 byte data
    pkt2_data = bytes([0x33])

    packets = ReceivedPackets(pkt1_hdr + pkt1_data + pkt2_hdr + pkt2_data)
    result = list(packets)

    assert len(result) == 2
    assert result[0] == (pkt1_hdr, pkt1_data)
    assert result[1] == (pkt2_hdr, pkt2_data)


def test_header_too_short_raises():
    """Less than 7 bytes raises PacketTooShortError."""
    packets = ReceivedPackets(bytes([0x01, 0x02, 0x03]))
    with pytest.raises(PacketTooShortError):
        list(packets)


def test_data_too_short_raises():
    """Header says 5 bytes of data but only 2 remain."""
    header = bytes([0x07, 0x00, 0x0A, 0xFF, 0xFF, 0x01, 0x05])  # data_length=5
    payload = bytes([0xAA, 0xBB])  # only 2
    packets = ReceivedPackets(header + payload)
    with pytest.raises(PacketTooShortError):
        list(packets)


def test_data_length_is_byte_6_not_byte_5():
    """Verify data_length comes from index 6 (not 5 / dsn)."""
    # byte[5]=0x42 (dsn), byte[6]=0x02 (data_length)
    header = bytes([0x07, 0x00, 0x0A, 0xFF, 0xFF, 0x42, 0x02])
    payload = bytes([0xDE, 0xAD])
    packets = ReceivedPackets(header + payload)
    result = list(packets)

    assert len(result) == 1
    _, data = result[0]
    # If data_length were byte[5]=0x42, we'd need 66 bytes and get PacketTooShortError
    assert data == payload


def test_remaining_after_iteration():
    """remaining property returns unprocessed bytes."""
    header = bytes([0x07, 0x00, 0x0A, 0xFF, 0xFF, 0x01, 0x01])  # 1 byte data
    payload = bytes([0xAA])
    packets = ReceivedPackets(header + payload)

    # Consume
    list(packets)
    assert packets.remaining == b""


def test_header_size_constant():
    """HEADER_SIZE should be 7 (includes data_length byte)."""
    assert ReceivedPackets.HEADER_SIZE == 7
