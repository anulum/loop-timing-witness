// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — whole-report publication without replacement

//! Publish whole reports into new directories and refuse every unsafe destination.
//!
//! Kernel failures are real: a file-size limit stops staging, and an injected
//! rename error stops publication, each in an owned child process.

use rustix::process::{Resource, Rlimit, getrlimit, setrlimit};
use serde_json::{Value, json};
use std::ffi::OsStr;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use witness_analysis::write_neural_report;

const CHILD: &str = "WITNESS_PUBLICATION_CHILD";

/// An exclusive owned directory removed with its contents.
struct Owned {
    root: PathBuf,
}

impl Owned {
    fn create() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("current clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "witness-publication-{}-{now}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).expect("exclusive owned allocation");
        Self { root }
    }

    /// Return the sorted entry names, to show that nothing was left behind.
    fn entries(&self) -> Vec<String> {
        let mut names: Vec<_> = std::fs::read_dir(&self.root)
            .expect("owned directory")
            .map(|entry| {
                entry
                    .expect("entry")
                    .file_name()
                    .to_string_lossy()
                    .into_owned()
            })
            .collect();
        names.sort();
        names
    }
}

impl Drop for Owned {
    fn drop(&mut self) {
        let _ = std::fs::set_permissions(&self.root, std::fs::Permissions::from_mode(0o700));
        std::fs::remove_dir_all(&self.root).expect("remove only this test's owned allocation");
    }
}

/// The report every case publishes.
fn report() -> Value {
    json!({"verification": {"whole": true}, "findings": ["one"]})
}

/// Run one test of this binary in a child process with its own owned directory.
fn child(name: &str, root: &Path, wrapper: &[&str]) -> std::process::Output {
    let executable = std::env::current_exe().expect("current test executable");
    let mut arguments: Vec<&OsStr> = wrapper.iter().map(OsStr::new).collect();
    arguments.push(executable.as_os_str());
    arguments.extend(["--exact", name, "--test-threads=1"].map(OsStr::new));
    let output = Command::new("timeout")
        .args(["--signal=TERM", "--kill-after=1s", "20s"])
        .args(arguments)
        .env(CHILD, root)
        .current_dir(root)
        .output()
        .expect("owned child test process");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    output
}

/// Return the owned directory selected for this process when it is a child.
fn selected() -> Option<PathBuf> {
    std::env::var_os(CHILD).map(PathBuf::from)
}

#[test]
fn a_complete_report_is_published_whole_and_alone() {
    let owned = Owned::create();
    let target = owned.root.join("report");
    assert_eq!(write_neural_report(&target, &report()), Ok(()));
    let mut expected = serde_json::to_vec_pretty(&report()).expect("JSON");
    expected.push(b'\n');
    assert_eq!(
        std::fs::read(target.join("report.json")).expect("report"),
        expected
    );
    assert_eq!(owned.entries(), ["report"]);
}

#[test]
fn unsafe_destinations_are_refused_before_staging() {
    let owned = Owned::create();
    std::fs::create_dir(owned.root.join("existing")).expect("existing directory");
    std::os::unix::fs::symlink("absent", owned.root.join("dangling")).expect("dangling link");
    std::fs::write(owned.root.join("file"), b"").expect("regular file");
    let invalid = OsStr::from_bytes(b"\xff");
    for (destination, message) in [
        (PathBuf::from(".."), "Invalid neural report destination."),
        (
            owned.root.join("absent/report"),
            "Neural report parent directory is unavailable.",
        ),
        (
            owned.root.join("existing"),
            "Neural report output directory already exists.",
        ),
        (
            owned.root.join("dangling"),
            "Neural report output directory already exists.",
        ),
        (
            owned.root.join("file/report"),
            "Cannot inspect neural report destination.",
        ),
        (
            owned.root.join(invalid),
            "Invalid neural report destination.",
        ),
    ] {
        assert_eq!(
            write_neural_report(&destination, &report()),
            Err(message.into()),
            "{destination:?}"
        );
    }
    let oversized = json!("x".repeat(8 * 1024 * 1024));
    assert_eq!(
        write_neural_report(&owned.root.join("large"), &oversized),
        Err("Complete neural report exceeds its byte allocation.".into())
    );
    assert_eq!(owned.entries(), ["dangling", "existing", "file"]);
}

#[test]
fn an_unwritable_parent_refuses_staging() {
    let owned = Owned::create();
    std::fs::set_permissions(&owned.root, std::fs::Permissions::from_mode(0o500))
        .expect("read-only parent");
    assert_eq!(
        write_neural_report(&owned.root.join("report"), &report()),
        Err("Cannot create an exclusive consumer temporary directory.".into())
    );
}

#[test]
fn a_relative_destination_is_published_in_the_working_directory() {
    if let Some(root) = selected() {
        assert_eq!(write_neural_report(Path::new("report"), &report()), Ok(()));
        assert!(root.join("report/report.json").is_file());
        return;
    }
    let owned = Owned::create();
    child(
        "a_relative_destination_is_published_in_the_working_directory",
        &owned.root,
        &[],
    );
    assert_eq!(owned.entries(), ["report"]);
}

#[test]
fn a_file_size_limit_refuses_staging_and_leaves_nothing() {
    if let Some(root) = selected() {
        let limit = getrlimit(Resource::Fsize);
        setrlimit(
            Resource::Fsize,
            Rlimit {
                current: Some(16),
                maximum: limit.maximum,
            },
        )
        .expect("lower the file-size limit of this child");
        let result = write_neural_report(&root.join("report"), &report());
        setrlimit(Resource::Fsize, limit).expect("restore the file-size limit");
        assert_eq!(
            result,
            Err("Cannot stage the complete neural report.".into())
        );
        return;
    }
    let owned = Owned::create();
    // An ignored SIGXFSZ survives exec, so the write fails with EFBIG instead.
    child(
        "a_file_size_limit_refuses_staging_and_leaves_nothing",
        &owned.root,
        &["sh", "-c", "trap '' XFSZ; exec \"$@\"", "sh"],
    );
    assert!(owned.entries().is_empty());
}

#[test]
fn a_failed_rename_refuses_publication_and_leaves_nothing() {
    if let Some(root) = selected() {
        assert_eq!(
            write_neural_report(&root.join("report"), &report()),
            Err("Cannot publish the complete neural report without replacement.".into())
        );
        return;
    }
    let owned = Owned::create();
    let trace = owned.root.join("rename.trace");
    let output = child(
        "a_failed_rename_refuses_publication_and_leaves_nothing",
        &owned.root,
        &[
            "strace",
            "-f",
            "-e",
            "trace=renameat2",
            "-e",
            "inject=renameat2:error=EIO",
            "-o",
            trace.to_str().expect("UTF-8 owned path"),
        ],
    );
    assert!(output.status.success());
    let recorded = std::fs::read_to_string(&trace).expect("rename trace");
    assert!(
        recorded.contains("EIO") && recorded.contains("INJECTED"),
        "{recorded}"
    );
    assert_eq!(owned.entries(), ["rename.trace"]);
}
