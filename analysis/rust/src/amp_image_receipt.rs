// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — captured image declarations against topology and executable bytes

//! Check an AMP image's receipt as the Python module `amp_image_receipt`
//! does.
//!
//! [`validate_image_receipt`] holds the image's declarations to its
//! preparation, checks the Rust kernel receipt, reads the verification
//! request the image recorded without running it, binds the captured
//! platform, reads the run configuration, admits the firmware's contract and
//! ISA exit channel, and requires the image's declared platform, run, stack
//! and segments to equal what was admitted, with Python's equality. Every
//! refusal and read error is Python's, met in Python's order.
//!
//! [`validate_image_receipt`]: crate::amp_image_receipt::validate_image_receipt

use crate::amp_elf::LoadSegment;
use crate::amp_exit_channel::admit_exit_channel;
use crate::amp_failure::AmpFailure;
use crate::amp_files::{file_bytes, load_document};
use crate::amp_image_contract::admit_image_contract;
use crate::amp_platform::{AmpPlatform, MemorySelection, bind_platform};
use crate::amp_run_input::{AmpRun, read_amp_run};
use crate::amp_rust_receipt::{member, validate_rust_image_receipt};
use crate::control_paths::pure;
use crate::control_receipts::python_equal;
use crate::device_tree::{PlicBinding, PlicSelection, Region, decode_device_tree};
use serde_json::{Map, Value, json};
use std::path::Path;

/// The options of a recorded verification vector, in their only order.
const OPTIONS: [&str; 11] = [
    "--dtb",
    "--configuration",
    "--ram-node",
    "--firmware-node",
    "--telemetry-node",
    "--device-node",
    "--plic-node",
    "--plic-layout",
    "--hart",
    "--interrupt",
    "--stack-bytes",
];
/// The words after the interpreter: the verifier and its directory.
const PREFIX: [&str; 3] = ["source/tools/verify_amp_image.py", "--directory", "."];
/// The telemetry mailbox an image requests.
const MAILBOX_BYTES: i128 = 16496;
/// The longest canonical signed 64-bit decimal: a sign and 19 digits.
const MAX_INTEGER_TEXT: usize = 20;

/// A refusal with Python's text.
fn refused<T>(text: &str) -> Result<T, AmpFailure> {
    Err(AmpFailure::Refused(text.into()))
}

/// Python's `ImageRequest` with the layout name as recorded.
struct Request {
    memory: MemorySelection,
    plic: PlicSelection,
    device_path: String,
    layout: String,
}

/// Python's `_recorded_integer`: one canonical decimal within the signed 64-bit range.
fn recorded_integer(text: &str) -> Result<i128, AmpFailure> {
    let digits = text.strip_prefix('-').unwrap_or(text);
    let canonical = text == "0"
        || (digits.starts_with(|first: char| ('1'..='9').contains(&first))
            && digits.bytes().all(|byte| byte.is_ascii_digit()));
    match text.parse::<i128>() {
        Ok(value)
            if text.len() <= MAX_INTEGER_TEXT
                && canonical
                && (i128::from(i64::MIN)..=i128::from(i64::MAX)).contains(&value) =>
        {
            Ok(value)
        }
        _ => refused("AMP original image verification arguments disagree"),
    }
}

/// Python's `verification_arguments`: the request as the vector records it.
fn verification_arguments(request: &Request) -> Vec<String> {
    let values = [
        "platform.dtb".to_owned(),
        "configuration.txt".to_owned(),
        request.memory.ram_path.clone(),
        request.memory.firmware_path.clone(),
        request.memory.shared_path.clone(),
        request.device_path.clone(),
        request.plic.path.clone(),
        request.layout.clone(),
        request.plic.hart.to_string(),
        request.plic.source.to_string(),
        request.memory.stack_bytes.to_string(),
    ];
    OPTIONS
        .iter()
        .zip(values)
        .flat_map(|(option, value)| [(*option).to_owned(), value])
        .collect()
}

