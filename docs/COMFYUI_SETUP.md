# ComfyUI Bridge setup — V2-06

## Current status

The repository contains a provider-neutral bridge contract at `services/comfyui-bridge` and eight
versioned allowlisted workflow descriptors under `workflows/comfyui`. The mock backend is tested in
CI. A real ComfyUI server, GPU, model weight and production workflow graph are not bundled, not
configured and not claimed as tested.

The bridge is an optional Compose service behind the `gpu` profile. It does not start with the
default stack. The API and worker never send an arbitrary graph: they send only an allowlisted
`workflow_id`, typed inputs and an idempotent client request ID.

## Approved workflow catalogue

The V2-06 manifest defines versioned contracts for text-to-image, image-to-image, inpainting,
outpainting, upscale, background replacement, image-to-video and video generation. Each entry
declares its graph file, input/output JSON Schema, model identifiers, required custom nodes,
expected VRAM and timeout.

The checked-in graph JSON files are non-executable owner-provisioning placeholders. Before a real
GPU acceptance, an owner-approved change must replace a placeholder with a reviewed ComfyUI API
graph matching the same manifest version. Do not accept a graph in an API request and do not add a
generic graph upload endpoint.

## Safe local contract test

```bash
python -m pip install -e "services/comfyui-bridge[dev]"
python -m pytest services/comfyui-bridge/tests -q
```

The tests cover manifest validation, allowlist/version rejection, input validation, idempotent
submission, progress, result validation, cancellation, timeout, failure and retry. They use only a
deterministic mock and create no real media.

## Optional container

The service remains disabled by default:

```bash
docker compose --profile gpu config
```

Do not start real execution with repository defaults. `COMFYUI_EXECUTION_ENABLED=false` and
`COMFYUI_BACKEND=disabled` are intentional. The bridge health route can load the workflow
manifest while reporting the backend as not configured.

## Owner-gated real acceptance

Before enabling a real backend:

1. provision an isolated GPU host/runtime and pin ComfyUI plus custom-node revisions;
2. license and checksum every model; keep weights outside Git and the API container;
3. review and version the exact workflow graph and schemas;
4. add authenticated, network-restricted bridge transport and secret-manager references;
5. define VND cost/resource budgets, concurrency, queue limits and cancellation behavior;
6. test timeout/retry and artifact checksum registration with non-sensitive media;
7. review generated-media rights and production eligibility;
8. run a manual owner-approved provider acceptance and record evidence;
9. keep publishing disabled and require a separate human review.

Only after those gates may an environment select `IMAGE_GENERATION_PROVIDER=comfyui` or
`VIDEO_GENERATION_PROVIDER=comfyui`, enable external execution and start the `gpu` profile.
Paid execution remains a separate owner gate. Never commit endpoints containing credentials,
tokens, model files or secrets.

## Failure behavior

Unknown workflow/version and schema mismatch are rejected before queueing. Disabled backend is
`not_configured`. Jobs expose bounded failure codes and never return credentials. A timeout or
cancelled/failed job may be retried explicitly; the original workflow/version and request identity
remain auditable. Result artifacts must be registered through the V2 object/provenance layer before
they can participate in a media plan.
