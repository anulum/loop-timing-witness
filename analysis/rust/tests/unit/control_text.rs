// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python text, crate-internal controls

//! Compare string and error text with CPython 3.13 `repr` and `str(OSError)`.

use super::{os_error, printable, pure_path, python_display, repr, units};
use std::ffi::OsStr;
use std::os::unix::ffi::OsStrExt;
use std::path::Path;

/// CPython's `repr` of a string, as paths are printed.
fn python_repr(text: &str) -> String {
    repr(&units(text.as_bytes()))
}

/// Strings with their CPython 3.13 `repr`.
const PYTHON_REPR: &[(&str, &str)] = &[
    ("plain", "'plain'"),
    ("it's", "\"it's\""),
    ("say \"hi\"", "'say \"hi\"'"),
    ("both ' and \"", "'both \\' and \"'"),
    ("tab\u{9}here", "'tab\\there'"),
    ("line\u{a}break\u{d}", "'line\\nbreak\\r'"),
    ("back\\slash", "'back\\\\slash'"),
    ("\u{0}\u{1f}\u{7f}", "'\\x00\\x1f\\x7f'"),
    ("\u{e9} \u{fc} \u{6f22}", "'\u{e9} \u{fc} \u{6f22}'"),
    ("\u{a0}\u{ad}", "'\\xa0\\xad'"),
    ("\u{2028}", "'\\u2028'"),
    ("\u{1f600}", "'\u{1f600}'"),
    ("\u{e0001}", "'\\U000e0001'"),
    ("\u{feff}", "'\\ufeff'"),
    (
        "/run/j\u{fc}rgen/events.bin",
        "'/run/j\u{fc}rgen/events.bin'",
    ),
];

#[test]
fn strings_print_as_python_repr() {
    for &(text, expected) in PYTHON_REPR {
        assert_eq!(python_repr(text), expected, "{text:?}");
    }
}

#[test]
fn printable_follows_the_python_table() {
    assert!(printable('a'));
    assert!(printable('\u{e9}'));
    assert!(!printable('\u{0}'));
    assert!(!printable('\u{10ffff}'));
    assert!(!printable('\u{a0}'));
}

#[test]
fn operating_system_errors_print_as_python_str() {
    let path = Path::new(OsStr::from_bytes(b"/tmp/a\xffb\xc3"));
    let error = std::fs::read(path).expect_err("absent file");
    assert_eq!(
        os_error(&error, path),
        "[Errno 2] No such file or directory: '/tmp/a\\udcffb\\udcc3'"
    );
    let custom = std::io::Error::other("not an operating-system error");
    assert_eq!(os_error(&custom, Path::new("x")), "[Errno 0] Success: 'x'");
}

#[test]
fn paths_print_as_python_with_surrogate_escapes() {
    let path = Path::new(OsStr::from_bytes(b"/tmp/a\xffb"));
    assert_eq!(python_display(path), "/tmp/a\\udcffb");
    assert_eq!(python_display(Path::new("/tmp/plain")), "/tmp/plain");
}

/// Paths with CPython 3.13 `str(Path(text))`.
const PURE: &[(&str, &str)] = &[
    ("//a/b", "//a/b"),
    ("///a/b", "/a/b"),
    ("/a//./b/", "/a/b"),
    ("a/./b//", "a/b"),
    ("./a", "a"),
    ("../a/..", "../a/.."),
    ("//", "//"),
    ("/", "/"),
    ("a/b/.", "a/b"),
    ("", "."),
    ("./", "."),
];

#[test]
fn pure_paths_are_python_text() {
    for &(text, expected) in PURE {
        assert_eq!(pure_path(Path::new(text)), expected, "{text}");
    }
    let invalid = Path::new(OsStr::from_bytes(b"a/\xff//b"));
    assert_eq!(pure_path(invalid), "a/\\udcff/b");
}
