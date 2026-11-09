// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — schema patterns with Python search semantics

//! Match the regular expressions of the committed schemas as Python's `re.search` does.
//!
//! The supported syntax is the subset the run and measurement-domain schemas use:
//! the anchors `^` and `$`, literal characters, bracketed classes of single
//! characters and ranges, the classes `\S` and `\d`, the escaped `\.`, groups and
//! the quantifiers `*`, `+`, `?`,
//! `{n}` and `{m,n}`. Any other construct is refused when the pattern is compiled,
//! so a schema change cannot be matched with different semantics silently.
//!
//! Python semantics that differ from many other engines are kept: a match may
//! start anywhere unless anchored, `$` also matches before one final newline, and
//! `\S` excludes exactly the characters for which Python's `str.isspace` is true,
//! and `\d` matches every character for which `str.isdecimal` is true, not only
//! the ASCII digits.

use crate::control_text::python_decimal;

/// One element of a compiled pattern.
#[derive(Debug, Clone, PartialEq)]
enum Atom {
    /// The start of the text.
    Start,
    /// The end of the text, or the position before one final newline.
    End,
    /// One character from inclusive ranges.
    Class(Vec<(char, char)>),
    /// One character that Python does not treat as whitespace.
    NotSpace,
    /// One character that Python treats as a decimal digit.
    Digit,
    /// A parenthesised sequence.
    Group(Vec<Piece>),
}

/// An atom with its repetition bounds.
#[derive(Debug, Clone, PartialEq)]
struct Piece {
    atom: Atom,
    minimum: usize,
    maximum: Option<usize>,
}

/// A compiled schema pattern.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct Pattern(Vec<Piece>);

/// Tell whether Python's `str.isspace` is true for one character.
pub(crate) fn python_space(character: char) -> bool {
    matches!(
        character,
        '\t'..='\r'
            | '\u{1c}'..='\u{20}'
            | '\u{85}'
            | '\u{a0}'
            | '\u{1680}'
            | '\u{2000}'..='\u{200a}'
            | '\u{2028}'
            | '\u{2029}'
            | '\u{202f}'
            | '\u{205f}'
            | '\u{3000}'
    )
}

impl Pattern {
    /// Compile one pattern of the supported subset.
    pub(crate) fn compile(text: &str) -> Result<Self, String> {
        let characters: Vec<char> = text.chars().collect();
        let mut position = 0;
        let pieces = sequence(&characters, &mut position, text)?;
        if position != characters.len() {
            return Err(unsupported(text));
        }
        Ok(Self(pieces))
    }

    /// Tell whether the pattern matches anywhere in the text, as `re.search` does.
    pub(crate) fn search(&self, text: &str) -> bool {
        let characters: Vec<char> = text.chars().collect();
        (0..=characters.len()).any(|start| matches(&self.0, &characters, start, &mut |_| true))
    }
}

/// The refusal for syntax outside the supported subset.
fn unsupported(text: &str) -> String {
    format!("Unsupported schema pattern {text}.")
}

/// Parse pieces until the end of the text or a closing parenthesis.
fn sequence(characters: &[char], position: &mut usize, text: &str) -> Result<Vec<Piece>, String> {
    let mut pieces = Vec::new();
    while let Some(&character) = characters.get(*position) {
        let atom = match character {
            ')' => break,
            '^' => Atom::Start,
            '$' => Atom::End,
            '[' => class(characters, position, text)?,
            '(' => {
                *position += 1;
                let inner = sequence(characters, position, text)?;
                if characters.get(*position) != Some(&')') {
                    return Err(unsupported(text));
                }
                Atom::Group(inner)
            }
            '\\' => match characters.get(*position + 1) {
                Some('S') => {
                    *position += 1;
                    Atom::NotSpace
                }
                Some('d') => {
                    *position += 1;
                    Atom::Digit
                }
                Some('.') => {
                    *position += 1;
                    Atom::Class(vec![('.', '.')])
                }
                _ => return Err(unsupported(text)),
            },
            '*' | '+' | '?' | '{' | '|' | '.' | ']' | '}' => return Err(unsupported(text)),
            literal => Atom::Class(vec![(literal, literal)]),
        };
        *position += 1;
        let (minimum, maximum) = quantifier(characters, position, text)?;
        if matches!(atom, Atom::Start | Atom::End) && (minimum, maximum) != (1, Some(1)) {
            return Err(unsupported(text));
        }
        pieces.push(Piece {
            atom,
            minimum,
            maximum,
        });
    }
    Ok(pieces)
}