/// The layout a recorded name selects; Python refuses another name only
/// when the binding is checked.
fn binding(layout: &str) -> PlicBinding {
    match layout {
        "sifive" => PlicBinding::Sifive,
        "spike" => PlicBinding::Spike,
        _ => PlicBinding::Unbound,
    }
}

/// Python's `recorded_request`: the verification selection the image
/// recorded, decoded without running its command.
fn recorded_request(directory: &Path) -> Result<Request, AmpFailure> {
    let (document, _) = load_document(directory, "build_commands.json")?;
    let words: Option<Vec<&str>> = member(&document, "verify")
        .as_array()
        .and_then(|items| items.iter().map(Value::as_str).collect());
    let Some(words) = words.filter(|words| {
        words.len() == 1 + PREFIX.len() + 2 * OPTIONS.len()
            && words[0].starts_with('/')
            && words[1..=PREFIX.len()] == PREFIX
            && words[4..].iter().step_by(2).eq(OPTIONS.iter())
    }) else {
        return refused("AMP original image verification vector is invalid");
    };
    let value = |option: &str| {
        let index = OPTIONS
            .iter()
            .position(|name| *name == option)
            .expect("an option");
        words[5 + 2 * index].to_owned()
    };
    let stack_bytes = recorded_integer(&value("--stack-bytes"))?;
    let hart = recorded_integer(&value("--hart"))?;
    let source = recorded_integer(&value("--interrupt"))?;
    let layout = value("--plic-layout");
    let request = Request {
        memory: MemorySelection {
            ram_path: value("--ram-node"),
            firmware_path: value("--firmware-node"),
            shared_path: value("--telemetry-node"),
            mailbox_bytes: MAILBOX_BYTES,
            stack_bytes,
        },
        plic: PlicSelection {
            path: value("--plic-node"),
            hart,
            source,
            binding: binding(&layout),
        },
        device_path: value("--device-node"),
        layout,
    };
    if words[4..] != verification_arguments(&request) {
        return refused("AMP original image verification arguments disagree");
    }
    Ok(request)
}

/// The image and preparation declarations of an ISA image built with the
/// compiler its preparation names.
fn check_declarations(
    image: &Map<String, Value>,
    preparation: &Map<String, Value>,
) -> Result<(), AmpFailure> {
    let driver = &member(preparation, "toolchain")["driver"];
    let inputs = member(preparation, "inputs");
    let mut declared = Map::new();
    declared.insert(
        "compiler".into(),
        member(preparation, "compiler_sha256").clone(),
    );
    declared.extend(inputs.as_object().cloned().unwrap_or_default());
    if !python_equal(
        member(preparation, "schema"),
        &json!("loop-timing-witness.amp-image-preparation.v1"),
    ) || *member(preparation, "isa") != Value::Bool(true)
        || !python_equal(member(preparation, "compiler"), &driver["path"])
        || !python_equal(member(preparation, "compiler_sha256"), &driver["sha256"])
        || inputs.get("compiler").is_some()
        || !python_equal(member(image, "inputs"), &Value::Object(declared))
        || !python_equal(
            member(image, "schema"),
            &json!("loop-timing-witness.amp-image.v1"),
        )
        || *member(image, "simulation_only") != Value::Bool(true)
        || *member(image, "physical_verified") != Value::Bool(false)
        || !python_equal(member(image, "exit_mode"), &json!("isa_htif"))
    {
        return refused("AMP original image preparation or mode declarations disagree");
    }
    Ok(())
}

/// A value of an admitted platform, which lies below 2^64.
fn word(value: u128) -> u64 {
    u64::try_from(value).expect("an admitted RV64 value")
}

/// An extent as `dataclasses.asdict` writes it.
fn region(extent: Region) -> Value {
    json!({"address": word(extent.address), "size": word(extent.size)})
}

