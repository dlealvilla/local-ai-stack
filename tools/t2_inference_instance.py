"""Stage 1.6K T2: clean wheel proves plan-driven InferenceInstance create.

Installs the committed wheel into an isolated venv with no source checkout.
Proves CURRENT DeploymentPlan + exact ModelArtifact + matching ACTIVE
ResourceReservation → InferenceInstance CREATED. vLLM START is refused
and does not launch reference-serving. Isolated reference lifecycle
remains intact when that runtime is selected explicitly.
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
GIB = 1024**3


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
        "plan_driven_instance": True,
        "plan_from_authoritative": False,
        "fixture_provisioner": True,
        "fixture_verifier": True,
        "vllm_launched": False,
        "reference_substituted": False,
        "production_endpoint": False,
        "prompt": False,
        "response": False,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16k-") as workspace:
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
from kultrun.inference.contracts import ObservedState
from kultrun.kernel.ids import Name
from kultrun.main import build, resolve_configuration
from kultrun.model.contracts import ArtifactId
from kultrun.resource.contracts import ReservationId

p = build(resolve_configuration())
def call(path, method=Method.GET, **query):
    return p.router.handle(ApiRequest(method=method, path=path, query=query))
assert call('/v1/runtimes/foundation/select', Method.POST, mode='auto').status == 200
assert call('/v1/runtimes/foundation/realize', Method.POST).status == 200
assert call('/v1/runtimes/foundation/verify', Method.POST).status == 200
created = call('/v1/deployments/plan', Method.POST)
assert created.status == 200
plan = created.body['payload']
assert plan['status'] == 'current'
prepared = call('/v1/deployments/plan/prepare', Method.POST)
assert prepared.status == 200
prep = prepared.body['payload']
assert prep['plan_status'] == 'current'
assert prep['admission']['verdict'] == 'admitted'
assert prep['launch'] is False
reservation_id = prep['admission']['reservation_id']
instance = call('/v1/inference/instances', Method.POST, reservation_id=reservation_id)
assert instance.status == 200
body = instance.body['payload']
assert body['observed_state'] == 'created'
assert body['plan_id'] == plan['plan_id']
assert body['plan_basis'] == plan['plan_basis']
assert body['configuration_current'] is True
assert body['model_id'] == plan['model_id']
assert body['logical_name'] == plan['selected_model']
assert body['artifact_id'] == prep['artifact_id']
assert body['reservation_id'] == reservation_id
assert body['runtime'] == plan['runtime'] == 'vllm'
assert body['executor'] == plan['executor']
assert body['placement'] == plan['settings']['placement']
started = call('/v1/inference/instances/start', Method.POST, instance_id=body['instance_id'])
assert started.status == 412
assert started.body['error']['context']['reason'] == 'runtime_launch_unsupported'
from kultrun.inference.contracts import InstanceId
stored = p.instances.get(InstanceId.parse(body['instance_id']))
assert stored is not None
assert stored.observed_state is ObservedState.CREATED
assert stored.endpoint is None
vllm_executions = len(p.executions.list())
assert vllm_executions == 0

selection = call('/v1/models/selection').body['payload']
other = next(item['logical_name'] for item in selection['feasible'] if item['logical_name'] != plan['selected_model'])
assert call('/v1/models/selection', Method.POST, mode='manual', model=other).status == 200
manual_plan = call('/v1/deployments/plan', Method.POST).body['payload']
assert manual_plan['selected_model'] == other
manual_prep = call('/v1/deployments/plan/prepare', Method.POST)
assert manual_prep.status == 200
manual_body = call('/v1/inference/instances', Method.POST, reservation_id=manual_prep.body['payload']['admission']['reservation_id']).body['payload']
assert manual_body['logical_name'] == other
assert manual_body['model_id'] == manual_plan['model_id']
assert manual_body['artifact_id'] == manual_prep.body['payload']['artifact_id']
assert plan['selected_model'] not in {manual_body['logical_name']}

stale_start = call('/v1/inference/instances/start', Method.POST, instance_id=body['instance_id'])
assert stale_start.status == 412
assert stale_start.body['error']['context']['reason'] == 'plan_stale'
assert p.instances.get(InstanceId.parse(body['instance_id'])).observed_state is ObservedState.CREATED
assert p.executions.list() == ()

# Isolated reference lifecycle: explicit harness runtime, not a vLLM substitute.
artifact = p.inventory.get(ArtifactId.parse(manual_prep.body['payload']['artifact_id']))
reservation = p.resources.get(ReservationId.parse(manual_prep.body['payload']['admission']['reservation_id']))
ref = p.instances.create(artifact, reservation, runtime=Name('reference-serving'), executor=Name('native-process'))
host = p.hosts.current
envelope = p.capacity.compute(host, {})
running = p.instances.start(ref.instance_id, ledger_health=p.resources.summary(envelope).health)
assert running.observed_state is ObservedState.RUNNING
assert running.runtime.value == 'reference-serving'
p.instances.stop(ref.instance_id)
chat = p.router.handle(ApiRequest(Method.GET, '/v1/chat/completions'))
print(json.dumps({
    'plan_status': plan['status'],
    'instance_id': body['instance_id'],
    'plan_id': body['plan_id'],
    'plan_basis': body['plan_basis'],
    'model': body['logical_name'],
    'runtime': body['runtime'],
    'executor': body['executor'],
    'artifact_id': body['artifact_id'],
    'reservation_id': reservation_id,
    'manual_reservation_id': manual_prep.body['payload']['admission']['reservation_id'],
    'manual_model': manual_body['logical_name'],
    'vllm_start_reason': started.body['error']['context']['reason'],
    'stale_before_start': stale_start.body['error']['context']['reason'],
    'vllm_running': stored.observed_state.value,
    'vllm_executions': vllm_executions,
    'reference_runtime': running.runtime.value,
    'reference_stopped': p.instances.observe(ref.instance_id).observed_state.value,
    'chat_status': chat.status,
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

        stale_cli = run(
            [str(kultrun), "instances", "create", str(payload["reservation_id"])],
            env,
        )
        evidence["cli_stale_create"] = stale_cli.returncode
        if stale_cli.returncode == 0:
            print("FAIL: CLI created from stale reservation", stale_cli.stdout)
            return 1
        created = run(
            [
                str(kultrun),
                "instances",
                "create",
                str(payload["manual_reservation_id"]),
            ],
            env,
        )
        if created.returncode != 0:
            print(created.stderr or created.stdout)
            return 1
        evidence["cli_create"] = created.stdout.strip()
        if "Configuration: CURRENT" not in created.stdout:
            print("FAIL: CLI create", created.stdout)
            return 1
        listing = run([str(kultrun), "instances"], env)
        evidence["cli"] = listing.stdout.strip()
        inspect = run(
            [str(kultrun), "instances", "inspect", str(payload["instance_id"])], env
        )
        evidence["cli_inspect"] = inspect.stdout.strip()
        if "plan " not in inspect.stdout:
            print("FAIL: CLI inspect", inspect.stdout)
            return 1

        mobility = run(
            [
                str(python),
                "-c",
                r"""
