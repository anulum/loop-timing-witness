// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — original complete checker receipt validation

//! Validate recorded original operations independently of fresh source-checker execution.

use crate::files::{FileRef, decode, read_bound};
use crate::public_binding::PublicRun;
use crate::public_checker_fields::{Environment, Receipt, Roles};
use crate::public_policy::same;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

/// Bind one whole inventory and return actual-path correspondence without execution.
///
/// The checks and their order follow the Python verifier, so both refuse a
/// damaged inventory with the same message.
fn inventory(
    run: &PublicRun,
    reference: &FileRef,
    expected: &BTreeMap<String, FileRef>,
) -> Result<BTreeMap<String, String>, String> {
    let raw = read_bound(&run.core.root, reference, 1048576)?;
    let observed = crate::strict_json::decode_object(&raw, "observed checker inventory")?;
    let rows = match (observed.get("schema_id"), observed.get("files")) {
        (Some(Value::String(schema)), Some(Value::Array(rows)))
            if observed.len() == 2
                && schema == "loop-timing-witness.checker-observed-inventory.v1" =>
        {
            rows
        }
        _ => {
            return Err(
                "Checker observed inventory requires its closed versioned structure.".into(),
            );
        }
    };
    let mut paths = BTreeMap::new();
    let mut roles = BTreeSet::new();
    for row in rows {
        let fields = row.as_object().filter(|fields| {
            fields.len() == 4
                && fields.get("path").is_some_and(Value::is_string)
                && fields.get("actual_path").is_some_and(Value::is_string)
                && fields.contains_key("sha256")
                && fields
                    .get("byte_length")
                    .is_some_and(|value| value.is_i64() || value.is_u64())
        });
        let Some(fields) = fields else {
            return Err("Checker observed inventory row is malformed.".into());
        };
        let (name, actual) = (fields["path"].as_str(), fields["actual_path"].as_str());
        let (Some(name), Some(actual)) = (name, actual) else {
            return Err("Checker observed inventory row is malformed.".into());
        };
        let identity = expected.get(name);
        if roles.contains(name)
            || paths.contains_key(actual)
            || identity.is_none_or(|identity| {
                fields["sha256"] != identity.sha256.as_str()
                    || fields["byte_length"] != identity.byte_length
            })
        {
            return Err(
                "Checker observed inventory differs from the complete reviewed roles.".into(),
            );
        }
        paths.insert(actual.to_owned(), name.to_owned());
        roles.insert(name.to_owned());
    }
    if roles != expected.keys().cloned().collect() {
        return Err("Checker observed inventory omits a reviewed role.".into());
    }
    Ok(paths)
}

/// Compare each complete original operation input and output to its bound run role.
fn input_outputs(
    run: &PublicRun,
    receipt: &Receipt,
    operation: &str,
) -> Result<Vec<String>, String> {
    let roles: Vec<(&FileRef, &str)> = match (operation, &receipt.inputs, &receipt.outputs) {
        ("generate", Roles::Empty(_), Roles::Fixture(fixture)) => vec![
            (&fixture.stimuli, "original_stimulus"),
            (&fixture.reference, "reference_projection"),
        ],
        ("check", Roles::Projection(projection), Roles::Empty(_)) => vec![
            (&projection.stimuli, "original_stimulus"),
            (&projection.reference, "reference_projection"),
            (&projection.observed, "numerical_projection"),
        ],
        _ => {
            return Err(
                "Original checker invocation lacks its complete input/output roles.".into(),
            );
        }
    };
    let mut findings = Vec::new();
    for (reference, name) in roles {
        if read_bound(&run.core.root, reference, 65536)? != run.core.files[name] {
            findings.push(
                "Original checker input/output differs from its bound whole-run role.".into(),
            );
        }
    }
    Ok(findings)
}

/// Bind both original complete checker receipts without executing their argv.
pub(crate) fn findings(run: &mut PublicRun) -> Result<Vec<String>, String> {
    let source_roles: BTreeMap<_, _> = run
        .contract
        .checker
        .source_files
        .iter()
        .map(|reference| (reference.path.clone(), reference.clone()))
        .collect();
    let runtime_roles: BTreeMap<_, _> = run
        .contract
        .installation
        .references()
        .into_iter()
        .map(|reference| (reference.path.clone(), reference))
        .collect();
    let mut failures = Vec::new();
    for (label, operation) in [("generation", "generate"), ("check", "check")] {
        let receipt: Receipt = decode(
            &run.core.files[&format!("checker_{label}_receipt")],
            "original checker invocation",
        )?;
        if receipt.schema_id != "loop-timing-witness.sc-checker-execution.v1" {
            return Err(
                "Original checker invocation requires its complete closed versioned receipt."
                    .into(),
            );
        }
        if receipt.started_ns == 0
            || receipt.completed_ns < receipt.started_ns
            || receipt.elapsed_ns > 45_000_000_000
        {
            return Err(
                "Original checker timing and native status require exact finite integers.".into(),
            );
        }
        if !same(&receipt.source_contract_ref, &run.source_contract_ref)
            || !same(
                &receipt.checker_policy_ref,
                &run.contract.policy.checker_policy_ref,
            )
            || receipt.operation != operation
        {
            failures.push(
                "Original checker invocation source or operation differs from its static binding."
                    .into(),
            );
        }
        let paths = inventory(run, &receipt.observed_source_inventory_ref, &source_roles)?;
        inventory(run, &receipt.observed_runtime_inventory_ref, &runtime_roles)?;
        let arguments = if operation == "generate" {
            &run.contract.checker.generate_arguments
        } else {
            &run.contract.checker.check_arguments
        };
        if receipt.actual_argv.len() != 6
            || receipt.actual_argv.first().and_then(|name| paths.get(name))
                != Some(&run.contract.checker.entry_point.path)
            || receipt.actual_argv.get(1..) != Some(arguments.as_slice())
        {
            failures.push(
                "Original source-program argv differs from the bound fixed checker operation."
                    .into(),
            );
        }
        let observed: Environment = decode(
            &read_bound(&run.core.root, &receipt.environment_ref, 65536)?,
            "original checker environment",
        )?;
        let expected = crate::public_execution::environment(&run.core.root)?;
        if observed.0.keys().collect::<BTreeSet<_>>() != expected.keys().collect::<BTreeSet<_>>()
            || expected
                .iter()
                .any(|(key, value)| key != "TMPDIR" && observed.0.get(key) != Some(value))
        {
            failures.push(
                "Original checker environment differs from the selected closed worker profile."
                    .into(),
            );
        }
        failures.extend(input_outputs(run, &receipt, operation)?);
        let stdout = read_bound(&run.core.root, &receipt.stdout_ref, 1048576)?;
        let stderr = read_bound(&run.core.root, &receipt.stderr_ref, 1048576)?;
        if receipt.native_returncode != 0 || receipt.cleanup != "reaped" || !stderr.is_empty() {
            failures.push(
                "Original checker invocation did not complete cleanly with a passing comparison."
                    .into(),
            );
        }
        run.core
            .files
            .insert(format!("original_checker_{operation}_stdout"), stdout);
        run.core
            .files
            .insert(format!("original_checker_{operation}_stderr"), stderr);
    }
    Ok(failures)
}
