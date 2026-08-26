# Security and safety — V2-01

## Defaults

- Publishing is absent and `PUBLISH_ENABLED=true` fails startup validation.
- Human approval is mandatory and `HUMAN_APPROVAL_REQUIRED=false` fails startup validation.
- API/renderer bind to localhost by default; Redis is internal-only.
- External TTS is disabled in local/CI defaults and normal CI uses no paid call.
- No AgentHub, CRM, Ads, messaging or CMS credentials belong in this repository.

## Data and artifact controls

- Strict Pydantic/Zod/JSON Schema contracts reject unknown fields.
- Project folders and job IDs are constrained; resolved paths must remain under configured
  roots.
- Artifact download serves only names recorded on the job.
- Runtime storage, E2E artifacts, media and `.env` are git-ignored.
- Provider error envelopes do not return API credentials or internal exception text.

## Credential contract

Only variable names appear in source. `OPENAI_API_KEY` may be supplied through a protected
manual environment; it must never be stored in requests, Redis, manifests, artifacts or
logs. Production credentials and media were not migrated from the source repository.

## Integration boundary

AgentHub and V2 must not share database, Redis, packages or process memory. Future bridge
traffic requires versioned contracts, authentication, replay protection and signed webhooks.
No such bridge is enabled in V2-01.
