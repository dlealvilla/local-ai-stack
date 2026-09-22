# M5 physical evidence — not closed

The frozen candidate is commit `d3b45dda63eaca99116e5fa37744c498c259913b`,
wheel SHA256 `9a8747ffb567c5270911fcb67cc10000bad65fc00740e4b813b7a1c25dd713bd`,
build `0.1.0+d3b45dda63ea`. An earlier wheel from `b877353` failed
inspection on a CUDA container because Capacity refused more than 64
storage domains. That cap is now 512. The CUDA proof below used the
rebuilt wheel.

## CUDA — pass

Pod `1ohrpr3b9r8geg`, terminated after evidence was read.
Secure NVIDIA A40 in CA-MTL-1, catalog price $0.49/hour.
Host CUDA 12.8, driver 570.195.03, 46068 MiB.
Image `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` (official
template `runpod-torch-v280`).

Inspect: `supported`, backend `cuda`, failure `none`.
Provision and re-entry: `ready`.
One generation: `fgen_7d35608a014edb96`.
Candidate `vllm-0.18.0-cuda`.
Managed Python 3.12. Reported vLLM `0.18.0`. Torch CUDA `12.9`.
Persistent bytes `10169619031`. Cache bytes `10148791521`.
No Hugging Face model download. A small `hadamards.safetensors`
file ships inside the `compressed_tensors` package.

Approximate compute: about 16 minutes, about $0.13 at the catalog rate.

## ROCm — not ready

Pod `mll2gjv7cu6jq0`, terminated.
Secure MI300X in EU-RO-1, catalog price $2.39/hour.
Official image `runpod/pytorch:2.4.0-py3.10-rocm6.1.0-ubuntu22.04`.
`rocminfo` reported gfx942 / AMD Instinct MI300X and ROCm `6.1.0-82`.
`amd-smi` still lacked PyYAML; PrerequisiteReadiness diagnosed
`missing_interpreter_dependency`. Inspect still resolved `supported`.

Provision installed `vllm==0.18.0+rocm700`. Verification failed.
Importing torch raised `OSError: libmpi_cxx.so.40: cannot open shared
object file`. That library is not on this image. A second provision
did not treat the failed generation as healthy. No model was served.

Approximate compute: about 9 minutes, about $0.37 at the catalog rate.

A follow-up pod `98xur55q2dlcpc` used the public image
`rocm/pytorch:rocm7.0_ubuntu24.04_py3.12_pytorch_release_2.8.0`.
It stayed in `start container ... begin` and never published SSH.
It was terminated. Approximate compute: about 12 minutes, about $0.48
at the catalog rate.

No pod created for this campaign is still running.
