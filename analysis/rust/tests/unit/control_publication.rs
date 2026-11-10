// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — control_publication, crate-internal controls

//! The one publication fault the command parity runs cannot produce.
//!
//! A staged file is created in a new private directory the same publication has
//! just made, so no condition a caller controls makes that open fail
//! deterministically; only a concurrent removal or exhausted resources would.
//! This test therefore calls the production writer directly, on a real path
//! whose open fails in the kernel, and requires Python's text, which names the
//! path. Every other publication fault (unwritable parent, file-size limit,
//! failed directory creation and renames) is held through the command against
//! Python in `tests/test_control_command_parity.py`. Review when the kernel
//! tracer used there can target a file inside an unpredictable directory.

use super::write_file;
use std::path::Path;

#[test]
fn a_file_that_cannot_be_opened_is_named_in_the_refusal() {
    let path = Path::new("/proc/self/absent-directory/report.json");
    assert_eq!(
        write_file(path, b"{}"),
        Err(format!(
            "[Errno 2] No such file or directory: '{}'",
            path.display()
        ))
    );
}
