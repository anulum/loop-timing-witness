// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — IRQ-free physical Linux AMP mapping and ordered ownership

#include "amp_uio_device.h"
#include <cerrno>
#include <cstring>
#include <endian.h>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <time.h>
#include <unistd.h>

namespace witness {
namespace {
/** Retain the actual failed syscall and errno without hardware fallback. */
[[noreturn]] void failure(const char *operation) {
    throw std::runtime_error(std::string(operation) + ": " + std::strerror(errno));
}
/** Require one original complete sysfs attribute, without embedded NUL or extra rows. */
std::string attribute(const std::filesystem::path &path) {
    std::ifstream input(path);
    std::string value, extra;
    if (!input || !std::getline(input, value) || value.find('\0') != std::string::npos ||
        std::getline(input, extra) || !input.eof())
        throw std::runtime_error("cannot read AMP sysfs attribute: " + path.string());
    return value;
}
/** Parse a full unsigned sysfs quantity before any narrowing or physical map arithmetic. */
std::uint64_t quantity(const std::string &text) {
    const bool hex = text.size() > 2 && text.substr(0, 2) == "0x";
    const auto digits = text.substr(hex ? 2 : 0);
    if (digits.empty() || digits.find_first_not_of(hex ? "0123456789abcdefABCDEF" : "0123456789") !=
                              std::string::npos)
        throw std::runtime_error("invalid AMP sysfs quantity");
    return std::stoull(digits, nullptr, hex ? 16 : 10);
}
/** Order mapped physical mailbox and fabric accesses on the supported actual architectures. */
void fence() {
#if defined(__riscv) && __riscv_xlen == 64
    asm volatile("fence iorw,iorw" ::: "memory");
#elif defined(__x86_64__)
    __sync_synchronize();
#else
#error "AMP UIO ordering is implemented only for RV64 and x86_64"
#endif
}
/** Match all original named page-aligned UIO map attributes exactly. */
void verify_map(const std::filesystem::path &sysfs, const AmpUioMap &selection) {
    const auto map = sysfs / "maps" / ("map" + std::to_string(selection.index));
    if (attribute(map / "name") != selection.name ||
        quantity(attribute(map / "addr")) != selection.address ||
        quantity(attribute(map / "size")) != selection.bytes || quantity(attribute(map / "offset")))
        throw std::runtime_error("AMP original named UIO map identity changed");
}
} // namespace

AmpUioDevice::AmpUioDevice(const UioIdentity &identity, const AmpUioMap &fabric,
                           const AmpUioMap &mailbox) {
    if (identity.device.size() < 4 || identity.device.substr(0, 3) != "uio" ||
        identity.device.substr(3).find_first_not_of("0123456789") != std::string::npos ||
        identity.name.empty() || identity.version.empty() || identity.map != fabric.index ||
        identity.physical_address != fabric.address || fabric.name.empty() || mailbox.name.empty())
        throw std::runtime_error("invalid AMP UIO identity");
    const long system_page = sysconf(_SC_PAGESIZE);
    if (system_page <= 0)
        throw std::runtime_error("cannot determine AMP mapping page size");
    const auto page = static_cast<std::uint64_t>(system_page);
    for (const auto *map : {&fabric, &mailbox}) {
        if (!map->address || map->address % page || !map->bytes || map->bytes % page ||
            map->bytes > std::numeric_limits<std::size_t>::max() ||
            map->address > UINT64_MAX - map->bytes ||
            map->index > static_cast<std::uint64_t>(std::numeric_limits<off_t>::max()) / page)
            throw std::runtime_error("AMP UIO map extent or alignment outside bounds");
    }
    if (fabric.bytes != page || mailbox.bytes < sizeof(witness_amp_mailbox) ||
        fabric.index == mailbox.index ||
        (fabric.address < mailbox.address + mailbox.bytes &&
         mailbox.address < fabric.address + fabric.bytes))
        throw std::runtime_error("AMP UIO resources overlap or lack complete mailbox capacity");
    const auto sysfs = std::filesystem::path("/sys/class/uio") / identity.device;
    const auto verify = [&]() {
        const auto node = sysfs / "device/of_node";
        if (attribute(sysfs / "name") != identity.name ||
            attribute(sysfs / "version") != identity.version ||
            std::filesystem::canonical(sysfs / "device/driver").filename() != "uio_pdrv_genirq" ||
            !std::filesystem::is_directory(node) || std::filesystem::exists(node / "interrupts") ||
            std::filesystem::exists(node / "interrupts-extended"))
            throw std::runtime_error("AMP UIO driver identity or dedicated IRQ ownership mismatch");
        verify_map(sysfs, fabric);
        verify_map(sysfs, mailbox);
    };
    verify();
    register_bytes = static_cast<std::size_t>(fabric.bytes);
    telemetry_bytes = static_cast<std::size_t>(mailbox.bytes);
    shared = mailbox.address;
    try {
        descriptor = open(("/dev/" + identity.device).c_str(), O_RDWR | O_CLOEXEC | O_NOFOLLOW);
        if (descriptor < 0)
            failure("open AMP UIO");
        struct stat status {};
        if (fstat(descriptor, &status) < 0)
            failure("stat AMP UIO");
        if (!S_ISCHR(status.st_mode) ||
            attribute(sysfs / "dev") !=
                std::to_string(major(status.st_rdev)) + ":" + std::to_string(minor(status.st_rdev)))
            throw std::runtime_error("AMP UIO character device identity mismatch");
        if (flock(descriptor, LOCK_EX | LOCK_NB) < 0)
            failure("lock AMP UIO");
        registers = mmap(nullptr, register_bytes, PROT_READ | PROT_WRITE, MAP_SHARED, descriptor,
                         static_cast<off_t>(static_cast<std::uint64_t>(fabric.index) * page));
        if (registers == MAP_FAILED) {
            registers = nullptr;
            failure("map AMP fabric");
        }
        telemetry = mmap(nullptr, telemetry_bytes, PROT_READ | PROT_WRITE, MAP_SHARED, descriptor,
                         static_cast<off_t>(static_cast<std::uint64_t>(mailbox.index) * page));
        if (telemetry == MAP_FAILED) {
            telemetry = nullptr;
            failure("map AMP mailbox");
        }
        verify();
        if (read(0x7c).data != 1)
            throw std::runtime_error("unsupported AMP fabric register ABI");
    } catch (...) {
        close();
        throw;
    }
}
void AmpUioDevice::close() noexcept {
    if (telemetry)
        munmap(telemetry, telemetry_bytes);
    if (registers)
        munmap(registers, register_bytes);
    if (descriptor >= 0)
        ::close(descriptor);
    telemetry = registers = nullptr;
    descriptor = -1;
}
AmpUioDevice::~AmpUioDevice() { close(); }
std::size_t AmpUioDevice::offset(std::uint64_t address) const {
    if (address < shared || address - shared > sizeof(witness_amp_mailbox) - 4 || address % 4)
        throw std::invalid_argument("AMP access outside the original mailbox");
    return static_cast<std::size_t>(address - shared);
}
std::uint64_t AmpUioDevice::time() const {
    timespec stamp{};
    if (clock_gettime(CLOCK_MONOTONIC, &stamp) < 0)
        failure("AMP monotonic clock");
    return static_cast<std::uint64_t>(stamp.tv_sec) * 1000000000 +
           static_cast<std::uint64_t>(stamp.tv_nsec);
}
void AmpUioDevice::advance(std::uint64_t nanoseconds) {
    timespec delay{static_cast<time_t>(nanoseconds / 1000000000),
                   static_cast<long>(nanoseconds % 1000000000)};
    while (nanosleep(&delay, &delay) < 0)
        if (errno != EINTR)
            failure("AMP polling sleep");
}
ProtocolReply AmpUioDevice::read(std::uint8_t address) {
    if (address % 4)
        return {2, 0};
    fence();
    const auto value = static_cast<volatile std::uint32_t *>(registers)[address / 4];
    fence();
    return {0, le32toh(value)};
}
ProtocolReply AmpUioDevice::write(std::uint8_t address, std::uint32_t value, std::uint8_t strobes) {
    if (strobes != 15 ||
        !(address == 0x38 || address == 0x3c || address == 0x94 || address == 0x98 ||
          (address >= 0x44 && address <= 0x64 && address % 4 == 0)))
        return {2, 0};
    fence();
    static_cast<volatile std::uint32_t *>(registers)[address / 4] = htole32(value);
    fence();
    return {0, 0};
}
std::uint32_t AmpUioDevice::read_memory32(std::uint64_t address) {
    const auto index = offset(address) / 4;
    fence();
    const auto value = static_cast<volatile std::uint32_t *>(telemetry)[index];
    fence();
    return le32toh(value);
}
void AmpUioDevice::write_memory32(std::uint64_t address, std::uint32_t value) {
    const auto displacement = offset(address);
    if (displacement != offsetof(witness_amp_mailbox, consumer) &&
        displacement != offsetof(witness_amp_mailbox, logger_status))
        throw std::invalid_argument("AMP logger cannot write firmware-owned memory");
    fence();
    static_cast<volatile std::uint32_t *>(telemetry)[displacement / 4] = htole32(value);
    fence();
}
} // namespace witness
