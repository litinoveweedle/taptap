# Gateway Protocol Stack Implementation

## Overview

This document details the implementation of the gateway network stack, which handles communication over RS-485 between the controller and TAP gateways.

## Architecture

```
┌──────────────────────────────────────┐
│      Gateway Transport Layer         │
│  - Command/Response handling         │
│  - Receive packet batching           │
│  - Enumeration sequences             │
│  - Sequence number tracking          │
├──────────────────────────────────────┤
│       Gateway Link Layer             │
│  - Frame assembly/disassembly        │
│  - CRC validation                    │
│  - Byte escaping/unescaping          │
│  - Preamble detection                │
├──────────────────────────────────────┤
│      Gateway Physical Layer          │
│  - Serial port (RS-485)              │
│  - TCP (tcpserial_hook)              │
│  - Termios (low-level POSIX)         │
└──────────────────────────────────────┘
```

---

## Physical Layer

**Module**: `src/gateway/physical/`

### Purpose

Abstraction over different I/O mechanisms for RS-485 communication.

### Implementations

#### 1. Serial Port (`serialport.rs`)

**Dependencies**: `serialport` crate

**Configuration**:
```rust
pub struct SerialSourceConfig {
    pub port: String,           // e.g., "/dev/ttyUSB0"
    pub baud_rate: u32,         // Default: 9600
}
```

**Characteristics**:
- Hardware RS-485 adapter (USB or HAT)
- Buffered reads
- Platform-agnostic (uses serialport crate)

#### 2. TCP (`tcp.rs`)

**Dependencies**: `socket2` crate

**Configuration**:
```rust
pub struct TcpConnectionConfig {
    pub address: String,        // IP or hostname
    pub port: u16,              // Default: 502 (Modbus)
    pub reconnect_timeout: Duration,
    pub reconnect_retry: u32,   // 0 = infinite
    pub reconnect_delay: Duration,
}
```

**Features**:
- TCP keepalive (idle, interval, count)
- Automatic reconnection on timeout
- Suitable for tcpserial_hook

**TCP Keepalive Settings**:
```rust
socket.set_tcp_keepalive(&TcpKeepalive::new()
    .with_time(Duration::from_secs(10))
    .with_interval(Duration::from_secs(5))
    .with_retries(3))
```

#### 3. Termios (`termios.rs`)

**Dependencies**: `libc` (POSIX)

**Purpose**: Low-level serial port control

**Platform**: Unix/Linux only

**Configuration**:
```c
struct termios {
    c_iflag: IGNBRK | IGNPAR,  // Ignore breaks and parity errors
    c_oflag: 0,                // No output processing
    c_cflag: CS8 | CREAD | CLOCAL,  // 8-bit, enable receiver, local line
    c_lflag: 0,                // No line processing
    c_cc[VMIN]: 0,             // Non-blocking reads
    c_cc[VTIME]: 0,
}
```

**Baud Rate**: B9600 (via `cfsetspeed`)

#### 4. Trace Mesh DCD (`trace_meshdcd/`)

**Purpose**: Debug trace file reader

**Format**: Custom binary format with metadata

**Use Case**: Replay captured RS-485 traffic for testing

---

## Link Layer

**Module**: `src/gateway/link/`

### Purpose

Frame assembly, CRC validation, and byte-level protocol handling.

### Frame Structure

```
┌─────────────┬─────────┬─────┬─────────┬─────┬────────────┐
│  Preamble   │ Address │ Type│ Payload │ CRC │ Terminator │
│  3-5 bytes  │ 2 bytes │2 B  │ N bytes │ 2 B │  2 bytes   │
└─────────────┴─────────┴─────┴─────────┴─────┴────────────┘
```

### Preamble

**Direction-dependent**:

**From Gateway → Controller**:
```
0xFF 0x7E 0x07
```

**To Gateway ← Controller**:
```
0x00 0xFF 0xFF 0x7E 0x07
```

**Rationale**: Asymmetric preambles help identify direction

### Address Field

**Size**: 2 bytes (big-endian u16)

**Format**:
```
Bit 15: Direction (0=To, 1=From)
Bits 14-0: GatewayID (15-bit)
```

**Example**:
```rust
To(GatewayID(4609))   → 0x1201 → [0x12, 0x01]
From(GatewayID(4609)) → 0x9201 → [0x92, 0x01]
```

### Type Field

**Size**: 2 bytes (big-endian u16)

**Values**: See transport layer section

### Payload

**Size**: Variable (0-N bytes)

**Content**: Depends on frame type

**Escaping**: Special byte sequences are escaped

### CRC

