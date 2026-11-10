// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native repeat campaign command

//! Expose the native repeat campaign analysis with the campaign/output-directory arguments.

use witness_analysis::campaign_command;

/// Run the campaign command on the process arguments.
fn main() {
    let arguments: Vec<_> = std::env::args_os().skip(1).collect();
    std::process::exit(campaign_command::run(
        &arguments,
        &mut std::io::stdout(),
        &mut std::io::stderr(),
    ));
}
