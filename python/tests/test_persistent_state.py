"""Tests for persistent state."""

import pytest
import json
import tempfile
from pathlib import Path

from taptap.observer.persistent_state import PersistentState
from taptap.observer.node_table import NodeTable
from taptap.gateway.link.address import GatewayID
from taptap.pv.network.types import NodeID, LongAddress


def test_persistent_state_empty():
    """Test empty persistent state."""
    state = PersistentState()
    
    assert len(state.gateway_identities) == 0
    assert len(state.gateway_versions) == 0
    assert len(state.gateway_node_tables) == 0


def test_persistent_state_add_gateway():
    """Test adding gateway identity."""
    state = PersistentState()
    
    addr = LongAddress(bytes.fromhex('04C05B3012345678'))
    state.gateway_identities[4609] = addr
    state.gateway_versions[4609] = 'Mgate Version 1.2.3'
    
    assert state.gateway_identities[4609] == addr
    assert state.gateway_versions[4609] == 'Mgate Version 1.2.3'


def test_persistent_state_add_nodes():
    """Test adding node table."""
    state = PersistentState()
    
    table = NodeTable()
    table.set(NodeID(116), LongAddress(bytes.fromhex('04C05B40009A57A2')))
    table.set(NodeID(82), LongAddress(bytes.fromhex('04C05B40009A57A3')))
    
    state.gateway_node_tables[4609] = table
    
    assert len(state.gateway_node_tables[4609]) == 2


def test_persistent_state_save_load():
    """Test saving and loading persistent state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / 'state.json'
        
        # Create state
        state = PersistentState()
        addr = LongAddress(bytes.fromhex('04C05B3012345678'))
        state.gateway_identities[4609] = addr
        state.gateway_versions[4609] = 'Version 1.0'
        
        table = NodeTable()
        table.set(NodeID(116), LongAddress(bytes.fromhex('04C05B40009A57A2')))
        state.gateway_node_tables[4609] = table
        
        # Save
        state.save(path)
        
        assert path.exists()
        
        # Load
        loaded = PersistentState.load(path)
        
        assert loaded.gateway_identities[4609] == addr
        assert loaded.gateway_versions[4609] == 'Version 1.0'
        assert len(loaded.gateway_node_tables[4609]) == 1


def test_persistent_state_load_nonexistent():
    """Test loading from nonexistent file returns empty state."""
    path = Path('/tmp/nonexistent_file_12345.json')
    state = PersistentState.load(path)
    
    assert len(state.gateway_identities) == 0
    assert len(state.gateway_versions) == 0
    assert len(state.gateway_node_tables) == 0


def test_persistent_state_to_infrastructure_event():
    """Test converting to infrastructure event."""
    state = PersistentState()
    
    addr = LongAddress(bytes.fromhex('04C05B3012345678'))
    state.gateway_identities[4609] = addr
    state.gateway_versions[4609] = 'Version 1.0'
    
    table = NodeTable()
    table.set(NodeID(116), LongAddress(bytes.fromhex('04C05B40009A57A2')))
    state.gateway_node_tables[4609] = table
    
    event = state.to_infrastructure_event()
    
    assert event['event_type'] == 'infrastructure_report'
    assert '4609' in event['gateways']
    assert event['gateways']['4609']['address'] == '04:C0:5B:30:12:34:56:78'
    assert event['gateways']['4609']['version'] == 'Version 1.0'
    
    assert '4609' in event['nodes']
    assert '116' in event['nodes']['4609']
    assert event['nodes']['4609']['116']['address'] == '04:C0:5B:40:00:9A:57:A2'
    assert event['nodes']['4609']['116']['barcode'] == '4-9A57A2L'


def test_persistent_state_save_atomic():
    """Test that save is atomic (uses temp file)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / 'state.json'
        
        state = PersistentState()
        state.gateway_versions[4609] = 'Version 1.0'
        
        # Save
        state.save(path)
        
        # Temp file should not exist after save
        temp_path = path.with_suffix('.tmp')
        assert not temp_path.exists()
        
        # Main file should exist
        assert path.exists()


def test_persistent_state_json_format():
    """Test JSON format is correct."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / 'state.json'
        
        state = PersistentState()
        addr = LongAddress(bytes.fromhex('04C05B3012345678'))
        state.gateway_identities[4609] = addr
        state.gateway_versions[4609] = 'Version 1.0'
        
        state.save(path)
        
        # Read raw JSON
        with open(path, 'r') as f:
            data = json.load(f)
        
        assert 'gateway_identities' in data
        assert 'gateway_versions' in data
        assert 'gateway_node_tables' in data
        
        # Check format
        assert data['gateway_identities']['4609'] == '04:C0:5B:30:12:34:56:78'
        assert data['gateway_versions']['4609'] == 'Version 1.0'
