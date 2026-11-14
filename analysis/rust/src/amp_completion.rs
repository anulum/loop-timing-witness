// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — logger completion of an AMP capture and its captured streams

//! Read an AMP capture's logger completion and hold its counters to the
//! captured streams as the Python module `amp_completion` does.
//!
//! [`completion_receipt`] requires exactly one completion line in the
//! simulator log; [`decode_completion`] admits its six typed counters;
//! [`validate_capture`] validates the retained measurement domain, decodes the
//! events and the raw tracking, refuses a FIFO overflow, and requires the
//! event count and the sampled cycles to agree with the completion. Every
//! refusal is Python's text for the same first defect.
//!
//! [`completion_receipt`]: crate::amp_completion::completion_receipt
//! [`decode_completion`]: crate::amp_completion::decode_completion
//! [`validate_capture`]: crate::amp_completion::validate_capture

use crate::amp_tracking::decode_tracking;
use crate::control_events::{Names, decode};
use crate::control_json::decode_object;
use crate::control_manifest::load_domain;
use crate::control_number::Num;
use serde_json::Value;

/// The start of the logger's completion line.
const PREFIX: &[u8] = b"WITNESS_AMP_COMPLETION ";
/// The completion's members.
const FIELDS: [&str; 6] = ["samples", "events", "misses", "overflow", "safe", "thermal"];

/// The logger's final drain counters.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AmpCompletion {
    /// Observed telemetry rows.
    pub samples: u64,
    /// Observed drained records.
    pub events: u64,
    /// The fabric's deadline-miss counter.
    pub misses: u32,
    /// The fabric's dropped-record counter.
    pub overflow: u32,
    /// The fabric's latched safe state.
    pub safe: bool,
    /// The plant selector the running RTL reported.
    pub thermal: bool,
}

/// The log's lines, split at every `\r` and `\n`. Python's
/// `bytes.splitlines` ends a line at `\n`, `\r\n` or a lone `\r`; splitting
/// at each character gives the same lines and some empty ones, and an empty
/// line never holds the completion prefix.
fn lines(log: &[u8]) -> impl Iterator<Item = &[u8]> {
    log.split(|byte| matches!(byte, b'\r' | b'\n'))
}

/// Require exactly one completion line in the whole simulator log.
///
/// # Errors
///
/// Python's refusal text when no completion line or more than one is present,
/// or the completion is invalid.
pub fn completion_receipt(log: &[u8]) -> Result<AmpCompletion, String> {
    let records: Vec<&[u8]> = lines(log)
        .filter_map(|line| line.strip_prefix(PREFIX))
        .collect();
    let [record] = records.as_slice() else {
        return Err("AMP requires exactly one actual logger completion receipt".to_owned());
    };
    decode_completion(record)
}

/// Admit one completion object: the six members, two flags and four counters
/// within the native ABI.
///
/// # Errors
///
/// Python's refusal text when the bytes break the bounded JSON rules, the
/// members or flag types differ, or a counter is not an integer within its
/// bound.
pub fn decode_completion(content: &[u8]) -> Result<AmpCompletion, String> {
    let (data, _) = decode_object(content, "AMP completion")?;
    let members = data.len() == FIELDS.len() && FIELDS.iter().all(|name| data.contains_key(*name));
    let flags = members.then(|| (data["safe"].as_bool(), data["thermal"].as_bool()));
    let Some((Some(safe), Some(thermal))) = flags else {
        return Err("AMP completion fields or safe-state type are invalid".to_owned());
    };
    let counter = |name: &str| data[name].as_u64();
    let narrow = |value: Option<u64>| value.and_then(|value| u32::try_from(value).ok());
    let (Some(samples), Some(events), Some(misses), Some(overflow)) = (
        counter("samples"),
        counter("events"),
        narrow(counter("misses")),
        narrow(counter("overflow")),
    ) else {
        return Err("AMP completion counters are outside the native ABI".to_owned());
    };
    Ok(AmpCompletion {
        samples,
        events,
        misses,
        overflow,
        safe,
        thermal,
    })
}

/// Hold the completion to the captured events and raw tracking.
///
/// `domain` is the retained measurement domain and `cycles` the configured
/// cycle count.
///
/// # Errors
///
/// Python's refusal text when the measurement domain breaks its contract, a
/// stream is malformed, the FIFO overflowed, or the event count or the
/// sampled cycles disagree with the completion.
pub fn validate_capture(
    completion: &AmpCompletion,
    events: &[u8],
    tracking: &[u8],
    domain: &[u8],
    cycles: u32,
) -> Result<(), String> {
    let domain: Value = load_domain(domain, "AMP measurement domain")?;
    let contracts = &domain["design_contracts"];
    let decoded = decode(events, contracts, "CONTROL", Num::Int(u128::from(cycles)))?;
    let observations = decode_tracking(tracking, cycles, completion.samples)?;
    if completion.overflow != 0 {
        return Err("AMP fabric FIFO overflow invalidates capture".to_owned());
    }
    let names = Names::of(contracts);
    let read_cycles = decoded
        .iter()
        .filter(|event| names.get(event.code) == Some("SAMPLE_READ"))
        .map(|event| event.cycle);
    if decoded.len() as u64 != completion.events
        || !read_cycles.eq(observations.iter().map(|row| row.cycle))
    {
        return Err("AMP completion and event/telemetry observations disagree".to_owned());
    }
    Ok(())
}

#[cfg(test)]
#[path = "../tests/unit/amp_completion.rs"]
mod tests;
