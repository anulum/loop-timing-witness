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

/// Decode one hex-escaped path emitted by the pinned strace -xx profile.
fn hex_path(encoded: &str) -> Result<PathBuf, String> {
    if !encoded.len().is_multiple_of(4) {
        return Err("Checker file trace has an invalid hex path.".into());
    }
    let mut bytes = Vec::new();
    for part in encoded.as_bytes().as_chunks::<4>().0 {
        if &part[..2] != b"\\x" {
            return Err("Checker file trace has an invalid hex path.".into());
        }
        let pair = std::str::from_utf8(&part[2..])
            .map_err(|_| "Checker file trace has an invalid hex path.".to_owned())?;
        bytes.push(
            u8::from_str_radix(pair, 16)
                .map_err(|_| "Checker file trace has an invalid hex path.".to_owned())?,
        );
    }
    let text = String::from_utf8(bytes)
        .map_err(|_| "Checker observed path requires exact UTF-8.".to_owned())?;
    Ok(PathBuf::from(text))
}

/// Recover every successful regular-file open, preserving directory-descriptor anchoring.
pub(crate) fn opened(raw: &[u8], directory: &Path) -> Result<BTreeSet<PathBuf>, String> {
    let text = std::str::from_utf8(raw)
        .map_err(|_| "Checker file trace requires exact UTF-8.".to_owned())?;
    let mut paths = BTreeSet::new();
    for line in text.lines() {
        if line.contains("<unfinished ...>") || line.contains(" resumed>") {
            return Err("Checker file trace contains an incomplete open observation.".into());
        }
        let Some((_, call)) = line
            .split_once("openat(")
            .or_else(|| line.split_once("openat2("))
        else {
            continue;
        };
        let Some((arguments, result)) = call.rsplit_once(" = ") else {
            continue;
        };
        let descriptor = result.split('<').next().unwrap_or(result).trim();
        if descriptor.parse::<u32>().is_err() {
            continue;
        }
        let (base, remainder) = arguments
            .split_once(", \"")
            .ok_or("Checker file trace has an unsupported open record.")?;
        let (encoded, flags) = remainder
            .split_once('"')
            .ok_or("Checker file trace has an incomplete pathname.")?;
        if flags.contains("O_DIRECTORY") {
            continue;
        }
        let mut path = hex_path(encoded)?;
        if [
            "/proc/self/maps",
            "/sys/devices/system/cpu/possible",
            "/dev/urandom",
        ]
        .iter()
        .any(|name| path == Path::new(name))
        {
            continue;
        }
        if !path.is_absolute() {
            if base.starts_with("AT_FDCWD") {
                path = directory.join(path);
            } else {
                let (_, name) = base
                    .split_once('<')
                    .ok_or("Checker file trace has an unbound relative descriptor.")?;
                let name = name
                    .strip_suffix('>')
                    .ok_or("Checker file trace has an unbound relative descriptor.")?;
                path = Path::new(name).join(path);
            }
        }
        let resolved = path
            .canonicalize()
            .map_err(|_| "Actual checker observed file is unavailable.".to_owned())?;
        if resolved.is_file() {
            paths.insert(resolved);
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
    let Some(observation) = &actual.observation else {
        return Ok(vec![
            "Actual source checker opened-file observation is unavailable.".into(),
        ]);
    };
    if actual.trace.is_empty() {
        return Ok(vec![
            "Actual source checker opened-file observation is unavailable.".into(),
        ]);
    }
    let observed = opened(&actual.trace, directory)?;
    let runtime: BTreeSet<_> = installation
        .observed_roles()
        .into_iter()
        .map(|(_, path)| path)
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
