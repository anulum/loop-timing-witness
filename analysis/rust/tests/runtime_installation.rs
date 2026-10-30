// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public installation construction and revalidation contracts

//! Check actual installation metadata without admitting a source or executing its checker.
//!
//! The two actual tools and three packaged worker bodies exercise construction only.
//! This inventory is not a complete SC execution closure or a trusted source registration.

use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use witness_analysis::public_runtime::{Installation, InstalledFile};

const INVENTORY: &str = "Selected checker runtime inventory or platform baseline differs.";
const ROOTS: &str = "Selected checker runtime import roots are unavailable.";
const WORKERS: &[(&str, &[u8])] = &[
    (
        "__init__.py",
        include_bytes!("../checker_worker/loop_timing_witness/__init__.py"),
    ),
    (
        "neural_checker_worker.py",
        include_bytes!("../checker_worker/loop_timing_witness/neural_checker_worker.py"),
    ),
    (
        "neural_checker_isolation.py",
        include_bytes!("../checker_worker/loop_timing_witness/neural_checker_isolation.py"),
    ),
];

/// Own worker copies while selecting the actual installed Python and tracer read-only.
struct SelectedInstallation {
    root: PathBuf,
    workers: PathBuf,
    tools: Vec<PathBuf>,
    descriptor: Value,
}

impl SelectedInstallation {
    fn create() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let instant = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("current clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "witness-installation-{}-{instant}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let workers = root.join("worker-package");
        std::fs::create_dir(&root).expect("exclusive installation allocation");
        std::fs::create_dir_all(workers.join("loop_timing_witness"))
            .expect("owned actual worker package");
        let python = Command::new("python3")
            .args(["-I", "-S", "-c", "import sys; print(sys.executable)"])
            .output()
            .expect("actual installed Python identity");
        assert!(python.status.success(), "{python:?}");
        assert!(python.stderr.is_empty());
        let interpreter = PathBuf::from(
            String::from_utf8(python.stdout)
                .expect("actual interpreter path")
                .trim(),
        )
        .canonicalize()
        .expect("resolved actual Python executable");
        let search = std::env::var_os("PATH").expect("actual executable search path");
        let tracer = std::env::split_paths(&search)
            .filter_map(|directory| directory.join("strace").canonicalize().ok())
            .find(|path| path.is_file())
            .expect("actual installed process tracer");
        let tools = vec![interpreter, tracer];
        let files: Vec<_> = ["interpreter/python", "tracer/strace"]
            .into_iter()
            .zip(&tools)
            .map(|(name, path)| {
                let raw = std::fs::read(path).expect("complete actual installed tool bytes");
                json!({
                    "path": name,
                    "sha256": format!("{:x}", Sha256::digest(&raw)),
                    "byte_length": raw.len(),
                })
            })
            .collect();
        let worker_sources: Vec<_> = WORKERS
            .iter()
            .map(|(name, raw)| {
                let relative = format!("loop_timing_witness/{name}");
                std::fs::write(workers.join(&relative), raw)
                    .expect("unchanged actual packaged worker bytes");
                json!({
                    "path": relative,
                    "sha256": format!("{:x}", Sha256::digest(raw)),
                    "byte_length": raw.len(),
                })
            })
            .collect();
        let kernel = std::fs::read_to_string("/proc/sys/kernel/osrelease")
            .expect("actual running kernel release");
        let descriptor = json!({
            "schema_id": "loop-timing-witness.sc-checker-runtime.v1",
            "interpreter": files[0],
            "tracer": files[1],
            "import_namespaces": ["imports/0"],
            "worker_sources": worker_sources,
            "files": files,
            "platform_baseline": {
                "id": "public-installation-constructor-metadata-control",
                "system": "Linux",
                "machine": "x86_64",
                "kernel_release": kernel.trim_end(),
            },
            "execution_contract": {
                "profile": "linux-x86_64-seccomp-no-network.v1",
                "address_space_bytes": 805306368,
                "cpu_seconds": 30,
                "wall_seconds": 45,
                "file_bytes": 1048576,
                "python_site_initialisation": false,
                "bytecode_writes": false,
                "bytecode_reads": "owned-empty-prefix",
            },
        });
        Self {
            root,
            workers,
            tools,
            descriptor,
        }
    }

    fn files(&self) -> Vec<InstalledFile> {
        self.descriptor["files"]
            .as_array()
            .expect("actual tool references")
            .iter()
            .zip(&self.tools)
            .map(|(reference, path)| InstalledFile {
                name: reference["path"].as_str().expect("tool role").into(),
                path: path.clone(),
                sha256: reference["sha256"]
                    .as_str()
                    .expect("whole tool hash")
                    .into(),
                byte_length: reference["byte_length"].as_u64().expect("tool length"),
            })
            .collect()
    }

