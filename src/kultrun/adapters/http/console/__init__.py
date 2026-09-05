"""The Prototype Console's static assets.

Lives inside the HTTP adapter that serves it, rather than as its own
architecture position. Serving a file is a transport concern, and the
console is a **client** of the Platform API, not a part of it — it reaches
the platform the same way any other client would, over `/v1`. If it ever
becomes the real Admin UI, that is a deliberate architecture change with a
position of its own.

A package so the files ship inside the wheel and can be located through
`importlib.resources` rather than a path relative to a source tree.

The console holds **no product intelligence**: every number, judgement and
status it shows comes from the Platform API. It formats and lays out; it
never decides. A classification made in the browser would be untested,
unversioned and invisible to the architecture tests.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

#: Served under `/prototype`. Listed explicitly so a packaging test can
#: assert each one is present in a built artifact — a console that silently
#: vanished from the wheel would fail only on a deployment target.
ASSETS: tuple[str, ...] = ("index.html", "style.css", "app.js")

CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def asset_root() -> Path:
    """Where the assets live, inside the installed package."""
    return Path(str(resources.files(__name__)))


def read(name: str) -> bytes | None:
    """One asset's bytes, or None when it is not a console asset.

    An allow-list, so a request path can never be used to read a file that
    was not meant to be served. Path traversal is not a risk to mitigate
    here; it is a shape the code cannot express.
    """
    if name not in ASSETS:
        return None
    try:
        return (asset_root() / name).read_bytes()
    except OSError:
        return None


def content_type(name: str) -> str:
    return CONTENT_TYPES.get(Path(name).suffix, "application/octet-stream")
