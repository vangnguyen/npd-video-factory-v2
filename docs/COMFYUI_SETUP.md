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

## Durable contract — North Star Wave 5

The optional bridge now owns a separate SQLite store and a single-process file lease. Requests,
job state/progress, exact workflow definition/graph fingerprints, result metadata hashes and a
content-free event audit persist. Queue concurrency/waiting counts, total stored jobs and explicit
retry count are bounded. A restarted or gracefully stopped active job becomes RECOVERY_REQUIRED;
startup does not replay it. Explicit retry preserves identity and rejects approved graph/schema
drift. Completed request replay still works when the backend is offline. Returned objects cannot
mutate saved state. The result metadata hash verifies JSON metadata, not generated media bytes.

Every `/v1/jobs` operation requires a service Bearer token and `X-VF-Workspace-Id`. Submission binds
that header to required `workspace_id`; request identities and list/read/cancel/retry/event access
remain workspace-scoped. Health stays available without GPU/auth configuration; readiness requires
both a configured backend and token. `COMFYUI_BRIDGE_TOKEN` is excluded from API settings exports.
API/worker generation scopes include trusted workspace/project/resolution-job identities, never
process-wide mutable state. Poll responses must match the requested job/workspace/workflow.
Arbitrary graph/model-weight keys are rejected even inside older permissive input schemas.
Backend/schema errors expose fixed messages rather than private inputs/provider error bodies.

`COMFYUI_JOB_STORE_PATH` defaults to `/workspace/storage/comfyui-bridge/jobs.sqlite3`; Compose mounts
its own `comfyui-bridge-data` volume. Defaults are one concurrent execution, 32 waiting jobs and
three explicit retries. The CPU stack still excludes the `gpu` service. Container wiring is
inspected source; Docker execution remains unverified on this host.

Unknown GPU estimates/actual costs stay null. Unpriced configured generation requires approval
before queueing; legacy numeric MediaPlan fields describe only the known lower bound and carry
explicit unknown-estimate flags. No free GPU cost is inferred. An unconfigured provider retains
its NOT_CONFIGURED failure path. A retained CPU/ASGI contract bundle validates persistence,
offline replay, scoped access and explicit interruption recovery; all backend outputs are mocks.
See `docs/north-star/comfyui-durable-contract-evidence.json` for hashes and test logs.

Mode routing now selects the approved text/image/reference/inpaint/upscale/video descriptors.
Inpaint requires image references and a mask; upscale requires references and a bounded 2x/4x
factor. Image-to-video/reference-assisted requests require references. Typed envelope selection
matches each checked-in input schema and preserves legacy text-generation fingerprints. Saved
evidence retains actual routed workflow/version, seed, requested/resolved mode, references,
mask/scale, null costs and local adapter elapsed time. Reference strings do not authorize arbitrary
file reads or URL downloads. Nine variants pass through actual ASGI bridge handlers and persist
mock results; `comfyui-generation-modes-n3` contains eleven retained exports.

Live backend transport, executable reviewed graphs, verified reference resolution,
binary artifact registration/decoding, provider cost receipts and real GPU acceptance remain open.
The repository still ships no executable GPU graph and does not claim generative media readiness.

Reviewed execution declarations can now specify a pinned graph SHA256, an approval reference/kind,
allowed node classes, exact scalar input bindings, output nodes and approved aspect dimensions.
The compiler reads only the manifest-selected graph, leaves source bytes unchanged, rejects hash,
node/binding/output drift and refuses placeholders or test-fixture execution by default. Reference
bindings require matching typed workspace/upload tokens from a trusted staging resolver; these
types do not independently verify uploads or rights. Approval references are declarations, not
proof of Owner approval. Live admission verification, reference staging and GPU transport remain
required. New unconfigured execution fields are excluded from fingerprints so existing approved
descriptor/job identities stay compatible. CPU tests use explicitly fake nodes and approval refs.

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
