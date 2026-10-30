// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual isolated source-checker execution

//! Execute only fixed operations with complete observations and owned-group cleanup.

use crate::files::decode;
use crate::public_runtime::Installation;
use rustix::process::{Pid, Signal, kill_process_group};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{File, OpenOptions};
use std::io::Read;
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const LIMIT_BOOTSTRAP: &str = "import os,resource,sys; resource.setrlimit(resource.RLIMIT_AS,(805306368,805306368)); resource.setrlimit(resource.RLIMIT_CORE,(0,0)); resource.setrlimit(resource.RLIMIT_CPU,(30,30)); resource.setrlimit(resource.RLIMIT_FSIZE,(8388608,8388608)); os.execv(sys.argv[1],sys.argv[1:])";
const WORKER_BOOTSTRAP: &str = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('loop_timing_witness.neural_checker_worker',run_name='__main__')";

/// Actual loaded module observation from the selected worker.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ModuleObservation {
    pub name: String,
    pub path: String,
}

/// Complete original actual file observation, retaining physical path provenance.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FileObservation {
    pub path: String,
    pub sha256: String,
    pub byte_length: u64,
}

/// Closed selected worker observation, independent of recorded producer receipts.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkerObservation {
    pub schema_id: String,
    pub operation: String,
    pub actual_argv: Vec<String>,
    pub native_returncode: i32,
    pub phase: String,
    pub started_ns: u64,
    pub completed_ns: u64,
    pub elapsed_ns: u64,
    pub modules: Vec<ModuleObservation>,
    pub files: Vec<FileObservation>,
}

/// Complete finite original observations of one actual source-checker process.
pub(crate) struct Invocation {
    pub command: Vec<String>,
    pub returncode: i32,
    pub started_ns: u64,
    pub completed_ns: u64,
    pub elapsed_ns: u64,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub trace: Vec<u8>,
    pub observation: Option<WorkerObservation>,
    pub interrupted: bool,
}

/// A spawned group remains owned until its actual leader is reaped.
struct RunningChecker {
    child: Child,
    group: Pid,
    reaped: bool,
}

impl Drop for RunningChecker {
    fn drop(&mut self) {
        if !self.reaped {
            let _ = kill_process_group(self.group, Signal::KILL);
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

/// Construct the same closed environment used by the Python consumer.
pub(crate) fn environment(directory: &Path) -> Result<BTreeMap<String, String>, String> {
    let values = [
        ("PATH", "/usr/bin:/bin"),
        ("LANG", "C.UTF-8"),
        ("LC_ALL", "C.UTF-8"),
        ("TZ", "UTC"),
        ("OPENBLAS_NUM_THREADS", "1"),
        ("OMP_NUM_THREADS", "1"),
        ("MKL_NUM_THREADS", "1"),
        ("NUMEXPR_NUM_THREADS", "1"),
    ];
    let mut result: BTreeMap<_, _> = values
        .into_iter()
        .map(|(key, value)| (key.into(), value.into()))
        .collect();
    result.insert("TMPDIR".into(), path_text(directory)?.into());
    Ok(result)
}

/// Preserve exact UTF-8 argument bytes rather than lossy host-path substitutions.
fn path_text(path: &Path) -> Result<&str, String> {
    path.to_str()
        .ok_or_else(|| "Checker path requires exact UTF-8.".into())
}

/// Return a finite current epoch timestamp with no numeric truncation.
fn timestamp() -> Result<u64, String> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "Checker system clock precedes its supported epoch.".to_owned())?
        .as_nanos()
        .try_into()
        .map_err(|_| "Checker timestamp exceeds its allocation.".into())
}

/// Read an owned completed output through a finite regular no-follow descriptor.
pub(crate) fn output_bytes(path: &Path, limit: u64) -> Result<Vec<u8>, String> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(0o400000 | 0o4000)
        .open(path)
        .map_err(|_| "Actual checker output is unavailable.".to_owned())?;
    if !file
        .metadata()
        .map_err(|_| "Cannot inspect checker output.".to_owned())?
        .is_file()
    {
        return Err("Actual checker output must be a regular file.".into());
    }
    let mut raw = Vec::new();
    file.take(limit + 1)
        .read_to_end(&mut raw)
        .map_err(|_| "Cannot read actual checker output.".to_owned())?;
    if raw.len() as u64 > limit {
        return Err("Actual checker output exceeds its allocation.".into());
    }
    Ok(raw)
}

