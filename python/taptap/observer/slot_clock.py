"""Slot clock for mapping slot counters to wall-clock time.

The PV network uses slot counters for time synchronization. This module
maps those slot counters to actual datetime values.
"""

from datetime import datetime, timedelta
from typing import Optional

from ..pv.link.slot_counter import SlotCounter


# Slot duration: ~5ms nominal (can vary ±15%)
NOMINAL_DURATION_PER_SLOT = timedelta(milliseconds=5)
# Index duration: 1000 slots = ~5 seconds
NOMINAL_DURATION_PER_INDEX = timedelta(milliseconds=5000)


class SlotClock:
    """Maps slot counters to wall-clock time.
    
    Maintains a table of reference times indexed by slot counter ranges.
    The table has 48 entries, one per 1000 slots, covering the full
    4-epoch cycle (48000 slots).
    """
    
    def __init__(self, slot_counter: SlotCounter, time: datetime):
        """Create a new slot clock.
        
        Args:
            slot_counter: Initial slot counter reference
            time: Wall-clock time for the reference
            
        Raises:
            ValueError: If slot counter has invalid slot number
        """
        index, offset = self._index_and_offset(slot_counter)
        index_time = time - offset
        
        # Initialize table with nominal times
        self._times = [index_time] * 48
        self._last_index = index
        self._last_time = time
        
        # Walk backwards from reference, assuming nominal time per index
        current_time = index_time
        i = index
        for _ in range(47):
            i = (i - 1) % 48
            current_time -= NOMINAL_DURATION_PER_INDEX
            self._times[i] = current_time
    
    def _index_and_offset(self, slot_counter: SlotCounter) -> tuple:
        """Calculate table index and offset within index for slot counter.
        
        Args:
            slot_counter: Slot counter to convert
            
        Returns:
            Tuple of (index, offset) where:
                index: Table index (0-47)
                offset: Time offset within index
                
        Raises:
            ValueError: If slot number is invalid
        """
        # Calculate absolute slot number across all epochs
        # Each epoch has 12000 slots, 4 epochs total
        absolute_slot = slot_counter.epoch.value * 12000 + slot_counter.slot_number.value
        
        # Index: which 1000-slot block (0-47)
        index = absolute_slot // 1000
        
        # Offset: position within the 1000-slot block
        offset = NOMINAL_DURATION_PER_SLOT * (absolute_slot % 1000)
        
        return (index, offset)
    
    def set(self, slot_counter: SlotCounter, time: datetime) -> None:
        """Update the slot clock with a new reference point.
        
        Args:
            slot_counter: New slot counter reference
            time: Wall-clock time for the reference
            
        Raises:
            ValueError: If slot counter has invalid slot number
        """
        if time < self._last_time:
            # Clock went backwards - replace entire table
            self.__init__(slot_counter, time)
            return
        
        index, offset = self._index_and_offset(slot_counter)
        
        if self._last_index != index:
            # New index - update this entry and backfill
            index_time = time - offset
            self._times[index] = index_time
            
            # Walk backwards to last_index, updating with nominal times
            current_time = index_time
            i = index
            while True:
                i = (i - 1) % 48
                if i == self._last_index:
                    break
                current_time -= NOMINAL_DURATION_PER_INDEX
                self._times[i] = current_time
        
        # Update tracking
        self._last_index = index
        self._last_time = time
    
    def get(self, slot_counter: SlotCounter) -> datetime:
        """Get wall-clock time for a slot counter.
        
        Args:
            slot_counter: Slot counter to convert
            
        Returns:
            Estimated wall-clock time
            
        Raises:
            ValueError: If slot counter has invalid slot number
        """
        index, offset = self._index_and_offset(slot_counter)
        return self._times[index] + offset
