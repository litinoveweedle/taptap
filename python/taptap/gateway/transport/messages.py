"""Gateway transport layer message types."""

from dataclasses import dataclass
from typing import Optional, Tuple

from ...pv.link.slot_counter import SlotCounter
from ...pv.network.received_packets import ReceivedPackets


def interpret_packet_number_lo(new_lo: int, old: int) -> int:
    """Expand 8-bit packet number to 16-bit using old value as reference.
    
    Args:
        new_lo: New low byte
        old: Previous 16-bit packet number
        
    Returns:
        New 16-bit packet number
    """
    old_hi = (old >> 8) & 0xFF
    old_lo = old & 0xFF
    
    if new_lo >= old_lo:
        new_hi = old_hi
    else:
        # Wrapped around
        new_hi = (old_hi + 1) & 0xFF
    
    return (new_hi << 8) | new_lo


@dataclass
class ReceiveRequest:
    """A receive request frame payload (5 bytes)."""
    unknown_1: bytes  # 2 bytes
    packet_number: int  # u16
    unknown_2: int  # u8
    
    @classmethod
    def from_bytes(cls, data: bytes) -> Optional['ReceiveRequest']:
        """Parse from bytes.
        
        Args:
            data: 5-byte payload
            
        Returns:
            ReceiveRequest or None if invalid
        """
        if len(data) < 5:
            return None
        
        return cls(
            unknown_1=data[0:2],
            packet_number=int.from_bytes(data[2:4], byteorder='big'),
            unknown_2=data[4]
        )


@dataclass
class ReceiveResponse:
    """A receive response frame payload (variable length)."""
    rx_buffers_used: Optional[int]
    tx_buffers_free: Optional[int]
    unknown_a: Optional[bytes]
    unknown_b: Optional[bytes]
    packet_number: int
    slot_counter: SlotCounter
    
    @classmethod
    def read_from_bytes(
        cls, 
        data: bytes, 
        old_packet_number: int
    ) -> Optional[Tuple['ReceiveResponse', ReceivedPackets]]:
        """Parse ReceiveResponse from bytes with variable fields.
        
        Args:
            data: Payload bytes
            old_packet_number: Previous packet number for expansion
            
        Returns:
            Tuple of (ReceiveResponse, ReceivedPackets) or None if invalid
        """
        # Need at least 2 bytes for status_type
        if len(data) < 2:
            return None
        
        # Read status_type bitmask
        status_type = int.from_bytes(data[0:2], byteorder='big')
        
        # Validate known pattern (bits 5-7 must be set)
        if status_type & 0x00E0 != 0x00E0:
            return None
        
        offset = 2
        
        # Calculate expected minimum length
        expected = 0
        if status_type & 0x0001 == 0:
            expected += 1  # rx_buffers_used
        if status_type & 0x0002 == 0:
            expected += 1  # tx_buffers_free
        if status_type & 0x0004 == 0:
            expected += 2  # unknown_a
        if status_type & 0x0008 == 0:
            expected += 2  # unknown_b
        if status_type & 0x0010 == 0:
            expected += 2  # full packet number
        else:
            expected += 1  # 8-bit packet number
        expected += 2  # slot counter
        
        if len(data) - 2 < expected:
            return None
        
        # Parse rx_buffers_used
        rx_buffers_used = None
        if status_type & 0x0001 == 0:
            rx_buffers_used = data[offset]
            offset += 1
        
        # Parse tx_buffers_free
        tx_buffers_free = None
        if status_type & 0x0002 == 0:
            tx_buffers_free = data[offset]
            offset += 1
        
        # Parse unknown_a
        unknown_a = None
        if status_type & 0x0004 == 0:
            unknown_a = data[offset:offset+2]
            offset += 2
        
        # Parse unknown_b
        unknown_b = None
        if status_type & 0x0008 == 0:
            unknown_b = data[offset:offset+2]
            offset += 2
        
        # Parse packet_number
        if status_type & 0x0010 == 0:
            # Full 16-bit
            packet_number = int.from_bytes(data[offset:offset+2], byteorder='big')
            offset += 2
        else:
            # 8-bit, expand using old value
            packet_number = interpret_packet_number_lo(data[offset], old_packet_number)
            offset += 1
        
        # Parse slot_counter (2 bytes)
        slot_counter = SlotCounter.from_bytes(data[offset:offset+2])
        offset += 2
        
        # Remaining data is packets
        packets = ReceivedPackets(data[offset:])
        
        return (cls(
            rx_buffers_used=rx_buffers_used,
            tx_buffers_free=tx_buffers_free,
            unknown_a=unknown_a,
            unknown_b=unknown_b,
            packet_number=packet_number,
            slot_counter=slot_counter
        ), packets)


@dataclass
class CommandRequest:
    """A command request frame payload (5 bytes)."""
    unknown: bytes  # 3 bytes
    packet_type: int  # u8
    sequence_number: int  # u8
    
    @classmethod
    def from_bytes(cls, data: bytes) -> Optional['CommandRequest']:
        """Parse from bytes.
        
        Args:
            data: At least 5 bytes
            
        Returns:
            CommandRequest or None if too short
        """
        if len(data) < 5:
            return None
        
        return cls(
            unknown=data[0:3],
            packet_type=data[3],
            sequence_number=data[4]
        )


@dataclass
class CommandResponse:
    """A command response frame payload (5 bytes)."""
    unknown_1: int  # u8
    tx_buffers_free: int  # u8
    unknown_2: int  # u8
    packet_type: int  # u8
    command_sequence_number: int  # u8
    
    @classmethod
    def from_bytes(cls, data: bytes) -> Optional['CommandResponse']:
        """Parse from bytes.
        
        Args:
            data: At least 5 bytes
            
        Returns:
            CommandResponse or None if too short
        """
        if len(data) < 5:
            return None
        
        return cls(
            unknown_1=data[0],
            tx_buffers_free=data[1],
            unknown_2=data[2],
            packet_type=data[3],
            command_sequence_number=data[4]
        )
