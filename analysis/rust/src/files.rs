// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Finite complete file acquisition and SHA-256 binding before interpretation.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io::Read;
use std::os::fd::AsRawFd;
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;

const PATH_LIMIT: usize = 4096;
const LINUX_O_NOFOLLOW: i32 = 0o400000;
const LINUX_O_NONBLOCK: i32 = 0o4000;
const LINUX_O_DIRECTORY: i32 = 0o200000;

/// Complete closed original file reference.
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FileRef {
    /// Original within-run relative name.
    pub path: String,
    /// Original whole-file lowercase SHA-256.
    pub sha256: String,
    /// Exact whole-file length, including a present zero-byte file.
    pub byte_length: u64,
}

/// Return the actual complete-byte digest without source execution.
pub(crate) fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

/// Open every canonical within-root component through an owned directory descriptor.
///
/// Linux procfs names refer only to descriptors held by this process; acquisition
/// symlinks never select a parent directory or the final file. O_NONBLOCK makes
/// an actual FIFO inspectable and rejectable without waiting for a writer.
fn regular_descriptor(root: &Path, name: &str) -> Result<File, String> {
    if name.is_empty()
        || name.len() > PATH_LIMIT
        || name.split('/').any(|part| {
            part.is_empty()
                || part == "."
                || part == ".."
                || !part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"_.-".contains(&byte))
        })
    {
        return Err(format!("Invalid within-run original path: {name}."));
    }
    let resolved = root
        .canonicalize()
        .map_err(|_| "Run directory unavailable.".to_owned())?;
    let mut directory = OpenOptions::new()
        .read(true)
        .custom_flags(LINUX_O_NOFOLLOW | LINUX_O_DIRECTORY)
        .open(resolved)
        .map_err(|_| "Run directory descriptor unavailable.".to_owned())?;
    let (parents, final_name) = name.rsplit_once('/').unwrap_or(("", name));
    for part in parents.split('/').filter(|part| !part.is_empty()) {
        let anchored = format!("/proc/self/fd/{}/{part}", directory.as_raw_fd());
        directory = OpenOptions::new()
            .read(true)
            .custom_flags(LINUX_O_NOFOLLOW | LINUX_O_DIRECTORY)
            .open(anchored)
            .map_err(|_| format!("Cannot open original parent without symlinks: {name}."))?;
    }
    let anchored = format!("/proc/self/fd/{}/{final_name}", directory.as_raw_fd());
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(LINUX_O_NOFOLLOW | LINUX_O_NONBLOCK)
        .open(anchored)
        .map_err(|_| format!("Cannot open original file without symlinks: {name}."))?;
    if !file
        .metadata()
        .map_err(|_| format!("Cannot inspect original file descriptor: {name}."))?
        .is_file()
    {
        return Err(format!(
            "Original file is not regular within the run: {name}."
        ));
    }
    Ok(file)
}

/// Read one complete regular original through a finite no-follow descriptor.
pub(crate) fn read_regular(root: &Path, name: &str, limit: usize) -> Result<Vec<u8>, String> {
    if limit >= isize::MAX as usize {
        return Err("Original file allocation cannot admit an index-sized boundary check.".into());
    }
    let stream = regular_descriptor(root, name)?;
    let mut raw = Vec::new();
    stream
        .take(limit as u64 + 1)
        .read_to_end(&mut raw)
        .map_err(|_| format!("Cannot read full original file: {name}."))?;
    if raw.len() > limit {
        return Err(format!("Original file exceeds allocation: {name}."));
    }
    Ok(raw)
}

/// Bind complete original bytes through bounded regular no-follow descriptors.
///
/// Reference names must contain only canonical ASCII components, at most4096bytes.
/// Internal and escaping symlinks, FIFO and directory inputs are refused before
/// reading. Missing files cannot substitute for an actual zero-byte original.
///
/// # Errors
///
/// Returns authored refusals when the path, file kind, complete length/digest or
/// caller-selected allocation cannot be established. The caller selects a stable
/// acquisition root; Linux procfs must expose this process's owned descriptors.
pub fn read_bound(root: &Path, reference: &FileRef, limit: usize) -> Result<Vec<u8>, String> {
    read_with_expected(root, reference, limit, None)
}

/// Bind an original against both a reviewed complete body and its file reference.
///
/// Exact bytes are compared before hashing so the consumer's body check remains
/// independent of the declared digest. Path, allocation, length and SHA-256
/// verification are retained. The caller owns the expected body and diagnostic.
///
/// # Errors
///
/// Returns the caller's diagnostic on a different complete body, or the ordinary
/// file-binding refusal when reference, descriptor or length/digest checks fail.
pub fn read_expected(
    root: &Path,
    reference: &FileRef,
    limit: usize,
    expected: &[u8],
    mismatch_message: &str,
) -> Result<Vec<u8>, String> {
    read_with_expected(root, reference, limit, Some((expected, mismatch_message)))
}

/// Share descriptor and identity checks between digest-only and exact-body callers.
fn read_with_expected(
    root: &Path,
    reference: &FileRef,
    limit: usize,
    expected: Option<(&[u8], &str)>,
) -> Result<Vec<u8>, String> {
    if reference.byte_length > limit as u64
        || reference.sha256.len() != 64
        || !reference
            .sha256
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(format!(
            "Invalid original file reference: {}.",
            reference.path
        ));
    }
    let raw = read_regular(root, &reference.path, reference.byte_length as usize)?;
    if let Some((body, message)) = expected
        && raw != body
    {
        return Err(message.into());
    }
    if raw.len() as u64 != reference.byte_length || digest(&raw) != reference.sha256 {
        return Err(format!(
            "Original whole length/SHA-256 differs: {}.",
            reference.path
        ));
    }
    Ok(raw)
}

/// Decode a full closed typed JSON object with field/range/duplicate refusals.
pub(crate) fn decode<T: serde::de::DeserializeOwned>(raw: &[u8], name: &str) -> Result<T, String> {
    serde_json::from_slice(&crate::json_integer::integer_zeroes(raw))
        .map_err(|_| format!("Invalid original {name}."))
}

/// Decode a closed actual receipt as the Python receipt reader does.
///
/// A document that is not one strict JSON object names the document; any other
/// departure from the closed typed form refuses the receipt as incomplete.
pub(crate) fn receipt<T: serde::de::DeserializeOwned>(raw: &[u8], name: &str) -> Result<T, String> {
    let object = crate::strict_json::decode_object(raw, name)?;
    serde_json::from_value(serde_json::Value::Object(object))
        .map_err(|_| format!("Invalid complete actual receipt: {name}."))
}
