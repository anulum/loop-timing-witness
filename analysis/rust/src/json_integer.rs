// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — exact JSON integer-zero interoperability

//! Preserve integer -0 as zero without admitting decimal or exponent encodings.

use std::borrow::Cow;

/// Replace only complete unquoted -0 integer tokens, retaining all original fields.
///
/// RFC8259 section6 permits an optional minus before the integer zero. serde_json
/// represents that spelling as a float; Python represents it as an integer.
/// This token-only view leaves strings, decimals, exponents and duplicate fields
/// intact. Callers retain and hash the original input bytes separately.
pub(crate) fn integer_zeroes(raw: &[u8]) -> Cow<'_, [u8]> {
    if !raw.windows(2).any(|pair| pair == b"-0") {
        return Cow::Borrowed(raw);
    }
    let mut result: Option<Vec<u8>> = None;
    let mut quoted = false;
    let mut escaped = false;
    for (index, &byte) in raw.iter().enumerate() {
        if quoted {
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                quoted = false;
            }
        } else if byte == b'"' {
            quoted = true;
        } else if byte == b'-'
            && raw.get(index + 1) == Some(&b'0')
            && (index == 0 || b":,[ \t\r\n".contains(&raw[index - 1]))
            && raw
                .get(index + 2)
                .is_none_or(|next| b",]} \t\r\n".contains(next))
        {
            result.get_or_insert_with(|| raw[..index].to_vec());
            continue;
        }
        if let Some(output) = &mut result {
            output.push(byte);
        }
    }
    result.map_or(Cow::Borrowed(raw), Cow::Owned)
}
