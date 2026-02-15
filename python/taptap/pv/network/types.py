"""PV network layer types."""

import struct
from dataclasses import dataclass
from typing import Optional


class NodeID:
    """PV network node identifier (non-zero u16)."""
    
    GATEWAY = 1
    MAX = 0xFFFF
    
    def __init__(self, value: int):
        """Create NodeID.
        
        Args:
            value: Node ID value (1-65535)
            
        Raises:
            ValueError: If value is 0 or out of range
        """
        if not (1 <= value <= 0xFFFF):
            raise ValueError(f"NodeID must be 1-65535, got {value}")
        self._value = value
    
    @property
    def value(self) -> int:
        """Get the node ID value."""
        return self._value
    
    def successor(self) -> Optional['NodeID']:
        """Get next node ID, or None if at MAX."""
        if self._value >= self.MAX:
            return None
        return NodeID(self._value + 1)
    
    def to_bytes(self) -> bytes:
        """Encode as big-endian u16."""
        return struct.pack('>H', self._value)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'NodeID':
        """Decode from big-endian u16."""
        if len(data) != 2:
            raise ValueError(f"NodeID must be 2 bytes, got {len(data)}")
        value = struct.unpack('>H', data)[0]
        return cls(value)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, NodeID):
            return NotImplemented
        return self._value == other._value
    
    def __hash__(self) -> int:
        return hash(self._value)
    
    def __int__(self) -> int:
        return self._value
    
    def __str__(self) -> str:
        return str(self._value)
    
    def __repr__(self) -> str:
        return f"NodeID({self._value})"


class NodeAddress:
    """Node address (0 = broadcast, 1+ = node ID)."""
    
    ZERO = 0  # Broadcast
    GATEWAY = 1
    
    def __init__(self, value: int):
        """Create NodeAddress.
        
        Args:
            value: Address value (0-65535)
            
        Raises:
            ValueError: If value is out of range
        """
        if not (0 <= value <= 0xFFFF):
            raise ValueError(f"NodeAddress must be 0-65535, got {value}")
        self._value = value
    
    @property
    def value(self) -> int:
        """Get the address value."""
        return self._value
    
    def to_node_id(self) -> Optional[NodeID]:
        """Convert to NodeID (None if broadcast)."""
        if self._value == 0:
            return None
        return NodeID(self._value)
    
    @classmethod
    def from_node_id(cls, node_id: Optional[NodeID]) -> 'NodeAddress':
        """Create from NodeID (None = broadcast)."""
        if node_id is None:
            return cls(0)
        return cls(node_id.value)
    
    def to_bytes(self) -> bytes:
        """Encode as big-endian u16."""
        return struct.pack('>H', self._value)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'NodeAddress':
        """Decode from big-endian u16."""
        if len(data) != 2:
            raise ValueError(f"NodeAddress must be 2 bytes, got {len(data)}")
        value = struct.unpack('>H', data)[0]
        return cls(value)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, NodeAddress):
            return NotImplemented
        return self._value == other._value
    
    def __hash__(self) -> int:
        return hash(self._value)
    
    def __int__(self) -> int:
        return self._value
    
    def __str__(self) -> str:
        if self._value == 0:
            return "Broadcast"
        return str(self._value)
    
    def __repr__(self) -> str:
        return f"NodeAddress({self._value})"


class ShortAddress:
    """802.15.4 short address (16-bit)."""
    
    def __init__(self, value: int):
        """Create ShortAddress.
        
        Args:
            value: Address value (0-65535)
            
        Raises:
            ValueError: If value is out of range
        """
        if not (0 <= value <= 0xFFFF):
            raise ValueError(f"ShortAddress must be 0-65535, got {value}")
        self._value = value
    
    @property
    def value(self) -> int:
        """Get the address value."""
        return self._value
    
    def to_bytes(self) -> bytes:
        """Encode as big-endian u16."""
        return struct.pack('>H', self._value)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'ShortAddress':
        """Decode from big-endian u16."""
        if len(data) != 2:
            raise ValueError(f"ShortAddress must be 2 bytes, got {len(data)}")
        value = struct.unpack('>H', data)[0]
        return cls(value)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, ShortAddress):
            return NotImplemented
        return self._value == other._value
    
    def __hash__(self) -> int:
        return hash(self._value)
    
    def __int__(self) -> int:
        return self._value
    
    def __str__(self) -> str:
        return f"0x{self._value:04X}"
    
    def __repr__(self) -> str:
        return f"ShortAddress(0x{self._value:04X})"


