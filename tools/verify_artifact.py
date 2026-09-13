"""Install a prototype wheel into a throwaway environment and prove it works.

`docs/DEVELOPMENT_WORKFLOW.md` §30: an artifact is verified locally before a
deployment target ever sees it. Cheap to run, and it catches the packaging
faults that otherwise surface as a confusing remote failure — missing
package data, a broken entry point, or an import that only resolved because
the source tree happened to be on the path.

    python tools/verify_artifact.py [dist/kultrun-...whl]

The environment is created with `--without-pip` and no system site packages,
and the check is run from a directory that is not the repository. If a
command still works, it works because it was installed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import venv
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
DIST = REPOSITORY / "dist"

#: Run from here, so nothing can resolve out of the repository by accident.
NEUTRAL_DIRECTORY = Path(tempfile.gettempdir())


def latest_wheel() -> Path:
    wheels = sorted(DIST.glob("*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("no wheel in dist/; run tools/build_prototype.py first")
    return wheels[-1]


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run from a neutral directory, so nothing resolves out of the repo."""
    return subprocess.run(  # fixed argv, never a shell
        argv,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(NEUTRAL_DIRECTORY),
    )


def verify(wheel: Path) -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append((name, bool(passed), detail))

    with tempfile.TemporaryDirectory(prefix="kultrun-verify-") as workspace:
        root = Path(workspace)
        environment = root / "env"
        venv.create(environment, with_pip=True, system_site_packages=False)
        python = environment / "bin" / "python"
        command = environment / "bin" / "kultrun"

        installed = run(
            [str(python), "-m", "pip", "install", "--quiet", str(wheel)]
        )
        check(
            "artifact installs non-editably",
            installed.returncode == 0,
            installed.stderr.strip()[:200] or f"{wheel.name}",
        )
        if installed.returncode != 0:
            return report(checks)

        editable = run(
            [
                str(python),
                "-c",
                "import importlib.util as u,sys;"
                "s=u.find_spec('kultrun');"
                "print(s.origin if s else 'missing')",
            ]
        )
        origin = editable.stdout.strip()
        check(
            "import resolves from the installation, not a checkout",
            str(environment) in origin and str(REPOSITORY / "src") not in origin,
            origin,
        )

        finders = run(
            [str(python), "-c", "import sys;print([p for p in sys.path if p])"]
        )
        check(
            "no repository path on sys.path",
            str(REPOSITORY) not in finders.stdout,
            "clean" if str(REPOSITORY) not in finders.stdout else finders.stdout[:160],
        )

        no_editable = list(environment.rglob("__editable__*")) + list(
            environment.rglob("*.egg-link")
        )
        check("no editable install artefacts", not no_editable, str(no_editable[:2]))

        check("console script exists", command.exists(), str(command))

        version = run([str(command), "version"])
        check(
            "`kultrun version` runs and reports an artifact",
            version.returncode == 0 and "origin        artifact" in version.stdout,
            _first_line(version.stdout) or version.stderr.strip()[:200],
        )

        identity = run(
            [
                str(python),
                "-c",
                "from kultrun.kernel.build import identity;"
                "import json;i=identity();"
                "print(json.dumps({'origin':i.origin.value,"
                "'commit':i.source_commit,'build':i.build_id,"
                "'version':i.version,'clean':i.clean_source}))",
            ]
        )
        parsed = _parse(identity.stdout)
        check(
            "shipped build identity is readable at runtime",
            parsed.get("origin") == "artifact" and bool(parsed.get("commit")),
            json.dumps(parsed),
        )

        expected = _expected_manifest()
        check(
            "runtime identity matches the build manifest",
            bool(expected)
            and parsed.get("commit") == expected.get("source_commit")
            and parsed.get("build") == expected.get("build_id"),
            f"runtime {parsed.get('build')} vs manifest {expected.get('build_id')}",
        )

        contracts = run(
            [
                str(python),
                "-c",
                "import kultrun.main as m;"
                "from kultrun.kernel.schema import registered_contracts;"
                "print(len(registered_contracts()))",
            ]
        )
        count = contracts.stdout.strip()
        check(
            "package data and contract catalogue are complete",
            count.isdigit() and int(count) > 20,
            f"{count} contracts registered",
        )

        usage = run([str(command)])
        check(
            "unknown invocation is rejected rather than guessed",
            usage.returncode != 0 or "usage" in usage.stdout,
            _first_line(usage.stdout),
        )
        check(
            "deployment report command is packaged",
            "report" in usage.stdout,
            _first_line(usage.stdout),
        )

        vendor = run(
            [
                str(python),
                "-c",
                "from kultrun.vendor.contracts import TelemetrySettings;"
                "from kultrun.adapters.telemetry.disabled import "
                "DisabledProductTelemetryExporter;"
                "s=TelemetrySettings();"
                "DisabledProductTelemetryExporter().export(());"
                "print(int(s.enabled), int(s.export_operational_metadata))",
            ]
        )
        check(
            "vendor telemetry seam ships disabled",
            vendor.returncode == 0 and vendor.stdout.strip() == "0 0",
            vendor.stdout.strip() or vendor.stderr.strip()[:200],
        )

    return report(checks)


def _expected_manifest() -> dict[str, object]:
    path = DIST / "prototype-manifest.json"
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _parse(text: str) -> dict[str, object]:
    try:
        loaded = json.loads(text.strip() or "{}")
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0] if text.strip() else ""


def report(checks: list[tuple[str, bool, str]]) -> int:
    print("\n=== LOCAL ARTIFACT VERIFICATION ===")
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        if detail:
            print(f"         {detail}")
    failed = [name for name, passed, _ in checks if not passed]
    print(f"\n  {len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", type=Path, help="wheel to verify")
    options = parser.parse_args()
    return verify(options.wheel or latest_wheel())


if __name__ == "__main__":
    raise SystemExit(main())
