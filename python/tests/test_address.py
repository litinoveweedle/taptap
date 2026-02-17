"""Tests for gateway addressing."""

import pytest
from taptap.gateway.link import GatewayID, Address


def test_gateway_id_valid():
    """Test GatewayID with valid values."""
    gw = GatewayID(4609)
    assert gw.value == 4609
    assert int(gw) == 4609
    assert str(gw) == "4609"


def test_gateway_id_boundary():
    """Test GatewayID boundary values."""
    GatewayID(0)  # Min
    GatewayID(0x7FFF)  # Max
    
    with pytest.raises(ValueError):
        GatewayID(-1)
    
    with pytest.raises(ValueError):
        GatewayID(0x8000)


def test_address_to():
    """Test To address creation and encoding."""
    gw = GatewayID(4609)
    addr = Address.to(gw)
    
    assert addr.is_to
    assert not addr.is_from
    assert addr.gateway_id == gw
    
    # Encode and verify
    data = addr.to_bytes()
    assert len(data) == 2
    # Verify no direction bit set
    assert (data[0] & 0x80) == 0


def test_address_from():
    """Test From address creation and encoding."""
    gw = GatewayID(4609)
    addr = Address.from_(gw)
    
    assert addr.is_from
    assert not addr.is_to
    assert addr.gateway_id == gw
    
    # Encode and verify
    data = addr.to_bytes()
    assert len(data) == 2
    # Verify direction bit set
    assert (data[0] & 0x80) != 0


def test_address_roundtrip():
    """Test address encoding and decoding."""
    gw = GatewayID(4609)
    
    # Test To address
    addr_to = Address.to(gw)
    data_to = addr_to.to_bytes()
    decoded_to = Address.from_bytes(data_to)
    assert decoded_to == addr_to
    assert decoded_to.is_to
    
    # Test From address
    addr_from = Address.from_(gw)
    data_from = addr_from.to_bytes()
    decoded_from = Address.from_bytes(data_from)
    assert decoded_from == addr_from
    assert decoded_from.is_from


def test_address_known_values():
    """Test address encoding with known values."""
    # To(GatewayID(4609)) should encode as 0x1201
    gw = GatewayID(4609)
    addr_to = Address.to(gw)
    assert addr_to.to_bytes() == bytes([0x12, 0x01])
    
    # From(GatewayID(4609)) should encode as 0x9201
    addr_from = Address.from_(gw)
    assert addr_from.to_bytes() == bytes([0x92, 0x01])


def test_address_decode_known():
    """Test address decoding from known values."""
    # 0x1201 = To(GatewayID(4609))
    addr = Address.from_bytes(bytes([0x12, 0x01]))
    assert addr.is_to
    assert addr.gateway_id.value == 4609
    
    # 0x9201 = From(GatewayID(4609))
    addr = Address.from_bytes(bytes([0x92, 0x01]))
    assert addr.is_from
    assert addr.gateway_id.value == 4609


def test_address_equality():
    """Test address equality."""
    gw1 = GatewayID(4609)
    gw2 = GatewayID(4609)
    gw3 = GatewayID(4610)
    
    assert Address.to(gw1) == Address.to(gw2)
    assert Address.from_(gw1) == Address.from_(gw2)
    assert Address.to(gw1) != Address.from_(gw1)
    assert Address.to(gw1) != Address.to(gw3)


def test_address_hashable():
    """Test that addresses can be used in sets/dicts."""
    gw = GatewayID(4609)
    addr_set = {Address.to(gw), Address.from_(gw)}
    assert len(addr_set) == 2