class LongAddress:
    """802.15.4 long address (64-bit MAC address)."""
    
    def __init__(self, address: bytes):
        """Create LongAddress.
        
        Args:
            address: 8-byte address
            
        Raises:
            ValueError: If address is not 8 bytes
        """
        if len(address) != 8:
            raise ValueError(f"LongAddress must be 8 bytes, got {len(address)}")
        self._address = bytes(address)
    
    @property
    def address(self) -> bytes:
        """Get the 8-byte address."""
        return self._address
    
    def to_bytes(self) -> bytes:
        """Get address as bytes."""
        return self._address
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'LongAddress':
        """Create from bytes."""
        return cls(data)
    
    def barcode(self) -> 'Barcode':
        """Convert to Barcode."""
        from ...barcode import Barcode
        return Barcode(self._address)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, LongAddress):
            return NotImplemented
        return self._address == other._address
    
    def __hash__(self) -> int:
        return hash(self._address)
    
    def __str__(self) -> str:
        return ':'.join(f'{b:02X}' for b in self._address)
    
    def __repr__(self) -> str:
        return f"LongAddress('{self}')"


class DSN:
    """Data Sequence Number (8-bit)."""
    
    def __init__(self, value: int):
        """Create DSN.
        
        Args:
            value: Sequence number (0-255)
            
        Raises:
            ValueError: If value is out of range
        """
        if not (0 <= value <= 0xFF):
            raise ValueError(f"DSN must be 0-255, got {value}")
        self._value = value
    
    @property
    def value(self) -> int:
        """Get the DSN value."""
        return self._value
    
    def __add__(self, other: int) -> 'DSN':
        """Wrapping addition."""
        return DSN((self._value + other) & 0xFF)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, DSN):
            return NotImplemented
        return self._value == other._value
    
    def __hash__(self) -> int:
        return hash(self._value)
    
    def __int__(self) -> int:
        return self._value
    
    def __str__(self) -> str:
        return str(self._value)
    
    def __repr__(self) -> str:
        return f"DSN({self._value})"


class RSSI:
    """Received Signal Strength Indicator (8-bit)."""
    
    def __init__(self, value: int):
        """Create RSSI.
        
        Args:
            value: RSSI value (0-255)
            
        Raises:
            ValueError: If value is out of range
        """
        if not (0 <= value <= 0xFF):
            raise ValueError(f"RSSI must be 0-255, got {value}")
        self._value = value
    
    @property
    def value(self) -> int:
        """Get the RSSI value."""
        return self._value
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, RSSI):
            return NotImplemented
        return self._value == other._value
    
    def __hash__(self) -> int:
        return hash(self._value)
    
    def __int__(self) -> int:
        return self._value
    
    def __str__(self) -> str:
        return str(self._value)
    
    def __repr__(self) -> str:
        return f"RSSI({self._value})"


@dataclass(frozen=True)
class ReceivedPacketHeader:
    """Header for PV network received packet (5 bytes)."""
    
    packet_type: int  # u8
    node_address: NodeAddress  # u16 BE
    short_address: ShortAddress  # u16 BE
    dsn: DSN  # u8
    data_length: int  # u8
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'ReceivedPacketHeader':
        """Parse header from bytes.
        
        Args:
            data: At least 6 bytes (5-byte header + length indicator)
            
        Returns:
            ReceivedPacketHeader instance
        """
        if len(data) < 6:
            raise ValueError(f"ReceivedPacketHeader requires at least 6 bytes, got {len(data)}")
        
        packet_type = data[0]
        node_address = NodeAddress.from_bytes(data[1:3])
        short_address = ShortAddress.from_bytes(data[3:5])
        dsn = DSN(data[5])
        data_length = data[6] if len(data) > 6 else 0
        
        return cls(
            packet_type=packet_type,
            node_address=node_address,
            short_address=short_address,
            dsn=dsn,
            data_length=data_length
        )
    
    def to_bytes(self) -> bytes:
        """Encode header to bytes."""
        return bytes([
            self.packet_type,
            *self.node_address.to_bytes(),
            *self.short_address.to_bytes(),
            self.dsn.value,
            self.data_length
        ])
