"""Stage 1.6F T2: clean wheel proves runtime-aware eligible models.

Installs the committed wheel into an isolated venv with no source checkout.
Proves selected foundation → installation → VERIFIED profile → EligibleModelView
CURRENT with ELIGIBLE, BLOCKED, and UNRESOLVED, then profile-basis STALE.
Does not install or import real vLLM. Does not remap capacity.
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
        "capacity_remapped": False,
        "fixture_provisioner": True,
        "fixture_verifier": True,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16f-") as workspace:
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
from kultrun.runtime.contracts import EligibleViewStatus, RuntimeEligibilityStatus, VerificationStatus

p = build(resolve_configuration())
empty = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/eligible'))
assert empty.status == 200
payload = empty.body['payload']
assert payload['mutations'] is False
assert payload['acquire'] is False
assert payload['capacity'] is False
assert payload['inventory'] is False
assert payload['status'] == EligibleViewStatus.UNAVAILABLE.value
p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/select', query={'mode': 'auto'}))
realized = p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/realize'))
assert realized.status == 200
verified = p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/verify'))
assert verified.status == 200
assert verified.body['payload']['status'] == VerificationStatus.VERIFIED.value
eligible = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/eligible'))
assert eligible.status == 200
body = eligible.body['payload']
assert body['status'] == EligibleViewStatus.CURRENT.value
assert body['authoritative'] is True
assert body['eligible_count'] >= 1
assert body['blocked_count'] >= 1
assert body['unresolved_count'] >= 1
statuses = {item['status'] for item in body['candidates']}
assert RuntimeEligibilityStatus.ELIGIBLE.value in statuses
assert RuntimeEligibilityStatus.BLOCKED.value in statuses
assert RuntimeEligibilityStatus.UNRESOLVED.value in statuses
selection = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/selection'))
assert selection.status == 200
select = selection.body['payload']
assert select['runtime_eligibility_status'] == EligibleViewStatus.CURRENT.value
assert select['runtime_eligibility_authoritative'] is True
foundation = p.router.handle(ApiRequest(method=Method.GET, path='/v1/runtimes/foundation'))
blocked = foundation.body['payload']['blocked']
assert blocked
changed = p.router.handle(ApiRequest(
    method=Method.POST,
    path='/v1/runtimes/foundation/select',
    query={'mode': 'manual', 'candidate_id': blocked[0]},
))
assert changed.status == 412
print(json.dumps({
    'status': body['status'],
    'eligible_count': body['eligible_count'],
    'blocked_count': body['blocked_count'],
    'unresolved_count': body['unresolved_count'],
    'selected_candidate_id': body['selected_candidate_id'],
    'runtime': body['runtime'],
    'profile_status': body['profile_status'],
    'blocked_refused': changed.status,
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

        listed = run([str(kultrun), "models", "eligible"], env)
        if listed.returncode != 0:
            print(listed.stderr or listed.stdout)
            return 1
        evidence["cli_eligible"] = listed.stdout.strip()
        if "view current" not in listed.stdout:
            print("FAIL: CLI eligible view", listed.stdout)
            return 1
        if "eligible" not in listed.stdout or "blocked" not in listed.stdout:
            print("FAIL: CLI missing statuses", listed.stdout)
            return 1
        if "unresolved" not in listed.stdout:
            print("FAIL: CLI missing unresolved", listed.stdout)
            return 1

        restart = run(
            [
                str(python),
                "-c",
                """
import json
from kultrun.api.contracts import ApiRequest, Method
from kultrun.main import build, resolve_configuration
from kultrun.runtime.contracts import EligibleViewStatus

p = build(resolve_configuration())
eligible = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/eligible'))
assert eligible.status == 200
body = eligible.body['payload']
assert body['status'] == EligibleViewStatus.CURRENT.value
assert body['eligible_count'] >= 1
print(json.dumps({'restart_status': body['status']}))
""",
            ],
            env,
        )
        if restart.returncode != 0:
            print(restart.stderr or restart.stdout)
            return 1
        evidence["restart"] = json.loads(restart.stdout.strip().splitlines()[-1])

        invalid = run(
            [
                str(python),
                "-c",
                """
import json
from dataclasses import replace
from kultrun.main import build, resolve_configuration
from kultrun.platform.eligibility import catalog_facts
from kultrun.runtime.contracts import EligibleViewStatus, RuntimePolicy

p = build(resolve_configuration())
host = p.hosts.current
executors = (p.executions.capabilities(host), p.plane.container_capability(host))
descriptors = p.runtimes.descriptors()
accelerator = replace(host.accelerators[0], driver_version='changed-driver')
shifted = replace(host, accelerators=(accelerator, *host.accelerators[1:]))
stale = p.eligibility.evaluate(
    shifted,
    executors,
    descriptors,
    catalog_facts(p.models),
    RuntimePolicy(),
    components={'vllm': 'missing'},
)
assert stale.status is EligibleViewStatus.STALE
print(json.dumps({'invalidation': stale.status.value}))
""",
            ],
            env,
        )
        if invalid.returncode != 0:
            print(invalid.stderr or invalid.stdout)
            return 1
        evidence.update(json.loads(invalid.stdout.strip().splitlines()[-1]))

        inspect = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Eligible models' in html,"
                " '/models/eligible' in js,"
                " 'declared runtimes' in js,"
                " 'Select Model' not in js)",
            ],
            env,
        )
        evidence["console"] = inspect.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if payload.get("status") != "current":
            print("FAIL: eligible view", payload)
            return 1
        if evidence.get("invalidation") != "stale":
            print("FAIL: invalidation", evidence)
            return 1
        if "True True True True True" not in inspect.stdout:
            print("FAIL: console", inspect.stdout)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
