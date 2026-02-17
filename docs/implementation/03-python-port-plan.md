# Python Port Development Plan

## Overview

This document outlines the plan for porting TapTap from Rust to Python while maintaining 100% functional parity with the original implementation.

## Project Structure

```
taptap-python/
├── setup.py                    # Package configuration
├── requirements.txt            # Dependencies
├── README.md                   # Python-specific documentation
├── taptap/                     # Main package
│   ├── __init__.py
│   ├── barcode.py              # Device barcode encoding/decoding
│   ├── config.py               # Configuration classes
│   ├── capture.py              # GZIP capture format
│   │
│   ├── gateway/                # Gateway network stack
│   │   ├── __init__.py
│   │   ├── physical/           # Physical layer
│   │   │   ├── __init__.py
│   │   │   ├── tcp.py          # TCP connection
│   │   │   ├── serial.py       # Serial port
│   │   │   └── base.py         # Abstract base classes
│   │   ├── link/               # Link layer
│   │   │   ├── __init__.py
│   │   │   ├── address.py      # Gateway addressing
│   │   │   ├── crc.py          # CRC calculation
│   │   │   ├── escaping.py     # Byte escaping
│   │   │   └── receiver.py     # Frame receiver
│   │   └── transport/          # Transport layer
│   │       ├── __init__.py
│   │       ├── types.py        # Frame types
│   │       └── receiver.py     # Transport receiver
│   │
│   ├── pv/                     # PV network stack
│   │   ├── __init__.py
│   │   ├── physical.py         # Physical layer types
│   │   ├── link/               # Link layer
│   │   │   ├── __init__.py
│   │   │   ├── types.py        # Address types
│   │   │   └── slot_counter.py # Time synchronization
│   │   ├── network/            # Network layer
│   │   │   ├── __init__.py
│   │   │   └── types.py        # Node types, packet headers
│   │   └── application/        # Application layer
│   │       ├── __init__.py
│   │       ├── types.py        # Packet types
│   │       └── receiver.py     # Packet receiver
│   │
│   ├── observer/               # Application layer
│   │   ├── __init__.py
│   │   ├── observer.py         # Main observer
│   │   ├── event.py            # Event types
│   │   ├── node_table.py       # Device registry
│   │   ├── persistent_state.py # State persistence
│   │   └── slot_clock.py       # Slot-to-time mapping
│   │
│   └── cli/                    # Command-line interface
│       ├── __init__.py
│       └── main.py             # CLI entry point
│
└── tests/                      # Test suite
    ├── __init__.py
    ├── test_barcode.py
    ├── test_crc.py
    ├── test_escaping.py
    ├── test_slot_counter.py
    ├── test_gateway_link.py
    ├── test_gateway_transport.py
    ├── test_pv_packets.py
    ├── test_observer.py
    └── test_data/              # Recorded protocol samples
        ├── __init__.py
        └── samples.py
```

---

## Dependency Mapping

### Rust → Python Dependencies

| Rust Crate | Python Package | Purpose |
|------------|----------------|---------|
| `zerocopy` | `struct` (stdlib) | Binary struct parsing |
| `serde` + `serde_json` | `json` (stdlib) + `dataclasses` | Serialization |
| `schemars` | `jsonschema` | JSON schema validation |
| `chrono` | `datetime` (stdlib) | Timestamps |
| `flate2` | `gzip` (stdlib) | GZIP compression |
| `socket2` | `socket` (stdlib) | Socket operations |
| `libc` | `termios` (Unix) | Serial settings |
| `log` | `logging` (stdlib) | Logging |
| `thiserror` | Custom exceptions | Error types |
| `serialport` | `pyserial` | Serial port access |
| `clap` | `argparse` or `click` | CLI parsing |
| `env_logger` | `logging.basicConfig` | Log initialization |

### Python-Specific Dependencies

**requirements.txt**:
```
pyserial>=3.5          # Serial port communication
jsonschema>=4.0        # JSON schema validation
click>=8.0             # CLI framework (alternative: argparse)
pytest>=7.0            # Testing framework
pytest-cov>=4.0        # Test coverage
black>=23.0            # Code formatting
mypy>=1.0              # Type checking
```

---

## Module-by-Module Implementation Plan

### Phase 1: Core Data Structures (Week 1)

#### 1.1 Barcode (`taptap/barcode.py`)

**Complexity**: Low

