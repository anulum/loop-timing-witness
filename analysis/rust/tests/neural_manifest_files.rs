// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public manifest descriptor input contracts

//! Verify actual manifest descriptors, kernel failures and a bounded no-writer FIFO.

mod support;

use std::path::Path;
use std::process::Command;
use support::Declaration;
use witness_analysis::load_neural_manifest;

#[test]
fn manifest_file_identity_distinguishes_missing_symlink_directory_and_read_failure() {
    let fixture = Declaration::recorded();
    let path = fixture.write("manifest.json", Declaration::raw());
    assert_eq!(
        load_neural_manifest(&path).expect("actual original declarations"),
        fixture.value()
    );
    let missing = fixture.root().join("absent.json");
    assert_eq!(
        load_neural_manifest(&missing),
        Err("Cannot read neural manifest as a regular file without symlinks.".into())
    );
    let alias = fixture.root().join("alias.json");
    std::os::unix::fs::symlink("manifest.json", &alias).expect("actual manifest symlink");
    assert_eq!(
        load_neural_manifest(&alias),
        Err("Cannot read neural manifest as a regular file without symlinks.".into())
    );
    assert_eq!(
        load_neural_manifest(fixture.root()),
        Err("Neural manifest must be a regular file.".into())
    );
    assert_eq!(
        load_neural_manifest(Path::new("/proc/self/mem")),
        Err("Cannot read neural manifest bytes.".into())
    );
}

#[test]
fn manifest_metadata_failure_is_an_authored_descriptor_refusal() {
    const INPUT_FLAG: &str = "WITNESS_MANIFEST_METADATA_INPUT";
    if let Some(path) = std::env::var_os(INPUT_FLAG) {
        assert_eq!(
            load_neural_manifest(Path::new(&path)),
            Err("Cannot inspect neural manifest descriptor.".into())
        );
        return;
    }
    let fixture = Declaration::recorded();
    let input = fixture.write("manifest.json", Declaration::raw());
    let trace_path = fixture.root().join("metadata.trace");
    let output = Command::new("timeout")
        .args(["--signal=TERM", "--kill-after=1s", "5s", "strace"])
        .args([
            "-f",
            "-yy",
            "-e",
            "trace=statx",
            "-e",
            "inject=statx:error=EIO:when=1",
            "-o",
        ])
        .arg(&trace_path)
        .arg(std::env::current_exe().expect("current public manifest test executable"))
        .args([
            "--exact",
            "manifest_metadata_failure_is_an_authored_descriptor_refusal",
            "--test-threads=1",
        ])
        .env(INPUT_FLAG, &input)
        .output()
        .expect("bounded actual manifest metadata failure");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(output.status.success(), "{stderr}");
    let trace = std::fs::read_to_string(&trace_path).expect("actual descriptor trace");
    let metadata = trace
        .lines()
        .find(|line| line.contains("manifest.json>"))
        .expect("metadata syscall addresses the original manifest");
    assert!(metadata.contains("EIO"));
    assert!(metadata.contains("INJECTED"));
}

#[test]
fn manifest_fifo_without_a_writer_is_refused_without_waiting() {
    const CHILD_FLAG: &str = "WITNESS_MANIFEST_FIFO_CHILD";
    if std::env::var_os(CHILD_FLAG).is_some() {
        let fixture = Declaration::recorded();
        let fifo = fixture.root().join("manifest.fifo");
        assert!(
            Command::new("mkfifo")
                .arg(&fifo)
                .status()
                .expect("actual manifest FIFO")
                .success()
        );
        assert_eq!(
            load_neural_manifest(&fifo),
            Err("Neural manifest must be a regular file.".into())
        );
        return;
    }
    let output = Command::new("timeout")
        .args(["--signal=TERM", "--kill-after=1s", "5s"])
        .arg(std::env::current_exe().expect("current public manifest test executable"))
        .args([
            "--exact",
            "manifest_fifo_without_a_writer_is_refused_without_waiting",
            "--test-threads=1",
        ])
        .env(CHILD_FLAG, "1")
        .output()
        .expect("bounded actual manifest FIFO input");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(output.status.success(), "{stderr}");
}
