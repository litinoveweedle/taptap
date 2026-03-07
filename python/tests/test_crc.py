"""Tests for CRC calculation."""

import pytest
from taptap.gateway.link.crc import crc


def test_crc_empty():
    """Test CRC of empty buffer."""
    assert crc(b'') == 0x8408


def test_crc_single_byte():
    """Test CRC of single byte."""
    assert crc(bytes([0x92])) == 0x3B57


def test_crc_two_bytes():
    """Test CRC of two bytes."""
    assert crc(bytes([0x92, 0x01])) == 0x3788


def test_crc_known_vector_1():
    """Test CRC with known vector 1."""
    data = bytes([0x92, 0x01, 0x01, 0x49, 0x00, 0xFF, 0x7C, 0xDB, 0xC2])
    assert crc(data) == 0x85A3


def test_crc_known_vector_2():
    """Test CRC with known vector 2."""
    data = bytes([0x12, 0x01, 0x01, 0x48, 0x00, 0x01, 0x18, 0x82, 0x04])
    assert crc(data) == 0x5DCF


def test_crc_deterministic():
    """Test that CRC is deterministic."""
    data = bytes([0x01, 0x02, 0x03, 0x04])
    assert crc(data) == crc(data)


def test_crc_different_data():
    """Test that different data produces different CRC."""
    data1 = bytes([0x01, 0x02, 0x03])
    data2 = bytes([0x01, 0x02, 0x04])
    assert crc(data1) != crc(data2)
