"""Stage 1.6L — native vLLM launch, readiness, and bounded inference."""

from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import fields, replace
from pathlib import Path

import pytest

from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.api.contracts import Method
from kultrun.inference.contracts import InferenceRequest, InstanceId, ObservedState
from kultrun.inference.endpoint import LOOPBACK, allocate_loopback_port
from kultrun.inference.service import (
    InstanceService,
    parse_inference_request,
    served_model_identity,
)
from kultrun.kernel.errors import PreconditionFailedError, ValidationError
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import to_dict
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import main
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.runtime.contracts import RuntimeLaunchRequest, RuntimeLaunchSpec
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named, scan
from tests.test_inference_instance import SMALL, _Stack
from tests.test_runtime_deployment_plan import _call, _product
from tests.test_runtime_deployment_prepare import _current_plan
from tests.vllm_protocol import ProtocolServer, wrap_launch_with_protocol

SOURCE = Path(__file__).resolve().parent.parent / "src"
UNIQUE_PROMPT = "UNIQUE_PROMPT_TOKEN_16L_DO_NOT_STORE"
GIB = 1024**3
EIGHT_GIB = 8 * GIB
THIRTY_TWO_GIB = 32 * GIB
FOUR_GIB = 4 * GIB


def _model_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "artifact-model"
    directory.mkdir(exist_ok=True)
    (directory / "config.json").write_text("{}", encoding="utf-8")
    return directory


def _interpreter(tmp_path: Path) -> Path:
    path = tmp_path / "venv" / "bin" / "python"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _request(
    tmp_path: Path,
    *,
    served: str = "probe-model",
    context: object = 2048,
    accelerator: int = 0,
    quantization: object = "awq",
    port: int | None = None,
) -> RuntimeLaunchRequest:
    return RuntimeLaunchRequest(
        instance_id="inst_aaaaaaaaaaaaaaaa",
        interpreter=str(_interpreter(tmp_path)),
        model_path=str(_model_dir(tmp_path)),
        served_model=served,
        bind_address=LOOPBACK,
        bind_port=port or 18765,
        context_tokens=context,  # type: ignore[arg-type]
        accelerator_index=accelerator,
        quantization=quantization,  # type: ignore[arg-type]
        installation_id="rinst_bbbbbbbbbbbbbbbb",
        runtime_version="0.28.0",
    )


def test_launch_spec_honours_plan_installation_and_artifact(tmp_path: Path) -> None:
    request = _request(tmp_path, context=4096, accelerator=1)
    spec = VllmRuntimeSupport().launch_spec(request)
    assert spec.executable == str(_interpreter(tmp_path))
    assert spec.executable != "python"
    assert Path(spec.executable).is_absolute()
    assert spec.arguments[0:2] == ("-m", "vllm.entrypoints.openai.api_server")
    joined = " ".join(spec.arguments)
    assert str(_model_dir(tmp_path)) in spec.arguments
    assert "--model" in spec.arguments
    assert "huggingface.co" not in joined
    assert "download" not in joined.lower()
    assert "--host" in spec.arguments
    assert LOOPBACK in spec.arguments
    assert "0.0.0.0" not in spec.arguments
    assert "--served-model-name" in spec.arguments
    assert "probe-model" in spec.arguments
    assert "--max-model-len" in spec.arguments
    assert "4096" in spec.arguments
    assert "--quantization" in spec.arguments
    assert "awq" in spec.arguments
    assert "CUDA_VISIBLE_DEVICES=1" in spec.environment
    assert spec.device_indexes == (1,)
    assert "HF_HUB_OFFLINE=1" in spec.environment
    assert "TRANSFORMERS_OFFLINE=1" in spec.environment
    assert "PYTHONPATH=" in spec.environment
    assert "VLLM_USE_FLASHINFER_SAMPLER=0" in spec.environment
    assert "--trust-remote-code" not in spec.arguments
    assert "--no-enable-log-requests" in spec.arguments
    assert "--disable-log-requests" not in spec.arguments
    assert spec.runtime.value == "vllm"
    assert "--gpu-memory-utilization" not in spec.arguments
    assert "KULTRUN_GPU_MEMORY_SOURCE=runtime_default" in spec.environment


