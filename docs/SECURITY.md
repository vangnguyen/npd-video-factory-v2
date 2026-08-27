# Security and safety — V2-09

## Defaults

- Publishing supports validation and mock receipts only. All live publishing switches default
  false, and partial or incoherent combinations fail startup validation.
- Human approval is mandatory and `HUMAN_APPROVAL_REQUIRED=false` fails validation.
- API/renderer bind to localhost; PostgreSQL, Redis and MinIO are internal-only.
- Normal CI uses deterministic providers and no paid network call.
- No AgentHub, CRM, Ads, messaging or CMS credentials belong in this repository.
- Live trend providers are `not_configured`; the enabled dev/CI fixture is synthetic and startup
  rejects it in production.
- Trend references are metadata-only; no crawler, protection bypass, creator-media download or
  transcript-copy path exists.
- Auto Edit fixtures are synthetic and rejected at production startup. Live transcription stays
  `not_configured` until an owner-approved credential/adapter exists.
- The Vision fixture is synthetic, makes no network call and is rejected at production startup.
  Live Vision stays `not_configured`; fixture output never claims real pixel-model accuracy.
- Media fixtures are synthetic and production-ineligible. Unknown rights fail closed, social media
  is never downloaded, and external/paid media execution is disabled by default.
- ComfyUI accepts only allowlisted workflow IDs and typed inputs. Arbitrary workflow graphs, model
  uploads and direct frontend-to-ComfyUI access are absent.
- Timeline writes require optimistic concurrency and preserve immutable historical snapshots.
- Proxy previews are project-scoped, video-only, external-call-free and marked non-publishing.
- Subtitle/audio edits require expected versions; approval binds the exact review, timeline,
  subtitle and audio versions and is invalidated by any later accepted edit.
- Review/final responses and render schema use literal false publishing/external-action fields.
- External audio execution is disabled by default. eSpeak is local/CI only; a contract-only audio
  provider reports `not_configured` rather than pretending to use live data.
- Optional music must be a project-scoped audio asset with explicit owned/licensed/public-domain/
  royalty-free provenance. Unknown rights fail closed.

## Data and artifact controls

- Strict Pydantic/Zod/JSON Schema contracts reject unknown fields.
- IDs, filenames and object-key segments are constrained; path traversal is rejected.
- Artifact download requires a recorded name and verifies SHA-256 after object recovery.
- Idempotency keys are hashed before PostgreSQL persistence.
- Provider registry stores only a config reference; credentials are not returned by APIs.
- Runtime data, media, E2E artifacts and `.env` are git-ignored.
- Uploads use bounded part/file sizes, safe server-side names, SHA-256, magic-byte/MIME agreement,
  FFprobe validation and project-scoped object keys. Client extensions are never trusted.
- Source objects are immutable. Silence/highlight output is a reversible decision record only.
- Vision and crop plans are immutable evidence/decision records. Crop keyframes do not render,
  replace or mutate the source object.
- Media provenance records source, license, creator, rights and generation evidence. There is no
  owner-override write; V2-09 consumes this evidence only for fail-closed dry-run validation.
- Preview input paths come only from recorded project assets; output object keys are server-built,
  checksummed and registered before playback. Bounded render/download scratch is removed.
- Production-render input paths are derived from recorded project assets. Persisted render
  evidence replaces local paths with asset references and contains no provider secret.
- Full QC failures become `failed_qc` and cannot pass the approval/final-render boundary.
- Publication rows bind the exact final render and approval, store only a hashed idempotency key,
  and preserve blocked attempts with `external_action=false`.
- Platform OAuth/token material is external-only. Raw credential values and non-secret-store URI
  schemes fail startup validation; receipts and audits contain no credential reference value.

## Known security gate

V2-09 does not yet implement API authentication, RBAC or workspace membership. Localhost
binding is the only access boundary in this increment. Public routing and production
deployment are prohibited until those controls, rate limits and audit actor identity are
implemented and accepted.

## Credential contract

Only variable names/config references appear in source: `DATABASE_URL`, `OBJECT_STORAGE_*`,
optional `OPENAI_API_KEY`, `TRANSCRIPTION_PROVIDER`, `VISION_PROVIDER`, media provider selectors,
`COMFYUI_BRIDGE_URL`, `AUDIO_TTS_PROVIDER`, `AUDIO_EXTERNAL_EXECUTION_ENABLED`, the three publishing
gates, `PUBLISHING_CREDENTIAL_STORE` and platform credential reference names. Real values must come from an
external secret manager. They must never be
stored in project snapshots, jobs, assets, provider metadata, costs, logs or Git.

AgentHub and V2 must not share database, Redis, packages or process memory. Future bridge
traffic requires authentication, replay protection, signed requests and versioned contracts.
