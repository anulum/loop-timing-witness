// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — stable regular file SHA-256 acquisition

#include "file_digest.h"
#include <array>
#include <cerrno>
#include <fcntl.h>
#include <memory>
#include <openssl/evp.h>
#include <stdexcept>
#if !defined(OPENSSL_VERSION_MAJOR) || OPENSSL_VERSION_MAJOR < 3
#error "native artifact receipts require OpenSSL 3 or later"
#endif
#include <sys/stat.h>
#include <unistd.h>

namespace witness {
namespace {
/** Own the read descriptor during digest construction and exceptions. */
struct Descriptor {
    int value;
    ~Descriptor() {
        if (value >= 0)
            ::close(value);
    }
};
/** Compare identity and modification metadata of one opened regular file. */
bool unchanged(const struct stat &before, const struct stat &after) {
    return before.st_dev == after.st_dev && before.st_ino == after.st_ino &&
           before.st_size == after.st_size && before.st_mtim.tv_sec == after.st_mtim.tv_sec &&
           before.st_mtim.tv_nsec == after.st_mtim.tv_nsec &&
           before.st_ctim.tv_sec == after.st_ctim.tv_sec &&
           before.st_ctim.tv_nsec == after.st_ctim.tv_nsec;
}
} // namespace
FileDigest file_digest(const char *path) {
    Descriptor file{::open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)};
    struct stat before {
    }, after{}, named{};
    if (file.value < 0 || fstat(file.value, &before) != 0 || !S_ISREG(before.st_mode) ||
        before.st_size < 0)
        throw std::runtime_error("cannot hash actual regular artifact");
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> context(EVP_MD_CTX_new(),
                                                                    EVP_MD_CTX_free);
    if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1)
        throw std::runtime_error("cannot initialize native SHA-256");
    std::array<unsigned char, 65536> buffer{};
    FileDigest result;
    for (;;) {
        const auto count = ::read(file.value, buffer.data(), buffer.size());
        if (count < 0 && errno == EINTR)
            continue;
        if (count < 0)
            throw std::runtime_error("cannot read native artifact bytes");
        if (!count)
            break;
        const auto bytes = static_cast<std::size_t>(count);
        if (EVP_DigestUpdate(context.get(), buffer.data(), bytes) != 1)
            throw std::runtime_error("cannot hash native artifact bytes");
        result.bytes += static_cast<std::uint64_t>(bytes);
        if (result.bytes > static_cast<std::uint64_t>(before.st_size))
            throw std::runtime_error("native artifact grew during hashing");
    }
    unsigned size = 0;
    std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
    if (EVP_DigestFinal_ex(context.get(), digest.data(), &size) != 1 || size != 32)
        throw std::runtime_error("cannot finalize native SHA-256");
    if (fstat(file.value, &after) != 0 || lstat(path, &named) != 0 || !unchanged(before, after) ||
        !unchanged(before, named) || result.bytes != static_cast<std::uint64_t>(before.st_size))
        throw std::runtime_error("native artifact changed during hashing");
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned index = 0; index < size; ++index) {
        result.sha256 += hex[digest[index] >> 4];
        result.sha256 += hex[digest[index] & 15];
    }
    return result;
}
void verify_digest(const char *path, const FileDigest &original) {
    const auto actual = file_digest(path);
    if (actual.sha256 != original.sha256 || actual.bytes != original.bytes)
        throw std::runtime_error("native configuration changed during execution");
}
} // namespace witness
