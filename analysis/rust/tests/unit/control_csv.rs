// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python csv reading, crate-internal controls

//! Hold the CSV reader to Python's `csv.reader` for the shared corpus.
//!
//! `tests/test_control_series_corpus.py` builds the corpus from Python and
//! requires the committed file to equal it; these tests require the same
//! records and the same stopping error here.

use super::{DictRows, Records, Row};
use crate::control_json::decode_object;
use serde_json::Value;

/// The shared corpus of CSV texts, records and errors.
const CORPUS: &str = include_str!("../data/control-csv-cases.json");

/// Expand a corpus string written as a run of one repeated character.
fn unpacked(value: &Value) -> Value {
    match value {
        Value::Object(map) if map.contains_key("repeat") => {
            let run = map["repeat"]
                .as_str()
                .expect("repeat")
                .repeat(usize::try_from(map["count"].as_u64().expect("count")).expect("count"));
            Value::String(format!(
                "{}{run}{}",
                map["prefix"].as_str().expect("prefix"),
                map["suffix"].as_str().expect("suffix")
            ))
        }
        Value::Object(map) => Value::Object(
            map.iter()
                .map(|(key, item)| (key.clone(), unpacked(item)))
                .collect(),
        ),
        Value::Array(items) => Value::Array(items.iter().map(unpacked).collect()),
        other => other.clone(),
    }
}

#[test]
fn every_corpus_text_reads_as_python_reads_it() {
    let (corpus, _) = decode_object(CORPUS.as_bytes(), "corpus").expect("corpus");
    let cases = corpus["cases"].as_array().expect("cases");
    assert!(cases.len() > 20);
    for case in cases {
        let case = unpacked(case);
        let text = case["text"].as_str().expect("text");
        let mut records = Vec::new();
        let mut error = Value::Null;
        for record in Records::new(text) {
            match record {
                Ok(fields) => records.push(Value::from(fields)),
                Err(message) => {
                    error = Value::String(message);
                    break;
                }
            }
        }
        assert_eq!(Value::Array(records), case["records"], "{text:?}");
        assert_eq!(error, case["error"], "{text:?}");
    }
}

#[test]
fn dict_rows_skip_empty_records_and_mark_incomplete_rows() {
    let (header, rows) = DictRows::new("a,b\n\n1,2\n1\n1,2,3\n1,\n").expect("header");
    assert_eq!(header, Some(vec!["a".to_owned(), "b".to_owned()]));
    let rows: Vec<Row> = rows.collect::<Result<_, _>>().expect("rows");
    assert!(matches!(&rows[0], Row::Complete(cells) if cells == &["1", "2"]));
    assert!(rows[1..].iter().all(|row| matches!(row, Row::Incomplete)));
    let (header, mut rows) = DictRows::new("").expect("empty text");
    assert_eq!(header, None);
    assert!(rows.next().is_none());
    assert_eq!(
        DictRows::new("\"").err().as_deref(),
        Some("unexpected end of data")
    );
    let (_, mut rows) = DictRows::new("a\n\"b").expect("header");
    assert_eq!(
        rows.next().and_then(Result::err).as_deref(),
        Some("unexpected end of data")
    );
}
