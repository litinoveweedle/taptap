"""Device barcode encoding and decoding.

Implements the Tigo device barcode format with CRC checksum.
Format: X-NNNNNNNC where:
- X: Leading nibble (hex)
- NNNNNNN: 7 nibbles encoded as base-32
- C: CRC character (base-32)
"""

from typing import Optional

# CRC lookup table
_CRC_TABLE = [0, 3, 6, 5, 12, 15, 10, 9, 11, 8, 13, 14, 7, 4, 1, 2]

# Base-32 alphabet (no vowels to avoid words)
_ALPHABET = 'GHJKLMNPRSTVWXYZ'


class Barcode:
    """Device barcode with CRC validation."""
    
    def __init__(self, long_address: bytes):
        """Create barcode from 8-byte long address.
        
        Args:
            long_address: 8-byte device address
            
        Raises:
            ValueError: If address is not 8 bytes
        """
        if len(long_address) != 8:
            raise ValueError(f"Address must be 8 bytes, got {len(long_address)}")
        self._address = bytes(long_address)
    
    @property
    def address(self) -> bytes:
        """Get the 8-byte address."""
        return self._address
    
    def __str__(self) -> str:
        """Convert to X-NNNNNNNC format.
        
        Returns:
            Barcode string like "4-9A57A2L"
        """
        bytes_data = self._address
        
        # Barcode formatting only applies to addresses with 04:C0:5B prefix
        if bytes_data[0] != 0x04 or bytes_data[1] != 0xC0 or bytes_data[2] != 0x5B:
            # Fall back to hex representation
            return ':'.join(f'{b:02X}' for b in bytes_data)
        
        # Leading nibble from byte 3
        leading_nibble = (bytes_data[3] >> 4) & 0xF
        
        # Extract 9 nibbles from bytes 3-7
        nibbles = [
            bytes_data[3] & 0xF,
            bytes_data[4] >> 4,
            bytes_data[4] & 0xF,
            bytes_data[5] >> 4,
            bytes_data[5] & 0xF,
            bytes_data[6] >> 4,
            bytes_data[6] & 0xF,
            bytes_data[7] >> 4,
            bytes_data[7] & 0xF,
        ]
        
        # Skip leading zeros in the nibbles
        result = []
        skipping = True
        for i, nibble in enumerate(nibbles):
            if skipping and nibble == 0 and i < 9:
                continue
            skipping = False
            result.append(f'{nibble:X}')
        
        # Calculate CRC
        crc_char = chr(self._calculate_crc())
        
        return f"{leading_nibble:X}-{''.join(result)}{crc_char}"
    
    def _calculate_crc(self) -> int:
        """Calculate CRC for barcode.
        
        Returns:
            ASCII character code for CRC
        """
        # Extended CRC table from Rust
        TABLE = [
            0x0, 0x3, 0x6, 0x5, 0xc, 0xf, 0xa, 0x9, 0xb, 0x8, 0xd, 0xe, 0x7, 0x4, 0x1, 0x2,
            0x5, 0x6, 0x3, 0x0, 0x9, 0xa, 0xf, 0xc, 0xe, 0xd, 0x8, 0xb, 0x2, 0x1, 0x4, 0x7,
            0xa, 0x9, 0xc, 0xf, 0x6, 0x5, 0x0, 0x3, 0x1, 0x2, 0x7, 0x4, 0xd, 0xe, 0xb, 0x8,
            0xf, 0xc, 0x9, 0xa, 0x3, 0x0, 0x5, 0x6, 0x4, 0x7, 0x2, 0x1, 0x8, 0xb, 0xe, 0xd,
            0x7, 0x4, 0x1, 0x2, 0xb, 0x8, 0xd, 0xe, 0xc, 0xf, 0xa, 0x9, 0x0, 0x3, 0x6, 0x5,
            0x2, 0x1, 0x4, 0x7, 0xe, 0xd, 0x8, 0xb, 0x9, 0xa, 0xf, 0xc, 0x5, 0x6, 0x3, 0x0,
            0xd, 0xe, 0xb, 0x8, 0x1, 0x2, 0x7, 0x4, 0x6, 0x5, 0x0, 0x3, 0xa, 0x9, 0xc, 0xf,
            0x8, 0xb, 0xe, 0xd, 0x4, 0x7, 0x2, 0x1, 0x3, 0x0, 0x5, 0x6, 0xf, 0xc, 0x9, 0xa,
            0xe, 0xd, 0x8, 0xb, 0x2, 0x1, 0x4, 0x7, 0x5, 0x6, 0x3, 0x0, 0x9, 0xa, 0xf, 0xc,
            0xb, 0x8, 0xd, 0xe, 0x7, 0x4, 0x1, 0x2, 0x0, 0x3, 0x6, 0x5, 0xc, 0xf, 0xa, 0x9,
            0x4, 0x7, 0x2, 0x1, 0x8, 0xb, 0xe, 0xd, 0xf, 0xc, 0x9, 0xa, 0x3, 0x0, 0x5, 0x6,
            0x1, 0x2, 0x7, 0x4, 0xd, 0xe, 0xb, 0x8, 0xa, 0x9, 0xc, 0xf, 0x6, 0x5, 0x0, 0x3,
            0x9, 0xa, 0xf, 0xc, 0x5, 0x6, 0x3, 0x0, 0x2, 0x1, 0x4, 0x7, 0xe, 0xd, 0x8, 0xb,
            0xc, 0xf, 0xa, 0x9, 0x0, 0x3, 0x6, 0x5, 0x7, 0x4, 0x1, 0x2, 0xb, 0x8, 0xd, 0xe,
            0x3, 0x0, 0x5, 0x6, 0xf, 0xc, 0x9, 0xa, 0x8, 0xb, 0xe, 0xd, 0x4, 0x7, 0x2, 0x1,
            0x6, 0x5, 0x0, 0x3, 0xa, 0x9, 0xc, 0xf, 0xd, 0xe, 0xb, 0x8, 0x1, 0x2, 0x7, 0x4,
        ]
        
        crc = 2
        for byte in self._address:
            crc = TABLE[byte ^ (crc << 4)]
        
        return ord(_ALPHABET[crc])
    
    @classmethod
    def from_string(cls, s: str) -> 'Barcode':
        """Parse barcode from X-NNNNNNNC format.
        
        Args:
            s: Barcode string like "4-9A57A2L"
            
        Returns:
            Barcode instance
            
        Raises:
            ValueError: If format is invalid or CRC doesn't match
        """
        # Validate format
        if len(s) < 5:
            raise ValueError(f"Barcode too short: {s}")
        if s[1] != '-':
            raise ValueError("Barcode must have '-' at position 1")
        
        # Parse leading nibble
        try:
            leading_nibble = int(s[0], 16)
        except ValueError:
            raise ValueError(f"Invalid leading nibble: {s[0]}")
        
        # Split into middle and checksum
        middle = s[2:-1]
        checksum = s[-1]
        
        # Parse hex middle portion
        try:
            rest = int(middle, 16)
        except ValueError:
            raise ValueError(f"Invalid hex in barcode middle: {middle}")
        
        # Reconstruct full 64-bit address
        # Formula from Rust: rest | (0x04c05b0 | leading_nibble) << 36
        addr_value = rest | ((0x04c05b0 | leading_nibble) << 36)
        address = addr_value.to_bytes(8, 'big')
        
        # Verify CRC
        barcode = cls(address)
        expected_crc = chr(barcode._calculate_crc())
        
        if checksum != expected_crc:
            raise ValueError(f"CRC mismatch: expected {expected_crc}, got {checksum}")
        
        return barcode
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Barcode):
            return NotImplemented
        return self._address == other._address
    
    def __repr__(self) -> str:
        return f"Barcode('{self}')"
