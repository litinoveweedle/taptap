"""Tests for PV application types."""

import pytest
from taptap.pv.application.types import (
    PacketType,
    U12Pair,
    PowerReport,
    PowerReport15,
)
from taptap.pv.link.slot_counter import SlotCounter, SlotEpoch, SlotNumber
from taptap.pv.network.types import RSSI


def test_packet_type():
    """Test PacketType enum."""
    assert PacketType.POWER_REPORT == 0x31
    assert PacketType.NODE_TABLE_REQUEST == 0x26
    assert PacketType.STRING_REQUEST == 0x06


def test_u12_pair_from_bytes():
    """Test U12Pair from bytes."""
    # Example from Rust tests: [0x2b, 0x61, 0x58]
    pair = U12Pair(bytes([0x2b, 0x61, 0x58]))
    assert pair.first == 0x2b6  # 694
    assert pair.second == 0x158  # 344


def test_u12_pair_from_values():
    """Test U12Pair from values."""
    pair = U12Pair.from_values(0x2b6, 0x158)
    assert pair.first == 0x2b6
    assert pair.second == 0x158
    assert pair._data == bytes([0x2b, 0x61, 0x58])


def test_u12_pair_roundtrip():
    """Test U12Pair encode/decode roundtrip."""
    original = U12Pair(bytes([0x2b, 0x61, 0x58]))
    reconstructed = U12Pair.from_values(original.first, original.second)
    assert original == reconstructed


def test_u12_pair_invalid_values():
    """Test U12Pair rejects invalid values."""
    with pytest.raises(ValueError, match="12-bit"):
        U12Pair.from_values(0x1000, 0x100)  # First too large
    
    with pytest.raises(ValueError, match="12-bit"):
        U12Pair.from_values(0x100, 0x1000)  # Second too large


def test_u12_pair_invalid_size():
    """Test U12Pair rejects wrong size."""
    with pytest.raises(ValueError, match="3 bytes"):
        U12Pair(bytes([0x01, 0x02]))


def test_power_report_parsing():
    """Test PowerReport parsing from bytes."""
    # Create 13-byte power report
    data = bytes([
        # voltage_in_and_voltage_out (3 bytes)
        0x26, 0x51, 0x2E,  # voltage_in=613 (30.65V), voltage_out=302 (30.2V)
        # dc_dc_duty_cycle (1 byte)
        0xFF,  # 255 = 100%
        # current_and_temperature (3 bytes)
        0x22, 0xB1, 0x0C,  # current=555 (2.775A), temperature=268 (26.8C)
        # unknown (3 bytes)
        0x00, 0x00, 0x00,
        # slot_counter (2 bytes) - Epoch 4, slot 1234
        0x44, 0xD2,
        # rssi (1 byte)
        0x84,  # 132
    ])
    
    report = PowerReport.from_bytes(data)
    
    # Check parsed values
    assert abs(report.voltage_in - 30.65) < 0.01
    assert abs(report.voltage_out - 30.2) < 0.01
    assert abs(report.current - 2.775) < 0.001
    assert report.dc_dc_duty_cycle == 255
    assert abs(report.duty_cycle - 1.0) < 0.001
    assert abs(report.temperature - 26.8) < 0.01
    assert report.rssi.value == 132


def test_power_report_temperature_negative():
    """Test PowerReport with negative temperature."""
    # Temperature value with bit 11 set (negative)
    data = bytes([
        0x26, 0x51, 0x2E,  # voltages
        0xFF,  # duty cycle
        0x22, 0xBF, 0xFF,  # current=555, temperature=0xFFF (sign-extended = -1)
        0x00, 0x00, 0x00,  # unknown
        0x44, 0xD2,  # slot counter
        0x84,  # rssi
    ])
    
    report = PowerReport.from_bytes(data)
    assert abs(report.temperature - (-0.1)) < 0.01


def test_power_report_roundtrip():
    """Test PowerReport encode/decode roundtrip."""
    original_data = bytes([
        0x26, 0x51, 0x2E,
        0xFF,
        0x22, 0xB1, 0x0C,
        0x00, 0x00, 0x00,
        0x44, 0xD2,
        0x84,
    ])
    
    report = PowerReport.from_bytes(original_data)
    encoded = report.to_bytes()
    
    assert encoded == original_data


def test_power_report_invalid_size():
    """Test PowerReport rejects wrong size."""
    with pytest.raises(ValueError, match="13 bytes"):
        PowerReport.from_bytes(bytes([0x00] * 10))


def test_power_report15():
    """Test PowerReport15 parsing."""
    # 15 bytes = 13-byte PowerReport + 2 unknown bytes
    data = bytes([
        0x26, 0x51, 0x2E,
        0xFF,
        0x22, 0xB1, 0x0C,
        0x00, 0x00, 0x00,
        0x44, 0xD2,
        0x84,
        0xAB, 0xCD,  # 2 unknown bytes
    ])
    
    report15 = PowerReport15.from_bytes(data)
    assert report15.unknown == bytes([0xAB, 0xCD])
    assert abs(report15.power_report.voltage_in - 30.65) < 0.01


def test_power_report15_roundtrip():
    """Test PowerReport15 encode/decode roundtrip."""
    original_data = bytes([
        0x26, 0x51, 0x2E,
        0xFF,
        0x22, 0xB1, 0x0C,
        0x00, 0x00, 0x00,
        0x44, 0xD2,
        0x84,
        0xAB, 0xCD,
    ])
    
    report15 = PowerReport15.from_bytes(original_data)
    encoded = report15.to_bytes()
    
    assert encoded == original_data


def test_power_report15_invalid_size():
    """Test PowerReport15 rejects wrong size."""
    with pytest.raises(ValueError, match="15 bytes"):
        PowerReport15.from_bytes(bytes([0x00] * 13))