/// The platform as `dataclasses.asdict` writes it.
fn platform_document(platform: &AmpPlatform) -> Value {
    let plic = platform.device.plic;
    json!({
        "memory": {
            "firmware": region(platform.memory.firmware),
            "shared": region(platform.memory.shared),
        },
        "device": {
            "aperture": region(platform.device.aperture),
            "plic": {
                "context": plic.context,
                "priority": word(plic.priority),
                "enable_word": word(plic.enable_word),
                "threshold": word(plic.threshold),
                "claim": word(plic.claim),
            },
        },
        "hart": i64::try_from(platform.hart).expect("an admitted hart"),
        "source": i64::try_from(platform.source).expect("an admitted source"),
    })
}

/// The run as the image declares it: `asdict` with the coefficients as a list.
fn run_document(run: &AmpRun) -> Value {
    json!({
        "cycles": run.cycles,
        "period_ticks": run.period_ticks,
        "lqr": u32::from(run.lqr),
        "overload_iterations": run.overload_iterations,
        "coefficients": run.coefficients,
    })
}

/// The segments as `dataclasses.asdict` writes them.
fn segment_documents(segments: &[LoadSegment]) -> Value {
    segments
        .iter()
        .map(|segment| {
            json!({
                "offset": segment.offset,
                "address": segment.address,
                "file_bytes": segment.file_bytes,
                "memory_bytes": segment.memory_bytes,
                "flags": segment.flags,
            })
        })
        .collect()
}

/// Check an image's declarations against its preparation, recorded request,
/// platform, run configuration and firmware.
///
/// `image` is the decoded `image.json` and `preparation` the decoded
/// `preparation.json` of the image in `directory`, as the capture admission
/// passes them: the preparation's compiler identity already satisfies the
/// compiler schema and its inputs are a non-empty object. Outside that
/// domain Python raises `KeyError` or `TypeError`; this function refuses with
/// the declarations text instead.
///
/// # Errors
///
/// [`AmpFailure::Os`] with Python's text when a captured file cannot be read;
/// [`AmpFailure::Refused`] with Python's text for the first defect of the
/// declarations, the Rust kernel receipt, the recorded vector, the platform,
/// the run, the firmware contract, the exit channel, or the declared platform,
/// run, stack and segments.
///
/// # Panics
///
/// Never for an admitted platform: its addresses lie below 2^64 and its hart
/// and source are small.
pub fn validate_image_receipt(
    directory: &Path,
    image: &Map<String, Value>,
    preparation: &Map<String, Value>,
) -> Result<(), AmpFailure> {
    check_declarations(image, preparation)?;
    validate_rust_image_receipt(directory, image, preparation)?;
    let request = recorded_request(directory)?;
    let read = |name: &str| file_bytes(&pure(&directory.join(name)));
    let tree = decode_device_tree(&read("platform.dtb")?).map_err(AmpFailure::Refused)?;
    let platform = bind_platform(&tree, &request.memory, &request.device_path, &request.plic)
        .map_err(AmpFailure::Refused)?;
    let run = read_amp_run(&read("configuration.txt")?).map_err(AmpFailure::Refused)?;
    let content = read("firmware.elf")?;
    let segments = admit_image_contract(&content, &platform, &run, request.memory.stack_bytes)
        .map_err(AmpFailure::Refused)?;
    admit_exit_channel(&content, &segments).map_err(AmpFailure::Refused)?;
    let stack = i64::try_from(request.memory.stack_bytes).expect("a recorded 64-bit stack");
    let admitted = [
        ("platform", platform_document(&platform)),
        ("run", run_document(&run)),
        ("stack_bytes", json!(stack)),
        ("segments", segment_documents(&segments)),
    ];
    if admitted
        .iter()
        .any(|(name, value)| !python_equal(member(image, name), value))
    {
        return refused(
            "AMP original image declarations differ from captured topology or firmware",
        );
    }
    Ok(())
}

#[cfg(test)]
#[path = "../tests/unit/amp_image_receipt.rs"]
mod tests;
