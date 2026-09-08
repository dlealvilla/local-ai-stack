"""Stage 1.6B T2: clean wheel proves runtime candidate resolution.

Installs the committed wheel into an isolated venv with no source checkout.
Proves host discovery, executor profiles, AUTO/EXPLICIT candidates, API,
CLI, Console assets, reference exclusion, and Stage 1.6A native/container
contracts. Does not install or import vLLM.
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
        "vllm_installed": False,
        "vllm_imported": False,
        "provision": False,
        "verify": False,
        "runtime_resolver": True,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-16b-") as workspace:
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

        host = run([str(kultrun), "host"], env)
        if host.returncode != 0:
            print(host.stderr or host.stdout)
            return 1
        evidence["host"] = True

        seam = run(
            [
                str(python),
                "-c",
                """
from kultrun.adapters.container.recording import RecordingContainerEngine
from kultrun.adapters.execution.container import ContainerExecutor
from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.runtime.serving import PYTHON_COMPONENT, ReferenceServingRuntime
from kultrun.execution.contracts import ContainerExecutionConfig, FeatureSupport
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import build, resolve_configuration
from kultrun.platform.launch import executor_spec_from
from kultrun.runtime.contracts import RuntimeLaunchRequest, RuntimeSupportTier

p = build(resolve_configuration())
host = p.hosts.current
native = NativeProcessExecutor()
cap = native.capabilities(host)
assert cap.executor.value == 'native-process'
desc = ReferenceServingRuntime().support()
assert desc.support_tier is RuntimeSupportTier.TEST_ONLY
launch = ReferenceServingRuntime().launch_spec(RuntimeLaunchRequest(instance_id='t2'))
assert launch.executable == PYTHON_COMPONENT
assert 'docker' not in launch.executable.lower()
spec = executor_spec_from(launch)
engine = RecordingContainerEngine()
container = ContainerExecutor(
    engine, ContainerExecutionConfig(image='kultrun-reference-serving:stage-16a')
)
ccap = container.capabilities(host)
assert ccap.executor.value == 'container-docker'
assert ccap.executor_type.value == 'container'
assert ccap.isolation is FeatureSupport.SUPPORTED
assert ccap.accelerator_exposure is FeatureSupport.UNKNOWN
handle = container.start(host.host_id, spec)
assert handle.executor.value == 'container-docker'
assert not is_resolved(handle.pid)
assert is_resolved(handle.external_identity)
container.stop(handle)
print('seam-ok')
""",
            ],
            env,
        )
        if seam.returncode != 0 or "seam-ok" not in seam.stdout:
            print(seam.stderr or seam.stdout)
            return 1
        evidence["native_capability"] = True
        evidence["container_executor_contract"] = True

        proof = run(
            [
                str(python),
                "-c",
                """
import json
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.api.contracts import ApiRequest, Method
from kultrun.kernel.errors import ValidationError
from kultrun.main import build, resolve_configuration
from kultrun.runtime.contracts import RuntimeResolverMode
from kultrun.runtime.resolve import RuntimeResolver, resolve

