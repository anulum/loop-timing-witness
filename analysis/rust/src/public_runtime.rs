// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — verified source-checker runtime installation

//! Verify complete caller-selected installations before fixed source-checker operations.

use crate::files::{FileRef, decode, digest};
use crate::public_policy::same;
use serde::Deserialize;
use std::collections::BTreeSet;
use std::fs::OpenOptions;
use std::io::Read;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};

/// One reviewed runtime file, with an installation path supplied by the consumer.
pub struct InstalledFile {
    /// Portable role in the selected runtime descriptor.
    pub name: String,
    /// Actual resolved regular file in the consumer's selected installation.
    pub path: PathBuf,
    /// Expected complete lowercase SHA-256.
    pub sha256: String,
    /// Exact expected file length.
    pub byte_length: u64,
}

impl InstalledFile {
    /// Return the portable descriptor identity without exposing a host executable selector.
    pub(crate) fn reference(&self) -> FileRef {
        FileRef {
            path: self.name.clone(),
            sha256: self.sha256.clone(),
            byte_length: self.byte_length,
        }
    }

    /// Verify complete file bytes through a finite nonblocking no-follow descriptor.
    pub fn verify(&self) -> Result<(), String> {
        if self.byte_length > 256 * 1024 * 1024 {
            return Err("Selected checker runtime file exceeds its allocation.".into());
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(0o400000 | 0o4000)
            .open(&self.path)
            .map_err(|_| "Selected checker runtime file is unavailable.".to_owned())?;
        if !file
            .metadata()
            .map_err(|_| "Cannot inspect selected checker runtime file.".to_owned())?
            .is_file()
        {
            return Err("Selected checker runtime requires a regular resolved file.".into());
        }
        let mut raw = Vec::new();
        file.take(self.byte_length + 1)
            .read_to_end(&mut raw)
            .map_err(|_| "Selected checker runtime file is unavailable.".to_owned())?;
        if raw.len() as u64 != self.byte_length || digest(&raw) != self.sha256 {
            return Err("Selected checker runtime file differs from its reviewed binding.".into());
        }
        Ok(())
    }
}

/// Closed finite-resource contract implemented by the exact selected worker.
#[derive(Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ExecutionContract {
    profile: String,
    address_space_bytes: u64,
    cpu_seconds: u64,
    pub wall_seconds: u64,
    file_bytes: u64,
    python_site_initialisation: bool,
    bytecode_writes: bool,
    bytecode_reads: String,
}

impl ExecutionContract {
    /// Require the actual fixed worker limits, never a receipt-selected alternative.
    fn valid(&self) -> bool {
        self.profile == "linux-x86_64-seccomp-no-network.v1"
            && self.address_space_bytes == 805306368
            && self.cpu_seconds == 30
            && self.wall_seconds == 45
            && self.file_bytes == 1048576
            && !self.python_site_initialisation
            && !self.bytecode_writes
            && self.bytecode_reads == "owned-empty-prefix"
    }
}

/// Exact external platform boundary selected for this finite process profile.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Platform {
    id: String,
    system: String,
    machine: String,
    kernel_release: String,
}

/// Complete closed runtime descriptor, independent of acquisition code selection.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Runtime {
    schema_id: String,
    pub interpreter: FileRef,
    pub tracer: FileRef,
    import_namespaces: Vec<String>,
    pub worker_sources: Vec<FileRef>,
    pub files: Vec<FileRef>,
    platform_baseline: Platform,
    pub execution_contract: ExecutionContract,
}

/// The exact worker roles every selected runtime binds, relative to the worker root.
const WORKERS: [&str; 3] = [
    "loop_timing_witness/__init__.py",
    "loop_timing_witness/neural_checker_worker.py",
    "loop_timing_witness/neural_checker_isolation.py",
];

