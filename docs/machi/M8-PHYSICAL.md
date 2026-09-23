# M8 — Admit physical proof (NVIDIA)

The frozen wheel `0.1.0+aa9de288e897`, SHA256
`c9be0d96b764b13d4f32889086e56699e593ecf70db1cd44ac00ca4a0a768d26`,
was installed on one secure NVIDIA A40. The host hash matched.
The install was an artifact in site-packages, with Kultrun absent.

## Host

- Datacenter EU-SE-1, rate $0.49/hour
- Ubuntu 24.04.3, kernel 6.8.0-134-generic
- NVIDIA A40, UUID `GPU-20c65ff7-9c5a-1329-7403-8d8055ba8cb1`
- Driver 580.159.03, torch CUDA 13.0, reported memory 46068 MiB

## Chain

- Foundation `fgen_c26fd17227965d3d`, vLLM 0.18.0, backend cuda, READY, re-entry reused the generation
- Artifact `mart_01a30fdd655751ed`, revision `9fb191250dd56d0ba7ec9785a025ed29c03d5998`, 6477074 bytes, verified
- Capacity evidence `cap_foundation`
- SAFE host 49463128064, SAFE accelerator 48037363712
- Plan A `plan_9386cd212b6797e2`, context 2048, concurrency 4, tensor parallel 1, utilization 0.90
- Reservation A `rsv_2a0140a8698224c3`, state reserved, then released
- Plan B `plan_99937ebe5e9d59e9`, context 1024
- While A was held, B was refused `insufficient_host_memory` and created no hold
- After release, B was admitted as `rsv_c99c5951739509a5`
- A new ResourceManager on the same store still counted B and refused a conflicting admit
- Live reconciliation was `consistent`
- A copied envelope with SAFE host bytes of 1 reported `overcommitted` and left the hold in place
- A copied envelope with a different evidence id was refused `stale_capacity_input` and created no hold

A missing reservation id was not execution authorization. The matching reserved hold was. The released hold was not.

No vLLM server, serving instance, model load, or inference request was started. The managed vLLM install is Foundation, not Serve.

The pod was terminated. `M-8-01` and `M-8-02` stay open. AMD qualification stays `M-5-AMD-01`.