**Implementation**:
```python
class Barcode:
    """Device barcode with CRC checksum"""
    
    def __init__(self, long_address: bytes):
        if len(long_address) != 8:
            raise ValueError("Address must be 8 bytes")
        self._address = long_address
    
    def __str__(self) -> str:
        """Convert to X-NNNNNNNC format"""
        # Extract leading nibble
        # Encode 7 nibbles as base-32
        # Calculate CRC
        # Return formatted string
    
    @classmethod
    def from_string(cls, s: str) -> 'Barcode':
        """Parse X-NNNNNNNC format"""
        # Validate format
        # Decode base-32
        # Verify CRC
        # Return Barcode instance
```

**Tests**:
- Known address ↔ barcode conversions
- CRC validation
- Invalid format handling

#### 1.2 Gateway Link Address (`taptap/gateway/link/address.py`)

**Complexity**: Low

**Implementation**:
```python
@dataclass(frozen=True)
class GatewayID:
    """15-bit gateway identifier"""
    value: int
    
    def __post_init__(self):
        if not (0 <= self.value <= 0x7FFF):
            raise ValueError("GatewayID must be 15-bit")

class Address:
    """Gateway link address with direction"""
    
    @staticmethod
    def to(gateway_id: GatewayID) -> 'AddressTo':
        return AddressTo(gateway_id)
    
    @staticmethod
    def from_(gateway_id: GatewayID) -> 'AddressFrom':
        return AddressFrom(gateway_id)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'Address':
        """Decode big-endian u16"""
        value = struct.unpack('>H', data)[0]
        direction = (value >> 15) & 1
        gateway_id = GatewayID(value & 0x7FFF)
        
        if direction == 0:
            return AddressTo(gateway_id)
        else:
            return AddressFrom(gateway_id)
    
    def to_bytes(self) -> bytes:
        """Encode as big-endian u16"""
        # Implemented in subclasses
```

**Tests**:
- To/From encoding
- Round-trip serialization
- Edge cases (ID 0, max ID)

#### 1.3 Slot Counter (`taptap/pv/link/slot_counter.py`)

**Complexity**: Medium

**Implementation**:
```python
from enum import IntEnum

class SlotEpoch(IntEnum):
    EPOCH_0 = 0
    EPOCH_4 = 1
    EPOCH_8 = 2
    EPOCH_C = 3
    
    def __add__(self, other: int) -> 'SlotEpoch':
        return SlotEpoch((self.value + other) % 4)

@dataclass(frozen=True)
class SlotNumber:
    """14-bit slot number (0-11999)"""
    value: int
    
    MAX = 11999
    
    def __post_init__(self):
        if not (0 <= self.value <= self.MAX):
            raise ValueError(f"Slot number must be 0-{self.MAX}")

@dataclass(frozen=True)
class SlotCounter:
    """16-bit slot counter with epoch"""
    epoch: SlotEpoch
    slot_number: SlotNumber
    
    @classmethod
    def from_u16(cls, value: int) -> 'SlotCounter':
        """Decode big-endian u16"""
        epoch_bits = (value >> 14) & 0x3
        slot_bits = value & 0x3FFF
        
        epoch = SlotEpoch(epoch_bits)
        slot_number = SlotNumber(slot_bits)
        
        return cls(epoch, slot_number)
    
    def to_u16(self) -> int:
        """Encode as u16"""
        return (self.epoch << 14) | self.slot_number.value
    
    def slots_since(self, past: 'SlotCounter') -> int:
        """Calculate slots elapsed (handles wraparound)"""
        # Handle epoch wraparound
        # Calculate slot difference
```

**Tests**:
- Epoch wrapping
- Slot overflow detection
- slots_since calculation
- Edge cases (boundary epochs)

---

### Phase 2: Gateway Stack (Week 2)

#### 2.1 CRC (`taptap/gateway/link/crc.py`)

**Implementation**:
```python
def crc_ccitt(data: bytes) -> int:
    """CRC-CCITT calculation"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc
```

**Tests**:
- Known test vectors
- Compare with Rust implementation

#### 2.2 Escaping (`taptap/gateway/link/escaping.py`)

**Implementation**:
```python
def escape(data: bytes) -> bytes:
    """Escape special sequences"""
    # Implement escaping logic
    
def unescape(data: bytes) -> Optional[bytes]:
    """Unescape, returns None if invalid"""
    # Implement unescaping logic
```

