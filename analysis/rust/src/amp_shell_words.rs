// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — POSIX shell word splitting of dependency rules

//! Split text into words as CPython's `shlex.split(text)` does.
//!
//! `shlex.split` runs the POSIX lexer with `whitespace_split` set and no
//! comment characters. Under those settings its states reduce to four:
//!
//! - between words, whitespace (space, tab, carriage return, line feed) is
//!   skipped, a quote opens a quotation, a backslash escapes the next
//!   character and anything else starts a word;
//! - inside a word, whitespace ends the word, a quote opens a quotation and a
//!   backslash escapes the next character;
//! - inside a quotation, its own quote closes it and every other character is
//!   kept, except that inside double quotes a backslash escapes the next
//!   character and is itself kept unless that character is a backslash or a
//!   double quote;
//! - an escaped character is kept as it is.
//!
//! A quotation, even an empty one, makes a word. The lexer's break on
//! whitespace between words for a pending word is never reached under these
//! settings, as no word is pending there.

/// CPython's text for a quotation open at the end of the text.
pub(crate) const NO_CLOSING_QUOTATION: &str = "No closing quotation";
/// CPython's text for a backslash at the end of the text.
pub(crate) const NO_ESCAPED_CHARACTER: &str = "No escaped character";

/// The lexer's state between two characters.
#[derive(Clone, Copy, PartialEq, Eq)]
enum State {
    /// Between words.
    Space,
    /// Inside a word.
    Word,
    /// Inside a quotation opened by this quote.
    Quoted(char),
    /// After a backslash: inside double quotes when it holds the quote,
    /// inside a word otherwise.
    Escaped(Option<char>),
}

/// Split one text into words as CPython's `shlex.split` does.
///
/// # Errors
///
/// CPython's text when the text ends inside a quotation or after a
/// backslash.
pub(crate) fn split(text: &str) -> Result<Vec<String>, &'static str> {
    let mut words = Vec::new();
    let mut word = String::new();
    let mut state = State::Space;
    for character in text.chars() {
        state = match (state, character) {
            (State::Space | State::Word, ' ' | '\t' | '\r' | '\n') => {
                if state == State::Word {
                    words.push(std::mem::take(&mut word));
                }
                State::Space
            }
            (State::Space | State::Word, '\'' | '"') => State::Quoted(character),
            (State::Space | State::Word, '\\') => State::Escaped(None),
            (State::Space | State::Word, _) => {
                word.push(character);
                State::Word
            }
            (State::Quoted(quote), _) if character == quote => State::Word,
            (State::Quoted('"'), '\\') => State::Escaped(Some('"')),
            (State::Quoted(_), _) => {
                word.push(character);
                state
            }
            (State::Escaped(quote), _) => {
                if quote.is_some_and(|quote| character != '\\' && character != quote) {
                    word.push('\\');
                }
                word.push(character);
                quote.map_or(State::Word, State::Quoted)
            }
        };
    }
    match state {
        State::Space => {}
        State::Word => words.push(word),
        State::Quoted(_) => return Err(NO_CLOSING_QUOTATION),
        State::Escaped(_) => return Err(NO_ESCAPED_CHARACTER),
    }
    Ok(words)
}
