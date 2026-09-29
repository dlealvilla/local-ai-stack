"""Real-clock development heartbeat soak. No paid host."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


def _wait(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status in {200, 404}:
                    return
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 405}:
                return
        except OSError:
            time.sleep(0.3)
    raise SystemExit(f"service did not answer {url}")


def _post(url: str, body: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode())
    if not isinstance(payload, dict):
        raise SystemExit("response was not an object")
    return payload


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="rukan-soak-"))
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    admin = subprocess.Popen(
        [
            sys.executable, "-m", "machi.main", "admin", "serve",
            "--store-dir", str(root / "store"), "--port", "8791",
        ],
        env=env,
    )
    intake = subprocess.Popen(
        [
            sys.executable, "-m", "machi.main", "command-center", "intake",
            "--data-dir", str(root / "cc"), "--host", "127.0.0.1",
            "--port", "8792", "--local-test",
        ],
        env=env,
    )
    try:
        _wait("http://127.0.0.1:8791/v1/monitoring", 20)
        _wait("http://127.0.0.1:8792/v1/telemetry/reports", 20)
    except SystemExit:
        # Intake is write-only, so GET 404 still proves the process is up.
        pass
    issued = subprocess.run(
        [
            sys.executable, "-m", "machi.main", "command-center", "credential",
            "issue", "--data-dir", str(root / "cc"), "--install-id", "not_recorded",
        ],
        env=env, check=True, capture_output=True, text=True,
    )
    secret = ""
    key_id = ""
    for line in issued.stdout.splitlines():
        if line.startswith("secret"):
            secret = line.split(None, 1)[1].strip()
        if line.startswith("key_id"):
            key_id = line.split(None, 1)[1].strip()
    _post(
        "http://127.0.0.1:8791/v1/monitoring",
        {
            "endpoint": "http://127.0.0.1:8792/v1/telemetry/reports",
            "key_id": key_id,
            "secret": secret,
            "profile": "development",
            "enabled": True,
            "local_test": True,
        },
    )
    _post("http://127.0.0.1:8791/v1/monitoring/test", {})
    deadline = time.monotonic() + 420
    periodic: list[str] = []
    while time.monotonic() < deadline and len(periodic) < 2:
        time.sleep(5)
        periodic = _periodic(root / "cc" / "command.sqlite")
    print(f"root     {root}")
    print(f"periodic {len(periodic)}")
    for stamp in periodic:
        print(f"generated {stamp}")
    admin.send_signal(2)
    intake.send_signal(2)
    admin.wait(timeout=20)
    intake.wait(timeout=20)
    if len(periodic) < 2:
        return 1
    first = _parse(periodic[0])
    second = _parse(periodic[1])
    gap = (second - first).total_seconds()
    print(f"gap_s    {gap}")
    if not 110 <= gap <= 140:
        return 1
    return 0


def _periodic(path: Path) -> list[str]:
    if not path.is_file():
        return []
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT generated_at, triggers FROM reports ORDER BY generated_at"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        connection.close()
    return [str(row[0]) for row in rows if "periodic" in str(row[1])]


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
