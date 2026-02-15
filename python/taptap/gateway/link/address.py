"""Gateway link layer addressing."""

import struct
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class GatewayID:
    """15-bit gateway identifier."""
    
    value: int
    
    def __post_init__(self):
        if not (0 <= self.value <= 0x7FFF):
            raise ValueError(f"GatewayID must be 15-bit (0-32767), got {self.value}")
    
    def __str__(self) -> str:
        return str(self.value)
    
    def __int__(self) -> int:
        return self.value


class Address:
    """Gateway link address with direction bit.
    
    The MSB indicates direction:
    - 0: To gateway (controller → gateway)
    - 1: From gateway (gateway → controller)
    """
    
    def __init__(self, gateway_id: GatewayID, direction: bool):
        """Create address.
        
        Args:
            gateway_id: Gateway identifier
            direction: False for To, True for From
        """
        self.gateway_id = gateway_id
        self._from = direction
    
    @classmethod
    def to(cls, gateway_id: GatewayID) -> 'Address':
        """Create To address (controller → gateway)."""
        return cls(gateway_id, False)
    
    @classmethod
    def from_(cls, gateway_id: GatewayID) -> 'Address':
        """Create From address (gateway → controller)."""
        return cls(gateway_id, True)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'Address':
        """Decode from big-endian u16.
        
        Args:
            data: 2-byte big-endian value
            
        Returns:
            Address instance
        """
        if len(data) != 2:
            raise ValueError(f"Address must be 2 bytes, got {len(data)}")
        
        value = struct.unpack('>H', data)[0]
        direction = bool(value & 0x8000)
        gateway_id = GatewayID(value & 0x7FFF)
        
        return cls(gateway_id, direction)
    
    def to_bytes(self) -> bytes:
        """Encode as big-endian u16."""
        value = self.gateway_id.value
        if self._from:
            value |= 0x8000
        return struct.pack('>H', value)
    
    @property
    def is_to(self) -> bool:
        """Check if this is a To address."""
        return not self._from
    
    @property
    def is_from(self) -> bool:
        """Check if this is a From address."""
        return self._from
    
    @property
    def direction(self) -> int:
        """Get direction as integer (0=To, 1=From)."""
        return 1 if self._from else 0
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Address):
            return NotImplemented
        return self.gateway_id == other.gateway_id and self._from == other._from
    
    def __hash__(self) -> int:
        return hash((self.gateway_id.value, self._from))
    
    def __str__(self) -> str:
        direction = "From" if self._from else "To"
        return f"{direction}(GatewayID({self.gateway_id.value}))"
    
    def __repr__(self) -> str:
        return f"Address.{'from_' if self._from else 'to'}(GatewayID({self.gateway_id.value}))"
