// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — failing locations of the committed JSON Schemas

//! Report the document locations that break a committed Draft 2020-12 schema.
//!
//! The Python analysis validates with `jsonschema` and reports only failing
//! locations, never the validator's wording. This interpreter implements the
//! keywords the run and measurement-domain schemas use, with the same
//! applicability and equality rules, and reports the same locations: each
//! distinct location once, sorted by its path parts as strings. A keyword
//! outside the supported set is refused when the schema is loaded.
//!
//! Where an error is reported follows `jsonschema`: a failing `anyOf`, `oneOf` or
//! `not`, an unexpected member and a failing `propertyNames` are reported at the
//! object or value that holds them; `properties`, `items` and an
//! `additionalProperties` schema report at the member or item; `if` selects
//! `then` or `else` without reporting its own errors.

use crate::control_pattern::Pattern;
use serde_json::{Map, Number, Value};
use std::cmp::Ordering;
use std::collections::BTreeMap;

/// Keywords that only annotate and never fail.
const ANNOTATIONS: &[&str] = &[
    "$schema",
    "$id",
    "$defs",
    "$comment",
    "title",
    "description",
    "format",
    "default",
    "examples",
];

/// Keywords whose value is one subschema.
const SINGLE: &[&str] = &[
    "additionalProperties",
    "items",
    "propertyNames",
    "if",
    "then",
    "else",
    "not",
];

/// Keywords whose value is an array of subschemas.
const LISTS: &[&str] = &["allOf", "anyOf", "oneOf"];

/// Keywords whose value is checked directly against the instance.
const ASSERTIONS: &[&str] = &[
    "type",
    "enum",
    "const",
    "pattern",
    "minLength",
    "minimum",
    "maximum",
    "minItems",
    "uniqueItems",
    "required",
    "minProperties",
    "dependentRequired",
    "properties",
    "$ref",
];

/// A loaded schema with its compiled patterns.
pub(crate) struct Schema {
    root: Value,
    patterns: BTreeMap<String, Pattern>,
}

/// An exact numeric value as `jsonschema` compares it.
#[derive(Clone, Copy)]
enum Numeric {
    Integer(i128),
    Float(f64),
}

impl Schema {
    /// Load one committed schema, refusing any keyword or pattern outside the subset.
    pub(crate) fn load(text: &str) -> Result<Self, String> {
        let root: Value =
            serde_json::from_str(text).map_err(|_| "Unsupported schema document.".to_owned())?;
        let mut patterns = BTreeMap::new();
        audit(&root, &mut patterns)?;
        Ok(Self { root, patterns })
    }

    /// Return every failing location once, in path order; empty when the instance is valid.
    pub(crate) fn locations(&self, instance: &Value) -> Vec<String> {
        let mut errors = Vec::new();
        self.check(&self.root, instance, &mut Vec::new(), &mut errors);
        errors.sort();
        let mut locations: Vec<String> = Vec::new();
        for path in errors {
            let location = if path.is_empty() {
                "(root)".to_owned()
            } else {
                path.join("/")
            };
            if !locations.contains(&location) {
                locations.push(location);
            }
        }
        locations
    }

    /// Tell whether the instance satisfies one subschema.
    fn valid(&self, schema: &Value, instance: &Value) -> bool {
        let mut errors = Vec::new();
        self.check(schema, instance, &mut Vec::new(), &mut errors);
        errors.is_empty()
    }

    /// Record the path of every failing keyword of one subschema.
    fn check(
        &self,
        schema: &Value,
        instance: &Value,
        path: &mut Vec<String>,
        errors: &mut Vec<Vec<String>>,
    ) {
        let keywords = match schema {
            Value::Object(keywords) => keywords,
            Value::Bool(true) => return,
            _ => {
                errors.push(path.clone());
                return;
            }
        };
        for (keyword, value) in keywords {
            match keyword.as_str() {
                "properties" => self.properties(value, instance, path, errors),
                "additionalProperties" => self.additional(keywords, value, instance, path, errors),
                "items" => self.items(value, instance, path, errors),
                "propertyNames" => {
                    if let Value::Object(object) = instance
                        && object
                            .keys()
                            .any(|name| !self.valid(value, &Value::String(name.clone())))
                    {
                        errors.push(path.clone());
                    }
                }
                "$ref" => self.check(self.target(value), instance, path, errors),
                "allOf" => {
                    for item in list(value) {
                        self.check(item, instance, path, errors);
                    }
                }
                "anyOf" => {
                    if !list(value).iter().any(|item| self.valid(item, instance)) {
                        errors.push(path.clone());
                    }
                }
                "oneOf" => {
                    if list(value)
                        .iter()
                        .filter(|item| self.valid(item, instance))
                        .count()
                        != 1
                    {
                        errors.push(path.clone());
                    }
                }
                "not" => {
                    if self.valid(value, instance) {
                        errors.push(path.clone());
                    }
                }
                "if" => {
                    let branch = if self.valid(value, instance) {
                        "then"
                    } else {
                        "else"
                    };
                    if let Some(selected) = keywords.get(branch) {
                        self.check(selected, instance, path, errors);
                    }
                }
                "then" | "else" => {}
                _ if ANNOTATIONS.contains(&keyword.as_str()) => {}
                _ => {
                    if !self.holds(keyword, value, instance) {
                        errors.push(path.clone());
                    }
                }
            }
        }
    }

