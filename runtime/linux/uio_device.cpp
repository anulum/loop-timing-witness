// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Linux UIO map and IRQ implementation

#include "uio_device.h"
#include "../refusal.h"

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
    throw witness::RuntimeRefused(std::string(operation) + " (errno " + std::to_string(errno) +
                                  ")");
}

/** Read one whole sysfs text value; refuse truncation, extra rows or embedded NUL. */
std::string attribute(const std::filesystem::path &path) {
    std::ifstream stream(path);
    std::string value, extra;
    if (!stream || !std::getline(stream, value) || value.find('\0') != std::string::npos ||
        std::getline(stream, extra) || !stream.eof())
        throw witness::RuntimeRefused("cannot read sysfs attribute: " + path.string());
    return value;
}

/** Parse sysfs hex or decimal quantities without signs, whitespace or narrowing. */
std::uint64_t quantity(const std::string &value) {
    const bool hex = value.size() > 2 && value.substr(0, 2) == "0x";
    const std::string digits = value.substr(hex ? 2 : 0);
    if (digits.empty() || digits.find_first_not_of(hex ? "0123456789abcdefABCDEF" : "0123456789") !=
                              std::string::npos)
        throw witness::RuntimeRefused("invalid sysfs number");
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

/** One verified, exclusively locked and mapped UIO aperture. */
struct MappedAperture {
    int descriptor = -1;
    void *mapping = nullptr;
    std::size_t size = 0;
    std::size_t offset = 0;
};

/** Verify a UIO device's sysfs, driver and character-device identity, lock it, map its
 * page-aligned map holding `window` register bytes at the identity's physical address, and verify
 * the identity again after mapping; release everything on refusal. A map that reaches past its
 * 4 KiB register page is refused, so the run page's map never covers the fault page. */
MappedAperture map_aperture(const UioIdentity &identity, std::uint64_t window) {
    if (identity.device.size() < 4 || identity.device.substr(0, 3) != "uio" ||
        identity.device.substr(3).find_first_not_of("0123456789") != std::string::npos ||
        identity.name.empty() || identity.version.empty())
        throw witness::RuntimeRefused("invalid UIO identity");
    const auto sysfs = std::filesystem::path("/sys/class/uio") / identity.device;
    const auto map = sysfs / "maps" / ("map" + std::to_string(identity.map));
    const auto verify_identity = [&]() {
        if (attribute(sysfs / "name") != identity.name ||
            attribute(sysfs / "version") != identity.version ||
            std::filesystem::canonical(sysfs / "device/driver").filename() != "uio_pdrv_genirq")
            throw witness::RuntimeRefused("UIO name, version or platform driver mismatch");
    };
    verify_identity();
    const long system_page = sysconf(_SC_PAGESIZE);
    if (system_page <= 0)
        throw witness::RuntimeRefused("cannot determine page size");
    const auto page = static_cast<std::uint64_t>(system_page);
    const auto size = quantity(attribute(map / "size"));
    const auto offset = quantity(attribute(map / "offset"));
    const auto physical = quantity(attribute(map / "addr"));
    if (offset >= page || physical > std::numeric_limits<std::uint64_t>::max() - offset ||
        physical + offset != identity.physical_address || physical % page != 0 || offset % 4 != 0 ||
        size < offset + window || size > offset + fault_page || size % page != 0 ||
        size > std::numeric_limits<std::size_t>::max() ||
        static_cast<std::uint64_t>(identity.map) >
            static_cast<std::uint64_t>(std::numeric_limits<off_t>::max()) / page)
        throw witness::RuntimeRefused("UIO aperture identity, alignment or size mismatch");
    MappedAperture aperture;
    aperture.size = static_cast<std::size_t>(size);
    aperture.offset = static_cast<std::size_t>(offset);
    try {
        aperture.descriptor =
            open(("/dev/" + identity.device).c_str(), O_RDWR | O_CLOEXEC | O_NOFOLLOW);
        if (aperture.descriptor < 0)
            syscall_error("open UIO");
        struct stat status{};
        if (fstat(aperture.descriptor, &status) < 0)
            syscall_error("stat UIO");
        const auto device_number =
            std::to_string(major(status.st_rdev)) + ":" + std::to_string(minor(status.st_rdev));
        if (!S_ISCHR(status.st_mode) || device_number != attribute(sysfs / "dev"))
            throw witness::RuntimeRefused("UIO character device identity mismatch");
        if (flock(aperture.descriptor, LOCK_EX | LOCK_NB) < 0)
            syscall_error("lock UIO");
        aperture.mapping =
            mmap(nullptr, aperture.size, PROT_READ | PROT_WRITE, MAP_SHARED, aperture.descriptor,
                 static_cast<off_t>(static_cast<std::uint64_t>(identity.map) * page));
        if (aperture.mapping == MAP_FAILED) {
            aperture.mapping = nullptr;
            syscall_error("map UIO");
        }
        verify_identity();
        if (quantity(attribute(map / "addr")) != physical ||
            quantity(attribute(map / "size")) != size ||
            quantity(attribute(map / "offset")) != offset)
            throw witness::RuntimeRefused("UIO aperture changed during mapping");
    } catch (...) {
        if (aperture.mapping != nullptr)
            munmap(aperture.mapping, aperture.size);
        if (aperture.descriptor >= 0)
            ::close(aperture.descriptor);
        throw;
    }
    return aperture;
}

/** One aligned little-endian volatile 32-bit load or store at a register offset of a mapping. */
volatile std::uint32_t *register_word(void *mapping, std::size_t offset, std::uint16_t address) {
    return reinterpret_cast<volatile std::uint32_t *>(static_cast<unsigned char *>(mapping) +
                                                      offset) +
           address / 4;
}
} // namespace

