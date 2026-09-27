// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Linux UIO map and IRQ implementation

#include "uio_device.h"

#include <cerrno>
#include <cstring>
#include <endian.h>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <poll.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <time.h>
#include <unistd.h>

namespace witness {
namespace {
/** Preserve the failing syscall errno in an actionable transport error. */
[[noreturn]] void syscall_error(const char *operation) {
    throw std::runtime_error(std::string(operation) + ": " + std::strerror(errno));
}

/** Read one whole sysfs text value; refuse truncation, extra rows or embedded NUL. */
std::string attribute(const std::filesystem::path &path) {
    std::ifstream stream(path);
    std::string value, extra;
    if (!stream || !std::getline(stream, value) || value.find('\0') != std::string::npos ||
        std::getline(stream, extra) || !stream.eof())
        throw std::runtime_error("cannot read sysfs attribute: " + path.string());
    return value;
}

/** Parse sysfs hex or decimal quantities without signs, whitespace or narrowing. */
std::uint64_t quantity(const std::string &value) {
    const bool hex = value.size() > 2 && value.substr(0, 2) == "0x";
    const std::string digits = value.substr(hex ? 2 : 0);
    if (digits.empty() || digits.find_first_not_of(hex ? "0123456789abcdefABCDEF" : "0123456789") != std::string::npos)
        throw std::runtime_error("invalid sysfs number");
    return std::stoull(digits, nullptr, hex ? 16 : 10);
}

/** Order both device and ordinary memory accesses on supported CPU architectures. */
void mmio_fence() {
#if defined(__riscv) && __riscv_xlen == 64
    asm volatile("fence iorw, iorw" ::: "memory");
#elif defined(__x86_64__)
    __sync_synchronize();
#else
#error "UIO MMIO ordering is implemented only for RV64 and x86_64"
#endif
}
} // namespace

UioDevice::UioDevice(const UioIdentity &identity) {
    if (identity.device.size() < 4 || identity.device.substr(0, 3) != "uio" ||
        identity.device.substr(3).find_first_not_of("0123456789") != std::string::npos ||
        identity.name.empty() || identity.version.empty())
        throw std::runtime_error("invalid UIO identity");
    const auto sysfs = std::filesystem::path("/sys/class/uio") / identity.device;
    const auto map = sysfs / "maps" / ("map" + std::to_string(identity.map));
    const auto verify_identity = [&]() {
        if (attribute(sysfs / "name") != identity.name || attribute(sysfs / "version") != identity.version ||
            std::filesystem::canonical(sysfs / "device/driver").filename() != "uio_pdrv_genirq")
            throw std::runtime_error("UIO name, version or platform driver mismatch");
    };
    verify_identity();
    const long system_page = sysconf(_SC_PAGESIZE);
    if (system_page <= 0) throw std::runtime_error("cannot determine page size");
    const auto page = static_cast<std::uint64_t>(system_page);
    const auto size = quantity(attribute(map / "size"));
    const auto offset = quantity(attribute(map / "offset"));
    const auto physical = quantity(attribute(map / "addr"));
    if (offset >= page || physical > std::numeric_limits<std::uint64_t>::max() - offset ||
        physical + offset != identity.physical_address || physical % page != 0 ||
        offset % 4 != 0 || size < offset + 256 || size % page != 0 || size > std::numeric_limits<std::size_t>::max() ||
        static_cast<std::uint64_t>(identity.map) > static_cast<std::uint64_t>(std::numeric_limits<off_t>::max()) / page)
        throw std::runtime_error("UIO aperture identity, alignment or size mismatch");
    mapping_size = static_cast<std::size_t>(size);
    register_offset = static_cast<std::size_t>(offset);
    try {
        descriptor = open(("/dev/" + identity.device).c_str(), O_RDWR | O_CLOEXEC | O_NOFOLLOW);
        if (descriptor < 0) syscall_error("open UIO");
        struct stat status{};
        if (fstat(descriptor, &status) < 0) syscall_error("stat UIO");
        const auto device_number = std::to_string(major(status.st_rdev)) + ":" + std::to_string(minor(status.st_rdev));
        if (!S_ISCHR(status.st_mode) || device_number != attribute(sysfs / "dev"))
            throw std::runtime_error("UIO character device identity mismatch");
        if (flock(descriptor, LOCK_EX | LOCK_NB) < 0) syscall_error("lock UIO");
        mapping = mmap(nullptr, mapping_size, PROT_READ | PROT_WRITE, MAP_SHARED, descriptor,
                       static_cast<off_t>(static_cast<std::uint64_t>(identity.map) * page));
        if (mapping == MAP_FAILED) {
            mapping = nullptr;
            syscall_error("map UIO");
        }
        verify_identity();
        if (quantity(attribute(map / "addr")) != physical || quantity(attribute(map / "size")) != size ||
            quantity(attribute(map / "offset")) != offset)
            throw std::runtime_error("UIO aperture changed during mapping");
        if ((read(0x98).data & 7) != 7) throw std::runtime_error("witness banks are held or not ready");
        if (read(0x7c).data != 1) throw std::runtime_error("unsupported witness register ABI");
    } catch (...) {
        close();
        throw;
    }
}

void UioDevice::close() noexcept {
    if (descriptor >= 0 && irq_managed) {
        const std::int32_t disabled = 0;
        const auto ignored = ::write(descriptor, &disabled, sizeof(disabled));
        (void)ignored;
    }
    if (mapping != nullptr) munmap(mapping, mapping_size);
    if (descriptor >= 0) ::close(descriptor);
    mapping = nullptr;
    descriptor = -1;
    irq_managed = false;
}

UioDevice::~UioDevice() { close(); }

std::uint64_t UioDevice::time() const {
    timespec stamp{};
    if (clock_gettime(CLOCK_MONOTONIC, &stamp) < 0) syscall_error("monotonic clock");
    return static_cast<std::uint64_t>(stamp.tv_sec) * 1000000000 + static_cast<std::uint64_t>(stamp.tv_nsec);
}

ProtocolReply UioDevice::read(std::uint8_t address) {
    if (address % 4 != 0) return {2, 0};
    const auto registers = reinterpret_cast<volatile std::uint32_t *>(
        static_cast<unsigned char *>(mapping) + register_offset);
    mmio_fence();
    const std::uint32_t value = registers[address / 4];
    mmio_fence();
    return {0, le32toh(value)};
}

ProtocolReply UioDevice::write(std::uint8_t address, std::uint32_t data, std::uint8_t strobes) {
    if (address % 4 != 0 || strobes != 15) return {2, 0};
    const auto registers = reinterpret_cast<volatile std::uint32_t *>(
        static_cast<unsigned char *>(mapping) + register_offset);
    mmio_fence();
    registers[address / 4] = htole32(data);
    mmio_fence();
    return {0, 0};
}

void UioDevice::advance(std::uint64_t nanoseconds) {
    timespec delay{static_cast<time_t>(nanoseconds / 1000000000), static_cast<long>(nanoseconds % 1000000000)};
    while (nanosleep(&delay, &delay) < 0) {
        if (errno != EINTR) syscall_error("nanosleep");
    }
}

void UioDevice::irq_control(std::int32_t enabled) {
    const auto count = ::write(descriptor, &enabled, sizeof(enabled));
    if (count < 0) syscall_error("UIO IRQ control");
    if (count != static_cast<ssize_t>(sizeof(enabled))) throw std::runtime_error("short UIO IRQ control write");
    irq_managed = true;
}

bool UioDevice::wait_interrupt(std::uint64_t nanoseconds) {
    irq_control(1);
    pollfd event{descriptor, POLLIN, 0};
    const timespec timeout{static_cast<time_t>(nanoseconds / 1000000000), static_cast<long>(nanoseconds % 1000000000)};
    const int result = ppoll(&event, 1, &timeout, nullptr);
    if (result < 0) syscall_error("UIO IRQ wait");
    if (result == 0) return false;
    if (event.revents != POLLIN) throw std::runtime_error("UIO IRQ descriptor error");
    const auto count = ::read(descriptor, &interrupt_count, sizeof(interrupt_count));
    if (count < 0) syscall_error("UIO IRQ count");
    if (count != static_cast<ssize_t>(sizeof(interrupt_count))) throw std::runtime_error("short UIO IRQ count read");
    return true;
}
} // namespace witness
