# TapTap Data Structures Reference

## Overview

This document provides a comprehensive reference for all data structures used in the TapTap implementation. Each structure includes field definitions, sizes, serialization formats, and purposes.

## Table of Contents

1. [Device Identification](#device-identification)
2. [Gateway Network Structures](#gateway-network-structures)
3. [PV Network Structures](#pv-network-structures)
4. [Time Synchronization](#time-synchronization)
5. [Measurement Data](#measurement-data)
6. [Observer Events](#observer-events)
7. [Persistent State](#persistent-state)

---

## Device Identification

### Barcode

**Purpose**: Human-readable device identifier with CRC checksum

**Source**: `src/barcode.rs`

**Format**: `X-NNNNNNNC` (e.g., `4-9A57A2L`)

**Structure**:
```rust
pub struct Barcode(pub pv::LongAddress);  // Wraps 8-byte address
```

**Encoding Algorithm**:
1. Extract leading nibble from first byte
2. Mask address to `0x04C05B0xxxxxxxx` range
3. Convert remaining 7 nibbles to base-32 (GHJKLMNPRSTVWXYZ)
4. Calculate 4-bit CRC and append as base-32 character

**CRC Table**:
```rust
const TABLE: [u8; 16] = [0, 3, 6, 5, 12, 15, 10, 9, 11, 8, 13, 14, 7, 4, 1, 2];
```

**Example**:
- Address: `04:C0:5B:40:9A:57:A2:3E`
- Barcode: `4-9A57A2L`

---

## Gateway Network Structures

### GatewayID

**Purpose**: 15-bit identifier for TAP gateway devices

**Source**: `src/gateway/link/address.rs`

**Structure**:
```rust
pub struct GatewayID(u16);  // 15-bit value (0x0000-0x7FFF)
```

**Display Format**: Decimal (e.g., `4609`)

**Constraints**: Bit 15 must be 0

### Address

**Purpose**: Link-layer addressing with direction bit

**Source**: `src/gateway/link/address.rs`

**Size**: 2 bytes

**Structure**:
```rust
pub enum Address {
    To(GatewayID),    // Bit 15 = 0
    From(GatewayID),  // Bit 15 = 1
}
```

**Serialization**: Big-endian u16
- `To(gateway_id)`: `0x0000 | gateway_id`
- `From(gateway_id)`: `0x8000 | gateway_id`

**Example**:
- `To(4609)` → `0x1201` → `[0x12, 0x01]`
- `From(4609)` → `0x9201` → `[0x92, 0x01]`

### Frame

**Purpose**: Gateway link layer frame structure

**Source**: `src/gateway/link/receive.rs`

**Structure**:
```rust
pub struct Frame {
    pub address: Address,     // 2 bytes
    pub frame_type: Type,     // 2 bytes (big-endian)
    pub payload: Vec<u8>,     // Variable length
}
```

**Wire Format**:
```
[Preamble] [Address] [Type] [Payload] [CRC] [Terminator]
3-5 bytes   2 bytes  2 bytes  N bytes  2 bytes  2 bytes
```

**Preamble**:
- To: `0x00 0xFF 0xFF 0x7E 0x07` (5 bytes)
- From: `0xFF 0x7E 0x07` (3 bytes)

**Terminator**: `0x7E 0x08`

**CRC**: CRC-CCITT (polynomial 0x1021) over address + type + payload
- Serialized as little-endian u16

### Frame Types

**Source**: `src/gateway/transport/mod.rs`

| Type | Value | Direction | Purpose |
|------|-------|-----------|---------|
| COMMAND_REQUEST | 0x0001 | Controller→Gateway | Send command to PV network |
| COMMAND_RESPONSE | 0x0002 | Gateway→Controller | Command acknowledgment |
| RECEIVE_REQUEST | 0x0003 | Gateway→Controller | Poll for received packets |
| RECEIVE_RESPONSE | 0x0004 | Controller→Gateway | Batch of PV packets |
| ENUMERATION_START_REQUEST | 0x0005 | Controller→Gateway | Begin enumeration |
| ENUMERATION_START_RESPONSE | 0x0006 | Gateway→Controller | Enumeration ack |
| IDENTIFY_REQUEST | 0x0007 | Controller→Gateway | Request identity |
| IDENTIFY_RESPONSE | 0x0008 | Gateway→Controller | Contains LongAddress |
| VERSION_REQUEST | 0x000B | Controller→Gateway | Request firmware version |
| VERSION_RESPONSE | 0x000C | Gateway→Controller | Version string |

---

## PV Network Structures

### NodeID

**Purpose**: PV network node identifier

**Source**: `src/pv/network.rs`

**Size**: 2 bytes

**Structure**:
```rust
pub struct NodeID(NonZeroU16);  // 1-65535
```

**Special Values**:
- `GATEWAY`: `0x0001`
- `MAX`: `0xFFFF`

**Display Format**: Decimal (e.g., `116`)

**Serialization**: Big-endian u16

### NodeAddress

**Purpose**: Node identifier or broadcast address

**Source**: `src/pv/network.rs`

**Size**: 2 bytes

**Structure**:
```rust
pub struct NodeAddress(u16);  // 0-65535
```

**Special Values**:
- `ZERO`: `0x0000` (broadcast)
- `GATEWAY`: `0x0001`

**Conversion**:
- `NodeAddress(0)` → `None`
- `NodeAddress(n)` → `Some(NodeID(n))` for n > 0

### ShortAddress

**Purpose**: 802.15.4 short address

**Source**: `src/pv/link.rs`

**Size**: 2 bytes

**Structure**:
```rust
pub struct ShortAddress(pub u16);
```

**Display Format**: Hexadecimal with 0x prefix (e.g., `0x1234`)

**Serialization**: Big-endian u16

### LongAddress

**Purpose**: 802.15.4 long address (globally unique MAC)

**Source**: `src/pv/link.rs`

**Size**: 8 bytes

**Structure**:
```rust
pub struct LongAddress(pub [u8; 8]);
```

**Display Format**: Colon-separated hex (e.g., `04:C0:5B:40:9A:57:A2:3E`)

**Methods**:
- `barcode(&self) -> Barcode`: Convert to human-readable barcode

**Serialization**: JSON as hex string, binary as raw bytes

### DSN (Data Sequence Number)

**Purpose**: Packet sequence tracking

**Source**: `src/pv/link.rs`

**Size**: 1 byte

**Structure**:
```rust
pub struct DSN(pub u8);
```

**Operations**:
- Wrapping addition: `DSN(a) + b`

### RSSI (Received Signal Strength Indicator)

**Purpose**: Wireless signal strength measurement

**Source**: `src/pv/physical.rs`

**Size**: 1 byte

**Structure**:
```rust
pub struct RSSI(pub u8);
```

**Range**: 0-255 (higher = stronger signal)

---

## Time Synchronization

### SlotCounter

**Purpose**: Network-wide time synchronization

**Source**: `src/pv/link/slot_counter.rs`

**Size**: 2 bytes

**Structure**:
```rust
pub struct SlotCounter(u16);  // Big-endian
```

**Bit Layout**:
- Bits 15-14: Epoch (2 bits, 4 values)
- Bits 13-0: Slot number (14 bits, 0-11999)

**Epoch Values**:
```
Epoch0 (0x0xxx) → 0
Epoch4 (0x4xxx) → 1
Epoch8 (0x8xxx) → 2
EpochC (0xCxxx) → 3
```

**Timing**:
- Slot duration: ~4.29ms (5ms ± 15%)
- Epoch duration: ~51.5 seconds (12000 slots)
- Full cycle: ~206 seconds (4 epochs)

**Methods**:
```rust
pub fn new(epoch: SlotEpoch, slot_number: SlotNumber) -> Self
pub fn epoch(&self) -> SlotEpoch
pub fn slot_number(&self) -> Result<SlotNumber>
pub fn slots_since(&self, past: SlotCounter) -> Result<u16>
```

**Example**:
```
SlotCounter(0x4567) = Epoch4, slot 1383
  Bits: 01 00 0101 0110 0111
        ││ └──────┬──────┘
        ││     Slot: 1383
        │└ Epoch: 4
        └─ Reserved
```

### SlotEpoch

**Purpose**: Epoch identifier for time wraparound handling

**Source**: `src/pv/link/slot_counter.rs`

**Size**: 2 bits (stored in u16 high bits)

**Structure**:
```rust
pub enum SlotEpoch {
    Epoch0 = 0,  // 0x0xxx
    Epoch4 = 1,  // 0x4xxx
    Epoch8 = 2,  // 0x8xxx
    EpochC = 3,  // 0xCxxx
}
```

**Operations**:
- Wrapping addition: `epoch + 1` wraps at 4
- Successor: Epoch0→4→8→C→0

### SlotNumber

**Purpose**: Validated slot number within epoch

**Source**: `src/pv/link/slot_counter.rs`

**Size**: 14 bits

**Structure**:
```rust
pub struct SlotNumber(u16);  // 0-11999 (0x2EDF)
```

**Validation**: Must be ≤ 11999, returns error otherwise

---

## Measurement Data

### U12Pair

**Purpose**: Pack two 12-bit values into 3 bytes

**Source**: `src/pv/application/mod.rs`

**Size**: 3 bytes

**Structure**:
```rust
pub struct U12Pair([u8; 3]);
```

**Bit Layout**:
```
Byte 0: AAAA AAAA
Byte 1: AAAA BBBB
Byte 2: BBBB BBBB

First value (A):  bits [23:12] = bytes[0..2] >> 4
Second value (B): bits [11:0]  = bytes[1..3] & 0x0FFF
```

**Methods**:
```rust
pub fn first(&self) -> u16   // Upper 12 bits
pub fn second(&self) -> u16  // Lower 12 bits
```

**Example**:
```
Bytes: [0x12, 0x34, 0x56]
First:  0x123 (291)
Second: 0x456 (1110)
```

### PowerReport

**Purpose**: Real-time solar optimizer measurements

**Source**: `src/pv/application/mod.rs`

**Size**: 13 bytes

**Structure**:
```rust
#[repr(C)]
pub struct PowerReport {
    pub voltage_in_and_voltage_out: U12Pair,  // [0..3]
    pub dc_dc_duty_cycle: u8,                 // [3]
    pub current_and_temperature: U12Pair,     // [4..7]
    pub unknown: [u8; 3],                     // [7..10]
    pub slot_counter: SlotCounter,            // [10..12] BE
    pub rssi: RSSI,                           // [12]
}
```

**Field Conversions**:
```rust
voltage_in  = first(voltage_in_and_voltage_out) / 20.0   // Volts
voltage_out = second(voltage_in_and_voltage_out) / 10.0  // Volts
current     = first(current_and_temperature) / 200.0     // Amperes
temperature = temperature_from_u12(second(current_and_temperature))
duty_cycle  = dc_dc_duty_cycle / 255.0                   // Ratio
```

**Temperature Decoding**:
```rust
fn temperature_from_u12(raw: u16) -> f64 {
    let signed = if raw & 0x800 != 0 {
        (raw | 0xF000) as i16  // Sign-extend
    } else {
        raw as i16
    };
    signed as f64 / 10.0  // Celsius
}
```

### PowerReport15

**Purpose**: Extended power report with padding

**Source**: `src/pv/application/mod.rs`

**Size**: 15 bytes

**Structure**:
```rust
#[repr(C)]
pub struct PowerReport15 {
    pub power_report: PowerReport,  // 13 bytes
    pub unknown: [u8; 2],           // 2 bytes padding
}
```

### ReceivedPacketHeader

**Purpose**: Header for PV network packets

**Source**: `src/pv/network.rs`

**Size**: 5 bytes

**Structure**:
```rust
#[repr(C)]
pub struct ReceivedPacketHeader {
    pub packet_type: PacketType,      // [0]
    pub node_address: NodeAddress,    // [1..3] BE
    pub short_address: ShortAddress,  // [3..5] BE
    pub dsn: DSN,                     // [5]
    pub data_length: u8,              // [6]
}
```

**Total Packet Size**: 5 + data_length bytes

### PacketType

**Purpose**: PV packet type identifier

**Source**: `src/pv/application/mod.rs`

**Size**: 1 byte

**Common Values**:
```rust
STRING_REQUEST                      = 0x06
STRING_RESPONSE                     = 0x07
TOPOLOGY_REPORT                     = 0x09
GATEWAY_RADIO_CONFIGURATION_REQUEST = 0x0D
GATEWAY_RADIO_CONFIGURATION_RESPONSE= 0x0E
PV_CONFIGURATION_REQUEST            = 0x13
PV_CONFIGURATION_RESPONSE           = 0x18
BROADCAST                           = 0x22
BROADCAST_ACK                       = 0x23
NODE_TABLE_REQUEST                  = 0x26
NODE_TABLE_RESPONSE                 = 0x27
LONG_NETWORK_STATUS_REQUEST         = 0x2D
NETWORK_STATUS_REQUEST              = 0x2E
NETWORK_STATUS_RESPONSE             = 0x2F
POWER_REPORT                        = 0x31
```

### NodeTableRequest

**Purpose**: Request node registry starting at offset

**Source**: `src/pv/application/mod.rs`

**Size**: 2 bytes

**Structure**:
```rust
#[repr(C)]
pub struct NodeTableRequest {
    pub start_at: NodeAddress,  // BE u16
}
```

### NodeTableResponse

**Purpose**: Device registry response

**Source**: `src/pv/application/mod.rs`

**Size**: 4 + (10 × entries_count) bytes

**Structure**:
```rust
#[repr(C)]
pub struct NodeTableResponse {
    pub start_at: NodeAddress,      // [0..2] BE
    pub entries_count: u16,         // [2..4] BE
    pub entries: [NodeTableResponseEntry],  // DST
}
```

### NodeTableResponseEntry

**Purpose**: Single node registration entry

**Source**: `src/pv/application/mod.rs`

**Size**: 10 bytes

**Structure**:
```rust
#[repr(C)]
pub struct NodeTableResponseEntry {
    pub long_address: LongAddress,  // [0..8]
    pub node_id: NodeAddress,       // [8..10] BE
}
```

### TopologyReport

**Purpose**: Network mesh structure information

**Source**: `src/pv/application/mod.rs`

**Size**: 16 bytes

**Structure**:
```rust
#[repr(C)]
pub struct TopologyReport {
    pub short_address: ShortAddress,  // [0..2] BE
    pub pv_node_id: NodeAddress,      // [2..4] BE
    pub next_hop: NodeAddress,        // [4..6] BE
    pub unknown_1: [u8; 2],           // [6..8]
    pub long_address: LongAddress,    // [8..16]
    pub rssi: RSSI,                   // [16]
    pub unknown_2: [u8; 5],           // [17..22]
}
```

---

## Observer Events

### Event

**Purpose**: Top-level event envelope for JSON output

**Source**: `src/observer/event.rs`

**Structure**:
```rust
pub enum Event {
    PowerReport(PowerReportEvent),
}
```

### PowerReportEvent

**Purpose**: Processed power measurement with metadata

**Source**: `src/observer/event.rs`

**Structure**:
```rust
pub struct PowerReportEvent {
    pub event_type: "power_report",
    pub gateway: GatewayID,
    pub node: NodeID,
    pub timestamp: DateTime<Local>,
    pub voltage_in: f64,      // Volts
    pub voltage_out: f64,     // Volts
    pub current: f64,         // Amperes
    pub dc_dc_duty_cycle: f64,// 0.0-1.0
    pub temperature: f64,     // Celsius
    pub rssi: RSSI,           // 0-255
}
```

**JSON Example**:
```json
{
  "event_type": "power_report",
  "gateway": 4609,
  "node": 116,
  "timestamp": "2024-08-24T09:16:41.686961-05:00",
  "voltage_in": 30.6,
  "voltage_out": 30.2,
  "current": 6.94,
  "dc_dc_duty_cycle": 1.0,
  "temperature": 26.8,
  "rssi": 132
}
```

---

## Persistent State

### PersistentState

**Purpose**: Network topology storage for restart survival

**Source**: `src/observer/persistent_state.rs`

**Structure**:
```rust
pub struct PersistentState {
    pub gateway_node_tables: BTreeMap<GatewayID, NodeTable>,
    pub gateway_identities: BTreeMap<GatewayID, LongAddress>,
    pub gateway_versions: BTreeMap<GatewayID, String>,
}
```

**File Format**: JSON

**Storage Trigger**: Immediate write on any update

### PersistentStateEvent

**Purpose**: Infrastructure report event

**Source**: `src/observer/persistent_state.rs`

**Structure**:
```rust
pub struct PersistentStateEvent {
    pub event_type: "infrastructure_report",
    pub gateways: BTreeMap<GatewayID, PersistentStateEventGateway>,
    pub nodes: BTreeMap<GatewayID, BTreeMap<NodeID, PersistentStateEventNode>>,
}

pub struct PersistentStateEventGateway {
    pub address: String,  // XX:XX:XX:XX:XX:XX:XX:XX format
    pub version: String,
}

pub struct PersistentStateEventNode {
    pub address: String,  // XX:XX:XX:XX:XX:XX:XX:XX format
    pub barcode: String,  // X-NNNNNNNC format
}
```

**JSON Example**:
```json
{
  "event_type": "infrastructure_report",
  "gateways": {
    "4609": {
      "address": "04:C0:5B:30:12:34:56:78",
      "version": "Mgate Version 1.2.3"
    }
  },
  "nodes": {
    "4609": {
      "2": {
        "address": "04:C0:5B:40:9A:57:A2:3E",
        "barcode": "4-9A57A2L"
      }
    }
  }
}
```

---

## Serialization Summary

| Structure | Size | Byte Order | Serialization |
|-----------|------|------------|---------------|
| Barcode | 8 | N/A | Custom base-32 + CRC |
| GatewayID | 2 | BE | u16 |
| Address | 2 | BE | u16 with direction bit |
| NodeID | 2 | BE | NonZeroU16 |
| NodeAddress | 2 | BE | u16 |
| ShortAddress | 2 | BE | u16 |
| LongAddress | 8 | N/A | [u8; 8] |
| DSN | 1 | N/A | u8 |
| RSSI | 1 | N/A | u8 |
| SlotCounter | 2 | BE | u16 (epoch + slot) |
| U12Pair | 3 | N/A | Packed bits |
| PowerReport | 13 | Mixed | C-repr struct |
| ReceivedPacketHeader | 5 | BE | C-repr struct |
| NodeTableResponseEntry | 10 | BE | C-repr struct |
| TopologyReport | 16 | BE | C-repr struct |

**Notes**:
- BE = Big-endian
- All `#[repr(C)]` structs use zerocopy traits for safe serialization
- JSON uses serde with custom Display/FromStr for special types
