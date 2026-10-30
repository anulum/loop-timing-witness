// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public original-file binding contracts

//! Exercise complete-byte acquisition through the public API and actual Linux files.

use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use witness_analysis::files::{FileRef, read_bound, read_expected};

const ORIGINAL: &[u8] = include_bytes!("data/neural-selected-original.run.json");
const ORIGINAL_DIGEST: &str = "3a982fb1aa66f64135ce622c68e408c6dcefb78022cc270f2ecc7fd047a3b075";
const EMPTY_DIGEST: &str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

/// Own only the input files required to change one real acquisition condition.
struct OriginalFile {
    root: PathBuf,
    reference: FileRef,
}

impl OriginalFile {
    fn create() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let instant = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("current clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "witness-original-file-{}-{instant}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).expect("exclusive original-file allocation");
        std::fs::create_dir(root.join("source_parts-A.0")).expect("actual nested input directory");
        let reference = FileRef {
            path: "source_parts-A.0/run-1_original.json".into(),
            sha256: ORIGINAL_DIGEST.into(),
            byte_length: ORIGINAL.len() as u64,
        };
        std::fs::write(root.join(&reference.path), ORIGINAL).expect("exact original input bytes");
        Self { root, reference }
    }
}

impl Drop for OriginalFile {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root)
            .expect("remove only this test's original-file allocation");
    }
}

#[test]
fn original_and_present_empty_files_have_distinct_complete_bindings() {
    let original = OriginalFile::create();
    for limit in [
        ORIGINAL.len(),
        ORIGINAL.len() + 512,
        isize::MAX as usize,
        usize::MAX,
    ] {
        assert_eq!(
            read_bound(&original.root, &original.reference, limit).expect("whole original binding"),
            ORIGINAL
        );
    }
    let empty = FileRef {
        path: "empty.bin".into(),
        sha256: EMPTY_DIGEST.into(),
        byte_length: 0,
    };
    std::fs::write(original.root.join(&empty.path), []).expect("present zero-byte original");
    assert_eq!(read_bound(&original.root, &empty, 0), Ok(Vec::new()));
    assert_eq!(
        read_expected(
            &original.root,
            &empty,
            0,
            b"",
            "Expected empty body differs."
        ),
        Ok(Vec::new())
    );
    std::fs::remove_file(original.root.join(&empty.path)).expect("remove the actual original");
    assert_eq!(
        read_bound(&original.root, &empty, 0),
        Err("Cannot open original file without symlinks: empty.bin.".into())
    );
}

#[test]
fn consumer_expected_bytes_are_checked_before_the_digest() {
    let original = OriginalFile::create();
    let message = "Selected original body changed.";
    assert_eq!(
        read_expected(
            &original.root,
            &original.reference,
            ORIGINAL.len(),
            ORIGINAL,
            message,
        ),
        Ok(ORIGINAL.to_vec())
    );
    let mut changed = ORIGINAL.to_vec();
    changed[0] ^= 1;
    std::fs::write(original.root.join(&original.reference.path), changed)
        .expect("actual same-length replacement");
    assert_eq!(
        read_expected(
            &original.root,
            &original.reference,
            ORIGINAL.len(),
            ORIGINAL,
            message,
        ),
        Err(message.into())
    );
}

#[test]
fn expected_body_does_not_waive_the_declared_reference() {
    let original = OriginalFile::create();
    let mut wrong_digest = original.reference.clone();
    wrong_digest.sha256 = "0".repeat(64);
    let mut wrong_length = original.reference.clone();
    wrong_length.byte_length += 1;
    for reference in [wrong_digest, wrong_length] {
        assert_eq!(
            read_expected(
                &original.root,
                &reference,
                ORIGINAL.len() + 1,
                ORIGINAL,
                "Expected complete body differs.",
            ),
            Err(format!(
                "Original whole length/SHA-256 differs: {}.",
                reference.path
            ))
        );
    }
}

