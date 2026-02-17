"""Tests for byte escaping."""

import pytest
from taptap.gateway.link.escaping import (
    escape,
    unescape,
    escaped_length,
    unescaped_byte,
    InvalidEscapeSequence,
)


# Test examples from Rust implementation
EXAMPLES = [
    (b"", b""),
    (b"~", b"\x7e\x00"),
    (b"hello", b"hello"),
    (b"~hello~", b"\x7e\x00hello\x7e\x00"),
    (
        b"\x7e\xa3\xa4\xa5\x23\x24\x25abcdef",
        b"\x7e\x00\x7e\x05\x7e\x04\x7e\x06\x7e\x02\x7e\x01\x7e\x03abcdef",
    ),
    (
        bytes([0x92, 0x01, 0x01, 0x49, 0x00, 0xFF, 0x7C, 0xDB, 0xC2, 0xA3, 0x85]),
        bytes([0x92, 0x01, 0x01, 0x49, 0x00, 0xFF, 0x7C, 0xDB, 0xC2, 0x7E, 0x05, 0x85]),
    ),
]


def test_escaped_length():
    """Test escaped_length calculation."""
    for raw, escaped in EXAMPLES:
        assert escaped_length(raw) == len(escaped), f"Failed for {raw!r}"


def test_escape():
    """Test escape function."""
    for raw, escaped in EXAMPLES:
        assert escape(raw) == escaped, f"Failed for {raw!r}"


def test_unescape():
    """Test unescape function."""
    for raw, escaped in EXAMPLES:
        assert unescape(escaped) == raw, f"Failed for {escaped!r}"


def test_roundtrip():
    """Test escape/unescape roundtrip."""
    for raw, _ in EXAMPLES:
        assert unescape(escape(raw)) == raw


def test_unescaped_byte_valid():
    """Test unescaped_byte with valid sequences."""
    assert unescaped_byte(0x00) == 0x7e
    assert unescaped_byte(0x01) == 0x24
    assert unescaped_byte(0x02) == 0x23
    assert unescaped_byte(0x03) == 0x25
    assert unescaped_byte(0x04) == 0xa4
    assert unescaped_byte(0x05) == 0xa3
    assert unescaped_byte(0x06) == 0xa5


def test_unescaped_byte_invalid():
    """Test unescaped_byte with invalid sequences."""
    with pytest.raises(InvalidEscapeSequence):
        unescaped_byte(0x07)
    
    with pytest.raises(InvalidEscapeSequence):
        unescaped_byte(0xFF)


def test_unescape_incomplete():
    """Test unescape with incomplete escape sequence."""
    with pytest.raises(InvalidEscapeSequence, match="Incomplete"):
        unescape(b"\x7e")


def test_unescape_invalid_sequence():
    """Test unescape with invalid escape sequence."""
    with pytest.raises(InvalidEscapeSequence):
        unescape(b"\x7e\xFF")


def test_escape_all_special_bytes():
    """Test escaping of all special bytes."""
    special_bytes = bytes([0x7e, 0x23, 0x24, 0x25, 0xa3, 0xa4, 0xa5])
    escaped = escape(special_bytes)
    
    # Each special byte should be escaped to 2 bytes
    assert len(escaped) == len(special_bytes) * 2
    
    # Verify roundtrip
    assert unescape(escaped) == special_bytes
