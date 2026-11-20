// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Linux real-time context API validation

#include "../../runtime/linux/kernel_context.h"
#include "system_call_answer.h"
#include <iostream>
#include <string>
#include <sys/syscall.h>

/** Print the JSON member a context gives, or the refusal it raises.
 *
 * ``host`` reads the running kernel's own files; ``files`` reads the six given paths in the
 * order of KernelContextSources; ``uname_denied`` has the kernel refuse uname first;
 * ``empty_text`` asks for an empty identity text.
 */
int main(int argc, char **argv) {
    if (argc < 2)
        return 1;
    const std::string scenario = argv[1];
    try {
        if (scenario == "host" && argc == 2) {
            std::string text;
            witness::append_kernel_context_json(text, witness::read_kernel_context());
            std::cout << text;
        } else if (scenario == "files" && argc == 8) {
            const witness::KernelContextSources sources{argv[2], argv[3], argv[4],
                                                        argv[5], argv[6], argv[7]};
            std::string text;
            witness::append_kernel_context_json(text, witness::read_kernel_context(sources));
            std::cout << text;
        } else if (scenario == "uname_denied" && argc == 2) {
            answer_system_call(SYS_uname, EPERM);
            witness::read_kernel_context();
        } else if (scenario == "empty_text" && argc == 2) {
            witness::kernel_text("", 64, "kernel release");
        } else {
            return 1;
        }
    } catch (const std::runtime_error &error) {
        std::cout << "refused: " << error.what() << "\n";
    }
    return 0;
}
