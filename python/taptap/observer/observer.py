"""Main Observer class for monitoring TAP protocol."""

import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import sys

from ..gateway.link import GatewayID
from ..pv.link import SlotCounter
from ..pv.network import NodeID, NodeAddress
from ..pv.network.types import LongAddress
from ..pv.application import PowerReport
from .slot_clock import SlotClock
from .event import PowerReportEvent, Event
from .persistent_state import PersistentState
from .node_table import NodeTable


class _EnumerationState:
    """Tracks an active gateway enumeration cycle.
    
    During enumeration, gateway identities and versions are collected
    and applied atomically when enumeration ends.
    """
    
    def __init__(self, enumeration_gateway_id: GatewayID):
        self.enumeration_gateway_id = enumeration_gateway_id
        self.gateway_identities: Dict[int, LongAddress] = {}
        self.gateway_versions: Dict[int, str] = {}
    
    def gateway_identity_observed(self, gateway_id: GatewayID, address: LongAddress) -> None:
        """Record a gateway identity during enumeration."""
        # Filter out the temporary enumeration address
        if gateway_id.value == self.enumeration_gateway_id.value:
            return
        self.gateway_identities[gateway_id.value] = address
    
    def gateway_version_observed(self, gateway_id: GatewayID, version: str) -> None:
        """Record a gateway version during enumeration."""
        if gateway_id.value == self.enumeration_gateway_id.value:
            return
        self.gateway_versions[gateway_id.value] = version


