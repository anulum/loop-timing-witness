// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — immutable source-checker image executor

//! Run the admitted source checker inside a verified read-only executor image.
//!
//! The consumer binds every image file, directory and link, the host launcher
//! files and required absences, and verifies them before and after each
//! operation. Only the image root, the owned working directory and the fixed
//! operation are substituted into the source owner's launcher command.

use crate::files::{FileRef, decode, digest};
use crate::public_execution::{Invocation, run_group};
use crate::public_runtime::{ExecutionContract, Installation, InstalledFile, Runtime};
use serde::Deserialize;
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};
use std::fs::OpenOptions;
use std::io::Read;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::time::Duration;

/// Versioned consumer executor binding identity.
pub(crate) const SCHEMA: &str = "loop-timing-witness.sc-checker-image-executor.v1";
const PLACEHOLDERS: [&str; 3] = ["{image_root}", "{work_directory}", "{operation}"];
const WORK_DATA: [&str; 4] = [
    "stimuli.txt",
    "results_expected.txt",
    "results_verilog.txt",
    "checker-observation.json",
];

/// One host launcher or loader file with its exact identity.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HostFile {
    path: PathBuf,
    sha256: String,
    byte_length: u64,
}

/// Explicit host kernel, account, launcher files and required absences.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Host {
    system: String,
    machine: String,
    kernel_release: String,
    uid: u32,
    gid: u32,
    files: Vec<HostFile>,
    absent_paths: Vec<PathBuf>,
}

/// One bound image file.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ImageFile {
    path: String,
    sha256: String,
    byte_length: u64,
    mode: u32,
}

/// One bound image symbolic link.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ImageLink {
    path: String,
    target: String,
}

/// Complete image inventory.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Image {
    files: Vec<ImageFile>,
    directories: Vec<String>,
    symlinks: Vec<ImageLink>,
}

/// Closed consumer executor binding.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Binding {
    schema_id: String,
    #[serde(rename = "supplier")]
    _supplier: serde::de::IgnoredAny,
    #[serde(rename = "historical_contracts")]
    _historical_contracts: serde::de::IgnoredAny,
    command: Vec<String>,
    bootstrap_environment: BTreeMap<String, String>,
    deadline_seconds: u64,
    host_boundary: Host,
    image: Image,
    source_files: Vec<String>,
    worker_files: Vec<String>,
}

/// Consumer-selected immutable checker image with its fixed launcher contract.
pub(crate) struct ImageExecutor {
    root: PathBuf,
    binding_digest: String,
    binding: Binding,
    pub(crate) contract_bytes: Vec<u8>,
    pub(crate) runtime: Runtime,
}

/// Require each placeholder to be a whole value and no other braces.
fn closed<'a>(mut values: impl Iterator<Item = &'a String>) -> bool {
    values.all(|value| PLACEHOLDERS.contains(&value.as_str()) || !value.contains('{'))
}

impl ImageExecutor {
    /// Decode and close the binding and historical runtime contract.
    pub(crate) fn new(
        root: PathBuf,
        binding_bytes: &[u8],
        contract_bytes: Vec<u8>,
    ) -> Result<Self, String> {
        let binding: Binding = decode(binding_bytes, "checker image executor binding")?;
        let runtime: Runtime = decode(&contract_bytes, "checker image historical runtime")?;
        if binding.schema_id != SCHEMA
            || binding.command.is_empty()
            || !closed(binding.command.iter())
            || !closed(binding.bootstrap_environment.values())
            || !(1..=300).contains(&binding.deadline_seconds)
            || binding.source_files.is_empty()
            || binding.worker_files.is_empty()
        {
            return Err("Checker image executor binding is not its closed reviewed form.".into());
        }
        Ok(Self {
            root,
            binding_digest: digest(binding_bytes),
            binding,
            contract_bytes,
            runtime,
        })
    }

    /// Return the historical runtime and worker roles original receipts observed.
    pub(crate) fn references(&self) -> Vec<FileRef> {
        self.runtime
            .files
            .iter()
            .chain(&self.runtime.worker_sources)
            .cloned()
            .collect()
    }

    /// Verify the host launcher boundary and the complete image inventory.
    pub(crate) fn verify(&self) -> Result<(), String> {
        self.verify_host()?;
        self.verify_image()
    }

