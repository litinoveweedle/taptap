"""Event types for pytap protocol parser.

All events are dataclass instances with a to_dict() method for JSON serialization.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    """Base event. All events have a type discriminator and timestamp."""
    event_type: str
    timestamp: datetime

    def to_dict(self) -> dict:
        """Serialize to dictionary suitable for JSON output."""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d


@dataclass
class PowerReportEvent(Event):
    """Solar optimizer power measurement event."""
    gateway_id: int
    node_id: int
    barcode: Optional[str]
    voltage_in: float
    voltage_out: float
    current: float
    power: float             # = voltage_out * current
    temperature: float
    dc_dc_duty_cycle: float
    rssi: int

    def __init__(self, *, gateway_id: int, node_id: int, barcode: Optional[str],
                 voltage_in: float, voltage_out: float, current: float,
                 temperature: float, dc_dc_duty_cycle: float, rssi: int,
                 timestamp: datetime):
        super().__init__(event_type='power_report', timestamp=timestamp)
        self.gateway_id = gateway_id
        self.node_id = node_id
        self.barcode = barcode
        self.voltage_in = voltage_in
        self.voltage_out = voltage_out
        self.current = current
        self.power = round(voltage_out * current, 4)
        self.temperature = temperature
        self.dc_dc_duty_cycle = dc_dc_duty_cycle
        self.rssi = rssi


@dataclass
class InfrastructureEvent(Event):
    """Infrastructure state change (gateway/node discovery)."""
    gateways: dict  # {gw_id_int: {"address": str|None, "version": str|None}}
    nodes: dict     # {node_id_int: {"address": str|None, "barcode": str|None}}

    def __init__(self, *, gateways: dict, nodes: dict, timestamp: datetime):
        super().__init__(event_type='infrastructure', timestamp=timestamp)
        self.gateways = gateways
        self.nodes = nodes


@dataclass
class TopologyEvent(Event):
    """Mesh network topology report from a node."""
    gateway_id: int
    node_id: int
    data: bytes

    def __init__(self, *, gateway_id: int, node_id: int, data: bytes,
                 timestamp: datetime):
        super().__init__(event_type='topology', timestamp=timestamp)
        self.gateway_id = gateway_id
        self.node_id = node_id
        self.data = data

    def to_dict(self) -> dict:
        d = super().to_dict()
        d['data'] = self.data.hex()
        return d


@dataclass
class StringEvent(Event):
    """String request/response (diagnostic commands)."""
    gateway_id: int
    node_id: int
    direction: str    # "request" or "response"
    content: str

    def __init__(self, *, gateway_id: int, node_id: int, direction: str,
                 content: str, timestamp: datetime):
        super().__init__(event_type='string', timestamp=timestamp)
        self.gateway_id = gateway_id
        self.node_id = node_id
        self.direction = direction
        self.content = content
