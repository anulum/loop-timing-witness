// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python path semantics of the analysis command

//! Split, print and resolve paths as Python's `pathlib` and `posixpath` do.
//!
//! A pure path keeps a root of `""`, `"/"` or `"//"` and drops empty and `.`
//! parts. Resolution follows CPython 3.15's non-strict `os.path.realpath`,
//! which `Path.resolve()` uses.

use crate::control_text::{os_error_without_path, python_display};
use std::collections::HashMap;
use std::ffi::{OsStr, OsString};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};

/// Python's parts of a pure POSIX path: the root, `""`, `"/"` or `"//"` (two
/// leading separators are kept, three or more are one), and the names
/// without empty and `.` parts.
fn pure_parts(path: &Path) -> (&'static [u8], Vec<&[u8]>) {
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

/// Python's `os.path.realpath(path)` without `strict`, as `Path.resolve()` uses it.
///
/// Parts are resolved left to right from the root or the working directory:
/// `.` and empty parts are skipped, `..` drops the last resolved part, a
/// symbolic link is replaced by its resolved target, and a part that cannot be
/// inspected or read is kept as written. A link met again while it is being
/// resolved, a loop, is kept as written too.
pub(crate) fn realpath(path: &Path) -> Result<PathBuf, String> {
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
pub(crate) fn parent_and_name(path: &Path) -> (PathBuf, &OsStr) {
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
