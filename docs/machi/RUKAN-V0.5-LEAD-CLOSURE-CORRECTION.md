# Rukan v0.5 Lead closure correction

The preliminary closure at `124a1424ab20e6fd3e2ca96ee7fedb0cef539198`
and tag `checkpoint/rukan-core-product-closed-nvidia-vllm-124a142`
stay in history. This correction does not delete that tag.

## Tool calling

vLLM 0.18 documents `--enable-auto-tool-choice` and
`--tool-call-parser hermes` for `Qwen/Qwen2.5-*` and `Qwen/QwQ-*`.
The serve adapter adds those flags only when the artifact repository
matches that documented family. Other models stay
`tool_calling: unsupported`. The browser identity flow requires an ID
token nonce and does not accept an access token as the session
identity. The session cookie is `Secure` when `public_base` is HTTPS.

The corrected physical model, when the campaign uses a tool-capable
model, is `Qwen/Qwen2.5-0.5B-Instruct` revision
`7ae557604adf67be50417f59c2c2f167def9a775` (apache-2.0).