**Algorithm**: CRC-CCITT

**Polynomial**: `0x1021`

**Initial Value**: `0xFFFF`

**Input**: Address + Type + Payload (bytes)

**Output**: 16-bit value, transmitted as little-endian u16

**Implementation**:
```rust
pub fn crc_ccitt(data: &[u8]) -> u16 {
    let mut crc: u16 = 0xFFFF;
    for &byte in data {
        crc ^= (byte as u16) << 8;
        for _ in 0..8 {
            if crc & 0x8000 != 0 {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
        }
    }
    crc
}
```

**Verification**:
1. Calculate CRC over address + type + payload
2. Compare with received CRC (little-endian)
3. Discard frame if mismatch

### Terminator

**Bytes**: `0x7E 0x08`

**Purpose**: Mark end of frame

### Escaping

**Module**: `src/gateway/link/escaping.rs`

**Problem**: Preamble and terminator markers can appear in payload

**Solution**: Escape special byte sequences

**Escape Sequences** (exact implementation varies):
- Certain multi-byte patterns are escaped
- Escaped by inserting escape byte
- Unescape reverses the process

**Functions**:
```rust
pub fn escape(data: &[u8]) -> Vec<u8>
pub fn unescape(data: &[u8]) -> Option<Vec<u8>>
```

### Receiver State Machine

**Module**: `src/gateway/link/receive.rs`

**Structure**:
```rust
pub struct Receiver<S> {
    sink: S,              // Callback for assembled frames
    buffer: Vec<u8>,      // Accumulation buffer
    state: State,         // Current parsing state
}

enum State {
    Idle,
    InFrame { address: Address },
}
```

**Algorithm**:
```
1. Wait for preamble (0xFF 0x7E 0x07 or 0x00 0xFF 0xFF 0x7E 0x07)
2. Parse address field → determine direction
3. Accumulate bytes until terminator (0x7E 0x08)
4. Extract payload, unescape if needed
5. Validate CRC
6. If valid: emit Frame to sink
7. If invalid: discard and return to idle
```

**Trait Implementation**:
```rust
impl<S: Sink<Frame>> Extend<u8> for Receiver<S>
```

**Usage**:
```rust
let mut receiver = Receiver::new(my_sink);
receiver.extend_from_slice(&bytes_from_serial);
// Frames emitted to my_sink via callbacks
```

---

## Transport Layer

**Module**: `src/gateway/transport/`

### Purpose

Handle higher-level protocol messages: commands, responses, packet batches.

### Frame Types

| Type | Value | Direction | Payload |
|------|-------|-----------|---------|
| COMMAND_REQUEST | 0x0001 | Ctrl→GW | Command to send to PV network |
| COMMAND_RESPONSE | 0x0002 | GW→Ctrl | Command acknowledgment |
| RECEIVE_REQUEST | 0x0003 | GW→Ctrl | Poll for received PV packets |
| RECEIVE_RESPONSE | 0x0004 | Ctrl→GW | Batch of PV packets |
| ENUMERATION_START_REQUEST | 0x0005 | Ctrl→GW | Trigger enumeration |
| ENUMERATION_START_RESPONSE | 0x0006 | GW→Ctrl | Enumeration started |
| IDENTIFY_REQUEST | 0x0007 | Ctrl→GW | Request gateway identity |
| IDENTIFY_RESPONSE | 0x0008 | GW→Ctrl | LongAddress of gateway |
| VERSION_REQUEST | 0x000B | Ctrl→GW | Request firmware version |
| VERSION_RESPONSE | 0x000C | GW→Ctrl | Version string |

### COMMAND_REQUEST

**Direction**: Controller → Gateway

**Purpose**: Send a command packet to the PV network

**Payload Structure**:
```
[0]: PacketType (u8)
[1]: SequenceNumber (u8)
[2..]: Command data
```

**Example**: Request node table
```
PacketType: 0x26 (NODE_TABLE_REQUEST)
SequenceNumber: 0x42
Data: [0x00, 0x00]  // Start at node 0
```

### COMMAND_RESPONSE

**Direction**: Gateway → Controller

**Purpose**: Acknowledge command receipt

**Payload Structure**:
```
[0]: Status (u8)
      0x00 = Success
      0x01 = Busy (retry later)
[1]: FreeTxBuffers (u8)
[2]: SequenceNumber (u8) - echoed from request
```

**Sequence Number Matching**:
- Controller sends COMMAND_REQUEST with seq N
- Gateway responds with COMMAND_RESPONSE with seq N
- If seq doesn't match, retransmission occurred

### RECEIVE_REQUEST

**Direction**: Gateway → Controller

