# Native Agent Hub bridge

This increment connects the Native workflow to the existing `agent-hub-bridge.v1` event contract. It does not connect to Agent Hub production. Video Factory owns its SQLite state and its processes. No Agent Hub packages, database, Redis namespace or process memory are shared. The API backend remains separately documented in [AGENT_HUB_BRIDGE.md](AGENT_HUB_BRIDGE.md).

## Versioned Native service boundary

Every `/v1/` route requires a separately configured HMAC identity with exactly the `service` role. A human cookie, CSRF token or asserted Owner role cannot grant service access. The existing pure Video Factory HMAC helper signs the exact method, path, query, timestamp, nonce and SHA256 of the exact body. Accepted nonces persist in this workspace's Native database for 600 seconds; the clock window is 300 seconds. Unknown keys, replay, altered bodies, duplicate headers, duplicate JSON keys, expired timestamps, cross-site requests and foreign workspace requests fail closed. Body size is at most 64 KiB. Replay admission is bounded at 10,000 live nonces per workspace.

| Route | Behavior |
| --- | --- |
| `GET /v1/contract` | Authentication, implementation and default-off delivery state |
| `POST /v1/projects` | Unapproved draft, immutable initial history, event and idempotency receipt in one transaction |
| `GET /v1/projects/{native_project_id}` | Content-free current revision, hashes, counts, approval presence and latest job status |
| `GET /v1/events?limit=25&cursor=...` | Workspace-scoped event and delivery history, bounded 1–100, stable sequence cursor |
| `GET /v1/events/{event_id}/delivery` | Durable delivery state and at most five attempt records |

Native uses `native-bridge-draft-v1` and `native-project-summary-v1` DTOs. These are explicitly advertised in the contract response; Native's 32-hex project IDs and draft fields are not presented as PostgreSQL's `ProjectRead` DTO. Shared event envelopes and signing formats remain `agent-hub-bridge.v1`.

A draft body contains `workspace_id`, `name`, `input_kind` (`prompt`, `script`, `media`), `prompt`, `niche` and optional `channel_profile_ref`. Media drafts require empty prompt under the existing separate-media-project guard. All execution controls remain false: `start_pipeline`, `publish_requested`, `external_action_requested`; `execution_mode` must be `draft_only`. No route approves, uploads, schedules, runs a provider or publishes. An `Idempotency-Key` of 16–100 alphanumeric, underscore or hyphen characters is mandatory. A retry uses a **new HMAC nonce** with the same idempotency key and body. A changed body conflicts; replay returns the frozen initial receipt, even after subsequent editing or catalog changes. Project/history/outbox/receipt rollback together on failure.

## Event provenance and delivery

New Native workflow events are captured in the same transaction as the state change. An independent webhook worker handles delivery; a slow or unavailable Hub does not occupy the media worker. Research/idea source envelopes commit atomically in the separate Video Factory intelligence database; a bounded 50-row harvester transfers immutable envelopes and its cursor atomically into the workflow outbox. Interrupted harvesting repeats the same IDs. No historical backfill is enabled.

| Producer | Shared event |
| --- | --- |
| Research opportunity / generated shortlist | `trend.opportunity.detected`, `idea.shortlist.ready` |
| Draft creation and canonical edits | `video.project.created`, `video.approval.required` |
| Completed saved ASR, CPU scene/audio or frame jobs | `video.analysis.completed` |
| Actual completed local preview | `video.preview.ready` |
| Human workflow approval | `video.approved` |
| Render success/failure | `video.render.completed`, `video.render.failed` |
| Explicit Native dry run success/failure | `video.publish.completed`, `video.publish.failed` |
| Explicit fixture analytics / candidate assessment | `video.analytics.updated`, `video.winner.detected` |

Envelopes carry workspace, identifiers, immutable hashes, revision bindings and evidence flags. Prompt, narration, names, human notes, file paths, URLs, bearer tokens and key material are not exported. A research heuristic is labelled `research_heuristic` with `global_platform_metrics_verified=false`. It is not evidence of full Trend Radar metrics. Native publication events have `mock=true`, `mode=dry_run`, `actual_external_publication=false` and `remote_post_id=null`. Fixture analytics and winner events have `real_audience_observation=false`; the winner baseline remains unverified. Preview events identify their frozen revision and the current revision when emitted, and do not confer final approval.

Delivery is disabled by default, including when signing keys and a destination are loaded. Disabled historical events are not automatically replayed after enablement. Explicitly enabled new events are queued. The internal `enqueue()` method supports explicit selection of an older event; no service route exposes that authority. A Native Operator delivery/selection UI remains a gap.

Signing uses the existing keyring and exact body digest. The event ID is also the `Idempotency-Key`. Delivery is **at least once**: the receiver must durably deduplicate that ID before performing an action. Retries preserve the exact event body and ID, may rotate the signing key, and record each attempt. HTTP 408/425/429/5xx and transport failures retry up to five attempts with bounded exponential backoff and numeric Retry-After. Other non-2xx responses fail. Expired 120-second claims resume with the same event; old completion cannot overwrite a new claim. The destination fingerprint is frozen; a configured destination change cannot silently retarget queued events.

The HTTP adapter accepts only an approved HTTPS hostname on port 443 and `/agent-hub/events/v1`, with no credentials, query or fragment. It rejects private/non-global DNS results, connects to a validated IP while retaining hostname TLS verification, and does not follow redirects. Response bodies are bounded and never retained. An accepted HTTP response is not labelled a verified real Hub receipt. Fixture receiver success always remains a fixture.

## Configuration and recovery

`--bridge-auth-registry` selects an external, protected, workspace-bound JSON file with `version=1`, `native_workspace_id`, and `service_identities`. Keys use the existing base64 HMAC map, at least 32 bytes each. Roles must equal `["service"]`. `--bridge-webhook-registry` reads the same envelope with `webhook_signing` and `destination` (`endpoint`, `approved_host`). These files may be combined. They must be outside the Native state root, must not be linked, and must be at most 256 KiB; duplicate JSON keys fail. Only the explicit `--enable-bridge-http` flag enables the HTTP worker. **That flag must not be used against Agent Hub/NPD production without separate Owner approval. It has not been used in this program.** No real keys were read or created.

Owned additive tables preserve requests, nonce digests, envelopes, deliveries, attempts and the intelligence transfer cursor. Secrets remain outside backup state. Offline backup refuses pending/running/retrying deliveries, includes committed outbox metadata and source envelopes, and restores them into a fresh root. Restoration does not infer consent or automatically enable HTTP. The existing Phase 8/9 artifacts and repaired Phase 10 candidates are untouched.

## Evidence limits

See [native-bridge-evidence.json](north-star/native-bridge-evidence.json) for indexed tests, playable media, signed fixture delivery, restart and recovery evidence. Unit/HTTP tests use fixture keys and an in-process receiver; HTTPS wire tests mock the connection. The playable rehearsal uses actual FFmpeg pixels/tone, CPU media analysis, preview, final render and full QC. Transcript, research, ideas, publication and analytics are explicit fixtures. Locally generated source rights are seeded with explicit synthetic provenance in a fresh fixture root; the upload's default unknown-rights gate is preserved. This does not verify a runtime rights editor.

Real Agent Hub receiver compatibility, network deployment, secret provisioning, production routing, offline soak and production deployment remain unverified/external. Full Mode A, non-developer Mode B, full Trend Radar and learning acceptance remain open. Phase 10 Owner UAT remains required. This increment does not mark `AGENT_HUB_BRIDGE_READY`, `IMPLEMENTATION_COMPLETE` or North Star readiness.