**Tests**:
- Round-trip escaping
- Invalid escape sequences

#### 2.3 Gateway Link Receiver (`taptap/gateway/link/receiver.py`)

**Complexity**: High

**Implementation**:
```python
from enum import Enum, auto
from typing import Protocol, Optional

class Sink(Protocol):
    """Callback interface for frames"""
    def feed(self, frame: 'Frame') -> None:
        ...

class State(Enum):
    IDLE = auto()
    IN_FRAME = auto()

@dataclass
class Frame:
    address: Address
    frame_type: int  # u16
    payload: bytes

class Receiver:
    """Frame assembly state machine"""
    
    def __init__(self, sink: Sink):
        self._sink = sink
        self._buffer = bytearray()
        self._state = State.IDLE
        self._current_address: Optional[Address] = None
    
    def extend(self, data: bytes) -> None:
        """Process incoming bytes"""
        for byte in data:
            self._process_byte(byte)
    
    def _process_byte(self, byte: int) -> None:
        """State machine for byte processing"""
        if self._state == State.IDLE:
            # Look for preamble
            # Transition to IN_FRAME when found
        elif self._state == State.IN_FRAME:
            # Accumulate until terminator
            # Validate CRC
            # Emit frame to sink
```

**Tests**:
- Valid frame parsing
- CRC validation
- Preamble detection
- Error recovery

#### 2.4 Gateway Transport Receiver (`taptap/gateway/transport/receiver.py`)

**Complexity**: High

**Implementation**:
```python
class TransportReceiver:
    """Transport layer message handler"""
    
    def __init__(self, sink: Sink):
        self._sink = sink
        self._rx_packet_numbers: Dict[GatewayID, Dict[int, int]] = {}
        self._command_sequences: Dict[GatewayID, int] = {}
        self._counters = Counters()
    
    def feed(self, frame: Frame) -> None:
        """Handle incoming frame"""
        if frame.frame_type == FrameType.RECEIVE_RESPONSE:
            self._handle_receive_response(frame)
        elif frame.frame_type == FrameType.COMMAND_REQUEST:
            self._handle_command_request(frame)
        # ... other frame types
    
    def _handle_receive_response(self, frame: Frame) -> None:
        """Parse batch of PV packets"""
        # Parse status and slot counter
        # Iterate through packets
        # Deduplicate by DSN
        # Emit to sink
```

**Tests**:
- Frame type dispatch
- Packet iteration
- DSN deduplication
- Sequence tracking

---

### Phase 3: PV Stack (Week 3)

#### 3.1 PV Data Types (`taptap/pv/`)

**Implementation**:
```python
# Types for addresses
class NodeID:
    """Non-zero node identifier"""
    
class NodeAddress:
    """Node address (0 = broadcast)"""

class ShortAddress:
    """802.15.4 short address"""

class LongAddress:
    """802.15.4 long address (8 bytes)"""

# Packet types
class PacketType(IntEnum):
    STRING_REQUEST = 0x06
    STRING_RESPONSE = 0x07
    TOPOLOGY_REPORT = 0x09
    # ... etc
    POWER_REPORT = 0x31

# Measurement types
class U12Pair:
    """Two 12-bit values in 3 bytes"""
    
    def __init__(self, data: bytes):
        if len(data) != 3:
            raise ValueError("U12Pair requires 3 bytes")
        self._data = data
    
    @property
    def first(self) -> int:
        """Upper 12 bits"""
        return (self._data[0] << 4) | (self._data[1] >> 4)
    
    @property
    def second(self) -> int:
        """Lower 12 bits"""
        return ((self._data[1] & 0x0F) << 8) | self._data[2]
```

#### 3.2 PV Application Receiver

**Implementation**:
```python
class PowerReport:
    """Parse PowerReport packet (13 bytes)"""
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'PowerReport':
        if len(data) != 13:
            raise ValueError("PowerReport must be 13 bytes")
        
        voltage_pair = U12Pair(data[0:3])
        duty_cycle = data[3]
        current_temp_pair = U12Pair(data[4:7])
        slot_counter = SlotCounter.from_u16(
            struct.unpack('>H', data[10:12])[0]
        )
        rssi = data[12]
        
        return cls(
            voltage_in=voltage_pair.first / 20.0,
            voltage_out=voltage_pair.second / 10.0,
            current=current_temp_pair.first / 200.0,
            temperature=temperature_from_u12(current_temp_pair.second),
            dc_dc_duty_cycle=duty_cycle / 255.0,
            slot_counter=slot_counter,
            rssi=rssi
        )

def temperature_from_u12(raw: int) -> float:
    """Convert 12-bit temperature with sign extension"""
    if raw & 0x800:  # Negative
        signed = raw | 0xF000
        return struct.unpack('>h', struct.pack('>H', signed))[0] / 10.0
    else:
        return raw / 10.0
```

