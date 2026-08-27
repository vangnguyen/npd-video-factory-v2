# V3-01-01 Identity / Ingress Safety

## Decision

`PASS FOR LOCAL/CI REMEDIATION; BOUNDED G-08 APPROVED; NO PUBLIC OR PRODUCTION EXPOSURE`

The implementation is locked to code commit
`9635fb3ecf5d5fc5ba20aef3486708bad5960b8b`. It adds the human identity boundary required before
real-provider or production-path work. It does not create a release candidate and does not authorize
merge, deployment, credentials, paid calls, public ingress or publishing.

## Architecture

Human and service identities remain separate:

- normal `/api/v1/*` routes require a short-lived external bearer session;
- `/api/v1/bridge/*` retains its independent HMAC service identity, replay and clock-skew controls;
- `/healthz` and `/readyz` remain credential-free health probes;
- production OpenAPI/Swagger/ReDoc endpoints are disabled;
- Studio static assets may load a login shell, but API data remains deny-by-default.

The human registry is a read-only JSON secret mount described by
`packages/contracts/human-auth-registry.schema.json`. It stores only SHA-256 token digests, identity
metadata and role mappings. Raw session tokens are not stored in Git, images, Redis, API responses,
logs or acceptance evidence. Token lifetime is limited to 15 minutes through 24 hours, and digest
verification uses constant-time comparison. Missing, invalid, disabled, not-yet-valid and expired
credentials return the same secret-safe authentication failure.

## Role model

| Role | Read workspace data | Draft/edit | Approval decision | Dry-run publish request | Create workspace |
|---|---:|---:|---:|---:|---:|
| `viewer` | yes | no | no | no | no |
| `editor` | yes | yes | no | no | no |
| `reviewer` | yes | yes | yes | no | no |
| `owner` | yes | yes | yes | yes | platform owner only |

Roles may be platform-wide or bound to `workspace_id`, `slug:<workspace-slug>` or the explicit `*`
scope. Cross-workspace project, upload, job, artifact, trend and idea requests return the same `404`
contract as a missing object. A user with access to no workspace cannot enumerate the workspace
catalog.

## Studio session boundary

Studio validates a token through `/api/v1/auth/session` before loading workspace data. The raw token
is held only in browser `sessionStorage`, with a volatile-memory fallback for hardened contexts. It
is cleared on logout or any `401`; failed write requests are never replayed automatically. The
response exposes subject/display/role/expiry metadata only and never returns a token or digest.

This is an interim external-session contract, not an embedded identity provider. Production SSO or
OIDC issuance remains a later owner-selected integration; the API does not mint credentials.

## Emergency and abuse controls

- `HUMAN_API_ENABLED` disables all human API access.
- `HUMAN_WRITE_ENABLED` disables every human write while retaining authenticated reads.
- production Compose fixes `HUMAN_WRITE_ENABLED=false`.
- a Redis-backed fixed-minute limit is enforced per valid session token; Redis failure fails closed.
- the default mounted registry is empty, so an unprovisioned stack cannot authenticate a user.
- public ingress remains prohibited; network/WAF limits and unauthenticated-attempt throttling must
  be accepted with the production ingress in a later gate.

## Ingress tests

Evidence `EV-V3-SEC-001` proves locally and in disposable Docker:

- all human API routes reject missing/invalid credentials;
- explicit unauthenticated project, job and artifact requests return `401`;
- viewer/editor/reviewer/owner separation;
- cross-workspace project, asset, job and artifact requests return `404`;
- disabled, expired and changed tokens fail closed;
- rate limiting returns `429` with `Retry-After`;
- the write emergency switch returns `503`;
- Studio attaches authentication without mutating caller headers;
- Agent Hub service HMAC remains separate and passes replay/restart tests;
- no session secret appears in the response or committed evidence.

Evidence `EV-V3-SEC-002-PARTIAL` records the bounded upload-ingress result:

- traversal filenames are reduced to a safe leaf;
- unknown `source_url` input is rejected, so URL import/SSRF is absent;
- fake-extension and archive-signature payloads are rejected;
- maximum upload size and part checks are enforced;
- FFprobe receives an argv list through `create_subprocess_exec`, not a shell command.

`SEC-002` is not complete: malware scanning/quarantine, decompression-bomb resource acceptance,
unauthenticated ingress throttling and production WAF evidence remain assigned to V3-01-03.

## Verification

| Check | Result |
|---|---|
| Python API/worker/bridge regression | 142 passed |
| Studio tests and syntax | 14 passed |
| Renderer tests/typecheck/bundle | 14 passed |
| Focused identity/security tests | passed |
| Docker deterministic E2E | passed |
| Compose development + production contract | passed |
| Python compile / JavaScript syntax / shell syntax | passed |
| V3-01 evidence validator / `git diff --check` | passed |
| External provider calls / spend | 0 calls / 0 VND |

## Provisioning and rollback contract

Any later staging operator must create the raw session and hash-only registry outside the
repository, use a file readable only by the runtime operator, mount it read-only, and verify its
schema without printing content. Revocation means disabling/removing the record and performing a
guarded API restart; tokens must never be copied into an issue, shell transcript or evidence bundle.

Rollback is to disable public ingress, set `HUMAN_WRITE_ENABLED=false`, restore the previous image
and retain the registry outside the image. No database migration or Redis key migration was added by
V3-01-01.

## Remaining gates

- G-08 record `V3-01-APP-002` authorizes merge only after PR #13 is retargeted to exact `main` and
  all five CI jobs pass.
- G-04/G-09 must authorize any staging/production-path run or deploy.
- G-01 remains required before any provider credential is used.
- G-05/G-06 remain required before any external publication.

The repository verdict therefore remains `NO-GO`.
