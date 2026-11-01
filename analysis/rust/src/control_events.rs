// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — hash-bound fabric event records

//! Decode the 16-byte little-endian fabric event records without silent loss.
//!
//! Each record is `event_type` u8, a zero byte, a zero u16, `cycle` u32 and
//! `timebase_ticks` u64. The checks and texts are those of the Python
//! `event_stream.decode_events`, in its order for each record: reserved bits,
//! a code of the selected profile, a cycle inside the run, monotonic time and
//! cycle order, and one event of each kind per cycle.

use crate::control_number::Num;
use serde_json::Value;
use std::cmp::Ordering;

/// Bytes of one event record.
const RECORD: usize = 16;

/// One timestamp captured by the fabric witness.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Event {
    /// Event code, naming the event through the measurement domain.
    pub(crate) code: u8,
    /// Zero-based control or compute cycle.
    pub(crate) cycle: u32,
    /// Free-running fabric counter value, in clock ticks.
    pub(crate) ticks: u64,
}

/// Event names by code, from the measurement domain.
pub(crate) struct Names(Vec<Option<String>>);

impl Names {
    /// Map every declared numeric code to its event name.
    pub(crate) fn of(contracts: &Value) -> Self {
        let mut names = vec![None; 256];
        for (name, code) in contracts["event_codes"]
            .as_object()
            .expect("schema-checked object")
        {
            let index = match Num::of(code) {
                Num::Int(integer) => integer as usize,
                Num::Float(float) => float as usize,
            };
            names[index] = Some(name.clone());
        }
        Self(names)
    }

    /// The event name of one code, if the domain declares it.
    pub(crate) fn get(&self, code: u8) -> Option<&str> {
        self.0[usize::from(code)].as_deref()
    }
}

/// Decode and validate the complete binary event file of one profile.
pub(crate) fn decode(
    content: &[u8],
    contracts: &Value,
    profile: &str,
    cycle_count: Num,
) -> Result<Vec<Event>, String> {
    if !content.len().is_multiple_of(RECORD) {
        return Err("event file is not a whole number of 16-byte records".to_owned());
    }
    if content.is_empty() {
        return Err("event file is empty".to_owned());
    }
    let declared = &contracts["event_profiles"][profile];
    let allowed: Vec<&str> = ["periodic_events", "occasional_events"]
        .iter()
        .flat_map(|list| declared[*list].as_array().expect("schema-checked array"))
        .map(|name| name.as_str().expect("schema-checked string"))
        .collect();
    let names = Names::of(contracts);
    let mut events = Vec::with_capacity(content.len() / RECORD);
    let mut seen = [false; 256];
    let (mut previous_ticks, mut previous_cycle): (Option<u64>, Option<u32>) = (None, None);
    let (records, _) = content.as_chunks::<RECORD>();
    for (index, record) in records.iter().enumerate() {
        let code = record[0];
        let cycle = u32::from_le_bytes(record[4..8].try_into().expect("four bytes"));
        let ticks = u64::from_le_bytes(record[8..16].try_into().expect("eight bytes"));
        if record[1..4] != [0, 0, 0] {
            return Err(format!("event record {index}: reserved bits must be zero"));
        }
        if !names.get(code).is_some_and(|name| allowed.contains(&name)) {
            return Err(format!(
                "event record {index}: code {code} is not in {profile}"
            ));
        }
        if Num::Int(u128::from(cycle)).compare(cycle_count) != Ordering::Less {
            return Err(format!("event record {index}: cycle is outside the run"));
        }
        if previous_ticks.is_some_and(|previous| ticks < previous)
            || previous_cycle.is_some_and(|previous| cycle < previous)
        {
            return Err(format!("event record {index}: order is not monotonic"));
        }
        if previous_cycle != Some(cycle) {
            seen = [false; 256];
        }
        if seen[usize::from(code)] {
            let name = names.get(code).unwrap_or_default();
            return Err(format!(
                "event record {index}: duplicate {name} in cycle {cycle}"
            ));
        }
        seen[usize::from(code)] = true;
        events.push(Event { code, cycle, ticks });
        (previous_ticks, previous_cycle) = (Some(ticks), Some(cycle));
    }
    Ok(events)
}

#[cfg(test)]
#[path = "../tests/unit/control_events.rs"]
mod tests;
