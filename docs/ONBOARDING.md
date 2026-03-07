# TapTap — Architecture & Developer Onboarding Guide

> **Audience**: New architects and developers joining the project.
> **Last updated**: February 2026 · Version 0.2.6

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Domain Background](#2-domain-background)
3. [System Purpose & Philosophy](#3-system-purpose--philosophy)
4. [High-Level Architecture](#4-high-level-architecture)
5. [Protocol Deep Dive](#5-protocol-deep-dive)
6. [Rust Implementation](#6-rust-implementation)
7. [Python Implementation](#7-python-implementation)
8. [Data Flow — End to End](#8-data-flow--end-to-end)
9. [Key Algorithms & Data Structures](#9-key-algorithms--data-structures)
10. [Observer & Event System](#10-observer--event-system)
11. [Persistent State & Infrastructure Tracking](#11-persistent-state--infrastructure-tracking)
12. [CLI & User-Facing Interface](#12-cli--user-facing-interface)
13. [Testing Strategy](#13-testing-strategy)
14. [Build, Run & Deploy](#14-build-run--deploy)
15. [Design Patterns & Conventions](#15-design-patterns--conventions)
16. [Security & Safety Considerations](#16-security--safety-considerations)
17. [Known Limitations & Future Work](#17-known-limitations--future-work)
18. [Ecosystem & Related Projects](#18-ecosystem--related-projects)
19. [Glossary](#19-glossary)
20. [Quick Reference Cheat Sheet](#20-quick-reference-cheat-sheet)

---

## 1. Executive Summary

**TapTap** is a dual-language (Rust + Python) implementation of the proprietary Tigo TAP protocol for solar energy monitoring. It passively observes the RS-485 communication bus between a Tigo Cloud Connect Advanced (CCA) controller and one or more Tigo Access Point (TAP) gateways, extracting real-time per-panel telemetry — voltage, current, temperature, and duty cycle — without ever transmitting a single byte onto the bus.

The project provides:

- A **protocol implementation** that decodes two layered protocol stacks (a wired gateway network and a wireless PV network tunnelled through it).
- A **read-only observer** that outputs JSON events to `stdout`.
- **Persistent infrastructure state** that survives restarts.
- **100% local, offline operation** — no cloud dependency.

| Property       | Value                                     |
| -------------- | ----------------------------------------- |
| Languages      | Rust (primary), Python (full port)        |
| License        | MIT                                       |
| Rust version   | 0.2.6                                     |
| Python version | 0.2.6.post1                               |
| Test count     | Rust: `cargo test`, Python: 141 passing   |
| Lines of code  | ~4,700 total (Rust + Python impl + tests) |

---

## 2. Domain Background

### 2.1 The Tigo Solar Ecosystem

Tigo manufactures module-level power electronics (MLPEs) for solar photovoltaic installations. A typical system consists of:

| Component       | Role                                                             | Example Hardware                  |
| --------------- | ---------------------------------------------------------------- | --------------------------------- |
| **Optimizer**   | Attached per-panel; DC-DC conversion, monitoring, rapid shutdown | Tigo TS4-A-O                      |
| **TAP Gateway** | Bridge between wired RS-485 bus and wireless 802.15.4 PV mesh    | Tigo TAP                          |
| **Controller**  | Polls gateways, commands nodes, reports to cloud                 | Tigo CCA (Cloud Connect Advanced) |

```
┌────────────┐      RS-485 (wired)      ┌────────────┐
│ Controller │◄─────────────────────────►│    TAP     │
│   (CCA)    │                           │  Gateway   │
└────────────┘                           └─────┬──────┘
                                               │
                                               │ 802.15.4 (wireless)
                                               │
                                     ┌─────────┼─────────┐
                                     │         │         │
                                   ┌─┴─┐     ┌─┴─┐    ┌─┴─┐
                                   │Opt│     │Opt│    │Opt│  × 135
                                   └───┘     └───┘    └───┘
```

The controller (CCA) is the bus master. It polls each TAP gateway for wirelessly-received PV network packets, issues commands destined for individual optimizers via the gateway, and performs enumeration and housekeeping. All collected data is normally sent to Tigo's cloud.

### 2.2 Why TapTap Exists

Tigo's architecture requires an internet connection and their cloud platform to access monitoring data. TapTap gives system owners direct, real-time, local access to their own hardware data by listening to the RS-485 traffic that is already flowing over the cable.

### 2.3 Physical Connectivity

The gateway network uses **RS-485**, a multi-drop differential serial protocol running at **38,400 baud** (8N1). TapTap joins the bus as a passive listener. Two methods of connection are supported:

| Method                      | Description                                                         | CLI flag                |
| --------------------------- | ------------------------------------------------------------------- | ----------------------- |
| **Hardware RS-485 adapter** | USB-to-RS-485 or HAT; direct wiring to A/B lines                    | `--serial /dev/ttyUSB0` |
| **TCP bridge**              | `tcpserial_hook` on a rooted CCA, or a serial-to-Ethernet converter | `--tcp 192.168.1.100`   |

> **Important**: TapTap never transmits. It is completely invisible to the controller and gateways.

---

## 3. System Purpose & Philosophy

### Design Principles

1. **Passive observation only** — never transmits, never interferes.
2. **KISS (Keep It Simple, Stupid)** — outputs JSON to stdout; parsing, correlation, storage, and alerting are left to external tools (Logstash, FluentD, MQTT bridges, etc.).
3. **Dual-language parity** — Rust and Python implementations produce identical output.
4. **State persistence** — infrastructure metadata (gateway addresses, node barcodes) is persisted to survive restarts.
5. **Atomic writes** — state file writes go through a temporary file + rename pattern to prevent corruption.
6. **Layered protocol stack** — mirrors the OSI-like layers of the actual protocol.

---

## 4. High-Level Architecture

### 4.1 Two Protocol Stacks

TapTap implements two protocol stacks bridged by the TAP gateway:

```
┌─────────────────────────────────────────────────────┐
│     Application: Observer & CLI                     │
│     - Event generation (JSON to stdout)             │
│     - Persistent state management                   │
│     - Infrastructure tracking                       │
├─────────────────────────────────────────────────────┤
│  PV Network Stack        │  Gateway Transport       │
│  ┌───────────────────┐   │  ┌─────────────────┐    │
│  │ Application Layer │   │  │ Command/Response │    │
│  │ (PowerReport,     │   │  │ Receive batches  │    │
│  │  NodeTable, etc.) │   │  │ Enumeration      │    │
│  ├───────────────────┤   │  └─────────────────┘    │
│  │  Network Layer    │   │                          │
│  │  (NodeID, routing)│   │                          │
│  ├───────────────────┤   │                          │
│  │  Link Layer       │   │                          │
│  │  (802.15.4 addrs) │   │                          │
│  ├───────────────────┤   │                          │
│  │  Physical Layer   │   │                          │
│  │  (2.4 GHz radio)  │   │                          │
│  └───────────────────┘   │                          │
├──────────────────────────┴──────────────────────────┤
│          Gateway Link Layer                         │
│          - Frame delimiters (0x7E 0x07 / 0x7E 0x08) │
│          - CRC-16 validation                        │
│          - Byte escaping/unescaping                 │
│          - Address parsing (direction + GatewayID)  │
├─────────────────────────────────────────────────────┤
│          Physical Layer                             │
│          ┌─────────────┐  ┌──────────────┐          │
│          │ Serial/RS485│  │ TCP (remote) │          │
│          └─────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────┘
```

**Gateway Network (wired)**: RS-485 → Link (framing, CRC) → Transport (command/response, receive polling)

**PV Network (wireless, tunnelled)**: Extracted from gateway transport RECEIVE_RESPONSE payloads → Network (NodeID, routing) → Application (PowerReport, NodeTable, TopologyReport, StringRequest/Response)

### 4.2 Processing Pipeline

```
Physical source (TCP socket / Serial port)
       │
       │  raw bytes
       ▼
Gateway Link Receiver (state machine)
       │
       │  Frame { address, frame_type, payload }
       ▼
Gateway Transport Receiver
       │ ├── enumeration events
       │ ├── gateway identity/version events
       │ ├── slot counter synchronisation
       │ └── extracted PV packets
       ▼
PV Application Receiver
       │ ├── power_report()
       │ ├── node_table_page()
       │ ├── topology_report()
       │ ├── string_request/response()
       │ └── transport event forwarding
       ▼
Observer
       │ ├── JSON events → stdout
       │ ├── SlotClock maintenance
       │ ├── NodeTable building
       │ └── PersistentState → JSON file
       ▼
stdout (JSON lines)
```

### 4.3 Sink / Callback Architecture

Both implementations use a **sink pattern** (Rust: traits, Python: Protocols). Each layer defines a `Sink` interface. The layer above implements it and is injected as the downstream consumer. Data flows **downward** through extending/feeding; events flow **upward** through sink callbacks.

```
LinkReceiver   ──implements──►   Extend<u8>         (bytes in)
    │ owns sink: S where S: Sink<Frame>              (frames out)
    ▼
TransportReceiver  ──implements──►  link::Sink       (frames in)
    │ owns sink: S where S: transport::Sink          (transport events out)
    ▼
ApplicationReceiver ──implements──► transport::Sink  (transport events in)
    │ owns sink: S where S: application::Sink        (PV events out)
    │ ALSO forwards transport::Sink methods
    ▼
Observer ──implements──► transport::Sink + application::Sink
```

The PV Application Receiver uses the **decorator pattern**: it wraps a sink that must implement _both_ transport and application sink interfaces. It forwards all transport events to its inner sink while adding application-level packet parsing.

---

## 5. Protocol Deep Dive

### 5.1 Gateway Link Layer

#### Wire Format

```
[Preamble] [SOF] [Address] [Type] [Payload] [CRC] [EOF]
```

| Field          | Size      | Details                                                                     |
| -------------- | --------- | --------------------------------------------------------------------------- |
| Preamble       | 1–3 bytes | `0xFF` (from gateway) or `0x00 0xFF 0xFF` (from controller)                 |
| Start of Frame | 2 bytes   | `0x7E 0x07`                                                                 |
| Address        | 2 bytes   | Big-endian u16; bit 15 = direction (0=To, 1=From), bits 14–0 = GatewayID    |
| Type           | 2 bytes   | Big-endian u16; identifies frame type                                       |
| Payload        | N bytes   | Variable; escaped on the wire                                               |
| CRC            | 2 bytes   | **Little-endian** CRC-16 over (Address + Type + Payload, _before_ escaping) |
| End of Frame   | 2 bytes   | `0x7E 0x08`                                                                 |

#### CRC Algorithm

The CRC uses the **CRC-16/CCITT polynomial `0x8408` (reflected `0x1021`)** but with a non-standard initial value of `0x8408` rather than the normal `0xFFFF`. This makes it incompatible with standard CRC-CCITT implementations.

```
crc = 0x8408
for each byte b in (address || type || payload):
    crc = CRC_TABLE[(crc XOR b) & 0xFF] XOR (crc >> 8)
```

The resulting 16-bit CRC is transmitted in **little-endian** order.

#### Byte Escaping

Seven byte values are replaced with 2-byte escape sequences on the wire to avoid confusion with frame delimiters:

| Raw Byte | Escaped |     | Raw Byte | Escaped |
| -------- | ------- | --- | -------- | ------- |
| `0x7E`   | `7E 00` |     | `0xA4`   | `7E 04` |
| `0x24`   | `7E 01` |     | `0xA3`   | `7E 05` |
| `0x23`   | `7E 02` |     | `0xA5`   | `7E 06` |
| `0x25`   | `7E 03` |     |          |         |

The receiver must unescape after removing delimiters and before CRC validation.

### 5.2 Gateway Transport Layer

The transport layer defines frame types for controller ↔ gateway communication:

| Frame Type            | Value    | Direction        | Purpose                        |
| --------------------- | -------- | ---------------- | ------------------------------ |
| RECEIVE_REQUEST       | `0x0148` | Ctrl → GW        | Poll for received PV packets   |
| RECEIVE_RESPONSE      | `0x0149` | GW → Ctrl        | Status + batch of PV packets   |
| COMMAND_REQUEST       | `0x0B0F` | Ctrl → GW        | Send command to PV network     |
| COMMAND_RESPONSE      | `0x0B10` | GW → Ctrl        | Command acknowledgement        |
| PING_REQUEST          | `0x0B00` | Ctrl → GW        | Keepalive                      |
| PING_RESPONSE         | `0x0B01` | GW → Ctrl        | Keepalive ack                  |
| ENUMERATION_START_REQ | `0x0014` | Ctrl → Broadcast | Begin bus enumeration          |
| ENUMERATION_START_RSP | `0x0015` | GW → Broadcast   | Enumeration ack                |
| IDENTIFY_REQUEST      | `0x003A` | Ctrl → GW        | Request hardware address       |
| IDENTIFY_RESPONSE     | `0x003B` | GW → Ctrl        | 8-byte LongAddress + GatewayID |
| VERSION_REQUEST       | `0x000A` | Ctrl → GW        | Request firmware version       |
| VERSION_RESPONSE      | `0x000B` | GW → Ctrl        | ASCII version string           |
| ENUMERATION_END_REQ   | `0x0E02` | Ctrl → GW        | End enumeration                |
| ENUMERATION_END_RSP   | `0x0006` | GW → Ctrl        | Enumeration end ack            |

#### Receive Response Structure

The RECEIVE_RESPONSE is the most complex and most frequent frame. Its payload begins with a **status bitfield** indicating which optional fields are present:

```
Status type: 0x00E0 (all fields)
  [Rx buffers used] [Tx buffers free] [???A] [???B] [Pkt# high]
  [Pkt# low] [Slot counter] [PV packets...]

Status type: 0x00FF (minimal)
  [Pkt# low] [Slot counter] [PV packets...]
```

Each PV packet is preceded by a 7-byte `ReceivedPacketHeader`:

```
[PacketType:1] [NodeAddress:2] [ShortAddress:2] [DSN:1] [DataLength:1] [Data:N]
```

### 5.3 PV Network Layer

PV devices are identified by three address types that must be correlated:

| Address Type                | Size    | Scope                   | Stability                    |
| --------------------------- | ------- | ----------------------- | ---------------------------- |
| **LongAddress** (EUI-64)    | 8 bytes | Global (factory-burned) | Permanent                    |
| **ShortAddress** (802.15.4) | 2 bytes | PAN-local               | Ephemeral (changes daily)    |
| **NodeID** (PV Node)        | 2 bytes | Gateway-local           | Semi-stable (via node table) |

Special NodeID values: `0x0001` = Gateway itself; `0x0000` = Broadcast.

### 5.4 PV Application Layer

Key packet types parsed by TapTap:

| Type                 | ID            | Dir        | Payload        | Purpose                         |
| -------------------- | ------------- | ---------- | -------------- | ------------------------------- |
| **Power Report**     | `0x31`        | Opt → GW   | 13 bytes       | Real-time measurements          |
| **Node Table Req**   | `0x26`        | Ctrl → GW  | 2 bytes        | Request address mapping         |
| **Node Table Rsp**   | `0x27`        | GW → Ctrl  | 4 + 10×N bytes | Address mapping entries         |
| **Topology Report**  | `0x09`        | Opt → GW   | 22 bytes       | Mesh routing info               |
| **String Req/Rsp**   | `0x06`/`0x07` | Ctrl ↔ Opt | Variable       | Version, config queries         |
| **PV Configuration** | `0x13`/`0x18` | Ctrl ↔ Opt | Variable       | Report timing setup             |
| **Broadcast**        | `0x22`/`0x23` | Ctrl ↔ GW  | 2 bytes        | PV on/off signal                |
| **GW Radio Config**  | `0x0D`/`0x0E` | Ctrl ↔ GW  | Variable       | Channel, PAN ID, encryption key |

### 5.5 Time Synchronisation — Slot Counter

The PV network uses a shared clock called the **slot counter**:

```
┌──────────┬────────────────────────────────┐
│ Epoch(2) │       Slot Number (14)         │
└──────────┴────────────────────────────────┘
  Bits 15-14          Bits 13-0
```

- **4 epochs**: `0x0xxx`, `0x4xxx`, `0x8xxx`, `0xCxxx` — cycle 0 → 4 → 8 → C → 0
- **12,000 slots per epoch** (0–11,999)
- **~5 ms per slot** → ~60 seconds per epoch → ~240 seconds full cycle
- Power reports include their measurement slot counter for temporal correlation
- TapTap maintains a `SlotClock` per gateway that maps slot counters to wall-clock `datetime`

---

## 6. Rust Implementation

### 6.1 Repository Layout

```
src/
├── lib.rs                  # Library root: exports barcode, gateway, pv, observer
├── main.rs                 # CLI binary (clap-based)
├── barcode.rs              # Barcode ↔ LongAddress conversion
├── config.rs               # SourceConfig abstraction
├── capture.rs              # GZIP capture format
├── test_data.rs            # Recorded protocol samples (#[cfg(test)])
│
├── gateway/
│   ├── mod.rs              # Re-exports Frame, GatewayID
│   ├── physical/
│   │   ├── mod.rs          # Source trait + SourceConfig dispatcher
│   │   ├── tcp.rs          # TcpStream with keepalive
│   │   ├── serialport.rs   # serialport crate integration
│   │   ├── termios.rs      # POSIX termios for low-level serial
│   │   └── trace_meshdcd/  # Debug trace file reader
│   ├── link/
│   │   ├── mod.rs          # Address, GatewayID, Frame types
│   │   ├── address.rs      # 15-bit GatewayID + direction encoding
│   │   ├── crc.rs          # CRC-16 with 0x8408 polynomial
│   │   ├── escaping.rs     # 7-sequence byte escaping
│   │   └── receive.rs      # State machine frame assembler
│   └── transport/
│       ├── mod.rs          # Type enum, Sink trait, ReceiveResponse parsing
│       └── receiver.rs     # Frame → transport event dispatcher
│
├── pv/
│   ├── mod.rs              # Re-exports key types
│   ├── physical.rs         # RSSI type
│   ├── link.rs             # LongAddress, ShortAddress, DSN
│   ├── network.rs          # NodeID, NodeAddress, ReceivedPacketHeader
│   └── application/
│       ├── mod.rs          # PacketType, Sink, Receiver; U12Pair, PowerReport
│       ├── node_table.rs   # NodeTableRequest/Response parsing
│       ├── packet_type.rs  # PacketType enum constants
│       └── power_report.rs # PowerReport structs + temp conversion
│
└── observer/
    ├── mod.rs              # Observer struct; transport+application Sink impl
    ├── event.rs            # PowerReportEvent → JSON serialisation
    ├── node_table.rs       # NodeTableBuilder for page accumulation
    ├── persistent_state.rs # PersistentState + infrastructure_report events
    ├── slot_clock.rs       # SlotClock: slot counter → wall-clock mapping
    └── tests.rs            # Integration tests with recorded data
```

### 6.2 Key Design Characteristics (Rust)

| Pattern                  | Usage                                                                    |
| ------------------------ | ------------------------------------------------------------------------ |
| **Traits as interfaces** | `Sink` traits for frame/event callbacks; `Extend<u8>` for byte ingestion |
| **Zero-copy parsing**    | `zerocopy` crate with `#[repr(C)]` structs for direct memory mapping     |
| **State machines**       | `gateway::link::Receiver` enum-driven frame assembly                     |
| **Iterator chains**      | `ReceivedPackets` iterator over variable-length packet batches           |
| **No `async`**           | Blocking I/O with reconnect loop; simplicity over concurrency            |
| **Feature gates**        | `serialport`, `clap`, `env_logger` are optional features                 |

### 6.3 Dependencies

| Crate                  | Purpose                         |
| ---------------------- | ------------------------------- |
| `zerocopy`             | Zero-copy binary struct parsing |
| `serde` / `serde_json` | JSON serialisation              |
| `schemars`             | JSON Schema generation          |
| `chrono`               | Timestamps with timezone        |
| `socket2`              | TCP socket with keepalive       |
| `libc`                 | POSIX termios                   |
| `log` / `env_logger`   | Logging                         |
| `clap`                 | CLI argument parsing            |
| `serialport`           | Serial port I/O                 |
| `flate2`               | GZIP for capture files          |
| `thiserror`            | Error type derivation           |

---

## 7. Python Implementation

### 7.1 Repository Layout

```
python/
├── setup.py                    # setuptools packaging
├── requirements.txt            # pyserial, jsonschema, click, dev tools
├── taptap/
│   ├── __init__.py             # Package root: exports Barcode
│   ├── barcode.py              # Barcode ↔ LongAddress
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py             # Click-based CLI (observe, list-serial-ports, peek-bytes)
│   ├── gateway/
│   │   ├── __init__.py
│   │   ├── physical/
│   │   │   ├── __init__.py
│   │   │   ├── tcp.py          # TcpSource with reconnect + keepalive
│   │   │   └── serial.py       # SerialSource (pyserial)
│   │   ├── link/
│   │   │   ├── __init__.py     # Exports GatewayID, Address, Frame
│   │   │   ├── address.py      # GatewayID, AddressTo, AddressFrom
│   │   │   ├── crc.py          # Table-driven CRC-16
│   │   │   ├── escaping.py     # escape/unescape/unescaped_byte
│   │   │   └── receiver.py     # State machine LinkReceiver
│   │   └── transport/
│   │       ├── __init__.py
│   │       ├── types.py        # Frame type constants, ReceiveResponse parser
│   │       └── receiver.py     # TransportReceiver
│   ├── pv/
│   │   ├── __init__.py
│   │   ├── link/
│   │   │   ├── __init__.py     # SlotCounter, SlotEpoch, LongAddress, etc.
│   │   │   └── slot_counter.py # SlotCounter/SlotEpoch/SlotNumber
│   │   ├── network/
│   │   │   ├── __init__.py
│   │   │   └── types.py        # NodeID, NodeAddress, LongAddress, ReceivedPacketHeader
│   │   └── application/
│   │       ├── __init__.py     # Re-exports PacketType, PowerReport, etc.
│   │       ├── types.py        # PacketType (IntEnum), U12Pair, PowerReport
│   │       └── receiver.py     # ApplicationReceiver
│   └── observer/
│       ├── __init__.py
│       ├── observer.py         # Observer class (transport + application Sink)
│       ├── event.py            # PowerReportEvent, Event envelope
│       ├── node_table.py       # NodeTable dict wrapper
│       ├── persistent_state.py # JSON persistence + infrastructure events
│       └── slot_clock.py       # 48-entry table-based SlotClock
└── tests/
    ├── test_address.py         # GatewayID, Address encoding (6 tests)
    ├── test_barcode.py         # Barcode ↔ LongAddress (25 tests)
    ├── test_crc.py             # CRC test vectors (6 tests)
    ├── test_escaping.py        # Escape/unescape/round-trip (10 tests)
    ├── test_slot_counter.py    # SlotCounter arithmetic (7 tests)
    ├── test_slot_clock.py      # SlotClock mapping (3 tests)
    ├── test_pv_types.py        # U12Pair, PowerReport (12 tests)
    ├── test_pv_application.py  # PacketType, PowerReport integration (17 tests)
    ├── test_node_table.py      # NodeTable operations (4 tests)
    ├── test_observer_event.py  # PowerReportEvent serialisation (3 tests)
    ├── test_observer_state.py  # PersistentState I/O (3 tests)
    ├── test_persistent_state.py # save/load round-trip (5 tests)
    ├── test_link_receiver.py   # LinkReceiver state machine (9 tests)
    ├── test_transport_receiver.py # TransportReceiver dispatch (4 tests)
    ├── test_received_packets.py # Packet iteration (4 tests)
    ├── test_serial_source.py   # SerialSource instantiation (3 tests)
    ├── test_tcp_source.py      # TcpSource instantiation (3 tests)
    ├── test_cli.py             # Click CLI runner (4 tests)
    ├── test_observer_integration.py # Observer + slot clock flow (5 tests)
    └── test_end_to_end.py      # Full stack integration (3 tests)
```

### 7.2 Key Design Characteristics (Python)

| Pattern                       | Usage                                                           |
| ----------------------------- | --------------------------------------------------------------- |
| **`typing.Protocol`**         | Sink interfaces (structural subtyping, no explicit inheritance) |
| **`@dataclass(frozen=True)`** | Immutable value types (GatewayID, SlotCounter, PowerReport)     |
| **`IntEnum`**                 | PacketType, SlotEpoch                                           |
| **`struct.unpack`**           | Binary parsing (replaces Rust's `zerocopy`)                     |
| **State machine**             | LinkReceiver with 7-state `State` enum                          |
| **Decorator pattern**         | ApplicationReceiver wraps and forwards transport events         |
| **Click**                     | CLI framework (replaces Rust's `clap`)                          |

### 7.3 Python Dependencies

| Package               | Purpose                | Rust Equivalent      |
| --------------------- | ---------------------- | -------------------- |
| `pyserial`            | Serial port I/O        | `serialport` crate   |
| `click`               | CLI framework          | `clap` crate         |
| `jsonschema`          | JSON schema validation | `schemars` crate     |
| **stdlib** `struct`   | Binary parsing         | `zerocopy`           |
| **stdlib** `json`     | JSON serialisation     | `serde_json`         |
| **stdlib** `socket`   | TCP sockets            | `socket2`            |
| **stdlib** `datetime` | Timestamps             | `chrono`             |
| **stdlib** `logging`  | Logging                | `log` + `env_logger` |

### 7.4 Development Dependencies

| Package      | Purpose              |
| ------------ | -------------------- |
| `pytest`     | Test framework       |
| `pytest-cov` | Coverage reporting   |
| `black`      | Code formatting      |
| `mypy`       | Static type checking |

---

## 8. Data Flow — End to End

### 8.1 Startup Sequence

```
1. CLI parses arguments (source, state-file)
2. Physical source is opened (TCP socket or serial port)
3. Observer is created
   └── reads persistent state from JSON file (if exists)
   └── emits infrastructure_report event to stdout
4. Protocol stack is wired up:
   Observer ← ApplicationReceiver ← TransportReceiver ← LinkReceiver
5. Main read loop begins
```

### 8.2 Per-Byte Processing

```
Source.read(1024 bytes)
  │
  ▼
LinkReceiver.extend_from_slice(bytes)
  │  For each byte:
  │  ├── IDLE: Wait for 0x7E
  │  ├── START_OF_FRAME: Expect 0x07
  │  ├── FRAME: Accumulate (max 256 bytes)
  │  │   └── 0x7E → FRAME_ESCAPE
  │  ├── FRAME_ESCAPE:
  │  │   ├── 0x08 → End of frame → parse
  │  │   └── 0x00-0x06 → Unescape byte, continue
  │  └── GIANT: Discard oversized frames
  │
  │  On valid frame (CRC check passed):
  ▼
TransportReceiver.frame(Frame)
  │  Dispatch by frame_type:
  │  ├── RECEIVE_REQUEST (0x0148)
  │  │   └── Store packet number, signal slot counter capture
  │  ├── RECEIVE_RESPONSE (0x0149)
  │  │   ├── Parse status bitfield
  │  │   ├── Extract slot counter → signal slot counter observed
  │  │   └── Iterate PV packets → packet_received()
  │  ├── COMMAND_REQUEST (0x0B0F)
  │  │   └── Store (packet_type, payload) keyed by (gateway, seq#)
  │  ├── COMMAND_RESPONSE (0x0B10)
  │  │   └── Correlate with request → command_executed()
  │  ├── IDENTIFY_RESPONSE (0x003B)
  │  │   └── gateway_identity_observed(GatewayID, LongAddress)
  │  ├── VERSION_RESPONSE (0x000B)
  │  │   └── gateway_version_observed(GatewayID, version_string)
  │  └── ENUMERATION_* → enumeration_started/ended
  │
  ▼
ApplicationReceiver
  │  Forwards all transport events to Observer
  │  Additionally processes:
  │  ├── packet_received():
  │  │   ├── POWER_REPORT (0x31) → parse 13-byte PowerReport → power_report()
  │  │   ├── TOPOLOGY_REPORT (0x09) → topology_report()
  │  │   └── STRING_RESPONSE (0x07) → string_response()
  │  └── command_executed():
  │      ├── NODE_TABLE (0x26/0x27) → parse entries → node_table_page()
  │      └── STRING (0x06/0x07) → string_request/response()
  │
  ▼
Observer
  ├── Slot clock maintenance:
  │   ├── gateway_slot_counter_captured() → record wall-clock time
  │   └── gateway_slot_counter_observed() → update SlotClock for gateway
  │
  ├── Infrastructure tracking:
  │   ├── gateway_identity_observed() → store LongAddress
  │   ├── gateway_version_observed() → store version string
  │   ├── node_table_page() → accumulate pages → build NodeTable
  │   └── enumeration_started/ended() → atomic gateway identity update
  │
  ├── Power report processing:
  │   └── power_report() → SlotClock.get(slot_counter) → timestamp
  │       └── PowerReportEvent → Event → JSON → stdout
  │
  └── State persistence:
      └── On any infrastructure change:
          ├── Write JSON to temp file
          ├── Atomic rename
          └── Emit infrastructure_report event to stdout
```

### 8.3 Output Event Types

#### Power Report (emitted per measurement)

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

#### Infrastructure Report (emitted on topology changes and at startup)

```json
{
  "event_type": "infrastructure_report",
  "gateways": {
    "4609": {
      "address": "04:C0:5B:30:12:34:56:78",
      "version": "Mgate Version G8.59\rJul  6 2020\r16:51:51\rGW-H158.4.3S0.12\r"
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

## 9. Key Algorithms & Data Structures

### 9.1 CRC-16 Calculation

- **Polynomial**: `0x8408` (reflected representation of `0x1021`)
- **Initial value**: `0x8408` (non-standard — intentional incompatibility)
- **Implementation**: 256-entry lookup table
- **Input**: Raw bytes of Address + Type + Payload (unescaped)
- **Output**: 16-bit value compared against frame's little-endian CRC field

### 9.2 Barcode Encoding

Tigo barcodes encode the 8-byte LongAddress (802.15.4 EUI-64) into a human-readable format: `X-NNNNNNNC`

**Encoding**:

1. Extract leading nibble from first byte (always `4` for current devices)
2. Vendor prefix `04:C0:5B` is implied and omitted
3. Zero-compression: leading zeros between nibble and significant digits are replaced by `-`
4. Remaining 7 nibbles are the hex representation of the unique portion
5. Final character is a CRC-4 using polynomial `0x3`, initial value `0x2`, alphabet `GHJKLMNPRSTVWXYZ`

**Example**: `04:C0:5B:40:00:9A:57:A2` → `4-9A57A2L`

### 9.3 SlotClock — Time Mapping

The SlotClock maps slot counter values to wall-clock time using a 48-entry lookup table:

- **48 entries** = 4 epochs × 12 buckets of 1,000 slots each
- **Nominal slot duration**: 5 ms ± 1%
- **Per-bucket duration**: ~5 seconds
- **Algorithm**: When a new (slot_counter, wall_time) reference arrives:
  1. Calculate the table index: `(epoch × 12000 + slot_number) / 1000`
  2. Store the wall time for that index
  3. Backfill intervening entries with nominal 5-second intervals
  4. To resolve any slot counter: look up its index, add sub-index offset (`(slot % 1000) × 5ms`)

This provides drift correction while maintaining smooth interpolation.

### 9.4 U12Pair — Packed 12-Bit Values

Two 12-bit unsigned integers are packed into 3 bytes:

```
Byte 0:    AAAA AAAA
Byte 1:    AAAA BBBB
Byte 2:    BBBB BBBB

First  (A) = bytes[0..2] >> 4     (upper 12 bits)
Second (B) = bytes[1..3] & 0x0FFF (lower 12 bits)
```

Used for voltage_in/voltage_out and current/temperature pairs in PowerReport.

### 9.5 PowerReport Field Conversions

| Field              | Raw            | Formula                       | Unit            |
| ------------------ | -------------- | ----------------------------- | --------------- |
| `voltage_in`       | U12Pair.first  | `× 0.05`                      | Volts           |
| `voltage_out`      | U12Pair.second | `× 0.1`                       | Volts           |
| `current`          | U12Pair.first  | `× 0.005`                     | Amperes         |
| `temperature`      | U12Pair.second | Sign-extend 12→16 bit, `÷ 10` | °C              |
| `dc_dc_duty_cycle` | u8             | `÷ 255`                       | Ratio (0.0–1.0) |
| `rssi`             | u8             | Raw                           | Unsigned 0–255  |

### 9.6 NodeTableBuilder — Page Accumulation

The node table is retrieved from the gateway in pages (each page fits in a single 802.15.4 frame ≤ ~124 bytes). The builder accumulates pages until an empty response signals completion, then atomically replaces the gateway's node table.

### 9.7 Receive Response Status Parsing

The receive response uses a 16-bit bitfield to indicate which optional status fields are present. Bits are read right-to-left; a `0` bit means the field is included:

```
0x00E0 = 0000_0000_1110_0000
  bit 0: Rx buffers used (1 byte)      ✓ present
  bit 1: Tx buffers free (1 byte)      ✓ present
  bit 2: ??? A (2 bytes)               ✓ present
  bit 3: ??? B (2 bytes)               ✓ present
  bit 4: (unused)
  bit 5: Packet# high (1 byte)         ✓ present
  ...always present: Packet# low, Slot counter, Packets
```

---

## 10. Observer & Event System

### 10.1 Observer Responsibilities

| Responsibility            | Trigger                                 | Action                                                                     |
| ------------------------- | --------------------------------------- | -------------------------------------------------------------------------- |
| Slot clock maintenance    | RECEIVE_REQUEST / RECEIVE_RESPONSE pair | Record wall-clock time on request, correlate with slot counter on response |
| Power report timestamping | `power_report()` callback               | Map slot counter → datetime via SlotClock, emit JSON                       |
| Infrastructure tracking   | IDENTIFY_RESPONSE, VERSION_RESPONSE     | Store in PersistentState, write to disk                                    |
| Node table building       | NODE_TABLE_RESPONSE pages               | Accumulate until empty page, replace atomically                            |
| Enumeration handling      | ENUMERATION_START / END                 | Buffer identities, apply atomically on end                                 |

### 10.2 Event Emission

Events are serialised as single-line JSON objects and written to `stdout`. This design allows pipe-based integration with any downstream consumer:

```bash
taptap observe --tcp 192.168.1.100 | jq '.voltage_in'
taptap observe --tcp 192.168.1.100 | tee raw.jsonl | some-processor
```

### 10.3 Enumeration State Machine

During gateway enumeration, the controller assigns temporary IDs. The Observer buffers all identity/version observations during enumeration and applies them atomically when enumeration ends. This prevents half-updated state:

```
enumeration_started(temp_gw_id)
  │ → Buffer identities (skip temp ID)
  ▼
identify_response(gw_id, address)
version_response(gw_id, version)
  │ → Store in buffer
  ▼
enumeration_ended(gw_id)
  │ → Replace persistent maps with buffer contents
  └ → Write state, emit infrastructure_report
```

---

## 11. Persistent State & Infrastructure Tracking

### 11.1 State File Format

```json
{
  "gateway_identities": {
    "4609": "04:C0:5B:30:12:34:56:78"
  },
  "gateway_versions": {
    "4609": "Mgate Version G8.59\rJul  6 2020\r16:51:51\rGW-H158.4.3S0.12\r"
  },
  "gateway_node_tables": {
    "4609": {
      "2": "04:C0:5B:40:9A:57:A2:3E",
      "3": "04:C0:5B:40:AA:BB:CC:DD"
    }
  }
}
```

### 11.2 Why Persistence Matters

Gateway identity (IDENTIFY_RESPONSE) and node table (NODE_TABLE_RESPONSE) frames are transmitted **infrequently** — typically only during overnight housekeeping, not during daytime PV operation. Without persistence, a restart mid-day would lose the ability to associate node IDs with barcodes until the next enumeration cycle (possibly the following night).

### 11.3 Write Strategy

1. Serialise state to JSON
2. Write to `<state-file>.tmp`
3. Atomic rename to `<state-file>` (POSIX `rename()` is atomic on the same filesystem)
4. Emit `infrastructure_report` event to stdout

---

## 12. CLI & User-Facing Interface

### 12.1 Commands

| Command             | Purpose                                     | Key Flags                            |
| ------------------- | ------------------------------------------- | ------------------------------------ |
| `observe`           | Main monitoring mode; JSON events to stdout | `--tcp` / `--serial`, `--state-file` |
| `peek-bytes`        | Debug: raw hex bytes from physical layer    | `--raw`                              |
| `peek-frames`       | Debug: assembled link-layer frames          |                                      |
| `peek-activity`     | Debug: transport + PV application events    |                                      |
| `list-serial-ports` | Enumerate available serial ports            |                                      |

### 12.2 Connection Options

| Flag                    | Default | Description                      |
| ----------------------- | ------- | -------------------------------- |
| `--tcp HOST`            | —       | TCP connection to serial bridge  |
| `--serial PORT`         | —       | Direct RS-485 serial port        |
| `--port N`              | 502     | TCP port (Modbus standard)       |
| `--reconnect-timeout N` | 60s     | Idle timeout before reconnect    |
| `--reconnect-retry N`   | 0 (∞)   | Max reconnect attempts           |
| `--reconnect-delay N`   | 5s      | Delay between reconnect attempts |
| `--state-file PATH`     | None    | JSON file for persistent state   |

### 12.3 Reconnect Behaviour

Both implementations implement robust reconnection:

1. On connection failure or idle timeout → close connection
2. Sleep for `reconnect_delay` seconds
3. Retry connection
4. If `reconnect_retry` > 0 and exceeded → exit with error code
5. On success → reset retry counter, resume read loop

TCP connections use keepalive probing (idle: 10s, interval: 5s, retries: 3) to detect dead connections before the OS's default timeout.

---

## 13. Testing Strategy

### 13.1 Test Pyramid

```
           ┌──────────────┐
           │  End-to-End  │   3 tests — full stack: bytes → JSON events
           ├──────────────┤
           │ Integration  │   9 tests — observer + receiver interactions
           ├──────────────┤
           │    Unit      │  129 tests — individual functions & types
           └──────────────┘
```

### 13.2 Test Categories (Python — 141 total)

| Category             | Tests | What's Covered                                 |
| -------------------- | ----- | ---------------------------------------------- |
| Barcode              | 25    | Encoding, decoding, CRC validation, edge cases |
| CRC                  | 6     | Known test vectors, empty input, incremental   |
| Escaping             | 10    | Escape/unescape, round-trip, invalid sequences |
| Address              | 6     | GatewayID encoding, direction bit, edge cases  |
| Slot Counter         | 7     | Epoch wrapping, slots_since, boundary values   |
| Slot Clock           | 3     | Mapping accuracy, drift correction             |
| PV Types             | 12    | U12Pair, PowerReport field extraction          |
| PV Application       | 17    | PacketType, PowerReport parsing                |
| Node Table           | 4     | Set/get, serialisation                         |
| Observer Events      | 3     | JSON serialisation format                      |
| Observer State       | 3     | PersistentState save/load                      |
| Persistent State     | 5     | Round-trip JSON, atomic write                  |
| Link Receiver        | 9     | State machine transitions, CRC validation      |
| Transport Receiver   | 4     | Frame type dispatch, counter tracking          |
| Received Packets     | 4     | Packet iteration over batches                  |
| Serial Source        | 3     | Instantiation, config                          |
| TCP Source           | 3     | Instantiation, config                          |
| CLI                  | 4     | Click runner, help output                      |
| Observer Integration | 5     | Slot clock flow, state persistence             |
| End-to-End           | 3     | Full stack processing, error recovery          |

### 13.3 Test Data

The Rust implementation uses `test_data.rs` containing hex-encoded recorded RS-485 captures. The Python tests construct known-good binary frames programmatically or use extracted constants from the Rust test data.

### 13.4 Running Tests

```bash
# Rust
cargo test

# Python
cd python
pytest                    # All 141 tests
pytest --cov=taptap       # With coverage
pytest tests/test_crc.py  # Single module
```

---

## 14. Build, Run & Deploy

### 14.1 Rust

```bash
# Build
cargo build --release

# Run (TCP)
cargo run --release -- observe --tcp 192.168.1.100 --state-file taptap.json

# Run (serial)
cargo run --release -- observe --serial /dev/ttyUSB0 --state-file taptap.json

# Debug — increasing verbosity
RUST_LOG=info cargo run -- observe --tcp 192.168.1.100
RUST_LOG=debug cargo run -- observe --tcp 192.168.1.100

# Build without optional features
cargo build --no-default-features
```

### 14.2 Python

```bash
cd python

# Install (editable mode for development)
pip install -e '.[dev]'

# Run
taptap observe --tcp 192.168.1.100 --state-file taptap.json
taptap observe --serial /dev/ttyUSB0
taptap list-serial-ports

# Development
pytest                   # Tests
pytest --cov=taptap      # Coverage
black taptap/            # Format
mypy taptap/             # Type check
```

### 14.3 Minimum Requirements

| Language | Version              |
| -------- | -------------------- |
| Rust     | 2021 edition (1.56+) |
| Python   | 3.8+                 |

---

## 15. Design Patterns & Conventions

### 15.1 Layered Receiver Pattern

Every protocol layer follows the same pattern:

```
Receiver<S: Sink> {
    sink: S,          // downstream consumer
    buffer: ...,      // layer-specific accumulation state
    counters: ...,    // diagnostic counters
}
```

Input arrives via a standard method (`extend_from_slice`, `frame()`, `packet_received()`). Parsed results are dispatched to the sink. Counters track success/failure metrics per frame type.

### 15.2 Immutable Value Types

Protocol data structures (`GatewayID`, `SlotCounter`, `PowerReport`, `LongAddress`) are immutable. In Rust: `#[derive(Copy, Clone)]`. In Python: `@dataclass(frozen=True)`.

### 15.3 Error Handling

- **Link layer**: CRC mismatches and invalid escapes cause frame drops (logged, counted, never fatal)
- **Transport layer**: Unknown frame types are logged and ignored
- **Observer**: Missing slot clock causes power reports to be discarded with a warning
- **State file**: Read failures fall back to empty state; write failures are logged but non-fatal

### 15.4 Naming Conventions

| Concept              | Rust                        | Python                      |
| -------------------- | --------------------------- | --------------------------- |
| Gateway source frame | `Frame`                     | `Frame`                     |
| Gateway ID           | `GatewayID`                 | `GatewayID`                 |
| PV optimizer         | `NodeID`                    | `NodeID`                    |
| Hardware address     | `LongAddress`               | `LongAddress`               |
| Time sync            | `SlotCounter` / `SlotClock` | `SlotCounter` / `SlotClock` |
| Callback interface   | `trait Sink`                | `class Sink(Protocol)`      |
| State machine state  | `enum State`                | `class State(Enum)`         |

### 15.5 Byte Order Summary

| Context                     | Byte Order        |
| --------------------------- | ----------------- |
| Address field               | Big-endian        |
| Frame type field            | Big-endian        |
| CRC field on wire           | **Little-endian** |
| SlotCounter                 | Big-endian        |
| NodeAddress                 | Big-endian        |
| All `#[repr(C)]` PV structs | Big-endian        |

---

## 16. Security & Safety Considerations

| Aspect                 | Detail                                                                                                      |
| ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Read-only**          | TapTap never transmits — it cannot interfere with PV system operation                                       |
| **No authentication**  | Physical RS-485 access is assumed to be access-controlled                                                   |
| **State file content** | Contains device barcodes and hardware addresses (may be considered PII)                                     |
| **Network exposure**   | TCP mode connects to a remote serial bridge; no encryption on this link                                     |
| **Encryption key**     | The gateway radio configuration response contains what appears to be an AES-128 key; TapTap does not use it |
| **Crash safety**       | Atomic state file writes prevent corruption                                                                 |

---

## 17. Known Limitations & Future Work

### Current Limitations

1. **Single controller assumption** — assumes one controller on the RS-485 bus
2. **No transmit capability** — cannot query devices directly or replace the controller
3. **Platform-specific serial** — POSIX termios requires Unix/Linux (the `serialport` feature works cross-platform)
4. **Protocol version** — developed against specific TAP firmware (G8.59, v4.0.1); other versions may differ
5. **No multi-TAP testing** — enumeration of multiple gateways is based on protocol analysis, not tested in practice
6. **No database sink** — by design; use external tools for storage

### Potential Future Enhancements

| Enhancement            | Description                                                                    |
| ---------------------- | ------------------------------------------------------------------------------ |
| Controller-less mode   | TapTap transmits on the bus to poll gateways directly                          |
| MQTT bridge            | Separate project: [taptap-mqtt](https://github.com/litinoveweedle/taptap-mqtt) |
| Web UI                 | Built on top of the library                                                    |
| Capture/replay         | GZIP capture format exists (`capture.rs`)                                      |
| Additional event types | Topology reports, PV configuration, network status                             |

---

## 18. Ecosystem & Related Projects

| Project                                                       | Description                              |
| ------------------------------------------------------------- | ---------------------------------------- |
| [taptap](https://github.com/willglynn/taptap)                 | This project — Rust implementation       |
| [taptap-mqtt](https://github.com/litinoveweedle/taptap-mqtt)  | MQTT bridge for TapTap output            |
| [tcpserial_hook](https://github.com/willglynn/tcpserial_hook) | Makes CCA serial data available over TCP |

### Integration Examples

```bash
# Pipe to jq for filtering
taptap observe --tcp 192.168.1.100 | jq 'select(.event_type == "power_report")'

# Pipe to MQTT
taptap observe --tcp 192.168.1.100 | taptap-mqtt

# Log to file
taptap observe --tcp 192.168.1.100 --state-file state.json >> events.jsonl

# Pipe to Logstash / FluentD for storage
taptap observe --tcp 192.168.1.100 | logstash -f taptap.conf
```

---

## 19. Glossary

| Term             | Definition                                                                            |
| ---------------- | ------------------------------------------------------------------------------------- |
| **CCA**          | Cloud Connect Advanced — Tigo's controller device                                     |
| **TAP**          | Tigo Access Point — gateway between RS-485 and 802.15.4 wireless                      |
| **Optimizer**    | Module-level power electronics attached to each solar panel (e.g., TS4-A-O)           |
| **RS-485**       | Differential serial bus standard; supports multi-drop (multiple devices on one cable) |
| **802.15.4**     | IEEE standard for low-rate wireless personal area networks (used at 2.4 GHz)          |
| **GatewayID**    | 15-bit identifier for a TAP on the RS-485 bus                                         |
| **NodeID**       | 16-bit identifier for a PV device within a gateway's node table                       |
| **LongAddress**  | 8-byte globally unique hardware address (EUI-64)                                      |
| **ShortAddress** | 2-byte ephemeral 802.15.4 link-layer address                                          |
| **Barcode**      | Human-readable encoding of a LongAddress (e.g., `4-9A57A2L`)                          |
| **SlotCounter**  | 16-bit time reference: 2-bit epoch + 14-bit slot number (0–11,999)                    |
| **SlotClock**    | TapTap's mapping from SlotCounter values to wall-clock datetime                       |
| **PowerReport**  | 13-byte telemetry packet from an optimizer: voltages, current, temperature, RSSI      |
| **DSN**          | Data Sequence Number — 1-byte packet sequence tracker                                 |
| **RSSI**         | Received Signal Strength Indicator — wireless signal quality (0–255)                  |
| **PAN ID**       | Personal Area Network identifier for 802.15.4                                         |
| **Sink**         | Callback interface pattern for passing events between protocol layers                 |
| **Frame**        | A Gateway link-layer PDU: address + type + payload (CRC validated)                    |
| **Preamble**     | Direction-indicating bytes before frame delimiter (`0xFF` or `0x00 0xFF 0xFF`)        |
| **KISS**         | Keep It Simple, Stupid — project design philosophy                                    |

---

## 20. Quick Reference Cheat Sheet

### Connecting

```bash
# Rust (TCP)
cargo run --release -- observe --tcp 192.168.1.100 --state-file state.json

# Python (TCP)
cd python && pip install -e . && taptap observe --tcp 192.168.1.100 --state-file state.json

# Rust (serial)
cargo run --release -- observe --serial /dev/ttyUSB0 --state-file state.json
```

### Debugging

```bash
# See raw bytes
taptap peek-bytes --tcp 192.168.1.100

# See link-layer frames
taptap peek-frames --tcp 192.168.1.100

# See transport/application activity
taptap peek-activity --tcp 192.168.1.100

# Enable debug logging (Rust)
RUST_LOG=debug taptap observe --tcp 192.168.1.100
```

### Key File Locations

| Purpose            | Rust                                | Python                                 |
| ------------------ | ----------------------------------- | -------------------------------------- |
| CRC implementation | `src/gateway/link/crc.rs`           | `taptap/gateway/link/crc.py`           |
| Frame receiver     | `src/gateway/link/receive.rs`       | `taptap/gateway/link/receiver.py`      |
| Transport receiver | `src/gateway/transport/receiver.rs` | `taptap/gateway/transport/receiver.py` |
| PV application     | `src/pv/application/mod.rs`         | `taptap/pv/application/types.py`       |
| Observer           | `src/observer.rs` + `src/observer/` | `taptap/observer/observer.py`          |
| Persistent state   | `src/observer/persistent_state.rs`  | `taptap/observer/persistent_state.py`  |
| Slot clock         | `src/observer/slot_clock.rs`        | `taptap/observer/slot_clock.py`        |
| CLI entry point    | `src/main.rs`                       | `taptap/cli/main.py`                   |
| Protocol spec      | `docs/protocol.md`                  | `docs/protocol.md`                     |

### Protocol Quick Reference

```
Frame: [Preamble] [7E 07] [Addr:2 BE] [Type:2 BE] [Payload:N] [CRC:2 LE] [7E 08]
CRC:   poly=0x8408, init=0x8408, table-driven, little-endian on wire
Baud:  38400, 8N1
Slot:  ~5ms each, 12000/epoch, 4 epochs, ~240s cycle
```

---

_This document was generated from the full project source code, protocol documentation, and implementation specifications. For the protocol wire format details, see [docs/protocol.md](protocol.md). For implementation specifics, see the [docs/implementation/](implementation/) directory._
