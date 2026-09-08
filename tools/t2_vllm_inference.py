"""Stage 1.6L T2: clean wheel proves native vLLM launch/inference contracts.

Installs the committed wheel into an isolated venv with no source checkout
and no editable install. Runs the full T0/T1/API/CLI/architecture/packaging
suite against that install (pythonpath does not include src/). Product vLLM
START without a real engine fails truthfully and does not launch
reference-serving. Protocol fixtures remain tests, not T5 evidence.
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
        "source_checkout": False,
        "editable": False,
        "reference_substituted": False,
        "chat_frontend": False,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16l-") as workspace:
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
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--quiet",
                str(wheel),
                "pytest>=8",
            ],
            env,
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

        identity = run(
            [
                str(python),
                "-c",
                "from kultrun.kernel.build import identity; "
                "found=identity(); "
                "print(found.origin.value, found.build_id or '', "
                "found.source_commit or '', found.acceptable_as_evidence)",
            ],
            env,
        )
        if identity.returncode != 0:
            print(identity.stderr or identity.stdout)
            return 1
        evidence["identity"] = identity.stdout.strip()
        if not identity.stdout.startswith("artifact "):
            print("FAIL: wheel did not report artifact identity", identity.stdout)
            return 1
        if identity.stdout.strip().split()[-1] != "True":
            print("FAIL: wheel is not acceptable evidence", identity.stdout)
            return 1

        version = run([str(kultrun), "version"], env)
        if version.returncode != 0:
            print(version.stderr or version.stdout)
            return 1
        evidence["version"] = version.stdout.strip()

        suite = run(
            [
                str(python),
                "-m",
                "pytest",
                str(REPOSITORY / "tests"),
                "-q",
                "--tb=line",
                "--override-ini",
                "pythonpath=.",
                "-k",
                "not test_the_live_source_tree_reports_itself_as_source",
            ],
            env,
            cwd=REPOSITORY,
        )
        evidence["pytest_returncode"] = suite.returncode
        evidence["pytest_tail"] = "\n".join(
            (suite.stdout or suite.stderr).strip().splitlines()[-8:]
        )
        if suite.returncode != 0:
            print(suite.stdout)
            print(suite.stderr)
            return 1

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
reservation_id = prepared.body['payload']['admission']['reservation_id']
instance = call('/v1/inference/instances', Method.POST, reservation_id=reservation_id)
assert instance.status == 200
body = instance.body['payload']
assert body['runtime'] == 'vllm'
started = call('/v1/inference/instances/start', Method.POST, instance_id=body['instance_id'])
assert started.status == 200
assert started.body['payload']['observed_state'] == 'failed'
assert started.body['payload']['runtime'] == 'vllm'
infer = call('/v1/inference/instances/infer', Method.POST, instance_id=body['instance_id'], prompt='hello')
assert infer.status == 412
assert infer.body['error']['context']['reason'] == 'instance_not_running'
from kultrun.inference.contracts import InstanceId
stored = p.instances.get(InstanceId.parse(body['instance_id']))
assert stored is not None and stored.runtime.value == 'vllm'
artifact = p.inventory.get(ArtifactId.parse(prepared.body['payload']['artifact_id']))
reservation = p.resources.get(ReservationId.parse(reservation_id))
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
    'runtime': body['runtime'],
    'vllm_start_state': started.body['payload']['observed_state'],
    'infer_reason': infer.body['error']['context']['reason'],
    'reference_runtime': running.runtime.value,
    'chat_status': chat.status,
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

        infer_cli = run([str(kultrun), "instances", "infer"], env)
        usage = (infer_cli.stderr or infer_cli.stdout).strip()
        evidence["cli_infer_usage"] = usage
        if infer_cli.returncode == 0 or "prompt" not in usage:
            print("FAIL: CLI infer usage", infer_cli.stdout, infer_cli.stderr)
            return 1

        console = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Inference instances' in html,"
                " '/inference/instances/infer' in js,"
                " 'Infer' in js,"
                " 'chat' not in js,"
                " 'Active Pool' not in js)",
            ],
            env,
        )
        evidence["console"] = console.stdout.strip()
        print(json.dumps(evidence, indent=2))
        if evidence.get("runtime") != "vllm":
            print("FAIL: runtime", evidence)
            return 1
        if evidence.get("vllm_start_state") != "failed":
            print("FAIL: vLLM start", evidence)
            return 1
        if evidence.get("infer_reason") != "instance_not_running":
            print("FAIL: infer", evidence)
            return 1
        if evidence.get("reference_runtime") != "reference-serving":
            print("FAIL: reference", evidence)
            return 1
        if evidence.get("chat_status") != 404:
            print("FAIL: chat route exists")
            return 1
        if "True True True True True True" not in console.stdout:
            print("FAIL: Console", console.stdout)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
