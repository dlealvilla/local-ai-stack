"""Loopback Ollama HTTP seam. A local stub stands in for the daemon."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from machi.adapters.model.ollama_api import OllamaApiError
from machi.adapters.model.ollama_http import (
    LoopbackOllamaClient,
    candidate_from_catalog,
)
from machi.kernel.schema import to_dict

DIGEST = "ab" * 32
_PROMPT = "Reply with ok."


class _Script(HTTPServer):
    def __init__(self, mode: str) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.mode = mode
        self.seen: list[tuple[str, str, object]] = []
        self.loaded = False


class _Handler(BaseHTTPRequestHandler):
    server: _Script

    def do_GET(self) -> None:
        self._read(None)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else None
        self._read(body)

    def _read(self, body: object) -> None:
        script = self.server
        script.seen.append((self.command, self.path, body))
        if script.mode == "malformed":
            self._send(200, b"{")
            return
        if script.mode == "shape":
            self._send(200, b'{"models":{}}')
            return
        if script.mode == "bounded":
            self._send(200, b'{"pad":"' + (b"x" * 80) + b'"}')
            return
        if script.mode == "timeout":
            import time

            time.sleep(2)
            self._send(200, b"{}")
            return
        if script.mode == "memory":
            self._send(
                500,
                b'{"error":"model requires more system memory than available"}',
            )
            return
        if self.path == "/api/tags":
            payload = {
                "models": [
                    {
                        "name": "tiny:latest",
                        "digest": f"sha256:{DIGEST}",
                        "size": 1000,
                        "details": {"family": "llama"},
                    }
                ]
            }
            self._send(200, json.dumps(payload).encode())
            return
        if self.path == "/api/show":
            payload = {
                "details": {
                    "family": "llama",
                    "format": "gguf",
                    "quantization_level": "Q8_0",
                    "parameter_size": "135M",
                }
            }
            self._send(200, json.dumps(payload).encode())
            return
        if self.path == "/api/ps":
            models = []
            if script.loaded:
                models.append(
                    {
                        "name": "tiny:latest",
                        "digest": f"sha256:{DIGEST}",
                        "size": 1000,
                        "size_vram": 800,
                        "expires_at": "2026-09-24T00:00:00Z",
                    }
                )
            self._send(200, json.dumps({"models": models}).encode())
            return
        if self.path == "/api/generate" and isinstance(body, dict):
            keep = body.get("keep_alive")
            payload: dict[str, object] = {}
            if keep == 0:
                script.loaded = False
            elif body.get("prompt") == "":
                script.loaded = True
                payload = {
                    "load_duration": 2_500_000_000,
                    "response": "hidden preload",
                }
            else:
                script.loaded = True
                payload = {
                    "load_duration": 9_000_000_000,
                    "prompt_eval_count": 2,
                    "prompt_eval_duration": 1000,
                    "eval_count": 4,
                    "eval_duration": 500_000_000,
                    "response": "hidden answer",
                }
            self._send(200, json.dumps(payload).encode())
            return
        self._send(404, b'{"error":"missing"}')

    def _send(self, status: int, raw: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args: object) -> None:
        del fmt, args


def _start(mode: str = "ok") -> tuple[_Script, str]:
    server = _Script(mode)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_endpoint_policy_rejects_non_loopback() -> None:
    for endpoint in (
        "https://127.0.0.1:11434",
        "http://127.0.0.1",
        "http://example.com:11434",
        "http://user:secret@127.0.0.1:11434",
        "http://8.8.8.8:11434",
    ):
        with pytest.raises(OllamaApiError) as caught:
            LoopbackOllamaClient(endpoint)
        assert caught.value.code == "endpoint"


def test_requests_timeouts_shape_and_timing() -> None:
    server, endpoint = _start()
    try:
        client = LoopbackOllamaClient(endpoint)
        listed = client.list_models()
        shown = client.show_model("tiny:latest")
        preloaded = client.preload("tiny:latest")
        running = client.running_models()
        generated = client.generate_probe("tiny:latest")
        unloaded = client.unload("tiny:latest")
        absent = client.running_models()
    finally:
        server.shutdown()
    assert listed[0].digest == f"sha256:{DIGEST}"
    assert shown is not None
    assert shown.family == "llama"
    assert shown.quantization == "Q8_0"
    assert shown.format_label == "gguf"
    assert shown.layer_count is None
    assert preloaded.failure == "none"
    assert preloaded.load_seconds == 2.5
    assert running[0].size_vram_bytes == 800
    assert generated.input_tokens == 2
    assert generated.output_tokens == 4
    assert generated.generation_seconds == 0.5
    assert unloaded.failure == "none"
    assert absent == ()
    methods = [(item[0], item[1]) for item in server.seen]
    assert methods == [
        ("GET", "/api/tags"),
        ("POST", "/api/show"),
        ("POST", "/api/generate"),
        ("GET", "/api/ps"),
        ("POST", "/api/generate"),
        ("POST", "/api/generate"),
        ("GET", "/api/ps"),
    ]
    preload_body = server.seen[2][2]
    probe_body = server.seen[4][2]
    unload_body = server.seen[5][2]
    assert isinstance(preload_body, dict)
    assert preload_body["keep_alive"] == -1
    assert preload_body["stream"] is False
    assert preload_body["prompt"] == ""
    assert isinstance(probe_body, dict)
    assert probe_body["keep_alive"] == -1
    assert probe_body["prompt"] == _PROMPT
    assert probe_body["options"] == {"num_predict": 8}
    assert isinstance(unload_body, dict)
    assert unload_body["keep_alive"] == 0
    candidate = candidate_from_catalog(listed[0], shown)
    rendered = json.dumps(to_dict(candidate))
    assert "hidden answer" not in rendered
    assert _PROMPT not in rendered
    assert "135M" not in rendered


def test_transport_failures_fail_closed() -> None:
    malformed, malformed_url = _start("malformed")
    shape, shape_url = _start("shape")
    bounded, bounded_url = _start("bounded")
    memory, memory_url = _start("memory")
    slow, slow_url = _start("timeout")
    try:
        with pytest.raises(OllamaApiError) as bad_json:
            LoopbackOllamaClient(malformed_url).list_models()
        assert bad_json.value.code == "malformed"
        with pytest.raises(OllamaApiError) as bad_shape:
            LoopbackOllamaClient(shape_url).list_models()
        assert bad_shape.value.code == "shape"
        with pytest.raises(OllamaApiError) as huge:
            LoopbackOllamaClient(bounded_url, max_body=16).list_models()
        assert huge.value.code == "bounded"
        assert LoopbackOllamaClient(memory_url).preload("tiny:latest").failure == (
            "no_fit"
        )
        timed = LoopbackOllamaClient(slow_url, connect_timeout=0.2, read_timeout=0.2)
        assert timed.preload("tiny:latest").failure == "timeout"
    finally:
        for server in (malformed, shape, bounded, memory, slow):
            server.shutdown()
