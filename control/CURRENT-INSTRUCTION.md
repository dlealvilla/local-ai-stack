# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-FUNCTIONAL-PRODUCT-V0.3-FIX-002`
Status: `AUTHORIZED_CORRECTION`
Predecessor: `RUKAN-FUNCTIONAL-PRODUCT-V0.3-FINISH-001`
Correction starting source: `fd13ede7553011033a140d1206982f54536b7032`
Branch: `rukan/connected-monitoring-v0.3`

The v0.3 functional finish is close, but Lead review found three remaining acceptance defects. Do not broaden scope. Correct them, run the complete local QA/soak gates, publish paste-back, and STOP.

# 1. PEOPLE ADMIN UI MUST EXPOSE THE REAL BACKEND CAPABILITIES

Current backend/API already supports substantially more than the current People page.

Current UI only:
- creates a user;
- creates a team;
- lists users/teams;
- toggles active/suspended.

That is insufficient for the accepted product requirement.

The customer Admin People surface must make the implemented local directory genuinely administrable.

## Required user UI

Provide a useful user list/detail workflow with:

- search/filter;
- display name;
- email;
- status;
- team memberships;
- stable `user_id` behind technical details/progressive disclosure;
- created/updated time where useful;
- current access intent;
- effective access projection;
- explicit enforcement state `gateway_not_available`.

Real actions:
- edit display name;
- edit email;
- suspend;
- reactivate a suspended user;
- deactivate with confirmation;
- manage team memberships;
- edit user access intent.

Do not offer "reactivate" for a deactivated user if backend semantics make deactivation terminal.

## Required team UI

Provide:

- team list/search;
- team name;
- description;
- active/archive state;
- stable `team_id` in details;
- member list/count;
- team access intent/defaults.

Real actions:
- create;
- edit name/description;
- archive;
- reactivate archived team where backend permits;
- add/remove members;
- edit team access intent.

## Access intent UX

Expose the four currently implemented capabilities:

- Platform access
- Inference access
- User model selection
- Agent Builder

Keep language explicit:

> Configured for future employee access. Enforcement begins when the employee gateway is enabled.

Show the **effective** resolved result separately from the configured user/team intent.

Do not imply login or employee inference exists.

## API/backend

Reuse the current real loopback API and directory backend. Do not create a second People state model.

If the API lacks detail/list shapes needed by the UI, extend the smallest query projection only.

Add Admin frontend tests for:
- create/edit user;
- suspend/reactivate;
- deactivation behavior;
- create/edit/archive/reactivate team;
- add/remove membership;
- set user intent;
- set team intent;
- read effective access;
- gateway-not-available wording;
- error/refusal rendering.

# 2. EFFECTIVE ACCESS MUST ENFORCE PLATFORM ACCESS AS THE PARENT GATE

Current resolver can produce inconsistent states such as:

```text
platform_access = deny
inference_access = allow
```

when a team grants a downstream capability without a platform grant.

Binding invariant:

> If effective platform access is denied, every downstream future employee capability is denied.

Required resolution order:

1. inactive/suspended/deactivated user -> deny all;
2. resolve effective platform access;
3. if platform access != allow -> deny inference/model-selection/agent-builder regardless of subordinate grants;
4. otherwise resolve each subordinate capability using the documented precedence.

Preserve conservative default-deny.

The currently documented precedence may remain:

`user deny > user allow > team grant > default deny`

but make it deterministic and test it.

## Provenance

Current `EffectiveAccess.provenance` is one scalar that can be overwritten while resolving several different capabilities and may misrepresent why individual results occurred.

Correct this before future gateway work.

Preferred:
- per-capability provenance fields/map, or
- another typed representation that truthfully explains the source of each resolved capability.

Do not leave one ambiguous global provenance if capabilities were resolved by different rules.

This is a candidate contract change before promotion, so evolve schema/fingerprint cleanly.

Tests must cover:

- no intents -> deny all;
- team inference allow but platform deny/default deny -> deny all downstream;
- team platform + inference allow -> both allow;
- user inference deny overrides team inference allow;
- user allow overrides absence of team grant;
- suspended/deactivated user -> deny all;
- archived team contributes no grant;
- multiple active teams resolve deterministically;
- provenance identifies the actual rule for each capability.

# 3. DO NOT RESURRECT ALREADY-FROZEN EVENT TRIGGERS WHILE A REPORT IS AWAITING ACK

