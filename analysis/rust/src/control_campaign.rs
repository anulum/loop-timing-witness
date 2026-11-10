// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — repeat campaign loading with hash-bound runs

//! Load a repeat campaign and the runs it orders, as Python's
//! `campaign_manifest.load_campaign` does.
//!
//! The steps, their order and every refusal text are Python's: the bounded
//! JSON object, the campaign schema, the repeat order, each run manifest path
//! inside the campaign directory, a run manifest bound twice, then each
//! repeat's digest and run, and last the run identities and the configuration
//! every loaded repeat must share. A run its own loader refuses stays in the
//! campaign as a refused repeat; a file that cannot be opened or read refuses
//! the whole campaign, as Python's `OSError` does.

use crate::control_json::decode_object;
use crate::control_manifest::{ControlRun, Failure, load_classified, read_file, resolve};
use crate::control_number::{Num, python_number};
use crate::control_receipts::python_equal;
use crate::control_schema::Schema;
use crate::control_text::{python_display, python_repr};
use crate::files::digest;
use serde_json::{Map, Value};
use std::path::{Component, Path, PathBuf};
use std::sync::LazyLock;

/// The committed repeat campaign schema.
static CAMPAIGN_SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../repeat-campaign.schema.json")).expect("committed schema")
});
/// Run fields that must agree before samples are pooled, after the source identity.
const CONFIGURATION: [&str; 9] = [
    "profile",
    "placement",
    "sample_period_ticks",
    "cycle_count",
    "warmup_cycles",
    "load_case",
    "controller",
    "plant",
    "fault_schedule",
];
/// Hardware artefacts whose digests a board configuration binds.
const HARDWARE: [&str; 4] = ["bitstream", "firmware", "linux_image", "controller_binary"];

/// One ordered repeat and the outcome of loading its run.
#[derive(Debug)]
pub(crate) struct Repeat {
    /// The schema-checked `repeat_index`, an integer or an integral float.
    pub(crate) index: Value,
    /// The operator's declaration that the board rebooted before this repeat.
    pub(crate) rebooted: bool,
    /// The verified SHA-256 of the run manifest bytes.
    pub(crate) sha256: String,
    /// The loaded run, or `None` when its loader refused it.
    pub(crate) run: Option<ControlRun>,
    /// The loader's refusal text of a refused run.
    pub(crate) refusal: Option<String>,
}

/// A validated campaign and its repeats in index order.
#[derive(Debug)]
pub(crate) struct Campaign {
    /// The schema-valid campaign manifest.
    pub(crate) manifest: Map<String, Value>,
    /// The SHA-256 of the exact campaign manifest bytes.
    pub(crate) sha256: String,
    /// The repeats in index order; every loaded repeat shares one configuration.
    pub(crate) repeats: Vec<Repeat>,
}

/// The run fields that must agree before samples are pooled, in Python's order:
/// the measurement-domain digest, the source tool identity, the run
/// configuration, the instrument floor and the hardware artefact digests.
pub(crate) fn configuration(run: &ControlRun) -> Vec<(&'static str, Value)> {
    let manifest = &run.manifest;
    let source = &manifest["source"];
    let mut fields = vec![
        (
            "measurement_domain_sha256",
            manifest["measurement_domain"]["sha256"].clone(),
        ),
        ("source_kind", source["kind"].clone()),
        ("source_tool", source["tool"].clone()),
        ("source_version", source["version"].clone()),
    ];
    fields.extend(CONFIGURATION.map(|name| (name, manifest[name].clone())));
    fields.push((
        "tracking_sampling",
        manifest
            .get("tracking_sampling")
            .cloned()
            .unwrap_or_default(),
    ));
    fields.push((
        "instrument_floor_ticks",
        manifest["instrument"]["floor_ticks"].clone(),
    ));
    let hardware = &manifest["hardware_artifacts"];
    let artefacts = if hardware.is_null() {
        Value::Null
    } else {
        let mut artefacts: Map<String, Value> = HARDWARE
            .iter()
            .map(|name| ((*name).to_owned(), hardware[*name]["sha256"].clone()))
            .collect();
        for name in ["libero_version", "toolchain_version"] {
            artefacts.insert(name.to_owned(), hardware[name].clone());
        }
        Value::Object(artefacts)
    };
    fields.push(("hardware_artifacts", artefacts));
    fields
}

/// The text of a schema-checked string member.
fn text(value: &Value) -> &str {
    value.as_str().expect("schema-checked string")
}

