"""Stage 1.6G T2: clean wheel proves requirement and capacity migration.

Installs the committed wheel into an isolated venv with no source checkout.
Proves selected foundation → VERIFIED profile → EligibleModelView CURRENT
→ ModelRequirement → CapacityAssessment for feasible, infeasible, unresolved
and blocked models, then foundation/profile invalidation.
Does not install or import real vLLM. Does not redesign ModelSelector.
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
        "model_selector_redesign": False,
        "deployment_plan_authoritative": False,
        "fixture_provisioner": True,
        "fixture_verifier": True,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16g-") as workspace:
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
empty = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/requirements'))
assert empty.status == 200
payload = empty.body['payload']
assert payload['mutations'] is False
assert payload['acquire'] is False
assert payload['admit'] is False
assert payload['view_status'] == 'unavailable'
p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/select', query={'mode': 'auto'}))
assert p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/realize')).status == 200
verified = p.router.handle(ApiRequest(method=Method.POST, path='/v1/runtimes/foundation/verify'))
assert verified.status == 200
eligible = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/eligible'))
assert eligible.body['payload']['status'] == 'current'
req = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/requirements'))
assert req.status == 200
body = req.body['payload']
assert body['view_status'] == 'current'
assert body['selected_runtime'] == 'vllm'
rows = {item['logical_name']: item for item in body['assessments']}
small, large, blocked, unresolved = rows['qwen2.5-0.5b-instruct-awq'], rows['qwen2.5-72b-instruct-awq'], rows['tinyllama-1.1b-chat-q4'], rows['kultrun-hf-acceptance-tiny']
assert small['requirement_status'] == 'ready' and small['capacity_verdict'] == 'feasible'
assert small['eligibility_status'] == 'eligible'
assert large['requirement_status'] == 'ready' and str(large['capacity_verdict']).startswith('infeasible')
assert large['eligibility_status'] == 'eligible'
assert blocked['requirement_status'] == 'refused' and blocked['capacity_verdict'] == 'not_assessed'
assert unresolved['requirement_status'] == 'unresolved' and unresolved['capacity_verdict'] != 'feasible'
assert small['assumed_runtime'] == 'vllm'
assert small['basis']
selection = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/selection'))
assert selection.body['payload']['selected_runtime'] == 'vllm'
print(json.dumps({
    'view_status': body['view_status'],
    'selected_runtime': body['selected_runtime'],
    'small_status': small['requirement_status'],
    'small_capacity': small['capacity_verdict'],
    'large_capacity': large['capacity_verdict'],
    'blocked_status': blocked['requirement_status'],
    'unresolved_status': unresolved['requirement_status'],
    'k94_blocked_feasible': blocked['capacity_verdict'] == 'feasible',
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

        listed = run([str(kultrun), "models", "requirements"], env)
        if listed.returncode != 0:
            print(listed.stderr or listed.stdout)
            return 1
        evidence["cli_requirements"] = listed.stdout.strip()
        if "runtime vllm" not in listed.stdout:
            print("FAIL: CLI requirements", listed.stdout)
            return 1
        if "ready" not in listed.stdout or "refused" not in listed.stdout:
            print("FAIL: CLI missing statuses", listed.stdout)
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
req = p.router.handle(ApiRequest(method=Method.GET, path='/v1/models/requirements'))
body = req.body['payload']
assert body['view_status'] == 'current'
assert body['selected_runtime'] == 'vllm'
print(json.dumps({'restart_status': body['view_status']}))
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
                r"""
import json
from dataclasses import replace
from kultrun.main import build, resolve_configuration
from kultrun.platform.eligibility import catalog_facts
from kultrun.platform.requirement import RequirementStatus, assess_catalog
from kultrun.runtime.contracts import EligibleViewStatus, RuntimePolicy

p = build(resolve_configuration())
host = p.hosts.current
executors = (p.executions.capabilities(host), p.plane.container_capability(host))
descriptors = p.runtimes.descriptors()
envelope = p.capacity.compute(host, {})
current = p.eligibility.evaluate(
    host, executors, descriptors, catalog_facts(p.models), RuntimePolicy(),
    components={'vllm': 'missing'},
)
assert current.status is EligibleViewStatus.CURRENT
first = assess_catalog(current, p.models, envelope, p.selection.estimator, p.selection.policy)
ready = next(item for item in first if item.logical_name == 'qwen2.5-0.5b-instruct-awq')
assert ready.requirement_status is RequirementStatus.READY
accelerator = replace(host.accelerators[0], driver_version='changed-driver')
shifted = replace(host, accelerators=(accelerator, *host.accelerators[1:]))
stale = p.eligibility.evaluate(
    shifted, executors, descriptors, catalog_facts(p.models), RuntimePolicy(),
    components={'vllm': 'missing'},
)
assert stale.status is EligibleViewStatus.STALE
second = assess_catalog(stale, p.models, envelope, p.selection.estimator, p.selection.policy)
later = next(item for item in second if item.logical_name == 'qwen2.5-0.5b-instruct-awq')
assert later.requirement_status is RequirementStatus.STALE
assert later.capacity_verdict == 'not_assessed'
print(json.dumps({'invalidation': stale.status.value, 'stale_requirement': later.requirement_status.value}))
""",
            ],
            env,
        )
        if invalid.returncode != 0:
            print(invalid.stderr or invalid.stdout)
            return 1
        evidence.update(json.loads(invalid.stdout.strip().splitlines()[-1]))

        k94 = run(
            [
                str(python),
                "-c",
                r"""
import inspect
from kultrun.planning.service import SelectionService
from pathlib import Path
import kultrun.planning.service as service
import kultrun.platform.admission as admission

sig = inspect.signature(SelectionService.recommend)
assert sig.parameters['runtime_compatibility'].default is inspect.Parameter.empty
from kultrun.planning.evaluate import evaluate
assert inspect.signature(evaluate).parameters['runtime_compatibility'].default is inspect.Parameter.empty
text = Path(service.__file__).read_text()
assert 'or CompatibilityVerdict.COMPATIBLE' not in text
assert 'meta.supported_runtimes' not in text
adm = Path(admission.__file__).read_text()
assert 'or CompatibilityVerdict.COMPATIBLE' not in adm
print('k94_removed')
""",
            ],
            env,
        )
        if k94.returncode != 0:
            print(k94.stderr or k94.stdout)
            return 1
        evidence["k94"] = k94.stdout.strip()

        inspect_console = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'selected runtime' in js,"
                " '/models/requirements' in js,"
                " 'Select Model' not in js)",
            ],
            env,
        )
        evidence["console"] = inspect_console.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if payload.get("view_status") != "current":
            print("FAIL: requirements view", payload)
            return 1
        if payload.get("k94_blocked_feasible"):
            print("FAIL: blocked treated as feasible", payload)
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
