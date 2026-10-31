// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — analysis command arguments and statuses

//! Run the analysis command with exact argument vectors and a selected registry.
//!
//! Passing and failing published reports are compared with the Python command
//! by the parity tests, which own complete acquisitions.

mod support;

use std::ffi::OsString;
use std::os::unix::ffi::OsStringExt;
use std::process::Command;
use support::Declaration;
use witness_analysis::{NeuralRegistry, public_command};

const UNREADABLE: &str = "Cannot read neural manifest as a regular file without symlinks.";

/// Run the command against an empty registry; return status, stdout and stderr.
fn command(arguments: &[OsString]) -> (i32, String, String) {
    let (mut stdout, mut stderr) = (Vec::new(), Vec::new());
    let status = public_command::run(arguments, &NeuralRegistry::new(), &mut stdout, &mut stderr);
    (
        status,
        String::from_utf8(stdout).expect("authored UTF-8"),
        String::from_utf8(stderr).expect("authored UTF-8"),
    )
}

/// Convert text arguments.
fn texts(items: &[&str]) -> Vec<OsString> {
    items.iter().map(OsString::from).collect()
}

/// Return the exact argument-error output for one reason.
fn usage_error(reason: &str) -> (i32, String, String) {
    (
        2,
        String::new(),
        format!(
            "{}\nrun analysis: argument error: {reason}\n",
            public_command::USAGE
        ),
    )
}

#[test]
fn help_is_recognised_only_before_the_literal_separator() {
    for help in ["-h", "--help"] {
        assert_eq!(
            command(&texts(&["run.json", help, "--unknown"])),
            (0, format!("{}\n", public_command::USAGE), String::new())
        );
    }
    assert_eq!(
        command(&texts(&["--output-dir", "report", "--", "-h"])),
        (
            1,
            String::new(),
            format!("run analysis: FAIL: {UNREADABLE}\n")
        )
    );
}

#[test]
fn argument_errors_name_their_reason_with_the_usage_line() {
    for (arguments, reason) in [
        (&["run.json"][..], "output directory is required"),
        (&["--output-dir", "report"][..], "manifest is required"),
        (
            &["run.json", "--output-dir"][..],
            "missing output directory",
        ),
        (
            &["run.json", "--output-dir", "a", "--output-dir", "b"][..],
            "output directory was provided more than once",
        ),
        (
            &["run.json", "--output-dir=a", "--output-dir=b"][..],
            "output directory was provided more than once",
        ),
        (
            &["run.json", "--output-dir=a", "--output-dir"][..],
            "output directory was provided more than once",
        ),
        (
            &["run.json", "--verbose"][..],
            "unsupported analysis argument",
        ),
        (&["a.json", "b.json"][..], "expected one manifest"),
        (
            &["--output-dir", "report", "--", "a.json", "b.json"][..],
            "expected one manifest",
        ),
    ] {
        assert_eq!(
            command(&texts(arguments)),
            usage_error(reason),
            "{arguments:?}"
        );
    }
    let dash = OsString::from_vec(b"-\xff".to_vec());
    assert_eq!(
        command(&[OsString::from("run.json"), dash]),
        usage_error("unsupported analysis argument")
    );
}

#[test]
fn inline_and_literal_operands_reach_the_selected_registry() {
    let fixture = Declaration::recorded();
    let path = fixture.write(
        "run.json",
        &serde_json::to_vec(&fixture.value()).expect("recorded declaration"),
    );
    let output = fixture.root().join("report");
    let refusal = (
        1,
        String::new(),
        "run analysis: FAIL: No reviewed source contract is admitted for this neural run.\n"
            .to_owned(),
    );
    let inline = OsString::from(format!("--output-dir={}", output.display()));
    assert_eq!(command(&[path.clone().into(), inline]), refusal);
    let raw = OsString::from_vec(b"\xff.json".to_vec());
    let literal = command(&[
        "--output-dir".into(),
        output.clone().into(),
        "--".into(),
        fixture.root().join(raw).into(),
    ]);
    assert_eq!(literal.0, 1);
    assert_eq!(literal.2, format!("run analysis: FAIL: {UNREADABLE}\n"));
    assert!(!output.exists());
}

#[test]
fn the_installed_command_runs_the_packaged_registry() {
    let binary = env!("CARGO_BIN_EXE_loop-timing-witness-analyze-native");
    let help = Command::new(binary)
        .arg("--help")
        .output()
        .expect("installed command");
    assert_eq!(help.status.code(), Some(0));
    assert_eq!(
        help.stdout,
        format!("{}\n", public_command::USAGE).into_bytes()
    );
    assert!(help.stderr.is_empty());
    let error = Command::new(binary).output().expect("installed command");
    assert_eq!(error.status.code(), Some(2));
    assert!(error.stdout.is_empty());
    assert_eq!(
        String::from_utf8(error.stderr).expect("authored UTF-8"),
        usage_error("manifest is required").2
    );
}

#[test]
fn a_relative_manifest_binds_the_working_directory() {
    let fixture = Declaration::recorded();
    fixture.write("run.json", Declaration::raw());
    let actual = Command::new(env!("CARGO_BIN_EXE_loop-timing-witness-analyze-native"))
        .args(["run.json", "--output-dir", "report"])
        .current_dir(fixture.root())
        .env_remove("LOOP_TIMING_WITNESS_CHECKER_INSTALLATION")
        .output()
        .expect("installed command");
    assert_eq!(actual.status.code(), Some(1));
    assert_eq!(
        String::from_utf8(actual.stderr).expect("authored UTF-8"),
        "run analysis: FAIL: No reviewed checker installation descriptor is selected for this \
         neural registration.\n"
    );
    assert!(!fixture.root().join("report").exists());
}

#[test]
fn an_unresolvable_acquisition_directory_is_a_binding_refusal() {
    let fixture = Declaration::recorded();
    let manifest = fixture.write("run.json", Declaration::raw());
    let trace = std::env::temp_dir().join(format!("witness-readlink-{}.trace", std::process::id()));
    let actual = Command::new("strace")
        .args(["-f", "-P"])
        .arg(fixture.root())
        .args([
            "-e",
            "trace=readlink",
            "-e",
            "inject=readlink:error=EIO",
            "-o",
        ])
        .arg(&trace)
        .arg(env!("CARGO_BIN_EXE_loop-timing-witness-analyze-native"))
        .arg(&manifest)
        .arg("--output-dir")
        .arg(fixture.root().join("report"))
        .output()
        .expect("traced installed command");
    let recorded = std::fs::read_to_string(&trace).expect("trace");
    std::fs::remove_file(&trace).expect("remove only this test's trace");
    assert!(recorded.contains("INJECTED"), "{recorded}");
    assert_eq!(actual.status.code(), Some(1));
    assert_eq!(
        String::from_utf8(actual.stderr).expect("authored UTF-8"),
        "run analysis: FAIL: Cannot bind the complete public neural acquisition.\n"
    );
}