**Purpose**: Poll gateway for received PV packets

**Payload**: Empty

**Frequency**: Controller polls periodically (observed ~1 Hz)

### RECEIVE_RESPONSE

**Direction**: Controller → Gateway

**Purpose**: Batch of PV packets received from wireless network

**Payload Structure**:
```
[0]: Status (u8)
      0x00 = No packets
      0x01 = Packets present
[1..2]: SlotCounter (u16 BE) - time reference
[3..]: Packet data (variable)
```

**Packet Data Format**:
```
For each packet:
  [0..1]: PacketLength (u16 BE) - includes header
  [2..7]: ReceivedPacketHeader (5 bytes)
  [7..7+data_length]: Packet payload
```

**Iteration**:
```rust
pub struct ReceivedPackets<'a> {
    data: &'a [u8],
    offset: usize,
}

impl<'a> Iterator for ReceivedPackets<'a> {
    type Item = ReceivedPacket<'a>;
    
    fn next(&mut self) -> Option<Self::Item> {
        // Parse packet length, header, payload
        // Advance offset
        // Return ReceivedPacket
    }
}
```

### ENUMERATION_START

**Purpose**: Trigger gateway enumeration sequence

**Request Payload**: Empty

**Response Payload**: Empty

**Effect**: Gateway assigns GatewayID to itself

### IDENTIFY

**Purpose**: Query gateway's LongAddress

**Request Payload**: Empty

**Response Payload**:
```
[0..8]: LongAddress (8 bytes)
```

**Use Case**: Map GatewayID ↔ LongAddress

### VERSION

**Purpose**: Query gateway firmware version

**Request Payload**: Empty

**Response Payload**:
```
[0..N]: ASCII string (variable length)
```

**Example**: `"Mgate Version 1.2.3\r"`

### Receiver Implementation

**Structure**:
```rust
pub struct Receiver<S> {
    sink: S,              // Callback for transport messages
    
    // Tracking state
    rx_packet_numbers: BTreeMap<GatewayID, BTreeMap<DSN, u16>>,
    command_sequence_numbers: BTreeMap<GatewayID, u8>,
    commands_awaiting_response: BTreeMap<GatewayID, VecDeque<u8>>,
    
    // Statistics
    counters: Counters,
}

pub struct Counters {
    pub receive_requests: u64,
    pub receive_responses: u64,
    pub receive_packets: u64,
    pub command_requests: u64,
    pub command_responses: u64,
    pub retransmitted_command_requests: u64,
    pub retransmitted_command_responses: u64,
    pub enumeration_start_requests: u64,
    pub enumeration_start_responses: u64,
    pub identify_requests: u64,
    pub identify_responses: u64,
    pub version_requests: u64,
    pub version_responses: u64,
    pub invalid_receive_responses: u64,
    pub receive_response_from_unknown_gateway: u64,
}
```

**Algorithm**:
```
impl<S: Sink<TransportMessage>> Sink<Frame> for Receiver<S> {
    fn feed(&mut self, frame: Frame) {
        match frame.frame_type {
            COMMAND_REQUEST => {
                // Parse packet type, sequence number
                // Track sequence number
                // Check for retransmission
                // Emit to sink
            }
            COMMAND_RESPONSE => {
                // Parse status, free buffers, sequence number
                // Match with pending command
                // Emit to sink
            }
            RECEIVE_REQUEST => {
                // Increment counter
                // Emit to sink
            }
            RECEIVE_RESPONSE => {
                // Parse status and slot counter
                // Iterate through packets
                // Track DSN to detect duplicates
                // Emit each packet to sink
            }
            IDENTIFY_RESPONSE => {
                // Parse LongAddress
                // Emit to sink
            }
            VERSION_RESPONSE => {
                // Parse version string
                // Emit to sink
            }
            // ... other frame types
        }
    }
}
```

**Deduplication**:
- Tracks DSN (Data Sequence Number) per gateway
- Detects retransmitted packets
- Prevents duplicate processing

**Sequence Number Tracking**:
- Tracks expected sequence numbers per gateway
- Detects out-of-order or retransmitted commands
- Maintains queue of pending command acknowledgments

---

## Error Handling

### Link Layer Errors

1. **CRC Mismatch**: Frame discarded
2. **Invalid Preamble**: Resynchronize
3. **Truncated Frame**: Timeout and discard
4. **Unescape Failure**: Frame discarded

### Transport Layer Errors

1. **Unknown Frame Type**: Logged, ignored
2. **Invalid Payload Length**: Frame discarded
3. **Unexpected GatewayID**: Logged
4. **Sequence Mismatch**: Retransmission detected