import datetime as dt
import json
import tempfile
from pathlib import Path
from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.capacity.contracts import AcceleratorCapacity, CapacityEnvelope, EvidenceRequirement, PoolCapacity
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import HostId
from kultrun.inference.service import InstanceService
from kultrun.kernel.clock import FixedClock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.model.contracts import ArtifactId, ArtifactState, MemoryPlacement, ModelArtifact, ModelId
from kultrun.model.inventory import ModelInventory
from kultrun.model.store import ModelArtifactStore
from kultrun.resource.contracts import RequestId, ResourceRequest, WorkloadType
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.catalogue import RuntimeCatalogue

GIB = 1024 ** 3
SAFE, SMALL, LARGE = 24 * GIB, 4 * GIB, 20 * GIB
INSTANT = dt.datetime(2026, 9, 7, 21, 0, tzinfo=dt.UTC)
tmp = Path(tempfile.mkdtemp())
store = FileStore(tmp / 'records')
clock = FixedClock(INSTANT)
arts = ModelArtifactStore(tmp / 'models')
inv = ModelInventory(store, arts)
res = ResourceManager(store, clock, AdmissionLock(tmp / 'locks'))
exe = ExecutionService(NativeProcessExecutor(SystemClock()), store)
svc = InstanceService(store, clock, inv, res, exe, RuntimeCatalogue((ReferenceServingRuntime(),)))
host_id = HostId.generate()

