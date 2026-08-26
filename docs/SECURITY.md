# Security and safety — V2-02

## Defaults

- Publishing is absent and `PUBLISH_ENABLED=true` fails startup validation.
- Human approval is mandatory and `HUMAN_APPROVAL_REQUIRED=false` fails validation.
- API/renderer bind to localhost; PostgreSQL, Redis and MinIO are internal-only.
- Normal CI uses deterministic providers and no paid network call.
- No AgentHub, CRM, Ads, messaging or CMS credentials belong in this repository.

## Data and artifact controls

- Strict Pydantic/Zod/JSON Schema contracts reject unknown fields.
- IDs, filenames and object-key segments are constrained; path traversal is rejected.
- Artifact download requires a recorded name and verifies SHA-256 after object recovery.
- Idempotency keys are hashed before PostgreSQL persistence.
- Provider registry stores only a config reference; credentials are not returned by APIs.
- Runtime data, media, E2E artifacts and `.env` are git-ignored.

## Known security gate

V2-02 does not yet implement API authentication, RBAC or workspace membership. Localhost
binding is the only access boundary in this increment. Public routing and production
deployment are prohibited until those controls, rate limits and audit actor identity are
implemented and accepted.

## Credential contract

Only variable names appear in source: `DATABASE_URL`, `OBJECT_STORAGE_*` and optional
`OPENAI_API_KEY`. Real values must come from an external secret manager. They must never be
stored in project snapshots, jobs, assets, provider metadata, costs, logs or Git.

AgentHub and V2 must not share database, Redis, packages or process memory. Future bridge
traffic requires authentication, replay protection, signed requests and versioned contracts.
