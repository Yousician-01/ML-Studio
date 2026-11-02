// Lifecycle adapter only: the real Next CLI/server remains the entry point.
// Windows can target CTRL_BREAK at an owned process group. Forward it to
// Next's existing SIGTERM cleanup handler instead of accepting Node's abrupt
// default SIGBREAK exit. No HTTP/application behavior is implemented here.
if (process.platform === "win32") {
  let stopping = false;
  process.on("SIGBREAK", () => {
    if (stopping) return;
    stopping = true;
    if (process.listenerCount("SIGTERM") > 0) {
      process.emit("SIGTERM", "SIGTERM");
    } else {
      process.exit(0); // cancelled before the framework installed its handlers
    }
  });
}