/// Parse a bracketed class of literal characters and ranges, ending on `]`.
fn class(characters: &[char], position: &mut usize, text: &str) -> Result<Atom, String> {
    let mut ranges = Vec::new();
    *position += 1;
    loop {
        let start = match characters.get(*position) {
            Some(']') if !ranges.is_empty() => return Ok(Atom::Class(ranges)),
            Some(character) if !matches!(character, '\\' | '[' | '^' | ']') => *character,
            _ => return Err(unsupported(text)),
        };
        match (characters.get(*position + 1), characters.get(*position + 2)) {
            (Some('-'), Some(&end)) if end != ']' => {
                if end < start || matches!(end, '\\' | '[') {
                    return Err(unsupported(text));
                }
                ranges.push((start, end));
                *position += 3;
            }
            _ => {
                ranges.push((start, start));
                *position += 1;
            }
        }
    }
}

/// Parse an optional quantifier after an atom.
fn quantifier(
    characters: &[char],
    position: &mut usize,
    text: &str,
) -> Result<(usize, Option<usize>), String> {
    let bounds = match characters.get(*position) {
        Some('*') => (0, None),
        Some('+') => (1, None),
        Some('?') => (0, Some(1)),
        Some('{') => {
            let close = characters[*position..]
                .iter()
                .position(|&character| character == '}')
                .ok_or_else(|| unsupported(text))?;
            let body: String = characters[*position + 1..*position + close]
                .iter()
                .collect();
            let bounds = match body.split_once(',') {
                Some((low, high)) => (number(low, text)?, Some(number(high, text)?)),
                None => {
                    let exact = number(&body, text)?;
                    (exact, Some(exact))
                }
            };
            if bounds.1.is_some_and(|high| high < bounds.0) {
                return Err(unsupported(text));
            }
            *position += close;
            bounds
        }
        _ => return Ok((1, Some(1))),
    };
    *position += 1;
    Ok(bounds)
}

/// Parse one unsigned decimal repetition bound.
fn number(text: &str, pattern: &str) -> Result<usize, String> {
    if text.is_empty() || !text.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(unsupported(pattern));
    }
    text.parse().map_err(|_| unsupported(pattern))
}

/// Match pieces from one position and pass the end position to the continuation.
fn matches(
    pieces: &[Piece],
    characters: &[char],
    position: usize,
    rest: &mut dyn FnMut(usize) -> bool,
) -> bool {
    let Some((piece, tail)) = pieces.split_first() else {
        return rest(position);
    };
    repeat(piece, 0, characters, position, &mut |end| {
        matches(tail, characters, end, rest)
    })
}

/// Match one piece greedily between its bounds, backtracking through the continuation.
fn repeat(
    piece: &Piece,
    count: usize,
    characters: &[char],
    position: usize,
    rest: &mut dyn FnMut(usize) -> bool,
) -> bool {
    if (piece.minimum, piece.maximum) == (1, Some(1)) {
        return once(&piece.atom, characters, position, rest);
    }
    if piece.maximum.is_none_or(|maximum| count < maximum) {
        let advanced = once(&piece.atom, characters, position, &mut |end| {
            end != position && repeat(piece, count + 1, characters, end, rest)
        });
        if advanced {
            return true;
        }
    }
    count >= piece.minimum && rest(position)
}

/// Match one atom once from a position.
fn once(
    atom: &Atom,
    characters: &[char],
    position: usize,
    rest: &mut dyn FnMut(usize) -> bool,
) -> bool {
    match atom {
        Atom::Start => position == 0 && rest(position),
        Atom::End => {
            let at_end = position == characters.len()
                || (position + 1 == characters.len() && characters[position] == '\n');
            at_end && rest(position)
        }
        Atom::Class(ranges) => {
            characters.get(position).is_some_and(|&character| {
                ranges
                    .iter()
                    .any(|&(low, high)| (low..=high).contains(&character))
            }) && rest(position + 1)
        }
        Atom::NotSpace => {
            characters
                .get(position)
                .is_some_and(|&character| !python_space(character))
                && rest(position + 1)
        }
        Atom::Digit => {
            characters
                .get(position)
                .is_some_and(|&character| python_decimal(character))
                && rest(position + 1)
        }
        Atom::Group(inner) => matches(inner, characters, position, rest),
    }
}

#[cfg(test)]
#[path = "../tests/unit/control_pattern.rs"]
mod tests;
