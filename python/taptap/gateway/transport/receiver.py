"""Gateway transport layer receiver.

Processes link layer frames and emits transport-level events.
"""

from dataclasses import dataclass
from typing import Protocol, Dict, Tuple

from ..link import Frame, Type, Address, GatewayID, Sink as LinkSink
from .messages import (
    ReceiveRequest, ReceiveResponse,
    CommandRequest, CommandResponse,
)
from ...pv.link.slot_counter import SlotCounter
from ...pv.network import ReceivedPacketHeader, PacketTooShortError
from ...pv.network.types import LongAddress


class Sink(Protocol):
    """Interface for receiving transport-level events.
    
    Matches the Rust gateway::transport::Sink trait with all 8 methods.
    """
    
    def enumeration_started(self, enumeration_gateway_id: GatewayID) -> None:
        """Enumeration started, using the indicated gateway ID."""
        ...
    
    def gateway_identity_observed(self, gateway_id: GatewayID, address: LongAddress) -> None:
        """A gateway's hardware address was observed."""
        ...
    
    def gateway_version_observed(self, gateway_id: GatewayID, version: str) -> None:
        """A gateway's version string was observed."""
        ...
    
    def enumeration_ended(self, gateway_id: GatewayID) -> None:
        """Enumeration ended."""
        ...
    
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
    
    def command_executed(
        self,
        gateway_id: GatewayID,
        request: Tuple[int, bytes],
        response: Tuple[int, bytes],
    ) -> None:
        """A command was executed by a gateway.
        
        Args:
            gateway_id: Gateway that executed the command
            request: Tuple of (packet_type, request_payload)
            response: Tuple of (packet_type, response_payload)
        """
        ...


@dataclass
class Counters:
    """Transport receiver activity counters.
    
    Matches all counter fields from the Rust implementation.
    """
    unhandled_frame_type: int = 0
    invalid_receive_request: int = 0
    receive_requests: int = 0
    invalid_receive_responses: int = 0
    receive_response_from_unknown_gateway: int = 0
    receive_responses: int = 0
    receive_packets: int = 0
    receive_packet_too_short: int = 0
    invalid_command_requests: int = 0
    retransmitted_command_requests: int = 0
    command_requests: int = 0
    invalid_command_responses: int = 0
    retransmitted_command_responses: int = 0
    command_responses: int = 0
    ping_requests: int = 0
    ping_responses: int = 0
    enumeration_start_requests: int = 0
    invalid_enumeration_start_request: int = 0
    enumeration_start_responses: int = 0
    enumeration_requests: int = 0
    enumeration_responses: int = 0
    invalid_enumeration_responses: int = 0
    version_requests: int = 0
    version_responses: int = 0
    invalid_version_responses: int = 0
    enumeration_end_requests: int = 0
    enumeration_end_responses: int = 0
    invalid_enumeration_end_responses: int = 0
    assign_gateway_id_requests: int = 0
    assign_gateway_id_responses: int = 0
    identify_requests: int = 0
    identify_responses: int = 0
    invalid_identify_responses: int = 0