    fn construct(&self, descriptor: &Value) -> Result<Installation, String> {
        Installation::from_selected_contract(
            serde_json::to_vec(descriptor).expect("complete caller descriptor"),
            self.files(),
            vec![self.workers.clone()],
            self.workers.clone(),
        )
    }
}

impl Drop for SelectedInstallation {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root)
            .expect("remove only this test's owned worker package and controls");
    }
}

#[test]
fn actual_installation_reverification_observes_worker_replacement_and_removal() {
    let selected = SelectedInstallation::create();
    let installation = selected
        .construct(&selected.descriptor)
        .expect("actual tool and worker metadata correspondence only");
    assert_eq!(installation.verify(), Ok(()));
    for (name, original) in WORKERS {
        let path = selected.workers.join("loop_timing_witness").join(name);
        let mut altered = original.to_vec();
        altered.push(b'\n');
        std::fs::write(&path, altered).expect("changed actual owned worker file");
        assert_eq!(
            installation.verify(),
            Err("Selected checker runtime file differs from its reviewed binding.".into())
        );
        std::fs::write(&path, original).expect("restore only the owned worker copy");
        assert_eq!(installation.verify(), Ok(()));
        std::fs::remove_file(&path).expect("remove only the owned worker copy");
        assert_eq!(
            installation.verify(),
            Err("Selected checker runtime file is unavailable.".into())
        );
        std::fs::write(path, original).expect("restore only the owned worker copy");
    }
}

#[test]
fn descriptor_inventory_platform_and_worker_population_are_closed() {
    let selected = SelectedInstallation::create();
    selected
        .construct(&selected.descriptor)
        .expect("intact metadata");
    let mut changes = Vec::new();
    for (pointer, replacement) in [
        ("/schema_id", json!("unsupported-runtime")),
        ("/platform_baseline/id", json!("")),
        ("/platform_baseline/system", json!("unsupported-system")),
        ("/platform_baseline/machine", json!("unsupported-machine")),
        (
            "/platform_baseline/kernel_release",
            json!("unsupported-kernel"),
        ),
        ("/import_namespaces", json!(["imports/1"])),
        (
            "/worker_sources/0/path",
            json!("loop_timing_witness/unknown.py"),
        ),
        ("/worker_sources/0/sha256", json!("0".repeat(64))),
        ("/files/0/sha256", json!("0".repeat(64))),
    ] {
        let mut altered = selected.descriptor.clone();
        *altered
            .pointer_mut(pointer)
            .expect("original declared field") = replacement;
        let expected = if pointer == "/worker_sources/0/sha256" {
            "Selected checker runtime file differs from its reviewed binding."
        } else {
            INVENTORY
        };
        changes.push((altered, expected));
    }
    for field in ["files", "worker_sources"] {
        let mut missing = selected.descriptor.clone();
        missing[field]
            .as_array_mut()
            .expect("original inventory")
            .pop();
        changes.push((missing, INVENTORY));
        let mut duplicate = selected.descriptor.clone();
        let first = duplicate[field][0].clone();
        duplicate[field]
            .as_array_mut()
            .expect("original inventory")
            .push(first);
        changes.push((duplicate, INVENTORY));
    }
    for (altered, expected) in changes {
        assert_eq!(
            selected.construct(&altered).err().as_deref(),
            Some(expected)
        );
    }
}

#[test]
fn inventory_bounds_refuse_before_unavailable_files_are_opened() {
    let selected = SelectedInstallation::create();
    for count in [0, 4097] {
        let mut descriptor = selected.descriptor.clone();
        let mut references = Vec::new();
        let mut files = Vec::new();
        for index in 0..count {
            let mut reference = selected.descriptor["files"][index % 2].clone();
            let name = format!("runtime/entry-{index}");
            reference["path"] = json!(name);
            files.push(InstalledFile {
                name,
                path: selected.root.join(format!("absent-{index}")),
                sha256: reference["sha256"]
                    .as_str()
                    .expect("actual tool hash")
                    .into(),
                byte_length: reference["byte_length"]
                    .as_u64()
                    .expect("actual tool length"),
            });
            references.push(reference);
        }
        if count != 0 {
            descriptor["interpreter"] = references[0].clone();
            descriptor["tracer"] = references[1].clone();
        }
        descriptor["files"] = json!(references);
        assert_eq!(
            Installation::from_selected_contract(
                serde_json::to_vec(&descriptor).expect("complete out-of-range declaration"),
                files,
                vec![selected.workers.clone()],
                selected.workers.clone(),
            )
            .err()
            .as_deref(),
            Some(INVENTORY)
        );
    }
}

