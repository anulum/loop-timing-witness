// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — schema patterns with Python search semantics

//! Match the regular expressions of the committed schemas as Python's `re.search` does.
//!
//! The supported syntax is the subset the committed schemas use: the anchors `^` and `$`,
//! literal characters, bracketed classes of single characters and ranges, the classes `\S` and
//! `\d`, the escaped `\.`, groups, alternatives (`|`) and the quantifiers `*`, `+`, `?`, `{n}`
//! and `{m,n}`. Any other construct is refused when the pattern is compiled, so a schema change
//! cannot be matched with different semantics silently.
//!
//! Python semantics that differ from many other engines are kept: a match may
//! start anywhere unless anchored, `$` also matches before one final newline, and
//! `\S` excludes exactly the characters for which Python's `str.isspace` is true,
//! and `\d` matches every character for which `str.isdecimal` is true, not only
//! the ASCII digits.
//!
//! A compiled pattern is a small instruction program that a breadth-first simulation runs
//! over the text: every start position at once, each instruction at most once per position,
//! and no recursion over the text. Whether a match exists anywhere, the only question a
//! schema asks, is the same as for Python's backtracking search, and the time and stack
//! needed grow with the text length times the program length, not with nesting depth.

use crate::control_text::{python_decimal, python_space};

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
    /// A parenthesised group of alternative sequences.
    Group(Vec<Vec<Piece>>),
}

/// An atom with its repetition bounds.
#[derive(Debug, Clone, PartialEq)]
struct Piece {
    atom: Atom,
    minimum: usize,
    maximum: Option<usize>,
}

/// One instruction of a compiled pattern.
#[derive(Debug, Clone, PartialEq)]
enum Instruction {
    /// Continue only at the start of the text.
    Start,
    /// Continue only at the end of the text, or before one final newline.
    End,
    /// Consume one character from inclusive ranges.
    Class(Vec<(char, char)>),
    /// Consume one character that Python does not treat as whitespace.
    NotSpace,
    /// Consume one character that Python treats as a decimal digit.
    Digit,
    /// Continue at both targets.
    Split(usize, usize),
    /// Continue at the target.
    Jump(usize),
    /// A match exists.
    Match,
}

/// A compiled schema pattern: its instruction program.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct Pattern(Vec<Instruction>);

impl Pattern {
    /// Compile one pattern of the supported subset.
    pub(crate) fn compile(text: &str) -> Result<Self, String> {
        let characters: Vec<char> = text.chars().collect();
        let mut position = 0;
        let found = alternatives(&characters, &mut position, text)?;
        if position != characters.len() {
            return Err(unsupported(text));
        }
        let mut program = Vec::new();
        emit_alternatives(&found, &mut program);
        program.push(Instruction::Match);
        Ok(Self(program))
    }

    /// Tell whether the pattern matches anywhere in the text, as `re.search` does.
    pub(crate) fn search(&self, text: &str) -> bool {
        let characters: Vec<char> = text.chars().collect();
        let mut seen = vec![usize::MAX; self.0.len()];
        let mut threads = Vec::new();
        for position in 0..=characters.len() {
            if self.add(0, position, &characters, &mut seen, &mut threads) {
                return true;
            }
            let mut following = Vec::new();
            for &thread in &threads {
                let consumed =
                    characters
                        .get(position)
                        .is_some_and(|&character| match &self.0[thread] {
                            Instruction::Class(ranges) => ranges
                                .iter()
                                .any(|&(low, high)| (low..=high).contains(&character)),
                            Instruction::NotSpace => !python_space(character),
                            _ => python_decimal(character),
                        });
                if consumed
                    && self.add(
                        thread + 1,
                        position + 1,
                        &characters,
                        &mut seen,
                        &mut following,
                    )
                {
                    return true;
                }
            }
            threads = following;
        }
        false
    }

