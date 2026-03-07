"""Tests for gateway link receiver."""

import pytest
from taptap.gateway.link import Receiver, Frame, Type, Address, GatewayID, Counters, State


class ListSink:
    """Simple sink that collects frames in a list."""
    
    def __init__(self):
        self.frames = []
    
    def frame(self, frame: Frame) -> None:
        self.frames.append(frame)


def test_receiver_happy_path():
    """Test receiver with valid frames (from Rust test)."""
    rx = Receiver(ListSink())
    
    # Data from Rust happy_path test
    data = bytes([
        0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x01, 0x48, 0x00, 0x01, 0x18, 0x83, 0x04,
        0x17, 0x44, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x01, 0x49, 0x00, 0xFE, 0x01,
        0x83, 0x5A, 0xDE, 0x07, 0x00, 0x0A, 0x01, 0x14, 0x63, 0x3A, 0x79, 0x26,
        0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x01, 0x48, 0x00, 0x01, 0x18,
        0x84, 0x04, 0x1F, 0x09, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x01, 0x49, 0x00,
        0xFF, 0x7C, 0xDB, 0xC2, 0x7E, 0x05, 0x85, 0x7E, 0x08,
    ])
    
    rx.extend_from_slice(data)
    
    assert rx.state == State.IDLE
    assert rx.counters.frames == 4
    assert rx.counters.runts == 0
    assert rx.counters.giants == 0
    assert rx.counters.checksums == 0
    assert rx.counters.noise == 0
    assert rx.buffer_len == 0
    
    # Verify frames
    frames = rx.sink.frames
    assert len(frames) == 4
    
    # Frame 1
    assert frames[0].address == Address.to(GatewayID(0x1201))
    assert frames[0].frame_type == Type.RECEIVE_REQUEST
    assert frames[0].payload == b"\x00\x01\x18\x83\x04"
    
    # Frame 2
    assert frames[1].address == Address.from_(GatewayID(0x1201))
    assert frames[1].frame_type == Type.RECEIVE_RESPONSE
    assert frames[1].payload == b"\x00\xFE\x01\x83\x5A\xDE\x07\x00\x0A\x01\x14\x63\x3A"
    
    # Frame 3
    assert frames[2].address == Address.to(GatewayID(0x1201))
    assert frames[2].frame_type == Type.RECEIVE_REQUEST
    assert frames[2].payload == b"\x00\x01\x18\x84\x04"
    
    # Frame 4
    assert frames[3].address == Address.from_(GatewayID(0x1201))
    assert frames[3].frame_type == Type.RECEIVE_RESPONSE
    assert frames[3].payload == b"\x00\xFF\x7C\xDB\xC2"


def test_receiver_interframe_noise():
    """Test receiver handles noise between frames."""
    rx = Receiver(ListSink())
    
    # Data from Rust interframe_noise test
    data = bytes([
        0xEE, 0xEE, 0xEE, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x01, 0x48, 0x00, 0x01,
        0x18, 0x83, 0x04, 0x17, 0x44, 0x7E, 0x08, 0x01, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x01,
        0x49, 0x00, 0xFE, 0x01, 0x83, 0x5A, 0xDE, 0x07, 0x00, 0x0A, 0x01, 0x14, 0x63, 0x3A,
        0x79, 0x26, 0x7E, 0x08, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF, 0x00,
        0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x01, 0x48, 0x00, 0x01, 0x18, 0x84, 0x04, 0x1F,
        0x09, 0x7E, 0x08, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x7E,
        0x07, 0x92, 0x01, 0x01, 0x49, 0x00, 0xFF, 0x7C, 0xDB, 0xC2, 0x7E, 0x05, 0x85, 0x7E,
        0x08,
    ])
    
    rx.extend_from_slice(data)
    
    assert rx.state == State.IDLE
    assert rx.counters.frames == 4
    assert rx.counters.runts == 0
    assert rx.counters.giants == 0
    assert rx.counters.checksums == 0
    assert rx.counters.noise == 3
    assert rx.buffer_len == 0


def test_receiver_checksum():
    """Test receiver detects bad checksums."""
    rx = Receiver(ListSink())
    
    # Data from Rust checksum test (with corrupted CRCs)
    data = bytes([
        0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x01, 0x48, 0x00, 0x01, 0x18, 0x83, 0x04,
        0x17, 0x44, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x01, 0x49, 0x00, 0xFE, 0x01,
        0x83, 0x5A, 0xDE, 0x07, 0x00, 0x0A, 0x01, 0x14, 0x63, 0x3A, 0x79, 0x25,  # Bad CRC
        0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x01, 0x48, 0x00, 0x01, 0x18,
        0x84, 0x04, 0x1E, 0x09, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x01, 0x49, 0x00,  # Bad CRC
        0xFF, 0x7C, 0xDB, 0xC2, 0x7E, 0x05, 0x85, 0x7E, 0x08,
    ])
    
    rx.extend_from_slice(data)
    
    assert rx.state == State.IDLE
    assert rx.counters.frames == 2
    assert rx.counters.runts == 0
    assert rx.counters.giants == 0
    assert rx.counters.checksums == 2
    assert rx.counters.noise == 0
    assert rx.buffer_len == 0