**Tests**:
- Binary parsing
- Value scaling
- Temperature sign extension

---

### Phase 4: Observer & State Management (Week 4)

#### 4.1 Slot Clock (`taptap/observer/slot_clock.py`)

**Implementation**:
```python
from datetime import datetime, timedelta

class SlotClock:
    """Map slot counters to wall-clock time"""
    
    def __init__(self):
        self._reference_slot: Optional[SlotCounter] = None
        self._reference_time: Optional[datetime] = None
    
    def update(self, slot: SlotCounter, time: datetime) -> None:
        """Update reference point"""
        self._reference_slot = slot
        self._reference_time = time
    
    def to_datetime(self, slot: SlotCounter) -> Optional[datetime]:
        """Convert slot counter to datetime"""
        if not self._reference_slot or not self._reference_time:
            return None
        
        try:
            slots_elapsed = slot.slots_since(self._reference_slot)
            delta = timedelta(milliseconds=slots_elapsed * 4.29)
            return self._reference_time + delta
        except ValueError:
            return None
```

#### 4.2 Observer (`taptap/observer/observer.py`)

**Implementation**:
```python
class Observer:
    """Main observation orchestrator"""
    
    def __init__(self, state_file: Optional[Path] = None):
        self._state = PersistentState.load(state_file) if state_file else PersistentState()
        self._state_file = state_file
        self._slot_clock = SlotClock()
        self._node_tables: Dict[GatewayID, NodeTable] = {}
    
    def feed(self, message: TransportMessage) -> None:
        """Handle transport message"""
        if isinstance(message, ReceiveResponse):
            for packet in message.packets:
                self._handle_packet(message.gateway_id, packet)
        elif isinstance(message, IdentifyResponse):
            self._handle_identify(message.gateway_id, message.long_address)
        # ... other message types
    
    def _handle_packet(self, gateway_id: GatewayID, packet: ReceivedPacket) -> None:
        """Dispatch packet by type"""
        if packet.header.packet_type == PacketType.POWER_REPORT:
            self._handle_power_report(gateway_id, packet)
        elif packet.header.packet_type == PacketType.NODE_TABLE_RESPONSE:
            self._handle_node_table(gateway_id, packet)
        # ... other packet types
    
    def _handle_power_report(self, gateway_id: GatewayID, packet: ReceivedPacket) -> None:
        """Process power report"""
        report = PowerReport.from_bytes(packet.data)
        
        # Update slot clock
        now = datetime.now()
        self._slot_clock.update(report.slot_counter, now)
        
        # Convert to event
        timestamp = self._slot_clock.to_datetime(report.slot_counter) or now
        
        event = PowerReportEvent(
            gateway=gateway_id,
            node=packet.header.node_address.to_node_id(),
            timestamp=timestamp,
            voltage_in=report.voltage_in,
            voltage_out=report.voltage_out,
            current=report.current,
            dc_dc_duty_cycle=report.dc_dc_duty_cycle,
            temperature=report.temperature,
            rssi=report.rssi
        )
        
        # Emit JSON
        print(json.dumps(dataclasses.asdict(event), default=str))
```

#### 4.3 Persistent State (`taptap/observer/persistent_state.py`)

**Implementation**:
```python
@dataclass
class PersistentState:
    gateway_identities: Dict[GatewayID, LongAddress] = field(default_factory=dict)
    gateway_versions: Dict[GatewayID, str] = field(default_factory=dict)
    gateway_node_tables: Dict[GatewayID, NodeTable] = field(default_factory=dict)
    
    @classmethod
    def load(cls, path: Path) -> 'PersistentState':
        """Load from JSON file"""
        if not path.exists():
            return cls()
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Deserialize from JSON
        return cls(...)
    
    def save(self, path: Path) -> None:
        """Save to JSON file (atomic)"""
        temp_path = path.with_suffix('.tmp')
        
        with open(temp_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        
        temp_path.replace(path)  # Atomic on POSIX
```