    /// Check one member schema for each declared member that is present.
    fn properties(
        &self,
        value: &Value,
        instance: &Value,
        path: &mut Vec<String>,
        errors: &mut Vec<Vec<String>>,
    ) {
        if let (Value::Object(schemas), Value::Object(object)) = (value, instance) {
            for (name, schema) in schemas {
                if let Some(member) = object.get(name) {
                    self.descend(schema, member, name.clone(), path, errors);
                }
            }
        }
    }

    /// Refuse or check every member that `properties` does not declare.
    fn additional(
        &self,
        keywords: &Map<String, Value>,
        value: &Value,
        instance: &Value,
        path: &mut Vec<String>,
        errors: &mut Vec<Vec<String>>,
    ) {
        let Value::Object(object) = instance else {
            return;
        };
        let declared = keywords.get("properties").and_then(Value::as_object);
        for (name, member) in object {
            if !declared.is_some_and(|declared| declared.contains_key(name)) {
                self.descend(value, member, name.clone(), path, errors);
            }
        }
    }

    /// Check every array item against one schema.
    fn items(
        &self,
        value: &Value,
        instance: &Value,
        path: &mut Vec<String>,
        errors: &mut Vec<Vec<String>>,
    ) {
        if let Value::Array(items) = instance {
            for (index, item) in items.iter().enumerate() {
                self.descend(value, item, index.to_string(), path, errors);
            }
        }
    }

    /// Check a member or item at its own location.
    ///
    /// As in `jsonschema`, a `false` subschema reached this way is reported at
    /// the holding value, without the member or item part of the path.
    fn descend(
        &self,
        schema: &Value,
        instance: &Value,
        part: String,
        path: &mut Vec<String>,
        errors: &mut Vec<Vec<String>>,
    ) {
        if schema == &Value::Bool(false) {
            errors.push(path.clone());
            return;
        }
        path.push(part);
        self.check(schema, instance, path, errors);
        path.pop();
    }

    /// Resolve one local JSON Pointer reference audited at load time.
    fn target(&self, reference: &Value) -> &Value {
        resolve(&self.root, reference).expect("references are resolved when the schema is loaded")
    }

    /// Tell whether one assertion keyword holds for the instance.
    fn holds(&self, keyword: &str, value: &Value, instance: &Value) -> bool {
        match keyword {
            "type" => match value {
                Value::String(name) => has_type(instance, name),
                _ => list(value)
                    .iter()
                    .any(|name| has_type(instance, name.as_str().unwrap_or_default())),
            },
            "enum" => list(value).iter().any(|item| equal(item, instance)),
            "const" => equal(value, instance),
            "pattern" => instance
                .as_str()
                .is_none_or(|text| self.patterns[value.as_str().unwrap_or_default()].search(text)),
            "minLength" => instance
                .as_str()
                .is_none_or(|text| !below(text.chars().count(), value)),
            "minItems" => instance
                .as_array()
                .is_none_or(|items| !below(items.len(), value)),
            "minProperties" => instance
                .as_object()
                .is_none_or(|object| !below(object.len(), value)),
            "minimum" => number(instance)
                .is_none_or(|actual| compare(actual, numeric(value)) != Ordering::Less),
            "maximum" => number(instance)
                .is_none_or(|actual| compare(actual, numeric(value)) != Ordering::Greater),
            "uniqueItems" => match instance {
                Value::Array(items) if value == &Value::Bool(true) => {
                    items.iter().enumerate().all(|(index, item)| {
                        items[..index].iter().all(|earlier| !equal(earlier, item))
                    })
                }
                _ => true,
            },
            "required" => instance.as_object().is_none_or(|object| {
                list(value)
                    .iter()
                    .all(|name| object.contains_key(name.as_str().unwrap_or_default()))
            }),
            _ => instance.as_object().is_none_or(|object| {
                value
                    .as_object()
                    .into_iter()
                    .flatten()
                    .all(|(name, needed)| {
                        !object.contains_key(name)
                            || list(needed).iter().all(|other| {
                                object.contains_key(other.as_str().unwrap_or_default())
                            })
                    })
            }),
        }
    }
}

/// Tell whether a count is below an integer bound.
fn below(count: usize, bound: &Value) -> bool {
    compare(Numeric::Integer(count as i128), numeric(bound)) == Ordering::Less
}

