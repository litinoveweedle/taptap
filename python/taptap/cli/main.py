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


@cli.command('peek-frames')
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
def peek_frames(serial_port, tcp_host, tcp_port):
    """Peek at the assembled frames at the gateway link layer.
    
    Displays assembled link-layer frames after deframing, escaping, and CRC validation.
    """
    if not serial_port and not tcp_host:
        click.echo("Error: Must specify either --serial or --tcp", err=True)
        sys.exit(1)
    
    from ..gateway.physical.tcp import TcpSource
    from ..gateway.physical.serial import SerialSource
    from ..gateway.link.receiver import Receiver as LinkReceiver
    
    class FramePrintSink:
        """Sink that prints each assembled frame."""
        def frame(self, frame):
            click.echo(repr(frame))
    
    # Create source
    if serial_port:
        source = SerialSource(serial_port)
    else:
        source = TcpSource(tcp_host, tcp_port)
    
    link_receiver = LinkReceiver(sink=FramePrintSink())
    
    click.echo("Reading frames (Ctrl+C to stop)...", err=True)
    
    try:
        while True:
            data = source.read()
            if data:
                link_receiver.extend_from_slice(data)
    except KeyboardInterrupt:
        click.echo("\nStopped", err=True)
    finally:
        source.close()


@cli.command('peek-activity')
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
def peek_activity(serial_port, tcp_host, tcp_port):
    """Peek at the gateway transport and PV application layer activity.
    
    Displays transport-level events (enumeration, slot counters, packets)
    and PV application-level events (string requests/responses, node table
    pages, topology reports, power reports).
    """
    if not serial_port and not tcp_host:
        click.echo("Error: Must specify either --serial or --tcp", err=True)
        sys.exit(1)
    
    import logging
    from ..gateway.physical.tcp import TcpSource
    from ..gateway.physical.serial import SerialSource
    from ..gateway.link.receiver import Receiver as LinkReceiver
    from ..gateway.transport.receiver import Receiver as TransportReceiver
    from ..pv.application.receiver import Receiver as ApplicationReceiver
    from ..pv.application.types import PacketType
    
    # Configure logging for info-level output (matches Rust log::info!)
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s %(message)s',
        stream=sys.stderr,
    )
    logger = logging.getLogger('taptap.peek_activity')
    
    class ActivitySink:
        """Sink that logs transport and application layer events.
        
        Mirrors the Rust peek_activity Sink, including slot counter throttling.
        """
        def __init__(self):
            self.slot_counters = {}  # gateway_id -> SlotCounter
        
        # --- transport.Sink methods ---
        
        def enumeration_started(self, enumeration_gateway_id):
            logger.info("enumeration started (at %r)", enumeration_gateway_id)
        
        def gateway_identity_observed(self, gateway_id, address):
            logger.info("gateway identity observed: %r = %r", gateway_id, address)
        
        def gateway_version_observed(self, gateway_id, version):
            logger.info("gateway version observed: %r = %r", gateway_id, version)
        
        def enumeration_ended(self, gateway_id):
            logger.info("enumeration ended: %r", gateway_id)
        
        def gateway_slot_counter_captured(self, gateway_id):
            pass
        
        def gateway_slot_counter_observed(self, gateway_id, slot_counter):
            should_print = True
            last = self.slot_counters.get(gateway_id)
            if last is not None:
                should_print = (
                    last.epoch != slot_counter.epoch
                    or (last.slot_number.value // 1000) != (slot_counter.slot_number.value // 1000)
                )
            self.slot_counters[gateway_id] = slot_counter
            if should_print:
                logger.info("slot counter: %r %r", gateway_id, slot_counter)
        
        def packet_received(self, gateway_id, header, data):
            # Filter out types handled at the application layer
            if header.packet_type in (
                PacketType.STRING_RESPONSE,
                PacketType.POWER_REPORT,
                PacketType.TOPOLOGY_REPORT,
            ):
                return
            logger.info("packet received: %r %r %r", gateway_id, header, data)
        
        def command_executed(self, gateway_id, request, response):
            req_type = request[0]
            # Filter out types handled at the application layer
            if req_type in (PacketType.STRING_REQUEST, PacketType.NODE_TABLE_REQUEST):
                return
            logger.info(
                "command executed: %r %r %r => %r %r",
                gateway_id, request[0], request[1], response[0], response[1]
            )
        
        # --- pv.application.Sink methods ---
        
        def string_request(self, gateway_id, pv_node_id, request):
            logger.info("string request: %r %r %r", gateway_id, pv_node_id, request)
        
        def string_response(self, gateway_id, pv_node_id, response):
            logger.info("string response: %r %r %r", gateway_id, pv_node_id, response)
        
        def node_table_page(self, gateway_id, start_address, nodes):
            logger.info("node table page: %r start %r %r", gateway_id, start_address, nodes)
        
        def topology_report(self, gateway_id, pv_node_id, topology_report):
            logger.info("topology report: %r %r %r", gateway_id, pv_node_id, topology_report)
        
        def power_report(self, gateway_id, pv_node_id, power_report):
            logger.info("power report: %r %r %r", gateway_id, pv_node_id, power_report)
    
    # Create source
    if serial_port:
        source = SerialSource(serial_port)
    else:
        source = TcpSource(tcp_host, tcp_port)
    
    # Build the full protocol stack:
    # bytes → LinkReceiver → TransportReceiver → ApplicationReceiver → ActivitySink
    activity_sink = ActivitySink()
    app_receiver = ApplicationReceiver(sink=activity_sink)
    transport_receiver = TransportReceiver(sink=app_receiver)
    link_receiver = LinkReceiver(sink=transport_receiver)
    
    click.echo("Reading activity (Ctrl+C to stop)...", err=True)
    
    try:
        while True:
            data = source.read()
            if data:
                link_receiver.extend_from_slice(data)
    except KeyboardInterrupt:
        click.echo("\nStopped", err=True)
    finally:
        source.close()


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()
