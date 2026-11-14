// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP plugin build receipts and their preparation identities

//! Decode an AMP plugin build receipt as the Python module
//! `amp_plugin_receipt` does.
//!
//! [`decode_plugin_receipt`] decodes the receipt under the bounded JSON rules,
//! refuses the first location that breaks the committed plugin build schema,
//! and requires the receipt to agree with the preparation it binds: every
//! identity but the sources equal to the receipt's own, every preparation and
//! compiler identity in the receipt's dependencies, and the preparation and
//! its generation record bound by digest. Every refusal is Python's text.
//!
//! [`decode_plugin_receipt`]: crate::amp_plugin_receipt::decode_plugin_receipt

use crate::amp_failure::AmpFailure;
use crate::control_json::decode_object;
use crate::control_json_text::canonical_json;
use crate::control_paths::parent_and_name;
use crate::control_receipts::python_equal;
use crate::control_schema::Schema;
use crate::control_text::python_display;
use crate::files::digest;
use serde_json::{Map, Value};
use std::path::Path;
use std::sync::LazyLock;

/// The plugin build receipt schema, a copy of the repository's, committed beside the crate.
static SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../amp-plugin-build.schema.json")).expect("committed schema")
});

/// Decode one complete plugin build receipt and check it against its preparation.
///
/// # Errors
///
/// [`AmpFailure::Refused`] with Python's text when the bytes break the bounded
/// JSON rules or the schema, or the receipt omits or contradicts the identities
/// of its preparation.
pub fn decode_plugin_receipt(content: &[u8]) -> Result<Map<String, Value>, AmpFailure> {
    let (data, _) = decode_object(content, "AMP plugin build").map_err(AmpFailure::Refused)?;
    if let Some(location) = SCHEMA.locations(&Value::Object(data.clone())).first() {
        return Err(AmpFailure::Refused(format!(
            "AMP plugin build receipt {location}: does not satisfy the AMP plugin build schema"
        )));
    }
    if contradicts(&data) {
        let text = "AMP plugin receipt omits or contradicts original preparation identities";
        return Err(AmpFailure::Refused(text.into()));
    }
    Ok(data)
}

/// Tell whether a schema-valid receipt contradicts its preparation, checked in
/// Python's order: identities, then every group of names, then the digests of
/// the preparation and, beside it, its generation record.
fn contradicts(data: &Map<String, Value>) -> bool {
    let preparation = &data["preparation"];
    let identity = preparation["identity"]
        .as_object()
        .expect("schema-checked identity");
    let dependencies = &data["dependencies"];
    let mut groups = vec![&identity["sources"], &identity["runtime_libraries"]];
    let compilers = identity["compilers"]
        .as_object()
        .expect("schema-checked compilers");
    groups.extend(
        compilers
            .values()
            .map(|compiler| &compiler["runtime_libraries"]),
    );
    groups.extend(
        ["dependencies", "dependency_records", "build_files"].map(|name| &preparation[name]),
    );
    let named = |name: &str| dependencies.get(name).unwrap_or(&Value::Null);
    let path = data["preparation_path"]
        .as_str()
        .expect("schema-checked path");
    let (parent, name) = parent_and_name(Path::new(path));
    identity
        .iter()
        .any(|(name, value)| name != "sources" && !python_equal(value, &data[name]))
        || groups
            .iter()
            .flat_map(|group| group.as_object().expect("schema-checked group"))
            .any(|(name, value)| !python_equal(named(name), value))
        || !python_equal(
            named(path),
            &Value::String(digest(&canonical_json(preparation))),
        )
        || name.is_empty()
        || !python_equal(
            named(&python_display(&parent.join("generation.json"))),
            &preparation["generation_sha256"],
        )
}