/// An external verified package or an owned copy of its exact reviewed source bytes.
enum WorkerRoot {
    External(PathBuf),
    Embedded(crate::public_temporary::OwnedDirectory),
}

/// Verified installation attached only to a consumer-owned source registration.
pub struct Installation {
    pub(crate) contract_bytes: Vec<u8>,
    pub(crate) runtime: Runtime,
    pub(crate) files: Vec<InstalledFile>,
    pub(crate) import_roots: Vec<PathBuf>,
    worker_root: WorkerRoot,
}

impl Installation {
    /// Bind a complete selected descriptor and consumer-supplied physical installation.
    ///
    /// This verifies installation correspondence only. It does not admit a source
    /// policy, authenticate a producer or establish physical timing.
    ///
    /// # Errors
    ///
    /// Refuses unknown roles, duplicate paths, changed bytes, unsupported platform,
    /// worker sources or execution limits, and nonregular or unavailable files.
    pub fn from_selected_contract(
        contract_bytes: Vec<u8>,
        files: Vec<InstalledFile>,
        import_roots: Vec<PathBuf>,
        worker_import_root: PathBuf,
    ) -> Result<Self, String> {
        let runtime = decode(&contract_bytes, "selected checker runtime descriptor")?;
        let installation = Self {
            contract_bytes,
            runtime,
            files,
            import_roots,
            worker_root: WorkerRoot::External(worker_import_root),
        };
        installation.verify()?;
        Ok(installation)
    }

    /// Bind a complete selected descriptor and an owned copy of exact worker sources.
    ///
    /// Each worker body is checked against the descriptor before it is written to
    /// a new owned directory, so no external analyzer package is required. The
    /// owned copy is removed with the installation.
    ///
    /// # Errors
    ///
    /// Refuses a worker population, role or body that differs from the descriptor,
    /// an unwritable owned copy, and everything [`Self::from_selected_contract`] refuses.
    pub fn with_embedded_workers(
        contract_bytes: Vec<u8>,
        files: Vec<InstalledFile>,
        import_roots: Vec<PathBuf>,
        workers: &[(&str, &[u8])],
    ) -> Result<Self, String> {
        let runtime: Runtime = decode(&contract_bytes, "selected embedded-worker descriptor")?;
        if workers.len() != runtime.worker_sources.len() {
            return Err("Embedded checker worker source population differs.".into());
        }
        for (name, body) in workers {
            let expected = runtime
                .worker_sources
                .iter()
                .find(|reference| reference.path == *name)
                .filter(|_| WORKERS.contains(name))
                .ok_or("Embedded checker worker role is not admitted.")?;
            if body.len() as u64 != expected.byte_length || digest(body) != expected.sha256 {
                return Err(
                    "Embedded checker worker body differs from its reviewed binding.".into(),
                );
            }
        }
        let owned = crate::public_temporary::OwnedDirectory::create(
            &std::env::temp_dir(),
            "neural-worker-",
        )?;
        std::fs::create_dir(owned.path.join("loop_timing_witness"))
            .map_err(|_| "Cannot create the owned checker worker package.".to_owned())?;
        for (name, body) in workers {
            std::fs::write(owned.path.join(name), body)
                .map_err(|_| "Cannot preserve exact embedded checker worker bytes.".to_owned())?;
        }
        let mut installation =
            Self::from_selected_contract(contract_bytes, files, import_roots, owned.path.clone())?;
        installation.worker_root = WorkerRoot::Embedded(owned);
        Ok(installation)
    }

    /// Resolve the consumer-owned location of the verified worker package.
    pub(crate) fn worker_import_root(&self) -> &Path {
        match &self.worker_root {
            WorkerRoot::External(path) => path,
            WorkerRoot::Embedded(owned) => &owned.path,
        }
    }

    /// Return the selected interpreter's verified actual installation path.
    pub(crate) fn interpreter(&self) -> Result<&Path, String> {
        self.file_path(&self.runtime.interpreter)
    }

