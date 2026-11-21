// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — corpus bytes and owned folders of the crate tests

//! Decode the hexadecimal bytes the shared corpora hold, own a folder for
//! corpus file trees, write those trees and their edits, patch documents, and
//! rebuild the stacked random edits of the firmware reader mutation corpus.

use serde_json::{Map, Value};
use std::path::{Path, PathBuf};

/// Decode a hexadecimal byte string of a corpus.
pub(crate) fn hex_bytes(text: &str) -> Vec<u8> {
    (0..text.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&text[index..index + 2], 16).expect("hex"))
        .collect()
}

/// A new folder under the temporary directory, held by its resolved path
/// and removed when dropped.
pub(crate) struct Scratch(pub(crate) PathBuf);

impl Scratch {
    /// Create a new empty folder whose name carries `label`, the process and the clock.
    pub(crate) fn new(label: &str) -> Self {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let name = format!("witness-{label}-{}-{nanos}", std::process::id());
        let path = std::env::temp_dir().join(name);
        std::fs::create_dir(&path).expect("scratch");
        Self(std::fs::canonicalize(&path).expect("resolved scratch"))
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).ok();
    }
}

/// Write one corpus tree entry under a case folder: text with `{root}`
/// replaced by the folder, hexadecimal bytes, a symbolic link (replacing a
/// folder whose files earlier removals took, empty folders left in it) or an
/// empty folder.
pub(crate) fn write_entry(directory: &Path, name: &str, entry: &Value) {
    let root = directory.to_str().expect("UTF-8 case folder");
    let path = directory.join(name);
    std::fs::create_dir_all(path.parent().expect("parent")).expect("tree folder");
    if let Some(text) = entry.as_str() {
        std::fs::write(&path, text.replace("{root}", root)).expect("text file");
    } else if let Some(target) = entry["symlink"].as_str() {
        if path.is_dir() && !path.is_symlink() {
            std::fs::remove_dir_all(&path).expect("emptied folder under a link");
        }
        std::os::unix::fs::symlink(target.replace("{root}", root), &path).expect("link");
    } else if let Some(hex) = entry["hex"].as_str() {
        std::fs::write(&path, hex_bytes(hex)).expect("byte file");
    } else {
        std::fs::create_dir_all(&path).expect("empty folder");
    }
}

/// Write a whole corpus tree under a case folder, in path order.
pub(crate) fn materialise(directory: &Path, tree: &Map<String, Value>) {
    for (name, entry) in tree {
        write_entry(directory, name, entry);
    }
}

/// Write a complete tree and one case's edits under a case folder: entries
/// removed, then entries written.
pub(crate) fn edited_tree(directory: &Path, template: &Map<String, Value>, edits: &Value) {
    materialise(directory, template);
    for name in edits["remove"].as_array().expect("removed entries") {
        let path = directory.join(name.as_str().expect("entry"));
        if path.is_dir() && !path.is_symlink() {
            std::fs::remove_dir(&path).expect("removed folder");
        } else {
            std::fs::remove_file(&path).expect("removed entry");
        }
    }
    for (name, entry) in edits["write"].as_object().expect("written entries") {
        write_entry(directory, name, entry);
    }
}

/// Apply a corpus patch to a base document: member paths set or removed.
pub(crate) fn patched(base: &Value, patch: &Value) -> Value {
    let mut document = base.clone();
    for operation in patch.as_array().expect("patch") {
        let path = operation["path"].as_array().expect("path");
        let (last, parents) = path.split_last().expect("a member path");
        let mut node = &mut document;
        for part in parents {
            node = &mut node[part.as_str().expect("member")];
        }
        let members = node.as_object_mut().expect("object");
        let name = last.as_str().expect("member");
        if operation.get("remove").is_some() {
            members.remove(name);
        } else {
            members.insert(name.to_owned(), operation["set"].clone());
        }
    }
    document
}

/// The SplitMix64 generator of Steele, Lea and Flood, from which the firmware
/// reader mutation corpus draws its edits.
pub(crate) struct SplitMix64(u64);

impl SplitMix64 {
    /// Start a sequence at a seed.
    pub(crate) fn new(seed: u64) -> Self {
        Self(seed)
    }

    /// The next 64-bit output.
    pub(crate) fn draw(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut mixed = self.0;
        mixed = (mixed ^ (mixed >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        mixed = (mixed ^ (mixed >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        mixed ^ (mixed >> 31)
    }

    /// The next output reduced modulo a positive bound.
    fn below(&mut self, bound: usize) -> usize {
        let bound = u64::try_from(bound).expect("bound");
        usize::try_from(self.draw() % bound).expect("index")
    }
}

/// One stacked random edit of a nonempty base, as the mutation corpus defines
/// it: one to eight runs of one to eight bytes overwritten at random offsets,
/// then, in one case of eight, a cut at a random length.
pub(crate) fn stacked_edits(base: &[u8], random: &mut SplitMix64) -> Vec<u8> {
    let mut data = base.to_vec();
    for _ in 0..1 + random.below(8) {
        let offset = random.below(data.len());
        let end = data.len().min(offset + 1 + random.below(8));
        for byte in &mut data[offset..end] {
            *byte = random.draw().to_le_bytes()[0];
        }
    }
    if random.below(8) == 0 {
        let length = random.below(data.len());
        data.truncate(length);
    }
    data
}

/// A corpus value with every refusal index replaced by its text.
pub(crate) fn with_table(value: &Value, texts: &[String]) -> Value {
    match value {
        Value::Object(members) => Value::Object(
            members
                .iter()
                .map(|(key, item)| {
                    let item = match item.as_u64().filter(|_| key == "refusal") {
                        Some(number) => {
                            Value::from(texts[usize::try_from(number).expect("index")].as_str())
                        }
                        None => with_table(item, texts),
                    };
                    (key.clone(), item)
                })
                .collect(),
        ),
        Value::Array(items) => {
            Value::Array(items.iter().map(|item| with_table(item, texts)).collect())
        }
        other => other.clone(),
    }
}

/// The committed firmware reader mutation corpus, its refusal texts and seed.
pub(crate) fn mutation_corpus() -> (Value, Vec<String>, u64) {
    let document: Value =
        serde_json::from_str(include_str!("../data/firmware-reader-mutations.json"))
            .expect("mutation corpus");
    assert_eq!(
        document["schema"],
        "loop-timing-witness.firmware-reader-mutations.v1"
    );
    let texts = document["texts"]
        .as_array()
        .expect("texts")
        .iter()
        .map(|text| text.as_str().expect("text").to_owned())
        .collect();
    let seed = document["seed"].as_u64().expect("seed");
    (document, texts, seed)
}

/// Each base of one reader in the mutation corpus: its name, its own sequence
/// and its expected outcomes, with the corpus's case count checked.
pub(crate) fn mutation_bases<'a>(
    document: &'a Value,
    seed: u64,
    reader: &str,
) -> Vec<(&'a str, SplitMix64, &'a [Value])> {
    let cases = usize::try_from(document["cases"].as_u64().expect("cases")).expect("cases");
    document["bases"]
        .as_array()
        .expect("bases")
        .iter()
        .enumerate()
        .filter(|(_, base)| base["reader"] == reader)
        .map(|(position, base)| {
            let outcomes = base["outcomes"].as_array().expect("outcomes");
            assert_eq!(outcomes.len(), cases);
            let position = u64::try_from(position).expect("position");
            (
                base["name"].as_str().expect("name"),
                SplitMix64::new(seed + position),
                outcomes.as_slice(),
            )
        })
        .collect()
}