Current ACK-owned source cursor is correct, but `tick()` still calls `_scan()` and `_observe()` while an outbox report is queued.

Because the authoritative journal/baseline cursor intentionally has not advanced yet, the scan can rediscover events already included in the frozen report and add their trigger reasons back into `pending`.

After ACK, that stale pending reason can cause a redundant event-trigger report even though there was no new material event.

Required semantics:

- one outstanding frozen report remains;
- events/usage/state changes occurring after its frozen boundary are never lost;
- reasons already represented in the queued report are not resurrected simply because ACK has not happened yet;
- after ACK, genuinely new events/state changes are detected and reported.

Prefer the simplest safe implementation.

A good option is:
- while a report is queued, do not re-run trigger discovery against the unadvanced ACK cursor;
- local journal/usage keeps accumulating;
- after ACK advances to the frozen boundary, the next scan naturally sees only later events;
- state observation after ACK compares current state to the ACKed report baseline and catches later state changes.

If Cursor chooses another design, prove that trigger discovery has an independent proposed cursor and cannot duplicate or lose events.

Add tests:

1. material event -> compose frozen report -> failed send/retries -> same event reason is not re-added;
2. ACK -> no redundant report if nothing new happened;
3. a new event appended while first report is queued is detected after ACK and causes the next report;
4. a model/runtime/SAFE state change while queued is detected after ACK;
5. usage accumulated while queued appears in the next post-ACK report.

# 4. PRESERVE ACCEPTED TELEMETRY/CADENCE WORK

Do not regress:

- development profile = 120 seconds;
- production profile = 21,600 seconds;
- central `kernel.cadence` policy;
- epoch-aligned stable phase;
- event/test reports do not move periodic schedule;
- ACK-owned cursors;
- exact report-id ACK;
- delivered_at truth;
- gap reconciliation;
- one outstanding report;
- machine auth/TLS;
- no Online/Offline claim;
- no customer content export;
- real-clock local soak.

# 5. PRESERVE PEOPLE PRIVACY / BOUNDARY

Do not regress:

- `directory.sqlite` customer-local authority;
- no People PII in telemetry/Command Center/support snapshot;
- no passwords;
- no employee login;
- no employee inference gateway;
- no chat/LibreChat;
- no Agent Builder implementation;
- no RAG;
- directory audit uses safe IDs rather than email/name in vendor-exportable data.

# 6. PEOPLE ACTIVITY

Ensure the Admin Activity surface can render the directory actions already recorded, and where practical resolve local user/team ids to friendly names **locally in the UI/API only**.

Do not alter vendor telemetry to include those names/emails.

Required directory action visibility:
- user.created;
- user.updated;
- user.status_changed;
- team.created/updated/archived/reactivated;
- membership.added/removed;
- access_intent.changed.

# 7. SERVER-TEST READINESS

Preserve the accepted playbook/preflight/evidence layout.

Do not execute paid/external server tests.

No RunPod.

The acceptance playbook should be updated if People UI steps need adjustment after this correction.

# 8. QA

Run all prior v0.3 gates plus focused corrections.

Backend:
- full `tests/machi`;
- `tests/acceptance_lab`;
- effective-access parent-gate tests;
- per-capability provenance tests;
- queued-trigger non-resurrection tests;
- post-ACK new-event detection tests;
- privacy negative tests;
- migration/schema fingerprint;
- ruff;
- mypy strict.

Admin frontend:
- People CRUD/status;
- user edit/deactivate;
- team edit/archive/reactivate;
- membership;
- user/team access intent;
- effective access;
- enforcement-readiness;
- empty/error/refusal states;
- activity integration;
- Vitest;
- tsc;
- Vite production build.

Command Center:
- existing tests/typecheck/build;
- verify no People fields introduced.

Run the development real-clock soak again if telemetry logic changes.

Wheel build + isolated verify.

# 9. TERMINAL STATUS

Only return:

`RUKAN_V0_3_FUNCTIONAL_LOCAL_PASS_SERVER_TEST_READY`

after these corrections pass.

Paste back:

A. status  
B. final SHA  
C. People UI functionality  
D. People API changes  
E. effective-access parent-gate semantics  
F. per-capability provenance  
G. queued-trigger correction  
H. post-ACK new-event evidence  
I. privacy evidence  
J. Admin Activity evidence  
K. focused tests  
L. full QA/build/soak  
M. server-test readiness status  
N. known limitations  
O. git state  
P. STOP

Then STOP for Lead review.

# END INSTRUCTION
