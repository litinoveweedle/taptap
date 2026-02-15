"""Tests for gateway transport receiver."""

import pytest
from taptap.gateway.transport.messages import (
    ReceiveRequest, ReceiveResponse, interpret_packet_number_lo
)
from taptap.gateway.transport.receiver import Receiver, Counters
from taptap.gateway.link import Frame, Type, Address, GatewayID
from taptap.pv.link.slot_counter import SlotCounter
from taptap.pv.network import ReceivedPacketHeader


def test_interpret_packet_number_lo():
    """Test packet number expansion."""
    # No wrap
    assert interpret_packet_number_lo(0x84, 0x1883) == 0x1884
    
    # Wrap
    assert interpret_packet_number_lo(0x00, 0x18FF) == 0x1900
    assert interpret_packet_number_lo(0x01, 0x18FF) == 0x1901


def test_receive_request_from_bytes():
    """Test parsing ReceiveRequest."""
    data = bytes([0x00, 0x01, 0x18, 0x83, 0x04])
    req = ReceiveRequest.from_bytes(data)
    
    assert req is not None
    assert req.unknown_1 == bytes([0x00, 0x01])
    assert req.packet_number == 0x1883
    assert req.unknown_2 == 0x04


def test_receive_request_too_short():
    """Test ReceiveRequest with insufficient data."""
    assert ReceiveRequest.from_bytes(bytes([1, 2, 3])) is None


def test_receive_response_from_bytes():
    """Test parsing ReceiveResponse."""
    # Example from Rust tests
    data = bytes([
        0x00, 0xFE,  # status_type
        0x01,  # rx_buffers_used
        0x83,  # packet_number_lo
        0x5A, 0xDE,  # slot_counter
        # Packets data follows
        0x07, 0x00, 0x0A, 0x01, 0x14, 0x63, 0x3A,
    ])
    
    result = ReceiveResponse.read_from_bytes(data, 0x1883)
    assert result is not None
    
    response, packets = result
    assert response.rx_buffers_used == 0x01
    assert response.tx_buffers_free is None
    assert response.packet_number == 0x1883  # Expanded from 0x83
    
    # Check slot counter
    assert response.slot_counter.to_u16() == 0x5ADE


def test_receive_response_full_packet_number():
    """Test ReceiveResponse with full 16-bit packet number."""
    data = bytes([
        0x00, 0xEF,  # status_type (bits 0-3 set, bit 4 clear = full packet number, bits 5-7 set)
        0x18, 0x84,  # packet_number (16-bit)
        0x5A, 0xDE,  # slot_counter
    ])
    
    result = ReceiveResponse.read_from_bytes(data, 0x0000)
    assert result is not None
    
    response, packets = result
    assert response.packet_number == 0x1884
    assert response.rx_buffers_used is None
    assert response.tx_buffers_free is None


class MockSink:
    """Mock sink for testing."""
    
    def __init__(self):
        self.slot_counter_captured = []
        self.slot_counter_observed = []
        self.packets_received = []
    
    def gateway_slot_counter_captured(self, gateway_id: GatewayID) -> None:
        self.slot_counter_captured.append(gateway_id)
    
    def gateway_slot_counter_observed(self, gateway_id: GatewayID, slot_counter: SlotCounter) -> None:
        self.slot_counter_observed.append((gateway_id, slot_counter))
    
    def packet_received(self, gateway_id: GatewayID, header: ReceivedPacketHeader, data: bytes) -> None:
        self.packets_received.append((gateway_id, header, data))


def test_transport_receiver_receive_request():
    """Test transport receiver handles RECEIVE_REQUEST."""
    sink = MockSink()
    rx = Receiver(sink)
    
    frame = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_REQUEST,
        payload=bytes([0x00, 0x01, 0x18, 0x83, 0x04])
    )
    
    rx.frame(frame)
    
    assert rx.counters.receive_requests == 1
    assert len(sink.slot_counter_captured) == 1


def test_transport_receiver_receive_response():
    """Test transport receiver handles RECEIVE_RESPONSE."""
    sink = MockSink()
    rx = Receiver(sink)
    
    # First send a request to establish packet number
    request_frame = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_REQUEST,
        payload=bytes([0x00, 0x01, 0x18, 0x83, 0x04])
    )
    rx.frame(request_frame)
    
    # Then send a response
    response_frame = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_RESPONSE,
        payload=bytes([
            0x00, 0xFE,  # status_type
            0x01,  # rx_buffers_used
            0x83,  # packet_number_lo
            0x5A, 0xDE,  # slot_counter
            # No packets
        ])
    )
    rx.frame(response_frame)
    
    assert rx.counters.receive_responses == 1
    assert len(sink.slot_counter_observed) == 1
    assert sink.slot_counter_observed[0][1].to_u16() == 0x5ADE


def test_transport_receiver_ping():
    """Test transport receiver counts ping frames."""
    sink = MockSink()
    rx = Receiver(sink)
    
    ping_req = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.PING_REQUEST,
        payload=bytes()
    )
    rx.frame(ping_req)
    
    ping_resp = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.PING_RESPONSE,
        payload=bytes()
    )
    rx.frame(ping_resp)
    
    assert rx.counters.ping_requests == 1
    assert rx.counters.ping_responses == 1


def test_transport_receiver_reset_counters():
    """Test counter reset."""
    sink = MockSink()
    rx = Receiver(sink)
    
    ping = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.PING_REQUEST,
        payload=bytes()
    )
    rx.frame(ping)
    
    assert rx.counters.ping_requests == 1
    
    rx.reset_counters()
    
    assert rx.counters.ping_requests == 0