#[test]
fn original_replacement_truncation_and_appending_never_reuse_a_reviewed_digest() {
    let original = OriginalFile::create();
    let path = original.root.join(&original.reference.path);
    let mut replaced = ORIGINAL.to_vec();
    replaced[0] ^= 1;
    for bytes in [replaced, ORIGINAL[..ORIGINAL.len() - 1].to_vec()] {
        std::fs::write(&path, bytes).expect("actual changed original file");
        assert_eq!(
            read_bound(&original.root, &original.reference, ORIGINAL.len()),
            Err(format!(
                "Original whole length/SHA-256 differs: {}.",
                original.reference.path
            ))
        );
    }
    let mut appended = ORIGINAL.to_vec();
    appended.push(b'\n');
    std::fs::write(&path, appended).expect("original plus one actual byte");
    assert_eq!(
        read_bound(&original.root, &original.reference, ORIGINAL.len() + 1),
        Err(format!(
            "Original file exceeds allocation: {}.",
            original.reference.path
        ))
    );
}

#[test]
fn reference_hash_and_allocation_limits_refuse_before_unbounded_reads() {
    let original = OriginalFile::create();
    assert_eq!(
        read_bound(&original.root, &original.reference, ORIGINAL.len() - 1),
        Err(format!(
            "Invalid original file reference: {}.",
            original.reference.path
        ))
    );
    for digest in [
        "0".repeat(63),
        "0".repeat(65),
        "A".repeat(64),
        "g".repeat(64),
        "é".repeat(32),
    ] {
        let mut reference = original.reference.clone();
        reference.sha256 = digest;
        assert_eq!(
            read_bound(&original.root, &reference, ORIGINAL.len()),
            Err(format!(
                "Invalid original file reference: {}.",
                reference.path
            ))
        );
    }
    for byte_length in [isize::MAX as u64, u64::MAX] {
        let mut reference = original.reference.clone();
        reference.byte_length = byte_length;
        assert_eq!(
            read_bound(&original.root, &reference, usize::MAX),
            Err("Original file allocation cannot admit an index-sized boundary check.".into())
        );
    }
}

#[test]
fn ambiguous_and_overlong_paths_never_select_an_original() {
    let original = OriginalFile::create();
    for path in [
        "",
        ".",
        "..",
        "../escape",
        "/absolute",
        "source/./input",
        "source/../input",
        "source//input",
        "source/",
        "source\\input",
        "source/input name",
        "source/é",
        "source/\0input",
        "source/input?",
    ] {
        let mut reference = original.reference.clone();
        reference.path = path.into();
        assert_eq!(
            read_bound(&original.root, &reference, ORIGINAL.len()),
            Err(format!("Invalid within-run original path: {path}."))
        );
    }
    let mut reference = original.reference.clone();
    reference.path = "a".repeat(4097);
    assert_eq!(
        read_bound(&original.root, &reference, ORIGINAL.len()),
        Err(format!(
            "Invalid within-run original path: {}.",
            reference.path
        ))
    );
    reference.path.truncate(4096);
    assert_eq!(
        read_bound(&original.root, &reference, ORIGINAL.len()),
        Err(format!(
            "Cannot open original file without symlinks: {}.",
            reference.path
        ))
    );
}

#[test]
fn missing_or_non_directory_roots_and_non_regular_inputs_are_distinct() {
    let original = OriginalFile::create();
    assert_eq!(
        read_bound(
            &original.root.join("absent"),
            &original.reference,
            ORIGINAL.len()
        ),
        Err("Run directory unavailable.".into())
    );
    assert_eq!(
        read_bound(
            &original.root.join(&original.reference.path),
            &original.reference,
            ORIGINAL.len()
        ),
        Err("Run directory descriptor unavailable.".into())
    );
    let mut directory = original.reference.clone();
    directory.path = "source_parts-A.0".into();
    assert_eq!(
        read_bound(&original.root, &directory, ORIGINAL.len()),
        Err("Original file is not regular within the run: source_parts-A.0.".into())
    );
    let mut missing_parent = original.reference.clone();
    missing_parent.path = "absent/input.json".into();
    assert_eq!(
        read_bound(&original.root, &missing_parent, ORIGINAL.len()),
        Err("Cannot open original parent without symlinks: absent/input.json.".into())
    );
}

