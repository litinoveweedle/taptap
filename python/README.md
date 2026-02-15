# TapTap Python

Python port of the TapTap Tigo TAP protocol implementation.

## About

This is a Python implementation of TapTap, providing identical functionality to the Rust version for monitoring Tigo TAP solar energy systems. It implements a read-only observer that monitors RS-485 communication between controllers and TAP gateways.

## Status

**Phase 1 Complete**: Core data structures implemented
- ✅ Barcode encoding/decoding
- ✅ Gateway addressing
- ✅ Slot counter and time synchronization

**In Progress**: Gateway and PV protocol stacks

## Installation

```bash
cd python
pip install -e .
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

Phase 1 tests:
```bash
cd python
pytest tests/test_barcode.py
pytest tests/test_address.py
pytest tests/test_slot_counter.py
```

## Implementation Status

See [docs/implementation/03-python-port-plan.md](../docs/implementation/03-python-port-plan.md) for the complete development plan.

### Completed

- [x] Project structure
- [x] Barcode encoding/decoding with CRC
- [x] Gateway link addressing
- [x] Slot counter with epoch handling
- [x] Basic test suite

### Next Steps

- [ ] Gateway CRC calculation
- [ ] Gateway byte escaping
- [ ] Gateway link layer receiver
- [ ] Gateway transport layer
- [ ] PV network types
- [ ] PV application layer
- [ ] Observer implementation
- [ ] CLI interface

## License

MIT License - Same as the original Rust implementation.
