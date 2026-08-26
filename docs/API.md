# API — V2-01

Base path: `/api/v1`. All request models forbid unknown fields.

## Health and capability

- `GET /healthz`: process liveness.
- `GET /readyz`: Redis and writable artifact-storage readiness.
- `GET /api/v1/capabilities`: reports deterministic jobs, publishing state, approval gate
  and absence of an AgentHub runtime dependency.

## Video jobs

- `POST /api/v1/video-jobs`: validates a `VideoJobCreate`, stores it and enqueues it.
  Optional `Idempotency-Key` prevents duplicate enqueueing.
- `GET /api/v1/video-jobs/{job_id}`: returns strict state, stage, progress, artifacts and
  stable error data.
- `GET /api/v1/video-jobs/{job_id}/artifacts/{artifact_name}`: returns only an artifact
  recorded for that job and contained by the configured storage root.

The accepted terminal success state is `awaiting_review`; V2-01 has no publish API.

Example payloads:

- `examples/vinhomes-green-paradise.request.json` — backward-compatible real-estate adapter;
- `examples/technology-explainer.request.json` — generic multi-niche core contract.

Manifest contract: `packages/contracts/video-manifest.schema.json`. Python and TypeScript
validators must stay semantically equivalent.
