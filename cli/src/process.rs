#[cfg(windows)]
use anyhow::ensure;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    io::Read,
    path::PathBuf,
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};
use sysinfo::{Pid, System};

pub fn output(command: &mut Command, timeout: Duration) -> Result<std::process::Output> {
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = Managed::spawn(command)?;
    let stdout = capture(child.child.stdout.take().context("Missing helper stdout")?);
    let stderr = capture(child.child.stderr.take().context("Missing helper stderr")?);
    let deadline = Instant::now() + timeout;
    let status = loop {
        if let Some(status) = child.poll()? {
            break status;
        }
        anyhow::ensure!(
            !crate::STOP.load(std::sync::atomic::Ordering::SeqCst),
            "CLI helper interrupted"
        );
        anyhow::ensure!(
            Instant::now() < deadline,
            "CLI helper timed out; preserve backup/log evidence before retrying"
        );
        thread::sleep(Duration::from_millis(100));
    };
    child.stop();
    Ok(std::process::Output {
        status,
        stdout: stdout
            .recv_timeout(Duration::from_secs(2))
            .context("Helper stdout did not close")?,
        stderr: stderr
            .recv_timeout(Duration::from_secs(2))
            .context("Helper stderr did not close")?,
    })
}

fn capture(mut reader: impl Read + Send + 'static) -> std::sync::mpsc::Receiver<Vec<u8>> {
    let (send, receive) = std::sync::mpsc::channel();
    thread::spawn(move || {
        let mut bytes = Vec::new();
        let mut buffer = [0u8; 4096];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(count) => {
                    let keep = count.min(65536usize.saturating_sub(bytes.len()));
                    bytes.extend_from_slice(&buffer[..keep]);
                }
            }
        }
        let _ = send.send(bytes);
    });
    receive
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Identity {
    pub pid: u32,
    pub started: u64,
    pub exe: PathBuf,
    pub command: Vec<std::ffi::OsString>,
}

impl Identity {
    pub fn capture(pid: u32) -> Result<Self> {
        let system = System::new_all();
        let process = system
            .process(Pid::from_u32(pid))
            .context("Process exited before ownership could be recorded")?;
        Ok(Self {
            pid,
            started: process.start_time(),
            exe: process
                .exe()
                .context("Cannot verify executable identity")?
                .to_path_buf(),
            command: process.cmd().to_vec(),
        })
    }
    pub fn current() -> Result<Self> {
        Self::capture(std::process::id())
    }
    pub fn alive(&self) -> bool {
        let system = System::new_all();
        system.process(Pid::from_u32(self.pid)).is_some_and(|p| {
            p.start_time() == self.started
                && p.exe() == Some(self.exe.as_path())
                && p.cmd() == self.command
        })
    }
}

pub struct Managed {
    pub child: Child,
    pub identity: Identity,
    #[cfg(windows)]
    job: windows_sys::Win32::Foundation::HANDLE,
    stopped: bool,
}

impl Managed {
    pub fn spawn(command: &mut Command) -> Result<Self> {
        command.stdin(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            use windows_sys::Win32::System::Threading::{
                CREATE_NEW_PROCESS_GROUP, CREATE_SUSPENDED,
            };
            command.creation_flags(CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
            #[cfg(target_os = "linux")]
            let parent = std::process::id() as libc::pid_t;
            #[cfg(target_os = "linux")]
            // SAFETY: only async-signal-safe OS calls in the post-fork child.
            unsafe {
                command.pre_exec(move || {
                    if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0 {
                        return Err(std::io::Error::last_os_error());
                    }
                    if libc::getppid() != parent {
                        libc::raise(libc::SIGTERM);
                    }
                    Ok(())
                });
            }
        }
        let mut child = command.spawn().context("Cannot launch component")?;
        #[cfg(windows)]
        let job = match windows_attach_and_resume(&child) {
            Ok(job) => job,
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(error);
            }
        };
        let identity = match Identity::capture(child.id()) {
            Ok(identity) => identity,
            // A fast installer command may exit before sysinfo observes it.
            // Ownership still resides in Child/the unreaped PID, never in this
            // sentinel identity. Installer polls its actual exit status; server
            // readiness rejects any already-exited root.
            Err(_) if poll_child(&mut child).is_ok_and(|status| status.is_some()) => Identity {
                pid: child.id(),
                started: 0,
                exe: PathBuf::new(),
                command: Vec::new(),
            },
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                #[cfg(windows)]
                unsafe {
                    windows_sys::Win32::Foundation::CloseHandle(job);
                }
                return Err(error);
            }
        };
        Ok(Self {
            child,
            identity,
            #[cfg(windows)]
            job,
            stopped: false,
        })
    }

    pub fn poll(&mut self) -> std::io::Result<Option<std::process::ExitStatus>> {
        poll_child(&mut self.child)
    }

    #[cfg(unix)]
    fn group_has_descendants(&self) -> bool {
        System::new_all().processes().keys().any(|pid| {
            let pid = pid.as_u32();
            pid != self.child.id() && unsafe { libc::getpgid(pid as i32) } == self.child.id() as i32
        })
    }

    pub fn stop(&mut self) {
        if self.stopped {
            return;
        }
        // Windows retains the process handle; Unix poll retains the unreaped PID.
        // Never signal groups using evidence loaded from a session/PID file.
        let running = matches!(self.poll(), Ok(None));
        #[cfg(unix)]
        let running = running || self.group_has_descendants();
        if running {
            #[cfg(windows)]
            unsafe {
                windows_sys::Win32::System::Console::GenerateConsoleCtrlEvent(
                    windows_sys::Win32::System::Console::CTRL_BREAK_EVENT,
                    self.child.id(),
                );
            }
            #[cfg(unix)]
            unsafe {
                libc::kill(-(self.child.id() as i32), libc::SIGTERM);
            }
            let deadline = Instant::now() + Duration::from_secs(15);
            while Instant::now() < deadline {
                let alive = matches!(self.poll(), Ok(None));
                #[cfg(unix)]
                let alive = alive || self.group_has_descendants();
                if !alive {
                    break;
                }
                thread::sleep(Duration::from_millis(100));
            }
            #[cfg(unix)]
            unsafe {
                libc::kill(-(self.child.id() as i32), libc::SIGKILL);
            }
            if matches!(self.poll(), Ok(None)) {
                let _ = self.child.kill();
            }
        }
        #[cfg(windows)]
        unsafe {
            // Job also contains grandchildren; closes even when the root exited.
            windows_sys::Win32::Foundation::CloseHandle(self.job);
        }
        let _ = self.child.wait();
        self.stopped = true;
    }
}

