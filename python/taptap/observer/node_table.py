"""Node table for tracking node ID to address mappings."""

from typing import Dict, Optional
from ..pv.network.types import NodeID, LongAddress


class NodeTable:
    """Maps node IDs to their long addresses (hardware addresses).
    
    This table is built from NODE_TABLE_RESPONSE packets received from
    the gateway.
    """
    
    def __init__(self):
        """Create an empty node table."""
        self._table: Dict[int, LongAddress] = {}
    
    def set(self, node_id: NodeID, address: LongAddress) -> None:
        """Add or update a node's address.
        
        Args:
            node_id: The node ID
            address: The node's hardware address
        """
        self._table[node_id.value] = address
    
    def get(self, node_id: NodeID) -> Optional[LongAddress]:
        """Get a node's address.
        
        Args:
            node_id: The node ID to look up
            
        Returns:
            The node's address, or None if not known
        """
        return self._table.get(node_id.value)
    
    def items(self):
        """Iterate over (node_id_value, address) pairs."""
        return self._table.items()
    
    def __len__(self) -> int:
        """Get number of entries in table."""
        return len(self._table)
    
    def __contains__(self, node_id: NodeID) -> bool:
        """Check if node ID is in table."""
        return node_id.value in self._table
    
    def to_dict(self) -> Dict[int, LongAddress]:
        """Convert to dictionary."""
        return self._table.copy()
