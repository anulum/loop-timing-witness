// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — owned checker process group, crate-internal controls

//! A normal exit of the group leader stops whatever it left running in its
//! group, as the Python runner does.

use super::run_group;
use std::collections::BTreeMap;
use std::time::{Duration, Instant};

#[test]
fn a_normal_exit_stops_what_the_leader_left_running() {
    let directory = std::env::temp_dir().join(format!("witness-group-{}", std::process::id()));
    std::fs::create_dir(&directory).expect("owned directory");
    let pid_file = directory.join("child.pid");
    let argv = vec![
        "/bin/sh".to_owned(),
        "-c".to_owned(),
        format!("sleep 60 & echo $! > '{}'; exit 0", pid_file.display()),
    ];
    let environment = BTreeMap::from([("PATH".to_owned(), "/usr/bin:/bin".to_owned())]);
    let completed = run_group(
        &argv,
        &directory,
        environment,
        (&directory.join("out"), &directory.join("err")),
        Duration::from_secs(30),
    )
    .expect("completed group");
    assert_eq!(completed.returncode, 0);
    assert!(!completed.interrupted);
    let child: u32 = std::fs::read_to_string(&pid_file)
        .expect("background process number")
        .trim()
        .parse()
        .expect("process number");
    let deadline = Instant::now() + Duration::from_secs(5);
    let stopped = loop {
        match std::fs::read_to_string(format!("/proc/{child}/stat")) {
            Err(_) => break true,
            Ok(stat) if stat.split_whitespace().nth(2) == Some("Z") => break true,
            Ok(_) if Instant::now() >= deadline => break false,
            Ok(_) => std::thread::sleep(Duration::from_millis(50)),
        }
    };
    std::fs::remove_dir_all(&directory).expect("remove the owned directory");
    assert!(stopped, "the background process outlived its group");
}
