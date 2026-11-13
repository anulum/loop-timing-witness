// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — corpus bytes and owned folders of the crate tests

//! Decode the hexadecimal bytes the shared corpora hold, and own a folder
//! for corpus file trees.

use std::path::PathBuf;

/// Decode a hexadecimal byte string of a corpus.
pub(crate) fn hex_bytes(text: &str) -> Vec<u8> {
    (0..text.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&text[index..index + 2], 16).expect("hex"))
        .collect()
}

/// A new folder under the temporary directory, held by its resolved path
/// and removed when dropped.
pub(crate) struct Scratch(pub(crate) PathBuf);

impl Scratch {
    /// Create a new empty folder whose name carries `label`, the process and the clock.
    pub(crate) fn new(label: &str) -> Self {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let name = format!("witness-{label}-{}-{nanos}", std::process::id());
        let path = std::env::temp_dir().join(name);
        std::fs::create_dir(&path).expect("scratch");
        Self(std::fs::canonicalize(&path).expect("resolved scratch"))
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).ok();
    }
}
