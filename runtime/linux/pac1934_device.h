// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — verified actual PAC1934 IIO attributes

#ifndef WITNESS_PAC1934_DEVICE_H
#define WITNESS_PAC1934_DEVICE_H
#include "power_configuration.h"
#include <sys/stat.h>

namespace witness {
/** Read-only acquisition of one actual named PAC1934 kernel instance. */
class Pac1934Device {
    PowerConfiguration configuration;
    int directory = -1;
    struct stat identity{};
    /** Read one whole kernfs text attribute through the owned device directory. */
    std::string attribute(const std::string &name) const;
public:
    /** Validate configuration before verifying real kernel, driver, rails and unsigned scales. */
    explicit Pac1934Device(const PowerConfiguration &config);
    /** Close the owned directory without changing sample/accumulator configuration. */
    ~Pac1934Device();
    Pac1934Device(const Pac1934Device &) = delete;
    Pac1934Device &operator=(const Pac1934Device &) = delete;
    /** Refuse unbind/rebind or changed calibration/configuration. */
    void verify() const;
    /** Require a rail from the verified mapping before reading exact raw/scale text. */
    std::string read(const PowerRail &rail, const std::string &quantity, bool scale) const;
};
} // namespace witness
#endif
