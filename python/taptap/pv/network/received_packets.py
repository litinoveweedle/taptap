"""PV network received packets iterator."""

from typing import Iterator, Tuple, Optional


class PacketTooShortError(Exception):
    """Packet data is too short to contain a valid header."""
    pass


class ReceivedPackets:
    """Iterator over zero or more received packets in a byte buffer.
    
    Each packet consists of a 6-byte header followed by data.
    """
    
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
            Tuple of (6-byte header, data bytes)
            
        Raises:
            PacketTooShortError: If remaining data is too short for header
        """
        while self._offset < len(self._data):
            remaining = self._data[self._offset:]
            
            # Need at least 6 bytes for header
            if len(remaining) < 6:
                raise PacketTooShortError(
                    f"Not enough bytes for header: {len(remaining)} < 6"
                )
            
            # Extract header
            header_bytes = remaining[0:6]
            
            # Data length is the 6th byte (index 5)
            data_length = header_bytes[5]
            
            # Check we have enough data
            if len(remaining) < 6 + data_length:
                raise PacketTooShortError(
                    f"Not enough bytes for packet: {len(remaining)} < {6 + data_length}"
                )
            
            # Extract data
            data_bytes = remaining[6:6 + data_length]
            
            # Advance offset
            self._offset += 6 + data_length
            
            yield (header_bytes, data_bytes)
    
    @property
    def remaining(self) -> bytes:
        """Get remaining unprocessed data."""
        return self._data[self._offset:]
