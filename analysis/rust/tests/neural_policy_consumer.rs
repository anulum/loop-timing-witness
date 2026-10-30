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
use witness_analysis::{
    ImageExecutor, NeuralEntry, NeuralRegistry, load_neural_run, load_neural_run_with_registry,
    neural_key,
};

const MANIFEST: &[u8] = include_bytes!("data/neural-selected-original.run.json");
const SOURCE: &[u8] = include_bytes!("../public-data/neural-selected-source-contract.json");
const CHECKER: &[u8] = include_bytes!("../public-data/neural-selected-checker-policy.json");
const RUNTIME: &[u8] = include_bytes!("../public-data/neural-selected-checker-runtime.json");
const SOURCE_SHA256: &str = "ec1236a69fc9e16a4eff1dfa7bdad8aa8b6088fc4ebceb8d8c43d33517199304";
/// Closed executor binding naming only absent host files; verification refuses it later.
const BINDING: &str = r#"{"schema_id":"loop-timing-witness.sc-checker-image-executor.v1","supplier":{},"historical_contracts":{},"command":["/absent/launcher","{image_root}","{work_directory}","{operation}"],"bootstrap_environment":{},"deadline_seconds":45,"host_boundary":{"system":"Linux","machine":"x86_64","kernel_release":"absent","uid":0,"gid":0,"files":[],"absent_paths":[]},"image":{"files":[],"directories":[],"symlinks":[]},"source_files":["absent.py"],"worker_files":["absent-worker.py"]}"#;

/// Register the reviewed policy bodies with an executor that needs no host files.
fn registry() -> NeuralRegistry {
    let mut registry = NeuralRegistry::new();
    registry.insert(
        neural_key(SOURCE_SHA256.to_owned()),
        Box::new(|| {
            let executor = ImageExecutor::new(
                PathBuf::from("/absent/image"),
                BINDING.as_bytes(),
                RUNTIME.to_vec(),
            )?;
            Ok(NeuralEntry::image(
                SOURCE.to_vec(),
                CHECKER.to_vec(),
                executor,
            ))
        }),
    );
    registry
}

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
        let registry = registry();
        let baseline = load_neural_run_with_registry(&manifest, &registry)
            .err()
            .expect("remaining whole acquisition is deliberately absent");
        assert_ne!(baseline, cases[0].2);
        assert_ne!(baseline, cases[1].2);
        let mut changed = original.to_vec();
        changed[0] ^= 1;
        std::fs::write(prefix.root.join(name), changed)
            .expect("actual same-length source-policy replacement");
        assert_eq!(
            load_neural_run_with_registry(&manifest, &registry).err(),
            Some(expected.to_owned())
        );
    }
}

#[test]
fn missing_acquired_policy_file_is_named_without_a_panic() {
    let prefix = OriginalPolicyPrefix::create();
    std::fs::remove_file(prefix.root.join("source-contract.json"))
        .expect("remove the acquired source policy");
    let refusal = load_neural_run_with_registry(&prefix.root.join("run.json"), &registry())
        .err()
        .expect("missing original acquisition files must refuse");
    assert!(refusal.contains("source-contract.json"), "{refusal}");
    assert!(!refusal.contains("panic"), "{refusal}");
}

#[test]
fn packaged_registry_builds_its_entry_before_reading_the_acquired_policy() {
    let prefix = OriginalPolicyPrefix::create();
    let manifest = prefix.root.join("run.json");
    let mut changed = SOURCE.to_vec();
    changed[0] ^= 1;
    std::fs::write(prefix.root.join("source-contract.json"), changed)
        .expect("actual same-length source-policy replacement");
    assert_eq!(
        load_neural_run(&manifest).err(),
        Some(
            "No reviewed checker installation descriptor is selected for this neural registration."
                .to_owned()
        )
    );
}

#[test]
fn a_registered_policy_must_match_its_admission_identity() {
    let prefix = OriginalPolicyPrefix::create();
    let mut registry = NeuralRegistry::new();
    registry.insert(
        neural_key(SOURCE_SHA256.to_owned()),
        Box::new(|| {
            let executor = ImageExecutor::new(
                PathBuf::from("/absent/image"),
                BINDING.as_bytes(),
                RUNTIME.to_vec(),
            )?;
            Ok(NeuralEntry::image(
                CHECKER.to_vec(),
                CHECKER.to_vec(),
                executor,
            ))
        }),
    );
    assert_eq!(
        load_neural_run_with_registry(&prefix.root.join("run.json"), &registry).err(),
        Some("Selected neural source registration differs from its reviewed identity.".to_owned())
    );
    assert_eq!(
        load_neural_run_with_registry(&prefix.root.join("run.json"), &NeuralRegistry::new()).err(),
        Some("No reviewed source contract is admitted for this neural run.".to_owned())
    );
}
