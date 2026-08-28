# V3-01-09 — OpenAI gpt-5-mini Vision adapter

## Decision summary

```text
PRODUCTION VERDICT: NO-GO
IMPLEMENTED AXIS: PASS ON CODE-ONLY COMMIT fe4837bfd2ae0436f5fca557eab6101ca4cf5654
MOCK-TESTED AXIS: PASS
REAL-PROVIDER-TESTED AXIS: NOT_TESTED
PRODUCTION-PATH-TESTED AXIS: NOT_TESTED
QUALITY-ACCEPTED AXIS: NOT_TESTED
EXTERNAL CALLS: 0
ACTUAL COST: 0 VND
NEXT OWNER GATE: NEW G-08 FOR THE V3-01-09 DRAFT PR
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

The adapter never stores or reports USD. Future G-02 must supply approved VND-per-million-token
rates and a positive operation estimate. Missing usage produces `PENDING`; missing VND rates in
live mode blocks before HTTP. Mock tests cover both zero-cost receipts and deterministic VND math,
but simulated values are not actual spend evidence. Current actual spend remains `0 VND`.

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

`vf-v3-01-rc1` peels to exact `main`
`f42a1709cba6f087369c1636bab9bd06053f7613`. V3-01-09 is based on RC-1 but changes adapter code. If
its draft PR is later approved and merged, RC-1 must not be used for live Vision acceptance; run
exact-main regression and lock a new RC-2 first.

The next action is a new bounded G-08 for the V3-01-09 PR. Only after merge, exact-main verification
and RC-2 lock may the owner consider G-01-A for exactly OpenAI / `gpt-5-mini` / Vision. G-02-A and
G-03-A remain separate. No call is allowed until all three apply to the same RC, alias, owned image,
operation ID, time window and VND ceiling.

## Rollback

Before merge, abandon the draft branch. After a future merge, revert only the V3-01-09 commits,
restore `VISION_PROVIDER=fixture` or `contract`, keep the key unmounted, keep budgets at 0 VND and
keep the global kill switch engaged. No runtime rollback is currently required because this work
was not deployed.
