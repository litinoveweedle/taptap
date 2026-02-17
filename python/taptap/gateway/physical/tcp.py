"""TCP data source for gateway physical layer.

Provides TCP connection to a device that bridges RS-485 to TCP/IP,
such as tcpserial_hook or a hardware serial-to-ethernet adapter.
"""

import socket
import time
from typing import Optional


class TcpSource:
    """TCP data source with automatic reconnection.
    
    Connects to a TCP host/port and reads data from it. Supports
    TCP keepalive and automatic reconnection on connection loss.
    """
    
    def __init__(
        self,
        host: str,
        port: int = 502,
        reconnect_timeout: float = 0,
        reconnect_retry: int = 0,
        reconnect_delay: float = 5.0
    ):
        """Create TCP source.
        
        Args:
            host: Hostname or IP address
            port: TCP port (default 502 for Modbus)
            reconnect_timeout: Seconds of no data before reconnect (0 = disabled)
            reconnect_retry: Number of reconnect attempts (0 = infinite)
            reconnect_delay: Seconds between reconnect attempts
        """
        self._host = host
        self._port = port
        self._socket: Optional[socket.socket] = None
        self._reconnect_timeout = reconnect_timeout
        self._reconnect_retry = reconnect_retry
        self._reconnect_delay = reconnect_delay
        self._connect()
    
    def _connect(self) -> None:
        """Establish TCP connection with keepalive."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Enable TCP keepalive
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        # Platform-specific TCP keepalive settings (Linux/Unix)
        if hasattr(socket, 'TCP_KEEPIDLE'):
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        
        # Set timeout if configured
        if self._reconnect_timeout > 0:
            self._socket.settimeout(self._reconnect_timeout)
        
        # Connect
        self._socket.connect((self._host, self._port))
    
    def _reconnect(self) -> None:
        """Reconnect after connection loss."""
        attempts = 0
        while True:
            if self._reconnect_retry > 0 and attempts >= self._reconnect_retry:
                raise ConnectionError(f"Failed to reconnect after {attempts} attempts")
            
            try:
                if self._socket:
                    try:
                        self._socket.close()
                    except Exception:
                        pass
                
                time.sleep(self._reconnect_delay)
                self._connect()
                break
            except (ConnectionRefusedError, OSError) as e:
                attempts += 1
                if self._reconnect_retry == 0:
                    # Infinite retries - keep trying
                    continue
                else:
                    # Limited retries - may raise on last attempt
                    if attempts >= self._reconnect_retry:
                        raise
    
    def read(self, size: int = 1024) -> bytes:
        """Read bytes from TCP connection.
        
        Args:
            size: Maximum bytes to read
            
        Returns:
            Bytes read (may be empty on timeout or reconnect)
        """
        if not self._socket:
            return b''
        
        try:
            data = self._socket.recv(size)
            if not data:
                # Connection closed by remote
                self._reconnect()
                return b''
            return data
        except socket.timeout:
            # Timeout - return empty
            return b''
        except (ConnectionResetError, BrokenPipeError, OSError):
            # Connection lost - reconnect
            self._reconnect()
            return b''
    
    def close(self) -> None:
        """Close the TCP connection."""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
