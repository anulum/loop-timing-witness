// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — kernel trace stop API corpus

#include "../../runtime/linux/trace_stop.h"
#include <fcntl.h>
#include <iostream>
#include <string>

/** Print what the trace stop API gives, or the refusal it raises.
 *
 * ``stop DIRECTORY CONDITION [MISSES SAFE]...`` opens a stop and observes each pair, then
 * prints its JSON member; ``path TEXT`` prints whether the text is a plain tracefs path;
 * ``clock TEXT`` prints the selected trace clock; ``read PATH`` prints the length of a control
 * file; ``full`` writes to ``/dev/full``.
 */
int main(int argc, char **argv) {
    if (argc < 2)
        return 1;
    const std::string scenario = argv[1];
    try {
        if (scenario == "stop" && argc >= 4 && argc % 2 == 0) {
            witness::TraceStop stop(argv[2], argv[3]);
            for (int index = 4; index < argc; index += 2)
                stop.observe(static_cast<std::uint32_t>(std::stoul(argv[index])),
                             std::string(argv[index + 1]) == "1");
            std::string text;
            witness::append_trace_stop_json(text, stop.report());
            std::cout << text;
        } else if (scenario == "path" && argc == 3) {
            std::cout << (witness::plain_trace_path(argv[2]) ? "plain\n" : "refused\n");
        } else if (scenario == "clock" && argc == 3) {
            std::cout << witness::selected_trace_clock(argv[2]) << "\n";
        } else if (scenario == "read" && argc == 3) {
            std::cout << witness::read_trace_control(argv[2]).size() << "\n";
        } else if (scenario == "full" && argc == 2) {
            const int descriptor = open("/dev/full", O_WRONLY | O_CLOEXEC);
            witness::write_trace_control(descriptor, "0", "tracing_on");
        } else {
            return 1;
        }
    } catch (const std::runtime_error &error) {
        std::cout << "refused: " << error.what() << "\n";
    }
    return 0;
}
