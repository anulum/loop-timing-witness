// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — bounded JSON objects decoded as CPython's scanner does

//! Decode a run-bound JSON object with the refusals and precedence of the Python analysis.
//!
//! The Python analysis decodes every run-bound document through
//! `manifest_io.parse_bounded_json_object`, which drives CPython's JSON scanner
//! with hooks. This decoder follows the same recursive descent, so a document
//! with several defects is refused for the same first one:
//!
//! - nesting deeper than [`MAX_DEPTH`] brackets outside strings is refused
//!   before decoding;
//! - `NaN`, `Infinity`, `-Infinity` and decimals that overflow are refused
//!   where the scanner reaches them, naming the token;
//! - integers must fit the signed or unsigned 64-bit range;
//! - repeated member names are refused when their object closes, so an inner
//!   object's repetition is reported before an outer one;
//! - an unpaired surrogate escape is refused only after the whole document
//!   decoded, and before the top-level type is checked.
//!
//! Any other malformed input is `invalid JSON`. A repeated member name is
//! compared exactly, unpaired surrogates included, and is named as standard
//! error prints it, with `\udXXX` for each unpaired surrogate.
//!
//! [`decode_dispatch_object`] decodes as Python's `parse_dispatch_json_object`,
//! which only chooses the analysis: the same nesting bound, with integers kept
//! as their decimal text and unpaired surrogates kept.

use serde_json::{Map, Number, Value};
use std::collections::{BTreeMap, HashSet};
use std::fmt::Write as _;

/// Deepest array or object nesting a bounded document may use.
pub(crate) const MAX_DEPTH: usize = 64;

/// The member names of every object in document order, keyed by the object's path.
///
/// Python keeps decoded objects in document order and the analysis iterates
/// some of them, so the order in which it reads files follows the document.
pub(crate) type Orders = BTreeMap<Vec<String>, Vec<String>>;

/// Decode one bounded JSON object, labelling every refusal with its source.
pub(crate) fn decode_object(
    raw: &[u8],
    source: &str,
) -> Result<(Map<String, Value>, Orders), String> {
    decode(raw, source, true)
}

/// Decode one JSON object only to choose its analysis, as Python's
/// `parse_dispatch_json_object`: integers are their decimal text and an
/// unpaired surrogate escape is kept.
pub(crate) fn decode_dispatch_object(
    raw: &[u8],
    source: &str,
) -> Result<Map<String, Value>, String> {
    decode(raw, source, false).map(|(object, _)| object)
}

/// Decode one object nested at most [`MAX_DEPTH`] deep; `run_bounds` adds the
/// 64-bit integer range and the refusal of unpaired surrogates.
fn decode(
    raw: &[u8],
    source: &str,
    run_bounds: bool,
) -> Result<(Map<String, Value>, Orders), String> {
    let text = std::str::from_utf8(raw).map_err(|_| format!("{source}: not UTF-8"))?;
    if nesting_depth(text) > MAX_DEPTH {
        return Err(format!("{source}: JSON input exceeds decoder limits"));
    }
    let mut scanner = Scanner {
        bytes: text.as_bytes(),
        position: 0,
        unpaired: false,
        run_bounds,
        path: Vec::new(),
        orders: Orders::new(),
    };
    let value = scanner.document().map_err(|refusal| {
        format!(
            "{source}: {}",
            refusal.unwrap_or_else(|| "invalid JSON".to_owned())
        )
    })?;
    if run_bounds && scanner.unpaired {
        return Err(format!(
            "{source}: JSON text holds an unpaired surrogate escape"
        ));
    }
    match value {
        Value::Object(object) => Ok((object, scanner.orders)),
        _ => Err(format!("{source}: top-level JSON value must be an object")),
    }
}

/// Return the deepest bracket nesting outside JSON strings, as the Python pre-scan does.
pub(crate) fn nesting_depth(text: &str) -> usize {
    let (mut depth, mut deepest) = (0_i64, 0_i64);
    let (mut in_string, mut escaped) = (false, false);
    for character in text.chars() {
        if in_string {
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_string = false;
            }
        } else if character == '"' {
            in_string = true;
        } else if matches!(character, '[' | '{') {
            depth += 1;
            deepest = deepest.max(depth);
        } else if matches!(character, ']' | '}') {
            depth -= 1;
        }
    }
    usize::try_from(deepest).unwrap_or(0)
}

/// A refusal: `None` is invalid JSON, `Some` is an authored refusal text.
type Refusal = Option<String>;

/// One decoded backslash escape.
enum Escape {
    /// A character, a joined surrogate pair included.
    Character(char),
    /// A UTF-16 surrogate code unit without its partner.
    Unpaired(u32),
}

