# TapTap Implementation Overview

## Purpose

This document provides a comprehensive guide to the TapTap implementation for senior Rust developers and serves as the foundation for porting to Python.

## System Architecture

TapTap is a protocol implementation for the Tigo TAP (Tigo Access Point) solar energy monitoring system. It implements a **read-only observer** that monitors RS-485 communication between:
- A **Controller** (Tigo Cloud Connect Advanced or similar)
- One or more **TAP Gateways** (bridging RS-485 to wireless PV network)
- Multiple **PV Optimizers** (solar panel monitoring devices)

### Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│     Application: Observer & CLI                     │
│     - Event generation (JSON output)                │
│     - State persistence                             │
│     - Infrastructure tracking                       │
├─────────────────────────────────────────────────────┤
│  PV Network Stack        │  Gateway Transport       │
│  - Application Layer     │  - Command/Response      │
│  - Network Layer         │  - Receive frames        │
│  - Link Layer            │  - Enumeration           │
│  - Physical Layer        │                          │
├──────────────────────────┴──────────────────────────┤
│          Gateway Link Layer                         │
│          - Frame assembly/disassembly               │
│          - CRC validation                           │
│          - Byte escaping/unescaping                 │
├─────────────────────────────────────────────────────┤
│          Physical Layer                             │
│          - Serial port (RS-485)                     │
│          - TCP (for tcpserial_hook)                 │
│          - Termios (low-level serial)               │
└─────────────────────────────────────────────────────┘
```

## Network Topology

```
┌────────────┐      RS-485        ┌────────────┐
│ Controller │◄────(gateway)──────►│    TAP     │
│    (CCA)   │     network         │  Gateway   │
└────────────┘                     └─────┬──────┘
                                         │
                                         │ 802.15.4
      ┌───────────┐                      │ wireless
      │  Monitor  │                      │ (PV network)
      │  (TapTap) │                      │
      └───────────┘                      │
           │                             │
           │ Passive                     │
           │ observation        ┌────────▼────────┐
           └────────────────────►│  PV Optimizers  │
                                 │  (solar panels) │
                                 └─────────────────┘
```

## Core Concepts

### 1. Two Protocol Stacks

**Gateway Network (RS-485, Wired)**
- Proprietary protocol over RS-485
- Controller ↔ TAP communication
- Frame-based with CRC
- Contains encapsulated PV network packets

**PV Network (802.15.4, Wireless)**
- Proprietary protocol over 802.15.4-like wireless
- TAP ↔ Optimizer communication
- Time-synchronized with slot counters
- Encapsulated within gateway frames

### 2. Passive Observation

TapTap operates in **receive-only mode**:
- Never transmits on the RS-485 bus
- Only observes controller ↔ gateway traffic
- Extracts PV network packets from gateway responses
- Maintains shadow state of infrastructure topology

### 3. Time Synchronization

The PV network uses a **slot counter** system:
- 16-bit counter with 4 epochs
- Each slot ≈ 4.29ms
- Wraps every ~240 seconds
- TapTap maintains `SlotClock` to map slots → wall-clock time

### 4. Infrastructure State

TapTap tracks network topology:
- Gateway IDs, addresses, and versions
- Node IDs, addresses, and barcodes
- Node ↔ Gateway associations
- Persistent storage to survive restarts

## Module Organization

```
taptap/
├── src/
│   ├── lib.rs              # Library root, exports public API
│   ├── barcode.rs          # Device barcode encoding/decoding
│   ├── config.rs           # Configuration structures
│   ├── capture.rs          # GZIP capture format
│   │
│   ├── gateway/            # Gateway network stack
│   │   ├── mod.rs          # Gateway module root
│   │   ├── physical/       # Physical layer
│   │   │   ├── mod.rs      # Physical layer traits
│   │   │   ├── tcp.rs      # TCP connection
│   │   │   ├── serialport.rs    # Serial port
│   │   │   ├── termios.rs  # Low-level serial (POSIX)
│   │   │   └── trace_meshdcd/   # Debug trace format
│   │   ├── link/           # Link layer
│   │   │   ├── mod.rs      # Link layer root
│   │   │   ├── address.rs  # Gateway addressing
│   │   │   ├── crc.rs      # CRC calculation
│   │   │   ├── escaping.rs # Byte escaping
│   │   │   └── receive.rs  # Frame receiver
│   │   └── transport/      # Transport layer
│   │       ├── mod.rs      # Transport types
│   │       └── receiver.rs # Transport receiver
│   │
│   ├── pv/                 # PV network stack
│   │   ├── mod.rs          # PV module root
│   │   ├── physical.rs     # PV physical layer types
│   │   └── link/           # PV link layer
│   │       ├── mod.rs      # Link layer types
│   │       └── slot_counter.rs  # Time synchronization
│   │
│   └── observer/           # Application layer
│       ├── mod.rs          # Observer root
│       ├── event.rs        # Event types (JSON output)
│       ├── node_table.rs   # Device registry
│       ├── persistent_state.rs  # State persistence
│       ├── slot_clock.rs   # Slot-to-time mapping
│       └── tests.rs        # Observer tests
│
└── docs/
    ├── protocol.md         # Protocol specification
    └── implementation/     # Implementation guides
        ├── 00-overview.md  # This file
        ├── 01-data-structures.md
        ├── 02-gateway-stack.md
        ├── 03-pv-stack.md
        ├── 04-observer.md
        └── 05-algorithms.md