UioDevice::UioDevice(const UioIdentity &identity) {
    const auto aperture = map_aperture(identity, 256);
    descriptor = aperture.descriptor;
    mapping = aperture.mapping;
    mapping_size = aperture.size;
    register_offset = aperture.offset;
    try {
        if ((read(0x98).data & 7) != 7)
            throw witness::RuntimeRefused("witness banks are held or not ready");
        if (read(0x7c).data != 2)
            throw witness::RuntimeRefused("unsupported witness register ABI");
    } catch (...) {
        close();
        throw;
    }
}

void UioDevice::open_fault_page(const UioIdentity &identity) {
    if (fault_mapping != nullptr)
        throw witness::RuntimeRefused("fault page is already mapped");
    const auto aperture = map_aperture(identity, 16);
    fault_descriptor = aperture.descriptor;
    fault_mapping = aperture.mapping;
    fault_size = aperture.size;
    fault_offset = aperture.offset;
}

void UioDevice::close_fault_page() noexcept {
    if (fault_mapping != nullptr)
        munmap(fault_mapping, fault_size);
    if (fault_descriptor >= 0)
        ::close(fault_descriptor);
    fault_mapping = nullptr;
    fault_descriptor = -1;
}

void UioDevice::close() noexcept {
    close_fault_page();
    if (descriptor >= 0 && irq_managed) {
        const std::int32_t disabled = 0;
        const auto ignored = ::write(descriptor, &disabled, sizeof(disabled));
        (void)ignored;
    }
    if (mapping != nullptr)
        munmap(mapping, mapping_size);
    if (descriptor >= 0)
        ::close(descriptor);
    mapping = nullptr;
    descriptor = -1;
    irq_managed = false;
}

UioDevice::~UioDevice() { close(); }

std::uint64_t UioDevice::time() const {
    timespec stamp{};
    if (clock_gettime(CLOCK_MONOTONIC, &stamp) < 0)
        syscall_error("monotonic clock");
    return static_cast<std::uint64_t>(stamp.tv_sec) * 1000000000 +
           static_cast<std::uint64_t>(stamp.tv_nsec);
}

ProtocolReply UioDevice::read(std::uint16_t address) {
    if (address % 4 != 0 ||
        (address >= 0x100 &&
         (fault_mapping == nullptr || address < fault_page || address >= fault_page + 0x10)))
        return {2, 0};
    const auto word = address < 0x100
                          ? register_word(mapping, register_offset, address)
                          : register_word(fault_mapping, fault_offset,
                                          static_cast<std::uint16_t>(address - fault_page));
    mmio_fence();
    const std::uint32_t value = *word;
    mmio_fence();
    return {0, le32toh(value)};
}

ProtocolReply UioDevice::write(std::uint16_t address, std::uint32_t data, std::uint8_t strobes) {
    if (address % 4 != 0 || strobes != 15 ||
        (address >= 0x100 &&
         (fault_mapping == nullptr || address < fault_page || address >= fault_page + 0x10)))
        return {2, 0};
    if (address == 0x38)
        close_fault_page();
    const auto word = address < 0x100
                          ? register_word(mapping, register_offset, address)
                          : register_word(fault_mapping, fault_offset,
                                          static_cast<std::uint16_t>(address - fault_page));
    mmio_fence();
    *word = htole32(data);
    mmio_fence();
    return {0, 0};
}

void UioDevice::advance(std::uint64_t nanoseconds) {
    timespec delay{static_cast<time_t>(nanoseconds / 1000000000),
                   static_cast<long>(nanoseconds % 1000000000)};
    while (nanosleep(&delay, &delay) < 0) {
        if (errno != EINTR)
            syscall_error("nanosleep");
    }
}

void UioDevice::irq_control(std::int32_t enabled) {
    const auto count = ::write(descriptor, &enabled, sizeof(enabled));
    if (count < 0)
        syscall_error("UIO IRQ control");
    if (count != static_cast<ssize_t>(sizeof(enabled)))
        throw witness::RuntimeRefused("short UIO IRQ control write");
    irq_managed = true;
}

bool UioDevice::wait_interrupt(std::uint64_t nanoseconds) {
    irq_control(1);
    pollfd event{descriptor, POLLIN, 0};
    const timespec timeout{static_cast<time_t>(nanoseconds / 1000000000),
                           static_cast<long>(nanoseconds % 1000000000)};
    const int result = ppoll(&event, 1, &timeout, nullptr);
    if (result < 0)
        syscall_error("UIO IRQ wait");
    if (result == 0)
        return false;
    if (event.revents != POLLIN)
        throw witness::RuntimeRefused("UIO IRQ descriptor error");
    const auto count = ::read(descriptor, &interrupt_count, sizeof(interrupt_count));
    if (count < 0)
        syscall_error("UIO IRQ count");
    if (count != static_cast<ssize_t>(sizeof(interrupt_count)))
        throw witness::RuntimeRefused("short UIO IRQ count read");
    return true;
}
} // namespace witness
