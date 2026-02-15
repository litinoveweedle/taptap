"""Persistent state for observer.

Stores infrequently-exchanged network metadata like hardware addresses,
version numbers, and node tables.
"""

import json
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, field

from ..gateway.link.address import GatewayID
from ..pv.network.types import NodeID, LongAddress
from .node_table import NodeTable


@dataclass
class PersistentState:
    """Persistent state of an observed network.
    
    Information like hardware addresses and version numbers are exchanged
    infrequently. This data is captured and stored persistently.
    """
    
    gateway_identities: Dict[int, LongAddress] = field(default_factory=dict)
    gateway_versions: Dict[int, str] = field(default_factory=dict)
    gateway_node_tables: Dict[int, NodeTable] = field(default_factory=dict)
    
    @classmethod
    def load(cls, path: Path) -> 'PersistentState':
        """Load persistent state from JSON file.
        
        Args:
            path: Path to JSON file
            
        Returns:
            PersistentState instance (empty if file doesn't exist)
        """
        if not path.exists():
            return cls()
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            # Deserialize gateway identities
            gateway_identities = {}
            for gw_id_str, addr_str in data.get('gateway_identities', {}).items():
                gw_id = int(gw_id_str)
                # Parse hex address string like "04:C0:5B:40:..."
                addr_bytes = bytes.fromhex(addr_str.replace(':', ''))
                gateway_identities[gw_id] = LongAddress(addr_bytes)
            
            # Deserialize gateway versions
            gateway_versions = {
                int(gw_id): version
                for gw_id, version in data.get('gateway_versions', {}).items()
            }
            
            # Deserialize node tables
            gateway_node_tables = {}
            for gw_id_str, nodes in data.get('gateway_node_tables', {}).items():
                gw_id = int(gw_id_str)
                table = NodeTable()
                for node_id_str, addr_str in nodes.items():
                    node_id = NodeID(int(node_id_str))
                    addr_bytes = bytes.fromhex(addr_str.replace(':', ''))
                    table.set(node_id, LongAddress(addr_bytes))
                gateway_node_tables[gw_id] = table
            
            return cls(
                gateway_identities=gateway_identities,
                gateway_versions=gateway_versions,
                gateway_node_tables=gateway_node_tables
            )
        except Exception as e:
            # If there's any error loading, return empty state
            print(f"Warning: Failed to load persistent state from {path}: {e}")
            return cls()
    
    def save(self, path: Path) -> None:
        """Save persistent state to JSON file (atomic).
        
        Args:
            path: Path to JSON file
        """
        # Serialize to dict
        data = {
            'gateway_identities': {
                str(gw_id): ':'.join(f'{b:02X}' for b in addr.address)
                for gw_id, addr in self.gateway_identities.items()
            },
            'gateway_versions': {
                str(gw_id): version
                for gw_id, version in self.gateway_versions.items()
            },
            'gateway_node_tables': {
                str(gw_id): {
                    str(node_id): ':'.join(f'{b:02X}' for b in addr.address)
                    for node_id, addr in table.items()
                }
                for gw_id, table in self.gateway_node_tables.items()
            }
        }
        
        # Atomic write: write to temp file then rename
        temp_path = path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
            temp_path.replace(path)  # Atomic on POSIX
        except Exception as e:
            # Clean up temp file if write failed
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    def to_infrastructure_event(self) -> dict:
        """Convert to infrastructure report event for JSON output.
        
        Returns:
            Dictionary representing the infrastructure state
        """
        gateways = {}
        for gw_id, addr in self.gateway_identities.items():
            version = self.gateway_versions.get(gw_id, '')
            gateways[str(gw_id)] = {
                'address': ':'.join(f'{b:02X}' for b in addr.address),
                'version': version
            }
        
        nodes = {}
        for gw_id, table in self.gateway_node_tables.items():
            node_dict = {}
            for node_id, addr in table.items():
                from ..barcode import Barcode
                barcode = Barcode(addr.address)
                node_dict[str(node_id)] = {
                    'address': ':'.join(f'{b:02X}' for b in addr.address),
                    'barcode': str(barcode)
                }
            if node_dict:
                nodes[str(gw_id)] = node_dict
        
        return {
            'event_type': 'infrastructure_report',
            'gateways': gateways,
            'nodes': nodes
        }