def test_launch_spec_context_and_concurrency_defaults(tmp_path: Path) -> None:
    request = replace(
        _request(tmp_path),
        context_tokens=NOT_PROVIDED,
        concurrency=NOT_PROVIDED,
        quantization=NOT_PROVIDED,
    )
    spec = VllmRuntimeSupport().launch_spec(request)
    assert "--max-model-len" not in spec.arguments
    assert "--max-num-seqs" not in spec.arguments
    assert "KULTRUN_CONTEXT_SOURCE=runtime_default" in spec.environment
    assert "KULTRUN_CONCURRENCY_SOURCE=runtime_default" in spec.environment
    assert "KULTRUN_GPU_MEMORY_SOURCE=runtime_default" in spec.environment
    assert "--quantization" not in spec.arguments


def test_launch_spec_refuses_public_bind_and_incomplete_request(
    tmp_path: Path,
) -> None:
    adapter = VllmRuntimeSupport()
    with pytest.raises(ValidationError, match="exact interpreter"):
        adapter.launch_spec()
    with pytest.raises(ValidationError, match="loopback"):
        adapter.launch_spec(replace(_request(tmp_path), bind_address="0.0.0.0"))
    with pytest.raises(ValidationError, match="absolute"):
        adapter.launch_spec(replace(_request(tmp_path), interpreter="python"))


def test_launch_spec_maps_reservation_to_gpu_memory_utilization(
    tmp_path: Path,
) -> None:
    adapter = VllmRuntimeSupport()
    eight = adapter.launch_spec(
        replace(
            _request(tmp_path),
            reserved_accelerator_bytes=EIGHT_GIB,
            accelerator_memory_total_bytes=THIRTY_TWO_GIB,
        )
    )
    assert "--gpu-memory-utilization" in eight.arguments
    value = eight.arguments[eight.arguments.index("--gpu-memory-utilization") + 1]
    assert value == "0.25"
    assert "KULTRUN_GPU_MEMORY_SOURCE=reservation" in eight.environment
    assert "KULTRUN_GPU_MEMORY_SOURCE=runtime_default" not in eight.environment
    assert f"KULTRUN_GPU_MEMORY_RESERVED_BYTES={EIGHT_GIB}" in eight.environment
    assert f"KULTRUN_GPU_MEMORY_DEVICE_BYTES={THIRTY_TWO_GIB}" in eight.environment
    assert "KULTRUN_GPU_MEMORY_UTILIZATION=0.25" in eight.environment
    four = adapter.launch_spec(
        replace(
            _request(tmp_path),
            reserved_accelerator_bytes=FOUR_GIB,
            accelerator_memory_total_bytes=THIRTY_TWO_GIB,
        )
    )
    other = four.arguments[four.arguments.index("--gpu-memory-utilization") + 1]
    assert other == "0.125"
    assert other != value
    assert eight.arguments[0:2] == ("-m", "vllm.entrypoints.openai.api_server")
    assert "--host" in eight.arguments


def test_launch_spec_refuses_invalid_gpu_memory_inputs(tmp_path: Path) -> None:
    adapter = VllmRuntimeSupport()
    with pytest.raises(ValidationError, match="greater than zero"):
        adapter.launch_spec(
            replace(
                _request(tmp_path),
                reserved_accelerator_bytes=0,
                accelerator_memory_total_bytes=THIRTY_TWO_GIB,
            )
        )
    with pytest.raises(ValidationError, match="greater than zero"):
        adapter.launch_spec(
            replace(
                _request(tmp_path),
                reserved_accelerator_bytes=-EIGHT_GIB,
                accelerator_memory_total_bytes=THIRTY_TWO_GIB,
            )
        )
    with pytest.raises(ValidationError, match="exceeds the selected device"):
        adapter.launch_spec(
            replace(
                _request(tmp_path),
                reserved_accelerator_bytes=THIRTY_TWO_GIB + 1,
                accelerator_memory_total_bytes=THIRTY_TWO_GIB,
            )
        )
    with pytest.raises(ValidationError, match="unresolved"):
        adapter.launch_spec(
            replace(
                _request(tmp_path),
                reserved_accelerator_bytes=EIGHT_GIB,
                accelerator_memory_total_bytes=NOT_PROVIDED,
            )
        )


