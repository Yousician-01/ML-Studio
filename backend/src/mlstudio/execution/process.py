"""One local workload, bounded streams, and identity-checked process cleanup."""

import os
import subprocess
import sys
import threading
import time

import psutil

from mlstudio.execution.artifacts import safe_path
from mlstudio.execution.results import ExecutionFailure


class WorkspaceLease:
    """OS lock survives HTTP requests and is released by the OS after a crash."""

    def __init__(self, home):
        self.stream = safe_path(home, ".execution.lock").open("a+b")
        try:
            self.stream.seek(0, os.SEEK_END)
            if self.stream.tell() == 0:
                self.stream.write(b"\0")
                self.stream.flush()
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            self.stream.close()
            raise

    def close(self):
        if not self.stream.closed:
            self.stream.close()


def environment():
    # This limits accidental credential/injection inheritance; it is NOT a sandbox.
    allowed = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}
    result = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    result.update(
        {
            key: "1"
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "BLIS_NUM_THREADS",
            )
        }
    )
    return result


def command(directory, dataset):
    # abspath, NOT resolve: resolving a POSIX venv symlink selects the base interpreter.
    return [
        os.path.abspath(sys.executable),
        "-I",
        "-B",
        "-u",
        "-X",
        "utf8",
        str(directory / "generated_run.py"),
        "--dataset",
        str(dataset),
        "--result",
        str(directory / ".pending" / "result.json"),
        "--model",
        str(directory / ".pending" / "model.joblib"),
    ]


def launch(arguments, directory):
    return subprocess.Popen(
        arguments,
        shell=False,
        cwd=directory,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment(),
        start_new_session=os.name != "nt",
    )


def identity(process):
    try:
        return {"pid": process.pid, "created": psutil.Process(process.pid).create_time()}
    except psutil.NoSuchProcess:
        # A fast-exiting child is still owned by the Popen handle and will be reaped.
        return {"pid": process.pid, "created": None}


def owned_process(evidence, arguments):
    try:
        candidate = psutil.Process(evidence["pid"])
        if evidence.get("created") is None or candidate.create_time() != evidence["created"]:
            return None
        if candidate.cmdline() != arguments:
            raise ExecutionFailure("ownership_uncertain", "recovery")
        return candidate
    except psutil.NoSuchProcess:
        return None
    except (psutil.AccessDenied, KeyError, TypeError):
        raise ExecutionFailure("ownership_uncertain", "recovery") from None


def stop_tree(process, grace):
    """psutil Process objects retain creation times and guard against PID reuse."""
    try:
        children = process.children(recursive=True)
        targets = [*reversed(children), process]
        for target in targets:
            try:
                target.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(targets, timeout=grace)
        for target in alive:
            try:
                target.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(alive, timeout=grace)
        if alive:
            raise ExecutionFailure("ownership_uncertain", "cleanup")
    except psutil.NoSuchProcess:
        pass
    except psutil.AccessDenied:
        raise ExecutionFailure("ownership_uncertain", "cleanup") from None


class Capture:
    def __init__(self, pipe, path, limit):
        self.pipe, self.path, self.limit = pipe, path, limit
        self.truncated = False
        self.failed = threading.Event()
        self.thread = threading.Thread(target=self.drain, name="mlstudio-log", daemon=False)

    def drain(self):
        stream = None
        written = 0
        try:
            try:
                stream = self.path.open("xb")
            except OSError:
                self.failed.set()
            while chunk := self.pipe.read(65536):
                remaining = self.limit - written
                self.truncated |= len(chunk) > remaining
                if stream and remaining:
                    try:
                        data = chunk[:remaining]
                        stream.write(data)
                        written += len(data)
                    except OSError:
                        self.failed.set()
                        stream.close()
                        stream = None
            if stream:
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            self.failed.set()
        finally:
            if stream:
                stream.close()
            self.pipe.close()


def wait(process, captures, settings, shutdown, ownership):
    deadline = time.monotonic() + settings.run_timeout_seconds
    failure = None
    while process.poll() is None:
        if shutdown.is_set():
            failure = "execution_interrupted"
        elif any(capture.failed.is_set() for capture in captures):
            failure = "log_storage"
        elif time.monotonic() >= deadline:
            failure = "timeout"
        if failure:
            if ownership is None:
                raise ExecutionFailure("ownership_uncertain", "cleanup")
            stop_tree(ownership, settings.run_termination_grace_seconds)
            break
        shutdown.wait(0.05)
    process.wait()
    for capture in captures:
        capture.thread.join(timeout=settings.run_termination_grace_seconds)
        if capture.thread.is_alive():
            # Trusted generated code does not spawn children. A surviving inherited
            # pipe is an ownership anomaly: never finalize while a writer may remain.
            raise ExecutionFailure("ownership_uncertain", "cleanup")
    if failure:
        raise ExecutionFailure(failure)
    if any(capture.failed.is_set() for capture in captures):
        raise ExecutionFailure("log_storage")
    return process.returncode
