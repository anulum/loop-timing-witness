// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python's text of strings, paths and operating-system errors

//! Print strings, paths and operating-system errors as the Python analysis prints them.
//!
//! A failed read in the Python analysis reaches the caller as `str(OSError)`:
//! `[Errno <number>] <strerror>: <repr(path)>`. This module builds the same text:
//! the C library's message, and CPython's `repr` of the path, in which bytes
//! that are not UTF-8 appear as surrogate escapes, as Python's file-system
//! decoding gives them.

use crate::control_printable::{DECIMAL, NON_PRINTABLE};
use std::ffi::OsStr;
use std::os::unix::ffi::OsStrExt;
use std::path::Path;

/// One unit of decoded text: a character, or a byte Python decodes as a surrogate escape.
enum Unit {
    Character(char),
    Escaped(u8),
}

/// Tell whether CPython's `str.isprintable` is true for one character.
pub(crate) fn printable(character: char) -> bool {
    !within(NON_PRINTABLE, character)
}

/// Tell whether CPython's `str.isdecimal` is true for one character.
pub(crate) fn python_decimal(character: char) -> bool {
    within(DECIMAL, character)
}

/// Tell whether a character lies in one of sorted, disjoint inclusive ranges.
fn within(ranges: &[(u32, u32)], character: char) -> bool {
    let code = u32::from(character);
    ranges
        .binary_search_by(|&(low, high)| {
            if high < code {
                std::cmp::Ordering::Less
            } else if low > code {
                std::cmp::Ordering::Greater
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

/// Decode bytes as UTF-8, keeping each invalid byte as Python's surrogate escape does.
fn units(bytes: &[u8]) -> Vec<Unit> {
    let mut units = Vec::new();
    let mut rest = bytes;
    while !rest.is_empty() {
        match std::str::from_utf8(rest) {
            Ok(text) => {
                units.extend(text.chars().map(Unit::Character));
                break;
            }
            Err(error) => {
                let (valid, invalid) = rest.split_at(error.valid_up_to());
                units.extend(String::from_utf8_lossy(valid).chars().map(Unit::Character));
                let length = error.error_len().unwrap_or(invalid.len());
                units.extend(invalid[..length].iter().map(|&byte| Unit::Escaped(byte)));
                rest = &invalid[length..];
            }
        }
    }
    units
}

/// CPython's `repr` of decoded text.
fn repr(units: &[Unit]) -> String {
    let has = |wanted: char| {
        units
            .iter()
            .any(|unit| matches!(unit, Unit::Character(character) if *character == wanted))
    };
    let quote = if has('\'') && !has('"') { '"' } else { '\'' };
    let mut text = String::from(quote);
    for unit in units {
        match unit {
            Unit::Escaped(byte) => text.push_str(&format!("\\udc{byte:02x}")),
            Unit::Character(character) => match *character {
                '\\' => text.push_str("\\\\"),
                '\t' => text.push_str("\\t"),
                '\n' => text.push_str("\\n"),
                '\r' => text.push_str("\\r"),
                character if character == quote => {
                    text.push('\\');
                    text.push(character);
                }
                character if printable(character) => text.push(character),
                character => {
                    let code = u32::from(character);
                    text.push_str(&if code <= 0xff {
                        format!("\\x{code:02x}")
                    } else if code <= 0xffff {
                        format!("\\u{code:04x}")
                    } else {
                        format!("\\U{code:08x}")
                    });
                }
            },
        }
    }
    text.push(quote);
    text
}

/// CPython's `repr` of a string, as an f-string's `!r` writes it.
pub(crate) fn python_repr(text: &str) -> String {
    repr(&text.chars().map(Unit::Character).collect::<Vec<_>>())
}

/// Python's printed form of a path: invalid bytes appear as `\udcXX`, as stderr shows them.
pub(crate) fn python_display(path: &Path) -> String {
    units(path.as_os_str().as_bytes())
        .iter()
        .map(|unit| match unit {
            Unit::Character(character) => character.to_string(),
            Unit::Escaped(byte) => format!("\\udc{byte:02x}"),
        })
        .collect()
}

/// Python's parts of a pure POSIX path: the root, `""`, `"/"` or `"//"` (two
/// leading separators are kept, three or more are one), and the names
/// without empty and `.` parts.
pub(crate) fn pure_parts(path: &Path) -> (&'static [u8], Vec<&[u8]>) {
    let bytes = path.as_os_str().as_bytes();
    let root: &'static [u8] = if bytes.starts_with(b"//") && !bytes.starts_with(b"///") {
        b"//"
    } else if bytes.starts_with(b"/") {
        b"/"
    } else {
        b""
    };
    let parts = bytes
        .split(|&byte| byte == b'/')
        .filter(|part| !part.is_empty() && *part != b".")
        .collect();
    (root, parts)
}

/// Python's `str(Path(text))` of a published output, as standard output prints it.
///
/// A published output always ends in a name, so the text is never empty.
pub(crate) fn pure_path(path: &Path) -> String {
    let (root, parts) = pure_parts(path);
    python_display(Path::new(OsStr::from_bytes(
        &[root, &parts.join(&b'/')].concat(),
    )))
}

/// The error number and the C library's message for it.
fn strerror(error: &std::io::Error) -> (i32, String) {
    let number = error.raw_os_error().unwrap_or_default();
    let message = std::io::Error::from_raw_os_error(number).to_string();
    let suffix = format!(" (os error {number})");
    (
        number,
        message.strip_suffix(&suffix).unwrap_or(&message).to_owned(),
    )
}

/// `str(OSError)` for an operating-system error without a file name.
pub(crate) fn os_error_without_path(error: &std::io::Error) -> String {
    let (number, strerror) = strerror(error);
    format!("[Errno {number}] {strerror}")
}

/// `str(OSError)` for an operating-system error on one path.
pub(crate) fn os_error(error: &std::io::Error, path: &Path) -> String {
    let (number, strerror) = strerror(error);
    format!(
        "[Errno {number}] {strerror}: {}",
        repr(&units(path.as_os_str().as_bytes()))
    )
}

#[cfg(test)]
#[path = "../tests/unit/control_text.rs"]
mod tests;
