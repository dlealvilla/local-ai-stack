# Rukan people and future access

People is a customer-local directory. It is not login, not chat, and
not a vendor export.

## Records

- User: `usr_` id, normalized unique email, display email, display name,
  status `active`, `suspended`, or `deactivated`.
- Team: `team_` id, name, description, `active` or `archived`.
- Membership: explicit user and team. Removing a membership keeps the row
  and marks it inactive.
- Access intent is stored per capability. A user may allow, deny, or
  inherit. A team may allow or deny. Inherit is refused on a team.
  Overriding one capability does not pin the others.

## Resolution

1. Suspended or deactivated users deny every capability. Provenance is
   `user_status`.
2. Platform access is resolved first. If it is not allow, inference,
   model selection, and agent builder are deny with provenance
   `platform_parent`.
3. Otherwise each capability uses user deny, then user allow, then any
   active team's allow, then default deny. Missing user intent inherits.
   Each capability keeps its own provenance.

The projection always says `enforcement: gateway_not_available`.
It does not create a session.

## Privacy

Directory audit lines store ids and actions, not email addresses.
Operational reports reject `email`, `email_display`, and
`email_normalized` keys. Command Center does not receive the directory.

## Later gateway

```text
identity provider establishes the user
    -> this resolver
    -> Rukan gateway
    -> an already admitted ServingInstance
    -> usage attributed to that user
    -> a client such as a first-party UI or LibreChat
```

LibreChat would be a client. It would not own identity.
