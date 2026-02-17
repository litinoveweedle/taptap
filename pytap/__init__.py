"""pytap — Tigo TAP protocol parser for solar monitoring systems.

Public surface re-exports from core modules and the api module.
"""

__version__ = '0.1.0'

# Core types
from .core.types import (
    GatewayID,
    Address,
    FrameType,
    Frame,
    NodeID,
    NodeAddress,
    LongAddress,
    RSSI,
    SlotCounter,
    PacketType,
    ReceivedPacketHeader,
    U12Pair,
    PowerReport,
    GatewayInfo,
    NodeInfo,
    iter_received_packets,
)

# Events
from .core.events import (
    Event,
    PowerReportEvent,
    InfrastructureEvent,
    TopologyEvent,
    StringEvent,
)

# State management
from .core.state import (
    SlotClock,
    NodeTableBuilder,
    PersistentState,
)

# Parser
from .core.parser import Parser

# Barcode utilities
from .core.barcode import encode_barcode, decode_barcode, barcode_from_address

# CRC
from .core.crc import crc

# API functions
from .api import (
    create_parser,
    parse_bytes,
    connect,
    observe,
)

__all__ = [
    '__version__',
    # Types
    'GatewayID', 'Address', 'FrameType', 'Frame',
    'NodeID', 'NodeAddress', 'LongAddress', 'RSSI', 'SlotCounter',
    'PacketType', 'ReceivedPacketHeader', 'U12Pair', 'PowerReport',
    'GatewayInfo', 'NodeInfo', 'iter_received_packets',
    # Events
    'Event', 'PowerReportEvent', 'InfrastructureEvent',
    'TopologyEvent', 'StringEvent',
    # State
    'SlotClock', 'NodeTableBuilder', 'PersistentState',
    # Parser
    'Parser',
    # Barcode
    'encode_barcode', 'decode_barcode', 'barcode_from_address',
    # CRC
    'crc',
    # API
    'create_parser', 'parse_bytes', 'connect', 'observe',
]
