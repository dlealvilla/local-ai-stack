# RUKAN-REAL-DEPLOYED-UI-DEMO-001 paste-back

A. Server: RunPod secure NVIDIA A40, pod `z0qqtyr43lj1n9`, EU-SE-1, CUDA 13.0, `$0.49/hour`. Created `2026-09-30T10:29:28Z`. Other account burn `$0.113/hour`. Balance before create `$34.899`. Floor `$0.50` held. The 90-minute rule puts the viewing deadline at `2026-09-30T11:59:28Z` (9:59 PM AEST). The pod was not stopped.

B. Accepted product: canonical `machi@70e7c4571deb181b3b5478d10f5bbc74f2ee02e7`. Installed wheel build `0.1.0+50f8d1e5f7ba`. SHA256 `57db4f492bea2219813831d67edb3b9604263551625f3c9ad758b43504a498ed`.

C. Admin is running on the server at `127.0.0.1:8765`. The SSH tunnel is already up on this machine. If it drops, paste:

```
ssh -N -T -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 8765:127.0.0.1:8765 -L 8790:127.0.0.1:8790 -L 8899:127.0.0.1:8899 -R 8781:127.0.0.1:8781 -p 22022 root@194.68.245.59
```

Open `http://127.0.0.1:8765`. Verified in the packaged UI: Overview (vLLM ready, model `mart_16a294cbd51b0ffd`, 7 requests), Deployment (one ready instance), People (Ada, Bob, team Desk), Identity, Workspace, MCP (Acceptance), System (SAFE host memory 46 GiB, SAFE accelerator memory 45 GiB). The navigation also contains Models, Inference, Analytics, Activity, and Settings.

D. Workspace is running on the server at `127.0.0.1:8790`. Same tunnel. Open `http://127.0.0.1:8790`. Sign in, then choose Continue as Ada or Continue as Bob. No password. Verified: model selector, Chat, Usage, Connections, Tools (Acceptance), Agents (Adder, with Edit, Chat, Archive), sign-in through the tunneled demo IdP, streaming chats, stop, regenerate, a real Qwen `add` tool call (`add 2 3`, answer contains 5), MCP resource and prompt, and per-message usage. Bob can chat and is denied agent create.

E. Command Center is running locally from the accepted wheel. Data dir `/tmp/rukan-demo-command-center`. Command: `machi command-center serve --data-dir /tmp/rukan-demo-command-center --port 8780`. Open `http://127.0.0.1:8780`. A real report has arrived: 1 deployment, 5 reports, 7 reported requests, 0 rejected.

F. Telemetry: the server posts to `http://127.0.0.1:8781/v1/telemetry/reports`. That port is an SSH reverse tunnel to the local intake (`machi command-center intake --data-dir /tmp/rukan-demo-command-center --host 127.0.0.1 --port 8781 --local-test`). Report received: yes. Canaries absent from the received documents: both synthetic emails, the agent instruction, the tool-turn request, the resource URI, `add 2 3`, and the conversation title.

G. Demo login: open `http://127.0.0.1:8790`, click Sign in, then Continue as Ada (agent builder allowed) or Continue as Bob (agent builder denied). No password and no bearer token.

H. Keep running:
- Server pid 476: `machi admin serve` on 8765
- Server pid 2486: `machi workspace serve` on 8790
- Server pid 2473: demo IdP on 8899
- Server pid 2484: acceptance MCP on 8766
- Server pid 1864: vLLM for `mart_16a294cbd51b0ffd`
- Local pid 25152: Command Center on 8780
- Local pid 25159: telemetry intake on 8781
- Local pid 25235: SSH tunnel

I. Shutdown, not executed:
```
kill 25229 25146 25153
ssh -T -o BatchMode=yes -p 22022 root@194.68.245.59 'kill 476 2486 2473 2484 1864'
```
Then delete pod `z0qqtyr43lj1n9` only after you say you are finished viewing.

J. `RUKAN_REAL_DEPLOYED_UI_DEMO_READY_FOR_DANIEL`
