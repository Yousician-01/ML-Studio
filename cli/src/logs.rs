use crate::{
    STOP,
    config::{self, Context},
};
use anyhow::Result;
use clap::ValueEnum;
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    sync::{Arc, Mutex, atomic::Ordering},
    thread::{self, JoinHandle},
    time::Duration,
};

const LIMIT: u64 = 5 * 1024 * 1024;
const KEEP: usize = 3;

#[derive(Clone, Copy, Debug, ValueEnum)]
pub enum Component {
    Backend,
    Frontend,
}
impl Component {
    pub fn name(self) -> &'static str {
        match self {
            Self::Backend => "backend",
            Self::Frontend => "frontend",
        }
    }
}

pub struct Writer {
    path: PathBuf,
    file: File,
    size: u64,
}
impl Writer {
    pub fn open(directory: &Path, name: &str) -> Result<Arc<Mutex<Self>>> {
        fs::create_dir_all(directory)?;
        let path = directory.join(format!("{name}.log"));
        let file = OpenOptions::new().create(true).append(true).open(&path)?;
        let size = file.metadata()?.len();
        Ok(Arc::new(Mutex::new(Self { path, file, size })))
    }
    fn write(&mut self, component: &str, stream: &str, bytes: &[u8]) -> Result<()> {
        if self.size >= LIMIT {
            // Replace the open handle before renames (Windows cannot rename an open log).
            self.file = OpenOptions::new()
                .append(true)
                .open(self.path.with_extension("rotate"))
                .or_else(|_| {
                    OpenOptions::new()
                        .create(true)
                        .append(true)
                        .open(self.path.with_extension("rotate"))
                })?;
            for index in (1..=KEEP).rev() {
                let target = self.path.with_extension(format!("log.{index}"));
                if target.exists() {
                    fs::remove_file(&target)?;
                }
                let source = if index == 1 {
                    self.path.clone()
                } else {
                    self.path.with_extension(format!("log.{}", index - 1))
                };
                if source.exists() {
                    fs::rename(source, target)?;
                }
            }
            self.file = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&self.path)?;
            let _ = fs::remove_file(self.path.with_extension("rotate"));
            self.size = 0;
        }
        let line = format!(
            "[{} UTC epoch] [{component}/{stream}] {}\n",
            config::now(),
            String::from_utf8_lossy(bytes).trim_end()
        );
        self.file.write_all(line.as_bytes())?;
        self.file.flush()?;
        self.size += line.len() as u64;
        Ok(())
    }
}

pub fn drain(
    reader: impl Read + Send + 'static,
    writer: Arc<Mutex<Writer>>,
    component: &'static str,
    stream: &'static str,
) -> JoinHandle<()> {
    thread::spawn(move || {
        let mut reader = reader;
        let mut buffer = [0u8; 4096];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(count) => {
                    if let Ok(mut writer) = writer.lock()
                        && let Err(error) = writer.write(component, stream, &buffer[..count])
                    {
                        eprintln!("mls: {component} log write failed: {error}");
                    }
                }
            }
        }
    })
}

pub fn show(context: &Context, follow: bool, component: Option<Component>) -> Result<()> {
    let components = component.map_or(vec![Component::Backend, Component::Frontend], |c| vec![c]);
    let mut offsets = vec![0; components.len()];
    let mut identities = vec![None; components.len()];
    let mut initial = true;
    loop {
        for (index, component) in components.iter().enumerate() {
            let path = context
                .state
                .join("logs")
                .join(format!("{}.log", component.name()));
            if let Ok(mut file) = File::open(path) {
                let metadata = file.metadata()?;
                let len = metadata.len();
                let identity = file_identity(&metadata);
                if initial {
                    offsets[index] = len.saturating_sub(32 * 1024);
                } else if identities[index] != Some(identity) {
                    offsets[index] = 0;
                }
                identities[index] = Some(identity);
                if len < offsets[index] {
                    offsets[index] = 0;
                }
                file.seek(SeekFrom::Start(offsets[index]))?;
                let mut bytes = vec![0; 32 * 1024];
                let count = file.read(&mut bytes)?;
                if count > 0 {
                    print!("{}", String::from_utf8_lossy(&bytes[..count]));
                    std::io::stdout().flush()?;
                    offsets[index] += count as u64;
                }
            } else if initial {
                println!("No {} logs yet.", component.name());
            }
        }
        initial = false;
        if !follow || STOP.load(Ordering::SeqCst) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(250));
    }
}

fn file_identity(metadata: &fs::Metadata) -> u128 {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        metadata.creation_time() as u128
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        ((metadata.dev() as u128) << 64) | metadata.ino() as u128
    }
}