/// The array of a list keyword; audited as an array at load time.
fn list(value: &Value) -> &[Value] {
    value.as_array().map_or(&[], Vec::as_slice)
}

/// Follow a `#/…` JSON Pointer inside the schema document.
fn resolve<'a>(root: &'a Value, reference: &Value) -> Option<&'a Value> {
    let pointer = reference.as_str()?.strip_prefix('#')?;
    root.pointer(pointer)
}

/// Check every subschema for supported keywords, resolvable references and patterns.
fn audit(root: &Value, patterns: &mut BTreeMap<String, Pattern>) -> Result<(), String> {
    let mut pending = vec![root];
    while let Some(schema) = pending.pop() {
        let keywords = match schema {
            Value::Object(keywords) => keywords,
            Value::Bool(_) => continue,
            _ => return Err("Unsupported schema document.".to_owned()),
        };
        for (keyword, value) in keywords {
            let name = keyword.as_str();
            if SINGLE.contains(&name) {
                pending.push(value);
            } else if LISTS.contains(&name) {
                pending.extend(value.as_array().ok_or_else(|| unsupported(name))?);
            } else if name == "properties" || name == "$defs" {
                pending.extend(value.as_object().ok_or_else(|| unsupported(name))?.values());
            } else if name == "$ref" {
                resolve(root, value).ok_or_else(|| unsupported(name))?;
            } else if name == "pattern" {
                let text = value.as_str().ok_or_else(|| unsupported(name))?;
                patterns.insert(text.to_owned(), Pattern::compile(text)?);
            } else if !ASSERTIONS.contains(&name) && !ANNOTATIONS.contains(&name) {
                return Err(unsupported(name));
            }
        }
    }
    Ok(())
}

/// The refusal for an unsupported keyword or malformed keyword value.
fn unsupported(keyword: &str) -> String {
    format!("Unsupported schema keyword {keyword}.")
}

/// Tell whether a value has one JSON Schema type, as `jsonschema` decides it.
fn has_type(instance: &Value, name: &str) -> bool {
    match name {
        "null" => instance.is_null(),
        "boolean" => instance.is_boolean(),
        "string" => instance.is_string(),
        "array" => instance.is_array(),
        "object" => instance.is_object(),
        "number" => instance.is_number(),
        "integer" => number(instance).is_some_and(|value| match value {
            Numeric::Integer(_) => true,
            Numeric::Float(float) => float.fract() == 0.0,
        }),
        _ => false,
    }
}

/// The exact numeric value of a JSON number; booleans are not numbers.
fn number(instance: &Value) -> Option<Numeric> {
    instance.as_number().map(from_number)
}

/// Convert a schema number, audited as numeric by the committed schemas.
fn numeric(value: &Value) -> Numeric {
    value
        .as_number()
        .map_or(Numeric::Float(f64::NAN), from_number)
}

/// Keep integers exact and floats as decoded.
fn from_number(number: &Number) -> Numeric {
    if let Some(integer) = number.as_i64() {
        Numeric::Integer(i128::from(integer))
    } else if let Some(integer) = number.as_u64() {
        Numeric::Integer(i128::from(integer))
    } else {
        Numeric::Float(number.as_f64().unwrap_or(f64::NAN))
    }
}

/// Compare two numbers exactly, as Python compares an int with a float.
fn compare(left: Numeric, right: Numeric) -> Ordering {
    match (left, right) {
        (Numeric::Integer(left), Numeric::Integer(right)) => left.cmp(&right),
        (Numeric::Float(left), Numeric::Float(right)) => {
            left.partial_cmp(&right).unwrap_or(Ordering::Equal)
        }
        (Numeric::Float(float), Numeric::Integer(integer)) => float_against(float, integer),
        (Numeric::Integer(integer), Numeric::Float(float)) => {
            float_against(float, integer).reverse()
        }
    }
}

/// Compare a finite float with an integer without rounding the integer.
fn float_against(float: f64, integer: i128) -> Ordering {
    let floor = float.floor();
    if floor < -1.0e38 {
        return Ordering::Less;
    }
    if floor > 1.0e38 {
        return Ordering::Greater;
    }
    match (floor as i128).cmp(&integer) {
        Ordering::Equal if float > floor => Ordering::Greater,
        ordering => ordering,
    }
}

/// Compare two values as `jsonschema` does: `1 == 1.0`, but a boolean is never a number.
fn equal(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Number(left), Value::Number(right)) => {
            compare(from_number(left), from_number(right)) == Ordering::Equal
        }
        (Value::Array(left), Value::Array(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|(left, right)| equal(left, right))
        }
        (Value::Object(left), Value::Object(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .all(|(name, value)| right.get(name).is_some_and(|other| equal(value, other)))
        }
        _ => left == right,
    }
}

#[cfg(test)]
#[path = "../tests/unit/control_schema.rs"]
mod tests;
