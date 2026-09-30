# Rukan v0.4 user access gateway

Status: implementation on `rukan/user-access-gateway-v0.4`. This is not a
canonical merge.

## Product decision

Rukan's employee inference authority is the User Gateway. LibreChat is the
first workspace adapter. A generic OpenAI-compatible client uses the same
gateway and does not need LibreChat.

```text
enterprise OIDC or Rukan user credential
        |
        +--> LibreChat adapter
        +--> generic client
                |
                v
        Rukan User Gateway
        bind identity, authorize, filter models, account
                |
                v
        authorised READY ServingInstance on loopback
```

Checked against the product vision: self-hosted, prompts stay off the vendor
path, LibreChat is replaceable, and ResourceManager remains the only admission
authority. No solution decision was left open. PyJWT verifies OIDC tokens.
The official MCP shape used here is Streamable HTTP JSON-RPC. LibreChat is
pinned, not imported.

## Workspace adapter

`LibreChatAdapter` is `machi.adapters.rukan.librechat`. It renders config and
a compose file. It does not open LibreChat's database.

Pinned compatibility target. This is a LibreChat pre-release, not a stable
LibreChat release, and it is not a Rukan core dependency:

- version `v0.8.8-rc4`
- commit `361553f3322d7b9bb547d0a9c2c5aaefc2934901`
- image `ghcr.io/danny-avila/librechat@sha256:929f4491cb9a87d6beb02e9e9ce9a54d4ee05bc56b65b1debe5b1f28a327a4fb`

GitHub still marks that tag prerelease. It is the current published release
whose custom-endpoint and MCP headers substitute
`{{LIBRECHAT_OPENID_ACCESS_TOKEN}}` from the live OIDC access token. v0.8.7's
example config does not. An unsigned email header is not accepted.

Capability profile, including what this pin does not do:

- chat, streaming, and OpenAI usage fields: yes
- model list from the gateway: yes
- OIDC access-token header: yes
- direct Serve endpoint: no
- per-user MCP menu: no
- per-user agent ACL: no
- agents: client-local workspace records, not Rukan `AgentDefinition`

## Identity

Approved email is the provisioning key. The first valid token whose email
matches one active user binds `issuer + subject` to that user. Later calls
trust the subject. A changed email is a mismatch, not a new user. A different
subject cannot take over a bound email. Admin reset deletes the binding and
writes an audit row. Bearer tokens are not stored.

API credentials are optional, hashed with scrypt, shown once, and cannot
exceed the user's current access. Suspending the user makes them fail closed.

## Usage

Every gateway inference resolves one user before the runtime call. The same
`usage_id` is written to the deployment usage ledger as `user_request` and to
the customer-local principal ledger. The accounting team is the earliest
active membership, or `unassigned`. Operator tests stay out of that sum.
Admin analytics shows whether the two sums match. Command Center export does
not receive names, emails, or user ids.

## MCP

LibreChat-native execution cannot enforce User A versus User B without
writing LibreChat's database, which Rukan does not do. The gateway therefore
brokers approved Streamable HTTP servers. Rukan owns the catalog and the
allow/deny decision. User-created servers stay off. Loopback and private
targets are allowed only when the exact admin-approved URL or authority
matches. Link-local and cloud metadata addresses are refused. Hostname
targets are checked at request time and are not pinned to one resolved
address (`R-04-01`).

## Future Rukan workspace

The gateway, People, usage, MCP catalog, and `AgentDefinition` contract stay
Rukan-owned. A later thin workspace can call the same `/v1` surface. Git
Brain can appear later as another approved MCP server. Neither is built here.

## Hardening

Streaming reads upstream SSE incrementally and forwards each content delta
before the next upstream event is read. The socket closes when the client
generator closes. Token totals come only from the upstream usage event.

Production OIDC uses discovery and JWKS. A static JWKS remains for tests.
An unknown `kid` refreshes the key set once, and repeated unknown keys are
not allowed to stampede the issuer. Cached keys are used until the TTL.
After the TTL, a failed refresh fails authentication closed. HTTP discovery
is explicit and is for a local test issuer.

API credentials are enforced by route. `models`, `inference`, `self_usage`,
and `mcp` are separate scopes. A scope never grants a People capability the
user does not already have. MCP requires the `mcp` scope so an inference-only
key cannot call tools. OIDC sessions are not scoped credentials; People
policy still applies.

Employee usage is one canonical `gateway_events` row. Telemetry is an
idempotent projection of that row. A failed projection stays
`projection_pending` and is retried. It is not reported as a mismatch.
A failed canonical append is `degraded` and does not invent a second request.

## Recommendation

Keep LibreChat as the default workspace while the next product increment is a
thin first-party Rukan workspace for chat, My Usage, and connections. Do not
start a native Agent Builder or Git Brain until that seam has been used.
LibreChat's missing per-user agent and MCP menus are the friction that makes
a thin Rukan workspace the next step, not a reason to fork LibreChat.
