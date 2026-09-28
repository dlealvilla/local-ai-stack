# CURRENT LEAD DEVELOPER INSTRUCTION

Instruction ID: `RUKAN-CONNECTED-MONITORING-V0.3-001`  
Status: `AUTHORIZED_IMPLEMENTATION_WITH_BOUNDED_ARCHITECTURE_REVIEW`  
Canonical baseline: `machi` at `d38a8e855f099f353e1ac090b990014eed67a826`  
Product: **Rukan**  
Internal package namespace remains: `machi`  
Implementation branch: `rukan/connected-monitoring-v0.3`

This is the next major productisation increment.

The objective is no longer merely to render the Stage-1 spine. The objective is to stand up a **functional, accountable Rukan system** in which:

1. customer deployments record truthful non-content usage and operational changes;
2. those deployments automatically send bounded operational reports;
3. the business/vendor Command Center receives and aggregates them;
4. the customer Admin UI becomes a useful AI operations cockpit;
5. the Command Center becomes a useful deployment portfolio/product-intelligence surface;
6. the system remains one-way and privacy-preserving: monitoring without remote control.

The desired end-to-end loop is:

```text
CUSTOMER RUKAN
  operational state
  event journal
  usage records
  support snapshot
       |
       | durable local outbox
       | scheduled + event-triggered report
       v
HTTPS one-way telemetry intake
       |
       v
COMMAND CENTER
  accepted reports
  deployments
  activity
  usage
  models
  support/product analytics
```

No RunPod/GPU physical qualification is required for this increment.

---

# 0. CURSOR DESIGN REVIEW — REQUIRED BEFORE IMPLEMENTATION

Before editing product code, inspect current repository truth and perform a short explicit architecture/product review.

Read at minimum:

- `docs/PRODUCT_VISION.md`
- `docs/machi/ARCHITECTURE.md`
- `docs/machi/ROADMAP.md`
- `docs/machi/TELEMETRY.md`
- `docs/machi/RUKAN.md`
- `docs/machi/RUKAN-ADMIN.md`
- `docs/machi/RUKAN-COMMAND-CENTER.md`
- `docs/machi/RUKAN-ANALYTICS.md`
- current Block 0 EventRecord/journal
- current Block 5–9 contracts/services
- current Admin API/application
- current Command Center SQLite hub
- current analytics export/bundle
- current native and Ollama inference completion paths
- current model catalog/warehouse/qualification/selection contracts
- current capacity/plan/selection contracts

Write/update a design note:

`docs/machi/RUKAN-CONNECTED-MONITORING-V0.3.md`

The review must explicitly address:

- product vision alignment;
- what Rukan owns versus what transport/runtime providers own;
- privacy boundary;
- security boundary;
- data authority;
- failure behavior;
- transport semantics;
- usage accounting;
- UI information architecture;
- what is genuinely implementable now versus future.

## Bounded architecture discretion

Cursor is explicitly allowed to **challenge, modify, rename, split, or simplify** the exact implementation proposed below if repository truth or a clearly stronger design demands it.

However:

- explain every material deviation;
- preserve the required product outcomes and invariants;
- do not silently broaden scope;
- do not introduce a mandatory cloud/vendor dependency without a Product Vision / Industry Solution Selection review;
- do not change the meaning of Stage-1 contracts merely to make UI/telemetry easier.

If a material strategic choice remains that cannot responsibly be selected without Lead input, stop only that subpart with a precise `DECISION_REQUIRED_...` state while completing all noncontroversial work.

Do not use this discretion to challenge away:
- automatic reporting;
- six-hour periodic cadence;
- material-event triggered reporting;
- machine-authenticated secure upload;
- durable outbox/retry;
- non-content usage accounting;
- useful Admin and Command Center product surfaces.

---

# 1. PRODUCT SEMANTICS — HEARTBEAT IS NOT ONLINE STATUS

The user wants a "heartbeat" every six hours and after material actions.

Use that product language if useful, but preserve the semantic distinction:

> A heartbeat is a scheduled **Operational Report** from a deployment.  
> It is evidence that a report was generated and accepted at a time.  
> It is NOT yet proof that the deployment is currently Online, Offline, Healthy, Unhealthy, or available.

Command Center may display:

- Last report received;
- report age;
- expected report cadence;
- report sequence;
- trigger reason;
- latest reported deployment state;
- "report later than scheduled" where useful.

It must NOT display or infer:

- Online;
- Offline;
- Currently healthy;
- Last seen;
- uptime SLA;
- availability percentage.

Those need a later explicit liveness/availability model.

---

# 2. REPORT CADENCE

Default periodic report interval:

**6 hours**

Implement bounded jitter so future fleets do not synchronize on the same second.

Recommended default jitter:
- deterministic per deployment;
- within roughly 0–15 minutes;
- stable enough to test.

Do not use randomness in persistent identity or report semantics.

Periodic reports must be generated even when there were no material state changes, so the business can see continued reporting activity and cumulative usage counters.

The interval may be represented in settings, but the default product behavior is six hours.

If allowing manual cadence override, bound it conservatively (for example 1–24 hours), make AUTO/default return to 6 hours, and persist/emit the change. Do not make arbitrary sub-minute reporting possible.

---

# 3. MATERIAL EVENT TRIGGERS

In addition to the six-hour cadence, request an immediate/coalesced report after material operational changes.

At minimum map current active Rukan evidence/events for:

## Deployment lifecycle

- serving/deployment reaches READY;
- serving/deployment transitions to STOPPED;
- reservation is released after stop;
- serve/start fails;
- admission is rejected for a planned deployment;
- deployment plan becomes stale/replaced where current events support it;
- reconciliation discovers a material mismatch;
- Witness becomes contradictory or failed.

