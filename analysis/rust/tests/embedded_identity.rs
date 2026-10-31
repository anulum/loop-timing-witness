// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — embedded assets and operator selections of the installed command

//! Change one embedded byte or one reviewed pin in a copy of the installed command.
//!
//! The real operator descriptors name host files and are never packaged. A
//! copy of the command whose pin names a test descriptor reaches the code an
//! operator review reaches, as the Python package-copy tests do; a copy with
//! one changed data byte proves that each embedded asset is checked.

mod support;

use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use support::Declaration;

const INSTALLATION_PIN: &str = "7e0e98ba8c02f8a5cf6d9ae58d9146d2106b1211ae0739f0945f2eeb093a611d";
const IMAGE_PIN: &str = "92727d94d239cab44f1ff966a890a438f5864086e8129b594ad75828c420ae2a";
const INSTALLATION: &str = "LOOP_TIMING_WITNESS_CHECKER_INSTALLATION";
const BINDING: &str = "LOOP_TIMING_WITNESS_CHECKER_IMAGE_BINDING";
const IMAGE: &str = "LOOP_TIMING_WITNESS_CHECKER_IMAGE";
const NO_INSTALLATION: &str =
    "No reviewed checker installation descriptor is selected for this neural registration.";
const NO_BINDING: &str =
    "No immutable checker image binding is selected for this neural registration.";
const RUNTIME_PIN: &str = "7f37448dcd18d9c2b41b2f1966154a5cff9f96081195a79b6dd5a5c8596b4890";
const RUNTIME: &[u8] = include_bytes!("../public-data/neural-selected-checker-runtime.json");
const POLICY: &[u8] = include_bytes!("../public-data/neural-selected-checker-policy.json");
const INITIALISER: &[u8] = include_bytes!("../checker_worker/loop_timing_witness/__init__.py");
const UNAVAILABLE: &str = "Selected neural profile installation asset is unavailable.";

/// Return the lowercase SHA-256 of whole bytes.
fn sha(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

/// Write a copy of the installed command with one unique byte range replaced.
fn patched(fixture: &Declaration, name: &str, old: &[u8], new: &[u8]) -> PathBuf {
    patched_all(fixture, name, &[(old, new)])
}

/// Write a copy of the installed command with unique byte ranges replaced in order.
///
/// Occurrences inside the embedded checker policy, which cites the runtime
/// digest, are not candidates; the replaced range must be unique elsewhere.
fn patched_all(fixture: &Declaration, name: &str, changes: &[(&[u8], &[u8])]) -> PathBuf {
    let mut image = std::fs::read(env!("CARGO_BIN_EXE_loop-timing-witness-analyze-native"))
        .expect("installed command");
    let policy = image
        .windows(POLICY.len())
        .position(|window| window == POLICY)
        .expect("embedded checker policy");
    for (old, new) in changes {
        assert_eq!(old.len(), new.len());
        let offsets: Vec<_> = image
            .windows(old.len())
            .enumerate()
            .filter(|(offset, window)| {
                window == old && !(policy..policy + POLICY.len()).contains(offset)
            })
            .map(|(offset, _)| offset)
            .collect();
        assert_eq!(offsets.len(), 1, "{name}: the replaced bytes occur once");
        image[offsets[0]..offsets[0] + old.len()].copy_from_slice(new);
    }
    let path = fixture.write(name, &image);
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700)).expect("executable");
    path
}

/// Replace the final newline of an embedded asset with a space.
fn changed_asset(fixture: &Declaration, name: &str, asset: &[u8]) -> PathBuf {
    assert!(asset.ends_with(b"\n"));
    let mut altered = asset.to_vec();
    *altered.last_mut().expect("nonempty asset") = b' ';
    patched(fixture, name, asset, &altered)
}

/// Write the recorded declaration, selecting the given source contract digest.
fn declaration(fixture: &Declaration, source: Option<String>) -> PathBuf {
    let mut value = fixture.value();
    if let Some(digest) = source {
        value["source_contract_ref"]["sha256"] = json!(digest);
    }
    fixture.write(
        "run.json",
        &serde_json::to_vec(&value).expect("recorded declaration"),
    )
}

