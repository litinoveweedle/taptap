"""Main Observer class for monitoring TAP protocol."""

import json
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import sys

from ..gateway.link import GatewayID
from ..pv.link import SlotCounter
from ..pv.network import NodeID, NodeAddress
from ..pv.application import PowerReport
from .slot_clock import SlotClock
from .event import PowerReportEvent, Event
from .persistent_state import PersistentState


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
        self._slot_clocks: Dict[int, SlotClock] = {}  # gateway_id.value -> SlotClock
        self._captured_slot_counters: Dict[int, datetime] = {}  # gateway_id.value -> time
        
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
            event = self._persistent_state.to_event()
            print(json.dumps(event.to_dict()), flush=True)
            
        except Exception as e:
            print(f"Warning: Failed to read persistent state: {e}", file=sys.stderr)
    
    def _write_persistent_state(self) -> None:
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
            event = self._persistent_state.to_event()
            print(json.dumps(event.to_dict()), flush=True)
            
        except Exception as e:
            print(f"Error: Failed to write persistent state: {e}", file=sys.stderr)
    
    # Implement transport.Sink
    
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
            # Update existing clock
            try:
                self._slot_clocks[gateway_id.value].set(slot_counter, capture_time)
            except Exception:
                pass  # Ignore errors
        else:
            # Create new clock
            try:
                clock = SlotClock(slot_counter, capture_time)
                self._slot_clocks[gateway_id.value] = clock
            except Exception:
                pass  # Ignore errors
    
    def packet_received(
        self,
        gateway_id: GatewayID,
        header: 'ReceivedPacketHeader',
        data: bytes
    ) -> None:
        """PV packet was received (optional hook for debugging).
        
        Args:
            gateway_id: Gateway that received the packet
            header: Packet header
            data: Packet data
        """
        # This is called by application receiver before parsing
        # We don't need to do anything here - the parsed events will come
        # through application.Sink methods
        pass
    
    # Implement application.Sink
    
    def string_request(self, gateway_id: GatewayID, pv_node_id: NodeID, request: str) -> None:
        """String request was sent (not currently used)."""
        pass
    
    def string_response(self, gateway_id: GatewayID, pv_node_id: NodeID, response: str) -> None:
        """String response was received (not currently used)."""
        pass
    
    def node_table_page(
        self,
        gateway_id: GatewayID,
        start_address: NodeAddress,
        nodes: list
    ) -> None:
        """Node table page was received (not currently used)."""
        pass
    
    def topology_report(
        self,
        gateway_id: GatewayID,
        pv_node_id: NodeID,
        topology_report: bytes
    ) -> None:
        """Topology report was received (not currently used)."""
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
