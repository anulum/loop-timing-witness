// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Decode original three-channel records and reconcile actual capture counters.

use crate::files::FileRef;
use serde::{Deserialize, Serialize};

/// Closed semantic channel role; untrusted names are rejected during root decoding.
#[derive(Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub(crate) enum Role {
    /// Actual input application stream.
    Input,
    /// Actual state/raw-spike observation stream.
    State,
    /// Actual encoder packet-service stream.
    Service,
}

impl std::fmt::Display for Role {
    /// Preserve the original semantic role label in located findings.
    fn fmt(&self, output: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        output.write_str(match self {
            Self::Input => "input",
            Self::State => "state",
            Self::Service => "service",
        })
    }
}

/// Original closed channel declaration from the complete root manifest.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ChannelDeclaration {
    /// Semantic input/state/service role.
    pub role: Role,
    /// Complete original binary export.
    pub capture: FileRef,
    /// Declared original data projection.
    pub payload: FileRef,
    /// Declared original marker projection.
    pub markers: FileRef,
    /// Original declared attempts.
    pub attempts: u64,
    /// Original declared accepts.
    pub accepted: u64,
    /// Original declared saturating drop count.
    pub dropped: u64,
    /// Original declared delivered count.
    pub drained: u64,
    /// Original declared payload population.
    pub payload_records: u64,
    /// Original declared alignment-marker count.
    pub marker_records: u64,
    /// Original declared sticky loss flag.
    pub overflowed: bool,
    /// Original declared saturation status.
    pub drop_counter_saturated: bool,
}

/// Actual source-domain snapshot, retaining the original counter value.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Counts {
    /// Original semantic role.
    pub role: Role,
    /// Original u64 attempts.
    pub attempts: u64,
    /// Original u64 accepted records.
    pub accepted: u64,
    /// Original saturating counter value.
    pub dropped: u64,
    /// Actual delivered records.
    pub drained: u64,
    /// Original sticky loss flag.
    pub overflowed: bool,
}

/// Actual original three-counter receipt.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CounterReceipt {
    /// Original receipt version.
    pub schema_id: String,
    /// Actual compiled drop-counter width.
    pub drop_counter_bits: u32,
    /// Actual input/state/service snapshots.
    pub channels: [Counts; 3],
}

/// One original record with its original offset and identity.
#[derive(Serialize)]
pub(crate) struct Event {
    /// Original step or service ordinal.
    pub identity: u32,
    /// Actual shared pre-increment capture tick.
    pub ticks: u64,
    /// Actual original stream byte offset.
    pub byte_offset: usize,
}

/// Decoded original bytes and markers, retaining partial populations.
pub(crate) struct Channel {
    /// Original semantic role.
    pub role: Role,
    /// Original data records in capture order.
    pub events: Vec<Event>,
    /// Original dedicated start marker, when actually exported.
    pub start: Option<u64>,
    /// Original dedicated end marker, when actually exported.
    pub end: Option<u64>,
    /// Original exact data projection.
    pub payload: Vec<u8>,
    /// Original exact marker projection.
    pub markers: Vec<u8>,
}

/// Decode each complete 16byte original tuple without relabelling after loss.
pub(crate) fn decode(raw: &[u8], role: Role, population: u32) -> Result<Channel, String> {
    let code = match role {
        Role::Input => 14,
        Role::State => 15,
        Role::Service => 16,
    };
    if !raw.len().is_multiple_of(16) {
        return Err(format!("{role}: incomplete original 16byte record."));
    }
    let mut channel = Channel {
        role,
        events: Vec::new(),
        start: None,
        end: None,
        payload: Vec::new(),
        markers: Vec::new(),
    };
    let mut previous_tick = None;
    let mut previous_id = None;
    for (index, record) in raw.as_chunks::<16>().0.iter().enumerate() {
        let id = u32::from_le_bytes([record[4], record[5], record[6], record[7]]);
        let tick = u64::from_le_bytes([
            record[8], record[9], record[10], record[11], record[12], record[13], record[14],
            record[15],
        ]);
        if record[1..4] != [0, 0, 0] || tick >= 65536 || previous_tick.is_some_and(|v| tick <= v) {
            return Err(format!("{role}: original reserved/tick fields differ."));
        }
        previous_tick = Some(tick);
        if record[0] == 17 {
            if id == 0 && index == 0 {
                channel.start = Some(tick);
            } else if id == 1 && index + 1 == raw.len() / 16 {
                channel.end = Some(tick);
            } else {
                return Err(format!(
                    "{role}: original marker identity or placement differs."
                ));
            }
            channel.markers.extend_from_slice(record);
        } else {
            if record[0] != code || id >= population || previous_id.is_some_and(|v| id <= v) {
                return Err(format!(
                    "{role}: original code/identity population differs."
                ));
            }
            previous_id = Some(id);
            channel.events.push(Event {
                identity: id,
                ticks: tick,
                byte_offset: index * 16,
            });
            channel.payload.extend_from_slice(record);
        }
    }
    Ok(channel)
}