def test_resource_manager_and_executor_do_not_own_vllm_gpu_flag() -> None:
    root = SOURCE
    manager = (root / "kultrun" / "resource" / "manager.py").read_text(encoding="utf-8")
    native = (
        root / "kultrun" / "adapters" / "execution" / "native_process.py"
    ).read_text(encoding="utf-8")
    request_source = (
        root / "kultrun" / "resource" / "contracts.py"
    ).read_text(encoding="utf-8")
    requirement = (root / "kultrun" / "model" / "contracts.py").read_text(
        encoding="utf-8"
    )
    capacity = (root / "kultrun" / "capacity" / "contracts.py").read_text(
        encoding="utf-8"
    )
    assert "gpu-memory-utilization" not in manager
    assert "gpu-memory-utilization" not in native
    assert "--gpu-memory-utilization" not in request_source
    assert "gpu-memory-utilization" not in requirement
    assert "gpu-memory-utilization" not in capacity


def test_launch_spec_has_no_implementation_fields(tmp_path: Path) -> None:
    spec = VllmRuntimeSupport().launch_spec(_request(tmp_path))
    names = {field.name for field in fields(spec)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)


def test_readiness_matrix() -> None:
    adapter = VllmRuntimeSupport()
    healthy = ProtocolServer(mode="healthy", model="probe-model")
    try:
        ready = adapter.inspect_readiness(
            stdout="",
            stderr="",
            execution_alive=True,
            bound_address=healthy.address,
            bound_port=healthy.port,
            expected_served_model="probe-model",
        )
        assert ready.ready is True
        assert "probe-model" in ready.served_models
    finally:
        healthy.close()
    failed = ProtocolServer(mode="health-fail", model="probe-model")
    try:
        not_ready = adapter.inspect_readiness(
            stdout="",
            stderr="",
            execution_alive=True,
            bound_address=failed.address,
            bound_port=failed.port,
            expected_served_model="probe-model",
        )
        assert not_ready.ready is False
        assert str(not_ready.reason) == "health probe failed"
    finally:
        failed.close()
    wrong = ProtocolServer(mode="wrong-model", model="probe-model")
    try:
        mismatch = adapter.inspect_readiness(
            stdout="",
            stderr="",
            execution_alive=True,
            bound_address=wrong.address,
            bound_port=wrong.port,
            expected_served_model="probe-model",
        )
        assert mismatch.ready is False
        assert str(mismatch.reason) == "runtime_model_mismatch"
    finally:
        wrong.close()
    dead = adapter.inspect_readiness(
        stdout="", stderr="", execution_alive=False, bound_port=9
    )
    assert dead.ready is False


def test_complete_parses_usage_and_text() -> None:
    server = ProtocolServer(mode="healthy", model="probe-model")
    try:
        result = VllmRuntimeSupport().complete(
            address=server.address,
            port=server.port,
            served_model="probe-model",
            prompt="hello there",
            max_output_tokens=8,
            temperature=0.0,
            timeout_seconds=2.0,
        )
        assert result.text.startswith("ok:hello there")
        assert result.finish_reason == "stop"
        assert result.input_tokens == 2
        assert result.output_tokens == 8
    finally:
        server.close()


