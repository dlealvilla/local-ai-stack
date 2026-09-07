"""Loopback reference server. Proves instance lifecycle, not inference.

Binds 127.0.0.1 on an ephemeral port, answers /health and /metadata,
and exits on SIGTERM. It does not generate tokens.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARKER = "kultrun-reference-serving"
MODES = (
    "healthy",
    "exit-immediately",
    "never-ready",
    "crash-after-ready",
)


class _Handler(BaseHTTPRequestHandler):
    instance_id = ""
    crash_after = False
    crashed = False

    def log_message(self, fmt: str, *args: object) -> None:
        del fmt, args

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in {"/health", "/metadata"}:
            self.send_error(404, "not a generation endpoint")
            return
        payload = {
            "ready": True,
            "instance_id": self.instance_id,
            "runtime": "reference-serving",
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if self.crash_after and not _Handler.crashed:
            _Handler.crashed = True
            threading.Thread(target=_exit_soon, daemon=True).start()


def _exit_soon() -> None:
    time.sleep(0.15)
    os._exit(3)


def main(argv: list[str] | None = None) -> int:
    del argv
    mode = os.environ.get("KULTRUN_REFERENCE_SERVING_MODE", "healthy")
    instance_id = os.environ.get("KULTRUN_INSTANCE_ID", "")
    host = os.environ.get("KULTRUN_REFERENCE_BIND", "127.0.0.1")
    if mode == "exit-immediately":
        print(f"{MARKER}:fail", flush=True)
        return 2
    if mode == "never-ready":
        print(f"{MARKER}:starting", flush=True)

        def _exit_on_term(_signum: int, _frame: object) -> None:
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _exit_on_term)
        while True:
            time.sleep(0.2)

    _Handler.instance_id = instance_id
    _Handler.crash_after = mode == "crash-after-ready"
    server = ThreadingHTTPServer((host, 0), _Handler)
    address = server.server_address
    bound_host = str(address[0])
    bound_port = int(address[1])
    print(f"{MARKER}:ready {bound_host} {bound_port}", flush=True)

    def _stop_on_term(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _stop_on_term)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
    print(f"{MARKER}:stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
