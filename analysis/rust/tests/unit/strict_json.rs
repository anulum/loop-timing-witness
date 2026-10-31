// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — strict JSON value decoder, crate-internal controls

//! Describe the accepted input when a non-JSON source offers another kind of value.
//!
//! JSON documents only reach the implemented visits; a byte buffer is the
//! input serde reports against the visitor's own description.

use super::Strict;
use serde::Deserialize;
use serde::de::value::{BytesDeserializer, Error};

#[test]
fn a_foreign_value_kind_is_described_as_a_json_value() {
    let refused = Strict::deserialize(BytesDeserializer::<Error>::new(b"bytes"))
        .err()
        .expect("bytes are not a JSON value");
    assert_eq!(
        refused.to_string(),
        "invalid type: byte array, expected a JSON value"
    );
}