def test_complete_timeout_and_malformed() -> None:
    slow = ProtocolServer(mode="slow-completion", model="probe-model", slow=1.5)
    try:
        with pytest.raises(PreconditionFailedError) as timed:
            VllmRuntimeSupport().complete(
                address=slow.address,
                port=slow.port,
                served_model="probe-model",
                prompt="hello",
                max_output_tokens=8,
                temperature=0.0,
                timeout_seconds=0.2,
            )
        assert timed.value.context["reason"] == "inference_timeout"
    finally:
        slow.close()
    bad = ProtocolServer(mode="malformed-completion", model="probe-model")
    try:
        with pytest.raises(PreconditionFailedError) as malformed:
            VllmRuntimeSupport().complete(
                address=bad.address,
                port=bad.port,
                served_model="probe-model",
                prompt="hello",
                max_output_tokens=8,
                temperature=0.0,
                timeout_seconds=2.0,
            )
        assert malformed.value.context["reason"] == "inference_invalid_response"
    finally:
        bad.close()


def _vllm_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str = "healthy",
    timeout: float = 3.0,
    delay: float = 0.3,
    slow: float = 2.0,
) -> _Stack:
    stack = _Stack(tmp_path)
    stack.runtimes = RuntimeCatalogue(
        (stack.runtimes.get(Name("reference-serving")), VllmRuntimeSupport())
    )
    original = VllmRuntimeSupport.launch_spec
    captured: dict[str, RuntimeLaunchSpec] = {}

    def wrapped(
        self: VllmRuntimeSupport, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        spec = original(self, request)
        captured["spec"] = spec
        return wrap_launch_with_protocol(
            original, mode=mode, delay=delay, slow=slow
        )(self, request)

    monkeypatch.setattr(VllmRuntimeSupport, "launch_spec", wrapped)
    stack.instances = InstanceService(
        stack.store,
        stack.clock,
        stack.inventory,
        stack.resources,
        stack.executions,
        stack.runtimes,
        startup_timeout=timeout,
        live_executor="native-process",
    )
    stack.captured_launch = captured
    return stack


def _complete_request(tmp_path: Path, instance: object) -> RuntimeLaunchRequest:
    port = allocate_loopback_port()
    return RuntimeLaunchRequest(
        instance_id=instance.instance_id.value,  # type: ignore[attr-defined]
        artifact_id=(
            instance.artifact_id.value  # type: ignore[attr-defined]
            if instance.artifact_id is not None  # type: ignore[attr-defined]
            else ""
        ),
        interpreter=str(_interpreter(tmp_path)),
        model_path=str(_model_dir(tmp_path)),
        served_model=served_model_identity(instance),  # type: ignore[arg-type]
        bind_address=LOOPBACK,
        bind_port=port,
        accelerator_index=0,
        quantization=NOT_PROVIDED,
        runtime_version="0.28.0",
        reserved_accelerator_bytes=FOUR_GIB,
        accelerator_memory_total_bytes=THIRTY_TWO_GIB,
    )


def test_start_ready_infer_stop_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    request = _complete_request(tmp_path, instance)
    started = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=request,
    )
    assert started.observed_state is ObservedState.RUNNING
    assert started.ready is True
    assert started.endpoint is not None
    assert started.endpoint.address == LOOPBACK
    pid = started.pid
    again = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=request,
    )
    assert again.pid == pid
    live = [
        item
        for item in stack.executions.list()
        if item.observed_state.value == "running"
    ]
    assert len(live) == 1
    spec = stack.captured_launch["spec"]
    assert "--gpu-memory-utilization" in spec.arguments
    assert spec.arguments[spec.arguments.index("--gpu-memory-utilization") + 1] == (
        "0.125"
    )
    assert "KULTRUN_GPU_MEMORY_SOURCE=reservation" in spec.environment
    response = stack.instances.infer(
        instance.instance_id,
        InferenceRequest(prompt="hello world", max_output_tokens=8),
    )
    assert response.generated_text.startswith("ok:hello world")
    assert response.served_model == "probe-model"
    assert response.runtime.value == "vllm"
    assert response.input_tokens == 2
    records = json.dumps(
        [to_dict(item) for item in stack.store.records(type(instance))]
    )
    assert "hello world" not in records
    assert UNIQUE_PROMPT not in records
    stopped = stack.instances.stop(instance.instance_id)
    assert stopped.observed_state is ObservedState.STOPPED
    time.sleep(0.1)
    with pytest.raises(PreconditionFailedError) as refused:
        stack.instances.infer(instance.instance_id, InferenceRequest(prompt="again"))
    assert refused.value.context["reason"] == "instance_not_running"
    restarted = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, instance),
    )
    assert restarted.observed_state is ObservedState.RUNNING
    assert restarted.pid != pid
    second = stack.instances.infer(
        instance.instance_id, InferenceRequest(prompt="second")
    )
    assert second.generated_text.startswith("ok:second")
    stack.instances.stop(instance.instance_id)


