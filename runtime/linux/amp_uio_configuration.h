// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — explicit original AMP Linux resource selection

#ifndef WITNESS_AMP_UIO_CONFIGURATION_H
#define WITNESS_AMP_UIO_CONFIGURATION_H
#include "amp_uio_device.h"
namespace witness {
/** Original IRQ-free map identities and explicitly bounded host polling. */
struct AmpUioConfiguration {
    UioIdentity identity;
    AmpUioMap fabric, mailbox;
    std::uint64_t startup_ns, completion_ns, poll_ns;
};
/** Read the complete resource configuration without inferred physical addresses or aliases. */
AmpUioConfiguration read_amp_uio_configuration(const std::string &path);
}
#endif