```

## Key Design Patterns

### 1. Trait-Based Architecture

TapTap uses Rust traits extensively:
- `Sink` trait for frame/packet callbacks
- `Source` trait for physical layer abstraction
- `Extend<u8>` for incremental byte processing

### 2. State Machines

Receivers are state machines:
- `gateway::link::Receiver` - assembles frames from bytes
- `gateway::transport::Receiver` - extracts packets from frames
- `pv::application::Receiver` - parses PV packets

### 3. Iterator Chains

Data flows through iterator transformations:
```rust
bytes → frames → transport_messages → pv_packets → events
```

### 4. Zero-Copy Parsing

Uses `zerocopy` crate for efficient binary parsing:
- C-like `#[repr(C)]` structs
- Direct memory mapping without allocations
- Big-endian byte order handling

## Data Flow

### Typical Observation Session

1. **Initialization**
   ```
   Physical connection opened (serial or TCP)
   ↓
   Observer created (loads persistent state)
   ↓
   Receiver stack built (link → transport → pv → observer)
   ```

2. **Byte Processing**
   ```
   Raw bytes from RS-485
   ↓ gateway::link::Receiver
   Assembled frames (with CRC validation)
   ↓ gateway::transport::Receiver
   Transport messages (RECEIVE_RESPONSE, etc.)
   ↓ pv::application::Receiver
   PV packets (POWER_REPORT, NODE_TABLE, etc.)
   ↓ Observer
   Events (JSON) + State updates
   ```

3. **Output**
   ```
   JSON events → stdout
   State updates → persistent file
   ```

## Critical Implementation Details

### 1. Byte Order

- Gateway link: **little-endian** CRC
- Frame types: **big-endian** u16
- PV packets: mixed (header is big-endian)

### 2. CRC Calculation

- Algorithm: CRC-CCITT
- Polynomial: 0x1021
- Initial value: 0xFFFF
- Applied to: address + frame_type + payload
- Transmitted: little-endian u16

### 3. Escaping

Special sequences in gateway link layer:
- Preamble markers must be escaped in payload
- Escape mechanism prevents frame boundary confusion

### 4. Slot Counter Arithmetic

- 16-bit value with 4 epochs (2-bit) + slot number (14-bit)
- Non-linear wraparound requires careful handling
- Must track epoch transitions

## Testing Strategy

### Existing Tests

1. **Unit Tests**: CRC, escaping, barcode encoding
2. **Integration Tests**: Observer with recorded data
3. **Test Data**: Pre-captured binary frames

### Testing Approach

- Use `test_data.rs` for recorded protocol samples
- Validate against known-good outputs
- Test edge cases: epoch wraparound, CRC errors, etc.

## External Dependencies

### Core Dependencies
- `zerocopy` - Binary struct parsing
- `serde` / `serde_json` - Serialization
- `chrono` - Timestamps

### Optional Dependencies
- `serialport` - Serial port access
- `clap` - CLI parsing
- `env_logger` - Logging

### Platform Dependencies
- `libc` - POSIX termios (Unix/Linux only)
- `socket2` - Advanced socket operations

## Build & Run

```bash
# Build library and binary
cargo build --release

# Run observer (serial port)
cargo run --release -- observe --serial /dev/ttyUSB0

# Run observer (TCP)
cargo run --release -- observe --tcp 192.168.1.100

# Run observer with state persistence
cargo run --release -- observe --tcp 192.168.1.100 --state-file taptap.json

# Run tests
cargo test

# Debug peek commands
cargo run -- peek-bytes --tcp 192.168.1.100
cargo run -- peek-frames --tcp 192.168.1.100
cargo run -- peek-activity --tcp 192.168.1.100
```

## Performance Considerations

1. **Memory Efficiency**: Zero-copy parsing minimizes allocations
2. **CPU Efficiency**: CRC lookup tables, not polynomial division
3. **I/O Efficiency**: Buffered reads from physical layer
4. **State Persistence**: Atomic writes to prevent corruption

## Security Considerations

1. **Read-Only**: Never transmits, cannot interfere with system
2. **No Authentication**: Assumes physical access control
3. **State File**: Contains device identifiers (barcodes, addresses)
4. **Network**: RS-485 is electrically isolated

## Known Limitations

1. **No Transmit**: Cannot query devices directly
2. **No Multi-Controller**: Assumes single controller on bus
3. **Platform-Specific**: Termios requires Unix/Linux
4. **Protocol Version**: Implements specific TAP firmware version

## Future Enhancements

1. **Controller-less Mode**: TapTap could request data from TAPs
2. **MQTT Bridge**: Separate project exists (taptap-mqtt)
3. **Database Sink**: Intentionally out-of-scope (KISS principle)
4. **Web UI**: Could be built on top of library

## References

- [Protocol Documentation](../protocol.md)
- [Repository](https://github.com/willglynn/taptap)
- [Tigo TAP Product Page](https://www.tigoenergy.com/product/tigo-access-point)
