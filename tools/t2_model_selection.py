"""Stage 1.6H T2: clean wheel proves bounded model selection.

Installs the committed wheel into an isolated venv with no source checkout.
Proves feasible set → recommendation → AUTO/MANUAL ModelSelection, refusals,
return-to-AUTO, and invalidation. Does not create DeploymentPlan authority.
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
        "deployment_plan_authoritative": False,
        "selected_deployment_candidate": False,
        "fixture_provisioner": True,
        "fixture_verifier": True,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16h-") as workspace:
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
p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/select', query={'mode': 'auto'}))
assert call('/v1/runtimes/foundation/realize', Method.POST).status == 200
assert call('/v1/runtimes/foundation/verify', Method.POST).status == 200
req = call('/v1/models/selection')
assert req.status == 200
body = req.body['payload']
assert body['status'] == 'current'
assert body['selection_mode'] == 'auto'
assert body['plan_authoritative'] is False
assert body['selected_runtime'] == 'vllm'
feasible = [item['logical_name'] for item in body['feasible']]
assert 'qwen2.5-0.5b-instruct-awq' in feasible
assert 'qwen2.5-7b-instruct-awq' in feasible
assert 'qwen2.5-72b-instruct-awq' not in feasible
assert 'tinyllama-1.1b-chat-q4' not in feasible
assert body['recommended'] in feasible
assert body['selected'] == body['recommended']
other = next(name for name in feasible if name != body['recommended'])
manual = call('/v1/models/selection', Method.POST, mode='manual', model=other)
assert manual.status == 200
chosen = manual.body['payload']
assert chosen['selection_mode'] == 'manual'
assert chosen['selected'] == other
assert chosen['recommended'] == body['recommended']
blocked = call('/v1/models/selection', Method.POST, mode='manual', model='tinyllama-1.1b-chat-q4')
assert blocked.status == 412
assert blocked.body['error']['context']['reason'] == 'model_not_eligible'
infeasible = call('/v1/models/selection', Method.POST, mode='manual', model='qwen2.5-72b-instruct-awq')
assert infeasible.status == 412
unresolved = call('/v1/models/selection', Method.POST, mode='manual', model='kultrun-hf-acceptance-tiny')
assert unresolved.status == 412
auto = call('/v1/models/selection', Method.POST, mode='auto')
assert auto.status == 200
assert auto.body['payload']['selection_mode'] == 'auto'
assert auto.body['payload']['selected'] == body['recommended']
print(json.dumps({
    'view_status': body['runtime_eligibility_status'],
    'feasible_count': body['feasible_count'],
    'recommended': body['recommended'],
    'auto_selected': body['selected'],
    'manual_selected': other,
    'recommendation_preserved': chosen['recommended'] == body['recommended'],
    'blocked': blocked.body['error']['context']['reason'],
    'infeasible': infeasible.status,
    'unresolved': unresolved.status,
    'return_auto': auto.body['payload']['selected'],
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

        listed = run([str(kultrun), "models", "selection"], env)
        if listed.returncode != 0:
            print(listed.stderr or listed.stdout)
            return 1
        evidence["cli_selection"] = listed.stdout.strip()
        if "mode auto" not in listed.stdout:
            print("FAIL: CLI selection", listed.stdout)
            return 1

        capacity = run(
            [
                str(python),
                "-c",
                r"""
import json
from dataclasses import replace
from kultrun.capacity.envelope import CapacityService
from kultrun.main import build, resolve_configuration
from kultrun.platform.eligibility import catalog_facts
from kultrun.platform.requirement import assess_catalog
from kultrun.runtime.contracts import RuntimePolicy

GIB = 1024 ** 3
p = build(resolve_configuration())
host = p.hosts.current
executors = (p.executions.capabilities(host), p.plane.container_capability(host))
descriptors = p.runtimes.descriptors()
envelope = p.capacity.compute(host, {})
view = p.eligibility.evaluate(host, executors, descriptors, catalog_facts(p.models), RuntimePolicy(), components={'vllm': 'missing'})
rows = assess_catalog(view, p.models, envelope, p.selection.estimator, p.selection.policy)
p.model_selection.select_manual('qwen2.5-7b-instruct-awq', host, view, envelope, rows)
tiny = replace(host.accelerators[0], memory_total_bytes=2 * GIB)
poor = CapacityService().compute(replace(host, accelerators=(tiny,)), {})
later = p.model_selection.view(host, view, poor, assess_catalog(view, p.models, poor, p.selection.estimator, p.selection.policy))
assert later.status.value == 'invalid'
assert later.selection.selection_mode.value == 'manual'
assert later.selection.selected_logical_name == 'qwen2.5-7b-instruct-awq'
assert 'qwen2.5-7b-instruct-awq' not in {item.logical_name for item in later.feasible}
print(json.dumps({'capacity_invalidation': later.status.value, 'capacity_manual_kept': later.selection.selected_logical_name}))
""",
            ],
            env,
        )
        if capacity.returncode != 0:
            print(capacity.stderr or capacity.stdout)
            return 1
        evidence.update(json.loads(capacity.stdout.strip().splitlines()[-1]))

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
overview = p.model_selection.view(host, view, envelope, rows)
other = next(item.logical_name for item in overview.feasible if item.logical_name != overview.selection.recommended_logical_name)
p.model_selection.select_manual(other, host, view, envelope, rows)
accelerator = replace(host.accelerators[0], driver_version='changed-driver')
shifted = replace(host, accelerators=(accelerator, *host.accelerators[1:]))
stale = p.eligibility.evaluate(shifted, executors, descriptors, catalog_facts(p.models), RuntimePolicy(), components={'vllm': 'missing'})
assert stale.status is EligibleViewStatus.STALE
later = p.model_selection.view(host, stale, envelope, assess_catalog(stale, p.models, envelope, p.selection.estimator, p.selection.policy))
assert later.status.value == 'stale'
assert later.selection.selection_mode.value == 'manual'
assert later.selection.selected_logical_name == other
print(json.dumps({'invalidation': later.status.value, 'manual_kept': later.selection.selected_logical_name}))
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
                "print(all(read(n) for n in ASSETS),"
                " 'Use AUTO' in js,"
                " 'Choose' in js,"
                " 'Select Model' not in js)",
            ],
            env,
        )
        evidence["console"] = inspect_console.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if payload.get("feasible_count", 0) < 2:
            print("FAIL: feasible set", payload)
            return 1
        if not payload.get("recommendation_preserved"):
            print("FAIL: recommendation overwritten", payload)
            return 1
        if evidence.get("capacity_invalidation") != "invalid":
            print("FAIL: capacity invalidation", evidence)
            return 1
        if evidence.get("invalidation") != "stale":
            print("FAIL: invalidation", evidence)
            return 1
        if "True True True True" not in inspect_console.stdout:
            print("FAIL: console", inspect_console.stdout)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
