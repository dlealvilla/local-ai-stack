# RUKAN v0.5 — FIRST-PARTY NATIVE WORKSPACE

Instruction ID: `RUKAN-V0.5-NATIVE-WORKSPACE-001`
Status: `QUEUED_PHASE_2_AFTER_BACKEND_FREEZE_PASS`

This phase builds the default employee-facing Rukan product.

No Docker.
No LibreChat dependency.
No direct browser access to Serve/vLLM/Ollama.

Use the repository's existing frontend conventions:
- React;
- TypeScript;
- Vite;
- Vitest;
- existing shared design tokens/components where useful.

Create a new first-party app:

`ui/workspace`

Production output is packaged into the Rukan Python artifact and served by the
Rukan Workspace service.

At runtime:
- Node is NOT required;
- npm is NOT required;
- a container runtime is NOT required.

The product goal is intentionally practical:

> a simple, polished, reliable organisational AI chat workspace with the most
> useful core features of products such as Open WebUI, while avoiding complex
> plugin systems and secondary features that would delay a usable Rukan product.

---

# 1. PRODUCT EXPERIENCE

The employee should see a focused workspace.

Suggested layout:

```text
┌─────────────────────────────────────────────────────────────┐
│ Rukan                    Model / Agent          Usage/Profile│
├────────────────┬────────────────────────────────────────────┤
│                │                                            │
│ New chat       │              Conversation                  │
│ Search         │                                            │
│                │ User message                               │
│ Conversations  │ Assistant streaming...                     │
│                │ Tool call / result when relevant           │
│                │                                            │
│ Agents         │                                            │
│ Tools          │                                            │
│                ├────────────────────────────────────────────┤
│ Settings       │ Attach?  Prompt box              Send/Stop │
└────────────────┴────────────────────────────────────────────┘
```

Do not clone Open WebUI visually.

Use Rukan's own visual language.

Primary qualities:
- calm;
- business-friendly;
- fast;
- readable;
- clear model/agent context;
- no infrastructure jargon on primary screens.

---

# 2. CORE NAVIGATION

Minimum:

- Chat;
- Conversations/history;
- Agents;
- Tools / Connections;
- My Usage;
- Profile/Session.

Desktop-first responsive behavior.

On smaller width:
- sidebar collapses;
- chat remains fully usable.

Do not build channels/social collaboration.

---

# 3. OIDC LOGIN / SESSION UX

Use the Phase 1 BFF/session foundation.

Routes:
- Sign in;
- callback;
- Sign out;
- session expired.

UI:
- one obvious "Sign in with <provider label>";
- no manual token pasting in normal product mode;
- useful errors for:
  - user not provisioned;
  - suspended;
  - binding conflict;
  - provider unavailable;
  - session expired.

Do not expose:
- access token;
- refresh token;
- subject id.

After sign-in:
- fetch `/api/workspace/v1/me`;
- load capabilities;
- show only allowed product features.

---

# 4. WORKSPACE CONTENT STORE

Add customer-local:

`workspace.sqlite`

or equivalent Rukan-owned Workspace database.

Schema-version it.

Minimum durable concepts:

## Conversation
- conversation_id;
- user_id;
- title;
- model_id;
- agent_id nullable;
- status active/archived;
- created_at;
- updated_at.

## Message
- message_id;
- conversation_id;
- ordinal;
- role;
- content;
- status;
- created_at;
- input/output token facts where applicable;
- usage_id where applicable;
- tool-call summary/reference nullable.

## Agent
Phase 3 will complete execution, but schema may be introduced now if clean.

## SavedPrompt
Optional if implemented.

Every query is scoped by authenticated Rukan user.

No cross-user conversation reads.

Conversation data is customer content:
- local only;
- excluded from vendor telemetry;
- excluded from ordinary operational support snapshot;
- included in customer backup/restore.

Use foreign keys and indexes.

---

# 5. CONVERSATION API

Workspace API under:

`/api/workspace/v1`

Required:

- GET conversations;
- POST conversation;
- GET conversation;
- PATCH conversation title;
- DELETE/archive conversation;
- POST message/send;
- POST stop/cancel;
- POST regenerate;
- PATCH user message + continue, if implemented cleanly;
- export conversation.

Use stable ids.

Do not let browser provide user_id.

User comes from session.

---

# 6. CHAT MESSAGE FLOW

Required happy path:

```text
user types message
      ↓
Workspace API stores durable user message
      ↓
authorizes current model/agent
      ↓
invokes Rukan Gateway
      ↓
streams response
      ↓
browser renders incremental tokens
      ↓
assistant message finalized locally
      ↓
usage linked
```

Do not write assistant content into operational analytics.

Operational usage remains non-content.

---

# 7. LIVE STREAMING UX

Use browser fetch streaming / ReadableStream or equivalent.

Do not add WebSocket unless genuinely needed.

