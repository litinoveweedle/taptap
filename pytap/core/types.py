"""Protocol types for the TapTap gateway and PV network.

All protocol types are defined in this single module:
- Gateway link-layer: GatewayID, Address, FrameType, Frame
- PV network: NodeID, NodeAddress, LongAddress, RSSI, SlotCounter
- PV application: PacketType, ReceivedPacketHeader, U12Pair, PowerReport
- Infrastructure: GatewayInfo, NodeInfo
"""

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar, Iterator


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

SLOTS_PER_EPOCH = 12000
MAX_SLOT_NUMBER = 11999


# ---------------------------------------------------------------------------
#  Gateway Link Layer Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GatewayID:
    """15-bit gateway identifier (0-32767)."""
    value: int

    def __post_init__(self):
        if not (0 <= self.value <= 0x7FFF):
            raise ValueError(f"GatewayID must be 0-32767, got {self.value}")

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class Address:
    """Gateway link address with direction bit.

    Bit 15: direction (0=To/controller->gateway, 1=From/gateway->controller)
    Bits 14-0: GatewayID
    """
    gateway_id: GatewayID
    is_from: bool  # True = gateway->controller, False = controller->gateway

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Address':
        """Decode from big-endian u16."""
        value = struct.unpack('>H', data)[0]
        is_from = bool(value & 0x8000)
        gateway_id = GatewayID(value & 0x7FFF)
        return cls(gateway_id, is_from)

    @property
    def direction(self) -> int:
        return 1 if self.is_from else 0

    def __str__(self) -> str:
        d = "From" if self.is_from else "To"
        return f"{d}(GatewayID({self.gateway_id.value}))"


class FrameType(IntEnum):
    """Gateway link layer frame types."""
    RECEIVE_REQUEST            = 0x0148
    RECEIVE_RESPONSE           = 0x0149
    COMMAND_REQUEST            = 0x0B0F
    COMMAND_RESPONSE           = 0x0B10
    PING_REQUEST               = 0x0B00
    PING_RESPONSE              = 0x0B01
    ENUMERATION_START_REQUEST  = 0x0014
    ENUMERATION_START_RESPONSE = 0x0015
    ENUMERATION_REQUEST        = 0x0038
    ENUMERATION_RESPONSE       = 0x0039
    ASSIGN_GATEWAY_ID_REQUEST  = 0x003C
    ASSIGN_GATEWAY_ID_RESPONSE = 0x003D
    IDENTIFY_REQUEST           = 0x003A
    IDENTIFY_RESPONSE          = 0x003B
    VERSION_REQUEST            = 0x000A
    VERSION_RESPONSE           = 0x000B
    ENUMERATION_END_REQUEST    = 0x0E02
    ENUMERATION_END_RESPONSE   = 0x0006


@dataclass(frozen=True)
class Frame:
    """Decoded gateway link-layer frame."""
    address: Address
    frame_type: int    # raw u16 (may or may not match FrameType enum)
    payload: bytes