/// A decoded string: its text, with U+FFFD for each unpaired surrogate, and,
/// only when it holds one, its printed form with `\udXXX` for each.
///
/// The pair identifies the decoded code points exactly.
type Text = (String, Option<String>);

/// Recursive-descent state over validated UTF-8 bytes.
struct Scanner<'a> {
    bytes: &'a [u8],
    position: usize,
    unpaired: bool,
    run_bounds: bool,
    path: Vec<String>,
    orders: Orders,
}

impl Scanner<'_> {
    /// Decode one value surrounded only by JSON whitespace.
    fn document(&mut self) -> Result<Value, Refusal> {
        self.whitespace();
        let value = self.value()?;
        self.whitespace();
        if self.position == self.bytes.len() {
            Ok(value)
        } else {
            Err(None)
        }
    }

    /// Skip the four JSON whitespace characters.
    fn whitespace(&mut self) {
        while matches!(
            self.bytes.get(self.position),
            Some(b' ' | b'\t' | b'\n' | b'\r')
        ) {
            self.position += 1;
        }
    }

    /// Consume an exact literal at the current position.
    fn literal(&mut self, text: &str) -> bool {
        let found = self.bytes[self.position..].starts_with(text.as_bytes());
        if found {
            self.position += text.len();
        }
        found
    }

    /// Decode one value in the order CPython's scanner tries its alternatives.
    fn value(&mut self) -> Result<Value, Refusal> {
        match self.bytes.get(self.position) {
            Some(b'"') => self.string().map(|(text, _)| Value::String(text)),
            Some(b'{') => self.object(),
            Some(b'[') => self.array(),
            _ if self.literal("null") => Ok(Value::Null),
            _ if self.literal("true") => Ok(Value::Bool(true)),
            _ if self.literal("false") => Ok(Value::Bool(false)),
            _ => match self.number()? {
                Some(number) => Ok(number),
                None => {
                    for token in ["NaN", "Infinity", "-Infinity"] {
                        if self.literal(token) {
                            return Err(Some(format!("non-finite JSON number: {token}")));
                        }
                    }
                    Err(None)
                }
            },
        }
    }

    /// Decode an object, refusing a repeated name once the object closes.
    fn object(&mut self) -> Result<Value, Refusal> {
        self.position += 1;
        self.whitespace();
        let mut members: Vec<(Text, Value)> = Vec::new();
        if self.bytes.get(self.position) != Some(&b'}') {
            loop {
                if self.bytes.get(self.position) != Some(&b'"') {
                    return Err(None);
                }
                let name = self.string()?;
                self.whitespace();
                if !self.literal(":") {
                    return Err(None);
                }
                self.whitespace();
                self.path.push(name.0.clone());
                let value = self.value()?;
                self.path.pop();
                members.push((name, value));
                self.whitespace();
                if self.literal(",") {
                    self.whitespace();
                } else if self.bytes.get(self.position) == Some(&b'}') {
                    break;
                } else {
                    return Err(None);
                }
            }
        }
        self.position += 1;
        let order = members.iter().map(|((name, _), _)| name.clone()).collect();
        self.orders.insert(self.path.clone(), order);
        let mut seen = HashSet::new();
        let mut object = Map::new();
        for (name, value) in members {
            if !seen.insert(name.clone()) {
                let (text, printed) = name;
                let shown = printed.unwrap_or(text);
                return Err(Some(format!("duplicate JSON key: {shown}")));
            }
            object.insert(name.0, value);
        }
        Ok(Value::Object(object))
    }

    /// Decode an array; a separator must be followed by another value.
    fn array(&mut self) -> Result<Value, Refusal> {
        self.position += 1;
        self.whitespace();
        let mut items = Vec::new();
        if self.literal("]") {
            return Ok(Value::Array(items));
        }
        loop {
            self.path.push(items.len().to_string());
            let value = self.value()?;
            self.path.pop();
            items.push(value);
            self.whitespace();
            if self.literal("]") {
                return Ok(Value::Array(items));
            }
            if !self.literal(",") {
                return Err(None);
            }
            self.whitespace();
        }
    }

    /// Decode a string, joining surrogate pairs and recording an unpaired surrogate.
    fn string(&mut self) -> Result<Text, Refusal> {
        self.position += 1;
        let mut text = String::new();
        let mut printed: Option<String> = None;
        loop {
            let start = self.position;
            while let Some(&byte) = self.bytes.get(self.position) {
                if byte == b'"' || byte == b'\\' || byte < 0x20 {
                    break;
                }
                self.position += 1;
            }
            let run = std::str::from_utf8(&self.bytes[start..self.position])
                .ok()
                .ok_or(None)?;
            text.push_str(run);
            if let Some(shown) = printed.as_mut() {
                shown.push_str(run);
            }
            match self.bytes.get(self.position) {
                Some(b'"') => {
                    self.position += 1;
                    return Ok((text, printed));
                }
                Some(b'\\') => {
                    self.position += 1;
                    match self.escape()? {
                        Escape::Character(character) => {
                            text.push(character);
                            if let Some(shown) = printed.as_mut() {
                                shown.push(character);
                            }
                        }
                        Escape::Unpaired(unit) => {
                            self.unpaired = true;
                            let shown = printed.get_or_insert_with(|| text.clone());
                            let _ = write!(shown, "\\u{unit:04x}");
                            text.push(char::REPLACEMENT_CHARACTER);
                        }
                    }
                }
                _ => return Err(None),
            }
        }
    }

    /// Decode one backslash escape after its backslash.
    fn escape(&mut self) -> Result<Escape, Refusal> {
        let byte = *self.bytes.get(self.position).ok_or(None)?;
        self.position += 1;
        let simple = match byte {
            b'"' => '"',
            b'\\' => '\\',
            b'/' => '/',
            b'b' => '\u{8}',
            b'f' => '\u{c}',
            b'n' => '\n',
            b'r' => '\r',
            b't' => '\t',
            b'u' => {
                let unit = self.hex()?;
                if (0xd800..=0xdbff).contains(&unit)
                    && self.bytes[self.position..].starts_with(b"\\u")
                {
                    self.position += 2;
                    let low = self.hex()?;
                    if (0xdc00..=0xdfff).contains(&low) {
                        let joined = 0x10000 + ((unit - 0xd800) << 10) + (low - 0xdc00);
                        return char::from_u32(joined).map(Escape::Character).ok_or(None);
                    }
                    self.position -= 6;
                }
                return Ok(char::from_u32(unit).map_or(Escape::Unpaired(unit), Escape::Character));
            }
            _ => return Err(None),
        };
        Ok(Escape::Character(simple))
    }

    /// Read exactly four hexadecimal digits.
    fn hex(&mut self) -> Result<u32, Refusal> {
        let digits = self
            .bytes
            .get(self.position..self.position + 4)
            .ok_or(None)?;
        if !digits.iter().all(u8::is_ascii_hexdigit) {
            return Err(None);
        }
        self.position += 4;
        let digits = std::str::from_utf8(digits).ok().ok_or(None)?;
        u32::from_str_radix(digits, 16).ok().ok_or(None)
    }

    /// Match `-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?` and decode it with the bounds.
    fn number(&mut self) -> Result<Option<Value>, Refusal> {
        let start = self.position;
        let mut end = start + usize::from(self.bytes.get(start) == Some(&b'-'));
        match self.bytes.get(end) {
            Some(b'0') => end += 1,
            Some(b'1'..=b'9') => end = self.digits(end),
            _ => return Ok(None),
        }
        let mut float = false;
        if self.bytes.get(end) == Some(&b'.')
            && self.bytes.get(end + 1).is_some_and(u8::is_ascii_digit)
        {
            end = self.digits(end + 1);
            float = true;
        }
        if matches!(self.bytes.get(end), Some(b'e' | b'E')) {
            let sign = end + 1 + usize::from(matches!(self.bytes.get(end + 1), Some(b'-' | b'+')));
            if self.bytes.get(sign).is_some_and(u8::is_ascii_digit) {
                end = self.digits(sign);
                float = true;
            }
        }
        self.position = end;
        let token = std::str::from_utf8(&self.bytes[start..end])
            .ok()
            .ok_or(None)?;
        if float {
            let value: f64 = token.parse().ok().ok_or(None)?;
            return Number::from_f64(value)
                .map(|number| Some(Value::Number(number)))
                .ok_or_else(|| Some(format!("non-finite JSON number: {token}")));
        }
        if !self.run_bounds {
            return Ok(Some(Value::String(token.to_owned())));
        }
        let outside = || Some(format!("integer outside the 64-bit range: {token}"));
        if token.trim_start_matches('-').len() > 20 {
            return Err(outside());
        }
        let integer: i128 = token.parse().ok().ok_or(None)?;
        if let Ok(signed) = i64::try_from(integer) {
            Ok(Some(Value::from(signed)))
        } else {
            u64::try_from(integer)
                .map(|unsigned| Some(Value::from(unsigned)))
                .map_err(|_| outside())
        }
    }

    /// Return the position after a run of decimal digits.
    fn digits(&self, mut position: usize) -> usize {
        while self.bytes.get(position).is_some_and(u8::is_ascii_digit) {
            position += 1;
        }
        position
    }
}

#[cfg(test)]
#[path = "../tests/unit/control_json.rs"]
mod tests;
