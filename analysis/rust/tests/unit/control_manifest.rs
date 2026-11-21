// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — run loading, crate-internal controls

//! Accept and refuse the same `started_utc` spellings as the Python rule.

use super::{read_file, utc_timestamp};
use rustix::fs::{CWD, FileType, Mode, mknodat};

#[test]
fn utc_timestamps_follow_the_python_rule() {
    for accepted in [
        "2026-09-26T00:00:00Z",
        "2026-09-26t00:00:00z",
        "2026-09-26T00:00:00+00:00",
        "2026-09-26T00:00:00-00:00",
        "2026-09-26T00:00:00.123456789Z",
        "2024-02-29T23:59:59Z",
        "2000-02-29T00:00:00Z",
        "0001-01-01T00:00:00Z",
    ] {
        assert!(utc_timestamp(accepted), "{accepted}");
    }
    for refused in [
        "2026-09-26T02:00:00+02:00",
        "2026-09-26T00:00:60Z",
        "2026-02-30T00:00:00Z",
        "1900-02-29T00:00:00Z",
        "2026-04-31T00:00:00Z",
        "2026-13-01T00:00:00Z",
        "2026-00-01T00:00:00Z",
        "0000-01-01T00:00:00Z",
        "2026-09-26T24:00:00Z",
        "2026-09-26T00:60:00Z",
        "2026-09-26T00:00Z",
        "2026-09-26T00:00:00Z\n",
        "2026-09-26 00:00:00Z",
        "2026-09-26T00:00:00.Z",
        "2026-09-26T00:00:00",
        "2026/09/26T00:00:00Z",
        "2026-09/26T00:00:00Z",
        "2026-09-26T00-00:00Z",
        "2026-09-26T00:00-00Z",
        "20x6-09-26T00:00:00Z",
    ] {
        assert!(!utc_timestamp(refused), "{refused}");
    }
}

#[test]
fn run_inputs_are_read_without_blocking_on_a_fifo() {
    let root = std::env::temp_dir().join(format!("witness-regular-{}", std::process::id()));
    std::fs::create_dir(&root).expect("owned directory");
    let regular = root.join("regular.bin");
    std::fs::write(&regular, b"bytes").expect("regular file");
    let fifo = root.join("pipe");
    mknodat(CWD, &fifo, FileType::Fifo, Mode::RUSR | Mode::WUSR, 0).expect("FIFO");
    let directory = root.join("directory");
    std::fs::create_dir(&directory).expect("directory");
    let text = |path: &std::path::Path| path.to_str().expect("UTF-8 path").to_owned();
    assert_eq!(read_file(&regular).ok(), Some(b"bytes".to_vec()));
    // A device reads as before; only what would block or never end is refused.
    assert_eq!(
        read_file(std::path::Path::new("/dev/null")).ok(),
        Some(Vec::new())
    );
    // A FIFO without a writer is refused at once instead of blocking the reader.
    assert_eq!(
        read_file(&fifo).err().map(|failure| failure.text()),
        Some(format!("[Errno 22] Invalid argument: '{}'", text(&fifo)))
    );
    assert_eq!(
        read_file(&directory).err().map(|failure| failure.text()),
        Some(format!("[Errno 21] Is a directory: '{}'", text(&directory)))
    );
    std::fs::remove_dir_all(&root).expect("remove the owned directory");
}
