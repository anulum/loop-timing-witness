// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — controllers/rust/src/main.rs

//! Streaming host entry point for the public fixed-point controller kernels.

use std::io::{self, BufRead, Write};
use witness_controller::{Coefficients, PidState, lqr_step};

/// Parse and validate the complete eleven-field immutable coefficient record.
fn coefficients(line: &str) -> Result<Coefficients, String> {
    let values = line
        .split(',')
        .map(|field| {
            field
                .parse::<i32>()
                .map_err(|_| "invalid coefficient row".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if values.len() != 11 {
        return Err("invalid coefficient row".to_owned());
    }
    let result = Coefficients {
        kp: values[0],
        ki_period: values[1],
        derivative_decay: values[2],
        derivative_gain: values[3],
        position_gain: values[4],
        velocity_gain: values[5],
        reference_gain: values[6],
        output_min: values[7],
        output_max: values[8],
        integral_min: values[9],
        integral_max: values[10],
    };
    result
        .validate()
        .map_err(|_| "invalid coefficients".to_owned())?;
    Ok(result)
}

/// Process real input records and flush one cycle-tagged command per sample.
fn run() -> Result<(), String> {
    let arguments: Vec<_> = std::env::args().collect();
    if arguments.len() != 2 || !matches!(arguments[1].as_str(), "pid" | "lqr") {
        return Err("usage: witness-controller pid|lqr < vectors.csv".to_owned());
    }
    let lqr = arguments[1] == "lqr";
    let input = io::stdin();
    let mut lines = input.lock().lines();
    let first = lines
        .next()
        .ok_or("invalid coefficient row")?
        .map_err(|error| error.to_string())?;
    let configuration = coefficients(&first)?;
    let mut state = PidState::default();
    let mut output = io::stdout().lock();
    for line in lines {
        let line = line.map_err(|error| error.to_string())?;
        if line == "reset" {
            state.reset();
            continue;
        }
        let fields: Vec<_> = line.split(',').collect();
        if fields.len() != 4 {
            return Err("invalid sample row".to_owned());
        }
        let cycle = fields[0].parse::<u32>().map_err(|_| "invalid sample row")?;
        let reference = fields[1].parse::<i32>().map_err(|_| "invalid sample row")?;
        let position = fields[2].parse::<i32>().map_err(|_| "invalid sample row")?;
        let velocity = fields[3].parse::<i32>().map_err(|_| "invalid sample row")?;
        let command = if lqr {
            lqr_step(&configuration, cycle, reference, position, velocity)
        } else {
            state.step(&configuration, cycle, reference, position)
        }
        .expect("coefficients validated before this immutable run");
        writeln!(
            output,
            "{},{},{},{},{},{}",
            command.cycle,
            command.command,
            command.integral,
            command.derivative,
            u8::from(command.clipped),
            u8::from(command.integral_held)
        )
        .map_err(|error| error.to_string())?;
    }
    Ok(())
}

/// Report protocol or I/O failure with a nonzero process exit.
fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
