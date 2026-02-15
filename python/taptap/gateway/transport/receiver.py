"""Gateway transport layer receiver.

Processes link layer frames and emits transport-level events.
"""

from dataclasses import dataclass
from typing import Protocol, Dict

from ..link import Frame, Type, Address, GatewayID, Sink as LinkSink
from .messages import ReceiveRequest, ReceiveResponse
from ...pv.link.slot_counter import SlotCounter
from ...pv.network import ReceivedPacketHeader, PacketTooShortError


class Sink(Protocol):
    """Interface for receiving transport-level events."""
    
    def gateway_slot_counter_captured(self, gateway_id: GatewayID) -> None:
        """Gateway captured its slot counter (in RECEIVE_REQUEST)."""
        ...
    
    def gateway_slot_counter_observed(self, gateway_id: GatewayID, slot_counter: SlotCounter) -> None:
        """Gateway slot counter was observed (in RECEIVE_RESPONSE)."""
        ...
    
    def packet_received(
        self,
        gateway_id: GatewayID,
        header: ReceivedPacketHeader,
        data: bytes
    ) -> None:
        """PV network packet was received from gateway."""
        ...


@dataclass
class Counters:
    """Transport receiver activity counters."""
    receive_requests: int = 0
    receive_responses: int = 0
    receive_packets: int = 0
    invalid_receive_request: int = 0
    invalid_receive_responses: int = 0
    receive_response_from_unknown_gateway: int = 0
    receive_packet_too_short: int = 0
    ping_requests: int = 0
    ping_responses: int = 0
    unhandled_frame_type: int = 0


class Receiver:
    """Gateway transport layer receiver.
    
    Implements link.Sink to receive frames and dispatches them
    to transport-level handlers.
    """
    
    def __init__(self, sink: Sink):
        """Create receiver with given sink.
        
        Args:
            sink: Object implementing Sink protocol
        """
        self._sink = sink
        self._rx_packet_numbers: Dict[int, int] = {}  # gateway_id -> packet_number
        self._counters = Counters()
    
    @property
    def sink(self) -> Sink:
        """Access the sink."""
        return self._sink
    
    @property
    def counters(self) -> Counters:
        """Get current counters."""
        return self._counters
    
    def reset_counters(self) -> None:
        """Reset all counters to zero."""
        self._counters = Counters()
    
    def frame(self, frame: Frame) -> None:
        """Handle incoming link layer frame (implements link.Sink).
        
        Args:
            frame: Link layer frame to process
        """
        if frame.frame_type == Type.RECEIVE_REQUEST:
            self._receive_request(frame)
        elif frame.frame_type == Type.RECEIVE_RESPONSE:
            self._receive_response(frame)
        elif frame.frame_type == Type.PING_REQUEST:
            self._counters.ping_requests += 1
        elif frame.frame_type == Type.PING_RESPONSE:
            self._counters.ping_responses += 1
        else:
            self._counters.unhandled_frame_type += 1
    
    def _receive_request(self, frame: Frame) -> None:
        """Handle RECEIVE_REQUEST frame.
        
        Args:
            frame: Link frame with RECEIVE_REQUEST type
        """
        # Must be To gateway
        if frame.address.direction != 0:  # Not To
            self._counters.invalid_receive_request += 1
            return
        
        gateway_id = frame.address.gateway_id
        
        # Parse payload
        request = ReceiveRequest.from_bytes(frame.payload)
        if request is None:
            self._counters.invalid_receive_request += 1
            return
        
        # Gateway captured slot counter now
        self._sink.gateway_slot_counter_captured(gateway_id)
        
        self._counters.receive_requests += 1
        
        # Record packet number for this gateway
        self._rx_packet_numbers[gateway_id.value] = request.packet_number
    
    def _receive_response(self, frame: Frame) -> None:
        """Handle RECEIVE_RESPONSE frame.
        
        Args:
            frame: Link frame with RECEIVE_RESPONSE type
        """
        # Must be From gateway
        if frame.address.direction != 1:  # Not From
            self._counters.invalid_receive_responses += 1
            return
        
        gateway_id = frame.address.gateway_id
        
        # Get stored packet number for this gateway
        old_packet_number = self._rx_packet_numbers.get(gateway_id.value)
        if old_packet_number is None:
            self._counters.receive_response_from_unknown_gateway += 1
            return
        
        # Parse response
        result = ReceiveResponse.read_from_bytes(frame.payload, old_packet_number)
        if result is None:
            self._counters.invalid_receive_responses += 1
            return
        
        response, packets = result
        self._counters.receive_responses += 1
        
        # Update packet number
        self._rx_packet_numbers[gateway_id.value] = response.packet_number
        
        # Observe slot counter
        self._sink.gateway_slot_counter_observed(gateway_id, response.slot_counter)
        
        # Process packets
        try:
            for header_bytes, data in packets:
                # Parse header
                header = ReceivedPacketHeader.from_bytes(header_bytes)
                self._counters.receive_packets += 1
                
                # Emit to sink
                self._sink.packet_received(gateway_id, header, data)
        except PacketTooShortError:
            self._counters.receive_packet_too_short += 1