## Foundation/runtime

- active Foundation/runtime/macropath selection changes;
- AUTO selects a different approved macropath;
- fallback to Ollama occurs under existing policy;
- verified runtime generation changes;
- Rukan software/build/version changes.

## Models

- active model selection changes;
- model artifact is acquired/imported/removed where those actions exist;
- provider model/digest used by the active deployment changes;
- model qualification result changes in a way that affects deployability;
- concrete active model variant changes.

## Capacity/configuration

Where active settings/contracts actually exist:

- context length;
- runtime/platform concurrency;
- replica count;
- placement/device;
- resource reserve/headroom;
- memory/VRAM/unified-memory allocation choice;
- AUTO/MANUAL selection mode;
- manual override value or return-to-AUTO;
- selected storage/model/runtime location only as safe non-path identity/fingerprint;
- material SAFE capacity change after rediscovery/recharacterization.

## Telemetry configuration

- telemetry enabled/disabled;
- endpoint changes;
- cadence changes;
- machine credential created/rotated/revoked;
- export privacy policy version changes.

## Do NOT trigger deployment telemetry for

- theme;
- UI density;
- dashboard filters;
- sort order;
- local browser preferences;
- Command Center local aliases/tags;
- purely presentational settings.

### Coalescing

A deploy operation can emit several events in seconds.

Do not upload five separate reports for:

Plan → Admit → Serve Started → READY.

Use a short bounded debounce/coalescing window and send the resulting stable state with all new events.

A target around 30–60 seconds is acceptable if it keeps the implementation simple.

Critical failure may request a prompt flush, but local operation must never wait for the network.

---

# 4. LOCAL TELEMETRY AGENT / SCHEDULER

Automatic reporting must run independently of the browser tab.

The browser UI must not own scheduling.

Prefer the smallest repository-consistent long-running local component.

Strong default:

- Rukan Admin backend/local service remains the customer-local long-running service;
- when telemetry is configured/enabled, it owns or composes a `TelemetryAgent`;
- the agent observes durable local state/journal/usage records;
- it periodically evaluates whether a report is due;
- it notices material trigger events;
- it writes a durable report into a local outbox;
- a sender attempts delivery asynchronously;
- browser open/closed state is irrelevant.

If repository truth strongly favors a separate small process, Cursor may choose it, but do not invent a large daemon framework.

The telemetry agent must not become authority for:
- ResourceManager;
- Plan;
- Serve;
- Foundation;
- Model;
- Capacity.

It observes and exports.

---

# 5. DURABLE OUTBOX — NON-NEGOTIABLE

Telemetry failure must never block:
- inference;
- deployment;
- stop;
- release;
- local Admin use.

Use a durable deployment-local outbox.

Required semantics:

1. report is composed from local truth;
2. canonical bytes are written durably before network send;
3. sender attempts upload;
4. server returns an acknowledgement for the stable report id;
5. only after acknowledgement is the report considered delivered;
6. local export cursor/sequence may advance;
7. failed reports remain queued;
8. retry uses bounded exponential backoff;
9. restart preserves the queue.

Delivery model:

**at-least-once + server idempotency**

Do not attempt distributed exactly-once semantics.

The server must safely accept retransmission of the exact same report id.

Bound the outbox so a long outage cannot fill customer storage indefinitely.

A conservative retention/maximum-size policy must be explicit and testable. If old reports must be compacted, do so only after preserving cumulative usage/state required to resume accountability.

---

# 6. SECURE UPLOAD: NO HUMAN AUTH YET, MACHINE AUTH REQUIRED

The user does not want a human authentication/tenancy system yet.

That is acceptable.

However, automatic Internet upload **cannot be unauthenticated**.

This increment must implement minimal machine-to-machine deployment authentication.

## Initial security model

Preferred simple v0.3 model:

- HTTPS;
- one high-entropy telemetry upload credential per deployment;
- stable key id;
- credential bound to one `install_id`;
- deployment presents the credential on upload;
- receiver verifies it before parsing/importing the report;
- receiver stores only a verifier/hash where practical;
- credential can be rotated/revoked;
- credential is never included in EventRecord, analytics bundle, Command Center analytics, logs or screenshots.

A long random bearer token over mandatory TLS is acceptable as the default if implemented carefully.

Do not build OAuth/OIDC/human sessions merely for this.

If Cursor proposes request signing/HMAC instead, it must show why the added complexity materially improves the current threat model.

mTLS may remain a future stronger option unless repository/product reality clearly favors it now.

## One-time pairing

Provide a simple manual bootstrap/pairing path.

Because no tenant/account system exists yet, it is acceptable for v0.3 to require one one-time operator step per deployment.

Preferred flow:

1. deployment has a resolved `install_id`;
2. Command Center local UI/CLI creates an upload key bound to that install id;
3. secret is shown exactly once;
4. operator configures that endpoint/key/secret in customer Rukan Admin Settings or a local credential command;
5. subsequent reporting is automatic.

Support credential rotation/revocation.

Do not require the business operator to repeatedly move report files once paired.

## Credential storage

Inspect current secret-handling seams.

If none exist, add the smallest Rukan-owned secret adapter.

Requirements:

- secret does not live in ordinary operational entity JSON;
- secret is not journaled;
- secret is not exportable;
- restrict file permissions where the host supports it;
- clear typed warning/refusal when permissions cannot meet the minimum policy;
- never return the secret from a read API after initial creation/configuration.

