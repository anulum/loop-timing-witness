// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — original declaration filesystem controls

//! Own an isolated directory containing only exact recorded or deliberately invalid input bytes.

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

/// Exact original declarations are not a substitute for their absent acquisition files.
pub struct Declaration {
    root: PathBuf,
}

impl Declaration {
    /// Create an exclusive owned directory and verify the complete recorded declaration.
    pub fn recorded() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("current clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "witness-declaration-{}-{now}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).expect("exclusive original declaration allocation");
        assert_eq!(
            format!("{:x}", Sha256::digest(Self::raw())),
            "3a982fb1aa66f64135ce622c68e408c6dcefb78022cc270f2ecc7fd047a3b075"
        );
        Self { root }
    }

    /// Return the original immutable captured manifest bytes.
    pub fn raw() -> &'static [u8] {
        include_bytes!("../data/neural-selected-original.run.json")
    }

    /// Decode the original recorded declaration for a deliberate public-input contradiction.
    pub fn value(&self) -> Value {
        serde_json::from_slice(Self::raw()).expect("original recorded JSON")
    }

    /// Preserve one entire control input in its owned allocation.
    pub fn write(&self, name: &str, raw: &[u8]) -> PathBuf {
        let path = self.root.join(name);
        std::fs::write(&path, raw).expect("whole original control bytes");
        path
    }

    /// Return the owned directory for command output integrity checks.
    pub fn root(&self) -> &Path {
        &self.root
    }
}

impl Drop for Declaration {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root).expect("remove only this test's owned allocation");
    }
}