/// Run one command copy with exactly the given operator variables; return its stderr.
fn refusal(binary: &Path, manifest: &Path, environment: &[(&str, &Path)]) -> String {
    let output = manifest.with_file_name("report");
    let mut command = Command::new(binary);
    command
        .arg(manifest)
        .arg("--output-dir")
        .arg(&output)
        .env_remove(INSTALLATION)
        .env_remove(BINDING)
        .env_remove(IMAGE);
    for (name, value) in environment {
        command.env(name, value);
    }
    let result = command.output().expect("installed command copy");
    assert_eq!(result.status.code(), Some(1));
    assert!(result.stdout.is_empty());
    assert!(!output.exists());
    let stderr = String::from_utf8(result.stderr).expect("authored UTF-8");
    stderr
        .strip_prefix("run analysis: FAIL: ")
        .and_then(|reason| reason.strip_suffix('\n'))
        .expect("one refusal line")
        .to_owned()
}

/// The digest of the packaged image source contract, which selects the image entry.
fn image_source() -> String {
    sha(include_bytes!(
        "../public-data/neural-image-source-contract.json"
    ))
}

/// Return a closed image executor binding naming only absent host files.
fn image_binding(command: Value) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "schema_id": "loop-timing-witness.sc-checker-image-executor.v1",
        "supplier": {},
        "historical_contracts": {},
        "command": command,
        "bootstrap_environment": {},
        "deadline_seconds": 45,
        "host_boundary": {
            "system": "Linux",
            "machine": "x86_64",
            "kernel_release": "absent",
            "uid": 0,
            "gid": 0,
            "files": [],
            "absent_paths": [],
        },
        "image": {"files": [], "directories": [], "symlinks": []},
        "source_files": ["absent.py"],
        "worker_files": ["absent-worker.py"],
    }))
    .expect("JSON")
}

/// Return a descriptor with the reviewed runtime identities and absent host paths.
fn installation_descriptor() -> Vec<u8> {
    let runtime: Value = serde_json::from_slice(RUNTIME).expect("packaged runtime");
    let bindings: Vec<_> = runtime["files"]
        .as_array()
        .expect("runtime files")
        .iter()
        .enumerate()
        .map(|(index, item)| {
            json!({
                "name": item["path"],
                "actual_path": format!("/absent/runtime/{index}"),
                "sha256": item["sha256"],
                "byte_length": item["byte_length"],
            })
        })
        .collect();
    let roots: Vec<_> = (0..runtime["import_namespaces"]
        .as_array()
        .expect("namespaces")
        .len())
        .map(|index| format!("/absent/imports/{index}"))
        .collect();
    serde_json::to_vec(&json!({"bindings": bindings, "import_roots": roots})).expect("JSON")
}

#[test]
fn each_embedded_asset_is_checked_before_use() {
    let fixture = Declaration::recorded();
    let selected = declaration(&fixture, None);
    let schema = changed_asset(
        &fixture,
        "schema-changed",
        include_bytes!("../neural-step-run.schema.json"),
    );
    assert_eq!(
        refusal(&schema, &selected, &[]),
        "Installed neural manifest schema differs from its admitted body."
    );
    let runtime = changed_asset(&fixture, "runtime-changed", RUNTIME);
    assert_eq!(
        refusal(&runtime, &selected, &[]),
        "Selected checker installation descriptor differs from its reviewed binding."
    );
    let image = changed_asset(
        &fixture,
        "image-runtime-changed",
        include_bytes!("../public-data/neural-image-checker-runtime.json"),
    );
    assert_eq!(
        refusal(&image, &declaration(&fixture, Some(image_source())), &[]),
        "Selected checker image descriptor differs from its reviewed binding."
    );
}

#[test]
fn operator_selections_must_be_absolute_regular_reviewed_files() {
    let fixture = Declaration::recorded();
    let manifest = declaration(&fixture, None);
    let binary = Path::new(env!("CARGO_BIN_EXE_loop-timing-witness-analyze-native"));
    let other = fixture.write("other.json", b"{}");
    let link = fixture.root().join("link.json");
    std::os::unix::fs::symlink(&other, &link).expect("final symlink");
    let large = fixture.write("large.json", &vec![b' '; 262_145]);
    for (value, message) in [
        (Path::new(""), NO_INSTALLATION),
        (Path::new("relative.json"), NO_INSTALLATION),
        (&fixture.root().join("absent.json"), UNAVAILABLE),
        (&link, UNAVAILABLE),
        (
            Path::new("/"),
            "Selected neural profile asset must be a regular file.",
        ),
        (
            &other,
            "Selected neural profile asset differs from its reviewed binding.",
        ),
        (
            &large,
            "Selected neural profile asset differs from its reviewed binding.",
        ),
    ] {
        assert_eq!(
            refusal(binary, &manifest, &[(INSTALLATION, value)]),
            message,
            "{value:?}"
        );
    }
    assert_eq!(refusal(binary, &manifest, &[]), NO_INSTALLATION);
    let image = declaration(&fixture, Some(image_source()));
    assert_eq!(refusal(binary, &image, &[]), NO_BINDING);
}

