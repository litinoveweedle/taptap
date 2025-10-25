//! An observer which can monitor a controller <-> gateway network.
//!
//! ```text
//! ┌───┐
//! │TAP│◁ ─ ─ ─ …
//! └───┘
//!   ▲
//!   │
//!   │
//!   ├──────┐
//!   ▼      ▼
//! ┌───┐  ┌───┐
//! │CCA│  │O_o│
//! └───┘  └───┘
//! ```

use crate::gateway::link::GatewayID;
use crate::pv::application::{NodeTableResponseEntry, TopologyReport};
use crate::pv::link::SlotCounter;
use crate::pv::network::{NodeAddress, ReceivedPacketHeader};
use crate::pv::{LongAddress, NodeID, PacketType};
use crate::{gateway, pv};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use std::collections::btree_map::Entry;
use std::collections::BTreeMap;
use std::time::SystemTime;

pub mod event;

mod persistent_state;
use persistent_state::{PersistentState, PersistentStateEvent};

mod node_table;
use node_table::NodeTableBuilder;

mod slot_clock;
use slot_clock::SlotClock;

/// An observer, monitoring a controller interacting with one or more TAPs via an RS-485 interface.
#[derive(Debug)]
pub struct Observer {
    persistent_state: PersistentState,

    enumeration_state: Option<EnumerationState>,
    captured_slot_counters: BTreeMap<GatewayID, SystemTime>,
    slot_clocks: BTreeMap<GatewayID, SlotClock>,
    node_table_builders: BTreeMap<GatewayID, NodeTableBuilder>,
}

impl Default for Observer {
    fn default() -> Self {
        Self::from_persistent_state(PersistentState::default())
    }
}

impl Observer {
    pub fn from_persistent_state(persistent_state: PersistentState) -> Self {
        Observer {
            persistent_state,
            enumeration_state: None,
            captured_slot_counters: Default::default(),
            slot_clocks: Default::default(),
            node_table_builders: Default::default(),
        }
    }

    pub fn persistent_state(&self) -> &PersistentState {
        &self.persistent_state
    }
}

impl gateway::transport::Sink for Observer {
    fn enumeration_started(&mut self, enumeration_gateway_id: GatewayID) {
        self.enumeration_state = Some(EnumerationState {
            enumeration_gateway_id,
            gateway_identities: Default::default(),
            gateway_versions: Default::default(),
        });
    }

    fn gateway_identity_observed(&mut self, gateway_id: GatewayID, address: LongAddress) {
        if let Some(enumeration_state) = self.enumeration_state.as_mut() {
            // We're enumerating
            // Delegate
            enumeration_state.gateway_identity_observed(gateway_id, address);
        } else {
            // Accept the identity as-is
            self.persistent_state
                .gateway_identities
                .insert(gateway_id, address);
            let infrastructure_event = PersistentStateEvent::from(&self.persistent_state);
            println!("{}", serde_json::to_string(&infrastructure_event).unwrap());
        }
    }

    fn gateway_version_observed(&mut self, gateway_id: GatewayID, version: &str) {
        let version = version.to_owned();

        if let Some(enumeration_state) = self.enumeration_state.as_mut() {
            enumeration_state
                .gateway_versions
                .insert(gateway_id, version);
        } else {
            self.persistent_state
                .gateway_versions
                .insert(gateway_id, version);
            let infrastructure_event = PersistentStateEvent::from(&self.persistent_state);
            println!("{}", serde_json::to_string(&infrastructure_event).unwrap());
        }
    }

    fn enumeration_ended(&mut self, _gateway_id: GatewayID) {
        // We're done enumerating
        // Did we catch the whole exchange?
        if let Some(enumeration_state) = self.enumeration_state.take() {
            // Accept the gateway information learned during enumeration as a replacement for our
            // existing state
            self.persistent_state.gateway_identities = enumeration_state.gateway_identities;
            self.persistent_state.gateway_versions = enumeration_state.gateway_versions;
            let infrastructure_event = PersistentStateEvent::from(&self.persistent_state);
            println!("{}", serde_json::to_string(&infrastructure_event).unwrap());
        }
    }