#[test]
fn execution_contract_and_descriptor_types_refuse_unreviewed_choices() {
    let selected = SelectedInstallation::create();
    for (field, replacement) in [
        ("profile", json!("unsupported-profile")),
        ("address_space_bytes", json!(805306369)),
        ("cpu_seconds", json!(31)),
        ("wall_seconds", json!(46)),
        ("file_bytes", json!(1048577)),
        ("python_site_initialisation", json!(true)),
        ("bytecode_writes", json!(true)),
        ("bytecode_reads", json!("unreviewed-cache")),
    ] {
        let mut altered = selected.descriptor.clone();
        altered["execution_contract"][field] = replacement;
        assert_eq!(
            selected.construct(&altered).err().as_deref(),
            Some(INVENTORY)
        );
    }
    for pointer in [
        "",
        "/platform_baseline",
        "/execution_contract",
        "/worker_sources/0",
    ] {
        let mut altered = selected.descriptor.clone();
        altered.pointer_mut(pointer).expect("original object")["unknown"] = json!(true);
        assert_eq!(
            selected.construct(&altered).err().as_deref(),
            Some("Invalid original selected checker runtime descriptor.")
        );
    }
    for replacement in [json!(true), json!(-1), json!(1.0)] {
        let mut altered = selected.descriptor.clone();
        altered["execution_contract"]["cpu_seconds"] = replacement;
        assert_eq!(
            selected.construct(&altered).err().as_deref(),
            Some("Invalid original selected checker runtime descriptor.")
        );
    }
}

#[test]
fn executable_membership_and_worker_runtime_aliases_are_distinct_refusals() {
    let selected = SelectedInstallation::create();
    for role in ["interpreter", "tracer"] {
        let mut missing = selected.descriptor.clone();
        missing[role]["path"] = json!("unlisted-executable");
        assert_eq!(
            selected.construct(&missing).err().as_deref(),
            Some("Selected checker runtime omits an executable role.")
        );
    }
    for alias in ["name", "path", "both"] {
        let mut descriptor = selected.descriptor.clone();
        let mut reference = descriptor["worker_sources"][1].clone();
        if alias == "path" {
            reference["path"] = json!("runtime/worker-source");
        }
        let actual_worker = selected
            .workers
            .join("loop_timing_witness/neural_checker_worker.py");
        let path = if alias == "name" {
            let copy = selected.root.join("runtime-worker-copy.py");
            std::fs::write(&copy, WORKERS[1].1).expect("exact owned distinct worker copy");
            copy
        } else {
            actual_worker
        };
        let mut files = selected.files();
        files.push(InstalledFile {
            name: reference["path"]
                .as_str()
                .expect("alias control role")
                .into(),
            path,
            sha256: reference["sha256"]
                .as_str()
                .expect("actual worker hash")
                .into(),
            byte_length: reference["byte_length"]
                .as_u64()
                .expect("actual worker length"),
        });
        descriptor["files"]
            .as_array_mut()
            .expect("tool inventory")
            .push(reference);
        assert_eq!(
            Installation::from_selected_contract(
                serde_json::to_vec(&descriptor).expect("complete alias declaration"),
                files,
                vec![selected.workers.clone()],
                selected.workers.clone(),
            )
            .err()
            .as_deref(),
            Some("Selected checker worker/runtime roles contain an alias.")
        );
    }
    for duplicate in ["name", "path"] {
        let mut files = selected.files();
        if duplicate == "name" {
            files[1].name = files[0].name.clone();
        } else {
            files[1].path = files[0].path.clone();
        }
        assert_eq!(
            Installation::from_selected_contract(
                serde_json::to_vec(&selected.descriptor).expect("original descriptor"),
                files,
                vec![selected.workers.clone()],
                selected.workers.clone(),
            )
            .err()
            .as_deref(),
            Some(INVENTORY)
        );
    }
}

#[test]
fn installation_import_and_worker_roots_must_be_actual_resolved_directories() {
    let selected = SelectedInstallation::create();
    let missing = selected.root.join("absent");
    let file = selected.root.join("regular-file");
    std::fs::write(&file, WORKERS[1].1).expect("actual file in place of an import directory");
    let linked = selected.root.join("linked-workers");
    std::os::unix::fs::symlink(&selected.workers, &linked).expect("actual final directory symlink");
    for root in [missing, file, linked] {
        for worker_root in [false, true] {
            let imports = if worker_root {
                &selected.workers
            } else {
                &root
            };
            let workers = if worker_root {
                &root
            } else {
                &selected.workers
            };
            assert_eq!(
                Installation::from_selected_contract(
                    serde_json::to_vec(&selected.descriptor).expect("original descriptor"),
                    selected.files(),
                    vec![imports.clone()],
                    workers.clone(),
                )
                .err()
                .as_deref(),
                Some(ROOTS)
            );
        }
    }
    assert_eq!(
        Installation::from_selected_contract(
            serde_json::to_vec(&selected.descriptor).expect("original descriptor"),
            selected.files(),
            Vec::new(),
            selected.workers.clone(),
        )
        .err()
        .as_deref(),
        Some(INVENTORY)
    );
}