Do not pretend a general enterprise secrets vault exists.

---

# 7. TLS / EXTERNAL INTAKE SURFACE

Rukan Command Center UI/control APIs remain loopback-local.

Automatic deployment uploads need a separately bounded intake surface.

Prefer a **separate handler/server surface** even if it runs in the same process.

External intake must expose only the smallest write API required for telemetry.

Conceptually:

`POST /v1/telemetry/reports`

It must NOT expose:
- deployment mutation;
- ResourceManager;
- Serve start/stop/release;
- model acquisition;
- filesystem access;
- shell;
- Command Center read APIs;
- customer Admin APIs.

## TLS rule

- non-loopback intake: HTTPS required;
- plaintext HTTP permitted only in explicit loopback/local-test mode;
- fail closed if asked to expose a non-loopback plaintext intake.

Cursor may choose:
- direct Python TLS with operator-supplied certificate/key; or
- a clearly documented standard TLS-terminator boundary if this better fits repository/product packaging.

Do not make a third-party reverse proxy a mandatory Rukan ontology/dependency.

If a material Industry Solution Selection decision remains, document it.

## External deployment acceptance

Implement the complete secure transport locally regardless.

Then inspect whether the development environment has sufficient owned external endpoint configuration to perform a real remote HTTPS acceptance.

Do not invent a public domain, certificate, cloud account or credentials.

If no externally reachable owned endpoint is available, complete the local secure implementation and return the exact remaining external inputs required.

That absence must not be disguised as an end-to-end Internet PASS.

---

# 8. TELEMETRY REPORT CONTRACT

Introduce a versioned Rukan-owned transport/report contract.

Name may differ if repository conventions demand it, but conceptually:

`rukan.operational_report@1`

It is transport evidence, not operational authority.

At minimum include:

- report schema/version;
- report id;
- install id;
- report sequence;
- generated_at UTC;
- trigger reasons (periodic, deployment_ready, deployment_stopped, settings_changed, etc.);
- Rukan version/build/source commit;
- previous acknowledged report id or equivalent continuity evidence;
- window start/end for incremental data;
- export/privacy policy version;
- latest safe support/deployment summary;
- incremental safe operational events since the last acknowledged cursor;
- inference usage rollups/records for the report window;
- cumulative usage counters sufficient to detect gaps;
- included record counts;
- data-source/provenance information;
- optional warning that some metrics are not recorded.

Do not send:
- prompt;
- response;
- messages;
- documents;
- RAG content;
- proprietary file contents;
- credentials;
- secrets;
- absolute paths;
- unrestricted logs.

Use stable ids and explicit unresolved/not_recorded states.

Receiver validates:
- auth;
- size;
- schema;
- install/key binding;
- report id;
- sequence shape;
- privacy;
- record counts;
- internal install identity consistency.

Unknown future additive fields may fail soft only where schema policy explicitly permits them.

---

# 9. REPORT SEQUENCE / ACK / GAP ACCOUNTABILITY

We need accountability from both ends.

Each deployment maintains report sequence/cursor state.

Receiver records:

- report id;
- install id;
- sequence;
- generated_at;
- received_at;
- trigger reasons;
- source Rukan version;
- credential key id;
- acceptance result;
- report/body digest;
- dataset counts.

Receiver must identify:
- exact duplicate report;
- unexpected sequence gap;
- out-of-order older report.

Do not reject useful historical data solely because it arrived late; preserve it with clear sequence/gap evidence.

Command Center should surface:
- Last report received;
- report sequence;
- gap detected / no gap known;
- trigger reason;
- accepted/rejected report history.

Again: sequence gaps are telemetry gaps, not proof the deployment was offline.

---

# 10. ACTIVE INFERENCE USAGE RECORD — IMPLEMENT NOW

The current Stage-1 `InferenceProof` is not sufficient as the long-term product usage model.

Create a Rukan-owned non-content inference usage contract.

Do not import the historical Kultrun contract wholesale without reviewing semantics.

A suitable v1 should preserve at minimum:

- `usage_id`;
- request/correlation id;
- occurred_at UTC;
- source/purpose;
- instance id;
- plan/reservation/foundation generation where currently resolvable;
- model identity and identity kind;
- runtime/macropath/provider;
- outcome;
- typed error/failure class;
- HTTP/protocol status if applicable;
- input tokens: resolved or not_recorded;
- output/completion tokens: resolved or not_recorded;
- latency at the Rukan request boundary;
- optional runtime-reported duration if distinct and available;
- Rukan build/version provenance if useful.

Never store:
- prompt text;
- generated text;
- raw request body;
- raw response body.

## Purpose/source is critical

At minimum distinguish:

- `operator_test` — Admin inference tester;
- `acceptance_probe` — product/qualification/proof request;
- `user_request` — reserved for future employee/gateway traffic;
- other explicit source only if repository truth requires it.

Admin test traffic must not silently appear as employee adoption.

Acceptance probes must not inflate customer inference usage.

## Current runtime token extraction

Where runtime responses already report token counts, capture them truthfully.

### Native/vLLM OpenAI-compatible path

Current completion responses may expose:
- prompt/input token count;
- completion/output token count.

Capture both when present.

### Ollama provider path

Current provider responses may expose:
- `prompt_eval_count`;
- `eval_count`.

Capture them as input/output tokens when present.

Unknown remains not_recorded.

Do not estimate tokens from string length.

## Latency

Measure wall-clock elapsed time at the Rukan-owned request boundary for all supported requests.

This creates a real persisted historical latency metric.

Do not call it TTFT.

TTFT remains not recorded unless a streaming/runtime-specific metric is later implemented.

