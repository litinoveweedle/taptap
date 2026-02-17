"""PV application layer types."""

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Tuple

from ..link.slot_counter import SlotCounter
from ..network.types import RSSI


class PacketType(IntEnum):
    """PV packet type identifiers."""
    
    STRING_REQUEST = 0x06
    STRING_RESPONSE = 0x07
    TOPOLOGY_REPORT = 0x09
    GATEWAY_RADIO_CONFIGURATION_REQUEST = 0x0D
    GATEWAY_RADIO_CONFIGURATION_RESPONSE = 0x0E
    PV_CONFIGURATION_REQUEST = 0x13
    PV_CONFIGURATION_RESPONSE = 0x18
    BROADCAST = 0x22
    BROADCAST_ACK = 0x23
    NODE_TABLE_REQUEST = 0x26
    NODE_TABLE_RESPONSE = 0x27
    LONG_NETWORK_STATUS_REQUEST = 0x2D
    NETWORK_STATUS_REQUEST = 0x2E
    NETWORK_STATUS_RESPONSE = 0x2F
    POWER_REPORT = 0x31


class U12Pair:
    """Two 12-bit unsigned integers packed into 3 bytes.
    
    Format:
    - First value: upper 12 bits from bytes [0:2]
    - Second value: lower 12 bits from bytes [1:3]
    """
    
    def __init__(self, data: bytes):
        """Create U12Pair from 3 bytes.
        
        Args:
            data: 3 bytes containing two 12-bit values
            
        Raises:
            ValueError: If data is not 3 bytes
        """
        if len(data) != 3:
            raise ValueError(f"U12Pair requires 3 bytes, got {len(data)}")
        self._data = bytes(data)
    
    @property
    def first(self) -> int:
        """Get first 12-bit value (upper)."""
        # Extract upper 12 bits: bytes[0:2] >> 4
        value = struct.unpack('>H', self._data[0:2])[0]
        return value >> 4
    
    @property
    def second(self) -> int:
        """Get second 12-bit value (lower)."""
        # Extract lower 12 bits: bytes[1:3] & 0x0FFF
        value = struct.unpack('>H', self._data[1:3])[0]
        return value & 0x0FFF
    
    def as_tuple(self) -> Tuple[int, int]:
        """Get both values as tuple."""
        return (self.first, self.second)
    
    @classmethod
    def from_values(cls, first: int, second: int) -> 'U12Pair':
        """Create from two 12-bit values.
        
        Args:
            first: First 12-bit value (0-4095)
            second: Second 12-bit value (0-4095)
            
        Returns:
            U12Pair instance
            
        Raises:
            ValueError: If values exceed 12 bits
        """
        if not (0 <= first <= 0xFFF):
            raise ValueError(f"First value must be 12-bit, got {first}")
        if not (0 <= second <= 0xFFF):
            raise ValueError(f"Second value must be 12-bit, got {second}")
        
        # Pack: first << 4 into bytes[0:2], second into bytes[1:3]
        a_bytes = (first << 4).to_bytes(2, 'big')
        b_bytes = second.to_bytes(2, 'big')
        
        return cls(bytes([a_bytes[0], a_bytes[1] | b_bytes[0], b_bytes[1]]))
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, U12Pair):
            return NotImplemented
        return self._data == other._data
    
    def __repr__(self) -> str:
        return f"U12Pair({self.first:#05x}, {self.second:#05x})"


@dataclass(frozen=True)
class PowerReport:
    """Solar optimizer power report (13 bytes)."""
    
    voltage_in_and_voltage_out: U12Pair  # 3 bytes
    dc_dc_duty_cycle: int  # 1 byte (u8)
    current_and_temperature: U12Pair  # 3 bytes
    unknown: bytes  # 3 bytes
    slot_counter: SlotCounter  # 2 bytes
    rssi: RSSI  # 1 byte
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'PowerReport':
        """Parse PowerReport from bytes.
        
        Args:
            data: 13 bytes of power report data
            
        Returns:
            PowerReport instance
            
        Raises:
            ValueError: If data is not 13 bytes
        """
        if len(data) != 13:
            raise ValueError(f"PowerReport requires 13 bytes, got {len(data)}")
        
        voltage_in_and_voltage_out = U12Pair(data[0:3])
        dc_dc_duty_cycle = data[3]
        current_and_temperature = U12Pair(data[4:7])
        unknown = data[7:10]
        slot_counter = SlotCounter.from_bytes(data[10:12])
        rssi = RSSI(data[12])
        
        return cls(
            voltage_in_and_voltage_out=voltage_in_and_voltage_out,
            dc_dc_duty_cycle=dc_dc_duty_cycle,
            current_and_temperature=current_and_temperature,
            unknown=unknown,
            slot_counter=slot_counter,
            rssi=rssi
        )
    
    def to_bytes(self) -> bytes:
        """Encode PowerReport to bytes."""
        return (
            self.voltage_in_and_voltage_out._data +
            bytes([self.dc_dc_duty_cycle]) +
            self.current_and_temperature._data +
            self.unknown +
            self.slot_counter.to_bytes() +
            bytes([self.rssi.value])
        )
    
    @property
    def voltage_in(self) -> float:
        """Get input voltage in volts."""
        return self.voltage_in_and_voltage_out.first / 20.0
    
    @property
    def voltage_out(self) -> float:
        """Get output voltage in volts."""
        return self.voltage_in_and_voltage_out.second / 10.0
    
    @property
    def current(self) -> float:
        """Get current in amperes."""
        return self.current_and_temperature.first / 200.0
    
    @property
    def temperature(self) -> float:
        """Get temperature in Celsius.
        
        Handles sign extension for negative temperatures.
        """
        raw = self.current_and_temperature.second
        
        # Check if negative (bit 11 set)
        if raw & 0x800:
            # Sign-extend to 16-bit signed
            signed = raw | 0xF000
            # Convert to signed integer
            signed_int = struct.unpack('>h', struct.pack('>H', signed))[0]
            return signed_int / 10.0
        else:
            return raw / 10.0
    
    @property
    def duty_cycle(self) -> float:
        """Get DC-DC converter duty cycle (0.0-1.0)."""
        return self.dc_dc_duty_cycle / 255.0


@dataclass(frozen=True)
class PowerReport15:
    """Extended 15-byte power report."""
    
    power_report: PowerReport  # 13 bytes
    unknown: bytes  # 2 bytes
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'PowerReport15':
        """Parse PowerReport15 from bytes.
        
        Args:
            data: 15 bytes of power report data
            
        Returns:
            PowerReport15 instance
            
        Raises:
            ValueError: If data is not 15 bytes
        """
        if len(data) != 15:
            raise ValueError(f"PowerReport15 requires 15 bytes, got {len(data)}")
        
        power_report = PowerReport.from_bytes(data[0:13])
        unknown = data[13:15]
        
        return cls(
            power_report=power_report,
            unknown=unknown
        )
    
    def to_bytes(self) -> bytes:
        """Encode PowerReport15 to bytes."""
        return self.power_report.to_bytes() + self.unknown