def test_receiver_intraframe_noise():
    """Test receiver handles noise within frames."""
    rx = Receiver(ListSink())
    
    # Data from Rust intraframe_noise test
    data = bytes([
        0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01, 0x01, 0x48, 0x00, 0x01, 0x7E, 0x83, 0x04,
        0x17, 0x44, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x01, 0x49, 0x00, 0xFE, 0x01,
        0x83, 0x5A, 0xDE, 0x07, 0x00, 0x0A, 0x01, 0x14, 0x63, 0x3A, 0x79, 0x7E,
        0x7E, 0x08, 0x00, 0xFF, 0xFF, 0x7E, 0x7E, 0x12, 0x01, 0x01, 0x48, 0x00, 0x01, 0x18,
        0x84, 0x04, 0x1F, 0x09, 0x7E, 0x08, 0xFF, 0x7E, 0x07, 0x92, 0x01, 0x01, 0x49, 0x00,
        0xFF, 0x7C, 0xDB, 0xC2, 0x7E, 0x05, 0x85, 0x7E, 0x08,
    ])
    
    rx.extend_from_slice(data)
    
    assert rx.state == State.IDLE
    assert rx.counters.frames == 1
    assert rx.counters.runts == 0
    assert rx.counters.giants == 0
    assert rx.counters.checksums == 0
    assert rx.counters.noise == 6
    assert rx.buffer_len == 0


def test_receiver_runt():
    """Test receiver detects frames that are too short."""
    rx = Receiver(ListSink())
    
    # Data from Rust runt test
    data = bytes([
        # Underlength frames
        0xFF, 0x7E, 0x07, 0x7E, 0x08,
        0xFF, 0x7E, 0x07, 0x00, 0x7E, 0x08,
        0xFF, 0x7E, 0x07, 0x00, 0x00, 0x7E, 0x08,
        0xFF, 0x7E, 0x07, 0x00, 0x00, 0x00, 0x7E, 0x08,
        0xFF, 0x7E, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7E, 0x08,
        # Minimum length frame
        0xFF, 0x7E, 0x07, 0x00, 0x01, 0x00, 0x00, 0x89, 0xD0, 0x7E, 0x08,
    ])
    
    rx.extend_from_slice(data)
    
    assert rx.state == State.IDLE
    assert rx.counters.frames == 1
    assert rx.counters.runts == 5
    assert rx.counters.giants == 0
    assert rx.counters.checksums == 0
    assert rx.counters.noise == 0
    assert rx.buffer_len == 0


def test_receiver_giant():
    """Test receiver detects frames that are too long."""
    rx = Receiver(ListSink())
    
    # Data from Rust giant test
    rx.extend_from_slice(bytes([0x00, 0xFF, 0xFF, 0x7E, 0x07, 0x12, 0x01]))
    rx.extend_from_slice(bytes([0] * 1000))
    
    assert rx.state == State.GIANT
    
    rx.extend_from_slice(bytes([0x7E]))
    assert rx.state == State.GIANT_ESCAPE
    
    rx.extend_from_slice(bytes([0x08]))
    assert rx.state == State.IDLE
    
    assert rx.counters.frames == 0
    assert rx.counters.runts == 0
    assert rx.counters.giants == 1
    assert rx.counters.checksums == 0
    assert rx.counters.noise == 0
    assert rx.buffer_len == 0


def test_receiver_reset_counters():
    """Test counter reset."""
    rx = Receiver(ListSink())
    
    # Generate some noise
    rx.extend_from_slice(bytes([0xAA, 0xBB, 0xCC]))
    
    assert rx.counters.noise > 0
    
    rx.reset_counters()
    
    assert rx.counters.frames == 0
    assert rx.counters.noise == 0


def test_frame_equality():
    """Test Frame equality comparison."""
    f1 = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_REQUEST,
        payload=b"\x00\x01"
    )
    
    f2 = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_REQUEST,
        payload=b"\x00\x01"
    )
    
    f3 = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_RESPONSE,
        payload=b"\x00\x01"
    )
    
    assert f1 == f2
    assert f1 != f3


def test_frame_repr():
    """Test Frame string representation."""
    f = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_REQUEST,
        payload=b"\x00\x01"
    )
    
    repr_str = repr(f)
    assert "Frame" in repr_str
    assert "RECEIVE_REQUEST" in repr_str