---

# 11. USAGE PERSISTENCE AND AGGREGATION

Usage records must be durable and locally queryable.

Use the smallest repository-consistent persistence model.

Requirements:

- append/non-destructive history;
- stable usage id;
- crash-safe enough for telemetry/accounting;
- request recording failure must not fail the user response;
- recording failure must emit bounded observability evidence where feasible;
- no prompt/response.

Local Admin should be able to aggregate by:
- time range;
- model;
- runtime/macropath;
- purpose/source;
- outcome.

At minimum support:
- requests;
- success/failure;
- input tokens total where reported;
- output tokens total where reported;
- token sample coverage;
- average latency;
- latency sample count;
- failure classes.

If percentile/histogram infrastructure does not already exist, do not fake p95.

---

# 12. WHAT EACH SIX-HOUR / EVENT REPORT SENDS FOR USAGE

Do not resend unlimited raw history every six hours.

Preferred vendor payload is a bounded incremental usage export plus cumulative safety counters.

At minimum send per report window, grouped as practical by:
- model identity/family where exact grouping exists;
- runtime/macropath;
- purpose/source;
- outcome.

Measures:
- request count;
- successful count;
- failed count;
- input tokens total + sample count;
- output tokens total + sample count;
- latency sum/count/min/max where truthfully recorded;
- failure-class counts.

If sending request-level non-content usage rows is simpler for v0.3, it is permissible within bounded volume/privacy limits, but Command Center should primarily present aggregates.

Include cumulative lifetime or rolling counters sufficient to identify a missed telemetry window without inventing data.

Do not send raw prompt/response.

---

# 13. LOCAL ADMIN ACTION ACCOUNTABILITY

Human identity is not implemented.

Do not invent it.

But we can still record **actor origin**.

For Admin actions/settings changes going forward, record a bounded source such as:

- local_admin_ui;
- local_cli;
- system_auto;
- scheduler;
- telemetry_agent;
- migration/reconciliation.

Where an operation already has an event, add actor-origin only if contract evolution can be done safely.

Otherwise create a bounded admin/action audit event/projection that references the affected entity/action.

Do not duplicate authoritative domain events.

Settings-change evidence must never contain credential secrets.

Command Center may receive vendor-safe action/event projections where allowed.

UI wording should say:
- Source: Admin UI
- Source: CLI
- Source: AUTO

not:
- User Daniel
- Administrator Alice

until real identity exists.

---

# 14. CUSTOMER RUKAN ADMIN — PRODUCT PURPOSE

Rukan Admin is not a developer dashboard.

It is the customer's **AI operations cockpit**.

The normal business/IT administrator should quickly understand:

1. Is Rukan ready to provide AI?
2. What AI capability/models do we currently have?
3. What is running?
4. How much is it being used?
5. Is anything failing or requiring attention?
6. What resources/headroom do we have?
7. What changed recently?
8. Is monitoring/reporting working?
9. What safe settings can I change?

Technical detail stays available through progressive disclosure.

---

# 15. ADMIN INFORMATION ARCHITECTURE — REASSESS AND IMPROVE

Cursor may refine exact navigation, but the resulting product should cover these concepts.

Recommended primary navigation:

- Overview
- Models
- Deployment
- Inference
- Analytics
- Activity
- System
- Settings

Do not add pages with no real backend truth.

If Activity fits better as a tab under Analytics/Deployment, Cursor may combine it, but accountability must remain easy to find.

---

# 16. ADMIN OVERVIEW — KEEP IT INTERESTING, NOT DENSE

Do not put every metric or setting on the main dashboard.

The Overview should be visually engaging and business-readable.

Recommended hierarchy:

## A. Readiness hero

Derived from real Witness/current chain.

Examples:
- Ready to serve AI
- Running with limitations
- Needs attention
- Deployment incomplete

Never synthetic 87/100 health scores.

## B. Active intelligence

Show the currently active model as a strong visual card:
- family/display name;
- concrete variant;
- runtime/macropath;
- context/concurrency where known;
- running state;
- qualification badge;
- current reported usage summary.

## C. Usage at a glance

When real usage records exist:
- requests in selected recent period;
- output tokens generated;
- input tokens where reported;
- success/failure;
- average latency with sample count.

Default a useful period such as last 24h/7d.

Clearly distinguish:
- operator tests;
- acceptance probes;
- future user requests.

## D. Capacity/headroom

Show SAFE resource capacity and selected/reserved requirements.

Do not show utilization if not measured.

Use language such as:
- SAFE GPU memory
- reserved by current deployment
- planning headroom

rather than fake GPU utilization.

## E. Recent activity

A small list:
- deployment READY;
- model changed;
- settings changed;
- stopped;
- report uploaded;
- relevant failures.

## F. Monitoring status

- reporting enabled/disabled;
- last successful report;
- next scheduled report;
- queued reports;
- last upload error if any.

Quick actions may include:
- Test inference;
- Browse models;
- View deployment;
- Open monitoring settings.

---

# 17. ADMIN MODELS — NETFLIX-LIKE MODEL LIBRARY

This is a major UX direction.

The user wants models to feel more like browsing a streaming library than reading infrastructure inventory.

Implement a visually rich model library using real catalog/warehouse/qualification metadata.

## Presentation hierarchy

Treat as UI grouping, not ontology:

### Series / Family
Examples:
- Qwen
- Llama
- Gemma
- Mistral

### Generation / Release line
Examples:
- Qwen 2.5
- Qwen 3

### Variant / Edition
Concrete deployable identity:
- parameter size;
- instruct/base;
- quantization;
- format;
- context capability;
- runtime-specific artifact/provider digest.