/// Run one fixed operation, observing real status and reaping every owned process.
pub(crate) fn invoke(
    installation: &Installation,
    script: &Path,
    operation: &str,
    directory: &Path,
) -> Result<Invocation, String> {
    if !["generate", "check"].contains(&operation) {
        return Err("Unsupported fixed source-checker operation.".into());
    }
    installation.verify()?;
    let interpreter = path_text(installation.interpreter()?)?;
    let tracer = path_text(installation.tracer()?)?;
    let cache = format!("pycache_prefix={}", path_text(&directory.join("bytecode"))?);
    let trace_path = directory.join("checker-open.log");
    let mut argv: Vec<String> = [
        interpreter,
        "-X",
        &cache,
        "-I",
        "-B",
        "-S",
        "-c",
        LIMIT_BOOTSTRAP,
        tracer,
        "--kill-on-exit",
        "-f",
        "-qq",
        "-xx",
        "-yy",
        "-s",
        "8192",
        "-e",
        "trace=openat,openat2,execve",
        "-o",
        path_text(&trace_path)?,
        interpreter,
        "-X",
        &cache,
        "-I",
        "-B",
        "-S",
        "-c",
        WORKER_BOOTSTRAP,
        path_text(installation.worker_import_root())?,
        path_text(script)?,
        operation,
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    for root in &installation.import_roots {
        argv.push(path_text(root)?.into());
    }
    let completed = run_group(
        &argv,
        directory,
        environment(directory)?,
        (
            &directory.join("checker.stdout"),
            &directory.join("checker.stderr"),
        ),
        Duration::from_secs(installation.runtime.execution_contract.wall_seconds),
    )?;
    let trace = if trace_path
        .try_exists()
        .map_err(|_| "Cannot inspect the actual checker trace.".to_owned())?
    {
        output_bytes(&trace_path, 8388608)?
    } else {
        Vec::new()
    };
    installation.verify()?;
    Ok(completed.into_invocation(argv, trace))
}

/// Finite observations of one completed and reaped checker process group.
pub(crate) struct Completed {
    returncode: i32,
    started_ns: u64,
    completed_ns: u64,
    elapsed_ns: u64,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    observation: Option<WorkerObservation>,
    interrupted: bool,
}

impl Completed {
    /// Attach the actual command and process boundary record.
    pub(crate) fn into_invocation(self, command: Vec<String>, trace: Vec<u8>) -> Invocation {
        Invocation {
            command,
            returncode: self.returncode,
            started_ns: self.started_ns,
            completed_ns: self.completed_ns,
            elapsed_ns: self.elapsed_ns,
            stdout: self.stdout,
            stderr: self.stderr,
            trace,
            observation: self.observation,
            interrupted: self.interrupted,
        }
    }
}

/// Spawn one owned process group, enforce its deadline and reap it completely.
///
/// The child gets only the given environment, a null stdin and exclusive log
/// files. A deadline stops the whole group; the process is never restarted.
pub(crate) fn run_group(
    argv: &[String],
    directory: &Path,
    environment: BTreeMap<String, String>,
    logs: (&Path, &Path),
    deadline: Duration,
) -> Result<Completed, String> {
    let stdout = File::create_new(logs.0)
        .map_err(|_| "Cannot create exclusive checker output.".to_owned())?;
    let stderr = File::create_new(logs.1)
        .map_err(|_| "Cannot create exclusive checker diagnostic.".to_owned())?;
    let started_ns = timestamp()?;
    let monotonic = Instant::now();
    let mut child = Command::new(&argv[0])
        .args(&argv[1..])
        .current_dir(directory)
        .env_clear()
        .envs(environment)
        .stdin(Stdio::null())
        .stdout(stdout)
        .stderr(stderr)
        .process_group(0)
        .spawn()
        .map_err(|_| "Cannot start the selected source checker.".to_owned())?;
    let raw_pid = i32::try_from(child.id()).ok().filter(|pid| *pid > 1);
    let Some(group) = raw_pid.and_then(Pid::from_raw) else {
        let _ = child.kill();
        let _ = child.wait();
        return Err("Source checker did not obtain an owned process group.".into());
    };
    let mut running = RunningChecker {
        child,
        group,
        reaped: false,
    };
    let mut interrupted = false;
    let status = loop {
        if let Some(status) = running
            .child
            .try_wait()
            .map_err(|_| "Cannot observe the actual source checker.".to_owned())?
        {
            running.reaped = true;
            break status;
        }
        if monotonic.elapsed() >= deadline {
            interrupted = true;
            kill_process_group(running.group, Signal::KILL)
                .map_err(|_| "Cannot stop the owned checker process group.".to_owned())?;
            let status = running
                .child
                .wait()
                .map_err(|_| "Cannot reap the interrupted source checker.".to_owned())?;
            running.reaped = true;
            break status;
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let returncode = status
        .code()
        .or_else(|| status.signal().map(|signal| -signal))
        .ok_or("Actual checker native status is unavailable.")?;
    let completed_ns = timestamp()?;
    let elapsed_ns = monotonic
        .elapsed()
        .as_nanos()
        .try_into()
        .map_err(|_| "Checker elapsed time exceeds its allocation.".to_owned())?;
    let observation_path: PathBuf = directory.join("checker-observation.json");
    let observation = if observation_path
        .try_exists()
        .map_err(|_| "Cannot inspect the actual checker observation.".to_owned())?
    {
        Some(decode(
            &output_bytes(&observation_path, 1048576)?,
            "actual checker observation",
        )?)
    } else {
        None
    };
    Ok(Completed {
        returncode,
        started_ns,
        completed_ns,
        elapsed_ns,
        stdout: output_bytes(logs.0, 1048576)?,
        stderr: output_bytes(logs.1, 1048576)?,
        observation,
        interrupted,
    })
}
