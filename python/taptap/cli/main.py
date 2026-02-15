#!/usr/bin/env python3
"""TapTap CLI - Command-line interface for Tigo TAP protocol observer.

This module provides the main entry point for the TapTap Python implementation.
"""

import sys
import signal
import json
from pathlib import Path
import click


@click.group()
@click.version_option(version='0.2.6.post1')
def cli():
    """TapTap: Tigo TAP protocol observer (Python implementation)
    
    Monitor Tigo TAP solar energy systems by observing RS-485 communication.
    """
    pass


@cli.command('list-serial-ports')
def list_serial_ports():
    """List the serial ports available on this system."""
    try:
        from serial.tools import list_ports
        
        ports = list(list_ports.comports())
        if not ports:
            click.echo("No serial ports found.")
            return
        
        for port in ports:
            click.echo(f"{port.device}: {port.description}")
    except ImportError:
        click.echo("Error: pyserial is not installed.", err=True)
        click.echo("Install with: pip install pyserial", err=True)
        sys.exit(1)


@cli.command()
@click.option('--serial', 'serial_port', 
              help='Serial port (e.g., /dev/ttyUSB0, COM1)',
              metavar='PORT')
@click.option('--tcp', 'tcp_host',
              help='TCP hostname or IP address',
              metavar='HOST')
@click.option('--port', 'tcp_port',
              default=502,
              help='TCP port number (default: 502)',
              metavar='PORT',
              type=int)
@click.option('--reconnect-timeout', 'reconnect_timeout',
              default=60,
              help='Reconnect timeout in seconds (0 for no timeout, default: 60)',
              metavar='SECONDS',
              type=int)
@click.option('--reconnect-retry', 'reconnect_retry',
              default=0,
              help='Number of reconnect attempts (0 for infinite, default: 0)',
              metavar='COUNT',
              type=int)
@click.option('--reconnect-delay', 'reconnect_delay',
              default=5,
              help='Delay between reconnect attempts in seconds (default: 5)',
              metavar='SECONDS',
              type=float)
@click.option('--state-file', 'state_file',
              help='Path to JSON file for persistent state storage',
              metavar='FILE',
              type=click.Path())
def observe(serial_port, tcp_host, tcp_port, reconnect_timeout, 
            reconnect_retry, reconnect_delay, state_file):
    """Observe the system, extracting data as it runs.
    
    Monitors the Tigo TAP system and outputs JSON events to stdout.
    Use either --serial for RS-485 or --tcp for network connection.
    """
    # Validate that exactly one source is specified
    if not serial_port and not tcp_host:
        click.echo("Error: Must specify either --serial or --tcp", err=True)
        sys.exit(1)
    
    if serial_port and tcp_host:
        click.echo("Error: Cannot specify both --serial and --tcp", err=True)
        sys.exit(1)
    
    # Import here to avoid requiring all dependencies for all commands
    from ..gateway.physical.tcp import TcpSource
    from ..gateway.physical.serial import SerialSource
    
    # Create data source
    if serial_port:
        try:
            source = SerialSource(serial_port)
            click.echo(f"Connected to serial port: {serial_port}", err=True)
        except ImportError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error opening serial port: {e}", err=True)
            sys.exit(1)
    else:
        try:
            source = TcpSource(
                tcp_host,
                tcp_port,
                reconnect_timeout=float(reconnect_timeout),
                reconnect_retry=reconnect_retry,
                reconnect_delay=reconnect_delay
            )
            click.echo(f"Connected to TCP: {tcp_host}:{tcp_port}", err=True)
        except Exception as e:
            click.echo(f"Error connecting to TCP: {e}", err=True)
            sys.exit(1)
    
    # Import observer components
    from ..gateway.link.receiver import Receiver as LinkReceiver
    from ..gateway.transport.receiver import Receiver as TransportReceiver
    from ..pv.application.receiver import Receiver as ApplicationReceiver
    from ..observer.observer import Observer
    
    # Create the full protocol stack
    observer = Observer(state_file=state_file)
    app_receiver = ApplicationReceiver(sink=observer)
    transport_receiver = TransportReceiver(sink=app_receiver)
    link_receiver = LinkReceiver(sink=transport_receiver)
    
    # Setup signal handling for graceful shutdown
    shutdown_requested = [False]  # Use list to allow modification in nested function
    
    def signal_handler(signum, frame):
        shutdown_requested[0] = True
        click.echo("\nShutdown requested...", err=True)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    click.echo("Observer mode - monitoring TAP protocol...", err=True)
    if state_file:
        click.echo(f"State file: {state_file}", err=True)
    
    try:
        # Main read loop
        while not shutdown_requested[0]:
            data = source.read()
            if data:
                # Feed bytes into the link receiver
                link_receiver.extend_from_slice(data)
    except KeyboardInterrupt:
        click.echo("\nInterrupted by user", err=True)
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        # Save state on exit
        if state_file:
            try:
                observer.write_persistent_state()
                click.echo(f"State saved to {state_file}", err=True)
            except Exception as e:
                click.echo(f"Warning: Failed to save state: {e}", err=True)
        
        source.close()
        click.echo("Connection closed", err=True)


@cli.command('peek-bytes')
@click.option('--serial', 'serial_port',
              help='Serial port (e.g., /dev/ttyUSB0)',
              metavar='PORT')
@click.option('--tcp', 'tcp_host',
              help='TCP hostname or IP address',
              metavar='HOST')
@click.option('--port', 'tcp_port',
              default=502,
              help='TCP port number (default: 502)',
              type=int)
@click.option('--raw', is_flag=True,
              help='Print raw binary bytes without escaping')
def peek_bytes(serial_port, tcp_host, tcp_port, raw):
    """Peek at the raw data flowing at the gateway physical layer.
    
    Displays raw bytes from the RS-485 bus in hexadecimal format.
    """
    if not serial_port and not tcp_host:
        click.echo("Error: Must specify either --serial or --tcp", err=True)
        sys.exit(1)
    
    from ..gateway.physical.tcp import TcpSource
    from ..gateway.physical.serial import SerialSource
    
    # Create source
    if serial_port:
        source = SerialSource(serial_port)
    else:
        source = TcpSource(tcp_host, tcp_port)
    
    click.echo("Reading bytes (Ctrl+C to stop)...", err=True)
    
    try:
        while True:
            data = source.read()
            if data:
                if raw:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                else:
                    hex_str = ' '.join(f'{b:02X}' for b in data)
                    click.echo(hex_str)
    except KeyboardInterrupt:
        click.echo("\nStopped", err=True)
    finally:
        source.close()


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()
