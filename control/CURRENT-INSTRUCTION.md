# CURRENT LEAD DEVELOPER INSTRUCTION

**Status:** HOLD — CHUNK 3 PRODUCT/ARCHITECTURE DISCUSSION
**Program:** `MACHI-OLLAMA-MACROPATH-001`
**Chunk:** 3 of 6

Do not execute the previous Chunk-3 gate.

Product direction has changed:
- native/vLLM uses Machi model catalog / Model Warehouse;
- Ollama macropath uses Ollama model catalog/store;
- do not build a default Machi-artifact -> Ollama-model conversion bridge.

Exact Ollama v0.34.3 contains an internal specialist fit/scheduler layer.
The Lead/product owner is deciding its boundary with Machi qualification.

Read:
- `control/OLLAMA-CHUNK-03-QUALIFIER-BOUNDARY.md`
- `control/CORE-VS-COMMODITY-POLICY.md`

No code, docs, tests, model bytes, server, load or inference until the Lead
publishes the next instruction.

STOP.
