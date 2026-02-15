"""Tests for observer event types."""

import pytest
from datetime import datetime
import json

from taptap.observer.event import PowerReportEvent, Gateway, Node
from taptap.gateway.link.address import GatewayID
from taptap.pv.network.types import NodeID, RSSI


def test_power_report_event_creation():
    """Test creating a power report event."""
    now = datetime.now()
    event = PowerReportEvent(
        gateway=4609,
        node=116,
        timestamp=now,
        voltage_in=30.5,
        voltage_out=30.0,
        current=2.5,
        dc_dc_duty_cycle=1.0,
        temperature=25.5,
        rssi=132
    )
    
    assert event.gateway == 4609
    assert event.node == 116
    assert event.voltage_in == 30.5
    assert event.current == 2.5
    assert event.temperature == 25.5


def test_power_report_event_to_json():
    """Test converting power report event to JSON."""
    now = datetime(2024, 8, 24, 9, 16, 41)
    event = PowerReportEvent(
        gateway=4609,
        node=116,
        timestamp=now,
        voltage_in=30.5,
        voltage_out=30.0,
        current=2.5,
        dc_dc_duty_cycle=1.0,
        temperature=25.5,
        rssi=132
    )
    
    json_str = event.to_json()
    data = json.loads(json_str)
    
    assert data['event_type'] == 'power_report'
    assert data['gateway'] == 4609
    assert data['node'] == 116
    assert data['voltage_in'] == 30.5
    assert data['current'] == 2.5
    assert data['rssi'] == 132


def test_power_report_event_from_power_report():
    """Test creating event from power report data."""
    from taptap.pv.application import PowerReport
    from taptap.observer.slot_clock import SlotClock
    from taptap.pv.link import SlotCounter
    
    gateway_id = GatewayID(4609)
    node_id = NodeID(116)
    
    # Create a slot clock
    slot_counter = SlotCounter.from_u16(0x1234)
    now = datetime.now()
    slot_clock = SlotClock(slot_counter, now)
    
    # Create a power report
    power_data = bytes([
        0x12, 0x34,  # slot_counter
        0x0A, 0xBC,  # voltage_in
        0xC1, 0x23,  # voltages
        0x45,  # voltage_out
        0x67, 0x89,  # current
        0xAB,  # dc_dc_duty_cycle
        0xCD, 0xEF,  # temperature
        0x84,  # rssi (132)
    ])
    power_report = PowerReport.from_bytes(power_data)
    
    event = PowerReportEvent.from_power_report(
        gateway_id=gateway_id,
        node_id=node_id,
        slot_clock=slot_clock,
        power_report=power_report
    )
    
    assert event.gateway == 4609
    assert event.node == 116
    assert event.rssi == 132
    assert event.rssi == 132


def test_gateway_to_dict():
    """Test Gateway to_dict."""
    gw = Gateway(id=4609)
    assert gw.to_dict() == {'id': 4609}
    
    gw_with_addr = Gateway(id=4609, address='04:C0:5B:30:12:34:56:78')
    assert gw_with_addr.to_dict() == {
        'id': 4609,
        'address': '04:C0:5B:30:12:34:56:78'
    }


def test_node_to_dict():
    """Test Node to_dict."""
    node = Node(id=116)
    assert node.to_dict() == {'id': 116}
    
    node_with_data = Node(
        id=116,
        address='04:C0:5B:40:00:9A:57:A2',
        barcode='4-9A57A2L'
    )
    assert node_with_data.to_dict() == {
        'id': 116,
        'address': '04:C0:5B:40:00:9A:57:A2',
        'barcode': '4-9A57A2L'
    }
