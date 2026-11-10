// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — repeat campaign command arguments and statuses

//! Run the installed repeat campaign command for its usage and argument errors.
//!
//! Published and refused campaigns are compared with the Python command by
//! the parity tests, which own complete campaigns of real captures.

use std::process::Command;
use witness_analysis::campaign_command;

#[test]
fn the_installed_campaign_command_prints_its_usage_and_argument_errors() {
    let binary = env!("CARGO_BIN_EXE_loop-timing-witness-campaign-native");
    let help = Command::new(binary)
        .arg("--help")
        .output()
        .expect("installed command");
    assert_eq!(help.status.code(), Some(0));
    assert_eq!(
        help.stdout,
        format!("{}\n", campaign_command::USAGE).into_bytes()
    );
    assert!(help.stderr.is_empty());
    let error = Command::new(binary)
        .args(["campaign.json"])
        .output()
        .expect("installed command");
    assert_eq!(error.status.code(), Some(2));
    assert!(error.stdout.is_empty());
    assert_eq!(
        String::from_utf8(error.stderr).expect("authored UTF-8"),
        format!(
            "{}\nrepeat campaign: argument error: output directory is required\n",
            campaign_command::USAGE
        )
    );
}
