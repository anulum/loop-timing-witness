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
//!
//! A profile's reference events, such as the CONTROL profile's pulse per second,
//! are records that the fabric writes into a slot no cycle event claims, with
//! the reference's own sequence number in the cycle field. They are checked on
//! their own, as in `event_stream.decode_stream`: zero reserved bits, then a
//! sequence number and counter value above the previous edge of the same kind.

use crate::control_number::Num;
use serde_json::Value;
use std::cmp::Ordering;

/// Bytes of one event record.
pub(crate) const RECORD: usize = 16;

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

/// One edge of an external time reference, timestamped by the fabric witness.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Edge {
    /// Event code, naming the reference through the measurement domain.
    pub(crate) code: u8,
    /// The reference's own edge count when this edge arrived.
    pub(crate) sequence: u32,
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

/// Decode and validate the complete binary event file of one profile, returning its cycle events.
pub(crate) fn decode(
    content: &[u8],
    contracts: &Value,
    profile: &str,
    cycle_count: Num,
) -> Result<Vec<Event>, String> {
    decode_stream(content, contracts, profile, cycle_count).map(|(events, _)| events)
}

/// Decode and validate the complete binary event file of one profile, cycle and reference records apart.
pub(crate) fn decode_stream(
    content: &[u8],
    contracts: &Value,
    profile: &str,
    cycle_count: Num,
) -> Result<(Vec<Event>, Vec<Edge>), String> {
    if !content.len().is_multiple_of(RECORD) {
        return Err("event file is not a whole number of 16-byte records".to_owned());
    }
    if content.is_empty() {
        return Err("event file is empty".to_owned());
    }
    let allowed = allowed(contracts, profile);
    let references = references(contracts, profile);
    let names = Names::of(contracts);
    let admitted = Admitted {
        names: &names,
        allowed: &allowed,
        profile,
        cycle_count,
    };
    let mut events = Vec::with_capacity(content.len() / RECORD);
    let mut edges = Vec::new();
    let mut latest: [Option<Edge>; 256] = [None; 256];
    let mut seen = [false; 256];
    let (mut previous_ticks, mut previous_cycle): (Option<u64>, Option<u32>) = (None, None);
    let (records, _) = content.as_chunks::<RECORD>();
    for (index, record) in records.iter().enumerate() {
        if let Some(name) = names
            .get(record[0])
            .filter(|name| references.contains(name))
        {
            let edge = reference_edge(index, record, name, &latest)?;
            latest[usize::from(edge.code)] = Some(edge);
            edges.push(edge);
            continue;
        }
        let Event { code, cycle, ticks } = admitted.event(index, record)?;
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
    Ok((events, edges))
}

/// The reference event names the profile admits; the member is optional.
fn references<'a>(contracts: &'a Value, profile: &str) -> Vec<&'a str> {
    contracts["event_profiles"][profile]
        .get("reference_events")
        .map_or_else(Vec::new, |list| {
            list.as_array()
                .expect("schema-checked array")
                .iter()
                .map(|name| name.as_str().expect("schema-checked string"))
                .collect()
        })
}

/// Decode one reference record with zero reserved bits, after the previous edge of its kind.
fn reference_edge(
    index: usize,
    record: &[u8; RECORD],
    name: &str,
    latest: &[Option<Edge>; 256],
) -> Result<Edge, String> {
    if record[1..4] != [0, 0, 0] {
        return Err(format!("event record {index}: reserved bits must be zero"));
    }
    let edge = Edge {
        code: record[0],
        sequence: u32::from_le_bytes(record[4..8].try_into().expect("four bytes")),
        ticks: u64::from_le_bytes(record[8..16].try_into().expect("eight bytes")),
    };
    if latest[usize::from(edge.code)]
        .is_some_and(|previous| edge.sequence <= previous.sequence || edge.ticks <= previous.ticks)
    {
        return Err(format!(
            "event record {index}: {name} order is not monotonic"
        ));
    }
    Ok(edge)
}

/// The event names the profile admits, periodic before occasional.
fn allowed<'a>(contracts: &'a Value, profile: &str) -> Vec<&'a str> {
    let declared = &contracts["event_profiles"][profile];
    ["periodic_events", "occasional_events"]
        .iter()
        .flat_map(|list| declared[*list].as_array().expect("schema-checked array"))
        .map(|name| name.as_str().expect("schema-checked string"))
        .collect()
}

/// The event names, the profile's admitted names and the run length one record is checked against.
struct Admitted<'a> {
    /// Event names by code.
    names: &'a Names,
    /// Names the profile admits.
    allowed: &'a [&'a str],
    /// Profile name, for refusals.
    profile: &'a str,
    /// Declared cycle count.
    cycle_count: Num,
}

impl Admitted<'_> {
    /// Decode one record with zero reserved bits, an admitted code and a cycle in the run.
    fn event(&self, index: usize, record: &[u8; RECORD]) -> Result<Event, String> {
        let code = record[0];
        let cycle = u32::from_le_bytes(record[4..8].try_into().expect("four bytes"));
        let ticks = u64::from_le_bytes(record[8..16].try_into().expect("eight bytes"));
        if record[1..4] != [0, 0, 0] {
            return Err(format!("event record {index}: reserved bits must be zero"));
        }
        if !self
            .names
            .get(code)
            .is_some_and(|name| self.allowed.contains(&name))
        {
            return Err(format!(
                "event record {index}: code {code} is not in {}",
                self.profile
            ));
        }
        if Num::Int(u128::from(cycle)).compare(self.cycle_count) != Ordering::Less {
            return Err(format!("event record {index}: cycle is outside the run"));
        }
        Ok(Event { code, cycle, ticks })
    }
}

#[cfg(test)]
#[path = "../tests/unit/control_events.rs"]
mod tests;
