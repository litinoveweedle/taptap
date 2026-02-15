"""PV application layer receiver.

Parses received PV packets and emits application-level events.
"""

from dataclasses import dataclass
from typing import Protocol

from ...gateway.link import GatewayID
from ...gateway.transport import Sink as TransportSink
from ...pv.network import ReceivedPacketHeader, NodeID, NodeAddress
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
    
    # Implement transport.Sink to forward events
    
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
        if hasattr(self._sink, 'packet_received'):
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
    
    def _handle_power_report(self, gateway_id: GatewayID, node_id: NodeID, data: bytes) -> None:
        """Parse and emit power report.
        
        Args:
            gateway_id: Gateway that received the packet
            node_id: PV node that sent the report
            data: Packet data
        """
        # Try 13-byte PowerReport first
        if len(data) == 13:
            try:
                power_report = PowerReport.from_bytes(data)
                self._counters.power_reports += 1
                self._sink.power_report(gateway_id, node_id, power_report)
                return
            except Exception:
                pass
        
        # Try 15-byte PowerReport15
        if len(data) == 15:
            try:
                power_report_15 = PowerReport15.from_bytes(data)
                self._counters.power_reports += 1
                # Extract the embedded 13-byte PowerReport
                self._sink.power_report(gateway_id, node_id, power_report_15.power_report)
                return
            except Exception:
                pass
        
        # Invalid
        self._counters.invalid_power_reports += 1
    
    def _handle_string_response(self, gateway_id: GatewayID, node_id: NodeID, data: bytes) -> None:
        """Parse and emit string response.
        
        Args:
            gateway_id: Gateway that received the packet
            node_id: PV node that sent the response
            data: Packet data
        """
        try:
            response = data.decode('utf-8')
            self._counters.string_responses += 1
            self._sink.string_response(gateway_id, node_id, response)
        except UnicodeDecodeError:
            self._counters.invalid_string_responses += 1
    
    def _handle_topology_report(self, gateway_id: GatewayID, node_id: NodeID, data: bytes) -> None:
        """Parse and emit topology report.
        
        Args:
            gateway_id: Gateway that received the packet
            node_id: PV node that sent the report
            data: Packet data
        """
        # For now, just forward the raw data
        # TODO: Parse TopologyReport structure
        self._counters.topology_reports += 1
        self._sink.topology_report(gateway_id, node_id, data)
