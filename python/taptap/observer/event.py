"""Observer event types for TapTap.

Events are generated from observed protocol messages and emitted as JSON.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import json

from ..gateway.link.address import GatewayID
from ..pv.network.types import NodeID, LongAddress, RSSI
from ..barcode import Barcode


@dataclass
class PowerReportEvent:
    """Power report event from a solar optimizer.
    
    This represents real-time measurements from a PV optimizer, including
    voltage, current, temperature, and other operational parameters.
    """
    
    gateway: int  # GatewayID value
    node: int  # NodeID value
    timestamp: datetime
    voltage_in: float  # Volts
    voltage_out: float  # Volts
    current: float  # Amperes
    dc_dc_duty_cycle: float  # 0.0-1.0
    temperature: float  # Celsius
    rssi: int  # RSSI value
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        data = {
            'event_type': 'power_report',
            'gateway': self.gateway,
            'node': self.node,
            'timestamp': self.timestamp.isoformat(),
            'voltage_in': self.voltage_in,
            'voltage_out': self.voltage_out,
            'current': self.current,
            'dc_dc_duty_cycle': self.dc_dc_duty_cycle,
            'temperature': self.temperature,
            'rssi': self.rssi,
        }
        return json.dumps(data)
    
    @classmethod
    def from_power_report(
        cls,
        gateway_id: GatewayID,
        node_id: NodeID,
        timestamp: datetime,
        voltage_in: float,
        voltage_out: float,
        current: float,
        duty_cycle: float,
        temperature: float,
        rssi: RSSI,
    ) -> 'PowerReportEvent':
        """Create event from power report data."""
        return cls(
            gateway=gateway_id.value,
            node=node_id.value,
            timestamp=timestamp,
            voltage_in=voltage_in,
            voltage_out=voltage_out,
            current=current,
            dc_dc_duty_cycle=duty_cycle,
            temperature=temperature,
            rssi=rssi.value,
        )


@dataclass
class Gateway:
    """Gateway metadata.
    
    Contains both the link layer ID (always present) and the hardware address
    (may be discovered later).
    """
    
    id: int  # GatewayID value
    address: Optional[str] = None  # LongAddress as hex string
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {'id': self.id}
        if self.address:
            result['address'] = self.address
        return result


@dataclass
class Node:
    """Node metadata.
    
    Contains the node ID (always present) and optionally the hardware address
    and barcode (discovered later).
    """
    
    id: int  # NodeID value
    address: Optional[str] = None  # LongAddress as hex string
    barcode: Optional[str] = None  # Barcode string
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {'id': self.id}
        if self.address:
            result['address'] = self.address
        if self.barcode:
            result['barcode'] = self.barcode
        return result