    /// Return the selected tracer's verified actual installation path.
    pub(crate) fn tracer(&self) -> Result<&Path, String> {
        self.file_path(&self.runtime.tracer)
    }

    /// Locate one role by its full reviewed identity.
    fn file_path(&self, reference: &FileRef) -> Result<&Path, String> {
        self.files
            .iter()
            .find(|item| same(&item.reference(), reference))
            .map(|item| item.path.as_path())
            .ok_or_else(|| "Selected checker runtime omits an executable role.".into())
    }

    /// Return every exact installed runtime and consumer-worker physical path.
    pub(crate) fn observed_roles(&self) -> Vec<(FileRef, PathBuf)> {
        let mut roles: Vec<_> = self
            .files
            .iter()
            .map(|item| (item.reference(), item.path.clone()))
            .collect();
        roles.extend(
            self.runtime
                .worker_sources
                .iter()
                .map(|item| (item.clone(), self.worker_import_root().join(&item.path))),
        );
        roles
    }

    /// Reverify the entire selected process boundary before and after execution.
    pub fn verify(&self) -> Result<(), String> {
        let runtime = &self.runtime;
        let platform = &runtime.platform_baseline;
        let kernel = std::fs::read_to_string("/proc/sys/kernel/osrelease")
            .map_err(|_| "Selected checker kernel baseline is unavailable.".to_owned())?;
        let expected_namespaces: Vec<_> = (0..self.import_roots.len())
            .map(|index| format!("imports/{index}"))
            .collect();
        let expected_workers: BTreeSet<_> = WORKERS.into_iter().collect();
        let workers: BTreeSet<_> = runtime
            .worker_sources
            .iter()
            .map(|item| item.path.as_str())
            .collect();
        if runtime.schema_id != "loop-timing-witness.sc-checker-runtime.v1"
            || platform.id.is_empty()
            || cfg!(not(all(target_os = "linux", target_arch = "x86_64")))
            || platform.system != "Linux"
            || platform.machine != "x86_64"
            || platform.kernel_release != kernel.trim_end()
            || !runtime.execution_contract.valid()
            || self.files.is_empty()
            || self.files.len() > 4096
            || self.files.len() != runtime.files.len()
            || self.import_roots.is_empty()
            || runtime.import_namespaces != expected_namespaces
            || workers != expected_workers
            || runtime.worker_sources.len() != 3
        {
            return Err("Selected checker runtime inventory or platform baseline differs.".into());
        }
        let mut names = BTreeSet::new();
        let mut paths = BTreeSet::new();
        for item in &self.files {
            if !names.insert(item.name.clone())
                || !paths.insert(item.path.clone())
                || !runtime
                    .files
                    .iter()
                    .any(|reference| same(reference, &item.reference()))
            {
                return Err(
                    "Selected checker runtime inventory or platform baseline differs.".into(),
                );
            }
            item.verify()?;
        }
        self.interpreter()?;
        self.tracer()?;
        for directory in self
            .import_roots
            .iter()
            .map(PathBuf::as_path)
            .chain([self.worker_import_root()])
        {
            let metadata = std::fs::symlink_metadata(directory)
                .map_err(|_| "Selected checker runtime import roots are unavailable.".to_owned())?;
            // The metadata does not follow links, so a symlink is not a directory.
            if !metadata.is_dir() {
                return Err("Selected checker runtime import roots are unavailable.".into());
            }
        }
        for reference in &runtime.worker_sources {
            let path = self.worker_import_root().join(&reference.path);
            if !names.insert(reference.path.clone()) || !paths.insert(path.clone()) {
                return Err("Selected checker worker/runtime roles contain an alias.".into());
            }
            InstalledFile {
                name: reference.path.clone(),
                path,
                sha256: reference.sha256.clone(),
                byte_length: reference.byte_length,
            }
            .verify()?;
        }
        Ok(())
    }
}
