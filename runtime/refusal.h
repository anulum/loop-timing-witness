// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — authored native refusals

/** @file refusal.h
 * Native refusals whose deliberately authored messages may reach a caller.
 */

#ifndef WITNESS_REFUSAL_H
#define WITNESS_REFUSAL_H
#include <stdexcept>

namespace witness {
/** Authored execution refusal, preserving the standard runtime-error contract. */
class RuntimeRefused final : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};

/** Authored argument refusal, preserving the standard invalid-argument contract. */
class ArgumentRefused final : public std::invalid_argument {
  public:
    using std::invalid_argument::invalid_argument;
};
} // namespace witness
#endif
