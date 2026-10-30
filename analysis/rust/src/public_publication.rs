// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — atomic public report publication

//! Stage a whole bounded report and publish through Linux no-replacement rename.

use crate::public_temporary::OwnedDirectory;
use rustix::fs::{CWD, RenameFlags, renameat_with};
use serde_json::Value;
use std::path::Path;

/// Publish a complete JSON report atomically into a new exclusive directory.
///
/// This file operation does not admit sources or authenticate the report's producer.
///
/// # Errors
///
/// Refuses existing destinations, unsupported paths, reports above8MiB and any
/// staging or kernel publication failure. Existing data is never replaced.
pub fn write_neural_report(directory: &Path, report: &Value) -> Result<(), String> {
    let name = directory
        .file_name()
        .ok_or("Invalid neural report destination.")?;
    let parent = directory
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."))
        .canonicalize()
        .map_err(|_| "Neural report parent directory is unavailable.".to_owned())?;
    let target = parent.join(name);
    match std::fs::symlink_metadata(&target) {
        Ok(_) => return Err("Neural report output directory already exists.".into()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => return Err("Cannot inspect neural report destination.".into()),
    }
    let raw = crate::public_report::canonical(report)?;
    if raw.len() > 8 * 1024 * 1024 {
        return Err("Complete neural report exceeds its byte allocation.".into());
    }
    let prefix = format!(
        ".{}.",
        name.to_str().ok_or("Invalid neural report destination.")?
    );
    let staging = OwnedDirectory::create(&parent, &prefix)?;
    std::fs::write(staging.path.join("report.json"), raw)
        .map_err(|_| "Cannot stage the complete neural report.".to_owned())?;
    renameat_with(CWD, &staging.path, CWD, &target, RenameFlags::NOREPLACE)
        .map_err(|_| "Cannot publish the complete neural report without replacement.".to_owned())?;
    Ok(())
}
