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

use rustix::process::{Resource, Rlimit, getrlimit, setrlimit};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use witness_analysis::public_runtime::{Installation, InstalledFile};

const CHILD: &str = "WITNESS_EMBEDDED_WORKER_CHILD";
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
        installed(&self.descriptor, &self.tools)
    }

    /// Construct with owned copies of the given worker bodies.
    fn embed(&self, descriptor: &Value, workers: &[(&str, &[u8])]) -> Result<Installation, String> {
        Installation::with_embedded_workers(
            serde_json::to_vec(descriptor).expect("complete caller descriptor"),
            self.files(),
            vec![self.workers.clone()],
            workers,
        )
    }

    /// Record what a child process needs to construct the same installation.
    fn request(&self) -> PathBuf {
        let path = self.root.join("request.json");
        let request = json!({
            "descriptor": self.descriptor,
            "tools": self.tools,
            "workers": self.workers,
        });
        std::fs::write(&path, serde_json::to_vec(&request).expect("JSON")).expect("request");
        path
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

/// Bind the descriptor's tool references to the actual tool paths.
fn installed(descriptor: &Value, tools: &[PathBuf]) -> Vec<InstalledFile> {
    descriptor["files"]
        .as_array()
        .expect("actual tool references")
        .iter()
        .zip(tools)
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

/// Worker roles and bodies as a packaged selection embeds them.
fn embedded() -> Vec<(String, &'static [u8])> {
    WORKERS
        .iter()
        .map(|(name, raw)| (format!("loop_timing_witness/{name}"), *raw))
        .collect()
}

/// Borrow embedded worker roles for the constructor.
fn borrowed<'a>(workers: &'a [(String, &'static [u8])]) -> Vec<(&'a str, &'static [u8])> {
    workers
        .iter()
        .map(|(name, raw)| (name.as_str(), *raw))
        .collect()
}

/// Construct from a parent's request inside a child process.
fn embed_requested(path: &Path) -> Result<Installation, String> {
    let request: Value =
        serde_json::from_slice(&std::fs::read(path).expect("request")).expect("request JSON");
    let tools: Vec<PathBuf> = serde_json::from_value(request["tools"].clone()).expect("tool paths");
    let workers = embedded();
    Installation::with_embedded_workers(
        serde_json::to_vec(&request["descriptor"]).expect("descriptor"),
        installed(&request["descriptor"], &tools),
        vec![PathBuf::from(
            request["workers"].as_str().expect("worker root"),
        )],
        &borrowed(&workers),
    )
}

/// Construct with the external worker root inside a child process.
fn construct_requested(path: &Path) -> Result<Installation, String> {
    let request: Value =
        serde_json::from_slice(&std::fs::read(path).expect("request")).expect("request JSON");
    let tools: Vec<PathBuf> = serde_json::from_value(request["tools"].clone()).expect("tool paths");
    let workers = PathBuf::from(request["workers"].as_str().expect("worker root"));
    Installation::from_selected_contract(
        serde_json::to_vec(&request["descriptor"]).expect("descriptor"),
        installed(&request["descriptor"], &tools),
        vec![workers.clone()],
        workers,
    )
}

/// Run one test of this binary as a child with a request and wrapper.
fn child(name: &str, request: &Path, wrapper: &[&str], temporary: &Path) {
    let executable = std::env::current_exe().expect("current test executable");
    let output = Command::new("timeout")
        .args(["--signal=TERM", "--kill-after=1s", "20s"])
        .args(wrapper)
        .arg(executable)
        .args(["--exact", name, "--test-threads=1"])
        .env(CHILD, request)
        .env("TMPDIR", temporary)
        .output()
        .expect("owned child test process");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
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

#[test]
fn embedded_workers_are_verified_before_an_owned_copy_is_written() {
    let selected = SelectedInstallation::create();
    let workers = embedded();
    let installation = selected
        .embed(&selected.descriptor, &borrowed(&workers))
        .expect("exact embedded worker bodies");
    assert_eq!(installation.verify(), Ok(()));
    let mut unknown = borrowed(&workers);
    unknown[0].0 = "loop_timing_witness/unknown.py";
    let mut changed = borrowed(&workers);
    changed[1].1 = b"changed";
    let mut same_length = borrowed(&workers);
    let mut altered = WORKERS[2].1.to_vec();
    altered[0] ^= 1;
    same_length[2].1 = altered.leak();
    let mut outside = selected.descriptor.clone();
    outside["worker_sources"][0]["path"] = json!("/outside/__init__.py");
    let mut escaping = borrowed(&workers);
    escaping[0].0 = "/outside/__init__.py";
    let mut kernel = selected.descriptor.clone();
    kernel["platform_baseline"]["kernel_release"] = json!("unsupported-kernel");
    for (descriptor, workers, message) in [
        (
            json!({}),
            borrowed(&workers),
            "Invalid original selected embedded-worker descriptor.",
        ),
        (
            selected.descriptor.clone(),
            borrowed(&workers[..2]),
            "Embedded checker worker source population differs.",
        ),
        (
            selected.descriptor.clone(),
            unknown,
            "Embedded checker worker role is not admitted.",
        ),
        (
            outside,
            escaping,
            "Embedded checker worker role is not admitted.",
        ),
        (
            selected.descriptor.clone(),
            changed,
            "Embedded checker worker body differs from its reviewed binding.",
        ),
        (
            selected.descriptor.clone(),
            same_length,
            "Embedded checker worker body differs from its reviewed binding.",
        ),
        (kernel, borrowed(&workers), INVENTORY),
    ] {
        assert_eq!(
            selected.embed(&descriptor, &workers).err().as_deref(),
            Some(message)
        );
    }
}

#[test]
fn an_unavailable_temporary_parent_refuses_the_owned_copy() {
    if let Some(request) = std::env::var_os(CHILD) {
        assert_eq!(
            embed_requested(Path::new(&request)).err().as_deref(),
            Some("Consumer temporary parent is unavailable.")
        );
        return;
    }
    let selected = SelectedInstallation::create();
    child(
        "an_unavailable_temporary_parent_refuses_the_owned_copy",
        &selected.request(),
        &[],
        &selected.root.join("absent"),
    );
}

#[test]
fn an_unwritable_owned_copy_refuses_the_worker_package() {
    if let Some(request) = std::env::var_os(CHILD) {
        assert_eq!(
            embed_requested(Path::new(&request)).err().as_deref(),
            Some("Cannot create the owned checker worker package.")
        );
        return;
    }
    let selected = SelectedInstallation::create();
    let temporary = selected.root.join("temporary");
    std::fs::create_dir(&temporary).expect("owned temporary parent");
    // The owned copy is created without write permission for its owner.
    child(
        "an_unwritable_owned_copy_refuses_the_worker_package",
        &selected.request(),
        &["sh", "-c", "umask 277; exec \"$@\"", "sh"],
        &temporary,
    );
    for entry in std::fs::read_dir(&temporary).expect("owned temporary parent") {
        let path = entry.expect("entry").path();
        std::fs::set_permissions(&path, std::os::unix::fs::PermissionsExt::from_mode(0o700))
            .expect("allow removal of the refused copy");
    }
}

#[test]
fn a_file_size_limit_refuses_the_worker_bytes() {
    if let Some(request) = std::env::var_os(CHILD) {
        let limit = getrlimit(Resource::Fsize);
        setrlimit(
            Resource::Fsize,
            Rlimit {
                current: Some(16),
                maximum: limit.maximum,
            },
        )
        .expect("lower the file-size limit of this child");
        let result = embed_requested(Path::new(&request));
        setrlimit(Resource::Fsize, limit).expect("restore the file-size limit");
        assert_eq!(
            result.err().as_deref(),
            Some("Cannot preserve exact embedded checker worker bytes.")
        );
        return;
    }
    let selected = SelectedInstallation::create();
    let temporary = selected.root.join("temporary");
    std::fs::create_dir(&temporary).expect("owned temporary parent");
    // An ignored SIGXFSZ survives exec, so the write fails with EFBIG instead.
    child(
        "a_file_size_limit_refuses_the_worker_bytes",
        &selected.request(),
        &["sh", "-c", "trap '' XFSZ; exec \"$@\"", "sh"],
        &temporary,
    );
    assert_eq!(std::fs::read_dir(&temporary).expect("parent").count(), 0);
}

#[test]
fn runtime_file_and_kernel_read_failures_are_named_refusals() {
    if let Some(request) = std::env::var_os(CHILD) {
        let expected = std::env::var("WITNESS_EXPECTED_REFUSAL").expect("expected refusal");
        assert_eq!(
            construct_requested(Path::new(&request)).err().as_deref(),
            Some(expected.as_str())
        );
        return;
    }
    let selected = SelectedInstallation::create();
    let request = selected.request();
    let interpreter = selected.tools[0].to_str().expect("UTF-8 interpreter path");
    for (path, syscall, expected) in [
        (
            interpreter,
            "statx",
            "Cannot inspect selected checker runtime file.",
        ),
        (
            interpreter,
            "read",
            "Selected checker runtime file is unavailable.",
        ),
        (
            "/proc/sys/kernel/osrelease",
            "openat",
            "Selected checker kernel baseline is unavailable.",
        ),
    ] {
        let trace = selected.root.join(format!("{syscall}.trace"));
        let output = Command::new("timeout")
            .args([
                "--signal=TERM",
                "--kill-after=1s",
                "20s",
                "strace",
                "-f",
                "-P",
                path,
            ])
            .args(["-e", &format!("trace={syscall}")])
            .args(["-e", &format!("inject={syscall}:error=EIO")])
            .arg("-o")
            .arg(&trace)
            .arg(std::env::current_exe().expect("current test executable"))
            .args([
                "--exact",
                "runtime_file_and_kernel_read_failures_are_named_refusals",
                "--test-threads=1",
            ])
            .env(CHILD, &request)
            .env("WITNESS_EXPECTED_REFUSAL", expected)
            .output()
            .expect("traced child test process");
        assert!(
            output.status.success(),
            "{syscall}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        let recorded = std::fs::read_to_string(&trace).expect("trace");
        assert!(recorded.contains("INJECTED"), "{recorded}");
    }
}
