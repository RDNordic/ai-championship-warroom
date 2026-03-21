from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


TRYCLOUDFLARE_URL_RE = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(url: str, timeout: float) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def wait_for_json_health(url: str, timeout_seconds: float, label: str) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            payload = read_json(url, timeout=5.0)
            if payload.get("status") == "ok":
                return payload
            last_error = RuntimeError(f"{label} returned unexpected payload: {payload}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, RuntimeError) as exc:
            last_error = exc
        time.sleep(1.0)

    raise RuntimeError(f"{label} did not become healthy within {timeout_seconds:.0f}s") from last_error


def default_python_bin(project_root: Path) -> Path:
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def default_npx_bin() -> str:
    for candidate in ("npx.cmd", "npx"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("Could not find npx or npx.cmd in PATH")


@dataclass
class ManagedProcess:
    name: str
    command: list[str]
    cwd: Path
    log_path: Path
    process: subprocess.Popen[str] | None = None
    tail: deque[str] = field(default_factory=lambda: deque(maxlen=40))
    _thread: threading.Thread | None = None

    def start(self, on_line: Callable[[str], None] | None = None) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = self.log_path.open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        def pump() -> None:
            assert self.process is not None
            assert self.process.stdout is not None
            try:
                for raw_line in self.process.stdout:
                    line = raw_line.rstrip("\n")
                    self.tail.append(line)
                    log_handle.write(raw_line)
                    log_handle.flush()
                    if on_line is not None:
                        on_line(line)
            finally:
                try:
                    self.process.stdout.close()
                except OSError:
                    pass
                log_handle.close()

        self._thread = threading.Thread(target=pump, name=f"{self.name}-log-pump", daemon=True)
        self._thread.start()

    def poll(self) -> int | None:
        if self.process is None:
            return None
        return self.process.poll()

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    @property
    def pid(self) -> int | None:
        if self.process is None:
            return None
        return self.process.pid


class PublicEndpointRunner:
    def __init__(
        self,
        *,
        project_root: Path,
        port: int,
        python_bin: Path,
        npx_bin: str,
        state_path: Path,
        local_timeout: float,
        public_timeout: float,
        skip_public_health: bool,
    ) -> None:
        self.project_root = project_root
        self.port = port
        self.python_bin = python_bin
        self.npx_bin = npx_bin
        self.state_path = state_path
        self.local_timeout = local_timeout
        self.public_timeout = public_timeout
        self.skip_public_health = skip_public_health
        self.cloudflare_url: str | None = None
        self._shutdown_requested = False
        self._cloudflared_url_ready = threading.Event()
        self._processes: list[ManagedProcess] = []

    def _write_state(self, *, public_health_ok: bool | None = None) -> None:
        payload = {
            "started_at": utc_now_iso(),
            "port": self.port,
            "local_health_url": f"http://127.0.0.1:{self.port}/health",
            "public_base_url": self.cloudflare_url,
            "public_health_url": f"{self.cloudflare_url}/health" if self.cloudflare_url else None,
            "uvicorn_pid": self._processes[0].pid if len(self._processes) > 0 else None,
            "cloudflared_pid": self._processes[1].pid if len(self._processes) > 1 else None,
            "public_health_ok": public_health_ok,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _build_processes(self) -> tuple[ManagedProcess, ManagedProcess]:
        logs_dir = self.project_root / "logs"
        uvicorn = ManagedProcess(
            name="uvicorn",
            command=[
                str(self.python_bin),
                "-m",
                "uvicorn",
                "tripletex_agent.app:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(self.port),
            ],
            cwd=self.project_root,
            log_path=logs_dir / f"public-uvicorn-{self.port}.log",
        )
        cloudflared = ManagedProcess(
            name="cloudflared",
            command=[
                self.npx_bin,
                "cloudflared",
                "tunnel",
                "--url",
                f"http://127.0.0.1:{self.port}",
            ],
            cwd=self.project_root,
            log_path=logs_dir / f"public-cloudflared-{self.port}.log",
        )
        return uvicorn, cloudflared

    def _on_cloudflared_line(self, line: str) -> None:
        if self.cloudflare_url is not None:
            return
        match = TRYCLOUDFLARE_URL_RE.search(line)
        if match:
            self.cloudflare_url = match.group(0)
            self._cloudflared_url_ready.set()

    def _install_signal_handlers(self) -> None:
        def handler(signum: int, _frame: object) -> None:
            self._shutdown_requested = True
            print(f"\nReceived signal {signum}. Shutting down public endpoint.", flush=True)

        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                signal.signal(sig, handler)

    def run(self) -> int:
        self._install_signal_handlers()
        uvicorn, cloudflared = self._build_processes()
        self._processes = [uvicorn, cloudflared]

        try:
            print(f"Starting uvicorn on port {self.port}", flush=True)
            uvicorn.start()
            wait_for_json_health(
                f"http://127.0.0.1:{self.port}/health",
                timeout_seconds=self.local_timeout,
                label="Local health",
            )
            print(f"Local health OK: http://127.0.0.1:{self.port}/health", flush=True)

            print("Starting quick Cloudflare tunnel", flush=True)
            cloudflared.start(on_line=self._on_cloudflared_line)

            if not self._cloudflared_url_ready.wait(timeout=self.public_timeout):
                raise RuntimeError("Cloudflared did not produce a public URL within the timeout window")

            assert self.cloudflare_url is not None
            print(f"Public URL: {self.cloudflare_url}", flush=True)

            public_health_ok = None
            if not self.skip_public_health:
                wait_for_json_health(
                    f"{self.cloudflare_url}/health",
                    timeout_seconds=self.public_timeout,
                    label="Public health",
                )
                public_health_ok = True
                print(f"Public health OK: {self.cloudflare_url}/health", flush=True)

            self._write_state(public_health_ok=public_health_ok)
            print(f"State written to {self.state_path}", flush=True)
            print("Leave this process running while the submission is live.", flush=True)

            return self._monitor()
        finally:
            for managed in reversed(self._processes):
                managed.stop()

    def _monitor(self) -> int:
        while not self._shutdown_requested:
            for managed in self._processes:
                exit_code = managed.poll()
                if exit_code is not None:
                    print(f"{managed.name} exited unexpectedly with code {exit_code}", flush=True)
                    if managed.tail:
                        print(f"Last {managed.name} log lines:", flush=True)
                        for line in managed.tail:
                            print(line, flush=True)
                    return 1
            time.sleep(1.0)
        return 0


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run uvicorn and a quick Cloudflare tunnel under one supervisor for live Tripletex submissions."
    )
    parser.add_argument("--port", type=int, default=8001, help="Local port for uvicorn")
    parser.add_argument(
        "--python-bin",
        default=str(default_python_bin(project_root)),
        help="Python executable to use for uvicorn",
    )
    parser.add_argument(
        "--npx-bin",
        default=default_npx_bin(),
        help="npx executable used to launch cloudflared",
    )
    parser.add_argument(
        "--state-path",
        default=str(project_root / "logs" / "public-endpoint-state.json"),
        help="Path where the current public endpoint metadata should be written",
    )
    parser.add_argument(
        "--local-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for local health before failing",
    )
    parser.add_argument(
        "--public-timeout",
        type=float,
        default=45.0,
        help="Seconds to wait for the tunnel URL and public health checks",
    )
    parser.add_argument(
        "--skip-public-health",
        action="store_true",
        help="Skip the external public /health probe after the tunnel URL appears",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    runner = PublicEndpointRunner(
        project_root=project_root,
        port=args.port,
        python_bin=Path(args.python_bin),
        npx_bin=args.npx_bin,
        state_path=Path(args.state_path),
        local_timeout=args.local_timeout,
        public_timeout=args.public_timeout,
        skip_public_health=args.skip_public_health,
    )
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
