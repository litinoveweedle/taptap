"""PV link layer time synchronization (slot counter)."""

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class SlotEpoch(IntEnum):
    """Slot counter epoch (2 bits, 4 values)."""
    
    EPOCH_0 = 0  # 0x0xxx
    EPOCH_4 = 1  # 0x4xxx
    EPOCH_8 = 2  # 0x8xxx
    EPOCH_C = 3  # 0xCxxx
    
    def __add__(self, other: int) -> 'SlotEpoch':
        """Wrapping addition (modulo 4)."""
        return SlotEpoch((self.value + other) % 4)
    
    def successor(self) -> 'SlotEpoch':
        """Get next epoch (wraps around)."""
        return self + 1
    
    @classmethod
    def from_bits(cls, bits: int) -> 'SlotEpoch':
        """Create from 2-bit value.
        
        Args:
            bits: 2-bit epoch value (0-3)
            
        Returns:
            SlotEpoch instance
            
        Raises:
            ValueError: If bits not in range 0-3
        """
        if not (0 <= bits <= 3):
            raise ValueError(f"Epoch bits must be 0-3, got {bits}")
        return cls(bits)


@dataclass(frozen=True)
class SlotNumber:
    """14-bit slot number within epoch (0-11999)."""
    
    value: int
    
    MAX = 11999  # 0x2EDF
    
    def __post_init__(self):
        if not (0 <= self.value <= self.MAX):
            raise ValueError(f"Slot number must be 0-{self.MAX}, got {self.value}")
    
    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class SlotCounter:
    """16-bit slot counter with epoch and slot number.
    
    Format:
    - Bits 15-14: Epoch (2 bits, 4 values)
    - Bits 13-0: Slot number (14 bits, 0-11999)
    
    Timing:
    - Slot duration: ~4.29ms (5ms ± 15%)
    - Epoch duration: ~51.5 seconds (12000 slots)
    - Full cycle: ~206 seconds (4 epochs)
    """
    
    epoch: SlotEpoch
    slot_number: SlotNumber
    
    @classmethod
    def new(cls, epoch: SlotEpoch, slot_number: SlotNumber) -> 'SlotCounter':
        """Create slot counter from components."""
        return cls(epoch, slot_number)
    
    @classmethod
    def from_u16(cls, value: int) -> 'SlotCounter':
        """Decode from 16-bit value (big-endian u16).
        
        Args:
            value: 16-bit slot counter value
            
        Returns:
            SlotCounter instance
            
        Raises:
            ValueError: If slot number exceeds maximum
        """
        if not (0 <= value <= 0xFFFF):
            raise ValueError(f"SlotCounter value must be 16-bit, got {value}")
        
        epoch_bits = (value >> 14) & 0x3
        slot_bits = value & 0x3FFF
        
        epoch = SlotEpoch.from_bits(epoch_bits)
        
        # Validate slot number
        if slot_bits > SlotNumber.MAX:
            raise ValueError(f"Slot number {slot_bits} exceeds maximum {SlotNumber.MAX}")
        
        slot_number = SlotNumber(slot_bits)
        
        return cls(epoch, slot_number)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'SlotCounter':
        """Decode from big-endian 2-byte representation.
        
        Args:
            data: 2-byte big-endian slot counter
            
        Returns:
            SlotCounter instance
        """
        if len(data) != 2:
            raise ValueError(f"SlotCounter must be 2 bytes, got {len(data)}")
        
        value = struct.unpack('>H', data)[0]
        return cls.from_u16(value)
    
    def to_u16(self) -> int:
        """Encode as 16-bit value."""
        return (self.epoch.value << 14) | self.slot_number.value
    
    def to_bytes(self) -> bytes:
        """Encode as big-endian 2-byte representation."""
        return struct.pack('>H', self.to_u16())
    
    def slots_since(self, past: 'SlotCounter') -> int:
        """Calculate slots elapsed since past counter (handles wraparound).
        
        Args:
            past: Earlier slot counter
            
        Returns:
            Number of slots elapsed (0-48000)
            
        Raises:
            ValueError: If calculation would overflow or go backwards more than 1 epoch
        """
        # Calculate epoch difference (with wrapping)
        epoch_diff = (self.epoch.value - past.epoch.value) % 4
        
        # Calculate total slots
        if epoch_diff == 0:
            # Same epoch
            slot_diff = self.slot_number.value - past.slot_number.value
            if slot_diff < 0:
                raise ValueError("Negative slot difference in same epoch")
            return slot_diff
        elif epoch_diff == 1:
            # Next epoch
            slots_to_end = SlotNumber.MAX - past.slot_number.value + 1
            slots_from_start = self.slot_number.value
            return slots_to_end + slots_from_start
        elif epoch_diff == 2:
            # Two epochs ahead
            return 2 * (SlotNumber.MAX + 1) + (self.slot_number.value - past.slot_number.value)
        elif epoch_diff == 3:
            # Three epochs ahead (or one epoch back - treat as forward)
            return 3 * (SlotNumber.MAX + 1) + (self.slot_number.value - past.slot_number.value)
        else:
            raise ValueError(f"Invalid epoch difference: {epoch_diff}")
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, SlotCounter):
            return NotImplemented
        return self.epoch == other.epoch and self.slot_number == other.slot_number
    
    def __hash__(self) -> int:
        return hash((self.epoch, self.slot_number.value))
    
    def __str__(self) -> str:
        return f"SlotCounter(epoch={self.epoch.name}, slot={self.slot_number.value})"
    
    def __repr__(self) -> str:
        return f"SlotCounter.from_u16(0x{self.to_u16():04X})"
