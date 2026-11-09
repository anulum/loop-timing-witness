// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python csv reading of the run series

//! Read CSV text exactly as Python's `csv.reader` does for the series files.
//!
//! The Python analysis reads each series with
//! `csv.DictReader(io.StringIO(text, newline=""), strict=True)` in the default
//! excel dialect. [`Records`] yields the same records and the same `csv.Error`
//! texts: the text is split into lines after `\n`, `\r\n` or a lone `\r`, each
//! line is run through CPython's reader state machine followed by an
//! end-of-line marker, and a record ends when the machine returns to the start
//! of a record. Empty lines give empty records, which `DictReader` skips.

/// CPython's default `csv.field_size_limit`, in characters.
const FIELD_LIMIT: usize = 131_072;

/// The reader states of CPython's `_csv.c` that the excel dialect reaches.
#[derive(Clone, Copy, PartialEq, Eq)]
enum State {
    StartRecord,
    StartField,
    InField,
    InQuotedField,
    QuoteInQuotedField,
    EatCrnl,
}

/// Successive CSV records of one text, as `csv.reader` returns them.
pub(crate) struct Records<'a> {
    text: &'a str,
    state: State,
    fields: Vec<String>,
    field: String,
    field_len: usize,
}

/// Whether an input is a line-break character or the end-of-line marker (`None`).
fn breaks(input: Option<char>) -> bool {
    matches!(input, None | Some('\n' | '\r'))
}

impl<'a> Records<'a> {
    /// Read the records of a decoded text.
    pub(crate) fn new(text: &'a str) -> Self {
        Self {
            text,
            state: State::StartRecord,
            fields: Vec::new(),
            field: String::new(),
            field_len: 0,
        }
    }

    /// The next line, with its terminator, as `StringIO(newline="")` splits it.
    fn line(&mut self) -> Option<&'a str> {
        if self.text.is_empty() {
            return None;
        }
        let bytes = self.text.as_bytes();
        let end = match bytes
            .iter()
            .position(|&byte| byte == b'\n' || byte == b'\r')
        {
            None => bytes.len(),
            Some(index) if bytes[index] == b'\r' && bytes.get(index + 1) == Some(&b'\n') => {
                index + 2
            }
            Some(index) => index + 1,
        };
        let (line, rest) = self.text.split_at(end);
        self.text = rest;
        Some(line)
    }

    /// Finish the current field.
    fn save(&mut self) {
        self.fields.push(std::mem::take(&mut self.field));
        self.field_len = 0;
    }

    /// Add one character to the current field, within the field size limit.
    fn add(&mut self, character: char) -> Result<(), String> {
        if self.field_len >= FIELD_LIMIT {
            return Err(format!("field larger than field limit ({FIELD_LIMIT})"));
        }
        self.field.push(character);
        self.field_len += 1;
        Ok(())
    }

    /// End a field at a line break, or at the end-of-line marker (`None`).
    fn end_line(&mut self, input: Option<char>) {
        self.save();
        self.state = if input.is_none() {
            State::StartRecord
        } else {
            State::EatCrnl
        };
    }

    /// Advance the state machine by one character, or by the end-of-line marker (`None`).
    fn process(&mut self, input: Option<char>) -> Result<(), String> {
        match self.state {
            // Every line has a character, which leaves this state, so the
            // end-of-line marker never arrives here.
            State::StartRecord => match input {
                Some('\n' | '\r') => self.state = State::EatCrnl,
                _ => self.start_field(input)?,
            },
            State::StartField => self.start_field(input)?,
            State::InField => match input {
                Some(',') => {
                    self.save();
                    self.state = State::StartField;
                }
                Some(character) if !breaks(input) => self.add(character)?,
                _ => self.end_line(input),
            },
            State::InQuotedField => match input {
                None => {}
                Some('"') => self.state = State::QuoteInQuotedField,
                Some(character) => self.add(character)?,
            },
            State::QuoteInQuotedField => match input {
                Some('"') => {
                    self.add('"')?;
                    self.state = State::InQuotedField;
                }
                Some(',') => {
                    self.save();
                    self.state = State::StartField;
                }
                _ if breaks(input) => self.end_line(input),
                _ => return Err("',' expected after '\"'".to_owned()),
            },
            State::EatCrnl => {
                // Lines are split after every line break, so only the second
                // character of `\r\n` or the end-of-line marker arrives here.
                if input.is_none() {
                    self.state = State::StartRecord;
                }
            }
        }
        Ok(())
    }

    /// Handle an input at the start of a field.
    fn start_field(&mut self, input: Option<char>) -> Result<(), String> {
        match input {
            Some('"') => self.state = State::InQuotedField,
            Some(',') => {
                self.save();
                self.state = State::StartField;
            }
            Some(character) if !breaks(input) => {
                self.add(character)?;
                self.state = State::InField;
            }
            _ => self.end_line(input),
        }
        Ok(())
    }

    /// Read lines until one record is complete.
    fn record(&mut self) -> Result<Option<Vec<String>>, String> {
        loop {
            let Some(line) = self.line() else {
                return if self.field_len != 0 || self.state == State::InQuotedField {
                    Err("unexpected end of data".to_owned())
                } else {
                    Ok(None)
                };
            };
            for character in line.chars() {
                self.process(Some(character))?;
            }
            self.process(None)?;
            if self.state == State::StartRecord {
                return Ok(Some(std::mem::take(&mut self.fields)));
            }
        }
    }
}

impl Iterator for Records<'_> {
    type Item = Result<Vec<String>, String>;

    fn next(&mut self) -> Option<Self::Item> {
        self.record().transpose()
    }
}

/// One `DictReader` data row: its cells, or a missing or excess cell.
pub(crate) enum Row {
    /// Exactly one nonempty cell per header field, in header order.
    Complete(Vec<String>),
    /// A missing, excess or empty cell.
    Incomplete,
}

/// Python's `DictReader` over [`Records`]: the header record, then data rows.
pub(crate) struct DictRows<'a> {
    records: Records<'a>,
    width: usize,
}

impl<'a> DictRows<'a> {
    /// Read the header record; `None` when the text has no record at all.
    pub(crate) fn new(text: &'a str) -> Result<(Option<Vec<String>>, Self), String> {
        let mut records = Records::new(text);
        let header = records.next().transpose()?;
        let width = header.as_ref().map_or(0, Vec::len);
        Ok((header, Self { records, width }))
    }
}

impl Iterator for DictRows<'_> {
    type Item = Result<Row, String>;

    fn next(&mut self) -> Option<Self::Item> {
        loop {
            match self.records.next()? {
                Err(error) => return Some(Err(error)),
                Ok(record) if record.is_empty() => {}
                Ok(record) => {
                    let complete =
                        record.len() == self.width && record.iter().all(|cell| !cell.is_empty());
                    return Some(Ok(if complete {
                        Row::Complete(record)
                    } else {
                        Row::Incomplete
                    }));
                }
            }
        }
    }
}

#[cfg(test)]
#[path = "../tests/unit/control_csv.rs"]
mod tests;
