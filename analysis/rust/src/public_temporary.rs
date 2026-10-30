// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — exclusive consumer-owned temporary directories

//! Keep owned source copies and staging directories finite and scoped to one invocation.

use std::os::unix::fs::DirBuilderExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

/// An exclusive owned directory removed on completion or early refusal.
pub(crate) struct OwnedDirectory {
    pub path: PathBuf,
}

impl OwnedDirectory {
    /// Allocate exclusively beneath a consumer-selected existing parent.
    pub fn create(parent: &Path, prefix: &str) -> Result<Self, String> {
        static SEQUENCE: AtomicU64 = AtomicU64::new(0);
        let parent = parent
            .canonicalize()
            .map_err(|_| "Consumer temporary parent is unavailable.".to_owned())?;
        let epoch = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "Consumer temporary clock is unavailable.".to_owned())?
            .as_nanos();
        for _ in 0..16 {
            let ordinal = SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!("{prefix}{}-{epoch}-{ordinal}", std::process::id()));
            match std::fs::DirBuilder::new().mode(0o700).create(&path) {
                Ok(()) => return Ok(Self { path }),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(_) => {
                    return Err("Cannot create an exclusive consumer temporary directory.".into());
                }
            }
        }
        Err("Cannot allocate a distinct consumer temporary directory.".into())
    }
}

impl Drop for OwnedDirectory {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.path);
    }
}
