// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native process AXI access to production RTL

#include "simulation.h"
#include "../process_protocol.h"
#ifdef WITNESS_RTL_COVERAGE
#include "verilated_cov.h"
#include <unistd.h>
#endif

/** Serve R/W/T/I/Q lines with response,data,simulation-nanoseconds replies. */
int main(int argc, char **argv) {
    if (argc != 1) {
        std::cerr << "usage: " << argv[0] << " < AXI requests\n";
        return 1;
    }
    try {
        witness::Simulation simulation;
        const auto result = witness::serve(simulation);
#ifdef WITNESS_RTL_COVERAGE
        const auto profile =
            std::string(argv[0]) + "." + std::to_string(getpid()) + ".coverage.dat";
        VerilatedCov::write(profile.c_str());
#endif
        return result;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
