// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — report assembly, crate-internal controls

//! Report parts that the RTL parity runs do not reach: board artefact digests,
//! repeated source paths and absent declared files. The complete reports are
//! held to Python by `tests/test_control_run_parity.py`.

use super::input_hashes;
use serde_json::json;

#[test]
fn input_digests_follow_python_order_and_board_artefacts() {
    let manifest = json!({
        "files": {"events": {"sha256": "e"}, "tracking": null},
        "measurement_domain": {"sha256": "m"},
        "source": {"files": [{"path": "a", "sha256": "1"}, {"path": "a", "sha256": "2"}]},
        "hardware_artifacts": {
            "bitstream": {"sha256": "b"},
            "firmware": {"sha256": "f"},
            "linux_image": {"sha256": "l"},
            "controller_binary": {"sha256": "c"},
        },
    });
    let hashes = input_hashes(manifest.as_object().expect("object"));
    assert_eq!(
        serde_json::Value::Object(hashes),
        json!({
            "events": "e",
            "measurement_domain": "m",
            "source:a": "2",
            "bitstream": "b",
            "firmware": "f",
            "linux_image": "l",
            "controller_binary": "c",
        })
    );
}