#[test]
fn a_reviewed_installation_descriptor_reaches_installation_verification() {
    let fixture = Declaration::recorded();
    let manifest = declaration(&fixture, None);
    let descriptor = installation_descriptor();
    let selected = fixture.write("installation.json", &descriptor);
    let binary = patched(
        &fixture,
        "installation-reviewed",
        INSTALLATION_PIN.as_bytes(),
        sha(&descriptor).as_bytes(),
    );
    assert_eq!(
        refusal(&binary, &manifest, &[(INSTALLATION, &selected)]),
        "Selected checker worker or installation differs from its reviewed runtime."
    );
    // A runtime that binds the current initialiser reaches installation verification.
    let reviewed = format!(
        "\"byte_length\": 2181,\n      \"path\": \"loop_timing_witness/__init__.py\",\n      \"sha256\": \"{}\"",
        "6d6ff4fdd628f6f3f21c495b37dbfcb92d00b1404a8bf2610c0427bfd3bab5f2"
    );
    let current = format!(
        "\"byte_length\": {},\n      \"path\": \"loop_timing_witness/__init__.py\",\n      \"sha256\": \"{}\"",
        INITIALISER.len(),
        sha(INITIALISER)
    );
    let source = String::from_utf8(RUNTIME.to_vec()).expect("UTF-8 runtime");
    assert_eq!(source.matches(&reviewed).count(), 1);
    let runtime = source.replace(&reviewed, &current).into_bytes();
    let binary = patched_all(
        &fixture,
        "installation-current-worker",
        &[
            (RUNTIME, &runtime),
            (RUNTIME_PIN.as_bytes(), sha(&runtime).as_bytes()),
            (INSTALLATION_PIN.as_bytes(), sha(&descriptor).as_bytes()),
        ],
    );
    let platform: Value = serde_json::from_slice(RUNTIME).expect("packaged runtime");
    let kernel = std::fs::read_to_string("/proc/sys/kernel/osrelease").expect("kernel");
    // The reviewed runtime names one host kernel; elsewhere the platform is refused first.
    let expected = if platform["platform_baseline"]["kernel_release"] == kernel.trim_end() {
        "Selected checker runtime file is unavailable."
    } else {
        "Selected checker runtime inventory or platform baseline differs."
    };
    assert_eq!(
        refusal(&binary, &manifest, &[(INSTALLATION, &selected)]),
        expected
    );
    let malformed = fixture.write("malformed.json", b"{}");
    let binary = patched(
        &fixture,
        "installation-malformed",
        INSTALLATION_PIN.as_bytes(),
        sha(b"{}").as_bytes(),
    );
    assert_eq!(
        refusal(&binary, &manifest, &[(INSTALLATION, &malformed)]),
        "Invalid original selected consumer installation."
    );
}

#[test]
fn a_reviewed_image_binding_requires_its_image_then_its_closed_form() {
    let fixture = Declaration::recorded();
    let manifest = declaration(&fixture, Some(image_source()));
    let valid = image_binding(json!([
        "/absent/launcher",
        "{image_root}",
        "{work_directory}",
        "{operation}"
    ]));
    let binding = fixture.write("binding.json", &valid);
    let binary = patched(
        &fixture,
        "image-reviewed",
        IMAGE_PIN.as_bytes(),
        sha(&valid).as_bytes(),
    );
    let root = fixture.root().join("image");
    let no_image = "No immutable checker image is selected for this neural registration.";
    assert_eq!(
        refusal(&binary, &manifest, &[(BINDING, &binding)]),
        no_image
    );
    assert_eq!(
        refusal(
            &binary,
            &manifest,
            &[(BINDING, &binding), (IMAGE, Path::new("image"))]
        ),
        no_image
    );
    assert_eq!(
        refusal(&binary, &manifest, &[(BINDING, &binding), (IMAGE, &root)]),
        "Cannot open original file without symlinks: source-contract.json."
    );
    let open = image_binding(json!([]));
    let unreviewed = fixture.write("open.json", &open);
    let binary = patched(
        &fixture,
        "image-open",
        IMAGE_PIN.as_bytes(),
        sha(&open).as_bytes(),
    );
    assert_eq!(
        refusal(
            &binary,
            &manifest,
            &[(BINDING, &unreviewed), (IMAGE, &root)]
        ),
        "Checker image executor binding is not its closed reviewed form."
    );
}

