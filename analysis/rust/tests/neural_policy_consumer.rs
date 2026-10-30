// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — original policy bodies through the public native loader

//! Bind original policy bodies through the complete public native loader.

use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use witness_analysis::load_neural_run;

const MANIFEST: &[u8] = include_bytes!("data/neural-selected-original.run.json");
const SOURCE: &[u8] = include_bytes!("../public-data/neural-selected-source-contract.json");
const CHECKER: &[u8] = include_bytes!("../public-data/neural-selected-checker-policy.json");

struct OriginalPolicyPrefix {
    root: PathBuf,
}

impl OriginalPolicyPrefix {
    fn create() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let instant = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("current clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "witness-policy-prefix-{}-{instant}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).expect("exclusive policy-prefix allocation");
        std::fs::write(root.join("run.json"), MANIFEST).expect("actual original declaration");
        std::fs::write(root.join("source-contract.json"), SOURCE)
            .expect("actual reviewed source policy");
        std::fs::write(root.join("checker-policy.json"), CHECKER)
            .expect("actual reviewed checker policy");
        Self { root }
    }
}

impl Drop for OriginalPolicyPrefix {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root).expect("remove only this policy-prefix allocation");
    }
}

#[test]
fn original_policy_body_checks_precede_runtime_and_remaining_acquisition_checks() {
    let cases = [
        (
            "source-contract.json",
            SOURCE,
            "Acquired neural source contract differs from its reviewed consumer policy.",
        ),
        (
            "checker-policy.json",
            CHECKER,
            "Acquired checker policy differs from its reviewed consumer binding.",
        ),
    ];
    for (name, original, expected) in cases {
        let prefix = OriginalPolicyPrefix::create();
        let manifest = prefix.root.join("run.json");
        let baseline = load_neural_run(&manifest)
            .err()
            .expect("remaining whole acquisition is deliberately absent");
        assert_ne!(baseline, cases[0].2);
        assert_ne!(baseline, cases[1].2);
        let mut changed = original.to_vec();
        changed[0] ^= 1;
        std::fs::write(prefix.root.join(name), changed)
            .expect("actual same-length source-policy replacement");
        assert_eq!(load_neural_run(&manifest).err(), Some(expected.to_owned()));
    }
}