# ---------------------------------------------------------------------------
#  PV Network Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeID:
    """PV network node identifier (1-65535, non-zero)."""
    value: int
    GATEWAY: ClassVar[int] = 1

    def __post_init__(self):
        if not (1 <= self.value <= 0xFFFF):
            raise ValueError(f"NodeID must be 1-65535, got {self.value}")

    @classmethod
    def from_node_address(cls, addr: 'NodeAddress') -> 'NodeID':
        """Convert NodeAddress to NodeID. NodeAddress 0 (broadcast) is invalid."""
        return cls(addr.value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class NodeAddress:
    """PV network address (0-65535, 0 = broadcast)."""
    value: int

    @classmethod
    def from_bytes(cls, data: bytes) -> 'NodeAddress':
        return cls(struct.unpack('>H', data)[0])


@dataclass(frozen=True)
class LongAddress:
    """IEEE 802.15.4 64-bit MAC address (8 bytes)."""
    data: bytes

    def __post_init__(self):
        if len(self.data) != 8:
            raise ValueError(f"LongAddress must be 8 bytes, got {len(self.data)}")

    def __str__(self) -> str:
        return ':'.join(f'{b:02X}' for b in self.data)

    @classmethod
    def from_str(cls, s: str) -> 'LongAddress':
        return cls(bytes.fromhex(s.replace(':', '')))


@dataclass(frozen=True)
class RSSI:
    """Received Signal Strength Indicator (0-255)."""
    value: int


@dataclass(frozen=True)
class SlotCounter:
    """Time synchronization counter: 2-bit epoch + 14-bit slot number."""
    raw: int

    @property
    def epoch(self) -> int:
        return (self.raw >> 14) & 0x3

    @property
    def slot_number(self) -> int:
        return self.raw & 0x3FFF

    @classmethod
    def from_bytes(cls, data: bytes) -> 'SlotCounter':
        return cls(struct.unpack('>H', data)[0])

    def slots_since(self, past: 'SlotCounter') -> int:
        """Number of slots elapsed since `past`."""
        epoch_diff = (self.epoch - past.epoch) % 4
        if epoch_diff == 0:
            return self.slot_number - past.slot_number
        elif epoch_diff == 1:
            return (MAX_SLOT_NUMBER - past.slot_number + 1) + self.slot_number
        else:  # 2 or 3
            return epoch_diff * SLOTS_PER_EPOCH + (self.slot_number - past.slot_number)


# ---------------------------------------------------------------------------
#  PV Application Types
# ---------------------------------------------------------------------------

class PacketType(IntEnum):
    """PV application packet types."""
    STRING_REQUEST                       = 0x06
    STRING_RESPONSE                      = 0x07
    TOPOLOGY_REPORT                      = 0x09
    GATEWAY_RADIO_CONFIGURATION_REQUEST  = 0x0D
    GATEWAY_RADIO_CONFIGURATION_RESPONSE = 0x0E
    PV_CONFIGURATION_REQUEST             = 0x13
    PV_CONFIGURATION_RESPONSE            = 0x18
    BROADCAST                            = 0x22
    BROADCAST_ACK                        = 0x23
    NODE_TABLE_REQUEST                   = 0x26
    NODE_TABLE_RESPONSE                  = 0x27
    LONG_NETWORK_STATUS_REQUEST          = 0x2D
    NETWORK_STATUS_REQUEST               = 0x2E
    NETWORK_STATUS_RESPONSE              = 0x2F
    POWER_REPORT                         = 0x31


@dataclass(frozen=True)
class ReceivedPacketHeader:
    """7-byte header for PV network received packets."""
    packet_type: int        # u8 — offset 0
    node_address: int       # u16 big-endian — offset 1-2
    short_address: int      # u16 big-endian — offset 3-4
    dsn: int                # u8 — offset 5
    data_length: int        # u8 — offset 6

    HEADER_SIZE: ClassVar[int] = 7

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ReceivedPacketHeader':
        if len(data) < 7:
            raise ValueError(f"ReceivedPacketHeader needs 7 bytes, got {len(data)}")
        return cls(
            packet_type=data[0],
            node_address=struct.unpack('>H', data[1:3])[0],
            short_address=struct.unpack('>H', data[3:5])[0],
            dsn=data[5],
            data_length=data[6],
        )


@dataclass(frozen=True)
class U12Pair:
    """Two 12-bit values packed into 3 bytes."""
    first: int
    second: int

    @classmethod
    def from_bytes(cls, data: bytes) -> 'U12Pair':
        """Unpack two 12-bit values from 3 bytes."""
        first = (data[0] << 4) | (data[1] >> 4)
        second = ((data[1] & 0x0F) << 8) | data[2]
        return cls(first, second)


@dataclass(frozen=True)
class PowerReport:
    """13-byte solar optimizer power measurement (raw values)."""
    voltage_in_out: U12Pair        # bytes 0-2
    dc_dc_duty_cycle_raw: int      # byte 3 (u8)
    current_temp: U12Pair          # bytes 4-6
    unknown: bytes                 # bytes 7-9
    slot_counter: SlotCounter      # bytes 10-11
    rssi: int                      # byte 12 (u8)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PowerReport':
        if len(data) < 13:
            raise ValueError(f"PowerReport needs 13 bytes, got {len(data)}")
        return cls(
            voltage_in_out=U12Pair.from_bytes(data[0:3]),
            dc_dc_duty_cycle_raw=data[3],
            current_temp=U12Pair.from_bytes(data[4:7]),
            unknown=data[7:10],
            slot_counter=SlotCounter.from_bytes(data[10:12]),
            rssi=data[12],
        )

    @property
    def voltage_in(self) -> float:
        """Input voltage in Volts."""
        return self.voltage_in_out.first / 20.0

    @property
    def voltage_out(self) -> float:
        """Output voltage in Volts."""
        return self.voltage_in_out.second / 10.0

    @property
    def current(self) -> float:
        """Current in Amps."""
        return self.current_temp.first / 200.0

    @property
    def temperature(self) -> float:
        """Temperature in °C (sign-extended)."""
        raw = self.current_temp.second
        if raw & 0x800:
            # Sign-extend 12-bit to 16-bit signed
            signed = raw | 0xF000
            signed_int = struct.unpack('>h', struct.pack('>H', signed))[0]
            return signed_int / 10.0
        return raw / 10.0

    @property
    def duty_cycle(self) -> float:
        """DC-DC converter duty cycle (0.0-1.0)."""
        return self.dc_dc_duty_cycle_raw / 255.0


# ---------------------------------------------------------------------------
#  Infrastructure Helper Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GatewayInfo:
    """Gateway address and version info."""
    address: LongAddress | None = None
    version: str | None = None


@dataclass(frozen=True)
class NodeInfo:
    """Node address and barcode info."""
    address: LongAddress | None = None
    barcode: str | None = None


# ---------------------------------------------------------------------------
#  Utility Functions
# ---------------------------------------------------------------------------

def iter_received_packets(data: bytes) -> Iterator[tuple[bytes, bytes]]:
    """Iterate over received packets in a RECEIVE_RESPONSE payload.

    Yields (header_bytes, packet_data) tuples.
    """
    offset = 0
    while offset < len(data):
        if offset + 7 > len(data):
            break  # truncated header
        header_bytes = data[offset:offset + 7]
        data_length = header_bytes[6]
        if offset + 7 + data_length > len(data):
            break  # truncated data
        pkt_data = data[offset + 7:offset + 7 + data_length]
        offset += 7 + data_length
        yield header_bytes, pkt_data
