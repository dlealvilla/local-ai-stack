# M6 physical acceptance

NVIDIA CUDA only. AMD was not a Model host. `M-5-AMD-01` stays open.

## Candidate

- Commit `a91ab2c8ae3d71d1e0370fc5264ab5c4f334c5e9`
- Wheel SHA256 `8212ab16fd3dfd2a256c3eb4c95bb681fef4cef2f420a38a2dddffbcd9369e4b`
- Build `0.1.0+a91ab2c8ae3d`
- Isolated `verify_ok`
- Lab campaign `camp_093923490aef3d30`
- Lab candidate `cand_3ad76308239b4e7d`

The download itself ran on ancestor `5fef071`, which already had
the storage gate and hub file sizes. `a91ab2c` adds citation of a
stored artifact and was re-inspected against that same warehouse.

## Host

- Pod `uqukv4so1hgtlv`, terminated
- Secure A40, CA-MTL-1, catalog rate $0.49/h
- Image `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`
- Host CUDA 12.8, torch CUDA 12.9, vLLM 0.18.0
- Foundation generation `fgen_8bac70ed6e01e752`
- Alive about 20 minutes, about $0.16 at the catalog rate
- No server process

## Case A — hub

Repository `hf-internal-testing/tiny-random-LlamaForCausalLM`.

Why this one: `LlamaForCausalLM` is recognized by the installed
vLLM 0.18.0 registry, the safetensors file is about 4 MiB, the
config does not ask for repository code, and the card does not
declare a license.

- Requested revision `main`
- Immutable revision `9fb191250dd56d0ba7ec9785a025ed29c03d5998`
- Architecture `LlamaForCausalLM`, dtype `float32`, quantization `none`
- Declared context 2048
- License metadata missing, commercial use unknown
- Compatibility `compatible`, provider qualification `qualified`
- Stored 6,477,074 bytes in 7 files
- Artifact `mart_01a30fdd655751ed`
- Second acquire reused that revision and byte count
- After `models/cache` was removed, the warehouse manifest remained
- A later inspect on the closure wheel cited `mart_01a30fdd655751ed`

## Case B — local import

The stored files were copied to an external directory that did not
contain `.machi-model.json`. Import copied them into the warehouse.
The external directory still had no manifest afterward.
Second artifact `mart_ee391b72cc5d6acc`, same 6,477,074 bytes.

## Case C — refusal

A local config naming `NotARealForCausalLM` inspected as
`unsupported` / `unsupported_architecture`. No weight download.

## Footprint

`models/` was about 12.4 MiB after both stored copies. The managed
vLLM tree was about 19.6 GiB and is Foundation, not the model
artifact. Staging was empty at the end.