/// Run the installed command under a tracer that fails one syscall on one path.
fn injected(manifest: &Path, selected: &Path, syscalls: &str) -> String {
    let trace = manifest.with_file_name(format!("{syscalls}.trace"));
    let output = manifest.with_file_name("report");
    let result = Command::new("strace")
        .args(["-f", "-P"])
        .arg(selected)
        .args(["-e", &format!("trace={syscalls}")])
        .args(["-e", &format!("inject={syscalls}:error=EIO")])
        .arg("-o")
        .arg(&trace)
        .arg(env!("CARGO_BIN_EXE_loop-timing-witness-analyze-native"))
        .arg(manifest)
        .arg("--output-dir")
        .arg(&output)
        .env(INSTALLATION, selected)
        .output()
        .expect("traced installed command");
    assert_eq!(result.status.code(), Some(1));
    let recorded = std::fs::read_to_string(&trace).expect("trace");
    assert!(recorded.contains("INJECTED"), "{recorded}");
    String::from_utf8(result.stderr).expect("authored UTF-8")
}

#[test]
fn operator_file_metadata_and_read_failures_are_unavailable() {
    let fixture = Declaration::recorded();
    let manifest = declaration(&fixture, None);
    let selected = fixture.write("installation.json", b"{}");
    for syscalls in ["statx", "read"] {
        assert_eq!(
            injected(&manifest, &selected, syscalls),
            format!("run analysis: FAIL: {UNAVAILABLE}\n"),
            "{syscalls}"
        );
    }
}

/// Return a whole-file reference to one actual file.
fn reference(name: &str, path: &Path) -> Value {
    let raw = std::fs::read(path).expect("actual file");
    json!({"path": name, "sha256": sha(&raw), "byte_length": raw.len()})
}

/// Resolve one actual executable on the search path.
fn executable(name: &str) -> PathBuf {
    let search = std::env::var_os("PATH").expect("search path");
    std::env::split_paths(&search)
        .filter_map(|directory| directory.join(name).canonicalize().ok())
        .find(|path| path.is_file())
        .expect("actual installed executable")
}

#[test]
fn a_runtime_binding_the_current_workers_constructs_the_host_installation() {
    let fixture = Declaration::recorded();
    let manifest = declaration(&fixture, None);
    let imports = fixture.root().join("imports");
    std::fs::create_dir(&imports).expect("import root");
    let tools = [
        ("interpreter/python", executable("python3")),
        ("tracer/strace", executable("strace")),
    ];
    let files: Vec<_> = tools
        .iter()
        .map(|(name, path)| reference(name, path))
        .collect();
    let workers = [
        "__init__.py",
        "neural_checker_worker.py",
        "neural_checker_isolation.py",
    ]
    .map(|name| {
        reference(
            &format!("loop_timing_witness/{name}"),
            &Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("checker_worker/loop_timing_witness")
                .join(name),
        )
    });
    let kernel = std::fs::read_to_string("/proc/sys/kernel/osrelease").expect("kernel");
    let mut runtime = serde_json::to_vec(&json!({
        "schema_id": "loop-timing-witness.sc-checker-runtime.v1",
        "interpreter": files[0],
        "tracer": files[1],
        "import_namespaces": ["imports/0"],
        "worker_sources": workers,
        "files": files,
        "platform_baseline": {
            "id": "test-host",
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
    }))
    .expect("JSON");
    // Trailing JSON whitespace keeps the embedded asset length.
    assert!(runtime.len() < RUNTIME.len());
    runtime.resize(RUNTIME.len(), b' ');
    let descriptor = serde_json::to_vec(&json!({
        "bindings": tools.iter().map(|(name, path)| {
            let item = reference(name, path);
            json!({
                "name": name,
                "actual_path": path,
                "sha256": item["sha256"],
                "byte_length": item["byte_length"],
            })
        }).collect::<Vec<_>>(),
        "import_roots": [imports],
    }))
    .expect("JSON");
    let selected = fixture.write("installation.json", &descriptor);
    let binary = patched_all(
        &fixture,
        "installation-host",
        &[
            (RUNTIME, &runtime),
            (RUNTIME_PIN.as_bytes(), sha(&runtime).as_bytes()),
            (INSTALLATION_PIN.as_bytes(), sha(&descriptor).as_bytes()),
        ],
    );
    // The installation is constructed; the absent acquisition files are refused next.
    assert_eq!(
        refusal(&binary, &manifest, &[(INSTALLATION, &selected)]),
        "Cannot open original file without symlinks: source-contract.json."
    );
}