def test_start_memory_fraction_follows_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    first = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, instance),
    )
    assert first.observed_state is ObservedState.RUNNING
    first_spec = stack.captured_launch["spec"]
    first_value = first_spec.arguments[
        first_spec.arguments.index("--gpu-memory-utilization") + 1
    ]
    assert first_value == "0.125"
    stack.instances.stop(instance.instance_id)
    second = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=replace(
            _complete_request(tmp_path, instance),
            reserved_accelerator_bytes=EIGHT_GIB,
        ),
    )
    assert second.observed_state is ObservedState.RUNNING
    second_spec = stack.captured_launch["spec"]
    second_value = second_spec.arguments[
        second_spec.arguments.index("--gpu-memory-utilization") + 1
    ]
    assert second_value == "0.25"
    assert second_value != first_value
    stack.instances.stop(instance.instance_id)


def test_start_refuses_impossible_gpu_memory_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    failed = stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=replace(
            _complete_request(tmp_path, instance),
            reserved_accelerator_bytes=0,
        ),
    )
    assert failed.observed_state is ObservedState.FAILED
    assert "spec" not in stack.captured_launch
    live = [
        item
        for item in stack.executions.list()
        if item.observed_state.value == "running"
    ]
    assert live == []


def test_early_exit_timeout_wrong_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exited = _vllm_stack(tmp_path, monkeypatch, mode="exit-immediately", timeout=1.0)
    artifact = exited.stored()
    reservation = exited.reserve(artifact, vram=SMALL)
    instance = exited.instances.create(artifact, reservation, runtime=Name("vllm"))
    failed = exited.instances.start(
        instance.instance_id,
        ledger_health=exited.health(),
        launch_request=_complete_request(tmp_path, instance),
    )
    assert failed.observed_state is ObservedState.FAILED
    assert "exited" in str(failed.failure_reason)

    delayed = _vllm_stack(
        tmp_path / "timeout", monkeypatch, mode="delayed", timeout=0.4, delay=5.0
    )
    artifact = delayed.stored()
    reservation = delayed.reserve(artifact, vram=SMALL)
    instance = delayed.instances.create(artifact, reservation, runtime=Name("vllm"))
    timed = delayed.instances.start(
        instance.instance_id,
        ledger_health=delayed.health(),
        launch_request=_complete_request(tmp_path / "timeout", instance),
    )
    assert timed.observed_state is ObservedState.FAILED
    assert "timeout" in str(timed.failure_reason)
    live = [
        item
        for item in delayed.executions.list()
        if item.observed_state.value == "running"
    ]
    assert live == []

    mismatch = _vllm_stack(tmp_path / "mismatch", monkeypatch, mode="wrong-model")
    artifact = mismatch.stored()
    reservation = mismatch.reserve(artifact, vram=SMALL)
    instance = mismatch.instances.create(artifact, reservation, runtime=Name("vllm"))
    wrong = mismatch.instances.start(
        instance.instance_id,
        ledger_health=mismatch.health(),
        launch_request=_complete_request(tmp_path / "mismatch", instance),
    )
    assert wrong.observed_state is ObservedState.FAILED
    assert "model" in str(wrong.failure_reason).lower()


