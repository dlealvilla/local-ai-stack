"""T1 vLLM HTTP protocol fixture. Not real vLLM and not product evidence."""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.contracts import RuntimeLaunchRequest, RuntimeLaunchSpec

PROTOCOL_SCRIPT = r"""
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer

MODE = os.environ.get("KULTRUN_VLLM_FIXTURE_MODE", "healthy")
HOST = os.environ.get("KULTRUN_VLLM_FIXTURE_HOST", "127.0.0.1")
PORT = int(os.environ.get("KULTRUN_VLLM_FIXTURE_PORT", "0"))
MODEL = os.environ.get("KULTRUN_VLLM_FIXTURE_MODEL", "fixture")
DELAY = float(os.environ.get("KULTRUN_VLLM_FIXTURE_DELAY", "0"))
SLOW = float(os.environ.get("KULTRUN_VLLM_FIXTURE_SLOW", "2"))
STARTED = time.monotonic()

if MODE == "exit-immediately":
    raise SystemExit(1)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            if MODE == "health-fail":
                self._send(500, {"error": "unhealthy"})
                return
            if MODE == "delayed" and (time.monotonic() - STARTED) < DELAY:
                self._send(503, {"error": "loading"})
                return
            self._send(200, {"status": "ok"})
            return
        if self.path == "/v1/models":
            name = "other-model" if MODE == "wrong-model" else MODEL
            self._send(200, {"data": [{"id": name, "object": "model"}]})
            return
        self._send(404, {"error": "missing"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        if self.path != "/v1/completions":
            self._send(404, {"error": "missing"})
            return
        if MODE == "slow-completion":
            time.sleep(SLOW)
        if MODE == "malformed-completion":
            raw = b"not-json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        payload = json.loads(body.decode("utf-8") or "{}")
        prompt = str(payload.get("prompt", ""))
        tokens = int(payload.get("max_tokens") or 8)
        self._send(200, {
            "id": "cmpl-fixture",
            "model": MODEL,
            "choices": [{"text": "ok:" + prompt[:80], "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": max(1, len(prompt.split()) or 1),
                "completion_tokens": tokens,
            },
        })

HTTPServer((HOST, PORT), Handler).serve_forever()
"""


class ProtocolServer:
    """In-process OpenAI-shaped vLLM stand-in for adapter unit tests."""

    def __init__(
        self,
        *,
        mode: str = "healthy",
        model: str = "probe-model",
        delay: float = 0.0,
        slow: float = 2.0,
        port: int = 0,
    ) -> None:
        this = self
        self.mode = mode
        self.model = model
        self.delay = delay
        self.slow = slow
        self.started = time.monotonic()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                if self.path == "/health":
                    if this.mode == "health-fail":
                        self._send(500, {"error": "unhealthy"})
                        return
                    if (
                        this.mode == "delayed"
                        and (time.monotonic() - this.started) < this.delay
                    ):
                        self._send(503, {"error": "loading"})
                        return
                    self._send(200, {"status": "ok"})
                    return
                if self.path == "/v1/models":
                    name = "other-model" if this.mode == "wrong-model" else this.model
                    self._send(200, {"data": [{"id": name, "object": "model"}]})
                    return
                self._send(404, {"error": "missing"})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                if self.path != "/v1/completions":
                    self._send(404, {"error": "missing"})
                    return
                if this.mode == "slow-completion":
                    time.sleep(this.slow)
                if this.mode == "malformed-completion":
                    raw = b"not-json"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                payload = json.loads(body.decode("utf-8") or "{}")
                prompt = str(payload.get("prompt", ""))
                tokens = int(payload.get("max_tokens") or 8)
                self._send(
                    200,
                    {
                        "id": "cmpl-fixture",
                        "model": this.model,
                        "choices": [
                            {"text": "ok:" + prompt[:80], "finish_reason": "stop"}
                        ],
                        "usage": {
                            "prompt_tokens": max(1, len(prompt.split()) or 1),
                            "completion_tokens": tokens,
                        },
                    },
                )

        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = int(self._httpd.server_address[1])
        self.address = "127.0.0.1"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=1)


def wrap_launch_with_protocol(
    original: Any,
    *,
    mode: str = "healthy",
    delay: float = 0.4,
    slow: float = 2.0,
) -> Any:
    """Keep real launch validation, exec the protocol fixture instead of vLLM."""

    def launch_spec(
        self: VllmRuntimeSupport, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        spec = original(self, request)
        assert request is not None
        port = int(request.bind_port) if is_resolved(request.bind_port) else 0
        served = str(request.served_model) if is_resolved(request.served_model) else ""
        extra = (
            f"KULTRUN_VLLM_FIXTURE_MODE={mode}",
            f"KULTRUN_VLLM_FIXTURE_HOST={request.bind_address}",
            f"KULTRUN_VLLM_FIXTURE_PORT={port}",
            f"KULTRUN_VLLM_FIXTURE_MODEL={served}",
            f"KULTRUN_VLLM_FIXTURE_DELAY={delay}",
            f"KULTRUN_VLLM_FIXTURE_SLOW={slow}",
        )
        return replace(
            spec,
            executable=sys.executable,
            arguments=("-c", PROTOCOL_SCRIPT),
            environment=spec.environment + extra,
            grace_period_seconds=2.0,
        )

    return launch_spec