class Receiver:
    """Gateway transport layer receiver.
    
    Implements link.Sink to receive frames and dispatches them
    to transport-level handlers. Handles all 18 frame types including
    enumeration, command, identify, and version flows.
    """
    
    def __init__(self, sink: Sink):
        """Create receiver with given sink.
        
        Args:
            sink: Object implementing Sink protocol
        """
        self._sink = sink
        self._rx_packet_numbers: Dict[int, int] = {}  # gateway_id -> packet_number
        self._command_sequence_numbers: Dict[int, int] = {}  # gateway_id -> seq_num
        self._commands_awaiting_response: Dict[Tuple[int, int], Tuple[int, bytes]] = {}
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
        ft = frame.frame_type
        if ft == Type.RECEIVE_REQUEST:
            self._receive_request(frame)
        elif ft == Type.RECEIVE_RESPONSE:
            self._receive_response(frame)
        elif ft == Type.COMMAND_REQUEST:
            self._command_request(frame)
        elif ft == Type.COMMAND_RESPONSE:
            self._command_response(frame)
        elif ft == Type.PING_REQUEST:
            self._counters.ping_requests += 1
        elif ft == Type.PING_RESPONSE:
            self._counters.ping_responses += 1
        elif ft == Type.ENUMERATION_START_REQUEST:
            self._enumeration_start_request(frame)
        elif ft == Type.ENUMERATION_START_RESPONSE:
            self._counters.enumeration_start_responses += 1
        elif ft == Type.ENUMERATION_REQUEST:
            self._counters.enumeration_requests += 1
        elif ft == Type.ENUMERATION_RESPONSE:
            self._enumeration_response(frame)
        elif ft == Type.ASSIGN_GATEWAY_ID_REQUEST:
            self._counters.assign_gateway_id_requests += 1
        elif ft == Type.ASSIGN_GATEWAY_ID_RESPONSE:
            self._counters.assign_gateway_id_responses += 1
        elif ft == Type.IDENTIFY_REQUEST:
            self._counters.identify_requests += 1
        elif ft == Type.IDENTIFY_RESPONSE:
            self._identify_response(frame)
        elif ft == Type.VERSION_REQUEST:
            self._counters.version_requests += 1
        elif ft == Type.VERSION_RESPONSE:
            self._version_response(frame)
        elif ft == Type.ENUMERATION_END_REQUEST:
            self._counters.enumeration_end_requests += 1
        elif ft == Type.ENUMERATION_END_RESPONSE:
            self._enumeration_end_response(frame)
        else:
            self._counters.unhandled_frame_type += 1
    
    def _receive_request(self, frame: Frame) -> None:
        """Handle RECEIVE_REQUEST frame."""
        if frame.address.direction != 0:
            self._counters.invalid_receive_request += 1
            return
        
        gateway_id = frame.address.gateway_id
        
        request = ReceiveRequest.from_bytes(frame.payload)
        if request is None:
            self._counters.invalid_receive_request += 1
            return
        
        self._sink.gateway_slot_counter_captured(gateway_id)
        self._counters.receive_requests += 1
        self._rx_packet_numbers[gateway_id.value] = request.packet_number
    
    def _receive_response(self, frame: Frame) -> None:
        """Handle RECEIVE_RESPONSE frame."""
        if frame.address.direction != 1:
            self._counters.invalid_receive_responses += 1
            return
        
        gateway_id = frame.address.gateway_id
        
        old_packet_number = self._rx_packet_numbers.get(gateway_id.value)
        if old_packet_number is None:
            self._counters.receive_response_from_unknown_gateway += 1
            return
        
        result = ReceiveResponse.read_from_bytes(frame.payload, old_packet_number)
        if result is None:
            self._counters.invalid_receive_responses += 1
            return
        
        response, packets = result
        self._counters.receive_responses += 1
        
        self._rx_packet_numbers[gateway_id.value] = response.packet_number
        self._sink.gateway_slot_counter_observed(gateway_id, response.slot_counter)
        
        try:
            for header_bytes, data in packets:
                header = ReceivedPacketHeader.from_bytes(header_bytes)
                self._counters.receive_packets += 1
                self._sink.packet_received(gateway_id, header, data)
        except PacketTooShortError:
            self._counters.receive_packet_too_short += 1
    
    def _command_request(self, frame: Frame) -> None:
        """Handle COMMAND_REQUEST frame.
        
        Records the request so it can be correlated with the response.
        """
        if frame.address.direction != 0:
            self._counters.invalid_command_requests += 1
            return
        
        gateway_id = frame.address.gateway_id
        
        if len(frame.payload) < 5:
            self._counters.invalid_command_requests += 1
            return
        
        request = CommandRequest.from_bytes(frame.payload[:5])
        if request is None:
            self._counters.invalid_command_requests += 1
            return
        
        payload = frame.payload[5:]
        
        key = (gateway_id.value, request.sequence_number)
        self._commands_awaiting_response[key] = (request.packet_type, bytes(payload))
        
        old_seq = self._command_sequence_numbers.get(gateway_id.value)
        if old_seq is not None and old_seq == request.sequence_number:
            self._counters.retransmitted_command_requests += 1
        else:
            self._command_sequence_numbers[gateway_id.value] = request.sequence_number
            self._counters.command_requests += 1
    
    def _command_response(self, frame: Frame) -> None:
        """Handle COMMAND_RESPONSE frame.
        
        Correlates with the stored request and emits command_executed.
        """
        if frame.address.direction != 1:
            self._counters.invalid_command_responses += 1
            return
        
        gateway_id = frame.address.gateway_id
        
        if len(frame.payload) < 5:
            self._counters.invalid_command_responses += 1
            return
        
        response = CommandResponse.from_bytes(frame.payload[:5])
        if response is None:
            self._counters.invalid_command_responses += 1
            return
        
        response_payload = frame.payload[5:]
        
        key = (gateway_id.value, response.command_sequence_number)
        request_data = self._commands_awaiting_response.pop(key, None)
        if request_data is None:
            self._counters.retransmitted_command_responses += 1
            return
        
        request_packet_type, request_payload = request_data
        self._counters.command_responses += 1
        
        self._sink.command_executed(
            gateway_id,
            (request_packet_type, request_payload),
            (response.packet_type, bytes(response_payload)),
        )
    
    def _enumeration_start_request(self, frame: Frame) -> None:
        """Handle ENUMERATION_START_REQUEST frame."""
        if frame.address.direction != 0 or frame.address.gateway_id.value != 0:
            self._counters.invalid_enumeration_start_request += 1
            return
        
        if len(frame.payload) < 6:
            self._counters.invalid_enumeration_start_request += 1
            return
        
        enum_addr = Address.from_bytes(frame.payload[4:6])
        if not enum_addr.is_to:
            self._counters.invalid_enumeration_start_request += 1
            return
        
        self._counters.enumeration_start_requests += 1
        self._sink.enumeration_started(enum_addr.gateway_id)
    
    def _enumeration_response(self, frame: Frame) -> None:
        """Handle ENUMERATION_RESPONSE frame."""
        if frame.address.direction != 1:
            self._counters.invalid_enumeration_responses += 1
            return
        
        if len(frame.payload) < 8:
            self._counters.invalid_enumeration_responses += 1
            return
        
        pv_long_address = LongAddress(frame.payload[0:8])
        self._counters.enumeration_responses += 1
        self._sink.gateway_identity_observed(frame.address.gateway_id, pv_long_address)
    
    def _identify_response(self, frame: Frame) -> None:
        """Handle IDENTIFY_RESPONSE frame."""
        if frame.address.direction != 1:
            self._counters.invalid_identify_responses += 1
            return
        
        if len(frame.payload) < 8:
            self._counters.invalid_identify_responses += 1
            return
        
        pv_long_address = LongAddress(frame.payload[0:8])
        self._counters.identify_responses += 1
        self._sink.gateway_identity_observed(frame.address.gateway_id, pv_long_address)
    
    def _version_response(self, frame: Frame) -> None:
        """Handle VERSION_RESPONSE frame."""
        if frame.address.direction != 1:
            self._counters.invalid_version_responses += 1
            return
        
        try:
            version = frame.payload.decode('utf-8')
        except UnicodeDecodeError:
            self._counters.invalid_version_responses += 1
            return
        
        if not version:
            self._counters.invalid_version_responses += 1
            return
        
        self._counters.version_responses += 1
        self._sink.gateway_version_observed(frame.address.gateway_id, version)
    
    def _enumeration_end_response(self, frame: Frame) -> None:
        """Handle ENUMERATION_END_RESPONSE frame."""
        if frame.address.direction != 1:
            self._counters.invalid_enumeration_end_responses += 1
            return
        
        self._counters.enumeration_end_responses += 1
        self._sink.enumeration_ended(frame.address.gateway_id)
