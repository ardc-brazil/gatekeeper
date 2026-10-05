# RFC 009 PR A — plan amendments (binding; override the plan where they differ)

Decided by the lead after the plan was written. Implementers read this together with their task brief.

## A1. Owners can withdraw invitations and revoke shares (Casbin DELETE)
`datasets_write` only allows `GET|POST|PUT`, so an owner whose only role is `datasets_write` — every account after this PR — gets 401 from Casbin on `DELETE /api/v1/datasets/{id}/tenancy-invitations/{id}` and on RFC 003's `DELETE /api/v1/datasets/{id}/share/...`.
- Add two narrow `p` rows for `datasets_write`: `DELETE` on `/api/v1/datasets/.*/share/.*` and on `/api/v1/datasets/.*/tenancy-invitations/.*`, `allow`, in the regex style of app/resources/casbin_seed_policies.sql.
- Seed them in the migration (insert into `casbin_rule` if absent; idempotent) and in tests/integration/fixtures/seed_clients.sql.
- Ownership/inviter checks stay in the services.
- Tests: an owner with only `datasets_write` withdraws an invitation (204) and revokes a share (204); a non-owner with `datasets_write` gets the service's refusal. Replace any test that pinned the 401.
- Applies to: the casbin/schema task (Task 3) and the invitations task (Task 12) + Task 16 integration.

## A2. Creating a dataset requires membership of the target tenancy
`POST /datasets` never checked that the caller belongs to the target tenancy; with `datasets_write` for everyone, any account could create in any tenancy.
- `POST /datasets` answers `403 {"detail": "not_a_member_of_tenancy"}` when the caller is not an enabled member of the requested tenancy.
- EXCEPT callers with the global `admin` role: their behaviour stays exactly as today (owner decision: admin behaviour unchanged).
- Tests: unit + integration — a member creates (201); a non-member gets 403; an admin who is not a member still creates as today.
- Applies to: the datasets task (Task 4) and Task 14 integration.

## A3. Contract adjustments (affect B/C, recorded here for completeness)
- The NextAuth session `admin` flag is produced by PR B.
- Webapp BFF routes forwarding gatekeeper detail codes use `accountHandler`, not `bffHandler`.
- `UserRef` / `UserBrief` are shared types created by PR B.
- `slugifyNamespace` strips diacritics first: "João Ciência" → "joao-ciencia".
