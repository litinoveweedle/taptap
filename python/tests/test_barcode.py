"""Tests for barcode encoding and decoding."""

import pytest
from taptap.barcode import Barcode


def test_barcode_from_address():
    """Test barcode creation from address."""
    address = bytes.fromhex('04C05B409A57A23E')
    barcode = Barcode(address)
    assert barcode.address == address


def test_barcode_to_string():
    """Test barcode string formatting."""
    # Test with known value from Rust tests
    address = bytes.fromhex('04C05B40009A57A2')
    barcode = Barcode(address)
    s = str(barcode)
    
    # Should be "4-9A57A2L" (length varies due to leading zero skipping)
    assert s == "4-9A57A2L"
    assert s[1] == '-'
    assert s[0] in '0123456789ABCDEF'


def test_barcode_roundtrip():
    """Test barcode encoding and decoding roundtrip."""
    address = bytes.fromhex('04C05B409A57A23E')
    barcode1 = Barcode(address)
    s = str(barcode1)
    barcode2 = Barcode.from_string(s)
    
    assert barcode1 == barcode2
    assert barcode1.address == barcode2.address


def test_barcode_invalid_length():
    """Test barcode rejects invalid address length."""
    with pytest.raises(ValueError, match="must be 8 bytes"):
        Barcode(b'\x00\x00')


def test_barcode_invalid_format():
    """Test barcode string parsing rejects invalid format."""
    with pytest.raises(ValueError):
        Barcode.from_string("invalid")
    
    with pytest.raises(ValueError):
        Barcode.from_string("4X9A57A2L")  # Wrong separator


def test_barcode_crc_validation():
    """Test barcode CRC validation."""
    # Create a valid barcode string and corrupt the CRC
    address = bytes.fromhex('04C05B409A57A23E')
    barcode = Barcode(address)
    valid = str(barcode)
    
    # Corrupt CRC (last character)
    invalid = valid[:-1] + ('X' if valid[-1] != 'X' else 'Y')
    
    with pytest.raises(ValueError, match="CRC"):
        Barcode.from_string(invalid)


def test_barcode_equality():
    """Test barcode equality."""
    address1 = bytes.fromhex('04C05B409A57A23E')
    address2 = bytes.fromhex('04C05B409A57A23E')
    address3 = bytes.fromhex('04C05B409A57A23F')
    
    barcode1 = Barcode(address1)
    barcode2 = Barcode(address2)
    barcode3 = Barcode(address3)
    
    assert barcode1 == barcode2
    assert barcode1 != barcode3
    assert barcode2 != barcode3
