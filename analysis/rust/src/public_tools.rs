// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — closed public native and checker receipt binding

//! Decode complete original receipts into typed analysis roles.

use crate::binding;
use crate::files::{FileRef, decode};
use crate::receipts::{PrefixRefs, ResetTool, Tool};
use serde::Deserialize;
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::Path;

/// Exact original generation and comparison receipt roles.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CheckerReceipts {
    generation: FileRef,
    check: FileRef,
}

/// Closed public epoch-zero auxiliary receipt.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PublicTool {
    pub schema_id: String,
    pub checker_receipts: CheckerReceipts,
    /// Actual original scope text.
    pub scope: String,
    /// Actual compiler/simulator receipts.
    pub compiler_simulator_runtime: FileRef,
    /// Actual recorded model/checker receipt.
    pub source_owned_public_model_checker: FileRef,
    /// Actual source counter snapshot.
    pub counter_receipt: FileRef,
    /// Full original parallel raw-spike trace.
    pub raw_spike_trace: FileRef,
    /// Unchanged original stimulus.
    pub original_stimulus: FileRef,
    /// Actual producer completion receipt.
    pub actual_completion: FileRef,
    /// Original detailed trial analysis, separately bounded.
    pub existing_trial_analysis: FileRef,
    /// Actual simulator edge schedule.
    pub declared_clock_schedule: FileRef,
}

/// Closed public reset auxiliary receipt.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PublicResetTool {
    pub schema_id: String,
    pub checker_receipts: CheckerReceipts,
    /// Actual original scope text.
    pub scope: String,
    /// Actual compiler/simulator receipts.
    pub compiler_simulator_runtime: FileRef,
    /// Actual recorded model/checker receipt.
    pub source_owned_public_model_checker: FileRef,
    /// Actual source counter snapshot.
    pub counter_receipt: FileRef,
    /// Full original parallel raw-spike trace.
    pub raw_spike_trace: FileRef,
    /// Unchanged original stimulus.
    pub original_stimulus: FileRef,
    /// Actual producer completion receipt.
    pub actual_completion: FileRef,
    /// Original detailed trial analysis.
    pub existing_trial_analysis: FileRef,
    /// Actual simulator edge schedule.
    pub declared_clock_schedule: FileRef,
    /// Actual original HDL reset receipt.
    pub reset_epoch_receipt: FileRef,
    /// Every actual abandoned trace reference.
    pub abandoned_prefix_traces: PrefixRefs,
}

/// Bind every complete original public tool/checker/reset role.
pub(crate) fn bind(
    root: &Path,
    epoch: u32,
    files: &mut BTreeMap<String, Vec<u8>>,
) -> Result<Value, String> {
    let raw = files["tool_receipt"].clone();
    let (schema_id, checker) = if epoch == 0 {
        let tool: PublicTool = decode(&raw, "public neural tool receipt")?;
        binding::tool_files(
            files,
            root,
            Tool {
                scope: tool.scope,
                compiler_simulator_runtime: tool.compiler_simulator_runtime,
                source_owned_public_model_checker: tool.source_owned_public_model_checker,
                counter_receipt: tool.counter_receipt,
                raw_spike_trace: tool.raw_spike_trace,
                original_stimulus: tool.original_stimulus,
                actual_completion: tool.actual_completion,
                existing_trial_analysis: tool.existing_trial_analysis,
                declared_clock_schedule: tool.declared_clock_schedule,
            },
        )?;
        (tool.schema_id, tool.checker_receipts)
    } else {
        let tool: PublicResetTool = decode(&raw, "public reset tool receipt")?;
        binding::reset_files(
            files,
            root,
            ResetTool {
                scope: tool.scope,
                compiler_simulator_runtime: tool.compiler_simulator_runtime,
                source_owned_public_model_checker: tool.source_owned_public_model_checker,
                counter_receipt: tool.counter_receipt,
                raw_spike_trace: tool.raw_spike_trace,
                original_stimulus: tool.original_stimulus,
                actual_completion: tool.actual_completion,
                existing_trial_analysis: tool.existing_trial_analysis,
                declared_clock_schedule: tool.declared_clock_schedule,
                reset_epoch_receipt: tool.reset_epoch_receipt,
                abandoned_prefix_traces: tool.abandoned_prefix_traces,
            },
        )?;
        (tool.schema_id, tool.checker_receipts)
    };
    if schema_id != "loop-timing-witness.neural-tool-receipt.v1" {
        return Err("Public neural tool receipt requires its complete closed successor.".into());
    }
    binding::role(
        files,
        root,
        "checker_generation_receipt",
        &checker.generation,
        65536,
    )?;
    binding::role(files, root, "checker_check_receipt", &checker.check, 65536)?;
    decode(&raw, "complete public tool receipt")
}
