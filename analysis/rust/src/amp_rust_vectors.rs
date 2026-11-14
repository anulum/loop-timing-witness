// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fixed RV64 compiler vectors of the Rust kernel

//! Build the Rust kernel's literal compiler vectors as the Python module
//! `amp_rust_vectors` does, so a captured preparation can be held to them.

use crate::control_paths::parent_and_name;
use crate::control_text::python_display;
use serde_json::{Value, json};
use std::path::Path;

/// The bare-metal RV64 target the kernel is compiled for.
const TARGET: &str = "riscv64imac-unknown-none-elf";
/// The controller crate's folder in the repository.
pub(crate) const CORE: &str = "controllers/rust";
/// The adapter crate's folder in the repository.
pub(crate) const ADAPTER: &str = "runtime/bare_metal/rust_kernel";
/// The static archive the image links.
pub(crate) const LIBRARY: &str = "objects/rust/libwitness_amp_rust_kernel.a";

/// Python's `str(Path(compiler).parent.parent)`, the toolchain's sysroot.
fn sysroot(compiler: &str) -> String {
    let (parent, _) = parent_and_name(Path::new(compiler));
    let (sysroot, _) = parent_and_name(&parent);
    python_display(&sysroot)
}

/// The words every vector starts with: the compiler, edition, target,
/// sysroot, code generation options and denied lints.
fn prefix(compiler: &str) -> Vec<String> {
    let mut words = vec![
        compiler.to_owned(),
        "--edition=2024".into(),
        "--target".into(),
        TARGET.into(),
        "--sysroot".into(),
        sysroot(compiler),
    ];
    for flag in [
        "panic=abort",
        "opt-level=3",
        "overflow-checks=yes",
        "codegen-units=1",
    ] {
        words.extend(["-C".into(), flag.into()]);
    }
    for lint in [
        "warnings",
        "missing_docs",
        "improper_ctypes",
        "improper_ctypes_definitions",
    ] {
        words.extend(["-D".into(), lint.into()]);
    }
    words
}

/// The two vectors Python's `rust_vectors(compiler, metadata=...)` returns:
/// the controller library, then the adapter, for metadata or for code.
pub(crate) fn rust_vectors(compiler: &str, metadata: bool) -> Value {
    let prefix = prefix(compiler);
    let (output, suffix, emit, archive) = if metadata {
        ("rust_metadata", "rmeta", "metadata", "rmeta")
    } else {
        ("objects/rust", "rlib", "link", "a")
    };
    let core = format!("{output}/libwitness_controller.{suffix}");
    let first = [
        "--crate-name",
        "witness_controller",
        "--crate-type",
        "rlib",
        "-D",
        "unsafe_code",
        "--emit",
        &format!("{emit},dep-info={output}/core.d"),
        &format!("source/{CORE}/src/lib.rs"),
        "-o",
        &core,
    ];
    let second = [
        "--crate-name",
        "witness_amp_rust_kernel",
        "--crate-type",
        "staticlib",
        "-D",
        "unsafe_op_in_unsafe_fn",
        "--extern",
        &format!("witness_controller={core}"),
        "--emit",
        &format!("{emit},dep-info={output}/adapter.d"),
        &format!("source/{ADAPTER}/src/lib.rs"),
        "-o",
        &format!("{output}/libwitness_amp_rust_kernel.{archive}"),
    ];
    let vector = |tail: &[&str]| {
        let mut words = prefix.clone();
        words.extend(tail.iter().map(|word| (*word).to_owned()));
        words
    };
    json!([vector(&first), vector(&second)])
}
