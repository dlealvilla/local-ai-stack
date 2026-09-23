# Machi Lead Developer ↔ Cursor Control Protocol

This branch is a **development control plane**, not a product/source branch.

## Authority

- `control/CURRENT-INSTRUCTION.md` is the current Lead Developer task.
- `control/STATE.json` is the machine-readable instruction state.
- `control/ARCHITECTURE-STATE.md` is a compact live architecture/status snapshot.
- `control/OPEN-DECISIONS.md` records decisions that remain genuinely open.
- `control/LATEST-PASTEBACK.md` is Cursor's latest complete final paste-back.

## Source-code isolation

Never merge this control branch into a Machi implementation branch.

Cursor works on its current implementation branch. It reads the control branch through `git fetch` / `git show` or `tools/machi_handoff.py sync`.

When work is complete:
1. Commit/push implementation/evidence on the implementation branch according to the task.
2. Write the full required paste-back to a local file.
3. Publish that file to this control branch with:
   `python tools/machi_handoff.py publish-pasteback <path>`
4. STOP.

## Lead Developer cycle

ChatGPT updates the instruction/state on this control branch.
Cursor is manually triggered with a short command such as **"Continue Machi from the Lead Developer handoff."**
Cursor syncs, executes, publishes its paste-back.
ChatGPT reads the paste-back directly from GitHub and issues the next instruction.

## Safety

- Control files never authorize bypassing Provider Selection Gates, physical acceptance gates, ownership rules, or privacy requirements.
- Product source is never patched on remote acceptance servers.
- Secrets, API keys, private SSH keys, prompts, customer content, and proprietary payloads must never be written to this branch.
- Historical evidence is not rewritten.
