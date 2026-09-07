"""Stage 1.4C T2: clean wheel, fixture lifecycle, bounded Hugging Face.

Run from a committed tree after `tools/build_prototype.py`.
Installs the wheel into an isolated venv with no source checkout on path.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
DIST = REPOSITORY / "dist"
NEUTRAL = Path(tempfile.gettempdir())
ACCEPTANCE = "kultrun-hf-acceptance-tiny"
TINYLLAMA = "tinyllama-1.1b-chat-q4"


def latest_wheel() -> Path:
    wheels = sorted(DIST.glob("*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("no wheel in dist/; run tools/build_prototype.py first")
    return wheels[-1]


def run(
    argv: list[str], env: dict[str, str], cwd: Path = NEUTRAL
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, capture_output=True, text=True, check=False, cwd=str(cwd), env=env
    )


def main() -> int:
    wheel = latest_wheel()
    evidence: dict[str, object] = {"wheel": wheel.name}
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-14c-") as workspace:
        root = Path(workspace)
        environment = root / "env"
        venv.create(environment, with_pip=True, system_site_packages=False)
        python = environment / "bin" / "python"
        kultrun = environment / "bin" / "kultrun"
        state = root / "state"
        env = os.environ.copy()
        env["KULTRUN_STATE_ROOT"] = str(state)
        env["KULTRUN_FIXTURE"] = "linux-x86_64-nvidia-blackwell-rtxpro4500"
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)

        installed = run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--quiet",
                f"{wheel}[acquisition]",
            ],
            env,
        )
        if installed.returncode != 0:
            print(installed.stderr)
            return 1
        spec = run(
            [
                str(python),
                "-c",
                "import kultrun,inspect,sys; print(kultrun.__file__)",
            ],
            env,
        )
        origin = (spec.stdout or "").strip()
        evidence["install_origin"] = origin
        if str(REPOSITORY) in origin:
            print("FAIL: installed package resolved from the source checkout")
            return 1

        env["KULTRUN_MODEL_ACQUISITION_PROVIDER"] = "fixture"
        catalog = run([str(kultrun), "models"], env)
        recommend = run([str(kultrun), "models", "recommend"], env)
        empty = run([str(kultrun), "models", "inventory"], env)
        first = run([str(kultrun), "models", "acquire", ACCEPTANCE], env)
        second = run([str(kultrun), "models", "acquire", TINYLLAMA], env)
        two = run([str(kultrun), "models", "inventory"], env)
        if any(
            item.returncode != 0
            for item in (catalog, recommend, empty, first, second, two)
        ):
            print(first.stderr or second.stderr or catalog.stderr)
            return 1
        listing = run(
            [
                str(python),
                "-c",
                "from kultrun.main import build, resolve_configuration;"
                "p=build(resolve_configuration());"
                "print('\\n'.join(a.artifact_id.value+' '+str(a.logical_name)"
                " for a in sorted(p.inventory.artifacts(),"
                " key=lambda a: str(a.logical_name))))",
            ],
            env,
        )
        rows = [line for line in listing.stdout.splitlines() if line.strip()]
        if len(rows) != 2:
            print("FAIL: expected two stored artifacts", listing.stdout)
            return 1
        delete_id = rows[0].split()[0]
        deleted = run([str(kultrun), "models", "delete", delete_id], env)
        left = run(
            [
                str(python),
                "-c",
                "from kultrun.main import build, resolve_configuration;"
                "p=build(resolve_configuration());"
                "arts=list(p.inventory.artifacts());"
                "print(len(arts));"
                "print(arts[0].logical_name if arts else '')",
            ],
            env,
        )
        evidence["fixture"] = {
            "catalog_ok": "tinyllama" in catalog.stdout,
            "recommend_ok": recommend.returncode == 0,
            "empty_inventory": "empty inventory" in empty.stdout,
            "acquired": 2,
            "deleted": delete_id,
            "remaining": left.stdout.strip(),
            "delete_ok": deleted.returncode == 0,
        }
        if left.returncode != 0 or not left.stdout.startswith("1"):
            print("FAIL: delete did not leave one artifact", left.stdout)
            return 1

        env["KULTRUN_MODEL_ACQUISITION_PROVIDER"] = "huggingface"
        hf = run([str(kultrun), "models", "acquire", ACCEPTANCE], env)
        if hf.returncode != 0:
            print(hf.stdout)
            print(hf.stderr)
            return 1
        detail = run(
            [
                str(python),
                "-c",
                "import json,os,importlib.metadata as m;"
                "from pathlib import Path;"
                "from kultrun.kernel.schema import to_dict;"
                "from kultrun.main import build, resolve_configuration;"
                "p=build(resolve_configuration());"
                "arts=[a for a in p.inventory.artifacts()"
                " if a.logical_name=='kultrun-hf-acceptance-tiny'];"
                "a=arts[-1]; d=to_dict(a);"
                "manifest=json.loads("
                "(Path(os.environ['KULTRUN_STATE_ROOT'])/'models'/'artifacts'"
                "/d['artifact_id']/'MANIFEST.json').read_text());"
                "print(json.dumps({"
                "'hub': m.version('huggingface_hub'),"
                "'provider': d['acquisition_provider'],"
                "'provider_version': d['acquisition_provider_version'],"
                "'source_ref': d['source_ref'],"
                "'requested': d['requested_revision'],"
                "'resolved': d['revision'],"
                "'bytes': d['installed_bytes'],"
                "'files': d['file_count'],"
                "'file_names': manifest.get('files'),"
                "'verification': d['verification_method'],"
                "'verification_state': d['verification_state'],"
                "'integrity': d['integrity_evidence'],"
                "'artifact_id': d['artifact_id'],"
                "'state': d['state'],"
                "'license_id': d['license_id'],"
                "'serving': False,"
                "}))",
            ],
            env,
        )
        if detail.returncode != 0:
            print(detail.stderr)
            return 1
        hub = json.loads(detail.stdout)
        if not isinstance(hub, dict):
            print("FAIL: huggingface evidence is not an object")
            return 1
        hub["cli"] = hf.stdout.strip()
        evidence["huggingface"] = hub

        api = run(
            [
                str(python),
                "-c",
                "from kultrun.api.contracts import ApiRequest, Method;"
                "from kultrun.main import build, resolve_configuration;"
                "p=build(resolve_configuration());"
                "r=p.router.handle(ApiRequest(Method.GET,'/v1/models/inventory'));"
                "print(r.status, r.body['payload']['count'],"
                " r.body['payload']['serving'])",
            ],
            env,
        )
        evidence["api"] = api.stdout.strip()
        console = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "print(all(read(n) for n in ASSETS))",
            ],
            env,
        )
        evidence["console_assets"] = console.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if api.returncode != 0 or console.stdout.strip() != "True":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