#[test]
fn symlinked_originals_and_parent_directories_never_substitute_other_bytes() {
    let original = OriginalFile::create();
    std::os::unix::fs::symlink(&original.reference.path, original.root.join("alias.json"))
        .expect("actual final-file symlink");
    let mut reference = original.reference.clone();
    reference.path = "alias.json".into();
    assert_eq!(
        read_bound(&original.root, &reference, ORIGINAL.len()),
        Err("Cannot open original file without symlinks: alias.json.".into())
    );
    std::os::unix::fs::symlink("source_parts-A.0", original.root.join("alias"))
        .expect("actual same-root parent symlink");
    reference.path = "alias/run-1_original.json".into();
    assert_eq!(
        read_bound(&original.root, &reference, ORIGINAL.len()),
        Err("Cannot open original parent without symlinks: alias/run-1_original.json.".into())
    );
}

#[test]
fn an_unreadable_regular_kernel_file_returns_an_authored_read_refusal() {
    let reference = FileRef {
        path: "mem".into(),
        sha256: EMPTY_DIGEST.into(),
        byte_length: 0,
    };
    assert_eq!(
        read_bound(std::path::Path::new("/proc/self"), &reference, 0),
        Err("Cannot read full original file: mem.".into())
    );
}

#[test]
fn metadata_failure_after_open_refuses_original_file() {
    const ROOT_FLAG: &str = "WITNESS_METADATA_INPUT_ROOT";
    if let Some(root) = std::env::var_os(ROOT_FLAG) {
        let reference = FileRef {
            path: "source_parts-A.0/run-1_original.json".into(),
            sha256: ORIGINAL_DIGEST.into(),
            byte_length: ORIGINAL.len() as u64,
        };
        assert_eq!(
            read_bound(&PathBuf::from(root), &reference, ORIGINAL.len()),
            Err(format!(
                "Cannot inspect original file descriptor: {}.",
                reference.path
            ))
        );
        return;
    }
    let original = OriginalFile::create();
    let trace_path = original.root.join("metadata-injection.trace");
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
        .arg(std::env::current_exe().expect("current public API test executable"))
        .args([
            "--exact",
            "metadata_failure_after_open_refuses_original_file",
            "--test-threads=1",
        ])
        .env(ROOT_FLAG, &original.root)
        .output()
        .expect("actual metadata syscall fault in an owned public API process");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(output.status.success(), "{stderr}");
    let trace = std::fs::read_to_string(&trace_path).expect("actual metadata fault trace");
    let metadata = trace
        .lines()
        .find(|line| line.contains("run-1_original.json>"))
        .expect("metadata syscall addresses the original file descriptor");
    assert!(metadata.contains("EIO"));
    assert!(metadata.contains("INJECTED"));
}

#[test]
fn a_fifo_without_a_writer_is_refused_without_waiting_for_input() {
    const CHILD_FLAG: &str = "WITNESS_ORIGINAL_FIFO_CHILD";
    if std::env::var_os(CHILD_FLAG).is_some() {
        let original = OriginalFile::create();
        let fifo = original.root.join("unwritten.fifo");
        assert!(
            Command::new("mkfifo")
                .arg(&fifo)
                .status()
                .expect("create an actual FIFO")
                .success()
        );
        let reference = FileRef {
            path: "unwritten.fifo".into(),
            sha256: EMPTY_DIGEST.into(),
            byte_length: 0,
        };
        assert_eq!(
            read_bound(&original.root, &reference, 0),
            Err("Original file is not regular within the run: unwritten.fifo.".into())
        );
        return;
    }
    let output = Command::new("timeout")
        .args(["--signal=TERM", "--kill-after=1s", "5s"])
        .arg(std::env::current_exe().expect("current public API test executable"))
        .args([
            "--exact",
            "a_fifo_without_a_writer_is_refused_without_waiting_for_input",
        ])
        .env(CHILD_FLAG, "1")
        .output()
        .expect("bounded actual FIFO API process");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(output.status.success(), "{stderr}");
}
