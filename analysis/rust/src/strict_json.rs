// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — JSON objects without repeated member names

//! Decode an open JSON object while refusing repeated member names at every depth.
//!
//! Typed records already refuse repeated fields. A document checked field by
//! field, in the order the Python verifier uses, is first decoded through this
//! value so that both languages refuse the same repeated names.

use crate::files::decode;
use serde::de::{Deserialize, Deserializer, Error, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};
use std::fmt;

/// JSON value whose objects reject repeated member names.
struct Strict(Value);

impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(StrictVisitor).map(Strict)
    }
}

/// Build plain values, refusing a repeated name inside one object.
struct StrictVisitor;

impl<'de> Visitor<'de> for StrictVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_bool<E: Error>(self, value: bool) -> Result<Value, E> {
        Ok(Value::Bool(value))
    }

    fn visit_i64<E: Error>(self, value: i64) -> Result<Value, E> {
        Ok(Value::from(value))
    }

    fn visit_u64<E: Error>(self, value: u64) -> Result<Value, E> {
        Ok(Value::from(value))
    }

    fn visit_f64<E: Error>(self, value: f64) -> Result<Value, E> {
        Ok(Number::from_f64(value).map_or(Value::Null, Value::Number))
    }

    fn visit_str<E: Error>(self, value: &str) -> Result<Value, E> {
        Ok(Value::String(value.to_owned()))
    }

    fn visit_unit<E: Error>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }

    fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Value, A::Error> {
        let mut items = Vec::new();
        while let Some(Strict(item)) = sequence.next_element()? {
            items.push(item);
        }
        Ok(Value::Array(items))
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Value, A::Error> {
        let mut object = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            let Strict(value) = map.next_value()?;
            if object.insert(key, value).is_some() {
                return Err(A::Error::custom("repeated JSON member name"));
            }
        }
        Ok(Value::Object(object))
    }
}

/// Decode one top-level JSON object; any other document is the named refusal.
pub(crate) fn decode_object(raw: &[u8], name: &str) -> Result<Map<String, Value>, String> {
    match decode::<Strict>(raw, name)?.0 {
        Value::Object(object) => Ok(object),
        _ => Err(format!("Invalid original {name}.")),
    }
}
