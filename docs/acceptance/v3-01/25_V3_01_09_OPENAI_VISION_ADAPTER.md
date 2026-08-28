# V3-01-09 — OpenAI gpt-5-mini Vision adapter

## Decision summary

```text
PRODUCTION VERDICT: NO-GO
IMPLEMENTED AXIS: PASS ON MERGED RC-2 5936aa7a9656d728be751d0ee61011fc1a5abc7a
MOCK-TESTED AXIS: PASS
REAL-PROVIDER-TESTED AXIS: NOT_TESTED
PRODUCTION-PATH-TESTED AXIS: NOT_TESTED
QUALITY-ACCEPTED AXIS: NOT_TESTED
EXTERNAL CALLS: 0
ACTUAL COST: 0 VND
PR: #22 MERGED; G-08 V3-01-APP-010 CONSUMED
NEXT OWNER GATES: G-03-A AND NEW G-08 FOR V3-01-10
```

V3-01-09 implements only the missing OpenAI Vision adapter foundation. It does not use the
provisioned key, enable a provider, unlock a budget, deploy, open ingress or publish. OpenAI
documents that `gpt-5-mini` accepts image input and supports Structured Outputs; this adapter uses
the Responses endpoint with `store=false` and a strict JSON Schema. Sources:
[model](https://developers.openai.com/api/docs/models/gpt-5-mini) and
[Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

## Architecture and fail-closed order

```text
VisionAnalysisService
  -> ProviderSafetyController / durable PostgreSQL safety state
     -> kill switch, G-01, G-03, G-02, duplicate, circuit and budget checks
        -> OpenAIVisionProvider
           -> resolve credential alias in memory
           -> extract bounded hashed frame evidence
           -> POST /v1/responses with strict structured output
           -> validate, normalize, hash and create VND cost receipt
```

Business logic does not call OpenAI directly. The adapter is `external_call=true` and `paid=true`,
so the central controller blocks it under the checked-in state. The active policy still has
external execution false, paid execution false, 0 VND limits and the global kill switch engaged.
Even if someone invokes the adapter directly, a zero cost envelope blocks it before frame
extraction or HTTP unless an explicit contract-test-only mock flag is injected by tests.

## Adapter contract

- provider/model: `openai-vision` / exact `gpt-5-mini`;
- endpoint: official `https://api.openai.com/v1/responses` only;
- credential: opaque alias `secret://openai/codex-video`; the value remains outside Git;
- input: one owned image or bounded FFmpeg-extracted video frames, each with SHA-256 and immutable
  `asset://` evidence reference;
- output: scene/frame description, composition, OCR, objects, primary subject, saliency/safe-crop,
  quality signals and calibrated confidence;
- persistence evidence: requested/returned model, request/response hashes, latency, source/frame
  hashes, response-ID hash, secret-recorded=false and VND-only cost receipt;
- privacy: `store=false`; no credential, raw request body or raw response body is stored in the
  provider ledger or returned by the capabilities/provider-safety APIs.

## Cost contract

The adapter never stores or reports USD. G-02-A now approves a preparation-only envelope of 500
VND per operation and 1,250 VND for two predeclared operations, with rates of 6,565 VND/M input,
656.5 VND/M cached input and 52,520 VND/M output. That approval grants no call authority and is not
active in checked-in settings. Missing usage produces `PENDING`; missing VND rates in live mode
blocks before HTTP. Mock tests cover both zero-cost receipts and deterministic VND math, but
simulated values are not actual spend evidence. Current actual spend remains `0 VND`.

The `gpt-5-mini` alias remains the approved model and is still listed as available. The deprecated
entry is the dated `gpt-5-mini-2025-08-07` snapshot; this audit has no evidence of an announced
shutdown date for the alias. Runtime failure must stop without automatic fallback.

## Contract tests

All HTTP behavior uses `httpx.MockTransport`; no external network request is possible.

| Boundary | Result |
|---|---|
| Strict Responses JSON schema and full frame coverage | PASS mock |
| Vietnamese OCR, composition, subject/safe-crop and quality mapping | PASS mock |
| Request/response/frame hashes, latency and provenance | PASS mock |
| Secret and credential-alias redaction | PASS |
| Missing alias/resolution | fail closed before transport |
| Zero VND envelope without G-02 | fail closed before frame/transport |
| Malformed response | rejected |
| Timeout and rate-limit retry | bounded by central policy |
| Circuit breaker and duplicate operation | blocked |
| Missing/rejected rights | blocked before adapter |
| Per-operation budget excess | blocked before adapter |
| Default application settings | resolver calls 0; transport calls 0; cost 0 VND |

Evidence ID `EV-V3-OPENAI-VISION-ADAPTER-001` covers only `implemented` and `mock-tested` for
`VIS-01`. It does not change any real-provider, production-path or quality axis.
The redacted, hash-validated evidence bundle is
`evidence/v3-01/vf-v3-01-20260828T094813Z-fe4837b`.

## Credential and container boundary

A separate OpenAI key was created and saved in the ignored local `.env` by the approved secure
helper. The key value was never printed, committed or placed in evidence. Local/CI Compose now
overrides `OPENAI_API_KEY` to an empty value for every service using the shared `.env`, preventing
the workstation key from propagating into containers. A later owner-gated G-01 implementation must
mount a capability-specific secret into only the approved API acceptance target.

Credential presence is not execution authority and is not proof that the key, project access or
billing path works.

## RC and next gates

PR #22 merged as `5936aa7a9656d728be751d0ee61011fc1a5abc7a`; annotated tag
`vf-v3-01-rc2` peels to that exact commit. G-01-A and G-02-A were subsequently approved for
preparation only. G-03-A remains pending, and V3-01-10 changes code after RC-2. Therefore no live
acceptance may run on RC-2. Merge V3-01-10 only under a new G-08, run exact-main regression, lock
RC-3, and rebind all three runtime records to the same RC, alias, owned image, operation IDs, time
window and VND ceiling before a separate execution decision.

## Rollback

If the adapter foundation must be removed, revert PR #22, restore `VISION_PROVIDER=fixture` or
`contract`, keep the key unmounted, keep budgets at 0 VND and keep the global kill switch engaged.
No runtime rollback is currently required because RC-2 was not deployed and no provider call was
made.