/// Resolve one run manifest without leaving the campaign directory.
///
/// The path names what Python's `Path` makes of it: repeated separators, `.`
/// parts and a final separator are dropped before it is resolved.
fn run_manifest_path(directory: &Path, declared: &str) -> Result<PathBuf, String> {
    let relative = Path::new(declared);
    // The schema pattern starts every path with a letter or digit, so it is never absolute.
    if relative
        .components()
        .any(|part| part == Component::ParentDir)
    {
        return Err(format!(
            "run manifest path must stay within the campaign directory: {declared}"
        ));
    }
    let parts: PathBuf = relative.components().collect();
    std::fs::canonicalize(directory.join(parts))
        .ok()
        .filter(|path| path.starts_with(directory) && path.is_file())
        .ok_or_else(|| {
            format!("run manifest is not a regular file inside the campaign: {declared}")
        })
}

/// Verify one run manifest digest and load its run from the verified bytes.
fn load_repeat(path: &Path, item: &Value) -> Result<Repeat, String> {
    let reference = &item["run_manifest"];
    let raw = read_file(path).map_err(Failure::text)?;
    let sha256 = text(&reference["sha256"]).to_owned();
    if digest(&raw) != sha256 {
        return Err(format!(
            "run manifest SHA-256 mismatch: {}",
            text(&reference["path"])
        ));
    }
    let (run, refusal) = match load_classified(path, Some(&raw)) {
        Ok(run) => (Some(run), None),
        Err(Failure::Refused(refusal)) => (None, Some(refusal)),
        Err(Failure::Os(error)) => return Err(error),
    };
    Ok(Repeat {
        index: item["repeat_index"].clone(),
        rebooted: item["rebooted_before_run"] == true,
        sha256,
        run,
        refusal,
    })
}

/// Require distinct runs and one configuration across the loaded repeats.
fn check_repeats(repeats: &[Repeat]) -> Result<(), String> {
    let loaded: Vec<(&Repeat, &ControlRun)> = repeats
        .iter()
        .filter_map(|repeat| repeat.run.as_ref().map(|run| (repeat, run)))
        .collect();
    let mut run_ids: Vec<&str> = Vec::new();
    for (repeat, run) in &loaded {
        let run_id = text(&run.manifest["run_id"]);
        if run_ids.contains(&run_id) {
            return Err(format!(
                "repeat {} reuses run_id {}",
                python_number(&repeat.index),
                python_repr(run_id)
            ));
        }
        run_ids.push(run_id);
    }
    let Some(((first, first_run), rest)) = loaded.split_first() else {
        return Ok(());
    };
    let reference = configuration(first_run);
    for (repeat, run) in rest {
        let fields = configuration(run);
        if let Some((name, _)) = reference
            .iter()
            .zip(&fields)
            .map(|((name, value), (_, other))| (name, python_equal(value, other)))
            .find(|(_, same)| !same)
        {
            return Err(format!(
                "repeat {} differs from repeat {} in {name}; incompatible runs are not pooled",
                python_number(&repeat.index),
                python_number(&first.index)
            ));
        }
    }
    Ok(())
}

/// Load a schema-valid repeat campaign and every run it binds.
pub(crate) fn load_campaign(path: &Path) -> Result<Campaign, String> {
    let raw = read_file(path).map_err(Failure::text)?;
    let (manifest, _) = decode_object(&raw, &python_display(path))?;
    let document = Value::Object(manifest.clone());
    if let Some(location) = CAMPAIGN_SCHEMA.locations(&document).first() {
        return Err(format!(
            "repeat campaign {location}: does not satisfy the repeat campaign schema"
        ));
    }
    let items = document["repeats"]
        .as_array()
        .expect("schema-checked array");
    let ordered = items.iter().enumerate().all(|(position, item)| {
        Num::of(&item["repeat_index"]).same(Num::Int(position as u128 + 1))
    });
    if !ordered {
        return Err("repeat_index values must run 1, 2, 3, ... in manifest order".to_owned());
    }
    let directory = resolve(path)
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_default();
    let paths = items
        .iter()
        .map(|item| run_manifest_path(&directory, text(&item["run_manifest"]["path"])))
        .collect::<Result<Vec<_>, _>>()?;
    if paths
        .iter()
        .enumerate()
        .any(|(position, path)| paths[..position].contains(path))
    {
        return Err("two repeats bind the same run manifest".to_owned());
    }
    let repeats = paths
        .iter()
        .zip(items)
        .map(|(path, item)| load_repeat(path, item))
        .collect::<Result<Vec<_>, _>>()?;
    check_repeats(&repeats)?;
    Ok(Campaign {
        manifest,
        sha256: digest(&raw),
        repeats,
    })
}
