// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — admission of a dedicated-hart capture and every artifact it binds

//! Admit an AMP capture as the Python function
//! `amp_simulation_manifest.admitted_capture` does.
//!
//! [`admitted_capture`] checks the capture receipt's schema and timestamps,
//! every captured artifact's path and digest in document order, the image's
//! preparation records and inputs, the tool and image identities, the
//! runtime, compiler and plugin snapshots, the image receipt, the logger
//! completion against the receipt's, the run configuration and the captured
//! streams. Every refusal and read error is Python's, met in Python's order.
//!
//! [`admitted_capture`]: crate::amp_capture::admitted_capture

use crate::amp_completion::{completion_receipt, decode_completion, validate_capture};
use crate::amp_failure::AmpFailure;
use crate::amp_files::{file_bytes, file_digest, load_document};
use crate::amp_image_dependencies::{
    image_dependency_record_count, validate_image_dependency_snapshot,
};
use crate::amp_image_receipt::validate_image_receipt;
use crate::amp_plugin_snapshot::validate_plugin_snapshot;
use crate::amp_run_input::read_amp_run;
use crate::amp_runtime_snapshot::validate_runtime_snapshot;
use crate::amp_rust_receipt::member;
use crate::control_json::{Orders, decode_object};
use crate::control_json_text::canonical_json;
use crate::control_manifest::utc_timestamp;
use crate::control_paths::{pure, realpath};
use crate::control_receipts::python_equal;
use crate::control_schema::Schema;
use serde_json::{Map, Value, json};
use std::path::Path;
use std::sync::LazyLock;

/// Python's `amp-capture.schema.json`, committed beside the crate.
static CAPTURE: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../amp-capture.schema.json")).expect("committed schema")
});

/// Python's closed C compiler identity: the plugin build schema's `$defs`
/// with its `compilers.c` member schema.
static COMPILER: LazyLock<Schema> = LazyLock::new(|| {
    let schema: Value = serde_json::from_str(include_str!("../amp-plugin-build.schema.json"))
        .expect("committed schema");
    let mut compiler = schema["properties"]["compilers"]["properties"]["c"]
        .as_object()
        .expect("the C compiler schema")
        .clone();
    compiler.insert("$defs".into(), schema["$defs"].clone());
    Schema::load(&Value::Object(compiler).to_string()).expect("the C compiler schema")
});

/// The artifacts every capture binds besides its precompile records.
const REQUIRED: [&str; 16] = [
    "image/firmware.elf",
    "image/platform.dtb",
    "image/configuration.txt",
    "image/image.json",
    "events.bin",
    "tracking_raw.csv",
    "spike.log",
    "measurement-domain.json",
    "command.json",
    "plugin_build.json",
    "plugin_source_index.json",
    "runtime_source_index.json",
    "image/runtime_source_index.json",
    "image/preparation.json",
    "image/compiler_source_index.json",
    "image/build_commands.json",
];
/// The image declarations held to the captured artifact digests.
const IMAGE_FILES: [(&str, &str); 4] = [
    ("firmware_sha256", "firmware.elf"),
    ("dtb_sha256", "platform.dtb"),
    ("configuration_sha256", "configuration.txt"),
    ("preparation_sha256", "preparation.json"),
];

/// A refusal with Python's text.
fn refused<T>(text: &str) -> Result<T, AmpFailure> {
    Err(AmpFailure::Refused(text.into()))
}

/// Python's `_capture_receipt`: the bounded JSON, the capture schema, then
/// the two UTC timestamps.
fn capture_receipt(content: &[u8]) -> Result<(Map<String, Value>, Orders), AmpFailure> {
    let (capture, orders) = decode_object(content, "AMP capture").map_err(AmpFailure::Refused)?;
    if let Some(location) = CAPTURE.locations(&Value::Object(capture.clone())).first() {
        return refused(&format!(
            "AMP capture receipt {location}: does not satisfy the AMP capture schema"
        ));
    }
    for field in ["started_utc", "completed_utc"] {
        if !utc_timestamp(capture[field].as_str().expect("schema-checked timestamp")) {
            return refused(&format!(
                "AMP capture receipt {field} must be an RFC 3339 date-time in UTC"
            ));
        }
    }
    Ok((capture, orders))
}

/// Every captured artifact inside the capture, unmoved and unchanged, in
/// document order. Python also refuses an absolute name; the capture schema's
/// name pattern starts with a letter or digit, so no admitted name is absolute.
fn check_artifacts(
    output: &Path,
    files: &Map<String, Value>,
    order: &[String],
) -> Result<(), AmpFailure> {
    let root = realpath(output).map_err(AmpFailure::Os)?;
    for name in order {
        let path = pure(&output.join(name));
        if name.split('/').any(|part| part == "..")
            || !realpath(&path).map_err(AmpFailure::Os)?.starts_with(&root)
            || files[name].as_str() != Some(file_digest(&path)?.as_str())
        {
            return refused("AMP capture artifact bytes or paths changed");
        }
    }
    Ok(())
}

