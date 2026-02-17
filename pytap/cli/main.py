"""pytap command-line interface."""

import json
import logging
import sys

try:
    import click
except ImportError:
    print(
        "CLI requires 'click' package. Install with: pip install pytap[cli]",
        file=sys.stderr,
    )
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
@click.option('--serial', 'serial_port', help='Serial port (e.g. /dev/ttyUSB0, COM3)')
@click.option('--state-file', default=None, type=click.Path(), help='Persistent state file')
@click.option('--reconnect-timeout', default=60, type=int, help='Silence timeout (seconds)')
@click.option('--reconnect-retries', default=0, type=int, help='Max retries (0=infinite)')
@click.option('--reconnect-delay', default=5, type=int, help='Delay between retries (seconds)')
def observe(tcp, port, serial_port, state_file, reconnect_timeout,
            reconnect_retries, reconnect_delay):
    """Stream parsed events as JSON (one object per line)."""
    if not tcp and not serial_port:
        click.echo("Error: --tcp or --serial is required", err=True)
        sys.exit(1)

    source_config = {}
    if tcp:
        source_config = {'tcp': tcp, 'port': port}
    elif serial_port:
        source_config = {'serial': serial_port}

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
@click.option('--serial', 'serial_port', help='Serial port')
def peek_bytes(tcp, port, serial_port):
    """Show raw hex bytes from the bus."""
    if not tcp and not serial_port:
        click.echo("Error: --tcp or --serial is required", err=True)
        sys.exit(1)

    source_config = (
        {'tcp': tcp, 'port': port} if tcp else {'serial': serial_port}
    )
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
        click.echo(
            "pyserial not installed. Install with: pip install pytap[serial]",
            err=True,
        )
