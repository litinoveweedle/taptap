"""Serial port data source for gateway physical layer.

Provides serial port (RS-485) connection for reading data from
Tigo TAP devices.
"""

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


class SerialSource:
    """Serial port data source.
    
    Wraps pyserial to provide a simple read interface for RS-485
    communication with Tigo TAP devices.
    """
    
    def __init__(self, port: str, baud_rate: int = 9600, timeout: float = 1.0):
        """Create serial source.
        
        Args:
            port: Serial port path (e.g., /dev/ttyUSB0, COM1)
            baud_rate: Baud rate (default 9600 for Tigo TAP)
            timeout: Read timeout in seconds
            
        Raises:
            ImportError: If pyserial is not installed
            serial.SerialException: If port cannot be opened
        """
        if not SERIAL_AVAILABLE:
            raise ImportError(
                "pyserial is required for serial port support. "
                "Install with: pip install pyserial"
            )
        
        self._serial = serial.Serial(
            port=port,
            baudrate=baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout
        )
    
    def read(self, size: int = 1024) -> bytes:
        """Read bytes from serial port.
        
        Args:
            size: Maximum bytes to read
            
        Returns:
            Bytes read (may be less than size, or empty on timeout)
        """
        if not self._serial or not self._serial.is_open:
            return b''
        
        return self._serial.read(size)
    
    def close(self) -> None:
        """Close the serial port."""
        if self._serial and self._serial.is_open:
            self._serial.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
