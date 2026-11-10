// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — single-node changes of the shared corpora

//! Apply one change of a corpus that Python generated to its base document.
//!
//! A change is `{"set": value}`, `{"remove": member}` or `{"add": member}` at
//! a path of member names and array indexes, as `apply` in
//! `tests/test_control_schema_corpus.py` applies it.

use serde_json::Value;

/// Apply one change at a path: replace the node, remove a member or add one with value 1.
pub(crate) fn changed(base: &Value, path: &[Value], change: &Value) -> Value {
    if let Some(value) = change.get("set").filter(|_| path.is_empty()) {
        return value.clone();
    }
    let mut document = base.clone();
    let keep = if change.get("set").is_some() {
        path.len() - 1
    } else {
        path.len()
    };
    let mut node = &mut document;
    for part in &path[..keep] {
        node = match part {
            Value::String(name) => &mut node[name.as_str()],
            index => &mut node[index_of(index)],
        };
    }
    if let Some(value) = change.get("set") {
        match &path[keep] {
            Value::String(name) => node[name.as_str()] = value.clone(),
            index => node[index_of(index)] = value.clone(),
        }
    } else if let Some(name) = change.get("remove") {
        node.as_object_mut()
            .expect("object")
            .remove(name.as_str().expect("member"));
    } else {
        node[change["add"].as_str().expect("member")] = Value::from(1);
    }
    document
}

/// The array index a path part names.
fn index_of(part: &Value) -> usize {
    usize::try_from(part.as_u64().expect("index")).expect("index")
}