Cursor may use labels such as Series → Generation → Variants instead of literal Season/Episode if that is clearer for business administrators.

The visual behavior may still resemble streaming-service rows/cards.

## Critical invariant

Never group by guessing from arbitrary free text if exact metadata is unavailable.

Never collapse two artifacts/digests into one backend identity.

The card is a projection over exact Rukan identities.

## Useful rows/collections where truth exists

- Running now
- Installed
- Recommended for this host
- Compatible with this host
- Available to acquire
- Recently used
- Model families

Do not show "Recommended" unless a real Rukan recommendation exists.

Do not fake a marketplace if global discovery is not implemented.

## Model card/detail

Show only real facts:
- family/display name;
- generation;
- parameter class where known;
- quantization/format;
- installed/acquired state;
- running state;
- qualification;
- supported runtime/macropath;
- context;
- expected/required memory/storage;
- SAFE fit/headroom;
- local usage requests/tokens;
- exact artifact/digest in technical details.

Allow variants to be compared visually.

Actions only if real:
- acquire/import;
- select;
- deploy;
- stop;
- remove.

If a safe end-to-end action is not currently available, do not fake it.

---

# 18. ADMIN ANALYTICS

Upgrade the existing Analytics page using the new usage record.

Recommended real views:

## Time range
- 24 hours
- 7 days
- 30 days
- all retained

## Summary
- requests;
- successful;
- failed;
- input tokens reported;
- output tokens generated;
- average latency;
- token/latency sample coverage.

## By model
- requests;
- tokens;
- failures;
- average latency.

## By purpose
- operator test;
- acceptance probe;
- future user request.

## By runtime/macropath
- native/vLLM;
- Ollama.

## Failures
- typed error class distribution;
- recent failed requests.

## Deployment/lifecycle activity
Keep operational-event analytics distinct from inference usage.

Do not add cost until cost exists.

Do not add user/team breakdown until identity exists.

---

# 19. ADMIN ACTIVITY / ACCOUNTABILITY

Provide an easy-to-read local activity timeline.

Examples:
- model selected;
- deployment planned;
- resources admitted;
- serving READY;
- inference failed;
- deployment stopped;
- reservation released;
- telemetry settings changed;
- report successfully uploaded;
- report upload failed;
- Rukan version changed.

Each row should show:
- timestamp;
- action;
- outcome;
- actor origin where known;
- affected model/deployment;
- technical detail disclosure.

Do not expose secrets or absolute paths.

---

# 20. ADMIN SYSTEM

Keep System focused on the machine and resource truth:

- OS/architecture;
- CPU/memory;
- accelerators;
- storage/mounts;
- SAFE capacity;
- reserved resources;
- current execution foundation;
- current Rukan build;
- qualification coverage.

Distinguish:
- observed;
- reported;
- SAFE;
- reserved;
- unresolved.

Do not turn this page into the main business dashboard.

---

# 21. ADMIN SETTINGS — MAKE IT REAL

Add a real Settings surface.

At minimum implement Monitoring/Privacy settings necessary for this increment:

- telemetry reporting enabled;
- endpoint URL;
- credential key id/status;
- six-hour cadence/default;
- next report;
- data categories sent;
- explicit "prompts/responses/documents are never sent";
- Send test report now;
- rotate/configure credential flow;
- last successful upload;
- queued report count.

For deployment/model/performance settings:

Audit repository truth and expose controls only when a safe bounded mutation seam exists.

Candidates that may warrant UI controls when current architecture supports them:
- selection AUTO/MANUAL;
- model selection;
- context length;
- concurrency;
- replica count;
- placement/device;
- reserve/headroom;
- runtime/foundation choice from verified feasible set.

Every such change must:
1. stay within platform-approved feasible bounds;
2. invalidate/recompute dependent state;
3. revalidate the whole configuration;
4. update DeploymentPlan;
5. remain subject to ResourceManager;
6. emit settings/action evidence;
7. trigger an Operational Report after stable recomputation.

If this backend seam does not yet exist for a candidate control, show the current value read-only or omit it. Do not create a frontend-only setting.

Keep advanced controls off the Overview.

---

# 22. COMMAND CENTER — PRODUCT PURPOSE

Rukan Command Center is the business/vendor **deployment portfolio and product intelligence** surface.

It should answer:

1. What Rukan deployments do we know about?
2. When did each deployment last report?
3. What version/hardware/runtime/model was last reported?
4. What changed?
5. Did deployment/start/stop/configuration actions succeed?
6. How much inference activity is occurring?
7. Which models/runtimes/hardware are actually being used?
8. Where are failures concentrated?
9. Which deployments have reporting gaps or old software?
10. Is the telemetry intake itself working correctly?

It must not become customer-host authority or remote control.

---

# 23. COMMAND CENTER OVERVIEW

Design a clear portfolio homepage.

Truth-backed top-level measures may include:

- known deployments;
- reports received in last 24h / 7d;
- deployments with a report in the expected 6h window;
- deployments whose **report age exceeds expected cadence**;
- Rukan version distribution;
- latest reported macropaths;
- latest reported model families;
- inference requests in selected period;
- output tokens generated in selected period;
- deployment/start failures;
- telemetry rejected reports.

Wording must remain report-centric.

Allowed:
- "Report received 2h ago"
- "No report for 14h"
- "Reporting later than scheduled"

Not allowed:
- "Offline"
- "Unhealthy"

Do not overwhelm the Overview.

Detailed charts belong in Analytics.

---

# 24. COMMAND CENTER DEPLOYMENTS