def layered(n):
    return LayeredBytes(n*2, n, n, Confidence.HIGH, Provenance(Name('t'), 't', INSTANT, 't'))

envelope = CapacityEnvelope(
    host_id=host_id, host_fingerprint='t', computed_at=INSTANT, policy_version='t',
    memory=layered(48*GIB), memory_requirement=EvidenceRequirement.SUFFICIENT,
    accelerators=(AcceleratorCapacity(0, layered(SAFE), EvidenceRequirement.SUFFICIENT),),
    pools=(PoolCapacity('/data', layered(10**11), EvidenceRequirement.SUFFICIENT, 'ext4'),),
)

def stored(name, size):
    art = ModelArtifact(ArtifactId.generate(), ModelId.generate(), 'rev', state=ArtifactState.STORED,
                        logical_name=name, installed_bytes=size)
    path = arts.manifest_path(art.artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}')
    inv.put(art, host_id)
    return inv.get(art.artifact_id)

def req(art, vram):
    return ResourceRequest(
        RequestId.generate(), host_id, art.artifact_id, art.model_id, 'plan',
        MemoryPlacement.DISCRETE_GPU, 2*GIB, vram, NOT_PROVIDED, logical_name=art.logical_name,
        accelerator_index=0, incremental_storage_bytes=NOT_PROVIDED,
        workload_type=WorkloadType.INFERENCE,
    )

small_a, large_a = stored('small', 4*GIB), stored('large', 20*GIB)
sr = res.admit(req(small_a, SMALL), envelope, small_a).reservation
si = svc.create(small_a, sr, runtime=Name('reference-serving'))
svc.start(si.instance_id, ledger_health=res.summary(envelope).health)
s1 = res.summary(envelope)
svc.stop(si.instance_id)
res.release(sr.reservation_id)
lr = res.admit(req(large_a, LARGE), envelope, large_a).reservation
li = svc.create(large_a, lr, runtime=Name('reference-serving'))
svc.start(li.instance_id, ledger_health=res.summary(envelope).health)
s3 = res.summary(envelope)
svc.stop(li.instance_id)
res.release(lr.reservation_id)
print(json.dumps({
    'small_reserved': s1.accelerators[0].reserved_bytes,
    'large_reserved': s3.accelerators[0].reserved_bytes,
    'safe': SAFE,
}))
""",
            ],
            env,
        )
        if mobility.returncode != 0:
            print(mobility.stderr or mobility.stdout)
            return 1
        evidence.update(json.loads(mobility.stdout.strip().splitlines()[-1]))

        console = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Inference instances' in html,"
                " '/inference/instances' in js,"
                " 'configuration' in js,"
                " 'chat' not in js,"
                " 'Active Pool' not in js)",
            ],
            env,
        )
        evidence["console"] = console.stdout.strip()
        evidence["source_checkout"] = False
        evidence["editable"] = False
        print(json.dumps(evidence, indent=2))
        if evidence.get("runtime") != "vllm":
            print("FAIL: runtime", evidence)
            return 1
        if evidence.get("vllm_start_reason") != "runtime_launch_unsupported":
            print("FAIL: vLLM start", evidence)
            return 1
        if evidence.get("stale_before_start") != "plan_stale":
            print("FAIL: stale start", evidence)
            return 1
        if evidence.get("vllm_running") != "created":
            print("FAIL: vLLM running", evidence)
            return 1
        if evidence.get("vllm_executions") != 0:
            print("FAIL: vLLM executions", evidence)
            return 1
        if evidence.get("reference_runtime") != "reference-serving":
            print("FAIL: reference", evidence)
            return 1
        if evidence.get("chat_status") != 404:
            print("FAIL: prompt route exists")
            return 1
        if evidence.get("small_reserved") != 4 * GIB:
            print("FAIL: small reserved", evidence)
            return 1
        if evidence.get("large_reserved") != 20 * GIB:
            print("FAIL: large reserved", evidence)
            return 1
        if "True True True True True True" not in console.stdout:
            print("FAIL: Console", console.stdout)
            return 1
        if evidence.get("manual_model") == evidence.get("model"):
            print("FAIL: manual model", evidence)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
