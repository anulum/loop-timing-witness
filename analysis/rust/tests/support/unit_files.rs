// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — corpus bytes and owned folders of the crate tests

//! Decode the hexadecimal bytes the shared corpora hold, own a folder for
//! corpus file trees, write those trees and their edits, and patch documents.

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