---

### Phase 5: Physical Layer & CLI (Week 5)

#### 5.1 Serial Port (`taptap/gateway/physical/serial.py`)

**Implementation**:
```python
import serial

class SerialSource:
    """Serial port data source"""
    
    def __init__(self, port: str, baud_rate: int = 9600):
        self._serial = serial.Serial(
            port=port,
            baudrate=baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
    
    def read(self, size: int = 1024) -> bytes:
        """Read bytes from serial port"""
        return self._serial.read(size)
    
    def close(self) -> None:
        self._serial.close()
```

#### 5.2 TCP Source (`taptap/gateway/physical/tcp.py`)

**Implementation**:
```python
import socket

class TcpSource:
    """TCP data source with reconnection"""
    
    def __init__(self, host: str, port: int = 502, 
                 reconnect_timeout: float = 0,
                 reconnect_delay: float = 5):
        self._host = host
        self._port = port
        self._socket: Optional[socket.socket] = None
        self._reconnect_timeout = reconnect_timeout
        self._reconnect_delay = reconnect_delay
        self._connect()
    
    def _connect(self) -> None:
        """Establish TCP connection with keepalive"""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        # Platform-specific TCP keepalive settings
        if hasattr(socket, 'TCP_KEEPIDLE'):
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        
        self._socket.connect((self._host, self._port))
    
    def read(self, size: int = 1024) -> bytes:
        """Read bytes with auto-reconnect"""
        try:
            return self._socket.recv(size)
        except (ConnectionResetError, BrokenPipeError):
            self._reconnect()
            return b''
```

#### 5.3 CLI (`taptap/cli/main.py`)

**Implementation**:
```python
import click

@click.group()
@click.version_option()
def cli():
    """TapTap: Tigo TAP protocol observer"""
    pass

@cli.command()
@click.option('--serial', help='Serial port (e.g., /dev/ttyUSB0)')
@click.option('--tcp', help='TCP host')
@click.option('--port', default=502, help='TCP port')
@click.option('--state-file', type=click.Path(), help='Persistent state JSON file')
def observe(serial, tcp, port, state_file):
    """Observe the system and emit events"""
    
    # Create physical source
    if serial:
        source = SerialSource(serial)
    elif tcp:
        source = TcpSource(tcp, port)
    else:
        raise click.UsageError("Must specify --serial or --tcp")
    
    # Build receiver stack
    observer = Observer(Path(state_file) if state_file else None)
    transport_rx = TransportReceiver(observer)
    link_rx = LinkReceiver(transport_rx)
    
    # Main loop
    try:
        while True:
            data = source.read()
            if data:
                link_rx.extend(data)
    except KeyboardInterrupt:
        pass
    finally:
        source.close()

@cli.command()
def list_serial_ports():
    """List available serial ports"""
    from serial.tools import list_ports
    for port in list_ports.comports():
        click.echo(f"{port.device}: {port.description}")

if __name__ == '__main__':
    cli()
```

---

### Phase 6: Testing (Week 6)

#### Test Structure

```python
# tests/test_barcode.py
import pytest
from taptap.barcode import Barcode

def test_barcode_encoding():
    address = bytes.fromhex('04C05B409A57A23E')
    barcode = Barcode(address)
    assert str(barcode) == '4-9A57A2L'

def test_barcode_decoding():
    barcode = Barcode.from_string('4-9A57A2L')
    assert barcode.address.hex().upper() == '04C05B409A57A23E'

def test_barcode_crc_validation():
    with pytest.raises(ValueError):
        Barcode.from_string('4-9A57A2X')  # Wrong CRC

# tests/test_gateway_link.py
def test_frame_parsing():
    # Load test data from Rust codebase
    frame_bytes = load_test_data('receive_response.bin')
    
    received_frames = []
    receiver = LinkReceiver(FrameCollector(received_frames))
    receiver.extend(frame_bytes)
    
    assert len(received_frames) == 1
    assert received_frames[0].frame_type == FrameType.RECEIVE_RESPONSE

# tests/test_observer.py
def test_power_report_event():
    observer = Observer()
    
    # Simulate power report packet
    packet = create_test_power_report()
    observer.feed(packet)
    
    # Verify event emission
    # (Would need to capture stdout or use mock)
```

#### Test Data Migration

- Copy `src/test_data.rs` binary samples to Python
- Convert to `.bin` files or Python byte constants
- Ensure identical test vectors

