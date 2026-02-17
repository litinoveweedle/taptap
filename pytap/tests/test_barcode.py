"""Tests for the barcode encoding/decoding module."""

import pytest
from pytap.core.barcode import encode_barcode, decode_barcode, barcode_from_address


# Known address from ENUMERATION_SEQUENCE
KNOWN_ADDRESS = bytes([0x04, 0xC0, 0x5B, 0x30, 0x00, 0x02, 0xBE, 0x16])


def test_encode_known_address():
    """Encoding a known address produces a valid barcode string."""
    barcode = encode_barcode(KNOWN_ADDRESS)
    assert barcode is not None
    assert '-' in barcode
    assert len(barcode) >= 5


def test_decode_roundtrip():
    """Encode then decode returns the same address."""
    barcode = encode_barcode(KNOWN_ADDRESS)
    decoded = decode_barcode(barcode)
    assert decoded == KNOWN_ADDRESS


def test_non_tigo_prefix_returns_none():
    """Non-Tigo prefix returns None."""
    addr = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77])
    assert encode_barcode(addr) is None


def test_invalid_check_character_raises():
    """Invalid check character raises ValueError."""
    barcode = encode_barcode(KNOWN_ADDRESS)
    # Replace check character with a wrong one
    alphabet = 'GHJKLMNPRSTVWXYZ'
    wrong_char = alphabet[(alphabet.index(barcode[-1]) + 1) % len(alphabet)]
    bad_barcode = barcode[:-1] + wrong_char
    with pytest.raises(ValueError, match="CRC mismatch"):
        decode_barcode(bad_barcode)


def test_barcode_from_address_convenience():
    """barcode_from_address returns same as encode_barcode."""
    assert barcode_from_address(KNOWN_ADDRESS) == encode_barcode(KNOWN_ADDRESS)


def test_barcode_from_address_invalid():
    """barcode_from_address returns None for invalid input."""
    assert barcode_from_address(b'') is None


def test_encode_wrong_length_raises():
    """Address that isn't 8 bytes raises ValueError."""
    with pytest.raises(ValueError):
        encode_barcode(b'\x04\xC0\x5B')


def test_decode_too_short_raises():
    """Barcode shorter than 5 chars raises ValueError."""
    with pytest.raises(ValueError):
        decode_barcode("X-1")


def test_decode_missing_dash_raises():
    """Barcode without dash at position 1 raises ValueError."""
    with pytest.raises(ValueError):
        decode_barcode("X1234567A")
