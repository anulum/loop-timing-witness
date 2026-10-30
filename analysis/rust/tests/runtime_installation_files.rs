// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public installed-runtime complete-file contracts

//! Bind real packaged worker bytes without selecting or executing an SC runtime.

use sha2::{Digest, Sha256};
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use witness_analysis::public_runtime::InstalledFile;

const WORKER: &[u8] =
    include_bytes!("../checker_worker/loop_timing_witness/neural_checker_worker.py");
const WORKER_DIGEST: &str = "28f2a3d33c3278738b589035f95944800a8a31a58031888783f468b93685e001";

/// Own a real worker copy whose file condition can change without touching its source.
struct InstalledWorker {
    root: PathBuf,
    binding: InstalledFile,
}

impl InstalledWorker {
    fn create() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        assert_eq!(WORKER.len(), 4789);
        assert_eq!(format!("{:x}", Sha256::digest(WORKER)), WORKER_DIGEST);
        let instant = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("current clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "witness-installed-worker-{}-{instant}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).expect("exclusive installed-worker allocation");
        let path = root.join("neural_checker_worker.py");
        std::fs::write(&path, WORKER).expect("exact complete packaged worker bytes");
        Self {
            root,
            binding: InstalledFile {
                name: "loop_timing_witness/neural_checker_worker.py".into(),
                path,
                sha256: WORKER_DIGEST.into(),
                byte_length: WORKER.len() as u64,
            },
        }
    }
}

impl Drop for InstalledWorker {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root)
            .expect("remove only this test's installed-worker allocation");
    }
}

#[test]
fn complete_worker_binding_refuses_replacement_truncation_and_appending() {
    let original = InstalledWorker::create();
    assert_eq!(original.binding.verify(), Ok(()));
    let mut replaced = WORKER.to_vec();
    replaced[0] ^= 1;
    let mut appended = WORKER.to_vec();
    appended.push(b'\n');
    for changed in [replaced, WORKER[..WORKER.len() - 1].to_vec(), appended] {
        std::fs::write(&original.binding.path, changed).expect("changed actual worker copy");
        assert_eq!(
            original.binding.verify(),
            Err("Selected checker runtime file differs from its reviewed binding.".into())
        );
    }
}

#[test]
fn correct_worker_bytes_do_not_waive_declared_length_digest_or_allocation() {
    let mut original = InstalledWorker::create();
    original.binding.sha256 = "0".repeat(64);
    assert_eq!(
        original.binding.verify(),
        Err("Selected checker runtime file differs from its reviewed binding.".into())
    );
    original.binding.sha256 = WORKER_DIGEST.into();
    for length in [0, WORKER.len() as u64 - 1, WORKER.len() as u64 + 1] {
        original.binding.byte_length = length;
        assert_eq!(
            original.binding.verify(),
            Err("Selected checker runtime file differs from its reviewed binding.".into())
        );
    }
    std::fs::remove_file(&original.binding.path).expect("remove only the owned worker copy");
    for length in [268435457, u64::MAX] {
        original.binding.byte_length = length;
        assert_eq!(
            original.binding.verify(),
            Err("Selected checker runtime file exceeds its allocation.".into())
        );
    }
}

#[test]
fn empty_regular_file_is_verified_and_missing_or_nonregular_files_are_refused() {
    let mut original = InstalledWorker::create();
    std::fs::write(&original.binding.path, []).expect("present zero-byte installed file");
    original.binding.byte_length = 0;
    original.binding.sha256 = format!("{:x}", Sha256::digest(b""));
    assert_eq!(original.binding.verify(), Ok(()));
    std::fs::remove_file(&original.binding.path).expect("remove only the owned empty file");
    assert_eq!(
        original.binding.verify(),
        Err("Selected checker runtime file is unavailable.".into())
    );
    std::fs::create_dir(&original.binding.path).expect("actual directory in place of a file");
    assert_eq!(
        original.binding.verify(),
        Err("Selected checker runtime requires a regular resolved file.".into())
    );
    std::fs::remove_dir(&original.binding.path).expect("remove only the owned empty directory");
    let target = original.root.join("actual-worker.py");
    std::fs::write(&target, WORKER).expect("exact original symlink target bytes");
    std::os::unix::fs::symlink(&target, &original.binding.path).expect("actual final symlink");
    original.binding.byte_length = WORKER.len() as u64;
    original.binding.sha256 = WORKER_DIGEST.into();
    assert_eq!(
        original.binding.verify(),
        Err("Selected checker runtime file is unavailable.".into())
    );
}

#[test]
fn unwritten_fifo_is_refused_without_waiting_for_a_writer() {
    const CHILD: &str = "WITNESS_INSTALLED_WORKER_FIFO_CHILD";
    if std::env::var_os(CHILD).is_some() {
        let original = InstalledWorker::create();
        std::fs::remove_file(&original.binding.path).expect("remove only the owned worker copy");
        assert!(
            Command::new("mkfifo")
                .arg(&original.binding.path)
                .status()
                .expect("create an actual owned FIFO")
                .success()
        );
        assert_eq!(
            original.binding.verify(),
            Err("Selected checker runtime requires a regular resolved file.".into())
        );
        return;
    }
    let result = Command::new("timeout")
        .args(["--signal=TERM", "--kill-after=1s", "5s"])
        .arg(std::env::current_exe().expect("actual public integration test executable"))
        .args([
            "--exact",
            "unwritten_fifo_is_refused_without_waiting_for_a_writer",
            "--test-threads=1",
        ])
        .env(CHILD, "1")
        .output()
        .expect("bounded actual public installed-file call");
    assert!(result.status.success(), "{result:?}");
}
