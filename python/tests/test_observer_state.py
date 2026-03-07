"""Tests for Observer + PersistentState integration (TEST-4).

Tests enumeration state machine, persistent state round-trips,
and node table accumulation in the Observer.
"""

import json
import tempfile
from pathlib import Path

import pytest

from taptap.observer.observer import Observer, _EnumerationState
from taptap.observer.persistent_state import PersistentState
from taptap.observer.node_table import NodeTable
from taptap.gateway.link import GatewayID
from taptap.pv.network import NodeID, NodeAddress
from taptap.pv.network.types import LongAddress
from taptap.pv.link import SlotCounter


# ---------------------------------------------------------------------------
# PersistentState serialization round-trip
# ---------------------------------------------------------------------------

def test_persistent_state_to_dict_empty():
    """Empty state serializes to empty dicts."""
    state = PersistentState()
    d = state.to_dict()

    assert d == {
        "gateway_identities": {},
        "gateway_versions": {},
        "gateway_node_tables": {},
    }


def test_persistent_state_roundtrip():
    """to_dict → from_dict preserves data."""
    addr = LongAddress(bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]))
    state = PersistentState()
    state.gateway_identities[1] = addr
    state.gateway_versions[1] = "2.0.0"

    table = NodeTable()
    node_addr = LongAddress(bytes([0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7]))
    table.set(NodeID(42), node_addr)
    state.gateway_node_tables[1] = table

    d = state.to_dict()
    restored = PersistentState.from_dict(d)

    assert restored.gateway_identities[1] == addr
    assert restored.gateway_versions[1] == "2.0.0"
    assert restored.gateway_node_tables[1].get(NodeID(42)) == node_addr


def test_persistent_state_save_load(tmp_path):
    """save() and load() round-trip through JSON file."""
    addr = LongAddress(bytes(range(8)))
    state = PersistentState()
    state.gateway_identities[5] = addr
    state.gateway_versions[5] = "1.0"

    path = tmp_path / "state.json"
    state.save(path)

    loaded = PersistentState.load(path)
    assert loaded.gateway_identities[5] == addr
    assert loaded.gateway_versions[5] == "1.0"


def test_persistent_state_load_nonexistent(tmp_path):
    """Loading from a missing file returns empty state."""
    loaded = PersistentState.load(tmp_path / "nope.json")
    assert len(loaded.gateway_identities) == 0


def test_persistent_state_from_dict_empty():
    """from_dict with empty dict returns empty state."""
    state = PersistentState.from_dict({})
    assert len(state.gateway_identities) == 0
    assert len(state.gateway_versions) == 0
    assert len(state.gateway_node_tables) == 0


def test_infrastructure_event():
    """to_infrastructure_event produces expected shape."""
    addr = LongAddress(bytes([0x04, 0xC0, 0x5B, 0x40, 0x00, 0x00, 0x00, 0x01]))
    state = PersistentState()
    state.gateway_identities[1] = addr
    state.gateway_versions[1] = "2.0.0"

    evt = state.to_infrastructure_event()
    assert evt["event_type"] == "infrastructure_report"
    assert "1" in evt["gateways"]
    assert evt["gateways"]["1"]["version"] == "2.0.0"


# ---------------------------------------------------------------------------
# _EnumerationState unit tests
# ---------------------------------------------------------------------------

def test_enumeration_state_filters_enum_gateway():
    """Enumeration state ignores the temporary enumeration gateway ID."""
    es = _EnumerationState(GatewayID(0x0005))

    # This should be filtered out
    es.gateway_identity_observed(
        GatewayID(0x0005),
        LongAddress(bytes(8)),
    )
    assert len(es.gateway_identities) == 0

    # This should be kept
    es.gateway_identity_observed(
        GatewayID(0x0001),
        LongAddress(bytes(8)),
    )
    assert len(es.gateway_identities) == 1


def test_enumeration_state_versions():
    """Enumeration state collects gateway versions."""
    es = _EnumerationState(GatewayID(0x0005))
    es.gateway_version_observed(GatewayID(0x0001), "1.0")
    es.gateway_version_observed(GatewayID(0x0002), "2.0")
    # Filtered
    es.gateway_version_observed(GatewayID(0x0005), "ignored")

    assert len(es.gateway_versions) == 2
    assert es.gateway_versions[1] == "1.0"
    assert es.gateway_versions[2] == "2.0"


# ---------------------------------------------------------------------------
# Observer enumeration integration
# ---------------------------------------------------------------------------

