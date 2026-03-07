"""Data sources for pytap: TCP and serial byte providers.

Sources have no protocol knowledge — they just provide raw bytes.
"""

import socket
from typing import Optional


class TcpSource:
    """TCP socket data source."""

    def __init__(self, host: str, port: int = 502):
        self._host = host
        self._port = port
        self._socket: Optional[socket.socket] = None

    def connect(self):
        """Open a TCP connection to the host."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(10.0)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Platform-specific keepalive tuning
        try:
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except (AttributeError, OSError):
            pass
        self._socket.connect((self._host, self._port))

    def read(self, size: int = 1024) -> bytes:
        """Read bytes from the socket."""
        if self._socket is None:
            return b''
        try:
            data = self._socket.recv(size)
            return data
        except socket.timeout:
            return b''
        except (ConnectionResetError, BrokenPipeError, OSError):
            return b''

    def close(self):
        """Close the socket connection."""
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None


class SerialSource:
    """Serial port data source (requires pyserial)."""

    def __init__(self, port: str, baud_rate: int = 38400):
        try:
            import serial
        except ImportError:
            raise ImportError(
                "pyserial is required for serial sources. "
                "Install with: pip install pytap[serial]"
            )
        self._serial = serial.Serial(
            port=port,
            baudrate=baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,
        )

    def read(self, size: int = 1024) -> bytes:
        """Read bytes from the serial port."""
        return self._serial.read(size)

    def close(self):
        """Close the serial port."""
        self._serial.close()
