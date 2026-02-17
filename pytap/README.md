# pytap

Simplified TapTap protocol parser for Tigo TAP solar monitoring systems.

Passively monitors the RS-485 bus between a Tigo Cloud Connect Advanced (CCA) gateway and its TAP controller, parsing frames into structured events (power reports, infrastructure discovery, topology, diagnostics).

## Requirements

- Python 3.10+
- No dependencies for core library usage

## Installation

```bash
cd pytap

# Core only (no dependencies)
pip install -e .

# With CLI support
pip install -e ".[cli]"

# With serial port support
pip install -e ".[serial]"

# With everything (CLI + serial + dev tools)
pip install -e ".[cli,serial,dev]"
```

## Quick Start

### CLI — Stream Events from a Live Gateway

Connect via TCP (e.g., to a ser2net or TCP-serial bridge):

```bash
pytap observe --tcp 192.168.1.100 --port 502
```

Connect via serial port:

```bash
pytap observe --serial /dev/ttyUSB0       # Linux
pytap observe --serial COM3               # Windows
```

Events are printed as one JSON object per line:

```json
{"event_type": "power_report", "timestamp": "2026-02-17T12:00:00", "gateway_id": 1, "node_id": 5, "barcode": "3-2BE16Y", "voltage_in": 40.0, "voltage_out": 40.0, "current": 2.5, "power": 100.0, "temperature": 25.0, "dc_dc_duty_cycle": 0.5, "rssi": 128}
{"event_type": "infrastructure", "timestamp": "2026-02-17T12:00:01", "gateways": {"1": {"address": "04:C0:5B:30:00:02:BE:16", "version": "Mgate Version G8.59"}}, "nodes": {}}
```

### CLI — Other Commands

```bash
# Show version
pytap --version

# View raw hex bytes from the bus
pytap peek-bytes --tcp 192.168.1.100

# List available serial ports
pytap list-serial-ports
```

### CLI Options

```
pytap observe [OPTIONS]

  --tcp TEXT                 TCP host (e.g. 192.168.1.100)
  --port INTEGER             TCP port (default: 502)
  --serial TEXT              Serial port (e.g. /dev/ttyUSB0, COM3)
  --state-file PATH          Persistent state file (JSON)
  --reconnect-timeout INT    Seconds of silence before reconnecting (default: 60, 0=disabled)
  --reconnect-retries INT    Max reconnect attempts (default: 0 = infinite)
  --reconnect-delay INT      Seconds between retries (default: 5)
```

## Library Usage

### Parse a Captured Byte Buffer

```python
import pytap

events = pytap.parse_bytes(raw_bytes)
for event in events:
    print(event.event_type, event.to_dict())
```

### Streaming with a Parser

```python
import pytap

parser = pytap.create_parser(state_file="state.json")

source = pytap.connect({"tcp": "192.168.1.100", "port": 502})
try:
    while True:
        data = source.read(1024)
        if data:
            for event in parser.feed(data):
                print(event.to_dict())
finally:
    source.close()
```

### Streaming with a Callback

```python
import pytap

def on_event(event):
    if event.event_type == "power_report":
        print(f"Node {event.node_id}: {event.power}W")

pytap.observe(
    source_config={"tcp": "192.168.1.100", "port": 502},
    callback=on_event,
    state_file="state.json",
)
```

### Barcode Utilities

```python
from pytap import encode_barcode, decode_barcode

barcode = encode_barcode(bytes([0x04, 0xC0, 0x5B, 0x30, 0x00, 0x02, 0xBE, 0x16]))
print(barcode)  # e.g. "3-2BE16Y"

address = decode_barcode(barcode)
print(address.hex(':'))  # "04:c0:5b:30:00:02:be:16"
```

## Event Types

| Type | `event_type` | Description |
|------|-------------|-------------|
| `PowerReportEvent` | `power_report` | Solar optimizer voltage, current, power, temperature |
| `InfrastructureEvent` | `infrastructure` | Gateway/node discovery (addresses, versions, barcodes) |
| `TopologyEvent` | `topology` | Mesh network topology report |
| `StringEvent` | `string` | Diagnostic string request/response |

## Running Tests

```bash
pip install -e ".[dev]"
pytest pytap/tests/ -v
```

## Project Structure

```
pytap/
├── __init__.py        # Public API re-exports
├── api.py             # Top-level functions: create_parser, parse_bytes, observe, connect
├── setup.py           # Package setup
├── core/
│   ├── barcode.py     # Tigo barcode encode/decode
│   ├── crc.py         # CRC-16-CCITT calculation
│   ├── events.py      # Event dataclasses (PowerReportEvent, etc.)
│   ├── parser.py      # Core protocol parser (frame → event pipeline)
│   ├── source.py      # TcpSource, SerialSource (byte providers)
│   ├── state.py       # SlotClock, NodeTableBuilder, PersistentState
│   └── types.py       # Protocol types (GatewayID, Frame, PowerReport, etc.)
├── cli/
│   └── main.py        # Click CLI (thin wrapper over pytap.api)
└── tests/
    ├── test_api.py
    ├── test_barcode.py
    ├── test_crc.py
    ├── test_parser.py
    └── test_types.py
```