Required:
- assistant placeholder appears immediately;
- content renders incrementally;
- visible generating state;
- Stop button;
- stop aborts request;
- backend closes upstream generation path;
- partial assistant response persists with status `interrupted` if useful;
- user can retry explicitly.

No automatic silent re-send after network disconnect.

A disconnect must not cause duplicate inference.

---

# 8. MESSAGE ACTIONS

Required:
- copy assistant response;
- regenerate last assistant response;
- edit latest/selected user message and continue from that point if architecture is
  simple and deterministic;
- delete/clear conversation with confirmation.

Desirable:
- retry failed message;
- fork conversation.

Do not build a complex branching tree UI unless the underlying edit/regenerate
semantics naturally require it.

Simplest acceptable edit semantics:
- editing an earlier user message truncates later messages after confirmation;
- then generates from the edited point.

This is easier to reason about than hidden branches.

---

# 9. MARKDOWN / CODE RENDERING

Render:
- paragraphs;
- headings;
- lists;
- tables;
- links;
- blockquotes;
- inline code;
- fenced code.

Syntax highlighting is desirable if a lightweight library is already acceptable.

Security:
- sanitize Markdown output;
- raw HTML disabled by default;
- javascript: links forbidden;
- external links use safe attributes.

Do not allow model output to execute scripts.

LaTeX/Mermaid are optional and deferred if they materially increase complexity.

---

# 10. MODEL SELECTOR

Use:
`GET /v1/models`

or Workspace projection of the same policy.

Only show allowed models.

If one:
- still display model context subtly;
- selector may collapse to one entry.

Changing model:
- applies to subsequent turns;
- conversation history remains;
- no model deployment authority.

If selected model becomes unavailable:
- show clear error;
- user may select another allowed model.

---

# 11. CONVERSATION HISTORY

Required:
- sidebar list;
- newest updated first;
- title;
- last updated;
- active selection;
- new chat;
- rename;
- delete/archive.

Conversation title:
- first user message truncated/sanitized by default;
- no extra model call required.

Search is desirable:
- simple local SQL LIKE/FTS on titles and optionally content.

If content search is implemented:
- customer-local only.

---

# 12. MY USAGE

Workspace includes a My Usage view.

Use Rukan authoritative user usage.

Show:
- 24h;
- 7d;
- 30d;
- retained/all;
- requests;
- input;
- output;
- total tokens;
- token coverage;
- model breakdown;
- failures where useful.

Do not derive cumulative usage from conversation content.

Per assistant message:
- show input/output/total when reported;
- otherwise `usage unavailable`, not estimated.

---

# 13. CONNECTIONS

Simple view:

## Rukan API access
- whether user may use API credentials;
- existing key metadata;
- create credential only if self-issuance is deliberately allowed;
- always allow self-revoke of owned key where current policy permits.

If self-issue remains admin-only in v0.5:
- show connection instructions;
- show key metadata;
- user must ask admin for new credential.

## Gateway
- base URL;
- OpenAI-compatible subset;
- allowed models.

Never show direct Serve endpoint.

---

# 14. TOOLS / MCP VIEW

Phase 3 will implement full official SDK integration.

Build UI contracts now.

Required views:
- approved MCP servers user can access;
- connection/status;
- tool count;
- tool names/descriptions;
- enabled/disabled for current chat where allowed.

Do not expose raw server credentials.

If MCP backend not yet ready during Phase 2:
- show feature behind capability flag;
- finish in Phase 3.

---

# 15. AGENTS VIEW / BUILDER SHELL

Phase 3 completes execution.

Build the first-party user experience now if backend contracts are ready.

Agent list:
- name;
- description;
- model;
- tool count;
- updated;
- owner.

Create/Edit form:
- name;
- description;
- model;
- instructions;
- tool selection;
- optional bounded generation settings.

No arbitrary Python.
No code editor.
No uploaded executable plugins.

Respect:
- agent_use;
- agent_builder.

If user can use agents but not create:
- list allowed agents;
- no create/edit actions.

---

# 16. SAVED PROMPTS

Implement only if low-risk after core chat is stable.

Simple:
- title;
- prompt text;
- user-owned;
- insert into composer.

Optional slash activation.

Do not delay core Workspace for it.

---

# 17. COMPOSER

Required:
- multiline input;
- Enter sends;
- Shift+Enter newline;
- Send;
- Stop while generating;
- disabled state during required conditions;
- current model/agent context visible.

Do not implement file upload/RAG in this phase.

Optionally add:
- prompt template picker;
- tool toggle.

---

# 18. CHAT CONTEXT ASSEMBLY

Workspace sends the conversation messages required for the current turn.

Do not send:
- deleted/truncated future messages;
- messages belonging to another user;
- UI-only metadata.

System messages:
- base agent instructions when agent selected;
- otherwise product may omit.

If no Agent:
- ordinary conversation only.

Bound total messages/content according to Gateway/runtime policy.

If context exceeds supported limit:
- return a clear error or apply a simple deterministic oldest-message truncation
  policy only if approved/documented.

