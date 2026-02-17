"""PV application layer receiver.

Parses received PV packets and emits application-level events.
"""

from dataclasses import dataclass
from typing import Protocol, Tuple

from ...gateway.link import GatewayID
from ...gateway.transport import Sink as TransportSink
from ...pv.network import ReceivedPacketHeader, NodeID, NodeAddress
from ...pv.network.types import LongAddress
from ...pv.link import SlotCounter
from .types import PacketType, PowerReport, PowerReport15


class Sink(Protocol):
    """Interface for receiving application-level events."""
    
    def string_request(self, gateway_id: GatewayID, pv_node_id: NodeID, request: str) -> None:
        """String request was sent to a PV node."""
        ...
    
    def string_response(self, gateway_id: GatewayID, pv_node_id: NodeID, response: str) -> None:
        """String response was received from a PV node."""
        ...
    
    def node_table_page(
        self,
        gateway_id: GatewayID,
        start_address: NodeAddress,
        nodes: list
    ) -> None:
        """Node table page was received."""
        ...
    
    def topology_report(
        self,
        gateway_id: GatewayID,
        pv_node_id: NodeID,
        topology_report: bytes
    ) -> None:
        """Topology report was received."""
        ...
    
    def power_report(
        self,
        gateway_id: GatewayID,
        pv_node_id: NodeID,
        power_report: PowerReport
    ) -> None:
        """Power report was received from a PV node."""
        ...


@dataclass
class Counters:
    """PV application receiver activity counters."""
    invalid_received_packet_node_ids: int = 0
    invalid_power_reports: int = 0
    power_reports: int = 0
    invalid_topology_reports: int = 0
    topology_reports: int = 0
    invalid_string_responses: int = 0
    string_responses: int = 0
    invalid_node_table_requests: int = 0
    invalid_node_table_responses: int = 0
    invalid_string_commands: int = 0
    string_commands: int = 0


