// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete actual checker trace reconciliation

//! Decode successful actual opens and compare complete source/runtime role boundaries.

use crate::public_execution::Invocation;
use crate::public_runtime::Installation;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

/// ASCII whitespace as the Python verifier's ASCII regular expressions read it.
fn space(c: char) -> bool {
    matches!(c, ' ' | '\t' | '\n' | '\r' | '\x0b' | '\x0c')
}

/// Return the rest after one or more leading ASCII digits, or `None` when there are none.
fn after_digits(text: &str) -> Option<&str> {
    let rest = text.trim_start_matches(|c: char| c.is_ascii_digit());
    (rest.len() < text.len()).then_some(rest)
}

/// Return the rest after one or more leading ASCII whitespace bytes.
fn after_space(text: &str) -> Option<&str> {
    let rest = text.trim_start_matches(space);
    (rest.len() < text.len()).then_some(rest)
}

/// Tell whether the text after the flags is `)WS+=WS+DIGITS[<...>]WS*`.
fn closes(tail: &str) -> bool {
    let Some(rest) = tail
        .strip_prefix(')')
        .and_then(after_space)
        .and_then(|rest| rest.strip_prefix('='))
        .and_then(after_space)
        .and_then(after_digits)
    else {
        return false;
    };
    let rest = rest.trim_end_matches(space);
    rest.is_empty() || (rest.starts_with('<') && rest.ends_with('>') && rest.len() > 1)
}

/// Match one successful open record: `[PID ]openat[2](BASE, "NAME", FLAGS) = FD[<...>]`.
///
/// Returns the base, the quoted name without its quotes and the flags.
fn record(line: &str) -> Option<(&str, &str, &str)> {
    let start = after_digits(line).and_then(after_space).unwrap_or(line);
    let call = start.strip_prefix("openat")?;
    let call = call.strip_prefix('2').unwrap_or(call).strip_prefix('(')?;
    let (base, rest) = call.split_once(',')?;
    let quoted = rest.strip_prefix(" \"").filter(|_| !base.is_empty())?;
    let mut escaped = false;
    let end = quoted.char_indices().find_map(|(index, c)| {
        let closing = !escaped && c == '"';
        escaped = !escaped && c == '\\';
        closing.then_some(index)
    })?;
    let (name, rest) = (&quoted[..end], quoted[end + 1..].strip_prefix(", ")?);
    rest.match_indices(')')
        .find(|(index, _)| closes(&rest[*index..]))
        .map(|(index, _)| (base, name, &rest[..index]))
}

/// Decode one quoted trace path of plain characters and hexadecimal byte escapes.
fn quoted_path(content: &str) -> Result<String, String> {
    let mut bytes = Vec::new();
    let mut rest = content;
    while let Some(c) = rest.chars().next() {
        if c != '\\' {
            bytes.extend_from_slice(&rest.as_bytes()[..c.len_utf8()]);
            rest = &rest[c.len_utf8()..];
            continue;
        }
        let digits = rest
            .strip_prefix("\\x")
            .and_then(|tail| tail.get(..2))
            .filter(|pair| pair.bytes().all(|byte| byte.is_ascii_hexdigit()))
            .ok_or("Checker file trace has an invalid quoted path.")?;
        bytes.push(u8::from_str_radix(digits, 16).unwrap_or_default());
        rest = &rest[4..];
    }
    String::from_utf8(bytes).map_err(|_| "Checker observed path requires exact UTF-8.".to_owned())
}

/// Resolve one successfully opened name against its directory descriptor.
fn opened_path(base: &str, name: &str, directory: &Path) -> Result<PathBuf, String> {
    let mut path = PathBuf::from(name);
    if !path.is_absolute() {
        if base.starts_with("AT_FDCWD") {
            path = directory.join(path);
        } else {
            let anchor = after_digits(base)
                .and_then(|rest| rest.strip_prefix('<'))
                .and_then(|rest| rest.strip_suffix('>'))
                .filter(|anchor| !anchor.is_empty() && !anchor.contains('>'))
                .ok_or("Checker file trace has an unbound relative descriptor.")?;
            path = Path::new(anchor).join(path);
        }
    }
    path.canonicalize()
        .map_err(|_| "Actual checker observed file is unavailable.".to_owned())
}

/// Recover every successful regular-file open, preserving directory-descriptor anchoring.
///
/// The grammar is the Python verifier's: lines end only at a line feed, and any
/// line that is not a complete successful open record, including a failed open,
/// is not an observation.
pub(crate) fn opened(raw: &[u8], directory: &Path) -> Result<BTreeSet<PathBuf>, String> {
    let text = std::str::from_utf8(raw)
        .map_err(|_| "Checker file trace requires exact UTF-8.".to_owned())?;
    let mut paths = BTreeSet::new();
    for line in text.split('\n') {
        if line.contains("<unfinished ...>") || line.contains(" resumed>") {
            return Err("Checker file trace contains an incomplete open observation.".into());
        }
        let Some((base, encoded, flags)) = record(line) else {
            continue;
        };
        let name = quoted_path(encoded)?;
        if [
            "/proc/self/maps",
            "/sys/devices/system/cpu/possible",
            "/dev/urandom",
        ]
        .contains(&name.as_str())
            || flags.contains("O_DIRECTORY")
        {
            continue;
        }
        let path = opened_path(base, &name, directory)?;
        if path.is_file() {
            paths.insert(path);
        }
    }
    Ok(paths)
}

/// Require real complete source opens and refuse any live or unbound source fallback.
pub(crate) fn findings(
    actual: &Invocation,
    directory: &Path,
    source_files: &BTreeSet<PathBuf>,
    installation: &Installation,
) -> Result<Vec<String>, String> {
    let Some(observation) = actual
        .observation
        .as_ref()
        .filter(|_| !actual.trace.is_empty())
    else {
        return Ok(vec![
            "Actual source checker opened-file observation is unavailable.".into(),
        ]);
    };
    let observed = opened(&actual.trace, directory)?;
    let runtime: BTreeSet<_> = installation
        .observed_roles()
        .into_iter()
        .map(|(_, path)| path.canonicalize().unwrap_or(path))
        .collect();
    let data: BTreeSet<_> = [
        "stimuli.txt",
        "results_expected.txt",
        "results_verilog.txt",
        "checker-observation.json",
    ]
    .into_iter()
    .map(|name| directory.join(name))
    .collect();
    let mut result = Vec::new();
    if !source_files.is_subset(&observed) {
        result.push(
            "Actual source checker did not open its complete admitted source closure.".into(),
        );
    }
    if observed
        .iter()
        .any(|path| !source_files.contains(path) && !runtime.contains(path) && !data.contains(path))
    {
        result.push(
            "Actual source checker opened a file outside its complete runtime binding.".into(),
        );
    }
    if observation.modules.iter().any(|module| {
        module.name.starts_with("sc_neurocore") && !source_files.contains(Path::new(&module.path))
    }) {
        result.push("Actual source checker imported a live or unbound SC source fallback.".into());
    }
    Ok(result)
}

#[cfg(test)]
#[path = "../tests/unit/public_trace.rs"]
mod tests;
