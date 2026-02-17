# pytap Implementation Plan

> **Target audience:** Developer implementing pytap from scratch.  
> **Reference code:** `python/taptap/` (layered port) and `src/` (Rust original).  
> **Architecture doc:** `pytap/docs/architecture.md`  
> **API reference:** `pytap/docs/api_reference.md`

---

## Table of Contents

1. [Project Setup](#1-project-setup)
2. [Phase 1 — CRC Module](#2-phase-1--crc-module)
3. [Phase 2 — Barcode Module](#3-phase-2--barcode-module)
4. [Phase 3 — Protocol Types](#4-phase-3--protocol-types)
5. [Phase 4 — Event Types](#5-phase-4--event-types)
6. [Phase 5 — State Management](#6-phase-5--state-management)
7. [Phase 6 — Parser Core](#7-phase-6--parser-core)
8. [Phase 7 — Data Sources](#8-phase-7--data-sources)
9. [Phase 8 — Public API](#9-phase-8--public-api)
10. [Phase 9 — CLI](#10-phase-9--cli)
11. [Phase 10 — Integration Tests & Polish](#11-phase-10--integration-tests--polish)
12. [Appendix A — Wire Format Quick Reference](#appendix-a--wire-format-quick-reference)
13. [Appendix B — Test Data](#appendix-b--test-data)

---

## 1. Project Setup

### 1.1 Create Directory Structure

```
pytap/
├── __init__.py
├── api.py
├── core/
│   ├── __init__.py
│   ├── barcode.py
│   ├── crc.py
│   ├── events.py
│   ├── parser.py
│   ├── source.py
│   ├── state.py
│   └── types.py
├── cli/
│   ├── __init__.py
│   └── main.py
├── docs/
│   ├── architecture.md
│   ├── api_reference.md
│   └── implementation_plan.md
└── tests/
    ├── __init__.py
    ├── test_api.py
    ├── test_barcode.py
    ├── test_crc.py
    ├── test_parser.py
    └── test_types.py
```

### 1.2 Create `setup.py` / `pyproject.toml`

```python
# setup.py
from setuptools import setup, find_packages

setup(
    name='pytap',
    version='0.1.0',
    packages=find_packages(),
    python_requires='>=3.10',
    install_requires=[],          # Core has ZERO dependencies
    extras_require={
        'serial': ['pyserial>=3.5'],
        'cli': ['click>=8.0'],
        'dev': ['pytest>=7.0', 'pytest-cov'],
    },
    entry_points={
        'console_scripts': [
            'pytap=pytap.cli.main:main',
        ],
    },
)
```

### 1.3 Create `pytap/__init__.py`

Stub that will be populated in Phase 8:

```python
"""pytap: Simplified TapTap protocol parser for Tigo TAP solar monitoring."""
__version__ = '0.1.0'
```

### 1.4 Validation

```bash
pip install -e ".[dev]"
pytest --co  # should discover 0 tests, no import errors
```

---

## 2. Phase 1 — CRC Module

**File:** `pytap/core/crc.py`  
**Reference:** `python/taptap/gateway/link/crc.py`  
**Depends on:** nothing

### 2.1 Specification

- **Algorithm:** CRC-16-CCITT (reflected polynomial)
- **Polynomial:** `0x8408`
- **Initial value:** `0x8408` (non-standard — this is intentional, matches the device firmware)
- **Computation:** table-driven, 256-entry lookup

### 2.2 Implementation

```python
"""CRC-16-CCITT calculation for gateway link layer frames."""

# Pre-computed CRC table: reflected polynomial 0x8408
_CRC_TABLE: list[int] = [
    0x0000, 0x1189, 0x2312, 0x329b, 0x4624, 0x57ad, 0x6536, 0x74bf,
    0x8c48, 0x9dc1, 0xaf5a, 0xbed3, 0xca6c, 0xdbe5, 0xe97e, 0xf8f7,
    0x1081, 0x0108, 0x3393, 0x221a, 0x56a5, 0x472c, 0x75b7, 0x643e,
    0x9cc9, 0x8d40, 0xbfdb, 0xae52, 0xdaed, 0xcb64, 0xf9ff, 0xe876,
    0x2102, 0x308b, 0x0210, 0x1399, 0x6726, 0x76af, 0x4434, 0x55bd,
    0xad4a, 0xbcc3, 0x8e58, 0x9fd1, 0xeb6e, 0xfae7, 0xc87c, 0xd9f5,
    0x3183, 0x200a, 0x1291, 0x0318, 0x77a7, 0x662e, 0x54b5, 0x453c,
    0xbdcb, 0xac42, 0x9ed9, 0x8f50, 0xfbef, 0xea66, 0xd8fd, 0xc974,
    0x4204, 0x538d, 0x6116, 0x709f, 0x0420, 0x15a9, 0x2732, 0x36bb,
    0xce4c, 0xdfc5, 0xed5e, 0xfcd7, 0x8868, 0x99e1, 0xab7a, 0xbaf3,
    0x5285, 0x430c, 0x7197, 0x601e, 0x14a1, 0x0528, 0x37b3, 0x263a,
    0xdecd, 0xcf44, 0xfddf, 0xec56, 0x98e9, 0x8960, 0xbbfb, 0xaa72,
    0x6306, 0x728f, 0x4014, 0x519d, 0x2522, 0x34ab, 0x0630, 0x17b9,
    0xef4e, 0xfec7, 0xcc5c, 0xddd5, 0xa96a, 0xb8e3, 0x8a78, 0x9bf1,
    0x7387, 0x620e, 0x5095, 0x411c, 0x35a3, 0x242a, 0x16b1, 0x0738,
    0xffcf, 0xee46, 0xdcdd, 0xcd54, 0xb9eb, 0xa022, 0x92b9, 0x8330,
    0x7bc7, 0x6a4e, 0x58d5, 0x495c, 0x3de3, 0x2c6a, 0x1ef1, 0x0f78,
    0x8408, 0x9581, 0xa71a, 0xb693, 0xc22c, 0xd3a5, 0xe13e, 0xf0b7,
    0x0840, 0x19c9, 0x2b52, 0x3adb, 0x4e64, 0x5fed, 0x6d76, 0x7cff,
    0x9489, 0x8500, 0xb79b, 0xa612, 0xd2ad, 0xc324, 0xf1bf, 0xe036,
    0x18c1, 0x0948, 0x3bd3, 0x2a5a, 0x5ee5, 0x4f6c, 0x7df7, 0x6c7e,
    0xa50a, 0xb483, 0x8618, 0x9791, 0xe32e, 0xf2a7, 0xc03c, 0xd1b5,
    0x2942, 0x38cb, 0x0a50, 0x1bd9, 0x6f66, 0x7eef, 0x4c74, 0x5dfd,
    0xb58b, 0xa402, 0x9699, 0x8710, 0xf3af, 0xe226, 0xd0bd, 0xc134,
    0x39c3, 0x284a, 0x1ad1, 0x0b58, 0x7fe7, 0x6e6e, 0x5cf5, 0x4d7c,
    0xc60c, 0xd785, 0xe51e, 0xf497, 0x8028, 0x91a1, 0xa33a, 0xb2b3,
    0x4a44, 0x5bcd, 0x6956, 0x78df, 0x0c60, 0x1de9, 0x2f72, 0x3efb,
    0xd68d, 0xc704, 0xf59f, 0xe416, 0x90a9, 0x8120, 0xb3bb, 0xa232,
    0x5ac5, 0x4b4c, 0x79d7, 0x685e, 0x1ce1, 0x0d68, 0x3ff3, 0x2e7a,
    0xe70e, 0xf687, 0xc41c, 0xd595, 0xa12a, 0xb0a3, 0x8238, 0x93b1,
    0x6b46, 0x7acf, 0x4854, 0x59dd, 0x2d62, 0x3ceb, 0x0e70, 0x1ff9,
    0xf78f, 0xe606, 0xd49d, 0xc514, 0xb1ab, 0xa022, 0x92b9, 0x8330,
    0x7bc7, 0x6a4e, 0x58d5, 0x495c, 0x3de3, 0x2c6a, 0x1ef1, 0x0f78,
]


def crc(buffer: bytes) -> int:
    """Compute CRC-16 over the given buffer.

    Returns a 16-bit integer.
    """
    value = 0x8408
    for byte in buffer:
        value = _CRC_TABLE[(value & 0xFF) ^ byte] ^ (value >> 8)
    return value
```

### 2.3 Tests — `tests/test_crc.py`

Write these exact test vectors:

| Input | Expected CRC |
|-------|-------------|
| `b''` (empty) | `33800` (`0x8408`) |
| `bytes([0x92])` | `15191` |
| `bytes([0x92, 0x01])` | `14216` |
| Two different non-empty buffers | Must differ |
| Known frame body from test data (see Appendix B) | Matches the CRC bytes in the frame |

**Acceptance:** All tests pass.

---

## 3. Phase 2 — Barcode Module

**File:** `pytap/core/barcode.py`  
**Reference:** `python/taptap/barcode.py`  
**Depends on:** nothing

### 3.1 Specification

Tigo device barcodes encode an 8-byte IEEE 802.15.4 MAC address into a human-readable format `X-NNNNNNNC`.

**MAC prefix for barcode-eligible addresses:** `04:C0:5B` (first 3 bytes).

**Barcode alphabet (16 characters, base-16, no vowels):**
```
GHJKLMNPRSTVWXYZ
```

**CRC lookup table (256 entries, 4-bit values):**
```python
_CRC_TABLE = [
    0x0, 0x3, 0x6, 0x5, 0xc, 0xf, 0xa, 0x9, 0xb, 0x8, 0xd, 0xe, 0x7, 0x4, 0x1, 0x2,
    0x5, 0x6, 0x3, 0x0, 0x9, 0xa, 0xf, 0xc, 0xe, 0xd, 0x8, 0xb, 0x2, 0x1, 0x4, 0x7,
    0xa, 0x9, 0xc, 0xf, 0x6, 0x5, 0x0, 0x3, 0x1, 0x2, 0x7, 0x4, 0xd, 0xe, 0xb, 0x8,
    0xf, 0xc, 0x9, 0xa, 0x3, 0x0, 0x5, 0x6, 0x4, 0x7, 0x2, 0x1, 0x8, 0xb, 0xe, 0xd,
    0x7, 0x4, 0x1, 0x2, 0xb, 0x8, 0xd, 0xe, 0xc, 0xf, 0xa, 0x9, 0x0, 0x3, 0x6, 0x5,
    0x2, 0x1, 0x4, 0x7, 0xe, 0xd, 0x8, 0xb, 0x9, 0xa, 0xf, 0xc, 0x5, 0x6, 0x3, 0x0,
    0xd, 0xe, 0xb, 0x8, 0x1, 0x2, 0x7, 0x4, 0x6, 0x5, 0x0, 0x3, 0xa, 0x9, 0xc, 0xf,
    0x8, 0xb, 0xe, 0xd, 0x4, 0x7, 0x2, 0x1, 0x3, 0x0, 0x5, 0x6, 0xf, 0xc, 0x9, 0xa,
    0xe, 0xd, 0x8, 0xb, 0x2, 0x1, 0x4, 0x7, 0x5, 0x6, 0x3, 0x0, 0x9, 0xa, 0xf, 0xc,
    0xb, 0x8, 0xd, 0xe, 0x7, 0x4, 0x1, 0x2, 0x0, 0x3, 0x6, 0x5, 0xc, 0xf, 0xa, 0x9,
    0x4, 0x7, 0x2, 0x1, 0x8, 0xb, 0xe, 0xd, 0xf, 0xc, 0x9, 0xa, 0x3, 0x0, 0x5, 0x6,
    0x1, 0x2, 0x7, 0x4, 0xd, 0xe, 0xb, 0x8, 0xa, 0x9, 0xc, 0xf, 0x6, 0x5, 0x0, 0x3,
    0x9, 0xa, 0xf, 0xc, 0x5, 0x6, 0x3, 0x0, 0x2, 0x1, 0x4, 0x7, 0xe, 0xd, 0x8, 0xb,
    0xc, 0xf, 0xa, 0x9, 0x0, 0x3, 0x6, 0x5, 0x7, 0x4, 0x1, 0x2, 0xb, 0x8, 0xd, 0xe,
    0x3, 0x0, 0x5, 0x6, 0xf, 0xc, 0x9, 0xa, 0x8, 0xb, 0xe, 0xd, 0x4, 0x7, 0x2, 0x1,
    0x6, 0x5, 0x0, 0x3, 0xa, 0x9, 0xc, 0xf, 0xd, 0xe, 0xb, 0x8, 0x1, 0x2, 0x7, 0x4,
]
```

### 3.2 Encode Algorithm

```
Input: 8-byte address (LongAddress)
Output: string in format "X-NNNNNNNC" or None if prefix doesn't match

1. Check bytes[0:3] == [0x04, 0xC0, 0x5B]. If not, return None.
2. leading_nibble = (bytes[3] >> 4) & 0xF  →  hex char (uppercase)
3. Extract the remaining 9 nibbles from bytes[3:8]:
     bytes[3] & 0xF, bytes[4]>>4, bytes[4]&0xF, bytes[5]>>4, bytes[5]&0xF,
     bytes[6]>>4, bytes[6]&0xF, bytes[7]>>4, bytes[7]&0xF
   Combine into an integer, format as 7-digit uppercase hex string
4. Compute CRC:
     crc = 2  (initial value)
     for each of the 8 address bytes:
         crc = _CRC_TABLE[byte ^ (crc << 4)]
   check_char = _ALPHABET[crc]
5. Return f"{leading_nibble}-{middle_hex}{check_char}"
```

### 3.3 Decode Algorithm

```
Input: string like "S-1234567A"
Output: 8-byte address, or error

1. Parse leading char → leading_nibble (int, 0-15 from hex)
2. Parse middle part (s[2:-1]) → integer (hex)
3. Parse check char → expected CRC nibble
4. Reconstruct 8-byte address:
     addr_int = (0x04C05B0 | leading_nibble) << 36 | middle_int
     Convert to 8 big-endian bytes
5. Verify CRC matches
```

### 3.4 Tests — `tests/test_barcode.py`

- Encode `04:C0:5B:30:00:02:BE:16` → verify produces valid barcode string
- Decode the result → verify round-trip to same 8 bytes
- Non-matching prefix (`00:11:22:...`) → returns `None`
- Invalid check character → raises error
- Known barcode from test data: address `04:C0:5B:30:00:02:BE:16` appears in `ENUMERATION_SEQUENCE`

**Acceptance:** Encode/decode round-trips for all valid addresses; non-Tigo addresses return None.

---

## 4. Phase 3 — Protocol Types

**File:** `pytap/core/types.py`  
**Reference:** Multiple files from `python/taptap/gateway/link/`, `python/taptap/pv/`  
**Depends on:** nothing

### 4.1 All Types to Implement

Implement these as `@dataclass(frozen=True)` or `IntEnum` classes in a single file.

#### 4.1.1 `GatewayID`

```python
@dataclass(frozen=True)
class GatewayID:
    value: int  # 15-bit: 0 <= value <= 0x7FFF (32767)

    def __post_init__(self):
        if not (0 <= self.value <= 0x7FFF):
            raise ValueError(f"GatewayID must be 0-32767, got {self.value}")
```

#### 4.1.2 `Address`

```python
@dataclass(frozen=True)
class Address:
    gateway_id: GatewayID
    is_from: bool  # True = gateway→controller, False = controller→gateway

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Address':
        value = struct.unpack('>H', data)[0]     # big-endian u16
        is_from = bool(value & 0x8000)            # bit 15 = direction
        gateway_id = GatewayID(value & 0x7FFF)    # bits 14-0 = ID
        return cls(gateway_id, is_from)
```

#### 4.1.3 `FrameType`

```python
class FrameType(IntEnum):
    RECEIVE_REQUEST          = 0x0148
    RECEIVE_RESPONSE         = 0x0149
    COMMAND_REQUEST          = 0x0B0F
    COMMAND_RESPONSE         = 0x0B10
    PING_REQUEST             = 0x0B00
    PING_RESPONSE            = 0x0B01
    ENUMERATION_START_REQUEST  = 0x0014
    ENUMERATION_START_RESPONSE = 0x0015
    ENUMERATION_REQUEST      = 0x0038
    ENUMERATION_RESPONSE     = 0x0039
    ASSIGN_GATEWAY_ID_REQUEST  = 0x003C
    ASSIGN_GATEWAY_ID_RESPONSE = 0x003D
    IDENTIFY_REQUEST         = 0x003A
    IDENTIFY_RESPONSE        = 0x003B
    VERSION_REQUEST          = 0x000A
    VERSION_RESPONSE         = 0x000B
    ENUMERATION_END_REQUEST  = 0x0E02
    ENUMERATION_END_RESPONSE = 0x0006
```

#### 4.1.4 `Frame`

```python
@dataclass(frozen=True)
class Frame:
    address: Address
    frame_type: int    # raw u16 (may or may not match FrameType enum)
    payload: bytes
```

#### 4.1.5 `NodeID`

```python
@dataclass(frozen=True)
class NodeID:
    value: int  # u16, 1-65535 (non-zero)
    GATEWAY: ClassVar[int] = 1

    def __post_init__(self):
        if not (1 <= self.value <= 0xFFFF):
            raise ValueError(f"NodeID must be 1-65535, got {self.value}")

    @classmethod
    def from_node_address(cls, addr: 'NodeAddress') -> 'NodeID':
        return cls(addr.value)  # NodeAddress 0 (broadcast) is invalid as NodeID
```

#### 4.1.6 `NodeAddress`

```python
@dataclass(frozen=True)
class NodeAddress:
    value: int  # u16, 0-65535. 0 = broadcast.

    @classmethod
    def from_bytes(cls, data: bytes) -> 'NodeAddress':
        return cls(struct.unpack('>H', data)[0])
```

#### 4.1.7 `LongAddress`

```python
@dataclass(frozen=True)
class LongAddress:
    data: bytes  # exactly 8 bytes, IEEE 802.15.4 64-bit MAC

    def __post_init__(self):
        if len(self.data) != 8:
            raise ValueError(f"LongAddress must be 8 bytes, got {len(self.data)}")

    def __str__(self) -> str:
        return ':'.join(f'{b:02X}' for b in self.data)

    @classmethod
    def from_str(cls, s: str) -> 'LongAddress':
        return cls(bytes.fromhex(s.replace(':', '')))
```

#### 4.1.8 `RSSI`

```python
@dataclass(frozen=True)
class RSSI:
    value: int  # u8, 0-255
```

#### 4.1.9 `SlotCounter`

```python
SLOTS_PER_EPOCH = 12000
MAX_SLOT_NUMBER = 11999

@dataclass(frozen=True)
class SlotCounter:
    raw: int  # u16

    @property
    def epoch(self) -> int:
        return (self.raw >> 14) & 0x3    # 2-bit, 0-3

    @property
    def slot_number(self) -> int:
        return self.raw & 0x3FFF         # 14-bit, 0-16383

    @classmethod
    def from_bytes(cls, data: bytes) -> 'SlotCounter':
        return cls(struct.unpack('>H', data)[0])

    def slots_since(self, past: 'SlotCounter') -> int:
        epoch_diff = (self.epoch - past.epoch) % 4
        if epoch_diff == 0:
            return self.slot_number - past.slot_number
        elif epoch_diff == 1:
            return (MAX_SLOT_NUMBER - past.slot_number + 1) + self.slot_number
        else:  # 2 or 3
            return epoch_diff * SLOTS_PER_EPOCH + (self.slot_number - past.slot_number)
```

#### 4.1.10 `PacketType`

```python
class PacketType(IntEnum):
    STRING_REQUEST                      = 0x06
    STRING_RESPONSE                     = 0x07
    TOPOLOGY_REPORT                     = 0x09
    GATEWAY_RADIO_CONFIGURATION_REQUEST = 0x0D
    GATEWAY_RADIO_CONFIGURATION_RESPONSE = 0x0E
    PV_CONFIGURATION_REQUEST            = 0x13
    PV_CONFIGURATION_RESPONSE           = 0x18
    BROADCAST                           = 0x22
    BROADCAST_ACK                       = 0x23
    NODE_TABLE_REQUEST                   = 0x26
    NODE_TABLE_RESPONSE                  = 0x27
    LONG_NETWORK_STATUS_REQUEST         = 0x2D
    NETWORK_STATUS_REQUEST              = 0x2E
    NETWORK_STATUS_RESPONSE             = 0x2F
    POWER_REPORT                        = 0x31
```

#### 4.1.11 `ReceivedPacketHeader`

```python
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
        return cls(
            packet_type=data[0],
            node_address=struct.unpack('>H', data[1:3])[0],
            short_address=struct.unpack('>H', data[3:5])[0],
            dsn=data[5],
            data_length=data[6],
        )
```

#### 4.1.12 `U12Pair`

```python
@dataclass(frozen=True)
class U12Pair:
    """Two 12-bit values packed into 3 bytes."""
    first: int
    second: int

    @classmethod
    def from_bytes(cls, data: bytes) -> 'U12Pair':
        # data is exactly 3 bytes
        first = (data[0] << 4) | (data[1] >> 4)           # upper 12 bits
        second = ((data[1] & 0x0F) << 8) | data[2]        # lower 12 bits
        return cls(first, second)
```

#### 4.1.13 `PowerReport`

```python
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
        return self.voltage_in_out.first / 20.0

    @property
    def voltage_out(self) -> float:
        return self.voltage_in_out.second / 10.0

    @property
    def current(self) -> float:
        return self.current_temp.first / 200.0

    @property
    def temperature(self) -> float:
        raw = self.current_temp.second
        if raw & 0x800:
            raw = raw | 0xF000          # sign-extend to 16-bit signed
            raw = raw - 0x10000 if raw >= 0x8000 else raw
        return raw / 10.0

    @property
    def duty_cycle(self) -> float:
        return self.dc_dc_duty_cycle_raw / 255.0
```

#### 4.1.14 Helper types

```python
@dataclass(frozen=True)
class GatewayInfo:
    address: LongAddress | None = None
    version: str | None = None

@dataclass(frozen=True)
class NodeInfo:
    address: LongAddress | None = None
    barcode: str | None = None
```

### 4.2 Tests — `tests/test_types.py`

- `GatewayID`: valid (0, 32767), invalid (-1, 32768)
- `Address.from_bytes`: controller→gateway (bit 15=0), gateway→controller (bit 15=1)
- `SlotCounter`: epoch extraction, slot_number extraction, `slots_since()` with same epoch, crossing epoch, wrapping
- `U12Pair.from_bytes`: `bytes([0xAB, 0xCD, 0xEF])` → first=`0xABC`, second=`0xDEF`
- `PowerReport.from_bytes`: 13-byte input, verify all derived properties
- `ReceivedPacketHeader.from_bytes`: 7-byte input, verify field values
- `FrameType` enum: verify all 18 values match the table above

**Acceptance:** All type constructors, validators, and conversions are tested.

---

## 5. Phase 4 — Event Types

**File:** `pytap/core/events.py`  
**Reference:** `python/taptap/observer/event.py`  
**Depends on:** `types.py`

### 5.1 Implementation

```python
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    """Base event. All events have a type discriminator and timestamp."""
    event_type: str
    timestamp: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d


@dataclass
class PowerReportEvent(Event):
    gateway_id: int
    node_id: int
    barcode: Optional[str]
    voltage_in: float
    voltage_out: float
    current: float
    power: float             # = voltage_out × current
    temperature: float
    dc_dc_duty_cycle: float
    rssi: int

    def __init__(self, *, gateway_id, node_id, barcode, voltage_in, voltage_out,
                 current, temperature, dc_dc_duty_cycle, rssi, timestamp):
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
    gateways: dict       # {gw_id_int: {"address": str|None, "version": str|None}}
    nodes: dict          # {node_id_int: {"address": str|None, "barcode": str|None}}

    def __init__(self, *, gateways, nodes, timestamp):
        super().__init__(event_type='infrastructure', timestamp=timestamp)
        self.gateways = gateways
        self.nodes = nodes


@dataclass
class TopologyEvent(Event):
    gateway_id: int
    node_id: int
    data: bytes            # raw topology report bytes (parsing TBD)

    def __init__(self, *, gateway_id, node_id, data, timestamp):
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
    gateway_id: int
    node_id: int
    direction: str         # "request" or "response"
    content: str

    def __init__(self, *, gateway_id, node_id, direction, content, timestamp):
        super().__init__(event_type='string', timestamp=timestamp)
        self.gateway_id = gateway_id
        self.node_id = node_id
        self.direction = direction
        self.content = content
```

### 5.2 Tests

- Construct each event type, verify `to_dict()` output
- Verify `power` field is computed correctly
- Verify `event_type` discriminator is set correctly
- Verify `timestamp` is serialized as ISO 8601 string

**Acceptance:** All 4 event types construct and serialize without error.

---

## 6. Phase 5 — State Management

**File:** `pytap/core/state.py`  
**Reference:** `python/taptap/observer/slot_clock.py`, `persistent_state.py`, `node_table.py`  
**Depends on:** `types.py`

### 6.1 SlotClock

Maps `SlotCounter` values to wall-clock `datetime` objects.

```python
class SlotClock:
    NOMINAL_MS_PER_SLOT = 5.0
    SLOTS_PER_INDEX = 1000
    NUM_INDICES = 48         # 4 epochs × 12 indices each = 48

    def __init__(self, slot_counter: SlotCounter, time: datetime):
        self._times: list[datetime] = [None] * self.NUM_INDICES
        self._last_index: int = -1
        self._last_time: datetime = time
        self._initialize(slot_counter, time)

    @staticmethod
    def _index_and_offset(sc: SlotCounter) -> tuple[int, timedelta]:
        absolute_slot = sc.epoch * SLOTS_PER_EPOCH + sc.slot_number
        index = absolute_slot // 1000
        offset = timedelta(milliseconds=5.0 * (absolute_slot % 1000))
        return index, offset

    def _initialize(self, sc: SlotCounter, time: datetime):
        index, offset = self._index_and_offset(sc)
        base = time - offset
        self._times[index] = base
        for i in range(1, self.NUM_INDICES):
            prev = (index - i) % self.NUM_INDICES
            self._times[prev] = base - timedelta(milliseconds=5000.0 * i)
        self._last_index = index
        self._last_time = time

    def set(self, sc: SlotCounter, time: datetime):
        if time < self._last_time:
            self._initialize(sc, time)
            return
        index, offset = self._index_and_offset(sc)
        self._times[index] = time - offset
        # Backfill intermediate indices with nominal timing
        if index != self._last_index:
            steps = (index - self._last_index) % self.NUM_INDICES
            for i in range(1, steps):
                fill_idx = (self._last_index + i) % self.NUM_INDICES
                self._times[fill_idx] = (self._times[self._last_index]
                                          + timedelta(milliseconds=5000.0 * i))
        self._last_index = index
        self._last_time = time

    def get(self, sc: SlotCounter) -> datetime:
        index, offset = self._index_and_offset(sc)
        return self._times[index] + offset
```

### 6.2 NodeTableBuilder

Accumulates node table pages until an empty page signals completion.

```python
class NodeTableBuilder:
    def __init__(self):
        self._entries: dict[int, LongAddress] = {}

    def push(self, start_address: NodeAddress, entries: list[tuple[NodeAddress, LongAddress]]
             ) -> dict[int, LongAddress] | None:
        """Add a page. Returns complete table when an empty page is received."""
        if len(entries) == 0:
            result = dict(self._entries)
            self._entries.clear()
            return result if result else None
        for node_addr, long_addr in entries:
            self._entries[node_addr.value] = long_addr
        return None
```

### 6.3 PersistentState

```python
@dataclass
class PersistentState:
    gateway_identities: dict[int, LongAddress]     # gw_id_int → address
    gateway_versions: dict[int, str]               # gw_id_int → version
    gateway_node_tables: dict[int, dict[int, LongAddress]]  # gw → {node_id → addr}

    def __init__(self):
        self.gateway_identities = {}
        self.gateway_versions = {}
        self.gateway_node_tables = {}

    def save(self, path: Path):
        """Atomic write: write to .tmp then rename."""
        tmp = path.with_suffix('.tmp')
        data = {
            'gateway_identities': {
                str(k): str(v) for k, v in self.gateway_identities.items()
            },
            'gateway_versions': {
                str(k): v for k, v in self.gateway_versions.items()
            },
            'gateway_node_tables': {
                str(gw): {str(nid): str(addr) for nid, addr in nodes.items()}
                for gw, nodes in self.gateway_node_tables.items()
            },
        }
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)          # atomic on POSIX

    @classmethod
    def load(cls, path: Path) -> 'PersistentState':
        state = cls()
        try:
            with open(path) as f:
                data = json.load(f)
            for k, v in data.get('gateway_identities', {}).items():
                state.gateway_identities[int(k)] = LongAddress.from_str(v)
            for k, v in data.get('gateway_versions', {}).items():
                state.gateway_versions[int(k)] = v
            for gw, nodes in data.get('gateway_node_tables', {}).items():
                state.gateway_node_tables[int(gw)] = {
                    int(nid): LongAddress.from_str(addr)
                    for nid, addr in nodes.items()
                }
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        return state
```

### 6.4 Tests

- **SlotClock:** init with a slot counter and time, then `get()` returns times within expected tolerance. Test `set()` with advancing slot counters.
- **NodeTableBuilder:** push 2 pages with entries, then empty page → returns merged table. Push empty page immediately → returns None.
- **PersistentState:** save/load round trip via `tmp_path` fixture. Load non-existent file → empty state.

**Acceptance:** All state management logic tested with known inputs/outputs.

---

## 7. Phase 6 — Parser Core

**File:** `pytap/core/parser.py`  
**Reference:** entire `python/taptap/gateway/` + `pv/` + `observer/` chain  
**Depends on:** `crc.py`, `types.py`, `events.py`, `state.py`, `barcode.py`

This is the largest and most complex phase. It consolidates 4 Receiver classes and the Observer into one.

### 7.1 Internal State

```python
class Parser:
    def __init__(self, state_file: str | Path | None = None):
        # Frame accumulator state
        self._state: _FrameState = _FrameState.IDLE
        self._buffer: bytearray = bytearray()

        # Transport state
        self._rx_packet_numbers: dict[int, int] = {}            # gw_id → last packet_number
        self._commands_awaiting: dict[tuple[int, int], tuple[int, bytes]] = {}
        self._command_sequence_numbers: dict[int, int] = {}     # gw_id → last seq

        # Slot clocks (one per gateway)
        self._slot_clocks: dict[int, SlotClock] = {}
        self._captured_slot_times: dict[int, datetime] = {}     # gw_id → capture time

        # Enumeration state
        self._enum_state: _EnumerationState | None = None

        # Infrastructure
        self._persistent_state: PersistentState
        self._state_file: Path | None
        self._node_table_builders: dict[int, NodeTableBuilder] = {}

        # Counters
        self._counters: _Counters = _Counters()

        # Load persistent state
        ...
```

### 7.2 Frame State Machine

```python
class _FrameState(Enum):
    IDLE = 0
    NOISE = 1
    START_OF_FRAME = 2
    FRAME = 3
    FRAME_ESCAPE = 4
    GIANT = 5
    GIANT_ESCAPE = 6

MAX_FRAME_SIZE = 256
```

**Implement `_accumulate(byte: int) -> Frame | None`:**

This method is called for EVERY byte. It maintains the state machine and returns a decoded `Frame` when a complete, valid frame is detected, or `None` otherwise.

Transition logic — exactly match the state machine from Section 2.3 above (reference specification). Key details:

- **IDLE:** `0x00`/`0xFF` → stay IDLE. `0x7E` → `START_OF_FRAME`. Anything else → `NOISE`.
- **NOISE:** `0x00`/`0xFF` → IDLE. `0x7E` → `START_OF_FRAME`. Else stay.
- **START_OF_FRAME:** `0x07` → FRAME (clear buffer). Anything else → `NOISE`.
- **FRAME:** `0x7E` → `FRAME_ESCAPE`. If buffer < MAX, append byte. Else → `GIANT`.
- **FRAME_ESCAPE:** `0x08` → parse completed frame from buffer → IDLE. `0x07` → restart FRAME. Else: try unescape byte. If valid and buffer < MAX → append, → FRAME. If valid but buffer >= MAX → GIANT. If invalid escape → NOISE.
- **GIANT / GIANT_ESCAPE:** consume bytes until `0x7E 0x08` (→ IDLE) or `0x7E 0x07` (→ FRAME restart).

**Implement `_decode_frame(buffer: bytearray) -> Frame | None`:**

```
1. if len(buffer) < 6: self._counters.runts += 1; return None
2. body = bytes(buffer[:-2])
3. expected_crc = int.from_bytes(buffer[-2:], 'little')   # CRC is little-endian
4. if crc(body) != expected_crc: self._counters.crc_errors += 1; return None
5. address = Address.from_bytes(buffer[0:2])               # big-endian u16
6. frame_type = int.from_bytes(buffer[2:4], 'big')         # big-endian u16
7. payload = bytes(buffer[4:-2])
8. return Frame(address, frame_type, payload)
```

**Implement byte unescaping (inline, not a separate module):**

```python
_UNESCAPE_MAP: dict[int, int] = {
    0x00: 0x7E,
    0x01: 0x24,
    0x02: 0x23,
    0x03: 0x25,
    0x04: 0xA4,
    0x05: 0xA3,
    0x06: 0xA5,
}

def _unescape_byte(b: int) -> int | None:
    return _UNESCAPE_MAP.get(b)
```

### 7.3 Frame Dispatch

**Implement `_dispatch_frame(frame: Frame) -> list[Event]`:**

Route `frame.frame_type` to handler methods. Each handler returns `list[Event]` (usually empty; only packet parsers produce events).

```python
match frame.frame_type:
    case FrameType.RECEIVE_REQUEST:
        return self._handle_receive_request(frame)
    case FrameType.RECEIVE_RESPONSE:
        return self._handle_receive_response(frame)
    case FrameType.COMMAND_REQUEST:
        return self._handle_command_request(frame)
    case FrameType.COMMAND_RESPONSE:
        return self._handle_command_response(frame)
    case FrameType.ENUMERATION_START_REQUEST:
        return self._handle_enumeration_start(frame)
    case FrameType.ENUMERATION_RESPONSE:
        return self._handle_enumeration_response(frame)
    case FrameType.IDENTIFY_RESPONSE:
        return self._handle_identify_response(frame)
    case FrameType.VERSION_RESPONSE:
        return self._handle_version_response(frame)
    case FrameType.ENUMERATION_END_RESPONSE:
        return self._handle_enumeration_end(frame)
    case _:
        return []
```

### 7.4 Transport Handlers

#### `_handle_receive_request(frame)` → `list[Event]`

```
1. Validate frame.address.is_from == False (controller → gateway)
2. Parse 5-byte payload: packet_number = int.from_bytes(payload[2:4], 'big')
3. Store: self._rx_packet_numbers[gw_id] = packet_number
4. Record capture time: self._captured_slot_times[gw_id] = datetime.now()
5. Return []
```

#### `_handle_receive_response(frame)` → `list[Event]`

```
1. Validate frame.address.is_from == True
2. Get gw_id = frame.address.gateway_id.value
3. Get old_packet_number from self._rx_packet_numbers.get(gw_id, 0)
4. Parse ReceiveResponse from payload (see parsing spec below)
5. Update stored packet number
6. Process slot counter:
   a. Get capture_time from self._captured_slot_times.pop(gw_id, None)
   b. If capture_time exists → update or create SlotClock for this gateway
7. Iterate ReceivedPackets from remaining bytes
8. For each (header_bytes, data_bytes):
   a. Parse ReceivedPacketHeader
   b. Call self._parse_pv_packet(gw_id, header, data_bytes)
   c. Collect returned events
9. Return accumulated events
```

**ReceiveResponse parsing (inline in handler):**

```
1. status_type = int.from_bytes(payload[0:2], 'big')
2. if (status_type & 0x00E0) != 0x00E0: return []  # invalid
3. offset = 2
4. if not (status_type & 0x0001): offset += 1   # rx_buffers_used
5. if not (status_type & 0x0002): offset += 1   # tx_buffers_free
6. if not (status_type & 0x0004): offset += 2   # unknown_a
7. if not (status_type & 0x0008): offset += 2   # unknown_b
8. if not (status_type & 0x0010):
     packet_number = int.from_bytes(payload[offset:offset+2], 'big')
     offset += 2
   else:
     lo = payload[offset]; offset += 1
     packet_number = _interpret_packet_number_lo(lo, old_packet_number)
9. slot_counter = SlotCounter.from_bytes(payload[offset:offset+2]); offset += 2
10. received_data = payload[offset:]
```

**`_interpret_packet_number_lo(new_lo, old)` (free function):**

```python
def _interpret_packet_number_lo(new_lo: int, old: int) -> int:
    old_hi = (old >> 8) & 0xFF
    old_lo = old & 0xFF
    new_hi = old_hi if new_lo >= old_lo else (old_hi + 1) & 0xFF
    return (new_hi << 8) | new_lo
```

**ReceivedPackets iteration (inline):**

```python
def _iter_received_packets(data: bytes) -> Iterator[tuple[bytes, bytes]]:
    offset = 0
    while offset < len(data):
        if offset + 7 > len(data):
            break  # truncated header
        header_bytes = data[offset:offset+7]
        data_length = header_bytes[6]
        if offset + 7 + data_length > len(data):
            break  # truncated data
        pkt_data = data[offset+7:offset+7+data_length]
        offset += 7 + data_length
        yield header_bytes, pkt_data
```

#### `_handle_command_request(frame)` → `list[Event]`

```
1. Validate is_from == False, payload >= 5 bytes
2. packet_type = payload[3]
3. sequence_number = payload[4]
4. gw_id = frame.address.gateway_id.value
5. Check for retransmit: if gw_id in _command_sequence_numbers and same seq → skip
6. Store: _command_sequence_numbers[gw_id] = sequence_number
7. Store: _commands_awaiting[(gw_id, sequence_number)] = (packet_type, payload[5:])
8. Return []
```

#### `_handle_command_response(frame)` → `list[Event]`

```
1. Validate is_from == True, payload >= 5 bytes
2. resp_packet_type = payload[3]
3. resp_seq = payload[4]
4. gw_id = frame.address.gateway_id.value
5. key = (gw_id, resp_seq)
6. Pop (req_type, req_payload) from _commands_awaiting.get(key). If missing → return []
7. resp_payload = payload[5:]
8. Return self._handle_command_pair(gw_id, req_type, req_payload, resp_packet_type, resp_payload)
```

#### `_handle_command_pair(gw_id, req_type, req_payload, resp_type, resp_payload)` → `list[Event]`

```
if req_type == PacketType.NODE_TABLE_REQUEST and resp_type == PacketType.NODE_TABLE_RESPONSE:
    return self._handle_node_table_command(gw_id, req_payload, resp_payload)
elif req_type == PacketType.STRING_REQUEST and resp_type == PacketType.STRING_RESPONSE:
    return self._handle_string_command(gw_id, req_payload, resp_payload)
else:
    return []
```

### 7.5 Enumeration Handlers

```python
@dataclass
class _EnumerationState:
    enumeration_gateway_id: int
    gateway_identities: dict[int, LongAddress]
    gateway_versions: dict[int, str]
```

#### `_handle_enumeration_start(frame)` → `list[Event]`

```
1. Validate is_from == False, gateway_id == 0, payload >= 6 bytes
2. enum_addr = Address.from_bytes(payload[4:6])
3. self._enum_state = _EnumerationState(
       enumeration_gateway_id=enum_addr.gateway_id.value,
       gateway_identities={}, gateway_versions={})
4. Return []
```

#### `_handle_enumeration_response(frame)` / `_handle_identify_response(frame)`

```
1. Validate is_from == True, payload >= 8 bytes
2. long_address = LongAddress(payload[0:8])
3. gw_id = frame.address.gateway_id.value
4. If self._enum_state is not None:
     if gw_id != self._enum_state.enumeration_gateway_id:
       self._enum_state.gateway_identities[gw_id] = long_address
   else:
     self._persistent_state.gateway_identities[gw_id] = long_address
     return self._emit_infrastructure_event()
5. Return []
```

#### `_handle_version_response(frame)` → `list[Event]`

```
1. Validate is_from == True
2. version = payload.decode('utf-8', errors='replace')
3. gw_id = frame.address.gateway_id.value
4. If self._enum_state is not None:
     self._enum_state.gateway_versions[gw_id] = version
   else:
     self._persistent_state.gateway_versions[gw_id] = version
     return self._emit_infrastructure_event()
5. Return []
```

#### `_handle_enumeration_end(frame)` → `list[Event]`

```
1. Validate is_from == True
2. If self._enum_state is not None:
     Apply atomically:
       self._persistent_state.gateway_identities = self._enum_state.gateway_identities
       self._persistent_state.gateway_versions = self._enum_state.gateway_versions
     self._enum_state = None
     return self._emit_infrastructure_event()
3. Return []
```

### 7.6 PV Packet Parsing

#### `_parse_pv_packet(gw_id, header, data)` → `list[Event]`

```
node_addr = header.node_address
try:
    node_id = node_addr   # NodeID value = NodeAddress value (if non-zero)
except:
    return []

match header.packet_type:
    case PacketType.POWER_REPORT:
        return self._handle_power_report(gw_id, node_id, data)
    case PacketType.STRING_RESPONSE:
        return self._handle_string_response(gw_id, node_id, data)
    case PacketType.TOPOLOGY_REPORT:
        return self._handle_topology_report(gw_id, node_id, data)
    case _:
        return []
```

#### `_handle_power_report(gw_id, node_id, data)` → `list[Event]`

```
1. Parse PowerReport.from_bytes(data)  (try 13 bytes; also accept >= 15 bytes, use first 13)
2. Get SlotClock for this gateway. If missing → log warning, return []
3. timestamp = slot_clock.get(report.slot_counter)
4. Look up barcode from persistent state node tables
5. Create PowerReportEvent(
     gateway_id=gw_id, node_id=node_id, barcode=barcode,
     voltage_in=report.voltage_in, voltage_out=report.voltage_out,
     current=report.current, temperature=report.temperature,
     dc_dc_duty_cycle=report.duty_cycle, rssi=report.rssi,
     timestamp=timestamp)
6. Return [event]
```

#### `_handle_string_response(gw_id, node_id, data)` → `list[Event]`

```
content = data.decode('utf-8', errors='replace')
return [StringEvent(gateway_id=gw_id, node_id=node_id,
                    direction='response', content=content,
                    timestamp=datetime.now())]
```

#### `_handle_topology_report(gw_id, node_id, data)` → `list[Event]`

```
return [TopologyEvent(gateway_id=gw_id, node_id=node_id, data=data,
                      timestamp=datetime.now())]
```

#### `_handle_node_table_command(gw_id, req_payload, resp_payload)` → `list[Event]`

```
1. start_address = NodeAddress.from_bytes(req_payload[0:2])
2. entries_count = resp_payload[0]
3. entries_data = resp_payload[1:]
4. if len(entries_data) != entries_count * 10: return []   # corrupt
5. entries = []
   for i in range(entries_count):
       off = i * 10
       node_addr = NodeAddress.from_bytes(entries_data[off:off+2])
       long_addr = LongAddress(entries_data[off+2:off+10])
       entries.append((node_addr, long_addr))
6. builder = self._node_table_builders.setdefault(gw_id, NodeTableBuilder())
7. result = builder.push(start_address, entries)
8. if result is not None:
     self._persistent_state.gateway_node_tables[gw_id] = result
     self._save_persistent_state()
     return self._emit_infrastructure_event()
9. return []
```

#### `_handle_string_command(gw_id, req_payload, resp_payload)` → `list[Event]`

```
1. node_addr = NodeAddress.from_bytes(req_payload[0:2])
2. request_str = req_payload[2:].decode('utf-8', errors='replace')
3. return [StringEvent(gateway_id=gw_id, node_id=node_addr.value,
                       direction='request', content=request_str,
                       timestamp=datetime.now())]
```

### 7.7 Infrastructure Event Helper

```python
def _emit_infrastructure_event(self) -> list[Event]:
    """Build an InfrastructureEvent from current persistent state."""
    gateways = {}
    for gw_id, addr in self._persistent_state.gateway_identities.items():
        gateways[gw_id] = {
            'address': str(addr),
            'version': self._persistent_state.gateway_versions.get(gw_id),
        }
    # Include gateways with only version info
    for gw_id, ver in self._persistent_state.gateway_versions.items():
        if gw_id not in gateways:
            gateways[gw_id] = {'address': None, 'version': ver}

    nodes = {}
    for gw_id, table in self._persistent_state.gateway_node_tables.items():
        for node_id_val, long_addr in table.items():
            barcode = Barcode.from_address(long_addr)  # returns str or None
            nodes[node_id_val] = {
                'address': str(long_addr),
                'barcode': barcode,
            }

    self._save_persistent_state()
    return [InfrastructureEvent(
        gateways=gateways, nodes=nodes, timestamp=datetime.now())]
```

### 7.8 Public Interface

```python
def feed(self, data: bytes) -> list[Event]:
    """Feed raw bytes, return parsed events."""
    events: list[Event] = []
    for byte in data:
        frame = self._accumulate(byte)
        if frame is not None:
            self._counters.frames += 1
            events.extend(self._dispatch_frame(frame))
    return events

def reset(self):
    """Reset frame accumulation state (not infrastructure)."""
    self._state = _FrameState.IDLE
    self._buffer.clear()

@property
def infrastructure(self) -> dict:
    """Current infrastructure snapshot."""
    return {
        'gateways': {
            gw: {'address': str(self._persistent_state.gateway_identities.get(gw)),
                 'version': self._persistent_state.gateway_versions.get(gw)}
            for gw in set(self._persistent_state.gateway_identities)
                     | set(self._persistent_state.gateway_versions)
        },
        'nodes': {
            nid: {'address': str(addr), 'barcode': Barcode.from_address(addr)}
            for gw_table in self._persistent_state.gateway_node_tables.values()
            for nid, addr in gw_table.items()
        },
    }

@property
def counters(self) -> dict:
    return asdict(self._counters)
```

### 7.9 Counters

```python
@dataclass
class _Counters:
    frames_received: int = 0
    crc_errors: int = 0
    runts: int = 0
    giants: int = 0
    noise_bytes: int = 0
```

### 7.10 Tests — `tests/test_parser.py`

These are the **critical** tests. They validate the entire pipeline.

#### Test 1: Frame accumulation

```python
def test_frame_accumulation():
    """Feed a valid frame with preamble/terminator, get Frame back."""
    from pytap.core.crc import crc
    parser = Parser()
    # Build: address(2) + frame_type(2) + payload + crc(2)
    body = bytes([0x12, 0x01, 0x0B, 0x00, 0x01])  # addr=0x1201, type=PING_REQUEST, payload=0x01
    c = crc(body)
    raw = bytes([0xFF, 0x7E, 0x07]) + body + c.to_bytes(2, 'little') + bytes([0x7E, 0x08])
    events = parser.feed(raw)
    assert parser.counters['frames_received'] == 1
    assert parser.counters['crc_errors'] == 0
```

#### Test 2: CRC error

```python
def test_crc_error():
    parser = Parser()
    body = bytes([0x12, 0x01, 0x0B, 0x00, 0x01])
    raw = bytes([0x7E, 0x07]) + body + bytes([0xFF, 0xFF]) + bytes([0x7E, 0x08])
    parser.feed(raw)
    assert parser.counters['crc_errors'] == 1
    assert parser.counters['frames_received'] == 0
```

#### Test 3: Runt frame

```python
def test_runt():
    parser = Parser()
    raw = bytes([0x7E, 0x07, 0xAA, 0xBB, 0x7E, 0x08])  # only 2 body bytes, need >= 6
    parser.feed(raw)
    assert parser.counters['runts'] == 1
```

#### Test 4: Enumeration sequence

Use `ENUMERATION_SEQUENCE` from Appendix B. Feed the full byte sequence and verify:
- Multiple frames parsed (>10)
- At least one `InfrastructureEvent` emitted with gateway identity
- No CRC errors

#### Test 5: Byte-at-a-time feeding

Same data as Test 1 but feed one byte per `feed()` call → same result.

#### Test 6: Escape handling

Build a frame whose body contains bytes requiring escaping (`0x7E` → `0x7E 0x00`, etc.). Verify correct parsing.

#### Test 7: Giant frame

Feed a frame with >256 body bytes → increment giants counter, no crash.

**Acceptance:** All parser tests pass. The enumeration sequence test produces infrastructure events with the correct gateway address `04:C0:5B:30:00:02:BE:16`.

---

## 8. Phase 7 — Data Sources

**File:** `pytap/core/source.py`  
**Depends on:** nothing (uses standard library + optional `pyserial`)

### 8.1 TcpSource

```python
class TcpSource:
    def __init__(self, host: str, port: int = 502):
        self._host = host
        self._port = port
        self._socket: socket.socket | None = None

    def connect(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(10.0)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Platform-specific keepalive tuning (try/except for portability)
        try:
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except (AttributeError, OSError):
            pass
        self._socket.connect((self._host, self._port))

    def read(self, size: int = 1024) -> bytes:
        try:
            data = self._socket.recv(size)
            return data
        except socket.timeout:
            return b''
        except (ConnectionResetError, BrokenPipeError, OSError):
            return b''

    def close(self):
        if self._socket:
            self._socket.close()
            self._socket = None
```

### 8.2 SerialSource

```python
class SerialSource:
    def __init__(self, port: str, baud_rate: int = 38400):
        import serial
        self._serial = serial.Serial(
            port=port, baudrate=baud_rate,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE, timeout=1.0)

    def read(self, size: int = 1024) -> bytes:
        return self._serial.read(size)

    def close(self):
        self._serial.close()
```

> **Note:** The existing Python port uses baud rate 9600, but the protocol spec and Rust implementation use **38400**. Use 38400 unless testing shows otherwise.

### 8.3 Tests

- **TcpSource:** Unit test with a mock socket (or localhost server) — connect, read, close.
- **SerialSource:** Skip if pyserial not installed. Test constructor validation.

**Acceptance:** Sources can be instantiated and produce bytes.

---

## 9. Phase 8 — Public API

**File:** `pytap/api.py`  
**Depends on:** `parser.py`, `source.py`

### 9.1 Implementation

```python
"""pytap public API — all protocol logic accessible via function calls."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .core.parser import Parser
from .core.events import Event
from .core.source import TcpSource, SerialSource

logger = logging.getLogger(__name__)


def create_parser(state_file: str | Path | None = None) -> Parser:
    return Parser(state_file=state_file)


def parse_bytes(data: bytes, state_file: str | Path | None = None) -> list[Event]:
    parser = Parser(state_file=state_file)
    return parser.feed(data)


def connect(source_config: dict):
    if 'tcp' in source_config:
        src = TcpSource(source_config['tcp'], source_config.get('port', 502))
        src.connect()
        return src
    elif 'serial' in source_config:
        return SerialSource(source_config['serial'])
    else:
        raise ValueError("source_config must contain 'tcp' or 'serial' key")


def observe(
    source_config: dict,
    callback: Callable[[Event], None],
    state_file: str | Path | None = None,
    reconnect_timeout: int = 60,
    reconnect_retries: int = 0,
    reconnect_delay: int = 5,
) -> None:
    parser = Parser(state_file=state_file)
    retries = 0

    while True:
        try:
            source = connect(source_config)
            logger.info("Connected to source")
            retries = 0
            last_data_time = time.monotonic()

            while True:
                data = source.read(1024)
                if data:
                    last_data_time = time.monotonic()
                    for event in parser.feed(data):
                        callback(event)
                elif reconnect_timeout > 0 and (time.monotonic() - last_data_time) > reconnect_timeout:
                    logger.warning("No data for %ds, reconnecting", reconnect_timeout)
                    break

        except Exception as e:
            logger.error("Connection error: %s", e)

        finally:
            try:
                source.close()
            except Exception:
                pass

        retries += 1
        if reconnect_retries > 0 and retries > reconnect_retries:
            logger.error("Max retries (%d) exceeded", reconnect_retries)
            return

        logger.info("Reconnecting in %ds (attempt %d/%s)...",
                     reconnect_delay, retries,
                     str(reconnect_retries) if reconnect_retries else '∞')
        time.sleep(reconnect_delay)
```

### 9.2 Update `pytap/__init__.py`

```python
"""pytap: Simplified TapTap protocol parser for Tigo TAP solar monitoring."""
__version__ = '0.1.0'

from .api import create_parser, parse_bytes, observe, connect
from .core.parser import Parser
from .core.events import Event, PowerReportEvent, InfrastructureEvent, TopologyEvent, StringEvent
from .core.types import (
    GatewayID, NodeID, NodeAddress, LongAddress, SlotCounter,
    PacketType, FrameType, Frame, PowerReport, RSSI,
)

__all__ = [
    'create_parser', 'parse_bytes', 'observe', 'connect',
    'Parser', 'Event', 'PowerReportEvent', 'InfrastructureEvent',
    'TopologyEvent', 'StringEvent',
    'GatewayID', 'NodeID', 'NodeAddress', 'LongAddress', 'SlotCounter',
    'PacketType', 'FrameType', 'Frame', 'PowerReport', 'RSSI',
]
```

### 9.3 Tests — `tests/test_api.py`

- `test_create_parser`: returns a `Parser` instance
- `test_parse_bytes_empty`: `parse_bytes(b'')` → `[]`
- `test_parse_bytes_with_data`: feed enumeration sequence → returns events
- `test_connect_tcp`: mock/patch socket → returns `TcpSource`
- `test_connect_serial`: skip if pyserial missing, verify constructor
- `test_connect_invalid`: `connect({})` → raises `ValueError`

**Acceptance:** All API functions callable, return correct types.

---

## 10. Phase 9 — CLI

**File:** `pytap/cli/main.py`  
**Depends on:** `pytap.api`

### 10.1 Implementation

```python
"""pytap command-line interface."""
import json
import sys
import logging

try:
    import click
except ImportError:
    print("CLI requires 'click' package. Install with: pip install pytap[cli]",
          file=sys.stderr)
    sys.exit(1)

import pytap


@click.group()
@click.version_option(pytap.__version__)
def main():
    """pytap: Tigo TAP protocol parser for solar monitoring."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


@main.command()
@click.option('--tcp', help='TCP host (e.g. 192.168.1.100)')
@click.option('--port', default=502, type=int, help='TCP port')
@click.option('--serial', help='Serial port (e.g. /dev/ttyUSB0, COM3)')
@click.option('--state-file', default=None, type=click.Path(), help='Persistent state file')
@click.option('--reconnect-timeout', default=60, type=int, help='Silence timeout (seconds)')
@click.option('--reconnect-retries', default=0, type=int, help='Max retries (0=infinite)')
@click.option('--reconnect-delay', default=5, type=int, help='Delay between retries (seconds)')
def observe(tcp, port, serial, state_file, reconnect_timeout, reconnect_retries, reconnect_delay):
    """Stream parsed events as JSON (one object per line)."""
    if not tcp and not serial:
        click.echo("Error: --tcp or --serial is required", err=True)
        sys.exit(1)

    source_config = {}
    if tcp:
        source_config = {'tcp': tcp, 'port': port}
    elif serial:
        source_config = {'serial': serial}

    def print_event(event):
        click.echo(json.dumps(event.to_dict()))

    pytap.observe(
        source_config=source_config,
        callback=print_event,
        state_file=state_file,
        reconnect_timeout=reconnect_timeout,
        reconnect_retries=reconnect_retries,
        reconnect_delay=reconnect_delay,
    )


@main.command('peek-bytes')
@click.option('--tcp', help='TCP host')
@click.option('--port', default=502, type=int)
@click.option('--serial', help='Serial port')
def peek_bytes(tcp, port, serial):
    """Show raw hex bytes from the bus."""
    source_config = {'tcp': tcp, 'port': port} if tcp else {'serial': serial}
    source = pytap.connect(source_config)
    try:
        while True:
            data = source.read(1024)
            if data:
                click.echo(' '.join(f'{b:02X}' for b in data), nl=False)
    except KeyboardInterrupt:
        pass
    finally:
        source.close()


@main.command('list-serial-ports')
def list_serial_ports():
    """List available serial ports."""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            click.echo("No serial ports detected.")
        for p in sorted(ports, key=lambda x: x.device):
            click.echo(f"  --serial {p.device}")
            if p.description and p.description != 'n/a':
                click.echo(f"    {p.description}")
    except ImportError:
        click.echo("pyserial not installed. Install with: pip install pytap[serial]",
                    err=True)
```

### 10.2 Tests

- `test_cli_version`: `pytap --version` outputs version string
- `test_cli_observe_requires_source`: `pytap observe` without --tcp/--serial → error

**Acceptance:** CLI installs as `pytap` entry point, runs without errors.

---

## 11. Phase 10 — Integration Tests & Polish

### 11.1 End-to-End Test

```python
def test_enumeration_sequence_end_to_end():
    """Feed the full ENUMERATION_SEQUENCE and verify infrastructure discovery."""
    events = pytap.parse_bytes(ENUMERATION_SEQUENCE)
    infra_events = [e for e in events if e.event_type == 'infrastructure']
    assert len(infra_events) >= 1
    last_infra = infra_events[-1]
    # Verify gateway with address 04:C0:5B:30:00:02:BE:16 was discovered
    found = any('04:C0:5B:30:00:02:BE:16' in str(gw.get('address', ''))
                for gw in last_infra.gateways.values())
    assert found, f"Expected gateway not found in {last_infra.gateways}"
```

### 11.2 Cross-Validation

Where possible, feed the same test data into both `python/taptap` and `pytap` and verify the same events are produced (same gateway IDs, same addresses, same power report values).

### 11.3 Polish Checklist

- [ ] All public functions and classes have docstrings
- [ ] All public functions have type hints
- [ ] `logging` used throughout (not `print`)
- [ ] No circular imports
- [ ] `__all__` defined in all `__init__.py`
- [ ] `py.typed` marker file for type checker support
- [ ] README.md in `pytap/` with usage examples

### 11.4 Edge Case Tests

- [ ] Feed bytes one at a time → same results as bulk feed
- [ ] Feed data split across two `feed()` calls mid-frame → correct parse
- [ ] CRC error → frame skipped, no crash, counter incremented
- [ ] Giant frame (>256 bytes) → skipped, counter incremented, parser recovers
- [ ] Truncated packet header in RECEIVE_RESPONSE → gracefully skipped
- [ ] Epoch wraparound in SlotCounter → slots_since() returns correct positive value
- [ ] Below-zero temperature → sign-extended correctly
- [ ] Empty node table page → triggers table completion
- [ ] Missing SlotClock for gateway → power report discarded with log warning
- [ ] Invalid escape sequence → noise counter incremented, parser recovers
- [ ] Concurrent frames from multiple gateways → independent state per gateway

---

## Appendix A — Wire Format Quick Reference

### Gateway Link Layer Frame

```
[preamble] [escaped body] [terminator]

Preamble:   0xFF (gateway) or 0x00 0xFF 0xFF (controller), then 0x7E 0x07
Body:       address(2, big-endian) + frame_type(2, big-endian) + payload(variable)
CRC:        2 bytes, LITTLE-endian, appended to body BEFORE escaping
Terminator: 0x7E 0x08

Byte escaping (within body+CRC, EXCLUDING preamble/terminator):
  0x7E → 0x7E 0x00
  0x24 → 0x7E 0x01
  0x23 → 0x7E 0x02
  0x25 → 0x7E 0x03
  0xA4 → 0x7E 0x04
  0xA3 → 0x7E 0x05
  0xA5 → 0x7E 0x06
```

### Address (2 bytes, big-endian)

```
Bit 15:    direction (0=To/controller→gateway, 1=From/gateway→controller)
Bits 14-0: GatewayID (0-32767)
```

### ReceiveResponse Variable Header

```
Bytes 0-1: status_type (big-endian u16, bitmask)
  Bits 5-7 MUST be set (mask 0x00E0)
  Bit 0 clear → +1 byte rx_buffers_used
  Bit 1 clear → +1 byte tx_buffers_free
  Bit 2 clear → +2 bytes unknown_a
  Bit 3 clear → +2 bytes unknown_b
  Bit 4 clear → +2 bytes packet_number (full)
  Bit 4 set   → +1 byte packet_number_lo (expand with old high byte)
Then: +2 bytes slot_counter (big-endian)
Then: remaining bytes = received packets
```

### ReceivedPacket (within RECEIVE_RESPONSE trailing data)

```
Header (7 bytes):
  [0]   packet_type (u8)
  [1-2] node_address (u16 big-endian)
  [3-4] short_address (u16 big-endian)
  [5]   dsn (u8)
  [6]   data_length (u8)
Data:
  [7..7+data_length] packet payload
```

### PowerReport (13 bytes)

```
[0-2]  U12Pair: voltage_in (÷20 = V), voltage_out (÷10 = V)
[3]    dc_dc_duty_cycle (÷255)
[4-6]  U12Pair: current (÷200 = A), temperature (÷10 = °C, sign-extend if bit 11 set)
[7-9]  unknown
[10-11] SlotCounter (big-endian u16)
[12]   RSSI (u8)
```

### Node Table Response

```
[0]    entries_count (u8)
[1..]  entries_count × 10-byte entries:
         [0-1] NodeAddress (u16 big-endian)
         [2-9] LongAddress (8 bytes)
```

---

## Appendix B — Test Data

### ENUMERATION_SEQUENCE

This byte sequence (from `src/test_data.rs`) contains a complete gateway enumeration exchange including:
- PING request/response
- ENUMERATION_START request/response (×5)
- ENUMERATION request/response
- ASSIGN_GATEWAY_ID request/response
- IDENTIFY request/response
- VERSION request/response (contains `"Mgate Version G8.59\r..."`)
- ENUMERATION_END request/response
- Final PING request/response

Gateway address: `04:C0:5B:30:00:02:BE:16`

```python
ENUMERATION_SEQUENCE = bytes([
    0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x0B, 0x00, 0x01, 0xFE, 0x83, 0x7E, 0x08, 0xFF, 0x7E,
    0x07, 0x92, 0x01, 0x0B, 0x01, 0x01, 0x73, 0x10, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x00,
    0x00, 0x00, 0x14, 0x37, 0x7E, 0x01, 0x92, 0x66, 0x12, 0x35, 0x06, 0x1A, 0x7E, 0x08, 0xFF, 0x7E,
    0x07, 0x80, 0x00, 0x00, 0x15, 0x17, 0xE0, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x00, 0x00,
    0x00, 0x14, 0x37, 0x7E, 0x01, 0x92, 0x66, 0x12, 0x35, 0x06, 0x1A, 0x7E, 0x08, 0xFF, 0x7E, 0x07,
    0x80, 0x00, 0x00, 0x15, 0x17, 0xE0, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x00, 0x00, 0x00,
    0x14, 0x37, 0x7E, 0x01, 0x92, 0x66, 0x12, 0x35, 0x06, 0x1A, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x80,
    0x00, 0x00, 0x15, 0x17, 0xE0, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x00, 0x00, 0x00, 0x14,
    0x37, 0x7E, 0x01, 0x92, 0x66, 0x12, 0x35, 0x06, 0x1A, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x80, 0x00,
    0x00, 0x15, 0x17, 0xE0, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x00, 0x00, 0x00, 0x14, 0x37,
    0x7E, 0x01, 0x92, 0x66, 0x12, 0x35, 0x06, 0x1A, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x80, 0x00, 0x00,
    0x15, 0x17, 0xE0, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x35, 0x00, 0x38, 0x5A, 0x72,
    0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x35, 0x00, 0x39, 0x04, 0xC0, 0x5B, 0x30, 0x00, 0x02, 0xBE,
    0x16, 0x12, 0x35, 0xA7, 0x83, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x35, 0x00, 0x3C,
    0x37, 0x7E, 0x01, 0x92, 0x66, 0x04, 0xC0, 0x5B, 0x30, 0x00, 0x02, 0xBE, 0x16, 0x12, 0x01, 0x58,
    0x0B, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x35, 0x00, 0x3D, 0x99, 0x08, 0x7E, 0x08, 0x00, 0xFF,
    0xFF, 0x7E, 0x07, 0x12, 0x35, 0x00, 0x38, 0x5A, 0x72, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07,
    0x12, 0x35, 0x00, 0x38, 0x5A, 0x72, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x35, 0x00,
    0x38, 0x5A, 0x72, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x35, 0x00, 0x38, 0x5A, 0x72,
    0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x35, 0x00, 0x38, 0x5A, 0x72, 0x7E, 0x08, 0x00,
    0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x00, 0x3A, 0x87, 0xB4, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92,
    0x01, 0x00, 0x3B, 0x04, 0xC0, 0x5B, 0x30, 0x00, 0x02, 0xBE, 0x16, 0x12, 0x01, 0xE6, 0xA6, 0x7E,
    0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x00, 0x3C, 0x37, 0x7E, 0x01, 0x92, 0x66, 0x04,
    0xC0, 0x5B, 0x30, 0x00, 0x02, 0xBE, 0x16, 0x12, 0x02, 0xDC, 0x60, 0x7E, 0x08, 0xFF, 0x7E, 0x07,
    0x92, 0x01, 0x00, 0x3D, 0x56, 0xED, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x02, 0x00,
    0x3A, 0xE3, 0x5B, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x02, 0x00, 0x3B, 0x04, 0xC0, 0x5B, 0x30,
    0x00, 0x02, 0xBE, 0x16, 0x12, 0x02, 0x8A, 0x9A, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x00,
    0x00, 0x00, 0x10, 0x37, 0x7E, 0x01, 0x92, 0x66, 0xC3, 0x27, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x80,
    0x00, 0x00, 0x11, 0x33, 0xA6, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x00, 0x3A,
    0x87, 0xB4, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x00, 0x3B, 0x04, 0xC0, 0x5B, 0x30, 0x00,
    0x02, 0xBE, 0x16, 0x12, 0x01, 0xE6, 0xA6, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01,
    0x00, 0x0A, 0x04, 0x85, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x00, 0x0B, 0x4D, 0x67, 0x61,
    0x74, 0x65, 0x20, 0x56, 0x65, 0x72, 0x73, 0x69, 0x6F, 0x6E, 0x20, 0x47, 0x38, 0x2E, 0x35, 0x39,
    0x0D, 0x4A, 0x75, 0x6C, 0x20, 0x20, 0x36, 0x20, 0x32, 0x30, 0x32, 0x30, 0x0D, 0x31, 0x36, 0x3A,
    0x35, 0x31, 0x3A, 0x35, 0x31, 0x0D, 0x47, 0x57, 0x2D, 0x48, 0x31, 0x35, 0x38, 0x2E, 0x34, 0x2E,
    0x33, 0x53, 0x30, 0x2E, 0x31, 0x32, 0x0D, 0x8A, 0xE2, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07,
    0x12, 0x01, 0x0E, 0x02, 0x5C, 0x93, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x00, 0x06, 0x06,
    0x62, 0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x0B, 0x00, 0x01, 0xFE, 0x83, 0x7E,
    0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x0B, 0x01, 0x01, 0x73, 0x10, 0x7E, 0x08,
])
```

**Expected parse results from this sequence:**
- **Total valid frames:** ~30+
- **Gateway IDs seen:** 0 (enumeration broadcast), 0x35 (53, temporary), 1, 2
- **Gateway address:** `04:C0:5B:30:00:02:BE:16` (appears in ENUMERATION_RESPONSE, IDENTIFY_RESPONSE, ASSIGN_GATEWAY_ID_REQUEST)
- **Version string:** `"Mgate Version G8.59\rJul  6 2020\r16:51:51\rGW-H158.4.3S0.12\r"`
- **Frame types seen:** PING_REQUEST, PING_RESPONSE, ENUMERATION_START_REQUEST/RESPONSE, ENUMERATION_REQUEST/RESPONSE, ASSIGN_GATEWAY_ID_REQUEST/RESPONSE, IDENTIFY_REQUEST/RESPONSE, VERSION_REQUEST/RESPONSE, ENUMERATION_END_REQUEST/RESPONSE

---

## Execution Order Summary

| Phase | Files | Depends On | Estimated LOC | Priority |
|-------|-------|-----------|--------------|----------|
| 1 | `crc.py`, `test_crc.py` | — | ~50 | Must |
| 2 | `barcode.py`, `test_barcode.py` | — | ~100 | Must |
| 3 | `types.py`, `test_types.py` | — | ~250 | Must |
| 4 | `events.py` | types | ~100 | Must |
| 5 | `state.py` | types | ~150 | Must |
| 6 | `parser.py`, `test_parser.py` | crc, types, events, state, barcode | ~500 | Must |
| 7 | `source.py` | — | ~80 | Must |
| 8 | `api.py`, `__init__.py`, `test_api.py` | parser, source | ~100 | Must |
| 9 | `cli/main.py` | api | ~80 | Should |
| 10 | Integration tests, polish | all | ~100 | Should |

**Total estimated:** ~1500 lines of code + ~500 lines of tests.

Each phase should be completed and tested before moving to the next. Phases 1-3 can be developed in parallel since they have no interdependencies.
