// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native artifact content receipts

/** @file file_digest.h
 * native artifact content receipts.
 */

#ifndef WITNESS_FILE_DIGEST_H
#define WITNESS_FILE_DIGEST_H
#include <cstdint>
#include <string>
#include <vector>

namespace witness {
/** Digest and exact byte count of one stable regular file. */
struct FileDigest {
    std::string sha256;
    std::uint64_t bytes = 0;
};
/** Named artifact digest; role names are internal fixed literals. */
struct ArtifactDigest {
    const char *role;
    FileDigest digest;
};
/** Hash actual bytes with OpenSSL EVP, refusing symlinks and concurrent file changes. */
FileDigest file_digest(const char *path);
/** Require a configuration to retain its original bytes across parsing and execution. */
void verify_digest(const char *path, const FileDigest &original);
} // namespace witness
/** @var witness::ArtifactDigest::role
 * Fixed role identifying the artifact in the receipt.
 */
/** @var witness::ArtifactDigest::digest
 * Observed SHA-256 digest and exact byte count.
 */
/** @var witness::FileDigest::sha256
 * Lowercase SHA-256 hexadecimal digest of stable file bytes.
 */
/** @var witness::FileDigest::bytes
 * Observed stable regular-file size in bytes.
 */

#endif
