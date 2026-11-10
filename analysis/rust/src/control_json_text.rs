// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python's indented JSON text

//! Write a JSON value as Python's
//! `json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)` writes it.
//!
//! Members are sorted by code point, which is the order of the decoded map;
//! integers are written as digits and floats as Python's `repr`; strings escape
//! only the quote, the backslash and control characters.

use crate::control_number::python_float;
use serde_json::Value;
use std::fmt::Write as _;

/// `json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)` and a newline.
pub(crate) fn canonical_json(value: &Value) -> Vec<u8> {
    let mut text = String::new();
    json_value(value, 0, &mut text);
    text.push('\n');
    text.into_bytes()
}

/// Append one value at an indentation depth.
fn json_value(value: &Value, depth: usize, text: &mut String) {
    match value {
        Value::Null => text.push_str("null"),
        Value::Bool(flag) => text.push_str(if *flag { "true" } else { "false" }),
        Value::Number(number) => text.push_str(&number_text(value, number.is_f64())),
        Value::String(string) => json_string(string, text),
        Value::Array(items) => {
            let rendered = items
                .iter()
                .map(|item| {
                    let mut part = String::new();
                    json_value(item, depth + 1, &mut part);
                    part
                })
                .collect();
            bracketed(('[', ']'), rendered, depth, text);
        }
        Value::Object(members) => {
            let rendered = members
                .iter()
                .map(|(name, member)| {
                    let mut part = String::new();
                    json_string(name, &mut part);
                    part.push_str(": ");
                    json_value(member, depth + 1, &mut part);
                    part
                })
                .collect();
            bracketed(('{', '}'), rendered, depth, text);
        }
    }
}

/// Append rendered items between brackets, one per line, or the bare brackets when empty.
fn bracketed(brackets: (char, char), items: Vec<String>, depth: usize, text: &mut String) {
    text.push(brackets.0);
    if !items.is_empty() {
        let inner = "  ".repeat(depth + 1);
        text.push('\n');
        text.push_str(&inner);
        text.push_str(&items.join(&format!(",\n{inner}")));
        text.push('\n');
        text.push_str(&"  ".repeat(depth));
    }
    text.push(brackets.1);
}

/// Python's text of a decoded JSON number: integers as digits, floats as `repr`.
pub(crate) fn number_text(value: &Value, float: bool) -> String {
    if float {
        python_float(value.as_f64().expect("float"))
    } else {
        value.to_string()
    }
}

/// A JSON string as Python's encoder writes it without ASCII escaping.
fn json_string(string: &str, text: &mut String) {
    text.push('"');
    for character in string.chars() {
        match character {
            '"' => text.push_str("\\\""),
            '\\' => text.push_str("\\\\"),
            '\n' => text.push_str("\\n"),
            '\r' => text.push_str("\\r"),
            '\t' => text.push_str("\\t"),
            '\u{8}' => text.push_str("\\b"),
            '\u{c}' => text.push_str("\\f"),
            control if control < ' ' => {
                let _ = write!(text, "\\u{:04x}", u32::from(control));
            }
            other => text.push(other),
        }
    }
    text.push('"');
}
