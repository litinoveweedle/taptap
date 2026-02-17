"""Tests for node table."""

import pytest
from taptap.observer.node_table import NodeTable
from taptap.pv.network.types import NodeID, LongAddress


def test_node_table_empty():
    """Test empty node table."""
    table = NodeTable()
    assert len(table) == 0


def test_node_table_set_get():
    """Test setting and getting entries."""
    table = NodeTable()
    
    node_id = NodeID(116)
    address = LongAddress(bytes.fromhex('04C05B40009A57A2'))
    
    table.set(node_id, address)
    
    assert len(table) == 1
    assert node_id in table
    assert table.get(node_id) == address


def test_node_table_get_missing():
    """Test getting missing entry returns None."""
    table = NodeTable()
    node_id = NodeID(999)
    
    assert table.get(node_id) is None
    assert node_id not in table


def test_node_table_update():
    """Test updating an entry."""
    table = NodeTable()
    
    node_id = NodeID(116)
    address1 = LongAddress(bytes.fromhex('04C05B40009A57A2'))
    address2 = LongAddress(bytes.fromhex('04C05B40009A57A3'))
    
    table.set(node_id, address1)
    assert table.get(node_id) == address1
    
    table.set(node_id, address2)
    assert table.get(node_id) == address2
    assert len(table) == 1  # Still only one entry


def test_node_table_multiple_entries():
    """Test multiple entries."""
    table = NodeTable()
    
    nodes = [
        (NodeID(116), LongAddress(bytes.fromhex('04C05B40009A57A2'))),
        (NodeID(82), LongAddress(bytes.fromhex('04C05B40009A57A3'))),
        (NodeID(19), LongAddress(bytes.fromhex('04C05B40009A57A4'))),
    ]
    
    for node_id, address in nodes:
        table.set(node_id, address)
    
    assert len(table) == 3
    
    for node_id, address in nodes:
        assert table.get(node_id) == address


def test_node_table_items():
    """Test iterating over items."""
    table = NodeTable()
    
    table.set(NodeID(116), LongAddress(bytes.fromhex('04C05B40009A57A2')))
    table.set(NodeID(82), LongAddress(bytes.fromhex('04C05B40009A57A3')))
    
    items = list(table.items())
    assert len(items) == 2
    
    # Check that we get all entries
    node_ids = {item[0] for item in items}
    assert node_ids == {116, 82}


def test_node_table_to_dict():
    """Test converting to dictionary."""
    table = NodeTable()
    
    addr1 = LongAddress(bytes.fromhex('04C05B40009A57A2'))
    addr2 = LongAddress(bytes.fromhex('04C05B40009A57A3'))
    
    table.set(NodeID(116), addr1)
    table.set(NodeID(82), addr2)
    
    d = table.to_dict()
    assert len(d) == 2
    assert d[116] == addr1
    assert d[82] == addr2
