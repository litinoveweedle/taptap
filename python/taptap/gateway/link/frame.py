"""Gateway link layer frames."""

from dataclasses import dataclass
from typing import List

from .address import Address


class Type:
    """Link layer frame type constants."""
    
    RECEIVE_REQUEST = 0x0148
    RECEIVE_RESPONSE = 0x0149
    COMMAND_REQUEST = 0x0B0F
    COMMAND_RESPONSE = 0x0B10
    PING_REQUEST = 0x0B00
    PING_RESPONSE = 0x0B01
    ENUMERATION_START_REQUEST = 0x0014
    ENUMERATION_START_RESPONSE = 0x0015
    ENUMERATION_REQUEST = 0x0038
    ENUMERATION_RESPONSE = 0x0039
    ASSIGN_GATEWAY_ID_REQUEST = 0x003C
    ASSIGN_GATEWAY_ID_RESPONSE = 0x003D
    IDENTIFY_REQUEST = 0x003A
    IDENTIFY_RESPONSE = 0x003B
    VERSION_REQUEST = 0x000A
    VERSION_RESPONSE = 0x000B
    ENUMERATION_END_REQUEST = 0x0E02
    ENUMERATION_END_RESPONSE = 0x0006
    
    @staticmethod
    def name(frame_type: int) -> str:
        """Get name for frame type."""
        names = {
            0x0148: "RECEIVE_REQUEST",
            0x0149: "RECEIVE_RESPONSE",
            0x0B0F: "COMMAND_REQUEST",
            0x0B10: "COMMAND_RESPONSE",
            0x0B00: "PING_REQUEST",
            0x0B01: "PING_RESPONSE",
            0x0014: "ENUMERATION_START_REQUEST",
            0x0015: "ENUMERATION_START_RESPONSE",
            0x0038: "ENUMERATION_REQUEST",
            0x0039: "ENUMERATION_RESPONSE",
            0x003C: "ASSIGN_GATEWAY_ID_REQUEST",
            0x003D: "ASSIGN_GATEWAY_ID_RESPONSE",
            0x003A: "IDENTIFY_REQUEST",
            0x003B: "IDENTIFY_RESPONSE",
            0x000A: "VERSION_REQUEST",
            0x000B: "VERSION_RESPONSE",
            0x0E02: "ENUMERATION_END_REQUEST",
            0x0006: "ENUMERATION_END_RESPONSE",
        }
        return names.get(frame_type, f"0x{frame_type:04X}")


@dataclass
class Frame:
    """Gateway link layer frame."""
    
    address: Address
    frame_type: int  # u16
    payload: bytes
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Frame):
            return NotImplemented
        return (self.address == other.address and 
                self.frame_type == other.frame_type and
                self.payload == other.payload)
    
    def __repr__(self) -> str:
        type_name = Type.name(self.frame_type)
        return f"Frame(address={self.address!r}, frame_type={type_name}, payload={self.payload!r})"