---

## Implementation Strategy

### Development Phases

1. **Week 1**: Core data structures + basic serialization
2. **Week 2**: Gateway link + transport layers
3. **Week 3**: PV network + application layers
4. **Week 4**: Observer + state management
5. **Week 5**: Physical layer + CLI
6. **Week 6**: Testing + documentation

### Testing Approach

**Unit Tests**:
- Each module has corresponding test file
- Test pure functions in isolation
- Use pytest fixtures for common setups

**Integration Tests**:
- Use recorded protocol traces from Rust version
- Validate identical output for same input
- Test full stack: bytes → events

**Cross-Validation**:
- Run both Rust and Python versions on same input
- Compare JSON output line-by-line
- Ensure bit-identical binary parsing

### Code Quality

**Type Hints**:
```python
from typing import Optional, List, Dict
from dataclasses import dataclass

def process_frame(frame: Frame) -> Optional[List[Event]]:
    ...
```

**Mypy Configuration** (mypy.ini):
```ini
[mypy]
python_version = 3.9
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
```

**Black Formatting**:
```bash
black --line-length 100 taptap/
```

**Docstrings**:
```python
def crc_ccitt(data: bytes) -> int:
    """Calculate CRC-CCITT checksum.
    
    Args:
        data: Input bytes
        
    Returns:
        16-bit CRC value
        
    Example:
        >>> crc_ccitt(b'123456789')
        10673
    """
```

---

## Performance Considerations

### Optimization Strategies

1. **Use `struct.unpack_from`** instead of slicing for binary parsing
2. **Cache property calculations** where appropriate
3. **Use `__slots__`** for frequently-allocated classes
4. **Avoid unnecessary copies** with `memoryview`
5. **Profile hot paths** with `cProfile`

### Example Optimizations

```python
# Instead of:
value = struct.unpack('>H', data[10:12])[0]

# Use:
value = struct.unpack_from('>H', data, 10)[0]

# For frequent allocations:
@dataclass
class SlotCounter:
    __slots__ = ['epoch', 'slot_number']
    epoch: SlotEpoch
    slot_number: SlotNumber
```

---

## Documentation

### README.md Structure

```markdown
# TapTap Python

Python port of the TapTap Tigo TAP protocol implementation.

## Installation

```bash
pip install taptap
```

## Usage

```bash
# Observe via TCP
taptap observe --tcp 192.168.1.100

# Observe via serial port
taptap observe --serial /dev/ttyUSB0

# With state persistence
taptap observe --tcp 192.168.1.100 --state-file taptap.json
```

## API Usage

```python
from taptap import Observer, TcpSource, LinkReceiver, TransportReceiver

source = TcpSource('192.168.1.100')
observer = Observer()
transport_rx = TransportReceiver(observer)
link_rx = LinkReceiver(transport_rx)

while True:
    data = source.read()
    link_rx.extend(data)
```

## Development

```bash
# Install dev dependencies
pip install -e '.[dev]'

# Run tests
pytest

# Type check
mypy taptap/

# Format code
black taptap/
```
```

---

## Completion Criteria

### Functional Parity Checklist

- [ ] All data structures implemented
- [ ] Binary parsing matches Rust byte-for-byte
- [ ] CRC calculation identical
- [ ] Frame escaping/unescaping identical
- [ ] All packet types supported
- [ ] Observer emits identical JSON events
- [ ] Persistent state format compatible
- [ ] CLI has all subcommands (observe, peek-*, list-serial-ports)
- [ ] Serial and TCP sources work
- [ ] Tests achieve >90% code coverage
- [ ] Documentation complete

### Validation Tests

```bash
# Run Rust version
cargo run --release -- observe --tcp HOST > rust_output.json

# Run Python version
taptap observe --tcp HOST > python_output.json

# Compare outputs
diff rust_output.json python_output.json
# Should be identical except for timestamps
```

---

## Future Enhancements

Once core parity is achieved:

1. **Python-specific features**:
   - Async/await support (asyncio)
   - Type stubs (`.pyi` files)
   - Dataclass JSON schema generation

2. **Additional tooling**:
   - MQTT bridge (Python version)
   - InfluxDB sink
   - Prometheus exporter
   - Web dashboard (Flask/FastAPI)

3. **Performance**:
   - Cython for hot paths
   - NumPy for batch processing
   - Multiprocessing for parallel gateways
