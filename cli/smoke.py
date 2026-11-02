"""Small CI/maintainer smoke check of the real CLI, not an application server.

Runs one disposable install/build, starts both actual servers, then uses abort.
No ML execution or user workspace access. Run with a prerequisite Python, not pip.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def ready(url, backend=False):
    try:
        # Ignore proxy settings for loopback readiness.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=2) as response:
            if response.status != 200:
                return False
            if backend:
                body = json.loads(response.read(4096))
                return body == {"status": "ok", "service": "ml-studio-api", "database": "ready"}
            return True
    except (OSError, ValueError, urllib.error.URLError):
        return False


def ports_closed():
    for port in (3000, 8000):
        with socket.socket() as connection:
            connection.settimeout(1)
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Owned server still listens on port {port}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node with npm is required")
    ports_closed()  # Never touch an existing service.
    # Retain evidence on failure; remove the generated directory only on success.
    with tempfile.TemporaryDirectory(prefix="mlstudio-cli-smoke-", delete=False) as temporary:
        directory = Path(temporary)
        print(f"Disposable evidence directory (retained on failure): {directory}", flush=True)
        home = directory / "workspace"
        env = dict(os.environ)
        env.update(
            MLS_STATE_HOME=str(directory / "state"),
            MLSTUDIO_HOME=str(home),
            MLSTUDIO_DATABASE_URL="sqlite+pysqlite:///" + (home / "mlstudio.db").as_posix(),
            MLSTUDIO_CODE_EXECUTION_ENABLED="false",
            MLSTUDIO_API_PREFIX="/api/v1",
            MLSTUDIO_CORS_ORIGINS='["http://127.0.0.1:3000","http://localhost:3000"]',
            NEXT_TELEMETRY_DISABLED="1",
        )
        base = [str(binary), "--repo", str(repo)]

        def run(*arguments, capture=False, timeout=120):
            command = base + list(arguments)
            print("mls", " ".join(arguments), flush=True)
            result = subprocess.run(
                command,
                cwd=repo,
                env=env,
                check=True,
                timeout=timeout,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.STDOUT if capture else None,
                text=True,
            )
            if capture:
                print(result.stdout, end="", flush=True)
            return result.stdout or ""

        run("--version")
        run("--help", capture=True)
        run("--python", sys.executable, "--node", node, "install", timeout=1800)
        run("doctor")
        output_path = directory / "supervisor.log"
        with output_path.open("wb") as output:
            process = subprocess.Popen(
                base + ["start"],
                cwd=repo,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                started = time.monotonic()
                deadline = started + 510
                reported = set()
                while not (
                    ready("http://127.0.0.1:8000/api/v1/health", True)
                    and ready("http://127.0.0.1:3000")
                ):
                    if process.poll() is not None:
                        raise RuntimeError("Supervisor exited before readiness")
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Two-server readiness exceeded 510 seconds")
                    if "backend" not in reported and ready(
                        "http://127.0.0.1:8000/api/v1/health", True
                    ):
                        print(
                            f"Backend HTTP ready after {time.monotonic() - started:.1f}s",
                            flush=True,
                        )
                        reported.add("backend")
                    time.sleep(0.5)
                # HTTP can become ready just before the supervisor publishes its
                # Running record. Poll only that small state transition.
                deadline = time.monotonic() + 10
                while True:
                    status = run("status", capture=True)
                    if "Session: running" in status:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Healthy servers were not recorded as Running")
                    time.sleep(0.25)
                if status.count("owned_alive=true, healthy=true") != 2:
                    raise RuntimeError("Status did not verify both server identities/readiness")
                run("logs")
                run("abort", timeout=45)
                if process.wait(timeout=10) != 0:
                    raise RuntimeError("Supervisor returned a failure after abort")
                ports_closed()
                run("status")
                run("abort")  # no active session is safe
            finally:
                if process.poll() is None:
                    try:
                        run("abort", timeout=45)
                    finally:
                        if process.poll() is None:
                            # This Popen handle is owned by this smoke check; no
                            # PID file or unrelated port occupant is terminated.
                            process.terminate()
                            process.wait(timeout=45)
                output.flush()
                with output_path.open("rb") as evidence:
                    evidence.seek(max(0, output_path.stat().st_size - 16384))
                    print(evidence.read().decode("utf-8", errors="replace"))
    # The target is exactly the generated, resolved tempfile root, never a user path.
    if directory.resolve().parent != Path(
        tempfile.gettempdir()
    ).resolve() or not directory.name.startswith("mlstudio-cli-smoke-"):
        raise RuntimeError("Refusing cleanup outside the generated smoke directory")
    shutil.rmtree(directory)
    print("CLI smoke passed: disposable install, two real servers, readiness, status/logs, abort.")


if __name__ == "__main__":
    main()
