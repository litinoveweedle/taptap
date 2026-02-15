"""Tests for slot clock."""

import pytest
from datetime import datetime, timedelta

from taptap.observer.slot_clock import SlotClock
from taptap.pv.link.slot_counter import SlotCounter, SlotEpoch, SlotNumber


def test_slot_clock_creation():
    """Test creating a slot clock."""
    now = datetime.now()
    slot = SlotCounter(SlotEpoch.EPOCH_C, SlotNumber(0))
    
    clock = SlotClock(slot, now)
    
    # Should be able to get time for the reference slot
    retrieved = clock.get(slot)
    assert abs((retrieved - now).total_seconds()) < 0.001


def test_slot_clock_get_past_slots():
    """Test getting times for past slot counters."""
    # Pick a reference time
    ref_time = datetime(2024, 8, 24, 12, 0, 0)
    
    # Reference is at 0xC000 (epoch C, slot 0)
    ref_slot = SlotCounter.from_u16(0xC000)
    
    clock = SlotClock(ref_slot, ref_time)
    
    # 0x8000 (epoch 8, slot 0) was ~60 seconds ago (12000 slots)
    past_slot = SlotCounter.from_u16(0x8000)
    past_time = clock.get(past_slot)
    
    # 12000 slots * 5ms = 60 seconds
    expected = ref_time - timedelta(seconds=60)
    assert abs((past_time - expected).total_seconds()) < 0.1
    
    # 0x4000 (epoch 4, slot 0) was ~120 seconds ago (24000 slots)
    earlier_slot = SlotCounter.from_u16(0x4000)
    earlier_time = clock.get(earlier_slot)
    
    expected = ref_time - timedelta(seconds=120)
    assert abs((earlier_time - expected).total_seconds()) < 0.1


def test_slot_clock_set_updates():
    """Test updating the clock with new reference points."""
    ref_time = datetime(2024, 8, 24, 12, 0, 0)
    ref_slot = SlotCounter.from_u16(0xC000)
    
    clock = SlotClock(ref_slot, ref_time)
    
    # Advance to 0xC000 + 1000 at 5 seconds later
    later_time = ref_time + timedelta(seconds=5)
    later_slot = SlotCounter.from_u16(0xC000 + 1000)
    
    clock.set(later_slot, later_time)
    
    # Check that later slot returns later time
    retrieved = clock.get(later_slot)
    assert abs((retrieved - later_time).total_seconds()) < 0.001
    
    # Previous slots should still be relative to original reference
    past_slot = SlotCounter.from_u16(0x8000)
    past_time = clock.get(past_slot)
    expected = ref_time - timedelta(seconds=60)
    assert abs((past_time - expected).total_seconds()) < 0.1


def test_slot_clock_index_and_offset():
    """Test index and offset calculation."""
    # Epoch 0, slot 0: index 0, offset 0
    slot = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(0))
    clock = SlotClock(slot, datetime.now())
    index, offset = clock._index_and_offset(slot)
    assert index == 0
    assert offset == timedelta(0)
    
    # Epoch 0, slot 999: index 0, offset 999*5ms
    slot = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(999))
    index, offset = clock._index_and_offset(slot)
    assert index == 0
    assert offset == timedelta(milliseconds=999 * 5)
    
    # Epoch 0, slot 1000: index 1, offset 0
    slot = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(1000))
    index, offset = clock._index_and_offset(slot)
    assert index == 1
    assert offset == timedelta(0)
    
    # Epoch 4 (0x4000), slot 0: index 12, offset 0
    slot = SlotCounter.from_u16(0x4000)
    index, offset = clock._index_and_offset(slot)
    assert index == 12
    assert offset == timedelta(0)


def test_slot_clock_wraparound():
    """Test slot clock handles epoch wraparound."""
    ref_time = datetime(2024, 8, 24, 12, 0, 0)
    
    # Start at epoch 0, slot 0
    slot = SlotCounter(SlotEpoch.EPOCH_0, SlotNumber(0))
    clock = SlotClock(slot, ref_time)
    
    # Epoch C slots should be in the past
    past_slot = SlotCounter(SlotEpoch.EPOCH_C, SlotNumber(0))
    past_time = clock.get(past_slot)
    
    # 12000 slots ago = 60 seconds
    expected = ref_time - timedelta(seconds=60)
    assert abs((past_time - expected).total_seconds()) < 0.1


def test_slot_clock_time_backwards():
    """Test clock handles time going backwards."""
    ref_time = datetime(2024, 8, 24, 12, 0, 0)
    ref_slot = SlotCounter.from_u16(0xC000)
    
    clock = SlotClock(ref_slot, ref_time)
    
    # Try to set time to earlier value
    earlier_time = ref_time - timedelta(seconds=10)
    new_slot = SlotCounter.from_u16(0xC100)
    
    # This should reinitialize the clock
    clock.set(new_slot, earlier_time)
    
    # New reference should work
    retrieved = clock.get(new_slot)
    assert abs((retrieved - earlier_time).total_seconds()) < 0.001
