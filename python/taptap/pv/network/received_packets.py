"""PV network received packets iterator."""

from typing import Iterator, Tuple, Optional


class PacketTooShortError(Exception):
    """Packet data is too short to contain a valid header."""
    pass


class ReceivedPackets:
    """Iterator over zero or more received packets in a byte buffer.
    
    Each packet consists of a 7-byte header followed by data.
    The header contains packet_type(1), node_address(2), short_address(2),
    dsn(1), and data_length(1).
    """
    
    HEADER_SIZE = 7
    
    def __init__(self, data: bytes):
        """Create iterator over packet data.
        
        Args:
            data: Raw packet data buffer
        """
        self._data = data
        self._offset = 0
    
    def __iter__(self) -> Iterator[Tuple[bytes, bytes]]:
        """Iterate over (header_bytes, data_bytes) tuples.
        
        Yields:
            Tuple of (7-byte header, data bytes)
            
        Raises:
            PacketTooShortError: If remaining data is too short for header
        """
        while self._offset < len(self._data):
            remaining = self._data[self._offset:]
            
            # Need at least 7 bytes for header
            if len(remaining) < self.HEADER_SIZE:
                raise PacketTooShortError(
                    f"Not enough bytes for header: {len(remaining)} < {self.HEADER_SIZE}"
                )
            
            # Extract header
            header_bytes = remaining[0:self.HEADER_SIZE]
            
            # Data length is the 7th byte (index 6)
            data_length = header_bytes[6]
            
            # Check we have enough data
            if len(remaining) < self.HEADER_SIZE + data_length:
                raise PacketTooShortError(
                    f"Not enough bytes for packet: {len(remaining)} < {self.HEADER_SIZE + data_length}"
                )
            
            # Extract data
            data_bytes = remaining[self.HEADER_SIZE:self.HEADER_SIZE + data_length]
            
            # Advance offset
            self._offset += self.HEADER_SIZE + data_length
            
            yield (header_bytes, data_bytes)
    
    @property
    def remaining(self) -> bytes:
        """Get remaining unprocessed data."""
        return self._data[self._offset:]