The deployment list should become the primary portfolio table.

Columns/fields where available:

- local friendly alias/tag;
- install id;
- last report received;
- report age;
- report cadence status;
- latest reported Rukan version;
- host/accelerator;
- macropath/runtime;
- active model;
- latest reported serving/deployment state;
- Witness;
- recent inference volume;
- latest material change.

Friendly alias is Command Center-local metadata only.

Do not export it back to the customer unless a later explicit feature does so.

Allow useful filters:
- version;
- accelerator;
- runtime/macropath;
- model family;
- Witness;
- report freshness;
- latest reported deployment state.

---

# 25. COMMAND CENTER DEPLOYMENT DETAIL

Recommended sections/tabs:

## Summary
Latest reported deployment snapshot.

## Activity
Material event/action timeline.

## Usage
Requests/tokens/latency/failures over time.

## Models
Current model plus historical model variants seen/used on the deployment.

## System
Hardware/capacity/runtime/build at latest report.

## Reports
Report history:
- received_at;
- generated_at;
- sequence;
- trigger reasons;
- schema;
- dataset counts;
- gap evidence;
- credential key id;
- accepted/rejected.

## Support
Existing structured support/Witness evidence.

Everything is "latest reported" or historical evidence, not a live control surface.

---

# 26. COMMAND CENTER ANALYTICS

Upgrade cross-deployment analytics.

Truth-backed views should include:

## Deployment/product
- deployment count;
- Rukan version distribution;
- OS/architecture;
- accelerator models;
- runtime/macropath distribution;
- Witness outcomes;
- deployment/start failure types;
- model qualification/fallback evidence where available.

## Usage
- request count by time;
- output tokens generated;
- input tokens reported;
- average latency/sample coverage;
- success/failure;
- usage by model;
- usage by runtime;
- operator_test vs acceptance_probe vs future user_request.

## Models
Create a cross-deployment "Model landscape":
- family;
- generations/variants;
- number of deployments last reporting the model;
- installed/used count where evidence exists;
- requests;
- input/output tokens;
- average latency;
- failure count.

This can use the same streaming-card visual language in a business-analytics way, but it should answer fleet/product questions rather than act as a marketplace.

---

# 27. COMMAND CENTER REPORTING / INTAKE ACCOUNTABILITY

Add a Reporting/Intake surface.

Show:

- intake configured;
- TLS mode;
- endpoint/public URL when configured;
- deployment upload credentials/key ids;
- credential status/revoked;
- accepted reports;
- rejected reports;
- rejection reasons;
- duplicate reports;
- sequence gaps;
- schema versions;
- reports by trigger reason;
- recent intake errors.

Do not show credential secrets after creation.

This surface is essential for diagnosing whether monitoring itself works.

---

# 28. COMMAND CENTER SETTINGS

Keep business-side settings separate from customer deployment settings.

Implement real settings only:

- intake bind/port configuration where product packaging allows;
- configured public intake URL;
- TLS/certificate status (never private-key content);
- credential issue/rotate/revoke;
- local deployment aliases/tags;
- local analytics retention if implemented;
- Command Center data location/status;
- export/download of Command Center analytics if easy and safe.

No remote deployment mutation.

---

# 29. TELEMETRY RECEIVER STORAGE

Extend Command Center SQLite in a versioned migration.

Add concepts equivalent to:

- telemetry credentials / key verifier;
- operational reports;
- report trigger reasons;
- accepted/rejected receipt evidence;
- report sequence/gap state;
- usage rollups or imported usage rows;
- local deployment aliases/tags if implemented.

Keep current:
- deployments;
- snapshots;
- events;
- inference/usage facts;
- sources/rejections.

Preserve stable source identities.

Use WAL/concurrency settings if appropriate for simultaneous loopback UI + intake writes.

Use transactions.

Do not turn SQLite into local deployment authority.

---

# 30. PRIVACY POLICY

Hard invariant.

Never send to Command Center:

- prompts;
- responses;
- messages;
- document text;
- RAG chunks;
- customer files;
- credentials;
- secrets;
- raw API request body;
- raw API response body;
- arbitrary logs;
- absolute filesystem paths;
- customer_content EventRecords.

Prefer aggregate non-content usage.

Operational event payloads remain explicit allow-list projections.

The Admin UI must provide an inspectable explanation of what is sent.

Add a "Preview next report" function if it can be implemented safely and clearly without exposing secrets.

This would be valuable for trust.

---

# 31. FAILURE / RETRY BEHAVIOR

Telemetry is supporting infrastructure.

If upload fails:

- local inference continues;
- deployment continues;
- stop/release continues;
- report remains in outbox;
- Admin shows queued count and last error;
- retries back off;
- a later success drains in order where practical.

Do not retry aggressively.

Bound network timeouts.

Do not let report composition scan unbounded customer data.

---

# 32. REPORT SIZE / ABUSE BOUNDS

Set explicit conservative bounds:

- max report body size;
- max event rows per report;
- max usage rows/rollup groups;
- max trigger reason count;
- max string lengths;
- intake rate per credential where simple;
- bounded rejected-body handling.

Reject before expensive parsing when possible.

Do not persist raw rejected secrets/bodies.

---

# 33. MODEL FAMILY/GROUPING METADATA

The visual model experience needs stable metadata.

Audit current model catalog definitions.

If family/generation/variant metadata already exists, use it.

If it does not, add the smallest optional presentation metadata contract owned by Rukan, without rewriting artifact identity.

Candidate optional fields:

- family;
- generation;
- parameter_class;
- variant_label;
- quantization;
- modality;
- role/tuning;
- format.