    /// Verify the explicit host kernel, account, launcher files and absences.
    fn verify_host(&self) -> Result<(), String> {
        let host = &self.binding.host_boundary;
        let kernel = std::fs::read_to_string("/proc/sys/kernel/osrelease")
            .map_err(|_| "Checker image host platform or account differs from its boundary.")?;
        if !cfg!(all(target_os = "linux", target_arch = "x86_64"))
            || host.system != "Linux"
            || host.machine != "x86_64"
            || host.kernel_release != kernel.trim_end()
            || rustix::process::getuid().as_raw() != host.uid
            || rustix::process::getgid().as_raw() != host.gid
        {
            return Err("Checker image host platform or account differs from its boundary.".into());
        }
        for item in &host.files {
            InstalledFile {
                name: item.path.display().to_string(),
                path: item.path.clone(),
                sha256: item.sha256.clone(),
                byte_length: item.byte_length,
            }
            .verify()?;
        }
        if host
            .absent_paths
            .iter()
            .any(|path| std::fs::symlink_metadata(path).is_ok())
        {
            return Err("Checker image host contains a path its boundary requires absent.".into());
        }
        Ok(())
    }

    /// Verify that the image tree holds exactly the bound entries and bytes.
    fn verify_image(&self) -> Result<(), String> {
        let metadata = std::fs::symlink_metadata(&self.root)
            .map_err(|_| "Checker image root must be an absolute real directory.")?;
        if !self.root.is_absolute() || !metadata.is_dir() {
            return Err("Checker image root must be an absolute real directory.".into());
        }
        let mut files = BTreeSet::new();
        let mut directories = BTreeSet::new();
        let mut links = BTreeMap::new();
        walk(&self.root, "", &mut files, &mut directories, &mut links)?;
        let image = &self.binding.image;
        let expected_files: BTreeSet<_> =
            image.files.iter().map(|item| item.path.clone()).collect();
        let expected_directories: BTreeSet<_> = image.directories.iter().cloned().collect();
        if files != expected_files || directories != expected_directories {
            return Err("Checker image entries differ from the bound image inventory.".into());
        }
        let expected_links: BTreeMap<_, _> = image
            .symlinks
            .iter()
            .map(|item| (item.path.clone(), item.target.clone()))
            .collect();
        if links != expected_links {
            return Err("Checker image links differ from the bound image inventory.".into());
        }
        for item in &image.files {
            image_file(&self.root.join(&item.path), item)?;
        }
        Ok(())
    }

    /// Run one fixed operation in the image and verify it stayed unchanged.
    pub(crate) fn invoke(&self, operation: &str, directory: &Path) -> Result<Invocation, String> {
        if !["generate", "check"].contains(&operation) {
            return Err("Unsupported fixed source-checker operation.".into());
        }
        self.verify()?;
        let text = |path: &Path| -> Result<String, String> {
            path.to_str()
                .map(str::to_owned)
                .ok_or_else(|| "Checker path requires exact UTF-8.".into())
        };
        let values: BTreeMap<&str, String> = [
            ("{image_root}", text(&self.root)?),
            ("{work_directory}", text(directory)?),
            ("{operation}", operation.to_owned()),
        ]
        .into_iter()
        .collect();
        let substitute = |item: &String| values.get(item.as_str()).cloned().unwrap_or(item.clone());
        let command: Vec<String> = self.binding.command.iter().map(substitute).collect();
        let environment: BTreeMap<String, String> = self
            .binding
            .bootstrap_environment
            .iter()
            .map(|(key, value)| (key.clone(), substitute(value)))
            .collect();
        let name = directory
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or("Checker path requires exact UTF-8.")?;
        let parent = directory
            .parent()
            .ok_or("Checker operation directory has no owned parent.")?;
        let completed = run_group(
            &command,
            directory,
            environment.clone(),
            (
                &parent.join(format!("{name}.stdout")),
                &parent.join(format!("{name}.stderr")),
            ),
            Duration::from_secs(self.binding.deadline_seconds),
        )?;
        self.verify()?;
        let boundary = crate::public_report::canonical(&json!({
            "schema_id": "loop-timing-witness.sc-checker-image-boundary.v1",
            "executor_binding_sha256": self.binding_digest,
            "image_and_host_boundary": "verified-before-and-after",
            "environment": environment,
        }))?;
        Ok(completed.into_invocation(command, boundary))
    }

