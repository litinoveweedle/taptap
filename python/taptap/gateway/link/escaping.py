"""Gateway link layer byte escaping.

The gateway link layer escapes certain special bytes to prevent them from
being interpreted as frame delimiters or control sequences.
"""


class InvalidEscapeSequence(Exception):
    """Raised when an invalid escape sequence is encountered."""
    pass


def escaped_length(input_bytes: bytes) -> int:
    """Calculate the length of the escaped version of input bytes.
    
    Args:
        input_bytes: Input bytes to escape
        
    Returns:
        Length of escaped output
    """
    count = len(input_bytes)
    for byte in input_bytes:
        if byte in (0x7e, 0x23, 0x24, 0x25, 0xa3, 0xa4, 0xa5):
            count += 1
    return count


def escape(buffer: bytes) -> bytes:
    """Apply link layer escaping to buffer.
    
    Escapes special bytes:
    - 0x7e → 0x7e 0x00
    - 0x24 → 0x7e 0x01
    - 0x23 → 0x7e 0x02
    - 0x25 → 0x7e 0x03
    - 0xa4 → 0x7e 0x04
    - 0xa3 → 0x7e 0x05
    - 0xa5 → 0x7e 0x06
    
    Args:
        buffer: Input bytes
        
    Returns:
        Escaped bytes
    """
    output = bytearray()
    
    for byte in buffer:
        if byte == 0x7e:
            output.extend([0x7e, 0x00])
        elif byte == 0x24:
            output.extend([0x7e, 0x01])
        elif byte == 0x23:
            output.extend([0x7e, 0x02])
        elif byte == 0x25:
            output.extend([0x7e, 0x03])
        elif byte == 0xa4:
            output.extend([0x7e, 0x04])
        elif byte == 0xa3:
            output.extend([0x7e, 0x05])
        elif byte == 0xa5:
            output.extend([0x7e, 0x06])
        else:
            output.append(byte)
    
    return bytes(output)


def unescaped_byte(byte_after_0x7e: int) -> int:
    """Unescape a byte that follows 0x7e.
    
    Args:
        byte_after_0x7e: Byte that follows the 0x7e escape marker
        
    Returns:
        Unescaped byte value
        
    Raises:
        InvalidEscapeSequence: If the escape sequence is invalid
    """
    if byte_after_0x7e == 0x00:
        return 0x7e
    elif byte_after_0x7e == 0x01:
        return 0x24
    elif byte_after_0x7e == 0x02:
        return 0x23
    elif byte_after_0x7e == 0x03:
        return 0x25
    elif byte_after_0x7e == 0x04:
        return 0xa4
    elif byte_after_0x7e == 0x05:
        return 0xa3
    elif byte_after_0x7e == 0x06:
        return 0xa5
    else:
        raise InvalidEscapeSequence(f"Invalid escape sequence: 0x7e 0x{byte_after_0x7e:02x}")


def unescape(buffer: bytes) -> bytes:
    """Unescape a buffer.
    
    Args:
        buffer: Escaped bytes
        
    Returns:
        Unescaped bytes
        
    Raises:
        InvalidEscapeSequence: If an invalid escape sequence is found
    """
    output = bytearray()
    i = 0
    
    while i < len(buffer):
        if buffer[i] == 0x7e:
            if i + 1 >= len(buffer):
                raise InvalidEscapeSequence("Incomplete escape sequence at end of buffer")
            output.append(unescaped_byte(buffer[i + 1]))
            i += 2
        else:
            output.append(buffer[i])
            i += 1
    
    return bytes(output)
