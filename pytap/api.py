"""pytap public API — all protocol logic accessible via function calls."""

import logging
import time
from pathlib import Path
from typing import Callable, Union

from .core.parser import Parser
from .core.events import Event
from .core.source import TcpSource, SerialSource

logger = logging.getLogger(__name__)


def create_parser(state_file: Union[str, Path, None] = None) -> Parser:
    """Create a new protocol parser instance.

    Args:
        state_file: Optional filesystem path for persistent infrastructure state.

    Returns:
        A Parser ready to accept bytes via feed().
    """
    return Parser(state_file=state_file)


def parse_bytes(
    data: bytes, state_file: Union[str, Path, None] = None,
) -> list[Event]:
    """One-shot convenience: creates a parser, feeds bytes, returns events.

    Suitable for batch processing of captured data.
    For streaming use, prefer create_parser() + feed().

    Args:
        data: Raw bytes from the RS-485 bus or a capture file.
        state_file: Optional persistent state file path.

    Returns:
        List of all events found in data.
    """
    parser = Parser(state_file=state_file)
    return parser.feed(data)


def connect(source_config: dict):
    """Open a byte source for manual use with a Parser.

    Args:
        source_config: Connection parameters:
            TCP: {"tcp": "192.168.1.100", "port": 502}
            Serial: {"serial": "/dev/ttyUSB0"} or {"serial": "COM3"}

    Returns:
        A source object with read(size) and close() methods.

    Raises:
        ValueError: If source_config is missing required keys.
    """
    if 'tcp' in source_config:
        src = TcpSource(source_config['tcp'], source_config.get('port', 502))
        src.connect()
        return src
    elif 'serial' in source_config:
        return SerialSource(source_config['serial'])
    else:
        raise ValueError("source_config must contain 'tcp' or 'serial' key")


def observe(
    source_config: dict,
    callback: Callable[[Event], None],
    state_file: Union[str, Path, None] = None,
    reconnect_timeout: int = 60,
    reconnect_retries: int = 0,
    reconnect_delay: int = 5,
) -> None:
    """Connect to a live data source and stream parsed events.

    Runs a blocking loop with automatic reconnection.

    Args:
        source_config: Connection parameters (same format as connect()).
        callback: Called with each Event as it is parsed.
        state_file: Optional persistent state file path.
        reconnect_timeout: Seconds of silence before reconnecting (0=disabled).
        reconnect_retries: Maximum reconnection attempts (0=infinite).
        reconnect_delay: Seconds between reconnection attempts.
    """
    parser = Parser(state_file=state_file)
    retries = 0
    source = None

    while True:
        try:
            source = connect(source_config)
            logger.info("Connected to source")
            retries = 0
            last_data_time = time.monotonic()

            while True:
                data = source.read(1024)
                if data:
                    last_data_time = time.monotonic()
                    for event in parser.feed(data):
                        callback(event)
                elif (
                    reconnect_timeout > 0
                    and (time.monotonic() - last_data_time) > reconnect_timeout
                ):
                    logger.warning(
                        "No data for %ds, reconnecting", reconnect_timeout
                    )
                    break

        except Exception as e:
            logger.error("Connection error: %s", e)

        finally:
            if source is not None:
                try:
                    source.close()
                except Exception:
                    pass

        retries += 1
        if reconnect_retries > 0 and retries > reconnect_retries:
            logger.error("Max retries (%d) exceeded", reconnect_retries)
            return

        logger.info(
            "Reconnecting in %ds (attempt %d/%s)...",
            reconnect_delay,
            retries,
            str(reconnect_retries) if reconnect_retries else '\u221e',
        )
        time.sleep(reconnect_delay)
