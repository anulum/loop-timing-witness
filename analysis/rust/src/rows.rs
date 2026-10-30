// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Complete original ASCII row grammar and full epoch/population/range admission.

use crate::binding::BoundRun;
use std::collections::BTreeMap;

/// Original exact integer row without post-loss identity changes.
pub(crate) type Row = Vec<i64>;
/// All admitted full original trace roles.
pub(crate) type Rows = BTreeMap<String, Vec<Row>>;

/// Decode complete LF-terminated, space-separated ASCII signed64 rows.
pub(crate) fn decode(raw: &[u8], columns: usize, name: &str) -> Result<Vec<Row>, String> {
    let text =
        std::str::from_utf8(raw).map_err(|_| format!("Original {name} trace is not ASCII."))?;
    if !text.is_ascii() {
        return Err(format!("Original {name} trace is not ASCII."));
    }
    if !text.is_empty() && !text.ends_with('\n') {
        return Err(format!("Original {name} trace lacks its final newline."));
    }
    let mut rows = Vec::new();
    for line in text.split_terminator('\n') {
        let fields: Vec<_> = line.split(' ').collect();
        if fields.len() != columns {
            return Err(format!("Malformed original {name} trace row."));
        }
        let mut row = Vec::new();
        for value in fields {
            let digits = value.strip_prefix(['+', '-']).unwrap_or(value);
            if digits.is_empty() || digits.len() > 20 || !digits.bytes().all(|b| b.is_ascii_digit())
            {
                return Err(format!("Malformed original {name} trace row."));
            }
            row.push(
                value.parse::<i64>().map_err(|_| {
                    format!("Original {name} trace integer outside signed64 range.")
                })?,
            );
        }
        rows.push(row);
    }
    Ok(rows)
}

/// Require every original population and epoch/step identity before projection/equality.
pub(crate) fn load(run: &BoundRun) -> Result<Rows, String> {
    let mut rows = BTreeMap::new();
    for (name, width) in [
        ("original_stimulus", 4),
        ("reference_projection", 2),
        ("input_trace", 7),
        ("numerical_trace", 5),
        ("raw_spike_trace", 4),
        ("numerical_projection", 2),
        ("service_trace", 5),
    ] {
        let data = decode(&run.files[name], width, name)?;
        if name != "service_trace" && data.len() != run.manifest.step_count as usize {
            return Err(format!("Complete requested population required: {name}."));
        }
        rows.insert(name.into(), data);
    }
    for name in ["input_trace", "numerical_trace", "raw_spike_trace"] {
        for (index, row) in rows[name].iter().enumerate() {
            if row[0] != i64::from(run.manifest.epoch) || row[1] != index as i64 {
                return Err(format!("Original epoch/step sequence differs: {name}."));
            }
        }
    }
    for (name, first, last) in [("original_stimulus", 0, 4), ("input_trace", 2, 6)] {
        if rows[name]
            .iter()
            .flat_map(|row| &row[first..last])
            .any(|v| !(-32768..=32767).contains(v))
        {
            return Err(format!("Original signed16 stimulus outside range: {name}."));
        }
    }
    for (name, offset) in [
        ("reference_projection", 0),
        ("numerical_projection", 0),
        ("numerical_trace", 2),
    ] {
        if rows[name].iter().any(|row| {
            !(0..=1).contains(&row[offset]) || !(-32768..=32767).contains(&row[offset + 1])
        }) {
            return Err(format!(
                "Original binary spike/signed16 state outside range: {name}."
            ));
        }
    }
    if rows["raw_spike_trace"]
        .iter()
        .any(|r| !(0..=1).contains(&r[2]))
    {
        return Err("Original raw spike outside binary range.".into());
    }
    for name in [
        "input_trace",
        "numerical_trace",
        "raw_spike_trace",
        "service_trace",
    ] {
        if rows[name].iter().any(|row| {
            row.last()
                .is_none_or(|v| *v < 0 || *v as u64 >= run.manifest.capture_horizon_edges)
        }) {
            return Err(format!(
                "Original observed tick outside no-wrap horizon: {name}."
            ));
        }
    }
    for (index, row) in rows["service_trace"].iter().enumerate() {
        if row[..3] != [i64::from(run.manifest.epoch), index as i64, 0] {
            return Err("Original service epoch/ordinal/neuron identity sequence differs.".into());
        }
        if !(0..65536).contains(&row[3]) {
            return Err("Original embedded service timestamp outside unsigned16 range.".into());
        }
    }
    Ok(rows)
}