def test_inference_preconditions_and_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    created = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    with pytest.raises(PreconditionFailedError) as idle:
        stack.instances.infer(created.instance_id, InferenceRequest(prompt="hello"))
    assert idle.value.context["reason"] == "instance_not_running"
    with pytest.raises(ValidationError, match="non-empty"):
        parse_inference_request({"prompt": ""})
    with pytest.raises(ValidationError, match="greater than zero"):
        parse_inference_request({"prompt": "hi", "max_output_tokens": "0"})
    with pytest.raises(ValidationError, match="may not choose"):
        parse_inference_request({"prompt": "hi", "model": "other"})
    starting = replace(
        created,
        observed_state=ObservedState.STARTING,
    )
    stack.store.put(starting.instance_id.value, starting)
    with pytest.raises(PreconditionFailedError) as starting_err:
        stack.instances.infer(created.instance_id, InferenceRequest(prompt="hello"))
    assert starting_err.value.context["reason"] == "instance_not_ready"
    stack.store.put(created.instance_id.value, created)
    running = stack.instances.start(
        created.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, created),
    )
    assert running.observed_state is ObservedState.RUNNING
    assert is_resolved(running.pid)
    os.kill(int(running.pid), signal.SIGTERM)
    time.sleep(0.2)
    crashed = stack.instances.observe(running.instance_id)
    assert crashed.observed_state is ObservedState.FAILED
    with pytest.raises(PreconditionFailedError) as after:
        stack.instances.infer(running.instance_id, InferenceRequest(prompt="hello"))
    assert after.value.context["reason"] == "instance_not_running"


