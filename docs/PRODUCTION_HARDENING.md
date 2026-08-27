# V2-11 Production Hardening

## Security posture

V2-11 changes the API version to `0.12.0` and adds request IDs, `nosniff`, frame denial,
no-referrer and no-store API response headers. Bridge endpoints are inaccessible unless the
bridge is explicitly enabled and a valid HMAC service identity is loaded.

The bridge rejects secret-like keys and token-shaped values before persistence. Database
constraints additionally enforce:

- no bridge-triggered execution;
- no bridge external action;
- no secret-bearing event state.

Publishing, paid media, external analytics and human-approval guards remain unchanged. Bridge
authentication does not grant permission to publish or call a paid provider.

## Roles and policy boundary

| Role | Intended scope | V2-11 state |
|---|---|---|
| `viewer` | Read project/output state | vocabulary defined; interactive auth not exposed |
| `editor` | Edit project/timeline | vocabulary defined; existing local Studio behavior unchanged |
| `reviewer` | Approve/request changes | existing version-bound approval rules remain canonical |
| `owner` | Providers/high-risk configuration | owner gates remain out-of-band and fail closed |
| `service` | Agent Hub system integration | HMAC authenticated and enforced on bridge routes |

## Production invariants

- Compose project is `npd-video-factory-v2`.
- PostgreSQL, Redis, MinIO, network, paths, environment and backups are V2-owned.
- No Agent Hub, n8n or Caddy service is defined by this repository.
- API, Studio and renderer stay bound to `127.0.0.1` unless an owner changes the deployment contract.
- Production rejects all deterministic fixture providers.
- `PUBLISH_ENABLED`, `PUBLISH_EXTERNAL_EXECUTION_ENABLED` and
  `PUBLISH_OWNER_GATE_ENABLED` stay false until a separate owner-approved publishing release.
- `HUMAN_APPROVAL_REQUIRED` stays true.
- HTTP webhook delivery requires all of: bridge enabled, `mode=http`, external-delivery flag,
  HTTPS URL and exact allowlisted hostname.
- CI/test reject external webhook delivery; production rejects fixture webhook delivery.

## Threat controls

| Threat | Control |
|---|---|
| Request replay | timestamp window plus Redis nonce `SET NX EX` |
| Body/path tampering | exact canonical HMAC and body SHA-256 |
| Key rotation invalidates history | active signing key plus historical verify-only keyring |
| SSRF through callback URL | callback URL is configuration-only; payload cannot supply it; HTTPS host allowlist |
| Secret persistence | external key file, input rejection, no secret fields in event/receipt APIs |
| Agent Hub outage | PostgreSQL outbox + retry state; V2 pipeline has no synchronous Agent Hub dependency |
| Shared-state coupling | separate DB, Redis, object storage and contract-only integration |
| Accidental external action | disabled default, explicit gate, fixture-only CI, unchanged publish guards |

## Operator checks

Before any exposure, review the generated OpenAPI, bridge contract, key-file ownership/mode,
firewall binding, backup evidence and the external URL allowlist. Do not put HMAC keys in `.env`,
Compose labels, command arguments, GitHub comments or smoke artifacts.

Caddy routing is intentionally absent. Adding a public hostname is a separate owner decision after
soak acceptance and interactive authentication design are accepted.
