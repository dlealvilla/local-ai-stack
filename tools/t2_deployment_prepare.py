"""Stage 1.6J T2: clean wheel proves plan-driven acquire and admit.

Installs the committed wheel into an isolated venv with no source checkout.
Proves CURRENT DeploymentPlan → exact artifact acquire/reuse →
plan-derived ResourceRequest → ResourceManager → ResourceReservation.
STORE_ONLY stays independent. No InferenceInstance. No launch.
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
        "plan_driven_prepare": True,
        "plan_from_authoritative": False,
        "fixture_provisioner": True,
        "fixture_verifier": True,
        "launch": False,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16j-") as workspace:
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
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import build, resolve_configuration
from kultrun.model.contracts import ArtifactId, MemoryPlacement
from kultrun.resource.contracts import RequestId, ResourceRequest, WorkloadType

p = build(resolve_configuration())
def call(path, method=Method.GET, **query):
    return p.router.handle(ApiRequest(method=method, path=path, query=query))
assert call('/v1/runtimes/foundation/select', Method.POST, mode='auto').status == 200
assert call('/v1/runtimes/foundation/realize', Method.POST).status == 200
assert call('/v1/runtimes/foundation/verify', Method.POST).status == 200
created = call('/v1/deployments/plan', Method.POST)
assert created.status == 200
body = created.body['payload']
assert body['status'] == 'current'
assert body['resource_request']['submitted'] is False
assert body['resource_request']['artifact_id'] is None
selected = body['selected_model']
spec = body['resource_request']
first = call('/v1/deployments/plan/acquire', Method.POST)
assert first.status == 200
acq = first.body['payload']
assert acq['plan_status'] == 'current'
assert acq['selected_model'] == selected
assert acq['acquisition']['reused'] is False
assert acq['admit'] is False
assert p.resources.reservations() == ()
assert p.instances.list() == ()
artifact_id = acq['artifact_id']
second = call('/v1/deployments/plan/acquire', Method.POST)
assert second.status == 200
assert second.body['payload']['acquisition']['reused'] is True
assert second.body['payload']['artifact_id'] == artifact_id
prepared = call('/v1/deployments/plan/prepare', Method.POST)
assert prepared.status == 200
prep = prepared.body['payload']
assert prep['acquisition']['reused'] is True
assert prep['admission']['verdict'] == 'admitted'
assert prep['request']['ram_bytes'] == spec['ram_bytes']
assert prep['request']['accelerator_bytes'] == spec['accelerator_bytes']
assert prep['request']['artifact_id'] == artifact_id
assert prep['request']['plan_fingerprint'] == body['plan_basis']
assert prep['launch'] is False
assert prep['instance'] is False
assert len(p.instances.list()) == 0
reservation_id = prep['admission']['reservation_id']
call('/v1/resources/reservations', Method.DELETE, reservation_id=reservation_id)
selection = call('/v1/models/selection').body['payload']
assert selection['plan_authoritative'] is False
other = next(item['logical_name'] for item in selection['feasible'] if item['logical_name'] != selected)
stored = call('/v1/models/acquire', Method.POST, candidate=other)
assert stored.status == 200
after_store = call('/v1/deployments/plan').body['payload']
assert after_store['status'] == 'current'
assert after_store['selected_model'] == selected
other_id = stored.body['payload']['artifact_id']
mismatch = call('/v1/deployments/plan/admit', Method.POST, artifact_id=other_id)
assert mismatch.status == 412
assert mismatch.body['error']['context']['reason'] == 'artifact_plan_mismatch'
artifact = p.inventory.get(ArtifactId.parse(other_id))
assert artifact is not None
host = p.hosts.current
envelope = p.capacity.compute(host, {})
available = p.resources.summary(envelope).accelerators[0].available_bytes
assert isinstance(available, int) and available > 0
competing = ResourceRequest(
    request_id=RequestId.generate(),
    host_id=envelope.host_id,
    artifact_id=artifact.artifact_id,
    model_id=artifact.model_id,
    plan_fingerprint='contention',
    placement=MemoryPlacement.DISCRETE_GPU,
    ram_bytes=1024**3,
    accelerator_bytes=available,
    unified_bytes=NOT_PROVIDED,
    accelerator_index=0,
    incremental_storage_bytes=NOT_PROVIDED,
    workload_type=WorkloadType.INFERENCE,
)
assert p.resources.admit(competing, envelope, artifact).verdict.value == 'admitted'
refused = call('/v1/deployments/plan/admit', Method.POST)
assert refused.status == 200
assert refused.body['payload']['admission']['verdict'] == 'rejected'
assert refused.body['payload']['reservation'] is None
assert call('/v1/deployments/plan').body['payload']['selected_model'] == selected
assert len(p.instances.list()) == 0
print(json.dumps({
    'plan_status': body['status'],
    'selected_model': selected,
    'artifact_id': artifact_id,
    'first_reused': acq['acquisition']['reused'],
    'second_reused': second.body['payload']['acquisition']['reused'],
    'request_from_plan': prep['request']['ram_bytes'] == spec['ram_bytes'],
    'admitted': prep['admission']['verdict'],
    'reservation_id': reservation_id,
    'store_only_model': other,
    'store_only_plan_unchanged': after_store['selected_model'] == selected,
    'mismatch_reason': mismatch.body['error']['context']['reason'],
    'refused_verdict': refused.body['payload']['admission']['verdict'],
    'instances': len(p.instances.list()),
    'plan_authoritative_selection': selection['plan_authoritative'],
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

        listed = run([str(kultrun), "deployments", "acquire"], env)
        if listed.returncode != 0:
            print(listed.stderr or listed.stdout)
            return 1
        evidence["cli_acquire"] = listed.stdout.strip()
        if "Plan: CURRENT" not in listed.stdout:
            print("FAIL: CLI acquire", listed.stdout)
            return 1

        stale = run(
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
plan = call('/v1/deployments/plan').body['payload']
assert plan['status'] == 'current'
acquired = call('/v1/deployments/plan/acquire', Method.POST)
assert acquired.status == 200
artifact_id = acquired.body['payload']['artifact_id']
selection = call('/v1/models/selection').body['payload']
other = next(item['logical_name'] for item in selection['feasible'] if item['logical_name'] != plan['selected_model'])
call('/v1/models/selection', Method.POST, mode='manual', model=other)
refused = call('/v1/deployments/plan/admit', Method.POST)
assert refused.status == 412
assert refused.body['error']['context']['reason'] == 'plan_stale'
from kultrun.model.contracts import ArtifactId
assert p.inventory.get(ArtifactId.parse(artifact_id)) is not None
print(json.dumps({'stale_admit': refused.body['error']['context']['reason'], 'stale_artifact_kept': True}))
""",
            ],
            env,
        )
        if stale.returncode != 0:
            print(stale.stderr or stale.stdout)
            return 1
        evidence.update(json.loads(stale.stdout.strip().splitlines()[-1]))

        inspect_console = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "js=read('app.js').decode();"
                "html=read('index.html').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Prepare deployment' in js,"
                " '/deployments/plan/prepare' in js,"
                " 'Start Model' not in js,"
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
        if evidence.get("second_reused") is not True:
            print("FAIL: reuse", evidence)
            return 1
        if evidence.get("request_from_plan") is not True:
            print("FAIL: request source", evidence)
            return 1
        if evidence.get("admitted") != "admitted":
            print("FAIL: admitted", evidence)
            return 1
        if evidence.get("store_only_plan_unchanged") is not True:
            print("FAIL: STORE_ONLY", evidence)
            return 1
        if evidence.get("refused_verdict") != "rejected":
            print("FAIL: refusal", evidence)
            return 1
        if evidence.get("stale_admit") != "plan_stale":
            print("FAIL: stale", evidence)
            return 1
        if evidence.get("instances") != 0:
            print("FAIL: instances", evidence)
            return 1
        if "True True True True True" not in inspect_console.stdout:
            print("FAIL: console", inspect_console.stdout)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
