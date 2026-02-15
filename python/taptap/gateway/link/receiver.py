"""Gateway link layer receiver.

Converts a stream of bytes into frames via state machine.
Handles preamble detection, frame assembly, CRC validation, and error recovery.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, List

from .frame import Frame
from .address import Address
from .crc import crc
from .escaping import unescaped_byte, InvalidEscapeSequence


class Sink(Protocol):
    """Interface for receiving assembled frames."""
    
    def frame(self, frame: Frame) -> None:
        """Called when a complete, valid frame is received."""
        ...


class State(Enum):
    """Receiver state machine states."""
    IDLE = auto()
    NOISE = auto()
    START_OF_FRAME = auto()
    FRAME = auto()
    FRAME_ESCAPE = auto()
    GIANT = auto()
    GIANT_ESCAPE = auto()


@dataclass
class Counters:
    """Receiver activity counters."""
    frames: int = 0
    runts: int = 0
    giants: int = 0
    checksums: int = 0
    noise: int = 0


class Receiver:
    """Gateway link layer frame receiver.
    
    Processes a byte stream and assembles frames, calling the sink
    for each valid frame received.
    """
    
    MAX_FRAME_SIZE = 256
    
    def __init__(self, sink: Sink):
        """Create receiver with given sink.
        
        Args:
            sink: Object with frame() method to receive assembled frames
        """
        self._sink = sink
        self._state = State.IDLE
        self._counters = Counters()
        self._buffer: List[int] = []
    
    @property
    def sink(self) -> Sink:
        """Access the sink."""
        return self._sink
    
    @property
    def counters(self) -> Counters:
        """Get current counters."""
        return self._counters
    
    @property
    def state(self) -> State:
        """Get current state (for testing)."""
        return self._state
    
    @property
    def buffer_len(self) -> int:
        """Get buffer length (for testing)."""
        return len(self._buffer)
    
    def reset_counters(self) -> None:
        """Reset all counters to zero."""
        self._counters = Counters()
    
    def extend_from_slice(self, data: bytes) -> None:
        """Process a slice of bytes.
        
        Args:
            data: Bytes to process
        """
        for byte in data:
            self._push_u8(byte)
    
    def _push_u8(self, byte: int) -> None:
        """Process a single byte through state machine.
        
        Args:
            byte: Byte value (0-255)
        """
        old_state = self._state
        
        if self._state == State.IDLE:
            # Looking for preamble
            if byte in (0x00, 0xFF):
                next_state = State.IDLE
            elif byte == 0x7E:
                next_state = State.START_OF_FRAME
            else:
                next_state = State.NOISE
        
        elif self._state == State.NOISE:
            # Discarding noise, looking for preamble
            if byte in (0x00, 0xFF):
                next_state = State.IDLE
            elif byte == 0x7E:
                next_state = State.START_OF_FRAME
            else:
                next_state = State.NOISE
        
        elif self._state == State.START_OF_FRAME:
            # Expecting 0x07 to confirm start of frame
            if byte == 0x07:
                next_state = State.FRAME
            else:
                next_state = State.NOISE
        
        elif self._state == State.FRAME:
            # Accumulating frame data
            if byte == 0x7E:
                next_state = State.FRAME_ESCAPE
            elif len(self._buffer) < self.MAX_FRAME_SIZE:
                self._buffer.append(byte)
                next_state = State.FRAME
            else:
                # Frame too long
                next_state = State.GIANT
        
        elif self._state == State.FRAME_ESCAPE:
            # Processing escape sequence
            if byte == 0x08:
                # End of frame
                self._parse_frame_from_buffer()
                self._buffer.clear()
                next_state = State.IDLE
            else:
                try:
                    unescaped = unescaped_byte(byte)
                    if len(self._buffer) < self.MAX_FRAME_SIZE:
                        self._buffer.append(unescaped)
                        next_state = State.FRAME
                    else:
                        self._buffer.clear()
                        next_state = State.GIANT_ESCAPE
                except InvalidEscapeSequence:
                    self._buffer.clear()
                    next_state = State.NOISE
        
        elif self._state == State.GIANT:
            # Discarding overlong frame
            if byte == 0x7E:
                next_state = State.GIANT_ESCAPE
            else:
                next_state = State.GIANT
        
        elif self._state == State.GIANT_ESCAPE:
            # In escape after giant frame
            if byte == 0x07:
                next_state = State.FRAME
            elif byte == 0x08:
                next_state = State.IDLE
            else:
                next_state = State.GIANT
        
        else:
            next_state = self._state
        
        # Update counters
        if next_state == State.NOISE and old_state != State.NOISE:
            self._counters.noise += 1
        
        if next_state == State.GIANT and old_state not in (State.GIANT, State.GIANT_ESCAPE):
            self._buffer.clear()
            self._counters.giants += 1
        
        self._state = next_state
    
    def _parse_frame_from_buffer(self) -> None:
        """Parse and emit frame from buffer."""
        # Check minimum length (address + type + crc = 2 + 2 + 2 = 6)
        if len(self._buffer) < 6:
            self._counters.runts += 1
            return
        
        # Verify CRC
        body = bytes(self._buffer[:-2])
        expected_crc_bytes = bytes(self._buffer[-2:])
        calculated_crc = crc(body)
        expected_crc = int.from_bytes(expected_crc_bytes, byteorder='little')
        
        if calculated_crc != expected_crc:
            self._counters.checksums += 1
            return
        
        # Parse frame
        address = Address.from_bytes(bytes(self._buffer[0:2]))
        frame_type = int.from_bytes(bytes(self._buffer[2:4]), byteorder='big')
        payload = bytes(self._buffer[4:-2])
        
        self._counters.frames += 1
        self._sink.frame(Frame(
            address=address,
            frame_type=frame_type,
            payload=payload
        ))
