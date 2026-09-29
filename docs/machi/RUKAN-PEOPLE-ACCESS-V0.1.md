# Rukan people and future access

People is a customer-local directory. It is not login, not chat, and
not a vendor export.

## Records

- User: `usr_` id, normalized unique email, display email, display name,
  status `active`, `suspended`, or `deactivated`.
- Team: `team_` id, name, description, `active` or `archived`.
- Membership: explicit user and team. Removing a membership keeps the row
  and marks it inactive.
- Access intent: allow or deny for platform access, inference, model
  selection, and agent builder. A team intent is a grant. A user intent
  can allow or deny.

## Resolution

1. Suspended or deactivated users deny every future capability.
2. A user platform deny denies the rest.
3. Otherwise each capability uses explicit user deny, then explicit user
   allow, then any active team's allow, then deny.

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