Unknown stays unknown.

Do not infer important compatibility from these presentation fields.

Do not parse marketing names and then treat the parse as authoritative model semantics.

A display-only conservative parser may be used only if clearly marked inferred and never used for planning/compatibility.

---

# 34. DESIGN LANGUAGE / UX

The Admin UI should feel like a polished local product, not an engineering console.

The Command Center should feel like a calm portfolio/operations product, not a raw telemetry viewer.

Use:

- strong hierarchy;
- large model artwork-style cards or tasteful generated visual treatment without requiring external image services;
- compact badges;
- progressive disclosure;
- clear empty states;
- helpful explanations in business language;
- technical IDs behind details.

Do not use fake stock imagery if it adds no information.

Avoid excessive dashboard tiles.

Use charts only when the data benefits from them.

Respect accessibility:
- keyboard focus;
- semantic headings;
- labels;
- contrast;
- responsive desktop layout.

Do not introduce a heavy design system unless existing frontend reality warrants it.

---

# 35. NO MOCK FUNCTIONALITY RULE

The user wants a functioning product, not visual mock-ups.

Every:
- metric;
- chart;
- badge;
- model card;
- button;
- settings control;
- report status;
- deployment status

must be backed by real implemented Rukan data/actions.

If data does not exist:
- omit it; or
- show explicit not_recorded / not available in this version.

Do not create dummy production data.

Demo/test fixtures are allowed only in clearly labelled tests/demo evidence.

---

# 36. LOCAL PRODUCTION STAND-UP

At completion, build the production frontend assets.

Stand up locally:

## Customer Admin

Backend/local service with production Admin static assets.

Verify:
- Overview;
- Models;
- Deployment;
- Inference;
- Analytics;
- Activity;
- System;
- Settings.

## Command Center

Persistent local service with production Command Center static assets.

Verify:
- Overview;
- Deployments;
- Deployment Detail;
- Analytics;
- Models landscape;
- Reporting/Intake;
- Settings.

Provide exact commands.

If repository/browser tooling already supports screenshots, capture key screens.

Do not add a large browser automation dependency solely for screenshots.

---

# 37. CONNECTED END-TO-END ACCEPTANCE

Create a deterministic local connected acceptance using two separate roots/processes:

A. simulated/fixture-backed customer Rukan deployment using real contracts/services;
B. Command Center/intake using real SQLite and receiver.

Acceptance flow:

1. create/identify install;
2. issue telemetry credential;
3. configure deployment endpoint/credential;
4. generate at least one real supported inference request through Rukan's inference seam;
5. persist usage with token/latency facts;
6. produce a material lifecycle/settings trigger;
7. telemetry agent writes report to outbox;
8. secure upload succeeds;
9. receiver authenticates and acknowledges;
10. Command Center persists report;
11. UI/API shows:
   - deployment;
   - Last report received;
   - trigger reason;
   - activity;
   - usage/request count;
   - output tokens;
   - latency;
   - model/runtime;
12. exact resend is idempotent;
13. bad credential rejected;
14. mismatched install/key rejected;
15. telemetry outage queues report and does not break inference;
16. restart drains queued report;
17. no customer content crosses the boundary.

Use explicit local-test TLS/loopback exception only as defined by product code.

Where feasible, also test direct HTTPS with a local temporary certificate.

---

# 38. REAL EXTERNAL CONNECTED ACCEPTANCE

After local connected acceptance passes, inspect the environment for an owned, explicitly available external HTTPS endpoint/configuration.

Do not guess.

Do not use RunPod for this.

If an appropriate endpoint/domain/certificate is already available to Cursor under project authorization, perform one bounded real-network telemetry acceptance:

deployment/client
→ HTTPS
→ intake
→ Command Center persistence

No customer content.

If the required public endpoint/certificate/firewall inputs are not available, do NOT fabricate a connected external PASS.

Return:

`RUKAN_CONNECTED_MONITORING_V0_3_LOCAL_PASS_EXTERNAL_ENDPOINT_REQUIRED`

and list the exact external inputs needed.

If a real external secure path is completed successfully, use:

`RUKAN_CONNECTED_MONITORING_V0_3_CONNECTED_PASS`

---

# 39. PACKAGING / ALWAYS-ON BEHAVIOR

The code must be suitable for later installer/service registration.

Do not prematurely build OS-specific installers in this increment unless current Rukan packaging already has the seam.

Document:

- which local service must stay running on customer host;
- which Command Center service(s) must stay running;
- which ports;
- which data roots;
- how to restart safely;
- how pending outbox survives.

If easy within current packaging, add simple foreground commands and service-ready exit/signals.

OS boot/login autostart can remain a packaging follow-up if not already available.

---

# 40. ARCHITECTURAL INVARIANTS

Preserve:

- Stage-1 Blocks 0–9 authority;
- one ResourceManager;
- STOP != RELEASE;
- native/vLLM primary;
- Ollama compatibility fallback;
- fallback is control-plane recomputation;
- model catalogs/identities remain distinct by path;
- Admin browser does not select arbitrary runtime endpoint;
- Command Center never becomes local deployment authority;
- telemetry network failure never blocks serving;
- customer content local by default;
- external intake is write-only monitoring, not remote control;
- product-facing name Rukan;
- internal `machi` namespace remains until explicit migration.

---

# 41. NON-GOALS

Do NOT implement in this increment:

- human authentication/login;
- tenant/account hierarchy;
- remote start/stop/release;
- remote shell;
- remote model installation;
- remote settings mutation;
- remote support control;
- Knowledge/RAG;
- Team Brain;
- employee chat product;
- LibreChat/Open WebUI integration;
- licensing/billing;
- Dynamo;
- Runtime Artifact Registry unless a tiny existing seam is required for displayed current runtime facts;
- Kubernetes/fleet scheduler;
- Online/Offline liveness semantics;
- SLA;
- alert paging/on-call system;
- email/SMS notifications;
- cost accounting unless an active cost source already exists;
- user/team inference attribution;
- GPU utilization history unless a real collector is added through a separately justified scope;
- RunPod physical qualification.

---

# 42. DOCUMENTATION / ROADMAP

Update current product docs to reflect the new truth.

At minimum:

- `docs/machi/TELEMETRY.md`
- `docs/machi/RUKAN.md`
- `docs/machi/RUKAN-ADMIN.md`
- `docs/machi/RUKAN-COMMAND-CENTER.md`
- `docs/machi/RUKAN-ANALYTICS.md`
- active Architecture/Roadmap where necessary.

Document:
- report semantics;
- six-hour cadence;
- material triggers;
- machine auth;
- privacy;
- outbox/retry;
- usage accounting;
- UI purposes;
- model-library presentation hierarchy;
- what remains deferred.

Do not rewrite historical evidence.

---

# 43. TESTING

## Usage

Test:
- native input/output token extraction;
- Ollama input/output token extraction;
- missing token fields stay unresolved;
- latency persisted;
- failure usage record;
- no prompt/response in usage record;
- operator_test vs acceptance_probe separation;
- recorder failure does not fail inference;
- restart/readback;
- aggregation by period/model/runtime/purpose.

## Telemetry client

Test:
- six-hour due calculation;
- deterministic jitter;
- event trigger mapping;
- settings trigger mapping;
- debounce/coalescing;
- durable outbox;
- retry/backoff;
- ack advances cursor;
- failed send does not;
- duplicate send safe;
- restart resumes;
- bounded queue/retention.

## Receiver/auth

Test:
- valid credential accepted;
- wrong credential rejected;
- revoked credential rejected;
- install/key mismatch rejected;
- missing TLS/non-loopback fails;
- loopback test mode explicit;
- body size bounds;
- malformed schema;
- report id duplicate;
- sequence gap recorded;
- out-of-order historical report handled safely;
- privacy violations fail closed;
- no raw rejected body persistence.

## Command Center

Test:
- reports persisted;
- report received time;
- latest reported state;
- usage aggregates;
- model aggregates;
- report gap evidence;
- credential issue/rotate/revoke;
- local alias isolation;
- service restart;
- concurrent intake/UI reads;
- schema migration from current v2 analytics hub.

## Admin

Test:
- usage metrics;
- models grouping;
- monitoring settings;
- test report;
- queued/error states;
- action/activity evidence;
- no fake setting action;
- privacy explanation.

## Full regression

Run:
- full `tests/machi`;
- `tests/acceptance_lab`;
- architecture/privacy tests;
- ruff;
- mypy strict;
- Admin frontend tests/typecheck/build;
- Command Center frontend tests/typecheck/build;
- wheel build;
- isolated wheel verification.

No physical GPU host required.

---

# 44. ACCEPTANCE

Minimum LOCAL PASS requires all of:

- active usage record exists and is persisted;
- current Admin inference captures real token/latency facts when runtimes report them;
- usage separates operator tests from acceptance probes;
- six-hour reporting scheduler exists;
- material-event trigger policy exists;
- settings changes that are actually implemented trigger reports;
- durable outbox exists;
- retry/ack/idempotency works;
- machine credential auth exists;
- non-loopback plaintext upload is refused;
- secure intake is write-only;
- Command Center stores report receipt/sequence/trigger provenance;
- Command Center shows Last report received/report age, not online/offline;
- Admin Overview/Models/Analytics/Settings are materially upgraded;
- Netflix-like model library is backed by exact Rukan identities;
- Command Center Overview/Deployments/Analytics/Models/Reporting are materially upgraded;
- no mock production functionality;
- no customer content export;
- full QA passes;
- branch clean and pushed.

External connected PASS additionally requires a real owned HTTPS endpoint acceptance.

---

# 45. PASTE BACK

Return a detailed structured report:

A. exact terminal status  
B. TL;DR  
C. starting/final SHA  
D. branch/worktree/origin  
E. architecture review and deviations from Lead proposal  
F. product-vision alignment  
G. telemetry agent architecture  
H. six-hour scheduler/jitter  
I. event-trigger map  
J. settings-trigger map  
K. durable outbox and retry/ack semantics  
L. report contract/schema  
M. credential/pairing model  
N. TLS/intake architecture  
O. usage record contract  
P. native token capture  
Q. Ollama token capture  
R. latency capture  
S. usage aggregation/reporting  
T. Admin information architecture  
U. Admin Overview  
V. Admin Netflix-like Models experience  
W. Admin Analytics  
X. Admin Activity/accountability  
Y. Admin Settings  
Z. Command Center information architecture  
AA. Command Center Overview  
AB. Deployments list/detail  
AC. Command Center Analytics  
AD. Command Center Models landscape  
AE. Reporting/Intake accountability  
AF. credential management  
AG. privacy/security review  
AH. local connected acceptance  
AI. external connected acceptance or exact missing inputs  
AJ. service/always-on commands  
AK. frontend build/visual evidence  
AL. backend QA  
AM. wheel/build evidence  
AN. schema migrations  
AO. known limitations/debt  
AP. recommended next product increment  
AQ. git state  
AR. STOP

Then STOP for Lead review.

# END INSTRUCTION
