mod config;
mod install;
mod logs;
mod process;
mod runtime;

use anyhow::Result;
use clap::{Parser, Subcommand};
use std::{path::PathBuf, sync::atomic::AtomicBool};

static STOP: AtomicBool = AtomicBool::new(false);

#[derive(Parser, Debug)]
#[command(version, about = "Install and manage the real local ML Studio servers")]
struct Cli {
    /// Checkout path (otherwise search ancestors or use the last installed checkout).
    #[arg(long, global = true)]
    repo: Option<PathBuf>,
    /// Explicit workspace override. Existing backend environment/.env otherwise wins.
    #[arg(long, global = true)]
    home: Option<PathBuf>,
    /// Python prerequisite executable (>=3.12).
    #[arg(long, global = true)]
    python: Option<PathBuf>,
    /// Node prerequisite executable (>=22.13.0).
    #[arg(long, global = true)]
    node: Option<PathBuf>,
    #[command(subcommand)]
    command: Action,
}

#[derive(Subcommand, Debug)]
enum Action {
    /// Prepare dependencies, production frontend, and backed-up database migrations.
    Install,
    /// Run both production servers in the foreground; Ctrl+C stops both.
    Start,
    /// Safely request shutdown of the installation's live supervisor.
    Abort,
    /// Report installation, owned processes, readiness, and stale session state.
    Status,
    /// Show recent persistent server logs (following never stops the servers).
    Logs {
        #[arg(long)]
        follow: bool,
        #[arg(long, value_enum)]
        component: Option<logs::Component>,
    },
    /// Read-only prerequisite, configuration, schema, and runtime diagnostics.
    Doctor,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("mls: {error:#}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let args = Cli::parse();
    ctrlc::set_handler(|| STOP.store(true, std::sync::atomic::Ordering::SeqCst))?;
    let context = config::Context::discover(&args)?;
    match args.command {
        Action::Install => install::run(&context),
        Action::Start => runtime::start(&context),
        Action::Abort => runtime::abort(&context),
        Action::Status => runtime::status(&context),
        Action::Logs { follow, component } => logs::show(&context, follow, component),
        Action::Doctor => install::doctor(&context),
    }
}

#[cfg(test)]
mod tests;
