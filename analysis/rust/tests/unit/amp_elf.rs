// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — firmware ELF readers held to Python's corpus

//! Hold the firmware ELF readers to Python's outcome for every image of the shared corpus.
//!
//! `tests/test_amp_elf_corpus.py` builds the corpus from the two real images
//! it holds and Python's readers and requires the committed file to equal it;
//! these tests require the same segments, symbols and refusals here.

use super::{admit_elf, read_symbols};
use crate::device_tree_resources::Region;
use crate::files::digest;
use crate::unit_files::hex_bytes;
use serde_json::{Map, Value, json};

/// The shared corpus, holding two real images and Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-elf-cases.json");
/// The images in the order the sweep numbers them.
const IMAGES: [&str; 2] = ["linked", "firmware"];

/// A corpus integer as a size or offset.
fn index(value: &Value) -> usize {
    usize::try_from(value.as_u64().expect("integer")).expect("index")
}

/// A corpus `[address, size]` pair as a reservation.
fn reservation(value: &Value) -> Region {
    Region {
        address: u128::from(value[0].as_u64().expect("address")),
        size: u128::from(value[1].as_u64().expect("size")),
    }
}

/// `admit_elf`'s outcome as the corpus writes it, refusals as their text.
fn admission(content: &[u8], reservation: Region) -> Value {
    match admit_elf(content, reservation) {
        Ok(segments) => json!({"segments": segments.iter().map(|segment| json!([
            segment.offset,
            segment.address,
            segment.file_bytes,
            segment.memory_bytes,
            segment.flags,
        ])).collect::<Vec<_>>()}),
        Err(refusal) => json!({"refusal": refusal}),
    }
}

/// `read_symbols`' outcome as the corpus writes it: every symbol, or the digest Python defines.
fn symbols(content: &[u8], whole: bool) -> Value {
    let found = match read_symbols(content) {
        Ok(found) => found,
        Err(refusal) => return json!({"refusal": refusal}),
    };
    if whole {
        let members: Map<String, Value> = found
            .iter()
            .map(|(name, symbol)| {
                let value = json!([symbol.address, symbol.size, symbol.kind, symbol.section]);
                (name.clone(), value)
            })
            .collect();
        return json!({"symbols": members});
    }
    let mut form = Vec::new();
    for (name, symbol) in &found {
        form.extend(u32::try_from(name.len()).expect("length").to_le_bytes());
        form.extend(name.as_bytes());
        form.extend(symbol.address.to_le_bytes());
        form.extend(symbol.size.to_le_bytes());
        form.push(symbol.kind);
        form.extend(symbol.section.to_le_bytes());
    }
    json!({"symbols_sha256": digest(&form)})
}

/// The committed corpus, its images and its refusal texts.
struct Corpus {
    document: Value,
    images: [Vec<u8>; 2],
    texts: Vec<String>,
}

impl Corpus {
    /// Parse the committed corpus and decode its images, requiring their recorded digests.
    fn load() -> Self {
        let document: Value = serde_json::from_str(CORPUS).expect("corpus");
        assert_eq!(document["schema"], "loop-timing-witness.amp-elf-cases.v1");
        let images = IMAGES.map(|name| {
            let image = hex_bytes(document["images"][name]["hex"].as_str().expect("hex"));
            assert_eq!(document["images"][name]["sha256"], digest(&image), "{name}");
            image
        });
        let texts = document["texts"]
            .as_array()
            .expect("texts")
            .iter()
            .map(|text| text.as_str().expect("text").to_owned())
            .collect();
        Self {
            document,
            images,
            texts,
        }
    }

    /// The image a corpus name selects.
    fn image(&self, name: &str) -> &[u8] {
        let position = IMAGES.iter().position(|known| *known == name);
        &self.images[position.expect("known image")]
    }

    /// Replace every refusal index of an expected value by its text.
    fn with_texts(&self, value: &Value) -> Value {
        match value {
            Value::Object(members) => Value::Object(
                members
                    .iter()
                    .map(|(key, item)| {
                        let item = match item.as_u64().filter(|_| key == "refusal") {
                            Some(number) => Value::from(
                                self.texts[usize::try_from(number).expect("index")].as_str(),
                            ),
                            None => self.with_texts(item),
                        };
                        (key.clone(), item)
                    })
                    .collect(),
            ),
            Value::Array(items) => {
                Value::Array(items.iter().map(|item| self.with_texts(item)).collect())
            }
            other => other.clone(),
        }
    }
}

#[test]
fn both_real_images_admit_and_read_as_python() {
    let corpus = Corpus::load();
    let ram = reservation(&corpus.document["reservation"]);
    for name in IMAGES {
        let expected = corpus.with_texts(&corpus.document["bases"][name]);
        assert_eq!(
            admission(corpus.image(name), ram),
            expected["admit"],
            "{name}"
        );
        assert_eq!(
            symbols(corpus.image(name), true),
            expected["symbols"],
            "{name}"
        );
    }
}

#[test]
fn every_named_case_admits_and_reads_as_python() {
    let corpus = Corpus::load();
    let ram = &corpus.document["reservation"];
    let cases = corpus.document["cases"].as_array().expect("cases");
    assert!(cases.len() > 20);
    for case in cases {
        let case = corpus.with_texts(case);
        let name = case["name"].as_str().expect("name");
        let mut content = corpus
            .image(case["image"].as_str().expect("image"))
            .to_vec();
        for edit in case
            .get("edits")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let change = hex_bytes(edit[1].as_str().expect("hex"));
            let offset = index(&edit[0]);
            content[offset..offset + change.len()].copy_from_slice(&change);
        }
        if let Some(length) = case.get("length") {
            content.truncate(index(length));
        }
        if let Some(length) = case.get("pad") {
            content.resize(index(length), 0);
        }
        let limits = reservation(case.get("reservation").unwrap_or(ram));
        assert_eq!(admission(&content, limits), case["admit"], "{name}");
        assert_eq!(symbols(&content, false), case["symbols"], "{name}");
    }
}

#[test]
fn every_field_change_admits_and_reads_as_python() {
    let corpus = Corpus::load();
    let ram = reservation(&corpus.document["reservation"]);
    let originals = [0, 1].map(|which| {
        (
            admission(&corpus.images[which], ram),
            symbols(&corpus.images[which], false),
        )
    });
    let rows = corpus.document["sweep"].as_array().expect("sweep");
    assert!(rows.len() > 2000);
    for row in rows {
        let row = corpus.with_texts(row);
        let which = index(&row[0]);
        let (offset, change) = (index(&row[1]), hex_bytes(row[2].as_str().expect("hex")));
        let mut content = corpus.images[which].clone();
        content[offset..offset + change.len()].copy_from_slice(&change);
        let found = [admission(&content, ram), symbols(&content, false)];
        for (position, (outcome, original)) in found
            .iter()
            .zip([&originals[which].0, &originals[which].1])
            .enumerate()
        {
            let expected = &row[3 + position];
            let same = expected.is_null() && outcome == original;
            assert!(
                same || outcome == expected,
                "image {which} at {offset}: {}",
                row[2]
            );
        }
    }
}
