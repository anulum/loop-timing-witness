// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Rust dependency records of AMP images

//! Hash the Rust sources that rustc's dependency records of an AMP image name.
//!
//! [`rust_dependency_hashes`] ports the Python module `amp_rust_dependencies`,
//! which the image receipt check uses for an image built with the Rust
//! kernel. Every digest, every refusal text and the order in which refusals
//! and read errors are reached is Python's. The crate tests hold it to the
//! corpus that `tests/test_amp_rust_dependency_corpus.py` builds from
//! Python's own reader and `shlex.split`.
//!
//! A record holds output rules and phony source rules. It is read as Python's
//! `read_text(encoding="utf-8")` reads it, with universal newlines, split into
//! lines at Python's line boundaries, and each side of a rule is split into
//! words by a port of CPython's POSIX `shlex.split`.
//!
//! [`rust_dependency_hashes`]: crate::amp_rust_dependencies::rust_dependency_hashes

use crate::amp_failure::AmpFailure;
use crate::amp_shell_words::split;
use crate::control_manifest::read_file;
use crate::control_paths::{pure, realpath};
use crate::control_pattern::python_space;
use crate::files::digest;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// Python's text for a Rust rule that is malformed, a comment among them.
const MALFORMED_RULE: &str = "Rust dependency rule is malformed or uses ambient environment";
/// Python's text for a Rust source outside the source snapshot.
const ESCAPING_SOURCE: &str = "Rust dependency source paths escape the original source snapshot";

/// Tell whether Python's `text.strip()` is empty.
fn blank(text: &str) -> bool {
    text.chars().all(python_space)
}

/// Tell whether a character ends a line for Python's `str.splitlines`.
///
/// The carriage return is left out: universal newlines have already turned
/// every one into a line feed.
fn line_boundary(character: char) -> bool {
    matches!(
        character,
        '\n' | '\u{b}' | '\u{c}' | '\u{1c}'..='\u{1e}' | '\u{85}' | '\u{2028}' | '\u{2029}'
    )
}

/// Read one record as Python's `read_text(encoding="utf-8")` does, universal
/// newlines included, refusing text that is not UTF-8.
fn record_text(path: &Path) -> Result<String, AmpFailure> {
    let content = read_file(path).map_err(|failure| AmpFailure::Os(failure.text()))?;
    let text = String::from_utf8(content)
        .map_err(|_| AmpFailure::Refused("Rust dependency record is not UTF-8".into()))?;
    Ok(text.replace("\r\n", "\n").replace('\r', "\n"))
}

/// Python's `sha256_of_file`: the digest of a whole file, or the `OSError`
/// text of opening or reading it.
fn file_digest(path: &Path) -> Result<String, AmpFailure> {
    let content = read_file(path).map_err(|failure| AmpFailure::Os(failure.text()))?;
    Ok(digest(&content))
}

/// The sources one Rust record names, reconciled with its phony rules.
///
/// Blank lines are skipped. Every other line is one rule with one target;
/// a rule with words adds them as sources, a rule without words is a phony
/// rule for its target, and every phony target must be a source.
fn record_sources(text: &str) -> Result<BTreeSet<String>, &'static str> {
    let mut sources = BTreeSet::new();
    let mut phony = BTreeSet::new();
    for line in text.split(line_boundary) {
        if blank(line) {
            continue;
        }
        let Some((target, words)) = line.split_once(':').filter(|(target, _)| {
            !blank(target) && !line.trim_start_matches(python_space).starts_with('#')
        }) else {
            return Err(MALFORMED_RULE);
        };
        let targets = split(target).map_err(|_| MALFORMED_RULE)?;
        let [target] = targets.as_slice() else {
            return Err("Rust dependency rule requires one original output or phony target");
        };
        let names = split(words).map_err(|_| MALFORMED_RULE)?;
        if names.is_empty() {
            phony.insert(target.clone());
        } else {
            sources.extend(names);
        }
    }
    if sources.is_empty() || !phony.is_subset(&sources) {
        return Err("Rust dependency source closure is empty or its phony rules disagree");
    }
    Ok(sources)
}

/// Hash every original Rust source that rustc's dependency records name.
///
/// Make continuations become spaces. Each record's sources are checked and
/// read in sorted order: a source must be relative and resolve inside
/// `directory`'s `source` tree. The result is keyed by the names as the
/// records write them.
///
/// # Errors
///
/// [`AmpFailure::Refused`] with Python's text when there is no record, or
/// a record is not UTF-8, holds a malformed rule or comment, a rule without
/// one target, no source or a phony rule for a name it does not source, or a
/// source escapes the snapshot; [`AmpFailure::Os`] when a record or a
/// source cannot be read. The first failure in record and source order is
/// reported.
pub fn rust_dependency_hashes(
    records: &[PathBuf],
    directory: &Path,
) -> Result<BTreeMap<String, String>, AmpFailure> {
    if records.is_empty() {
        let text = "Rust compilation requires actual dependency records";
        return Err(AmpFailure::Refused(text.into()));
    }
    let snapshot = realpath(directory).map_err(AmpFailure::Os)?.join("source");
    let mut result = BTreeMap::new();
    for record in records {
        let text = record_text(record)?.replace("\\\n", " ");
        let sources = record_sources(&text).map_err(|text| AmpFailure::Refused(text.into()))?;
        for name in sources {
            let path = pure(&directory.join(&name));
            if name.starts_with('/')
                || !realpath(&path)
                    .map_err(AmpFailure::Os)?
                    .starts_with(&snapshot)
            {
                return Err(AmpFailure::Refused(ESCAPING_SOURCE.into()));
            }
            let identity = file_digest(&path)?;
            result.insert(name, identity);
        }
    }
    Ok(result)
}

#[cfg(test)]
#[path = "../tests/unit/amp_rust_dependencies.rs"]
mod tests;
