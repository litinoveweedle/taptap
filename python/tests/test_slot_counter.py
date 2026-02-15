"""Tests for slot counter."""

import pytest
from taptap.pv.link import SlotCounter, SlotEpoch, SlotNumber


def test_slot_epoch_values():
    """Test SlotEpoch enum values."""
    assert SlotEpoch.EPOCH_0 == 0
    assert SlotEpoch.EPOCH_4 == 1
    assert SlotEpoch.EPOCH_8 == 2
    assert SlotEpoch.EPOCH_C == 3


def test_slot_epoch_wrapping():
    """Test SlotEpoch wrapping addition."""
    assert SlotEpoch.EPOCH_0 + 1 == SlotEpoch.EPOCH_4
    assert SlotEpoch.EPOCH_4 + 1 == SlotEpoch.EPOCH_8
    assert SlotEpoch.EPOCH_8 + 1 == SlotEpoch.EPOCH_C
    assert SlotEpoch.EPOCH_C + 1 == SlotEpoch.EPOCH_0  # Wrap
    
    assert SlotEpoch.EPOCH_0.successor() == SlotEpoch.EPOCH_4
    assert SlotEpoch.EPOCH_C.successor() == SlotEpoch.EPOCH_0


def test_slot_number_valid():
    """Test SlotNumber with valid values."""
    slot = SlotNumber(0)
    assert slot.value == 0
    
    slot = SlotNumber(11999)
    assert slot.value == 11999


def test_slot_number_invalid():
    """Test SlotNumber rejects invalid values."""
    with pytest.raises(ValueError):
        SlotNumber(-1)
    
    with pytest.raises(ValueError):
        SlotNumber(12000)  # Beyond MAX


def test_slot_counter_from_u16():
    """Test SlotCounter decoding from u16."""
    # Epoch 0, slot 0: 0x0000
    sc = SlotCounter.from_u16(0x0000)
    assert sc.epoch == SlotEpoch.EPOCH_0
    assert sc.slot_number.value == 0
    
    # Epoch 4, slot 1383: 0x4567
    sc = SlotCounter.from_u16(0x4567)
    assert sc.epoch == SlotEpoch.EPOCH_4
    assert sc.slot_number.value == 0x567  # 1383


def test_slot_counter_to_u16():
    """Test SlotCounter encoding to u16."""
    sc = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(0))
    assert sc.to_u16() == 0x0000
    
    sc = SlotCounter(SlotEpoch.EPOCH_4, SlotNumber(0x567))
    assert sc.to_u16() == 0x4567


def test_slot_counter_roundtrip():
    """Test SlotCounter encoding and decoding."""
    values = [0x0000, 0x4567, 0x8ABC, 0xC2ED]
    
    for value in values:
        sc1 = SlotCounter.from_u16(value)
        encoded = sc1.to_u16()
        sc2 = SlotCounter.from_u16(encoded)
        assert sc1 == sc2
        assert encoded == value


def test_slot_counter_from_bytes():
    """Test SlotCounter decoding from bytes."""
    # Big-endian 0x4567
    data = bytes([0x45, 0x67])
    sc = SlotCounter.from_bytes(data)
    assert sc.epoch == SlotEpoch.EPOCH_4
    assert sc.slot_number.value == 0x567


def test_slot_counter_to_bytes():
    """Test SlotCounter encoding to bytes."""
    sc = SlotCounter(SlotEpoch.EPOCH_4, SlotNumber(0x567))
    data = sc.to_bytes()
    assert data == bytes([0x45, 0x67])


def test_slot_counter_slots_since_same_epoch():
    """Test slots_since in same epoch."""
    sc1 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(100))
    sc2 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(200))
    
    assert sc2.slots_since(sc1) == 100


def test_slot_counter_slots_since_next_epoch():
    """Test slots_since across epoch boundary."""
    # Near end of epoch 0
    sc1 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(11990))
    # Beginning of epoch 4
    sc2 = SlotCounter(SlotEpoch.EPOCH_4, SlotNumber(10))
    
    # Should be (11999 - 11990 + 1) + 10 = 10 + 10 = 20
    assert sc2.slots_since(sc1) == 20


def test_slot_counter_slots_since_wraparound():
    """Test slots_since handles wraparound correctly."""
    # Test full epoch
    sc1 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(0))
    sc2 = SlotCounter(SlotEpoch.EPOCH_4, SlotNumber(0))
    
    # Should be exactly one epoch worth of slots
    assert sc2.slots_since(sc1) == 12000


def test_slot_counter_slots_since_negative():
    """Test slots_since rejects backwards time in same epoch."""
    sc1 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(200))
    sc2 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(100))
    
    with pytest.raises(ValueError, match="Negative"):
        sc2.slots_since(sc1)


def test_slot_counter_equality():
    """Test SlotCounter equality."""
    sc1 = SlotCounter(SlotEpoch.EPOCH_4, SlotNumber(100))
    sc2 = SlotCounter(SlotEpoch.EPOCH_4, SlotNumber(100))
    sc3 = SlotCounter(SlotEpoch.EPOCH_4, SlotNumber(101))
    sc4 = SlotCounter(SlotEpoch.EPOCH_8, SlotNumber(100))
    
    assert sc1 == sc2
    assert sc1 != sc3
    assert sc1 != sc4


def test_slot_counter_hashable():
    """Test SlotCounter can be used in sets/dicts."""
    sc1 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(100))
    sc2 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(100))
    sc3 = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(200))
    
    counter_set = {sc1, sc2, sc3}
    assert len(counter_set) == 2  # sc1 and sc2 are equal
