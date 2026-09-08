"""Stage 1.6E T2: clean wheel proves bounded foundation selection.

Installs the committed wheel into an isolated venv with no source checkout.
Proves AUTO selection → realize → verify → VERIFIED executable, MANUAL
refusal of a blocked candidate, stale seam on model selection, API/CLI/
Console. Does not install or import real vLLM. Does not score foundations.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from venv import EnvBuilder

REPOSITORY = Path(__file__).resolve().parent.parent
DIST = REPOSITORY / "dist"
NEUTRAL = Path(tempfile.gettempdir())


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
    evidence: dict[str, object] = {
        "wheel": wheel.name,
        "real_llm": False,
        "prompt_inference": False,
        "vllm_imported": False,
        "weighted_scoring": False,
        "fixture_provisioner": True,
        "fixture_verifier": True,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16e-") as workspace:
        root = Path(workspace)
        environment = root / "env"
        EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
        python = environment / "bin" / "python"
        kultrun = environment / "bin" / "kultrun"
        state = root / "state"
        env = os.environ.copy()
        env["KULTRUN_STATE_ROOT"] = str(state)
        env["KULTRUN_FIXTURE"] = "linux-x86_64-nvidia-blackwell-rtxpro4500"
        env["KULTRUN_MODEL_ACQUISITION_PROVIDER"] = "fixture"
        env["KULTRUN_RUNTIME_PROVISIONER"] = "fixture"
        env["KULTRUN_RUNTIME_VERIFIER"] = "fixture"
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)
        env.pop("KULTRUN_EXECUTOR", None)

        installed = run(
            [str(python), "-m", "pip", "install", "--quiet", str(wheel)], env
        )
        if installed.returncode != 0:
            print(installed.stderr)
            return 1
        origin = run(
            [str(python), "-c", "import kultrun; print(kultrun.__file__)"], env
        )
        evidence["install_origin"] = (origin.stdout or "").strip()
        if str(REPOSITORY) in (origin.stdout or ""):
            print("FAIL: installed package resolved from the source checkout")
            return 1

        version = run([str(kultrun), "version"], env)
        if version.returncode != 0:
            print(version.stderr or version.stdout)
            return 1
        evidence["version"] = version.stdout.strip()

        proof = run(
            [
                str(python),
                "-c",
                """
import json
from kultrun.api.contracts import ApiRequest, Method
from kultrun.main import build, resolve_configuration
from kultrun.runtime.contracts import VerificationStatus