impl Drop for Managed {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(windows)]
fn windows_attach_and_resume(child: &Child) -> Result<windows_sys::Win32::Foundation::HANDLE> {
    use std::{
        mem::{size_of, zeroed},
        os::windows::io::AsRawHandle,
        ptr::null,
    };
    use windows_sys::Win32::{
        Foundation::*,
        System::{Diagnostics::ToolHelp::*, JobObjects::*, Threading::*},
    };
    // SAFETY: handles are checked, thread is still suspended, structures match
    // their Win32 layouts. No application code runs before containment succeeds.
    unsafe {
        let job = CreateJobObjectW(null(), null());
        ensure!(!job.is_null(), "Cannot create Windows process Job");
        let operation = (|| -> Result<()> {
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            ensure!(
                SetInformationJobObject(
                    job,
                    JobObjectExtendedLimitInformation,
                    &limits as *const _ as *const _,
                    size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32
                ) != 0,
                "Cannot configure Windows process Job"
            );
            ensure!(
                AssignProcessToJobObject(job, child.as_raw_handle()) != 0,
                "Cannot contain child process in Windows Job"
            );
            let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
            ensure!(
                snapshot != INVALID_HANDLE_VALUE,
                "Cannot inspect suspended child thread"
            );
            let mut entry: THREADENTRY32 = zeroed();
            entry.dwSize = size_of::<THREADENTRY32>() as u32;
            let mut found = false;
            if Thread32First(snapshot, &mut entry) != 0 {
                loop {
                    if entry.th32OwnerProcessID == child.id() {
                        let thread = OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID);
                        if !thread.is_null() {
                            found = ResumeThread(thread) != u32::MAX;
                            CloseHandle(thread);
                        }
                        break;
                    }
                    if Thread32Next(snapshot, &mut entry) == 0 {
                        break;
                    }
                }
            }
            CloseHandle(snapshot);
            ensure!(found, "Cannot resume contained child process");
            Ok(())
        })();
        if let Err(error) = operation {
            CloseHandle(job);
            return Err(error);
        }
        Ok(job)
    }
}

fn poll_child(child: &mut Child) -> std::io::Result<Option<std::process::ExitStatus>> {
    #[cfg(windows)]
    {
        child.try_wait()
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        // WNOWAIT retains the child's PID until cleanup. Its process-group ID
        // cannot be reused while we stop descendants after a root crash.
        unsafe {
            let mut info: libc::siginfo_t = std::mem::zeroed();
            if libc::waitid(
                libc::P_PID,
                child.id(),
                &mut info,
                libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
            ) != 0
            {
                return Err(std::io::Error::last_os_error());
            }
            if info.si_pid() == 0 {
                return Ok(None);
            }
            let raw = if info.si_code == libc::CLD_EXITED {
                info.si_status() << 8
            } else {
                info.si_status()
            };
            Ok(Some(std::process::ExitStatus::from_raw(raw)))
        }
    }
}