def test_observer_enumeration_cycle(tmp_path, capsys):
    """Full enumeration cycle updates persistent state atomically."""
    state_file = tmp_path / "state.json"
    obs = Observer(state_file=state_file)

    gw1_addr = LongAddress(bytes([0x01] * 8))
    gw2_addr = LongAddress(bytes([0x02] * 8))
    enum_gw = GatewayID(0x0005)

    # Start enumeration
    obs.enumeration_started(enum_gw)

    # Identities during enumeration
    obs.gateway_identity_observed(GatewayID(1), gw1_addr)
    obs.gateway_identity_observed(GatewayID(2), gw2_addr)
    # Temporary address — should be filtered
    obs.gateway_identity_observed(enum_gw, LongAddress(bytes(8)))

    # Versions during enumeration
    obs.gateway_version_observed(GatewayID(1), "v1")
    obs.gateway_version_observed(GatewayID(2), "v2")

    # End enumeration
    obs.enumeration_ended(GatewayID(1))

    # Persistent state should have 2 gateways (not 3)
    assert len(obs._persistent_state.gateway_identities) == 2
    assert obs._persistent_state.gateway_identities[1] == gw1_addr
    assert obs._persistent_state.gateway_identities[2] == gw2_addr
    assert obs._persistent_state.gateway_versions[1] == "v1"

    # State file should have been written
    assert state_file.exists()
    with open(state_file, "r") as f:
        data = json.load(f)
    assert len(data["gateway_identities"]) == 2


def test_observer_identity_without_enumeration(tmp_path, capsys):
    """Identity outside enumeration updates state immediately."""
    state_file = tmp_path / "state.json"
    obs = Observer(state_file=state_file)

    addr = LongAddress(bytes([0xAA] * 8))
    obs.gateway_identity_observed(GatewayID(1), addr)

    assert obs._persistent_state.gateway_identities[1] == addr
    assert state_file.exists()


def test_observer_version_without_enumeration(tmp_path, capsys):
    """Version outside enumeration updates state immediately."""
    state_file = tmp_path / "state.json"
    obs = Observer(state_file=state_file)

    obs.gateway_version_observed(GatewayID(1), "3.0.0")

    assert obs._persistent_state.gateway_versions[1] == "3.0.0"


# ---------------------------------------------------------------------------
# Observer node table accumulation
# ---------------------------------------------------------------------------

def test_observer_node_table_accumulation(tmp_path, capsys):
    """Node table pages accumulate until empty page signals completion."""
    state_file = tmp_path / "state.json"
    obs = Observer(state_file=state_file)

    gw = GatewayID(1)
    node1 = (NodeAddress(2), LongAddress(bytes([0x01] * 8)))
    node2 = (NodeAddress(3), LongAddress(bytes([0x02] * 8)))

    # Page 1: two entries
    obs.node_table_page(gw, NodeAddress(2), [node1, node2])

    # Not yet stored — still accumulating
    assert gw.value not in obs._persistent_state.gateway_node_tables

    # Page 2: empty = done
    obs.node_table_page(gw, NodeAddress(4), [])

    # Now it should be persisted
    assert gw.value in obs._persistent_state.gateway_node_tables
    table = obs._persistent_state.gateway_node_tables[gw.value]
    assert len(table) == 2
    assert table.get(NodeID(2)) == node1[1]
    assert table.get(NodeID(3)) == node2[1]


# ---------------------------------------------------------------------------
# Observer state persistence round-trip
# ---------------------------------------------------------------------------

def test_observer_loads_existing_state(tmp_path, capsys):
    """Observer reads state file at startup and emits infrastructure event."""
    state_file = tmp_path / "state.json"

    # Pre-create state file
    addr = LongAddress(bytes([0x04, 0xC0, 0x5B, 0x40, 0x00, 0x00, 0x00, 0x01]))
    state = PersistentState()
    state.gateway_identities[1] = addr
    state.gateway_versions[1] = "2.0.0"
    state.save(state_file)

    # Create observer — should load state
    obs = Observer(state_file=state_file)

    assert obs._persistent_state.gateway_identities[1] == addr
    assert obs._persistent_state.gateway_versions[1] == "2.0.0"

    # Should have printed infrastructure event to stdout
    captured = capsys.readouterr()
    assert "infrastructure_report" in captured.out


def test_observer_no_state_file():
    """Observer without state_file works fine."""
    obs = Observer(state_file=None)
    assert len(obs._persistent_state.gateway_identities) == 0


def test_observer_command_executed_noop():
    """command_executed is a no-op at observer level."""
    obs = Observer(state_file=None)
    # Should not raise
    obs.command_executed(GatewayID(1), (0x0A, b""), (0x0B, b""))


def test_observer_slot_clock_lifecycle():
    """Slot clock is created on first capture/observe and updated later."""
    obs = Observer(state_file=None)
    gw = GatewayID(1)

    # Capture + observe = create clock
    obs.gateway_slot_counter_captured(gw)
    obs.gateway_slot_counter_observed(gw, SlotCounter.from_u16(0x1000))
    assert gw.value in obs._slot_clocks

    # Second capture + observe = update existing clock
    obs.gateway_slot_counter_captured(gw)
    obs.gateway_slot_counter_observed(gw, SlotCounter.from_u16(0x1010))
    assert gw.value in obs._slot_clocks


def test_observer_observe_without_capture_ignored():
    """Slot counter observation without prior capture is ignored."""
    obs = Observer(state_file=None)
    gw = GatewayID(1)

    # Observe without capture — should not create clock
    obs.gateway_slot_counter_observed(gw, SlotCounter.from_u16(0x1000))
    assert gw.value not in obs._slot_clocks