p = build(resolve_configuration())
host = p.hosts.current
req = ApiRequest(method=Method.GET, path='/v1/runtimes/candidates')
auto = p.router.handle(req)
assert auto.status == 200
payload = auto.body['payload']
assert payload['mutations'] is False
assert payload['install'] is False
assert payload['verify'] is False
resolution = payload['resolution']
names = {
    item['runtime']
    for group in ('candidates', 'unsupported', 'unresolved')
    for item in resolution.get(group, [])
}
assert 'vllm' in names
assert 'reference-serving' not in names
explicit = p.router.handle(
    ApiRequest(
        method=Method.GET,
        path='/v1/runtimes/candidates',
        query={'runtime': 'vllm'},
    )
)
assert explicit.status == 200
body = explicit.body['payload']
assert body['policy']['mode'] == 'explicit'
assert body['policy']['requested_runtime'] == 'vllm'
executors = (
    p.executions.capabilities(host),
    p.plane.container_capability(host),
)
descriptors = p.runtimes.descriptors()
from kultrun.runtime.contracts import RuntimePolicy
from kultrun.runtime.resolve import path_presence
required = [
    component.value
    for descriptor in descriptors
    for component in descriptor.required_components
]
policy = RuntimePolicy()
first = resolve(host, executors, descriptors, policy, components=path_presence(required))
second = RuntimeResolver().resolve(
    host, executors, descriptors, policy, components=path_presence(required)
)
assert [item.candidate_id for item in first.candidates] == [
    item.candidate_id for item in second.candidates
]
assert first.policy.mode is RuntimeResolverMode.AUTO
assert all(item.runtime.value != 'reference-serving' for item in first.candidates)
assert all(item.runtime.value != 'reference-serving' for item in first.unsupported)
opt_in = RuntimePolicy(allow_test_only=True, allow_reference_runtimes=True)
allowed = resolve(
    host, executors, descriptors, opt_in, components=path_presence(required)
)
assert any(
    item.runtime.value == 'reference-serving'
    for item in (*allowed.candidates, *allowed.unsupported, *allowed.unresolved)
)
adapter = VllmRuntimeSupport()
try:
    adapter.launch_spec()
except ValidationError as error:
    assert 'not installed' in str(error)
else:
    raise SystemExit('vLLM launch_spec must refuse')
try:
    import vllm  # noqa: F401
except ImportError:
    pass
else:
    raise SystemExit('vLLM must not be importable in T2')
print(json.dumps({
    'api': auto.status,
    'explicit_api': explicit.status,
    'auto_runtimes': sorted(names),
    'preferred': first.preferred_candidate_id
    if isinstance(first.preferred_candidate_id, str) else None,
    'classes': sorted({item.compatibility.value for item in first.candidates}),
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

        auto_cli = run([str(kultrun), "runtimes", "candidates"], env)
        if auto_cli.returncode != 0:
            print(auto_cli.stderr or auto_cli.stdout)
            return 1
        if "reference-serving" in auto_cli.stdout:
            print("FAIL: AUTO CLI listed reference-serving")
            print(auto_cli.stdout)
            return 1
        evidence["cli_auto"] = auto_cli.stdout.strip()
        repeat = run([str(kultrun), "runtimes", "candidates"], env)
        if repeat.stdout != auto_cli.stdout:
            print("FAIL: AUTO CLI not deterministic")
            return 1
        evidence["cli_deterministic"] = True

        explicit_cli = run(
            [str(kultrun), "runtimes", "candidates", "--runtime", "vllm"], env
        )
        if explicit_cli.returncode != 0:
            print(explicit_cli.stderr or explicit_cli.stdout)
            return 1
        if "mode explicit" not in explicit_cli.stdout:
            print("FAIL: explicit CLI", explicit_cli.stdout)
            return 1
        if "reference-serving" in explicit_cli.stdout:
            print("FAIL: EXPLICIT fell back to reference-serving")
            return 1
        evidence["cli_explicit"] = explicit_cli.stdout.strip()

        inspect = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "panel=html.split('Runtime candidates',1)[1].split('<section',1)[0];"
                "print(all(read(n) for n in ASSETS),"
                " 'Runtime candidates' in html,"
                " '/runtimes/candidates' in js,"
                " 'Install' not in panel,"
                " 'Start Runtime' not in html)",
            ],
            env,
        )
        evidence["console"] = inspect.stdout.strip()
        evidence["source_checkout"] = False
        print(json.dumps(evidence, indent=2))
        if payload.get("api") != 200 or payload.get("explicit_api") != 200:
            print("FAIL: API", payload)
            return 1
        if "True True True True True" not in inspect.stdout:
            print("FAIL: Console", inspect.stdout)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
