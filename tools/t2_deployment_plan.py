"""Stage 1.6I T2: clean wheel proves authoritative DeploymentPlan.

Installs the committed wheel into an isolated venv with no source checkout.
Proves verified runtime → eligible → requirement → capacity → selection →
CURRENT DeploymentPlan, MANUAL selected model, invalidation, refresh, and
no execution. Does not acquire, admit, or start inference.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
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
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    evidence: dict[str, object] = {
        "wheel": wheel.name,
        "sha256": digest,
        "real_llm": False,
        "deployment_plan_authoritative": True,
        "plan_from_authoritative": False,
        "selected_deployment_candidate": False,
        "fixture_provisioner": True,
        "fixture_verifier": True,
        "acquire": False,
        "admit": False,
        "launch": False,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16i-") as workspace:
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
                r"""
import json
from kultrun.api.contracts import ApiRequest, Method
from kultrun.main import build, resolve_configuration

p = build(resolve_configuration())
def call(path, method=Method.GET, **query):
    return p.router.handle(ApiRequest(method=method, path=path, query=query))
assert call('/v1/runtimes/foundation/select', Method.POST, mode='auto').status == 200
assert call('/v1/runtimes/foundation/realize', Method.POST).status == 200
assert call('/v1/runtimes/foundation/verify', Method.POST).status == 200
unread = call('/v1/deployments/plan')
assert unread.status == 200
assert unread.body['payload']['status'] == 'unavailable'
assert unread.body['payload']['mutations'] is False
assert p.inventory.artifacts() == ()
assert p.resources.reservations() == ()
assert p.instances.list() == ()
created = call('/v1/deployments/plan', Method.POST)
assert created.status == 200
body = created.body['payload']
assert body['status'] == 'current'
assert body['authoritative'] is True
assert body['model_selection_mode'] == 'auto'
assert body['runtime'] == 'vllm'
assert body['resource_request']['submitted'] is False
assert body['resource_request']['artifact_id'] is None
assert p.inventory.artifacts() == ()
assert p.resources.reservations() == ()
assert p.instances.list() == ()
selection = call('/v1/models/selection').body['payload']
assert selection['plan_authoritative'] is False
recommended = body['selected_model']
assert recommended == selection['recommended']
other = next(item['logical_name'] for item in selection['feasible'] if item['logical_name'] != recommended)
manual = call('/v1/models/selection', Method.POST, mode='manual', model=other)
assert manual.status == 200
assert manual.body['payload']['selected'] == other
assert manual.body['payload']['recommended'] == recommended
stale = call('/v1/deployments/plan').body['payload']
assert stale['status'] == 'stale'
assert stale['selected_model'] == recommended
refreshed = call('/v1/deployments/plan', Method.POST).body['payload']
assert refreshed['status'] == 'current'
assert refreshed['selected_model'] == other
assert refreshed['model_selection_mode'] == 'manual'
assert refreshed['plan_basis'] != stale['plan_basis'] or refreshed['generation'] != stale.get('generation')
print(json.dumps({
    'view_status': selection['runtime_eligibility_status'],
    'selected_runtime': body['runtime'],
    'plan_status': refreshed['status'],
    'auto_model': recommended,
    'manual_model': other,
    'recommendation_preserved': manual.body['payload']['recommended'] == recommended,
    'plan_authoritative_selection': selection['plan_authoritative'],
    'plan_id': refreshed['plan_id'],
    'plan_basis': refreshed['plan_basis'],
    'fingerprint': refreshed['plan_basis'],
    'artifacts': len(p.inventory.artifacts()),
    'reservations': len(p.resources.reservations()),
    'instances': len(p.instances.list()),
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

        listed = run([str(kultrun), "deployments", "plan"], env)
        if listed.returncode != 0:
            print(listed.stderr or listed.stdout)
            return 1
        evidence["cli_plan"] = listed.stdout.strip()
        if "CURRENT" not in listed.stdout:
            print("FAIL: CLI plan", listed.stdout)
            return 1

        restart = run(
            [
                str(python),
                "-c",
                r"""
import json
from kultrun.api.contracts import ApiRequest, Method
from kultrun.main import build, resolve_configuration

p = build(resolve_configuration())
body = p.router.handle(ApiRequest(method=Method.GET, path='/v1/deployments/plan', query={})).body['payload']
print(json.dumps({'restart_status': body['status'], 'restart_model': body['selected_model'], 'restart_plan_id': body['plan_id']}))
""",
            ],
            env,
        )
        if restart.returncode != 0:
            print(restart.stderr or restart.stdout)
            return 1
        evidence.update(json.loads(restart.stdout.strip().splitlines()[-1]))

        invalid = run(
            [
                str(python),
                "-c",
                r"""
import json
from dataclasses import replace
from kultrun.main import build, resolve_configuration
from kultrun.platform.eligibility import catalog_facts
from kultrun.platform.requirement import assess_catalog
from kultrun.runtime.contracts import EligibleViewStatus, RuntimePolicy

p = build(resolve_configuration())
host = p.hosts.current
executors = (p.executions.capabilities(host), p.plane.container_capability(host))
descriptors = p.runtimes.descriptors()
envelope = p.capacity.compute(host, {})
view = p.eligibility.evaluate(host, executors, descriptors, catalog_facts(p.models), RuntimePolicy(), components={'vllm': 'missing'})
rows = assess_catalog(view, p.models, envelope, p.selection.estimator, p.selection.policy)
selection = p.model_selection.view(host, view, envelope, rows)
foundation = p.foundation.stored(host)
current = p.deployment_plan.view(host, view, envelope, rows, selection, foundation)
assert current.status.value == 'current'
accelerator = replace(host.accelerators[0], driver_version='changed-driver')
shifted = replace(host, accelerators=(accelerator, *host.accelerators[1:]))
stale_view = p.eligibility.evaluate(shifted, executors, descriptors, catalog_facts(p.models), RuntimePolicy(), components={'vllm': 'missing'})
assert stale_view.status is EligibleViewStatus.STALE
stale_rows = assess_catalog(stale_view, p.models, envelope, p.selection.estimator, p.selection.policy)
stale_selection = p.model_selection.view(host, stale_view, envelope, stale_rows)
later = p.deployment_plan.view(host, stale_view, envelope, stale_rows, stale_selection, foundation)
assert later.status.value == 'stale'
refreshed = p.deployment_plan.refresh(host, stale_view, envelope, stale_rows, stale_selection, foundation)
assert refreshed.status.value != 'current'
print(json.dumps({'invalidation': later.status.value, 'refresh_while_stale': refreshed.status.value}))
""",
            ],
            env,
        )
        if invalid.returncode != 0:
            print(invalid.stderr or invalid.stdout)
            return 1
        evidence.update(json.loads(invalid.stdout.strip().splitlines()[-1]))

        inspect_console = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "js=read('app.js').decode();"
                "html=read('index.html').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Refresh plan' in js,"
                " '/deployments/plan' in js,"
                " 'Deployment plan' in html,"
                " 'Select Model' not in js)",
            ],
            env,
        )
        evidence["console"] = inspect_console.stdout.strip()
        evidence["source_checkout"] = False
        evidence["editable"] = False
        print(json.dumps(evidence, indent=2))
        if evidence.get("plan_status") != "current":
            print("FAIL: plan status", evidence)
            return 1
        if not evidence.get("recommendation_preserved"):
            print("FAIL: recommendation overwritten", evidence)
            return 1
        if evidence.get("restart_status") != "current":
            print("FAIL: restart", evidence)
            return 1
        if evidence.get("invalidation") != "stale":
            print("FAIL: invalidation", evidence)
            return 1
        if evidence.get("artifacts") != 0:
            print("FAIL: artifacts created", evidence)
            return 1
        if evidence.get("reservations") != 0:
            print("FAIL: reservations created", evidence)
            return 1
        if evidence.get("instances") != 0:
            print("FAIL: instances created", evidence)
            return 1
        if "True True True True True" not in inspect_console.stdout:
            print("FAIL: console", inspect_console.stdout)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
