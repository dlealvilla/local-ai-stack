"""A standard-library HTTP server over the Platform API router.

An adapter, and a thin one. It parses a request into an `ApiRequest`, hands
it to the router, and writes the router's answer back. It makes no routing
decision, renders no error, and knows nothing about what any endpoint means.

Replacing it with something asynchronous, or with a framework, should
require changing nothing outside this file. That property is the reason the
router exists separately at all.

`WORKING`, not permanent: single-threaded, no TLS, bound to loopback. See
`docs/DEBT.md`. It is adequate for a control plane an administrator reaches
from the machine it runs on, and is exactly wrong for anything else.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from kultrun.adapters.http import console
from kultrun.api.contracts import ApiRequest, Method
from kultrun.api.router import Router

#: Loopback only. There is no authentication yet, so reachability off-host
#: would be a security defect rather than a feature. See `docs/DEBT.md`.
#: Where the Prototype Console is served. Not under `/v1`: it is not a
#: Platform API surface, it is a client of one.
CONSOLE_PREFIX = "/prototype"

#: A POST body larger than this is ignored rather than read. The mutations
#: that exist take a mount point.
_MAX_BODY_BYTES = 64 * 1024

DEFAULT_ADDRESS = "127.0.0.1"


class PlatformHttpServer:
    """Serves a router over HTTP on the loopback interface."""

    def __init__(
        self, router: Router, *, address: str = DEFAULT_ADDRESS, port: int = 8420
    ) -> None:
        self._router = router
        self._server = HTTPServer((address, port), _make_handler(router))
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The port actually bound, which matters when port 0 was requested."""
        return int(self._server.server_address[1])

    @property
    def address(self) -> str:
        """The address actually bound."""
        return str(self._server.server_address[0])

    def start(self) -> None:
        """Serve in the background."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="kultrun-api", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and release the port.

        Releasing the port is the whole reason this is worth writing
        carefully: a control plane that leaks a listening socket on restart
        cannot restart, and an orphaned port is exactly the class of defect
        `docs/ROADMAP.md` Part II §4.5 is about.
        """
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


@contextmanager
def serving(
    router: Router, *, address: str = DEFAULT_ADDRESS, port: int = 8420
) -> Iterator[PlatformHttpServer]:
    """Serve for the duration of the block, then release the port."""
    server = PlatformHttpServer(router, address=address, port=port)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _make_handler(router: Router) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if self._serve_console(parsed.path):
                return
            request = ApiRequest(
                method=Method.GET,
                path=parsed.path,
                query={
                    key: values[0]
                    for key, values in parse_qs(parsed.query).items()
                    if values
                },
                correlation_id=self.headers.get("X-Correlation-Id"),
            )
            response = router.handle(request)
            self._write(response.status, response.body)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            request = ApiRequest(
                method=Method.POST,
                path=parsed.path,
                query=self._body(),
                correlation_id=self.headers.get("X-Correlation-Id"),
            )
            response = router.handle(request)
            self._write(response.status, response.body)

        def _body(self) -> dict[str, str]:
            """A POST body as flat string parameters.

            Deliberately flattened into the same shape as query parameters
            rather than handed through as arbitrary JSON: the mutations that
            exist take a mount point, and a handler that received free-form
            structure would be a larger surface than any of them needs.
            """
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > _MAX_BODY_BYTES:
                return {}
            try:
                parsed = json.loads(self.rfile.read(length))
            except (OSError, ValueError):
                return {}
            if not isinstance(parsed, dict):
                return {}
            return {
                str(key): str(value)
                for key, value in parsed.items()
                if isinstance(value, str | int | float | bool)
            }

        def _serve_console(self, path: str) -> bool:
            """Serve the Prototype Console's static assets.

            Handled in the transport adapter rather than the Platform API,
            because serving a file is an HTTP concern and the Platform API
            answers in contracts. The console gets its data from `/v1`.
            """
            if path in (CONSOLE_PREFIX, f"{CONSOLE_PREFIX}/"):
                name = "index.html"
            elif path.startswith(f"{CONSOLE_PREFIX}/"):
                name = path[len(CONSOLE_PREFIX) + 1 :]
            else:
                return False
            payload = console.read(name)
            if payload is None:
                self._write(404, {"error": {"code": "not_found", "path": path}})
                return True
            self.send_response(200)
            self.send_header("Content-Type", console.content_type(name))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return True

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Silence the default stderr access log.

            Request logging belongs to the platform's own logging, which is
            deferred; until then, writing to stderr from an adapter would be
            the adapter deciding platform policy.
            """

        def _write(self, status: int, body: dict[str, object]) -> None:
            payload = json.dumps(body, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def build(
    router: Router, *, address: str = DEFAULT_ADDRESS, port: int = 8420
) -> PlatformHttpServer:
    """Factory for the adapter registry."""
    return PlatformHttpServer(router, address=address, port=port)