/// The image's preparation records and inputs against the captured digests.
fn check_preparation(
    output: &Path,
    preparation: &Map<String, Value>,
    files: &Map<String, Value>,
    count: usize,
) -> Result<(), AmpFailure> {
    let mut records = Map::new();
    for index in 0..count {
        let path = pure(&output.join(format!("image/precompile/input_{index}.d")));
        records.insert(
            format!("precompile/input_{index}.d"),
            json!(file_digest(&path)?),
        );
    }
    if !python_equal(
        member(preparation, "dependency_records"),
        &Value::Object(records),
    ) {
        return refused("AMP original firmware preprocessing record identities disagree");
    }
    let inputs = member(preparation, "inputs").as_object();
    if inputs.is_none_or(|inputs| {
        inputs.is_empty()
            || inputs.iter().any(|(name, digest)| {
                !python_equal(member(files, &format!("image/{name}")), digest)
            })
    }) {
        return refused("AMP original firmware preparation input identities disagree");
    }
    Ok(())
}

/// The command's tools and runtime, the runtime's digest and the image's
/// toolchain, dependencies and artifact digests.
fn check_identities(
    capture: &Map<String, Value>,
    command: &Map<String, Value>,
    image: &Map<String, Value>,
    preparation: &Map<String, Value>,
) -> Result<(), AmpFailure> {
    let files = &capture["files"];
    if !python_equal(member(command, "tools"), &capture["tools"])
        || !python_equal(member(command, "runtime"), &capture["runtime"])
        || capture["runtime"]["sha256"] != capture["tools"]["spike"]
        || !python_equal(member(image, "toolchain"), member(preparation, "toolchain"))
        || !python_equal(
            member(image, "compiler_dependencies"),
            member(preparation, "compiler_dependencies"),
        )
        || IMAGE_FILES.iter().any(|(field, name)| {
            !python_equal(
                member(image, field),
                &files[format!("image/{name}").as_str()],
            )
        })
    {
        return refused("AMP capture tool or verified image identities disagree");
    }
    Ok(())
}

/// Admit a capture's receipt and every artifact it binds.
///
/// `content` is the capture receipt's bytes, already bound to the run.
///
/// # Errors
///
/// [`AmpFailure::Os`] with Python's text when a captured artifact cannot be
/// read; [`AmpFailure::Refused`] with Python's text for the first defect of
/// the receipt, the artifacts, the preparation, the identities, a snapshot,
/// the image receipt, the logger completion, the run configuration or the
/// captured streams.
pub fn admitted_capture(output: &Path, content: &[u8]) -> Result<Map<String, Value>, AmpFailure> {
    let (capture, orders) = capture_receipt(content)?;
    let (preparation, _) = load_document(output, "image/preparation.json")?;
    let count = image_dependency_record_count(&preparation)?;
    let files = capture["files"].as_object().expect("schema-checked files");
    let precompile = (0..count).map(|index| format!("image/precompile/input_{index}.d"));
    if !REQUIRED
        .iter()
        .map(|name| (*name).to_owned())
        .chain(precompile)
        .all(|name| files.contains_key(&name))
    {
        return refused("AMP capture lacks required original artifact identities");
    }
    check_artifacts(output, files, &orders[&vec!["files".to_owned()]])?;
    let (command, _) = load_document(output, "command.json")?;
    let (image, _) = load_document(output, "image/image.json")?;
    let toolchain = member(&preparation, "toolchain");
    if !COMPILER.locations(toolchain).is_empty() {
        return refused("AMP captured original compiler identity is invalid");
    }
    check_preparation(output, &preparation, files, count)?;
    check_identities(&capture, &command, &image, &preparation)?;
    admit_contents(output, &capture, &image, &preparation)?;
    Ok(capture)
}

/// The snapshots, the image receipt, the completion, the configuration and
/// the captured streams, in Python's order.
fn admit_contents(
    output: &Path,
    capture: &Map<String, Value>,
    image: &Map<String, Value>,
    preparation: &Map<String, Value>,
) -> Result<(), AmpFailure> {
    let refusal = AmpFailure::Refused;
    let read = |name: &str| file_bytes(&pure(&output.join(name)));
    validate_runtime_snapshot(output, &capture["runtime"]["runtime_libraries"])?;
    let libraries = &member(preparation, "toolchain")["runtime_libraries"];
    validate_runtime_snapshot(&output.join("image"), libraries)?;
    let dependencies = member(preparation, "compiler_dependencies");
    validate_image_dependency_snapshot(&output.join("image"), dependencies)?;
    validate_image_receipt(&output.join("image"), image, preparation)?;
    let completion = completion_receipt(&read("spike.log")?).map_err(refusal)?;
    let declared = decode_completion(&canonical_json(&capture["completion"])).map_err(refusal)?;
    if completion != declared {
        return refused("AMP capture completion differs from the actual logger");
    }
    let plugin = capture["tools"]["plugin"]
        .as_str()
        .expect("schema-checked digest");
    validate_plugin_snapshot(output, plugin, completion.thermal)?;
    let run = read_amp_run(&read("image/configuration.txt")?).map_err(refusal)?;
    let (events, tracking) = (read("events.bin")?, read("tracking_raw.csv")?);
    let domain = read("measurement-domain.json")?;
    validate_capture(&completion, &events, &tracking, &domain, run.cycles).map_err(refusal)
}