Do not silently summarize with another model call in v0.5.

---

# 19. GENERATION SETTINGS

Keep simple.

Global/default:
- max output tokens bounded by Gateway.

Optional agent setting:
- temperature;
- max tokens.

Expose only settings actually supported reliably by the current runtime path.

Do not build dozens of sampler knobs.

---

# 20. ERROR / EMPTY STATES

Every major screen:
- loading;
- empty;
- error;
- retry.

Chat errors:
- authentication;
- suspended;
- no ready model;
- model not allowed;
- overloaded;
- upstream failure;
- network interrupted.

Translate codes into plain language.

Technical error code may be behind details.

---

# 21. ACCESSIBILITY / KEYBOARD

Reasonable baseline:
- semantic buttons/forms;
- labels;
- focus states;
- keyboard navigation;
- color contrast;
- aria-live for streaming/status where appropriate;
- no mouse-only core action.

Do not attempt exhaustive formal certification in v0.5.

---

# 22. THEMING

Use Rukan brand system/shared tokens.

Support:
- system/light/dark if straightforward;
- otherwise one polished default theme is acceptable.

Do not spend significant time on theme customization.

---

# 23. SECURITY

## Browser
- no bearer tokens in localStorage;
- no raw HTML model rendering;
- CSP where practical;
- CSRF on state-changing cookie-authenticated requests;
- same-origin APIs;
- no secret values in JS bundle.

## IDOR
Every content endpoint derives user from session.

Test:
- conversation A owned by user A;
- user B cannot read/update/delete/export it;
- agent ownership similarly.

## Session
- HttpOnly;
- high entropy;
- expiry;
- logout invalidates;
- suspend checked server-side.

---

# 24. PRIVACY

Workspace conversation content is customer-local.

Explicit tests:
- prompt canary not in Command Center;
- response canary not in Command Center;
- agent instructions not in vendor telemetry;
- MCP tool payload not in vendor telemetry.

Usage telemetry may include:
- user_request class locally;
- deployment aggregate vendor-side according to allow-list.

No names/emails vendor-side.

---

# 25. EXPORT / DELETE

Conversation export:
- Markdown;
- JSON if easy.

Delete:
- user can delete own conversation;
- deletion semantics documented.

No vendor copy.

If soft-delete/archival is chosen:
- user-facing Delete should have clear behavior.

---

# 26. WORKSPACE SERVICE HEALTH

Add:
- version/build;
- API compatibility;
- DB migration state;
- current provider id/status;
- Gateway readiness;
- model availability.

User-facing health should be simple.

Admin/support gets technical details.

---

# 27. PACKAGING

Create:

`ui/workspace/package.json`

matching repository versions where practical.

Build:
- typecheck;
- Vitest;
- Vite production.

Package `dist` into Python wheel.

Wheel install on clean venv:
- Workspace assets available;
- `workspace serve` works;
- no source checkout;
- no Node runtime.

Add packaging verification.

---

# 28. FRONTEND TESTS

Vitest/JSDOM or existing stack.

Required:
- login screen;
- session/me load;
- conversation list;
- new conversation;
- rename/delete;
- streaming render;
- stop;
- copy;
- regenerate;
- model selector;
- usage;
- error states;
- agent-builder access gating shell;
- tool view capability flag;
- XSS/unsafe Markdown;
- session expiry.

Use deterministic mocked Workspace API only at component level.

Also add integration tests against real local Python Workspace server.

---

# 29. BACKEND WORKSPACE TESTS

Required:
- conversation CRUD;
- user isolation;
- durable restart;
- message sequence;
- stream finalization;
- partial interrupted response;
- regenerate;
- edit/truncate semantics;
- export;
- usage linkage;
- session auth;
- CSRF;
- suspend;
- API version mismatch;
- migrations.

---

# 30. LOCAL FULL PRODUCT DEMO

Before Phase 3:

Run locally/fixture:

1. create Ada;
2. configure synthetic OIDC provider;
3. browser/session login;
4. new conversation;
5. select model;
6. send message;
7. observe incremental response;
8. stop one response;
9. regenerate;
10. restart Workspace;
11. conversation still present;
12. usage visible;
13. user B cannot see Ada;
14. suspend Ada;
15. existing session denied;
16. reactivate;
17. login again.

Use real backend Workspace APIs.

Fake only the final model/runtime boundary if local GPU unavailable.

---

# 31. PHASE 2 PASS

Internal status:

`RUKAN_V0_5_NATIVE_WORKSPACE_LOCAL_PASS`

Required:
- packaged first-party Workspace;
- no Docker;
- OIDC login/session;
- chat/history;
- true streaming;
- stop/regenerate;
- model selector;
- usage;
- basic Tools/Agent screens;
- security/privacy tests;
- local full demo;
- full frontend/backend QA.

Then continue automatically to:

`RUKAN-V0.5-MCP-AGENTS-AND-CORE-CLOSURE-001`

Do not stop.

# END PHASE 2
