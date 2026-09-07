"""Stage 1.5C T2: clean wheel proves the reconciled Runtime / Executor seam.

Installs the committed wheel into an isolated venv with no source checkout.
Reuses the Stage 1.5B instance / mobility proof and adds capability,
descriptor, launch-spec, and handle checks.
"""

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
        "container_executor": False,
        "runtime_resolver": False,
        "vllm": False,
    }
    with tempfile.TemporaryDirectory(prefix="kultrun-t2-15c-") as workspace:
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

        seam = run(
            [
                str(python),
                "-c",
                """
from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.execution.recording import RecordingExecutor
from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.execution.contracts import FeatureSupport
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import build, resolve_configuration
from kultrun.platform.launch import executor_spec_from
from kultrun.runtime.contracts import RuntimeLaunchRequest, RuntimeSupportTier

p = build(resolve_configuration())
host = p.hosts.current
native = NativeProcessExecutor()
cap = native.capabilities(host)
assert cap.executor.value == 'native-process'
assert cap.process_execution is FeatureSupport.SUPPORTED
assert cap.isolation is FeatureSupport.UNSUPPORTED
desc = ReferenceServingRuntime().support()
assert desc.support_tier is RuntimeSupportTier.TEST_ONLY
assert desc.production_candidate is False
launch = ReferenceServingRuntime().launch_spec(RuntimeLaunchRequest(instance_id='t2'))
assert 'docker' not in launch.executable.lower()
spec = executor_spec_from(launch)
rec = RecordingExecutor().start(host.host_id, spec)
assert rec.executor.value == 'recording'
assert not is_resolved(rec.pid)
assert is_resolved(rec.external_identity)
print('seam-ok')
""",
            ],
            env,
        )
        if seam.returncode != 0 or "seam-ok" not in seam.stdout:
            print(seam.stderr or seam.stdout)
            return 1
        evidence["native_capability"] = True
        evidence["runtime_descriptor"] = True
        evidence["launch_spec"] = True
        evidence["recording_handle"] = True

        for name in (TINY, FOURTEEN):
            acquired = run([str(kultrun), "models", "acquire", name], env)
            if acquired.returncode != 0:
                print(acquired.stderr or acquired.stdout)
                return 1

        script = Path(__file__).with_name("t2_inference_instance.py").read_text(
            encoding="utf-8"
        )
        # Reuse the in-process lifecycle proof from the 1.5B T2 script body.
        start = script.find('script = r"""')
        end = script.find('"""', start + 13)
        if start < 0 or end < 0:
            print("FAIL: could not locate 1.5B proof script")
            return 1
        proof_src = script[start + 13 : end]
        proof = run([str(python), "-c", proof_src], env)
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
        inspect = run(
            [
                str(python),
                "-c",
                "from kultrun.adapters.http.console import ASSETS, read;"
                "html=read('index.html').decode(); js=read('app.js').decode();"
                "print(all(read(n) for n in ASSETS),"
                " 'Inference instances' in html,"
                " '/inference/instances' in js,"
                " 'execution id' in js,"
                " 'Active Pool' not in js)",
            ],
            env,
        )
        evidence["console"] = inspect.stdout.strip()
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
        if "True True True True True" not in inspect.stdout:
            print("FAIL: Console", inspect.stdout)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
