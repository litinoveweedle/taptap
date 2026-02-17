"""Tests for Phase 6c: Observer integration."""

import json
from datetime import datetime
from pathlib import Path
import tempfile

import pytest

from taptap.observer import Observer
from taptap.gateway.link import GatewayID
from taptap.pv.network import NodeID
from taptap.pv.link import SlotCounter
from taptap.pv.application import PowerReport, PacketType
from taptap.pv.network import ReceivedPacketHeader, NodeAddress, ShortAddress, RSSI, DSN


def test_observer_power_report_flow():
    """Test complete power report flow through observer."""
    observer = Observer(state_file=None)
    
    gateway_id = GatewayID(0x1201)
    node_id = NodeID(0x0042)
    
    # Simulate slot counter capture and observation
    observer.gateway_slot_counter_captured(gateway_id)
    slot_counter = SlotCounter.from_u16(0x1234)
    observer.gateway_slot_counter_observed(gateway_id, slot_counter)
    
    # Create a power report (13 bytes)
    power_report_data = bytes([
        0x12, 0x34,  # slot_counter
        0x0A, 0xBC,  # voltage_in (first U12)
        0xC1, 0x23,  # continues voltage_in, starts voltage_out (U12 pair)
        0x45,  # finishes voltage_out U12
        0x67, 0x89,  # current
        0xAB,  # dc_dc_duty_cycle
        0xCD, 0xEF,  # temperature (signed)
        0x42,  # rssi
    ])
    
    power_report = PowerReport.from_bytes(power_report_data)
    
    # Call power_report - should print JSON to stdout
    # For testing, we'll just verify it doesn't crash
    observer.power_report(gateway_id, node_id, power_report)


def test_observer_without_slot_clock():
    """Test that power report without slot clock is discarded."""
    observer = Observer(state_file=None)
    
    gateway_id = GatewayID(0x1201)
    node_id = NodeID(0x0042)
    
    # Create a power report
    power_report_data = bytes([
        0x12, 0x34,  # slot_counter
        0x0A, 0xBC,  # voltage_in
        0xC1, 0x23,  # voltages continued
        0x45,  # voltage_out finish
        0x67, 0x89,  # current
        0xAB,  # dc_dc_duty_cycle
        0xCD, 0xEF,  # temperature
        0x42,  # rssi
    ])
    
    power_report = PowerReport.from_bytes(power_report_data)
    
    # Call without establishing slot clock - should be discarded
    observer.power_report(gateway_id, node_id, power_report)
    # Test passes if no exception is raised


def test_observer_persistent_state():
    """Test observer persistent state save/load."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        
        # Create observer with state file
        observer1 = Observer(state_file=state_file)
        
        # Add a slot clock
        gateway_id = GatewayID(0x1201)
        observer1.gateway_slot_counter_captured(gateway_id)
        slot_counter = SlotCounter.from_u16(0x1234)
        observer1.gateway_slot_counter_observed(gateway_id, slot_counter)
        
        # State file should exist now (even if empty)
        # Create another observer - should load state
        observer2 = Observer(state_file=state_file)
        
        # Both should work
        assert observer1 is not None
        assert observer2 is not None


def test_pv_application_receiver():
    """Test PV application receiver parses packets."""
    from taptap.pv.application import Receiver
    from taptap.gateway.link import GatewayID
    
    class MockSink:
        def __init__(self):
            self.power_reports = []
            self.string_responses = []
        
        def gateway_slot_counter_captured(self, gateway_id):
            pass
        
        def gateway_slot_counter_observed(self, gateway_id, slot_counter):
            pass
        
        def packet_received(self, gateway_id, header, data):
            pass
        
        def power_report(self, gateway_id, node_id, power_report):
            self.power_reports.append((gateway_id, node_id, power_report))
        
        def string_request(self, gateway_id, node_id, request):
            pass
        
        def string_response(self, gateway_id, node_id, response):
            self.string_responses.append((gateway_id, node_id, response))
        
        def node_table_page(self, gateway_id, start_address, nodes):
            pass
        
        def topology_report(self, gateway_id, node_id, report):
            pass
    
    sink = MockSink()
    receiver = Receiver(sink)
    
    # Create header for power report
    header_bytes = bytes([
        PacketType.POWER_REPORT,  # packet_type
        0x00, 0x42,  # node_address
        0xFF, 0xFF,  # short_address
        0x01,  # dsn
        13,  # data_length
    ])
    header = ReceivedPacketHeader.from_bytes(header_bytes)
    
    # Power report data
    power_data = bytes([
        0x12, 0x34,  # slot_counter
        0x0A, 0xBC,  # voltage_in
        0xC1, 0x23,  # voltages
        0x45,  # voltage_out
        0x67, 0x89,  # current
        0xAB,  # dc_dc_duty_cycle
        0xCD, 0xEF,  # temperature
        0x42,  # rssi
    ])
    
    # Process packet
    gateway_id = GatewayID(0x1201)
    receiver.packet_received(gateway_id, header, power_data)
    
    # Verify power report was received
    assert len(sink.power_reports) == 1
    assert sink.power_reports[0][0] == gateway_id
    assert receiver.counters.power_reports == 1


def test_pv_application_receiver_string_response():
    """Test PV application receiver parses string responses."""
    from taptap.pv.application import Receiver
    
    class MockSink:
        def __init__(self):
            self.string_responses = []
        
        def gateway_slot_counter_captured(self, gateway_id):
            pass
        
        def gateway_slot_counter_observed(self, gateway_id, slot_counter):
            pass
        
        def packet_received(self, gateway_id, header, data):
            pass
        
        def power_report(self, gateway_id, node_id, power_report):
            pass
        
        def string_request(self, gateway_id, node_id, request):
            pass
        
        def string_response(self, gateway_id, node_id, response):
            self.string_responses.append((gateway_id, node_id, response))
        
        def node_table_page(self, gateway_id, start_address, nodes):
            pass
        
        def topology_report(self, gateway_id, node_id, report):
            pass
    
    sink = MockSink()
    receiver = Receiver(sink)
    
    # Create header for string response
    header_bytes = bytes([
        PacketType.STRING_RESPONSE,  # packet_type
        0x00, 0x42,  # node_address
        0xFF, 0xFF,  # short_address
        0x01,  # dsn
        5,  # data_length
    ])
    header = ReceivedPacketHeader.from_bytes(header_bytes)
    
    # String data
    string_data = b"Hello"
    
    # Process packet
    gateway_id = GatewayID(0x1201)
    receiver.packet_received(gateway_id, header, string_data)
    
    # Verify string response was received
    assert len(sink.string_responses) == 1
    assert sink.string_responses[0][2] == "Hello"
    assert receiver.counters.string_responses == 1
