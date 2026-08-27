# Media provider contracts — V2-06

This document is the provider catalogue required by the V2 master specification. The planning,
rights, persistence and resolution design is documented in [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md);
the optional GPU boundary is documented in [COMFYUI_SETUP.md](COMFYUI_SETUP.md).

## Capability matrix

| Capability | Interface | Local/CI adapter | Live adapter state | External or paid by default |
|---|---|---|---|---|
| Stock image/video | `StockMediaProvider` | deterministic licensed synthetic fixture | `not_configured` | no |
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
prohibited. A future real adapter must preserve the selected candidate contract durably so a
separate worker can resolve it after an API or worker restart.

## Generation contracts

Image generation receives prompt, negative prompt, aspect ratio, reference images, style, seed,
quality and operation. Video generation receives prompt, negative prompt, aspect ratio, reference
images, duration, seed and mode. Both expose a cost estimate before execution and return provider
job ID, model/workflow/seed/prompt provenance, artifact reference, actual VND cost when known and
rights metadata.

Generation resolution is asynchronous. PostgreSQL is canonical for job state; Redis carries only
delivery IDs. The API request does not remain open for a long generation job. Replayed requests use
a deterministic fingerprint and do not create another expensive job.

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