---

## Performance Optimization

### Zero-Copy Parsing

Uses `zerocopy` crate:
```rust
#[repr(C)]
#[derive(FromBytes, IntoBytes, Immutable, KnownLayout, Unaligned)]
pub struct ReceivedPacketHeader { ... }

let header = ReceivedPacketHeader::ref_from_bytes(&bytes[..5])?;
```

**Benefits**:
- No intermediate allocations
- Direct memory access
- Type-safe byte interpretation

### Buffering Strategy

- Link layer: Accumulates bytes until complete frame
- Transport layer: Processes frames immediately
- No double buffering

### CRC Calculation

- Implemented as bit-shift algorithm (no lookup table)
- Could be optimized with 256-entry lookup table
- Current implementation prioritizes code size

---

## Testing Strategy

### Unit Tests

**CRC Validation**:
```rust
#[test]
fn test_crc() {
    assert_eq!(crc_ccitt(b"123456789"), 0x29B1);
}
```

**Escaping**:
```rust
#[test]
fn test_escape_unescape() {
    let escaped = escape(data);
    assert_eq!(unescape(&escaped), Some(data));
}
```

### Integration Tests

**Frame Parsing**:
```rust
#[test]
fn test_receive_response() {
    let frame_bytes = include_bytes!("test_data/receive_response.bin");
    let mut receiver = Receiver::new(test_sink);
    receiver.extend_from_slice(frame_bytes);
    // Verify sink received expected frame
}
```

**Packet Iteration**:
```rust
#[test]
fn test_received_packets() {
    let payload = /* RECEIVE_RESPONSE payload */;
    let packets: Vec<_> = ReceivedPackets::new(payload).collect();
    assert_eq!(packets.len(), 3);
    assert_eq!(packets[0].header.packet_type, POWER_REPORT);
}
```

---

## Debugging Tools

### peek-bytes

**Purpose**: Display raw bytes from physical layer

**Output**:
```
FF 7E 07 12 01 00 04 ...
```

### peek-frames

**Purpose**: Display assembled frames with metadata

**Output**:
```
Frame {
    address: From(GatewayID(4609)),
    type: RECEIVE_REQUEST,
    payload: []
}
```

### peek-activity

**Purpose**: Display transport-layer messages

**Output**:
```
RECEIVE_REQUEST from GatewayID(4609)
RECEIVE_RESPONSE: 3 packets, slot 12345
  Packet: POWER_REPORT from Node 116
  Packet: POWER_REPORT from Node 82
  Packet: POWER_REPORT from Node 19
```

---

## Wire Format Examples

### Example 1: RECEIVE_REQUEST

```
Preamble:    FF 7E 07
Address:     92 01         (From GatewayID 4609)
Type:        00 03         (RECEIVE_REQUEST)
Payload:     (empty)
CRC:         XX XX         (little-endian)
Terminator:  7E 08
```

### Example 2: RECEIVE_RESPONSE with PowerReport

```
Preamble:    00 FF FF 7E 07
Address:     12 01         (To GatewayID 4609)
Type:        00 04         (RECEIVE_RESPONSE)
Payload:
  Status:    01            (packets present)
  SlotCtr:   45 67         (slot counter, BE)
  PktLen:    00 12         (18 bytes, BE)
  Header:
    Type:    31            (POWER_REPORT)
    NodeAddr: 00 74        (Node 116, BE)
    ShortAddr: XX XX       (BE)
    DSN:     42            (sequence 66)
    DataLen: 0D            (13 bytes)
  Data:      [13 bytes of PowerReport]
CRC:         XX XX         (little-endian)
Terminator:  7E 08
```

### Example 3: IDENTIFY_RESPONSE

```
Preamble:    00 FF FF 7E 07
Address:     12 01         (To GatewayID 4609)
Type:        00 08         (IDENTIFY_RESPONSE)
Payload:     04 C0 5B 30 12 34 56 78  (LongAddress)
CRC:         XX XX         (little-endian)
Terminator:  7E 08
```

---

## Implementation Checklist for Python Port

- [ ] CRC-CCITT calculation function
- [ ] Byte escaping/unescaping functions
- [ ] Address encoding/decoding (To/From with direction bit)
- [ ] Frame receiver state machine
- [ ] CRC validation
- [ ] Transport message parsing
- [ ] ReceivedPackets iterator
- [ ] Sequence number tracking
- [ ] DSN deduplication
- [ ] Error handling and logging
- [ ] Serial port I/O (pyserial)
- [ ] TCP socket I/O (socket module)
- [ ] Zero-copy optimization (struct.unpack_from)
