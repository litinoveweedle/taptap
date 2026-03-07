"""Tests for the CRC-16-CCITT module."""

from pytap.core.crc import crc


def test_crc_empty():
    """Empty buffer returns initial value 0x8408."""
    assert crc(b'') == 33800  # 0x8408


def test_crc_single_byte():
    """Single byte 0x92."""
    assert crc(bytes([0x92])) == 15191


def test_crc_two_bytes():
    """Two bytes 0x92, 0x01."""
    assert crc(bytes([0x92, 0x01])) == 14216


def test_crc_different_buffers_differ():
    """Two different non-empty buffers produce different CRC values."""
    assert crc(b'\x01\x02') != crc(b'\x03\x04')


def test_crc_known_frame():
    """Validate CRC against a known frame from the ENUMERATION_SEQUENCE.

    First frame body (after unescaping): 0x12 0x01 0x0B 0x00 0x01
    CRC bytes (little-endian): 0xFE 0x83 → 0x83FE = 33790
    """
    body = bytes([0x12, 0x01, 0x0B, 0x00, 0x01])
    result = crc(body)
    # The CRC in the frame is little-endian 0xFE 0x83
    expected = int.from_bytes(bytes([0xFE, 0x83]), 'little')
    assert result == expected


def test_crc_deterministic():
    """Same input always produces same output."""
    data = b'\xAA\xBB\xCC\xDD'
    assert crc(data) == crc(data)