class Observer:
    """Observer monitors a controller interacting with TAP gateways.
    
    Implements both transport.Sink and application.Sink to receive
    all protocol events and generate JSON output.
    """
    
    def __init__(self, state_file: Optional[Path] = None):
        """Create observer with optional state file.
        
        Args:
            state_file: Path to JSON file for persistent state (optional)
        """
        self._state_file = state_file
        self._persistent_state = PersistentState()
        self._enumeration_state: Optional[_EnumerationState] = None
        self._slot_clocks: Dict[int, SlotClock] = {}  # gateway_id.value -> SlotClock
        self._captured_slot_counters: Dict[int, datetime] = {}  # gateway_id.value -> time
        self._node_table_builders: Dict[int, Dict[int, LongAddress]] = {}  # gw -> partial table
        
        # Read existing state if file exists
        self._read_persistent_state()
    
    def _read_persistent_state(self) -> None:
        """Load persistent state from JSON file if it exists."""
        if self._state_file is None:
            return
        
        if not self._state_file.exists():
            return
        
        try:
            with open(self._state_file, 'r') as f:
                data = json.load(f)
                self._persistent_state = PersistentState.from_dict(data)
            
            # Emit infrastructure event
            event = self._persistent_state.to_infrastructure_event()
            print(json.dumps(event), flush=True)
            
        except Exception as e:
            print(f"Warning: Failed to read persistent state: {e}", file=sys.stderr)
    
    def write_persistent_state(self) -> None:
        """Write persistent state to JSON file atomically."""
        if self._state_file is None:
            return
        
        try:
            # Write to temporary file first
            tmp_path = self._state_file.with_suffix('.tmp')
            with open(tmp_path, 'w') as f:
                json.dump(self._persistent_state.to_dict(), f, indent=2)
            
            # Atomic rename
            tmp_path.replace(self._state_file)
            
            # Emit infrastructure event
            event = self._persistent_state.to_infrastructure_event()
            print(json.dumps(event), flush=True)
            
        except Exception as e:
            print(f"Error: Failed to write persistent state: {e}", file=sys.stderr)
    
    # Implement transport.Sink — enumeration methods
    
    def enumeration_started(self, enumeration_gateway_id: GatewayID) -> None:
        """Enumeration started, using the indicated gateway ID.
        
        Args:
            enumeration_gateway_id: Temporary gateway ID used during enumeration
        """
        self._enumeration_state = _EnumerationState(enumeration_gateway_id)
    
    def gateway_identity_observed(self, gateway_id: GatewayID, address: LongAddress) -> None:
        """A gateway's hardware address was observed.
        
        Args:
            gateway_id: Gateway ID (may be temporary during enumeration)
            address: Gateway's 8-byte hardware address
        """
        if self._enumeration_state is not None:
            self._enumeration_state.gateway_identity_observed(gateway_id, address)
        else:
            self._persistent_state.gateway_identities[gateway_id.value] = address
            self.write_persistent_state()
    
    def gateway_version_observed(self, gateway_id: GatewayID, version: str) -> None:
        """A gateway's version string was observed.
        
        Args:
            gateway_id: Gateway ID
            version: Version string
        """
        if self._enumeration_state is not None:
            self._enumeration_state.gateway_version_observed(gateway_id, version)
        else:
            self._persistent_state.gateway_versions[gateway_id.value] = version
            self.write_persistent_state()
    
    def enumeration_ended(self, gateway_id: GatewayID) -> None:
        """Enumeration ended — apply collected identities atomically.
        
        Args:
            gateway_id: Gateway ID that ended enumeration
        """
        if self._enumeration_state is not None:
            # Replace persistent state with enumeration results
            self._persistent_state.gateway_identities = self._enumeration_state.gateway_identities
            self._persistent_state.gateway_versions = self._enumeration_state.gateway_versions
            self._enumeration_state = None
            self.write_persistent_state()
    
    # Implement transport.Sink — slot counter methods
    
    def gateway_slot_counter_captured(self, gateway_id: GatewayID) -> None:
        """Gateway captured its slot counter (in RECEIVE_REQUEST).
        
        Args:
            gateway_id: Gateway that captured the counter
        """
        self._captured_slot_counters[gateway_id.value] = datetime.now()
    
    def gateway_slot_counter_observed(self, gateway_id: GatewayID, slot_counter: SlotCounter) -> None:
        """Gateway slot counter was observed (in RECEIVE_RESPONSE).
        
        Args:
            gateway_id: Gateway ID
            slot_counter: Observed slot counter value
        """
        # Get the capture time
        capture_time = self._captured_slot_counters.pop(gateway_id.value, None)
        if capture_time is None:
            return
        
        # Update or create slot clock
        if gateway_id.value in self._slot_clocks:
            try:
                self._slot_clocks[gateway_id.value].set(slot_counter, capture_time)
            except Exception:
                pass
        else:
            try:
                clock = SlotClock(slot_counter, capture_time)
                self._slot_clocks[gateway_id.value] = clock
            except Exception:
                pass
    
    def packet_received(
        self,
        gateway_id: GatewayID,
        header: 'ReceivedPacketHeader',
        data: bytes
    ) -> None:
        """PV packet was received (no-op at observer level)."""
        pass
    
    def command_executed(
        self,
        gateway_id: GatewayID,
        request: Tuple[int, bytes],
        response: Tuple[int, bytes],
    ) -> None:
        """Command was executed (no-op at observer level)."""
        pass
    
    # Implement application.Sink
    
    def string_request(self, gateway_id: GatewayID, pv_node_id: NodeID, request: str) -> None:
        """String request was sent."""
        pass
    
    def string_response(self, gateway_id: GatewayID, pv_node_id: NodeID, response: str) -> None:
        """String response was received."""
        pass
    
    def node_table_page(
        self,
        gateway_id: GatewayID,
        start_address: NodeAddress,
        nodes: list
    ) -> None:
        """Node table page was received — accumulate into node table.
        
        Args:
            gateway_id: Gateway ID
            start_address: Starting address of this page
            nodes: List of (NodeAddress, LongAddress) tuples
        """
        gw_val = gateway_id.value
        
        # Get or create builder for this gateway
        if gw_val not in self._node_table_builders:
            self._node_table_builders[gw_val] = {}
        
        builder = self._node_table_builders[gw_val]
        
        # Add entries from this page
        for node_addr, long_addr in nodes:
            node_id = node_addr.to_node_id()
            if node_id is not None:
                builder[node_id.value] = long_addr
        
        # If this page is empty or incomplete, the table is complete
        if len(nodes) == 0:
            # Build final node table
            table = NodeTable()
            for nid_val, addr in builder.items():
                table.set(NodeID(nid_val), addr)
            
            self._persistent_state.gateway_node_tables[gw_val] = table
            del self._node_table_builders[gw_val]
            self.write_persistent_state()
    
    def topology_report(
        self,
        gateway_id: GatewayID,
        pv_node_id: NodeID,
        topology_report: bytes
    ) -> None:
        """Topology report was received."""
        pass
    
    def power_report(
        self,
        gateway_id: GatewayID,
        pv_node_id: NodeID,
        power_report: PowerReport
    ) -> None:
        """Power report was received - generate JSON event.
        
        Args:
            gateway_id: Gateway that received the report
            pv_node_id: PV node that sent the report
            power_report: Parsed power report
        """
        # Get slot clock for this gateway
        slot_clock = self._slot_clocks.get(gateway_id.value)
        if slot_clock is None:
            print(
                f"Warning: Discarding power report from gateway {gateway_id} "
                f"due to missing slot clock",
                file=sys.stderr
            )
            return
        
        # Create PowerReportEvent
        try:
            event_payload = PowerReportEvent.from_power_report(
                gateway_id,
                pv_node_id,
                slot_clock,
                power_report
            )
        except Exception as e:
            print(
                f"Warning: Discarding power report from gateway {gateway_id} "
                f"due to invalid slot counter: {e}",
                file=sys.stderr
            )
            return
        
        # Wrap in Event envelope
        event = Event.power_report(event_payload)
        
        # Output as JSON
        print(json.dumps(event.to_dict()), flush=True)
