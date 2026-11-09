// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — atomic publication of a control report directory

//! Publish a control report directory as Python's `publish_report_directory`.
//!
//! The destination is the resolved parent joined with the requested name. An
//! existing destination, even a dangling link, and a missing parent are
//! refused with Python's texts. Linux `renameat2(RENAME_NOREPLACE)` is first
//! exercised on the parent, then every file is staged in a new private
//! directory beside the destination, which is renamed into place without
//! replacing anything. A failed step removes what it staged.

use crate::control_text::{os_error, os_error_without_path, pure_parts, python_display};
use rustix::fs::{CWD, RenameFlags, renameat_with};
use std::collections::HashMap;
use std::ffi::{OsStr, OsString};
use std::io::Write as _;
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::os::unix::fs::DirBuilderExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

/// A new private directory that is removed again unless it was published.
struct Staging(PathBuf);

impl Staging {
    /// Create a uniquely named directory with mode 0700, as `tempfile.mkdtemp`.
    fn create(parent: &Path, prefix: &str) -> Result<Self, String> {
        static SEQUENCE: AtomicU64 = AtomicU64::new(0);
        let epoch = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let ordinal = SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = parent.join(format!("{prefix}{}{epoch}{ordinal}", std::process::id()));
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&path)
            .map_err(|error| os_error(&error, &path))?;
        Ok(Self(path))
    }
}

impl Drop for Staging {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// Rename a directory without replacing an existing destination.
fn rename(source: &Path, target: &Path) -> Result<(), String> {
    renameat_with(CWD, source, CWD, target, RenameFlags::NOREPLACE)
        .map_err(|error| os_error(&std::io::Error::from(error), target))
}

/// Python's `os.path.realpath(path)` without `strict`, as `Path.resolve()` uses it.
///
/// Parts are resolved left to right from the root or the working directory:
/// `.` and empty parts are skipped, `..` drops the last resolved part, a
/// symbolic link is replaced by its resolved target, and a part that cannot be
/// inspected or read is kept as written. A link met again while it is being
/// resolved, a loop, is kept as written too.
fn realpath(path: &Path) -> Result<PathBuf, String> {
    let bytes = path.as_os_str().as_bytes();
    let mut rest: Vec<Option<Vec<u8>>> = bytes
        .split(|&byte| byte == b'/')
        .rev()
        .map(|part| Some(part.to_vec()))
        .collect();
    let mut count = rest.len();
    let mut resolved: Vec<u8> = if bytes.starts_with(b"/") {
        b"/".to_vec()
    } else {
        std::env::current_dir()
            .map_err(|error| os_error_without_path(&error))?
            .into_os_string()
            .into_vec()
    };
    let mut seen: HashMap<Vec<u8>, Option<Vec<u8>>> = HashMap::new();
    while count > 0 {
        let Some(name) = rest.pop().expect("a pending part") else {
            let link = rest.pop().expect("a resolved link").expect("a link path");
            seen.insert(link, Some(resolved.clone()));
            continue;
        };
        count -= 1;
        if name.is_empty() || name == b"." {
            continue;
        }
        if name == b".." {
            let cut = resolved
                .iter()
                .rposition(|&byte| byte == b'/')
                .expect("an absolute path");
            resolved.truncate(cut.max(1));
            continue;
        }
        let mut next = resolved.clone();
        if next != b"/" {
            next.push(b'/');
        }
        next.extend_from_slice(&name);
        let candidate = Path::new(OsStr::from_bytes(&next));
        let link = std::fs::symlink_metadata(candidate).is_ok_and(|status| status.is_symlink());
        let target = if link {
            match seen.get(&next) {
                Some(Some(done)) => {
                    resolved.clone_from(done);
                    continue;
                }
                Some(None) => None,
                None => std::fs::read_link(candidate).ok(),
            }
        } else {
            None
        };
        let Some(target) = target else {
            resolved = next;
            continue;
        };
        let target = target.into_os_string().into_vec();
        if target.starts_with(b"/") {
            resolved = b"/".to_vec();
        }
        seen.insert(next.clone(), None);
        rest.push(Some(next));
        rest.push(None);
        let parts: Vec<Option<Vec<u8>>> = target
            .split(|&byte| byte == b'/')
            .rev()
            .map(|part| Some(part.to_vec()))
            .collect();
        count += parts.len();
        rest.extend(parts);
    }
    Ok(PathBuf::from(OsString::from_vec(resolved)))
}

/// Python's `(path.parent, path.name)` of a pure POSIX path.
fn parent_and_name(path: &Path) -> (PathBuf, &OsStr) {
    let (root, mut parts) = pure_parts(path);
    let name = parts.pop().unwrap_or_default();
    let mut parent = [root, &parts.join(&b'/')].concat();
    if parent.is_empty() {
        parent.push(b'.');
    }
    (
        PathBuf::from(OsString::from_vec(parent)),
        OsStr::from_bytes(name),
    )
}

/// Create the report directory only after every file is staged.
pub(crate) fn publish_report_directory(
    output: &Path,
    files: &[(String, Vec<u8>)],
) -> Result<(), String> {
    let (requested, name) = parent_and_name(output);
    let resolved = realpath(&requested)?;
    let target = if name.is_empty() {
        resolved
    } else {
        resolved.join(name)
    };
    if std::fs::symlink_metadata(&target).is_ok() {
        return Err(format!(
            "report directory already exists: {}",
            python_display(&target)
        ));
    }
    let parent = target.parent().unwrap_or(&target);
    if !parent.is_dir() {
        return Err(format!(
            "report parent does not exist: {}",
            python_display(parent)
        ));
    }
    let probe = Staging::create(parent, ".report-publication-probe.")?;
    let source = probe.0.join("source");
    std::fs::create_dir(&source).map_err(|error| os_error(&error, &source))?;
    rename(&source, &probe.0.join("destination"))?;
    drop(probe);
    let mut prefix = OsStr::new(".").to_os_string();
    prefix.push(name);
    prefix.push(".");
    let staging = Staging::create(parent, &prefix.to_string_lossy())?;
    for (file, content) in files {
        write_file(&staging.0.join(file), content)?;
    }
    rename(&staging.0, &target)
}

/// Write one new file as Python's `Path.write_bytes`: a failed open names the
/// path, a failed write does not.
fn write_file(path: &Path, content: &[u8]) -> Result<(), String> {
    let mut file = std::fs::File::create(path).map_err(|error| os_error(&error, path))?;
    file.write_all(content)
        .map_err(|error| os_error_without_path(&error))
}

#[cfg(test)]
#[path = "../tests/unit/control_publication.rs"]
mod tests;