    /// Compare loaded files and SC modules with the image and admitted source closure.
    pub(crate) fn findings(&self, actual: &Invocation, digests: &[String]) -> Vec<String> {
        let Some(observation) = &actual.observation else {
            return vec!["Actual source checker opened-file observation is unavailable.".into()];
        };
        let files: BTreeMap<_, _> = self
            .binding
            .image
            .files
            .iter()
            .map(|item| (item.path.as_str(), item))
            .collect();
        let sources: BTreeSet<_> = self
            .binding
            .source_files
            .iter()
            .map(String::as_str)
            .collect();
        let mut failures = Vec::new();
        let mut image_digests: Vec<_> = sources
            .iter()
            .filter_map(|path| files.get(path).map(|item| item.sha256.clone()))
            .collect();
        let mut admitted = digests.to_vec();
        image_digests.sort();
        admitted.sort();
        if image_digests != admitted {
            failures.push("Checker image source closure differs from the admitted sources.".into());
        }
        let mut observed = BTreeSet::new();
        let mut outside = false;
        for record in &observation.files {
            let path = Path::new(&record.path);
            if path.parent() == Some(Path::new("/work"))
                && path
                    .file_name()
                    .and_then(|value| value.to_str())
                    .is_some_and(|value| WORK_DATA.contains(&value))
            {
                continue;
            }
            let relative = record.path.strip_prefix('/').unwrap_or(&record.path);
            if !path.is_absolute()
                || files.get(relative).is_none_or(|item| {
                    item.sha256 != record.sha256 || item.byte_length != record.byte_length
                })
            {
                outside = true;
            }
            observed.insert(relative);
        }
        if !sources.is_subset(&observed) {
            failures.push(
                "Actual source checker did not open its complete admitted source closure.".into(),
            );
        }
        if outside {
            failures.push(
                "Actual source checker opened a file outside its complete runtime binding.".into(),
            );
        }
        if observation.modules.iter().any(|item| {
            item.name.starts_with("sc_neurocore")
                && !sources.contains(item.path.strip_prefix('/').unwrap_or(&item.path))
        }) {
            failures.push(
                "Actual source checker imported a live or unbound SC source fallback.".into(),
            );
        }
        failures
    }
}

/// Collect every entry under one image directory without following links.
fn walk(
    root: &Path,
    prefix: &str,
    files: &mut BTreeSet<String>,
    directories: &mut BTreeSet<String>,
    links: &mut BTreeMap<String, String>,
) -> Result<(), String> {
    let entries = std::fs::read_dir(root.join(prefix))
        .map_err(|_| "Checker image entries differ from the bound image inventory.")?;
    for entry in entries {
        let entry =
            entry.map_err(|_| "Checker image entries differ from the bound image inventory.")?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| "Checker path requires exact UTF-8.")?;
        let relative = if prefix.is_empty() {
            name
        } else {
            format!("{prefix}/{name}")
        };
        let kind = entry
            .file_type()
            .map_err(|_| "Checker image entries differ from the bound image inventory.")?;
        if kind.is_symlink() {
            let target = std::fs::read_link(entry.path())
                .map_err(|_| "Checker image links differ from the bound image inventory.")?;
            links.insert(
                relative,
                target
                    .into_os_string()
                    .into_string()
                    .map_err(|_| "Checker path requires exact UTF-8.")?,
            );
        } else if kind.is_dir() {
            directories.insert(relative.clone());
            walk(root, &relative, files, directories, links)?;
        } else {
            files.insert(relative);
        }
    }
    Ok(())
}

/// Verify one image file's type, mode, length and digest without following links.
fn image_file(path: &Path, item: &ImageFile) -> Result<(), String> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(0o400000 | 0o4000)
        .open(path)
        .map_err(|_| "Checker image file is unavailable.")?;
    let metadata = file
        .metadata()
        .map_err(|_| "Checker image file is unavailable.")?;
    if !metadata.is_file()
        || metadata.permissions().mode() & 0o7777 != item.mode
        || metadata.len() != item.byte_length
        || metadata.len() > 256 * 1024 * 1024
    {
        return Err("Checker image file type, mode or length differs from its binding.".into());
    }
    let mut raw = Vec::new();
    file.take(item.byte_length + 1)
        .read_to_end(&mut raw)
        .map_err(|_| "Checker image file is unavailable.")?;
    if raw.len() as u64 != item.byte_length || digest(&raw) != item.sha256 {
        return Err("Checker image file bytes differ from its binding.".into());
    }
    Ok(())
}

/// A consumer registration's executor: a verified host installation or an image.
pub(crate) enum Executor {
    /// Reviewed host interpreter, tracer and import roots.
    Host(Box<Installation>),
    /// Source owner's qualified immutable executor image.
    Image(Box<ImageExecutor>),
}

impl Executor {
    /// Return the exact runtime contract the acquisition must carry.
    pub(crate) fn contract_bytes(&self) -> &[u8] {
        match self {
            Self::Host(installation) => &installation.contract_bytes,
            Self::Image(image) => &image.contract_bytes,
        }
    }

    /// Return the declared finite execution contract.
    pub(crate) fn execution_contract(&self) -> &ExecutionContract {
        match self {
            Self::Host(installation) => &installation.runtime.execution_contract,
            Self::Image(image) => &image.runtime.execution_contract,
        }
    }

    /// Return the runtime and worker roles original receipts must observe.
    pub(crate) fn references(&self) -> Vec<FileRef> {
        match self {
            Self::Host(installation) => installation
                .observed_roles()
                .into_iter()
                .map(|(reference, _)| reference)
                .collect(),
            Self::Image(image) => image.references(),
        }
    }

    /// Verify the complete executor boundary.
    pub(crate) fn verify(&self) -> Result<(), String> {
        match self {
            Self::Host(installation) => installation.verify(),
            Self::Image(image) => image.verify(),
        }
    }
}
