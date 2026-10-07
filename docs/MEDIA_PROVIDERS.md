# Media provider contracts — V2-06

This document is the provider catalogue required by the V2 master specification. The planning,
rights, persistence and resolution design is documented in [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md);
the optional GPU boundary is documented in [COMFYUI_SETUP.md](COMFYUI_SETUP.md).

## Capability matrix

| Capability | Interface | Local/CI adapter | Live adapter state | External or paid by default |
|---|---|---|---|---|
| Stock image/video | `StockMediaProvider` | deterministic fixture and official HTTP contract mocks | Pexels/Pixabay adapters, disabled until explicitly configured | no |
| AI image | `ImageGenerationProvider` | deterministic SVG fixture | ComfyUI contract, disabled | no |
| AI video | `VideoGenerationProvider` | deterministic non-playable JSON fixture | ComfyUI contract, disabled | no |
| Existing project media | internal media resolver | immutable registered asset | available inside V2 | no |

Core planning uses these interfaces only; it does not import a vendor SDK. Provider state is
reported as `healthy`, `disabled` or `not_configured`, so missing credentials or infrastructure
are never represented as live capability.

## Required stock evidence

Each returned candidate must include provider and provider-asset IDs, creator, source reference,
license and optional license URL, attribution requirement, technical dimensions/duration, rights
status, production eligibility, estimated VND cost and provenance. Social-platform downloading is
prohibited. Selected candidates persist in MediaPlan; the official adapter refreshes canonical
metadata by provider ID before download, ignoring client-supplied URLs and license claims.

## Official stock adapters — North Star Wave 5

`app.stock_media_providers` implements image/video search, get and download against
[Pexels API](https://www.pexels.com/api/documentation/) and
[Pixabay API](https://pixabay.com/api/docs/). API paths are fixed; media downloads use approved
HTTPS CDN hosts, reject redirects, and enforce byte, MIME/magic and timeout bounds.
Pixabay image dimensions describe the selected web rendition; video orientation is filtered
locally. Unavailable semantic and Vision relevance scores stay null.

Responses are cached for 24 hours under a checksum-bound workspace namespace, surviving API/worker
restart without cross-workspace reuse. Credentials enter only the API wire request; logs, cache,
settings exports, error messages and CDN requests omit them. Injected MockTransport evidence is
explicitly marked. `STOCK_MEDIA_PROVIDER=pexels|pixabay`, the corresponding SecretStr key and
`STOCK_CACHE_ROOT` configure adapters; external execution and the global provider safety gate
remain off by default. Configuration is not proof of provider health or acceptance.

Candidates retain creator, original source, attribution and
[Pexels License](https://www.pexels.com/license/) or
[Pixabay Content License](https://pixabay.com/service/license-summary/). General licensing does
not establish third-party or personality rights. Downloads remain production-ineligible until
full decoding, rights records and provider acceptance are complete. The API fee is zero for these
free adapters; local compute cost is unknown. This increment does not implement Native stock
search/import controls or bypass credential/right admission in the worker.

## Generation contracts

Image generation receives prompt, negative prompt, aspect ratio, reference images, style, seed,
quality and operation. Video generation receives prompt, negative prompt, aspect ratio, reference
images, duration, seed and mode. Both expose a cost estimate before execution and return provider
job ID, model/workflow/seed/prompt provenance, artifact reference, actual VND cost when known and
rights metadata.

Generation resolution is asynchronous. PostgreSQL is canonical for job state; Redis carries only
delivery IDs. The API request does not remain open for a long generation job. Replayed requests use
a deterministic fingerprint and do not create another expensive job.
The optional bridge now persists its own provider-side queue/state/audit in isolated SQLite;
workspace/project/job scopes bind authenticated requests and prevent cross-workspace identities.
Unpriced configured generation requires approval before queueing. GPU estimates and actual costs
remain null until verified; result-reference JSON is explicitly not a registered binary artifact.

## Fail-closed rules

- `MEDIA_EXTERNAL_EXECUTION_ENABLED=false` blocks external providers.
- `MEDIA_PAID_EXECUTION_ENABLED=false` blocks paid providers.
- Contract-only adapters return `not_configured` and make no call.
- CI fixtures report `real_provider_tested=false` and `production_eligible=false`.
- Rights `unknown` or `restricted` block publishing.
- V2-06 contains no owner-override, publishing or source-mutation path.
- All provider ledger entries use VND; unknown live cost is not silently recorded as zero.

Real stock, image-generation, video-generation and GPU acceptance are separate manual owner gates.
No real-provider result and no production deployment are claimed by V2-06.
