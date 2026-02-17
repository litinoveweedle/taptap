# pytap — Simplified TapTap Python Port

## Purpose

`pytap` is a simplified, flat-architecture Python implementation of the TapTap protocol for passive monitoring of Tigo TAP solar energy systems. Unlike the layered `python/taptap` port (which mirrors the Rust crate's sink-chain design), `pytap` collapses the entire protocol stack into a single-pass pipeline that converts raw bytes directly into final parsed events.

The primary design goal is **ease of integration**: the full parsing functionality lives in a library module that can be called programmatically, with the CLI being a thin, replaceable wrapper.

## Comparison with `python/taptap`

| Aspect | `python/taptap` | `pytap` |
|--------|-----------------|---------|
| Architecture | Layered sink-chain (5 layers, 3 Sink protocols) | Flat pipeline, single `Parser` class |
| Module count | ~25 files across 8 packages | ~8 files in 3 packages |
| Integration | Requires wiring 4 receivers + observer | Single `pytap.parse(source)` call |
| Extensibility | Add new Sink implementations | Subclass or compose `Parser` |
| CLI coupling | Click commands directly build pipeline | CLI imports and calls `pytap.api` |
| Output | JSON to stdout only | Returns Python objects; CLI serializes |

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  CLI  (pytap.cli)                                   │
│  Thin wrapper: argument parsing, I/O, JSON output   │
│  Replaceable with any caller of pytap.api           │
└──────────────────────┬──────────────────────────────┘
                       │ calls
                       ▼
┌─────────────────────────────────────────────────────┐
│  Public API  (pytap.api)                            │
│                                                     │
│  connect(source_config) → Connection                │
│  parse_bytes(data) → list[Event]                    │
│  observe(source_config, callback) → None            │
│  create_parser() → Parser                           │
└──────────────────────┬──────────────────────────────┘
                       │ uses
                       ▼
┌─────────────────────────────────────────────────────┐
│  Core  (pytap.core)                                 │
│                                                     │
│  ┌───────────────────────────────────────────┐      │
│  │  Parser                                   │      │
│  │  Single class implementing the full       │      │
│  │  byte → event pipeline:                   │      │
│  │                                           │      │
│  │  raw bytes                                │      │
│  │    → frame detection (preamble/terminator)│      │
│  │    → unescaping                           │      │
│  │    → CRC validation                       │      │
│  │    → frame type dispatch                  │      │
│  │    → transport interpretation             │      │
│  │    → PV packet extraction                 │      │
│  │    → application-level parsing            │      │
│  │    → Event objects                        │      │
│  └───────────────────────────────────────────┘      │
│                                                     │
│  ┌───────────────────────────────────────────┐      │
│  │  Types & Protocol Constants               │      │
│  │  Frame, GatewayID, NodeID, LongAddress,   │      │
│  │  SlotCounter, PacketType, PowerReport,    │      │
│  │  Barcode, etc.                            │      │
│  └───────────────────────────────────────────┘      │
│                                                     │
│  ┌───────────────────────────────────────────┐      │
│  │  Events                                   │      │
│  │  PowerReportEvent, InfrastructureEvent,   │      │
│  │  TopologyEvent, StringEvent               │      │
│  └───────────────────────────────────────────┘      │
│                                                     │
│  ┌───────────────────────────────────────────┐      │
│  │  Source                                   │      │
│  │  SerialSource, TcpSource                  │      │
│  │  (byte providers, no protocol knowledge)  │      │
│  └───────────────────────────────────────────┘      │
│                                                     │
│  ┌───────────────────────────────────────────┐      │
│  │  State                                    │      │
│  │  SlotClock, NodeTable, PersistentState    │      │
│  │  (internal to Parser, not part of API)    │      │
│  └───────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────┘
```

## Module Layout

```
pytap/
├── __init__.py              # Package root, re-exports pytap.api
├── api.py                   # Public API functions
├── core/
│   ├── __init__.py          # Exports Parser, types, events
│   ├── types.py             # All protocol types (flat, no layering)
│   ├── events.py            # Event dataclasses
│   ├── parser.py            # The single Parser class
│   ├── source.py            # SerialSource, TcpSource
│   ├── state.py             # SlotClock, NodeTable, PersistentState
│   ├── crc.py               # CRC-16-CCITT calculation
│   └── barcode.py           # Tigo barcode encoding/decoding
├── cli/
│   ├── __init__.py
│   └── main.py              # Click CLI (thin wrapper)
├── docs/
│   ├── architecture.md      # This file
│   └── api_reference.md     # Public API documentation
└── tests/
    ├── __init__.py
    ├── test_parser.py        # End-to-end parser tests
    ├── test_types.py         # Type construction/validation tests
    ├── test_crc.py           # CRC calculation tests
    ├── test_barcode.py       # Barcode encode/decode tests
    └── test_api.py           # Public API tests
```

## Data Flow

The entire protocol stack is collapsed into `Parser.feed(data: bytes) -> list[Event]`:

```
                    Parser.feed(bytes)
                          │
              ┌───────────┴────────────┐
              │   Frame Accumulator    │
              │   (state machine)      │
              │                        │
              │   States:              │
              │   IDLE → FRAME →       │
              │   complete frame bytes │
              └───────────┬────────────┘
                          │ raw frame bytes
              ┌───────────┴────────────┐
              │   Frame Decoder        │
              │                        │
              │   1. Unescape bytes    │
              │   2. Validate CRC      │
              │   3. Parse address,    │
              │      frame_type,       │
              │      payload           │
              └───────────┬────────────┘
                          │ Frame(gateway_id, type, payload)
              ┌───────────┴────────────┐
              │   Frame Dispatcher     │
              │                        │
              │   Routes by frame_type │
              │   to handler methods:  │
              │                        │
              │   RECEIVE_REQUEST/     │
              │   RECEIVE_RESPONSE     │
              │     → _handle_receive  │
              │                        │
              │   COMMAND_REQUEST/     │
              │   COMMAND_RESPONSE     │
              │     → _handle_command  │
              │                        │
              │   ENUMERATE_*          │
              │     → _handle_enum     │
              │                        │
              │   PING/PONG/other      │
              │     → _handle_misc     │
              └───────────┬────────────┘
                          │ extracted packet data
              ┌───────────┴────────────┐
              │   Packet Parser        │
              │                        │
              │   By PacketType:       │
              │   POWER_REPORT →       │
              │     PowerReportEvent   │
              │   NODE_TABLE_RESPONSE →│
              │     InfrastructureEvent│
              │   TOPOLOGY_REPORT →    │
              │     TopologyEvent      │
              │   STRING_* →           │
              │     StringEvent        │
              └───────────┬────────────┘
                          │
                     list[Event]
```

## Key Design Decisions

### 1. Single `Parser` Class

Instead of 4 separate Receiver classes connected by Sink protocols, `pytap` uses one `Parser` that owns the full state machine. This eliminates:
- 3 abstract Sink protocol definitions
- forwarding boilerplate (the existing `ApplicationReceiver` forwards 8 transport methods untouched)
- the need to wire receivers together manually

Internal methods are organized by concern (`_accumulate_frame`, `_decode_frame`, `_dispatch_frame`, `_parse_packet`) but are private — callers only see `feed()`.

### 2. Events as Return Values, Not Side Effects

The existing port calls `print(json.dumps(event))` from deep inside the Observer. `pytap` instead **returns** event objects from `Parser.feed()`, giving the caller full control over output format, filtering, buffering, and routing.

This is the key enabler for non-CLI usage (library calls, MQTT bridges, databases, web UIs).

### 3. Flat Type Module

All protocol types (`GatewayID`, `NodeID`, `LongAddress`, `SlotCounter`, `PacketType`, `Frame`, `PowerReport`, etc.) live in a single `types.py` instead of being scattered across `gateway.link.address`, `pv.network.types`, `pv.link.slot_counter`, `pv.application.types`, etc.

This means users import `from pytap.core.types import GatewayID` rather than needing to know which protocol layer a type belongs to.

### 4. CLI as Thin Wrapper

The CLI module only handles:
- Argument parsing (click)
- Source construction (serial/TCP config)
- JSON serialization of events to stdout
- Reconnection loop with retry logic

All protocol logic lives in `pytap.core` and `pytap.api`, making it trivial to replace the CLI with a function call:

```python
# CLI usage
# $ pytap observe --tcp 192.168.1.100

# Equivalent programmatic usage
from pytap.api import observe

def my_callback(event):
    store_in_database(event)

observe(
    source_config={"tcp": "192.168.1.100", "port": 502},
    callback=my_callback
)
```

Or for finer control:

```python
from pytap.api import create_parser

parser = create_parser()
events = parser.feed(raw_bytes)
for event in events:
    process(event)
```

### 5. State Management Inside Parser

`SlotClock`, `NodeTable`, and enumeration state are internal to `Parser`. Persistent state (optional) is configured at `Parser` construction time. The caller doesn't need to manage or understand these.

## Public API Surface

### `pytap.api`

```python
def create_parser(state_file: str | Path | None = None) -> Parser:
    """Create a new protocol parser.
    
    Args:
        state_file: Optional path for persistent infrastructure state.
        
    Returns:
        A Parser instance ready to receive bytes via feed().
    """

def parse_bytes(data: bytes, state_file: str | Path | None = None) -> list[Event]:
    """One-shot parse: create a parser, feed bytes, return events.
    
    Convenience for non-streaming use (e.g., parsing captured files).
    """

def observe(
    source_config: dict,
    callback: Callable[[Event], None],
    state_file: str | Path | None = None,
    reconnect_timeout: int = 60,
    reconnect_retries: int = 0,
    reconnect_delay: int = 5,
) -> None:
    """Connect to a source and stream parsed events to callback.
    
    Runs a blocking read loop with auto-reconnection.
    
    Args:
        source_config: {"tcp": "host", "port": 502} or {"serial": "/dev/ttyUSB0"}
        callback: Called with each Event as it is parsed.
        state_file: Optional persistent state file path.
        reconnect_timeout: Seconds of silence before reconnecting (0=disabled).
        reconnect_retries: Max reconnection attempts (0=infinite).
        reconnect_delay: Seconds between reconnect attempts.
    """

def connect(source_config: dict) -> Source:
    """Create and open a byte source (serial or TCP).
    
    Returns a Source with a read() method for manual feeding into a Parser.
    """
```

### `pytap.core.Parser`

```python
class Parser:
    def __init__(self, state_file: str | Path | None = None):
        """Initialize parser with optional persistent state."""
    
    def feed(self, data: bytes) -> list[Event]:
        """Feed raw bytes and return any events parsed from them.
        
        Can be called incrementally — the parser maintains internal state
        across calls for partial frames.
        """
    
    @property
    def infrastructure(self) -> dict:
        """Current known infrastructure: gateways, nodes, barcodes."""
    
    @property
    def counters(self) -> dict:
        """Parse statistics: frames, CRC errors, runts, etc."""
```

### `pytap.core.events`

```python
@dataclass
class Event:
    """Base event — all events have a type and timestamp."""
    event_type: str
    timestamp: datetime

@dataclass
class PowerReportEvent(Event):
    """Solar optimizer power measurement."""
    gateway_id: int
    node_id: int
    barcode: str | None
    voltage_in: float       # Volts
    voltage_out: float      # Volts
    current: float          # Amps
    power: float            # Watts (voltage_out * current)
    temperature: float      # °C
    dc_dc_duty_cycle: float # 0.0–1.0
    rssi: int               # Signal strength

@dataclass
class InfrastructureEvent(Event):
    """Infrastructure state change (gateway/node discovery)."""
    gateways: dict[int, GatewayInfo]
    nodes: dict[int, NodeInfo]

@dataclass
class TopologyEvent(Event):
    """Mesh network topology report from a node."""
    gateway_id: int
    node_id: int
    parent_address: int
    neighbors: list[int]

@dataclass
class StringEvent(Event):
    """String request/response (diagnostic commands)."""
    gateway_id: int
    node_id: int
    direction: str  # "request" | "response"
    content: str
```

## Implementation Plan

### Phase 1 — Core Types & CRC (foundation)
- [ ] `pytap/core/types.py` — All protocol types as dataclasses/NamedTuples
- [ ] `pytap/core/crc.py` — CRC-16-CCITT (port from `python/taptap`)  
- [ ] `pytap/core/barcode.py` — Barcode encode/decode
- [ ] Tests for types, CRC, barcode

### Phase 2 — Parser (the big piece)
- [ ] `pytap/core/parser.py` — Frame accumulator state machine
- [ ] Frame decoding (unescape + CRC + parse)
- [ ] Frame dispatch (route by frame type)
- [ ] Transport-level handling (receive, command correlation, enumeration)
- [ ] PV packet extraction and parsing
- [ ] Event generation (PowerReport, Infrastructure, Topology, String)
- [ ] Tests with captured test data

### Phase 3 — State Management
- [ ] `pytap/core/state.py` — SlotClock, NodeTable, PersistentState
- [ ] Integration into Parser
- [ ] State persistence tests

### Phase 4 — Events & API
- [ ] `pytap/core/events.py` — Event dataclasses with JSON serialization
- [ ] `pytap/api.py` — Public API functions
- [ ] `pytap/__init__.py` — Package exports
- [ ] API tests

### Phase 5 — Sources & CLI
- [ ] `pytap/core/source.py` — SerialSource, TcpSource
- [ ] `pytap/cli/main.py` — Click CLI
- [ ] End-to-end integration tests

### Phase 6 — Documentation & Polish
- [ ] `pytap/docs/api_reference.md`
- [ ] README.md
- [ ] Type hints, docstrings, logging
- [ ] Edge case tests (CRC errors, truncated frames, epoch wraparound)

## Testing Strategy

Tests reuse captured protocol data from the Rust implementation (`src/test_data.rs`) to validate byte-level correctness. Each phase includes tests:

1. **Unit**: CRC values, barcode encoding, type construction  
2. **Parser**: Feed known byte sequences, assert expected events  
3. **Integration**: Full `observe()` with recorded data, assert JSON output  
4. **Regression**: Edge cases from `python/taptap` test suite

## Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| `pyserial` | Serial port access | Optional (serial sources only) |
| `click` | CLI argument parsing | Optional (CLI only) |
| `dataclasses-json` | JSON serialization of events | Yes |

Zero required dependencies for the core parser — it uses only the Python standard library.
