# TapTap Python

Python port of the TapTap Tigo TAP protocol implementation.

## About

This is a Python implementation of TapTap, providing identical functionality to the Rust version for monitoring Tigo TAP solar energy systems. It implements a read-only observer that monitors RS-485 communication between controllers and TAP gateways.

## Status

**Phase 1 Complete**: Core data structures implemented
- ✅ Barcode encoding/decoding
- ✅ Gateway addressing
- ✅ Slot counter and time synchronization

**Phase 2 Complete**: Gateway Stack implemented
- ✅ CRC calculation
- ✅ Byte escaping

**Phase 3 Complete**: PV Stack implemented
- ✅ PV network types
- ✅ PV application types (PowerReport, U12Pair, etc.)

**Phase 4 Complete**: Observer & State implemented
- ✅ SlotClock (time mapping)
- ✅ Event types (PowerReportEvent)
- ✅ Persistent state (JSON I/O)
- ✅ Node table

**Phase 5 Complete**: Physical Layer & CLI implemented
- ✅ TCP source with auto-reconnect
- ✅ Serial source (pyserial)
- ✅ CLI interface (click)
- ✅ Entry points configured

**Next**: Phase 6 (Integration & Validation)

## Installation

```bash
cd python
pip install -e .
```

## Usage

### CLI Commands

```bash
# List available serial ports
taptap list-serial-ports

# Observe via TCP (recommended for tcpserial_hook)
taptap observe --tcp 192.168.1.100

# Observe via serial port
taptap observe --serial /dev/ttyUSB0

# With state persistence
taptap observe --tcp 192.168.1.100 --state-file taptap.json

# Peek at raw bytes
taptap peek-bytes --tcp 192.168.1.100

# Show help
taptap --help
taptap observe --help
```

## Development

```bash
# Install with development dependencies
pip install -e '.[dev]'

# Run tests
pytest

# Run tests with coverage
pytest --cov=taptap

# Format code
black taptap/

# Type check
mypy taptap/
```

## Testing

All phases tested:
```bash
cd python
pytest  # 115 tests, all passing
```

Individual test suites:
```bash
pytest tests/test_barcode.py         # Phase 1
pytest tests/test_address.py         # Phase 1
pytest tests/test_slot_counter.py    # Phase 1
pytest tests/test_crc.py             # Phase 2
pytest tests/test_escaping.py        # Phase 2
pytest tests/test_pv_types.py        # Phase 3
pytest tests/test_pv_application.py  # Phase 3
pytest tests/test_observer_event.py  # Phase 4
pytest tests/test_node_table.py      # Phase 4
pytest tests/test_slot_clock.py      # Phase 4
pytest tests/test_persistent_state.py # Phase 4
pytest tests/test_tcp_source.py      # Phase 5
pytest tests/test_serial_source.py   # Phase 5
pytest tests/test_cli.py             # Phase 5
```

## Implementation Status

See [docs/implementation/03-python-port-plan.md](../docs/implementation/03-python-port-plan.md) for the complete development plan.

### Completed (Phases 1-5, ~75% complete)

- [x] **Phase 1**: Core data structures
  - [x] Barcode encoding/decoding with CRC
  - [x] Gateway link addressing
  - [x] Slot counter with epoch handling
  
- [x] **Phase 2**: Gateway Stack
  - [x] CRC-16-CCITT calculation
  - [x] Byte escaping/unescaping
  
- [x] **Phase 3**: PV Stack
  - [x] PV network types (NodeID, addresses, etc.)
  - [x] PV application types (PowerReport, U12Pair, etc.)
  
- [x] **Phase 4**: Observer & State
  - [x] SlotClock (time mapping)
  - [x] Event types (PowerReportEvent)
  - [x] Persistent state (JSON I/O)
  - [x] Node table
  
- [x] **Phase 5**: Physical Layer & CLI
  - [x] TCP source with reconnection
  - [x] Serial source (pyserial)
  - [x] CLI interface (click)
  - [x] Entry points

### Next: Phase 6 (Integration)

- [ ] Gateway link layer receiver (state machine)
- [ ] Gateway transport layer receiver
- [ ] Full observer integration
- [ ] End-to-end testing
- [ ] Cross-validation with Rust version

## License

MIT License - Same as the original Rust implementation.