class Receiver:
    """PV application layer receiver.
    
    Wraps a sink that implements both transport.Sink and application.Sink,
    forwarding transport events and parsing packets into application events.
    """
    
    def __init__(self, sink):
        """Create receiver with given sink.
        
        Args:
            sink: Object implementing both TransportSink and Sink protocols
        """
        self._sink = sink
        self._counters = Counters()
    
    @property
    def sink(self):
        """Access the sink."""
        return self._sink
    
    @property
    def counters(self) -> Counters:
        """Get current counters."""
        return self._counters
    
    # Forward all transport.Sink events
    
    def enumeration_started(self, enumeration_gateway_id: GatewayID) -> None:
        """Forward to sink."""
        self._sink.enumeration_started(enumeration_gateway_id)
    
    def gateway_identity_observed(self, gateway_id: GatewayID, address: LongAddress) -> None:
        """Forward to sink."""
        self._sink.gateway_identity_observed(gateway_id, address)
    
    def gateway_version_observed(self, gateway_id: GatewayID, version: str) -> None:
        """Forward to sink."""
        self._sink.gateway_version_observed(gateway_id, version)
    
    def enumeration_ended(self, gateway_id: GatewayID) -> None:
        """Forward to sink."""
        self._sink.enumeration_ended(gateway_id)
    
    def gateway_slot_counter_captured(self, gateway_id: GatewayID) -> None:
        """Forward to sink."""
        self._sink.gateway_slot_counter_captured(gateway_id)
    
    def gateway_slot_counter_observed(self, gateway_id: GatewayID, slot_counter: SlotCounter) -> None:
        """Forward to sink."""
        self._sink.gateway_slot_counter_observed(gateway_id, slot_counter)
    
    def packet_received(
        self,
        gateway_id: GatewayID,
        header: ReceivedPacketHeader,
        data: bytes
    ) -> None:
        """Parse packet and emit application-level events.
        
        Args:
            gateway_id: Gateway that received the packet
            header: Parsed packet header
            data: Packet payload data
        """
        # Forward to sink first
        self._sink.packet_received(gateway_id, header, data)
        
        # Try to get node_id from node_address
        try:
            node_id = NodeID.from_node_address(header.node_address)
        except ValueError:
            self._counters.invalid_received_packet_node_ids += 1
            return
        
        # Dispatch by packet type
        if header.packet_type == PacketType.POWER_REPORT:
            self._handle_power_report(gateway_id, node_id, data)
        elif header.packet_type == PacketType.STRING_RESPONSE:
            self._handle_string_response(gateway_id, node_id, data)
        elif header.packet_type == PacketType.TOPOLOGY_REPORT:
            self._handle_topology_report(gateway_id, node_id, data)
    
    def command_executed(
        self,
        gateway_id: GatewayID,
        request: Tuple[int, bytes],
        response: Tuple[int, bytes],
    ) -> None:
        """Handle command execution — dispatch by packet type pair.
        
        Args:
            gateway_id: Gateway that executed the command
            request: Tuple of (packet_type, request_payload)
            response: Tuple of (packet_type, response_payload)
        """
        # Forward raw command to sink
        self._sink.command_executed(gateway_id, request, response)
        
        req_type, req_data = request
        resp_type, resp_data = response
        
        if req_type == PacketType.NODE_TABLE_REQUEST and resp_type == PacketType.NODE_TABLE_RESPONSE:
            self._node_table_command(gateway_id, req_data, resp_data)
        elif req_type == PacketType.STRING_REQUEST and resp_type == PacketType.STRING_RESPONSE:
            self._string_command(gateway_id, req_data, resp_data)
    
    def _handle_power_report(self, gateway_id: GatewayID, node_id: NodeID, data: bytes) -> None:
        """Parse and emit power report."""
        if len(data) == 13:
            try:
                power_report = PowerReport.from_bytes(data)
                self._counters.power_reports += 1
                self._sink.power_report(gateway_id, node_id, power_report)
                return
            except Exception:
                pass
        
        if len(data) == 15:
            try:
                power_report_15 = PowerReport15.from_bytes(data)
                self._counters.power_reports += 1
                self._sink.power_report(gateway_id, node_id, power_report_15.power_report)
                return
            except Exception:
                pass
        
        self._counters.invalid_power_reports += 1
    
    def _handle_string_response(self, gateway_id: GatewayID, node_id: NodeID, data: bytes) -> None:
        """Parse and emit string response."""
        try:
            response = data.decode('utf-8')
            self._counters.string_responses += 1
            self._sink.string_response(gateway_id, node_id, response)
        except UnicodeDecodeError:
            self._counters.invalid_string_responses += 1
    
    def _handle_topology_report(self, gateway_id: GatewayID, node_id: NodeID, data: bytes) -> None:
        """Parse and emit topology report."""
        # TODO: Parse TopologyReport structure
        self._counters.topology_reports += 1
        self._sink.topology_report(gateway_id, node_id, data)
    
    def _node_table_command(self, gateway_id: GatewayID, request_data: bytes, response_data: bytes) -> None:
        """Parse node table command and emit node_table_page.
        
        Request format: 2 bytes start_at (NodeAddress)
        Response format: 1 byte entries_count, then entries_count * 10 bytes
                         (2 bytes NodeAddress + 8 bytes LongAddress per entry)
        """
        # Parse request: start_at address
        if len(request_data) < 2:
            self._counters.invalid_node_table_requests += 1
            return
        
        start_address = NodeAddress.from_bytes(request_data[0:2])
        
        # Parse response: entries_count + entries
        if len(response_data) < 1:
            self._counters.invalid_node_table_responses += 1
            return
        
        entries_count = response_data[0]
        entries_data = response_data[1:]
        
        # Each entry is 10 bytes: 2 bytes NodeAddress + 8 bytes LongAddress
        if len(entries_data) != entries_count * 10:
            self._counters.invalid_node_table_responses += 1
            return
        
        nodes = []
        for i in range(entries_count):
            offset = i * 10
            node_addr = NodeAddress.from_bytes(entries_data[offset:offset+2])
            long_addr = LongAddress(entries_data[offset+2:offset+10])
            nodes.append((node_addr, long_addr))
        
        self._sink.node_table_page(gateway_id, start_address, nodes)
    
    def _string_command(self, gateway_id: GatewayID, request_data: bytes, response_data: bytes) -> None:
        """Parse string command and emit string_request.
        
        Request format: 2 bytes NodeAddress + UTF-8 string
        Response format: empty (expected)
        """
        if len(request_data) < 2:
            self._counters.invalid_string_commands += 1
            return
        
        node_addr = NodeAddress.from_bytes(request_data[0:2])
        
        try:
            node_id = NodeID.from_node_address(node_addr)
        except ValueError:
            self._counters.invalid_string_commands += 1
            return
        
        try:
            request_str = request_data[2:].decode('utf-8')
        except UnicodeDecodeError:
            self._counters.invalid_string_commands += 1
            return
        
        self._counters.string_commands += 1
        self._sink.string_request(gateway_id, node_id, request_str)