    fn gateway_slot_counter_captured(&mut self, gateway_id: GatewayID) {
        self.captured_slot_counters
            .insert(gateway_id, SystemTime::now());
    }

    fn gateway_slot_counter_observed(&mut self, gateway_id: GatewayID, slot_counter: SlotCounter) {
        let Some(time) = self.captured_slot_counters.remove(&gateway_id) else {
            return;
        };

        match self.slot_clocks.entry(gateway_id) {
            Entry::Vacant(e) => {
                if let Ok(clock) = SlotClock::new(slot_counter, time) {
                    e.insert(clock);
                }
            }
            Entry::Occupied(mut e) => {
                e.get_mut().set(slot_counter, time).ok();
            }
        }
    }

    fn packet_received(
        &mut self,
        _gateway_id: GatewayID,
        _packet_header: &ReceivedPacketHeader,
        _packet_data: &[u8],
    ) {
    }

    fn command_executed(
        &mut self,
        _gateway_id: GatewayID,
        _command_request: (PacketType, &[u8]),
        _command_response: (PacketType, &[u8]),
    ) {
    }
}

impl pv::application::Sink for Observer {
    fn string_request(
        &mut self,
        _gateway_id: GatewayID,
        _pv_node_id: NodeID,
        _string_request: &str,
    ) {
    }

    fn string_response(
        &mut self,
        _gateway_id: GatewayID,
        _pv_node_id: NodeID,
        _string_response: &str,
    ) {
    }

    fn node_table_page(
        &mut self,
        gateway_id: GatewayID,
        start_address: NodeAddress,
        nodes: &[NodeTableResponseEntry],
    ) {
        let builder = self.node_table_builders.entry(gateway_id).or_default();

        if let Some(new_table) = builder.push(start_address, nodes) {
            self.persistent_state
                .gateway_node_tables
                .insert(gateway_id, new_table);
            let infrastructure_event = PersistentStateEvent::from(&self.persistent_state);
            println!("{}", serde_json::to_string(&infrastructure_event).unwrap());
        }
    }

    fn topology_report(
        &mut self,
        _gateway_id: GatewayID,
        _pv_node_id: NodeID,
        _topology_report: &TopologyReport,
    ) {
    }

    fn power_report(
        &mut self,
        gateway_id: GatewayID,
        node_id: NodeID,
        power_report: &pv::application::PowerReport,
    ) {
        let Some(slot_clock) = self.slot_clocks.get(&gateway_id) else {
            log::error!(
                "discarding power report from gateway {:?} due to missing slot clock: {:?}",
                gateway_id,
                power_report
            );
            return;
        };

        let Ok(event) = event::PowerReportEvent::new(gateway_id, node_id, slot_clock, power_report)
        else {
            log::error!(
                "discarding power report from gateway {:?} due to invalid slot counter: {:?}",
                gateway_id,
                power_report
            );
            return;
        };

        println!("{}", serde_json::to_string(&event).unwrap());
    }
}

#[derive(Debug, Clone, Eq, PartialEq, serde::Serialize, serde::Deserialize)]
struct EnumerationState {
    enumeration_gateway_id: GatewayID,
    gateway_identities: BTreeMap<GatewayID, LongAddress>,
    gateway_versions: BTreeMap<GatewayID, String>,
}

impl EnumerationState {
    fn gateway_identity_observed(&mut self, gateway: GatewayID, address: LongAddress) {
        // Is this a persistent ID?
        if gateway == self.enumeration_gateway_id {
            // No, it's the enumeration address
            // Discard this response, since we'll get a persistent one shortly
            return;
        }

        // Store the identity
        self.gateway_identities.insert(gateway, address);
    }
}

#[cfg(test)]
mod tests;
