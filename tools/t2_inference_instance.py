"""Stage 1.5B T2: clean wheel, two artifacts, instances, mobility.

Run from a committed tree after `tools/build_prototype.py`.
Installs the wheel into an isolated venv with no source checkout on path.
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
TINY = "tinyllama-1.1b-chat-q4"
FOURTEEN = "qwen2.5-14b-instruct-q4"
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
    evidence: dict[str, object] = {
        "wheel": wheel.name,
        "fixed_stored_active_partition": False,
        "real_llm": False,
        "prompt_inference": False,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-15b-") as workspace:
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
        env["PYTHONNOUSERSITE"] = "1"
        env.pop("PYTHONPATH", None)

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

        for name in (TINY, FOURTEEN):
            acquired = run(
                [str(kultrun), "models", "acquire", "--store-only", name], env
            )
            if acquired.returncode != 0:
                print(acquired.stderr or acquired.stdout)
                return 1

        empty = run([str(kultrun), "instances"], env)
        if "instances 0" not in empty.stdout:
            print("FAIL: expected zero instances", empty.stdout)
            return 1

        script = r"""
import json, urllib.request
from kultrun.api.contracts import ApiRequest, Method
from kultrun.inference.contracts import ObservedState
from kultrun.kernel.errors import ConflictError, PreconditionFailedError
from kultrun.main import build, resolve_configuration
from kultrun.resource.contracts import LedgerHealth, ReservationState

from kultrun.runtime.contracts import RuntimePolicy
p = build(resolve_configuration())
arts = {str(a.logical_name): a for a in p.inventory.artifacts()}
tiny, large = arts['tinyllama-1.1b-chat-q4'], arts['qwen2.5-14b-instruct-q4']
assert tiny.state.value == 'stored' and large.state.value == 'stored'
assert len(p.instances.list()) == 0

host = p.hosts.current
envl = p.capacity.compute(host, {})
profile = p.runtime_setup.provision_and_verify(
    host, RuntimePolicy(allow_fixture_runtime=True, requested_runtime='fixture-vllm')
)
assert profile.status.value == 'verified'
result = p.deployment.recommend(host, {})
plan = result['plan']
assert plan is not None
p.deployment.acquire_normal(str(plan.plan_id), host, {})
d1 = p.admission.reserve(str(plan.plan_id), host, {})
d2 = p.admission.reserve(str(plan.plan_id), host, {})
assert d1.reservation and d2.reservation
planned = p.deployment.artifact_for_plan(plan)
assert planned is not None
a = p.instances.create(planned, d1.reservation)
b = p.instances.create(planned, d2.reservation)
del tiny, large
health = p.resources.summary(envl).health
ra = p.instances.start(a.instance_id, ledger_health=health)
assert ra.observed_state is ObservedState.RUNNING
url = f"{ra.endpoint.scheme}://{ra.endpoint.address}:{ra.endpoint.port}/health"
body = json.loads(urllib.request.urlopen(url, timeout=2).read().decode())
assert body['ready'] is True
rb = p.instances.start(b.instance_id, ledger_health=p.resources.summary(envl).health)
assert rb.observed_state is ObservedState.RUNNING
assert ra.pid != rb.pid
assert ra.endpoint.port != rb.endpoint.port
try:
    p.admission.release(d2.reservation.reservation_id)
    raise SystemExit('release while running was allowed')
except ConflictError as err:
    assert err.context.get('reason') == 'reservation_in_use'
p.instances.stop(a.instance_id)
assert p.instances.observe(b.instance_id).observed_state is ObservedState.RUNNING
p.instances.stop(b.instance_id)
p.admission.release(d2.reservation.reservation_id)
rc = p.instances.start(a.instance_id, ledger_health=p.resources.summary(envl).health)
assert rc.observed_state is ObservedState.RUNNING
p.instances.stop(a.instance_id)
p.admission.release(d1.reservation.reservation_id)

# Synthetic 24 / 4 / 20 mobility against the same ResourceManager types.
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.execution.native_process import NativeProcessExecutor
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
import datetime as dt
from pathlib import Path
import tempfile

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
si = svc.create(small_a, sr)
svc.start(si.instance_id, ledger_health=res.summary(envelope).health)
s1 = res.summary(envelope)
svc.stop(si.instance_id)
res.release(sr.reservation_id)
s2 = res.summary(envelope)
lr = res.admit(req(large_a, LARGE), envelope, large_a).reservation
li = svc.create(large_a, lr)
svc.start(li.instance_id, ledger_health=res.summary(envelope).health)
s3 = res.summary(envelope)
svc.stop(li.instance_id)
res.release(lr.reservation_id)
sr2 = res.admit(req(small_a, SMALL), envelope, small_a).reservation
si2 = svc.create(small_a, sr2)
svc.start(si2.instance_id, ledger_health=res.summary(envelope).health)
s4 = res.summary(envelope)
svc.stop(si2.instance_id)
res.release(sr2.reservation_id)

api = p.router.handle(ApiRequest(Method.GET, '/v1/inference/instances'))
chat = p.router.handle(ApiRequest(Method.GET, '/v1/chat/completions'))
print(json.dumps({
    'first_instance': ra.instance_id.value,
    'first_pid': ra.pid,
    'first_endpoint': f'{ra.endpoint.address}:{ra.endpoint.port}',
    'readiness': body['ready'],
    'second_instance': rb.instance_id.value,
    'second_pid': rb.pid,
    'second_endpoint': f'{rb.endpoint.address}:{rb.endpoint.port}',
    'two_concurrent': True,
    'independent_stop': True,
    'running_release_blocked': True,
    'restart_stopped': rc.observed_state.value,
    'small_reserved': s1.accelerators[0].reserved_bytes,
    'small_available': s1.accelerators[0].available_bytes,
    'after_small_release_reserved': s2.accelerators[0].reserved_bytes,
    'after_small_release_available': s2.accelerators[0].available_bytes,
    'large_reserved': s3.accelerators[0].reserved_bytes,
    'large_available': s3.accelerators[0].available_bytes,
    'small_again_reserved': s4.accelerators[0].reserved_bytes,
    'small_again_available': s4.accelerators[0].available_bytes,
    'safe': SAFE,
    'api_status': api.status,
    'chat_status': chat.status,
    'runtime': ra.runtime.value,
    'executor': ra.executor.value,
}))
"""
        proof = run([str(python), "-c", script], env)
        if proof.returncode != 0:
            print(proof.stderr or proof.stdout)
            return 1
        try:
            payload = json.loads(proof.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError:
            print("FAIL: proof output", proof.stdout)
            return 1
        evidence.update(payload)
        cli = run([str(kultrun), "instances"], env)
        evidence["cli"] = cli.stdout.strip()
        console = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Inference instances' in html,"
                " '/inference/instances' in js,"
                " 'Active Pool' not in js)",
            ],
            env,
        )
        evidence["console"] = console.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if payload.get("small_reserved") != 4 * GIB:
            print("FAIL: small reserved", payload)
            return 1
        if payload.get("large_reserved") != 20 * GIB:
            print("FAIL: large reserved", payload)
            return 1
        if payload.get("chat_status") != 404:
            print("FAIL: prompt route exists")
            return 1
        if "True True True True" not in console.stdout:
            print("FAIL: Console", console.stdout)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