    /// Follow every non-consuming instruction from one, at one position, collecting the
    /// consuming instructions reached; tell whether `Match` is reached.
    fn add(
        &self,
        first: usize,
        position: usize,
        characters: &[char],
        seen: &mut [usize],
        threads: &mut Vec<usize>,
    ) -> bool {
        let mut pending = vec![first];
        while let Some(index) = pending.pop() {
            if seen[index] == position {
                continue;
            }
            seen[index] = position;
            match &self.0[index] {
                Instruction::Start => {
                    if position == 0 {
                        pending.push(index + 1);
                    }
                }
                Instruction::End => {
                    if position == characters.len()
                        || (position + 1 == characters.len() && characters[position] == '\n')
                    {
                        pending.push(index + 1);
                    }
                }
                Instruction::Split(first_target, second_target) => {
                    pending.push(*second_target);
                    pending.push(*first_target);
                }
                Instruction::Jump(target) => pending.push(*target),
                Instruction::Match => return true,
                _ => threads.push(index),
            }
        }
        false
    }
}

/// Emit alternative sequences: each but the last behind a split, each ending at one join.
fn emit_alternatives(found: &[Vec<Piece>], program: &mut Vec<Instruction>) {
    let mut jumps = Vec::new();
    for (index, pieces) in found.iter().enumerate() {
        let split = program.len();
        if index + 1 < found.len() {
            program.push(Instruction::Split(split + 1, 0));
        }
        for piece in pieces {
            emit_piece(piece, program);
        }
        if index + 1 < found.len() {
            jumps.push(program.len());
            program.push(Instruction::Jump(0));
            let next = program.len();
            program[split] = Instruction::Split(split + 1, next);
        }
    }
    let join = program.len();
    for jump in jumps {
        program[jump] = Instruction::Jump(join);
    }
}

/// Emit one piece: its required copies, then a loop or its optional copies.
fn emit_piece(piece: &Piece, program: &mut Vec<Instruction>) {
    for _ in 0..piece.minimum {
        emit_atom(&piece.atom, program);
    }
    match piece.maximum {
        None => {
            let split = program.len();
            program.push(Instruction::Split(split + 1, 0));
            emit_atom(&piece.atom, program);
            program.push(Instruction::Jump(split));
            let after = program.len();
            program[split] = Instruction::Split(split + 1, after);
        }
        Some(maximum) => {
            let mut splits = Vec::new();
            for _ in piece.minimum..maximum {
                splits.push(program.len());
                program.push(Instruction::Split(program.len() + 1, 0));
                emit_atom(&piece.atom, program);
            }
            let after = program.len();
            for split in splits {
                program[split] = Instruction::Split(split + 1, after);
            }
        }
    }
}

/// Emit one atom.
fn emit_atom(atom: &Atom, program: &mut Vec<Instruction>) {
    match atom {
        Atom::Start => program.push(Instruction::Start),
        Atom::End => program.push(Instruction::End),
        Atom::Class(ranges) => program.push(Instruction::Class(ranges.clone())),
        Atom::NotSpace => program.push(Instruction::NotSpace),
        Atom::Digit => program.push(Instruction::Digit),
        Atom::Group(inner) => emit_alternatives(inner, program),
    }
}

/// The refusal for syntax outside the supported subset.
fn unsupported(text: &str) -> String {
    format!("Unsupported schema pattern {text}.")
}

/// Parse `|`-separated sequences until the end of the text or a `)`.
fn alternatives(
    characters: &[char],
    position: &mut usize,
    text: &str,
) -> Result<Vec<Vec<Piece>>, String> {
    let mut found = vec![sequence(characters, position, text)?];
    while characters.get(*position) == Some(&'|') {
        *position += 1;
        found.push(sequence(characters, position, text)?);
    }
    Ok(found)
}

/// Parse pieces until the end of the text, a `|` or a closing parenthesis.
fn sequence(characters: &[char], position: &mut usize, text: &str) -> Result<Vec<Piece>, String> {
    let mut pieces = Vec::new();
    while let Some(&character) = characters.get(*position) {
        let atom = match character {
            ')' | '|' => break,
            '^' => Atom::Start,
            '$' => Atom::End,
            '[' => class(characters, position, text)?,
            '(' => {
                *position += 1;
                let inner = alternatives(characters, position, text)?;
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
            '*' | '+' | '?' | '{' | '.' | ']' | '}' => return Err(unsupported(text)),
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

#[cfg(test)]
#[path = "../tests/unit/control_pattern.rs"]
mod tests;
