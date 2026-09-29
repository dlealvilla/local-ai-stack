"""Lab must not become a Machi product dependency."""

from __future__ import annotations

import ast
import tomllib

from tools.acceptance_lab.paths import repository_root

ROOT = repository_root()


def test_src_machi_does_not_mention_acceptance_lab() -> None:
    hits: list[str] = []
    for path in (ROOT / "src" / "machi").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "acceptance_lab" in alias.name:
                        hits.append(f"{path}:{alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "acceptance_lab" in node.module
            ):
                hits.append(f"{path}:{node.module}")
    assert hits == []


def test_machi_wheel_packages_only_src_machi() -> None:
    with (ROOT / "pyproject.machi.toml").open("rb") as handle:
        data = tomllib.load(handle)
    hatch = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert hatch["packages"] == ["src/machi"]
    assert "tools" not in str(hatch)


def test_machi_console_script_does_not_require_lab() -> None:
    with (ROOT / "pyproject.machi.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert data["project"]["scripts"] == {"machi": "machi.main:main"}
    assert data["project"]["dependencies"] == [
        "PyJWT[crypto]>=2.10,<3",
        "huggingface_hub>=0.26,<1",
    ]
    joined = " ".join(data["project"]["dependencies"])
    assert "acceptance_lab" not in joined
    assert "vllm" not in joined
    assert "torch" not in joined


def test_live_db_is_gitignored() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".local/machi-acceptance/" in text
    assert "*.sqlite3-wal" in text