def test_product_start_does_not_substitute_reference(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    prepared = _call(platform, "/deployments/plan/prepare", Method.POST).body["payload"]
    created = _call(
        platform,
        "/inference/instances",
        Method.POST,
        reservation_id=prepared["admission"]["reservation_id"],
    )
    body = created.body["payload"]
    started = _call(
        platform,
        "/inference/instances/start",
        Method.POST,
        instance_id=body["instance_id"],
    )
    assert started.status == 200
    payload = started.body["payload"]
    assert payload["runtime"] == plan["runtime"] == "vllm"
    assert payload["observed_state"] == "failed"
    stored = platform.instances.get(InstanceId.parse(body["instance_id"]))
    assert stored is not None
    assert stored.runtime.value == "vllm"
    assert stored.observed_state is ObservedState.FAILED
    infer = _call(
        platform,
        "/inference/instances/infer",
        Method.POST,
        instance_id=body["instance_id"],
        prompt="hello",
    )
    assert infer.status == 412
    assert infer.body["error"]["context"]["reason"] == "instance_not_running"


def test_product_protocol_infer_and_stale_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = VllmRuntimeSupport.launch_spec
    captured: dict[str, RuntimeLaunchSpec] = {}

    def wrapped(
        self: VllmRuntimeSupport, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        spec = original(self, request)
        captured["spec"] = spec
        return wrap_launch_with_protocol(original)(self, request)

    monkeypatch.setattr(VllmRuntimeSupport, "launch_spec", wrapped)
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    prepared = _call(platform, "/deployments/plan/prepare", Method.POST).body["payload"]
    created = _call(
        platform,
        "/inference/instances",
        Method.POST,
        reservation_id=prepared["admission"]["reservation_id"],
    ).body["payload"]
    started = _call(
        platform,
        "/inference/instances/start",
        Method.POST,
        instance_id=created["instance_id"],
    )
    assert started.status == 200
    payload = started.body["payload"]
    assert payload["observed_state"] == "running"
    assert payload["ready"] is True
    assert payload["runtime"] == "vllm"
    spec = captured["spec"]
    assert "--gpu-memory-utilization" in spec.arguments
    utilization = spec.arguments[spec.arguments.index("--gpu-memory-utilization") + 1]
    assert utilization
    assert utilization != "0.9"
    assert "KULTRUN_GPU_MEMORY_SOURCE=reservation" in spec.environment
    first = _call(
        platform,
        "/inference/instances/infer",
        Method.POST,
        instance_id=created["instance_id"],
        prompt=UNIQUE_PROMPT,
        max_output_tokens="8",
        temperature="0",
    )
    assert first.status == 200
    body = first.body["payload"]
    assert UNIQUE_PROMPT in body["generated_text"]
    assert body["served_model"] == created["logical_name"]
    assert body["runtime"] == "vllm"
    second = _call(
        platform,
        "/inference/instances/infer",
        Method.POST,
        instance_id=created["instance_id"],
        prompt="follow-up",
    )
    assert second.status == 200
    other = next(
        item["logical_name"]
        for item in _call(platform, "/models/selection").body["payload"]["feasible"]
        if item["logical_name"] != plan["selected_model"]
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    listing = _call(platform, "/inference/instances").body["payload"]["instances"][0]
    assert listing["configuration_current"] is False
    assert listing["observed_state"] == "running"
    still = _call(
        platform,
        "/inference/instances/infer",
        Method.POST,
        instance_id=created["instance_id"],
        prompt="still",
    )
    assert still.status == 200
    assert still.body["payload"]["configuration_current"] is False
    blocked = _call(
        platform,
        "/inference/instances/start",
        Method.POST,
        instance_id=created["instance_id"],
    )
    assert blocked.status == 200
    assert blocked.body["payload"]["observed_state"] == "running"
    stale_new = _call(
        platform,
        "/inference/instances",
        Method.POST,
        reservation_id=prepared["admission"]["reservation_id"],
    )
    assert stale_new.status == 412
    stopped = _call(
        platform,
        "/inference/instances/stop",
        Method.POST,
        instance_id=created["instance_id"],
    )
    assert stopped.status == 200
    assert stopped.body["payload"]["observed_state"] == "stopped"
    restart = _call(
        platform,
        "/inference/instances/start",
        Method.POST,
        instance_id=created["instance_id"],
    )
    assert restart.status == 412
    assert restart.body["error"]["context"]["reason"] == "plan_stale"
    serialized = json.dumps(to_dict(platform.instances.list()[0]))
    assert UNIQUE_PROMPT not in serialized
    assert main(["instances", "infer", created["instance_id"], "--prompt", "nope"]) == 1


def test_cli_infer_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["instances", "infer"]) == 2
    assert "usage" in capsys.readouterr().err


def test_architecture_and_source_guards() -> None:
    source = (SOURCE / "kultrun" / "adapters" / "runtime" / "vllm.py").read_text(
        encoding="utf-8"
    )
    assert "import vllm" not in source
    assert "from vllm" not in source
    assert "snapshot_download" not in source
    assert "--trust-remote-code" not in source
    assert (
        _imports_named(
            SOURCE / "kultrun" / "adapters" / "runtime" / "vllm.py",
            "kultrun.inference",
            "subprocess",
            "kultrun.planning",
            "kultrun.resource",
            "kultrun.host",
        )
        == []
    )
    assert (
        _imports_named(
            SOURCE / "kultrun" / "inference" / "service.py",
            "kultrun.planning",
            "kultrun.platform",
            "subprocess",
        )
        == []
    )
    edges = [
        edge
        for edge in scan(SOURCE)
        if edge.source_package == "inference"
        and edge.target_package in {"planning", "platform"}
    ]
    assert edges == []
    routes = (SOURCE / "kultrun" / "api" / "routes.py").read_text(encoding="utf-8")
    assert "/inference/instances/infer" in routes
    assert "VllmRuntimeV2" not in source
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    assert "chat" not in script
    assert "/inference/instances/infer" in script
