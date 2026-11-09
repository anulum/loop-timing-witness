// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — control_publication, crate-internal controls

//! Edge cases of `control_publication` that the command parity runs do not reach.

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
