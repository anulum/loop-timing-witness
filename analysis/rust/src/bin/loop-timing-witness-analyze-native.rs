// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native public neural analysis command

//! Expose the complete Rust verifier with the same manifest/output-directory arguments.

use witness_analysis::{NeuralRegistry, public_command};

/// Run the command against the packaged reviewed registry.
fn main() {
    let arguments: Vec<_> = std::env::args_os().skip(1).collect();
    std::process::exit(public_command::run(
        &arguments,
        &NeuralRegistry::reviewed(),
        &mut std::io::stdout(),
        &mut std::io::stderr(),
    ));
}
