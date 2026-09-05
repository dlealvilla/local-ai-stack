"""Packaging and build identity.

The deployment workflow rests on one claim: a real-host observation can be
traced back to the source state that produced it. These tests protect the
parts of that claim which can be checked without building a wheel — the rest
is `tools/verify_artifact.py`, which installs one into a throwaway
environment.

The test worth naming is `test_a_source_checkout_does_not_claim_to_be_a_build`.
A source tree quietly reporting itself as a built artifact would let a
development run masquerade as acceptance evidence, and nothing downstream
would ever notice.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from kultrun.kernel.build import (
    MANIFEST_NAME,
    BuildOrigin,
    identity,
)

REPOSITORY = Path(__file__).resolve().parent.parent
PYPROJECT = REPOSITORY / "pyproject.toml"


@pytest.fixture(scope="module")
def project() -> dict[str, object]:
    with PYPROJECT.open("rb") as handle:
        loaded: dict[str, object] = tomllib.load(handle)
    return loaded


def manifest(path: Path, **overrides: object) -> Path:
    """Write a build manifest as the build tool would."""
    content: dict[str, object] = {
        "version": "0.1.0",
        "source_commit": "a" * 40,
        "build_id": "0.1.0+aaaaaaaaaaaa",
        "built_at": "2026-09-05T12:00:00+00:00",
        "clean_source": True,
    }
    content.update(overrides)
    (path / MANIFEST_NAME).write_text(json.dumps(content), encoding="utf-8")
    return path


class TestBuildIdentity:
    def test_a_source_checkout_does_not_claim_to_be_a_build(
        self, tmp_path: Path
    ) -> None:
        """No manifest means a checkout, and it must say so.

        If this ever passes wrongly, a development run can be mistaken for
        acceptance evidence and the whole workflow's guarantee is gone.
        """
        found = identity(tmp_path)
        assert found.origin is BuildOrigin.SOURCE
        assert found.is_artifact is False
        assert found.acceptable_as_evidence is False
        assert found.source_commit is None
        assert "source checkout" in found.describe()

    def test_the_live_source_tree_reports_itself_as_source(self) -> None:
        """These tests run from the repository, so this must hold here."""
        assert identity().origin is BuildOrigin.SOURCE

    def test_a_shipped_manifest_is_read(self, tmp_path: Path) -> None:
        found = identity(manifest(tmp_path))
        assert found.origin is BuildOrigin.ARTIFACT
        assert found.source_commit == "a" * 40
        assert found.build_id == "0.1.0+aaaaaaaaaaaa"
        assert found.acceptable_as_evidence is True

    def test_a_dirty_build_is_not_acceptable_evidence(self, tmp_path: Path) -> None:
        """Iterating from a dirty tree is fine; accepting the result is not."""
        found = identity(manifest(tmp_path, clean_source=False))
        assert found.is_artifact is True
        assert found.acceptable_as_evidence is False
        assert "WIP" in found.describe()

    def test_an_unreadable_manifest_falls_back_rather_than_crashing(
        self, tmp_path: Path
    ) -> None:
        """A build that cannot describe itself must still start.

        Reporting `source` is wrong in a visible way. Refusing to start
        would take the platform down over a diagnostic file.
        """
        (tmp_path / MANIFEST_NAME).write_text("{not json", encoding="utf-8")
        assert identity(tmp_path).origin is BuildOrigin.SOURCE

    def test_a_manifest_missing_fields_is_still_an_artifact(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / MANIFEST_NAME).write_text('{"version": "9.9.9"}', encoding="utf-8")
        found = identity(tmp_path)
        assert found.origin is BuildOrigin.ARTIFACT
        assert found.build_id is None
        assert found.clean_source is None
        assert found.acceptable_as_evidence is False


class TestThePackageCanBeBuilt:
    def test_a_console_script_is_declared(self, project: dict[str, object]) -> None:
        scripts = project["project"]["scripts"]  # type: ignore[index]
        assert scripts == {"kultrun": "kultrun.main:main"}

    def test_the_declared_entry_point_resolves(self) -> None:
        """A console script naming a callable that does not exist installs
        cleanly and fails only when a deployment target runs it."""
        from kultrun.main import main

        assert callable(main)
        assert main([]) == 2  # no arguments is a usage error
        assert main(["--help"]) == 0

    def test_the_build_identity_is_force_included_in_the_wheel(
        self, project: dict[str, object]
    ) -> None:
        """The manifest is gitignored, so packaging must include it anyway.

        Without this the wheel builds successfully and every deployed
        instance reports itself as a source checkout — which is how it was
        found the first time.
        """
        wheel = project["tool"]["hatch"]["build"]["targets"]["wheel"]  # type: ignore[index]
        assert f"src/kultrun/{MANIFEST_NAME}" in wheel["artifacts"]

    def test_the_manifest_is_not_committed(self) -> None:
        """It names a commit, so a stale copy would be an active lie."""
        ignore = (REPOSITORY / ".gitignore").read_text(encoding="utf-8")
        assert f"src/kultrun/{MANIFEST_NAME}" in ignore
        assert not (REPOSITORY / "src" / "kultrun" / MANIFEST_NAME).exists()

    def test_the_package_has_no_runtime_dependencies(
        self, project: dict[str, object]
    ) -> None:
        """Kultrun installs on an air-gapped host with no wheel to fetch.

        Every dependency added here is one an offline deployment target must
        already have, so the empty list is a property worth protecting.
        """
        assert project["project"]["dependencies"] == []  # type: ignore[index]