p = build(resolve_configuration())
viewed = p.router.handle(ApiRequest(method=Method.GET, path='/v1/runtimes/foundation'))
assert viewed.status == 200
payload = viewed.body['payload']
assert payload['mutations'] is False
assert payload['verify'] is False
assert payload['selection_mode'] == 'auto'
assert payload['resolver_mode'] == 'auto'
assert payload['recommended_candidate_id']
blocked = payload['blocked']
assert blocked
refused = p.router.handle(ApiRequest(
    method=Method.POST,
    path='/v1/runtimes/foundation/select',
    query={'mode': 'manual', 'candidate_id': blocked[0]},
))
assert refused.status == 412
recommended = payload['recommended_candidate_id']
manual = p.router.handle(ApiRequest(
    method=Method.POST,
    path='/v1/runtimes/foundation/select',
    query={'mode': 'manual', 'candidate_id': recommended},
))
assert manual.status == 200
held = manual.body['payload']
assert held['selection_mode'] == 'manual'
assert held['selected_candidate_id'] == recommended
assert held['recommended_candidate_id'] == recommended
returned = p.router.handle(ApiRequest(
    method=Method.POST,
    path='/v1/runtimes/foundation/select',
    query={'mode': 'auto'},
))
assert returned.status == 200
choice = returned.body['payload']
assert choice['selection_mode'] == 'auto'
assert choice['selected_candidate_id'] == choice['recommended_candidate_id']
assert choice['downstream_stale'] is True
realized = p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/realize'))
assert realized.status == 200
installation = realized.body['payload']
assert installation['status'] == 'installed'
verified = p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/verify'))
assert verified.status == 200
profile = verified.body['payload']
assert profile['status'] == VerificationStatus.VERIFIED.value
again = p.router.handle(ApiRequest(method=Method.GET, path='/v1/runtimes/foundation'))
assert again.status == 200
fresh = again.body['payload']
assert fresh['verified_executable']
assert fresh['selected_candidate_id'] in fresh['verified_executable']
models = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/selection'))
assert models.status == 200
assert models.body['payload']['foundation_stale'] is True
restarted = build(resolve_configuration())
reloaded = restarted.router.handle(ApiRequest(method=Method.GET, path='/v1/runtimes/foundation'))
assert reloaded.status == 200
restored = reloaded.body['payload']
assert restored['selection_mode'] == 'auto'
assert restored['selected_candidate_id'] == choice['selected_candidate_id']
print(json.dumps({
    'selected_candidate_id': choice['selected_candidate_id'],
    'installation_id': installation['installation_id'],
    'profile_id': profile['profile_id'],
    'status': profile['status'],
    'verified_executable': fresh['verified_executable'],
    'foundation_stale': True,
    'blocked_refused': refused.status,
    'manual_then_auto': True,
    'restart_mode': restored['selection_mode'],
}))
""",
            ],
            env,
        )
        if proof.returncode != 0:
            print(proof.stderr or proof.stdout)
            return 1
        try:
            payload = json.loads(proof.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError:
            print("FAIL: proof output", proof.stdout)
            return 1
        evidence.update(payload)

        listed = run([str(kultrun), "runtimes", "foundation"], env)
        if listed.returncode != 0:
            print(listed.stderr or listed.stdout)
            return 1
        evidence["cli_foundation"] = listed.stdout.strip()
        manual_cli = run(
            [
                str(kultrun),
                "runtimes",
                "select",
                "--candidate",
                str(payload["selected_candidate_id"]),
            ],
            env,
        )
        if manual_cli.returncode != 0:
            print(manual_cli.stderr or manual_cli.stdout)
            return 1
        evidence["cli_select_manual"] = manual_cli.stdout.strip()
        if "manual" not in manual_cli.stdout:
            print("FAIL: CLI MANUAL", manual_cli.stdout)
            return 1
        selected = run([str(kultrun), "runtimes", "select", "--auto"], env)
        if selected.returncode != 0:
            print(selected.stderr or selected.stdout)
            return 1
        evidence["cli_select"] = selected.stdout.strip()
        if "auto" not in selected.stdout:
            print("FAIL: CLI return-to-AUTO", selected.stdout)
            return 1
        realized = run([str(kultrun), "runtimes", "realize"], env)
        if realized.returncode != 0:
            print(realized.stderr or realized.stdout)
            return 1
        verified = run([str(kultrun), "runtimes", "verify", "--selected"], env)
        if verified.returncode != 0 or "verified" not in verified.stdout:
            print("FAIL: verify --selected", verified.stdout)
            return 1
        evidence["cli_verify_selected"] = verified.stdout.strip()

        inspect = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "panel=html.split('candidates-panel',1)[1].split('<section',1)[0];"
                "print(all(read(n) for n in ASSETS),"
                " 'Runtime candidates' in html,"
                " '/runtimes/foundation' in js,"
                " 'Select foundation' in js,"
                " 'Use AUTO' in js,"
                " 'Recommended Runtime' not in js,"
                " 'Select Model' not in js,"
                " 'Verify' not in panel)",
            ],
            env,
        )
        evidence["console"] = inspect.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if payload.get("status") != "verified":
            print("FAIL: profile", payload)
            return 1
        if "True True True True True True True True" not in inspect.stdout:
            print("FAIL: Console", inspect.stdout)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
