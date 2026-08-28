# V3-01-10 — Verified Acceptance Gate Loader

## Decision summary

```text
PRODUCTION VERDICT: NO-GO
BASE RC: vf-v3-01-rc2 / 5936aa7a9656d728be751d0ee61011fc1a5abc7a
G-01-A: APPROVED FOR PREPARATION ONLY
G-02-A: APPROVED FOR PREPARATION ONLY
G-03-A: PENDING OWNER REVIEW
VERIFIED RUNTIME BUNDLE: NOT CREATED
EXTERNAL EXECUTION: false
PAID EXECUTION: false
GLOBAL KILL SWITCH: engaged
EXTERNAL CALLS IN V3-01-10: 0
ACTUAL COST IN V3-01-10: 0 VND
```

V3-01-10 implements a secret-free, fail-closed loader for a future bounded Vision acceptance
window. It does not activate the OpenAI adapter, read the credential, create a runtime gate bundle,
call a provider, deploy, open ingress, publish or collect production analytics.

Because V3-01-10 changes code after RC-2, RC-2 must never be used for the live acceptance. A future
merge requires exact-main regression and a new annotated `vf-v3-01-rc3` lock. Every runtime approval
record and the protected bundle must then bind that exact RC-3 commit.

## Owner-approved G-02-A envelope

| Control | Exact limit |
|---|---:|
| Provider / model / capability | `openai-vision` / `gpt-5-mini` / `vision` |
| Atomic reservation | 500 VND per operation |
| Acceptance-window ceiling | 1,250 VND |
| Operations | exactly two predeclared IDs |
| Input | one owned image per operation, maximum 2048 × 2048 |
| Image detail | `high` |
| Input accounting ceiling | 16,384 tokens |
| Output ceiling | 4,096 tokens |
| Request timeout | 60 seconds |
| Concurrency | 1 |
| Automatic retry | none; `max_attempts=1` |
| Activation window | at most four hours and cannot cross the UTC budget day |
| Input rate | 6,565 VND per million tokens |
| Cached-input rate | 656.5 VND per million tokens |
| Output rate | 52,520 VND per million tokens |

The worst-case accounting estimate under those ceilings is approximately 322.683 VND. The loader
requires the full 500 VND reservation; a lower or higher estimate is rejected as
`COST_RESERVATION_MISMATCH`. The durable PostgreSQL safety ledger performs the reservation
atomically before execution.

The `gpt-5-mini` alias remains the exact approved model. The current model page still lists that
alias as available; the deprecated label applies to the dated `gpt-5-mini-2025-08-07` snapshot,
not evidence of an announced shutdown for the alias. If the alias is unavailable when execution is
eventually authorized, the operation stops. There is no automatic fallback or model substitution.

The two operation IDs are predeclared and immutable:

1. `v3-01-g03a-openai-vision-call-01`
2. `v3-01-g03a-openai-vision-call-02`

Any other ID is rejected. The future owner approvals must also bind one execution-scope hash that
covers both IDs, exact RC, provider/model/capability/alias, activation and expiry, dated budget and
the approved RightsRecord hash. Changing any one of those fields invalidates all three approvals.

## Verified bundle contract

The future bundle is read from the protected path configured by
`PROVIDER_VERIFIED_GATE_BUNDLE_FILE`, defaulting to
`/run/secrets/video-factory-provider-gates.json`. It contains no API key, token or password. The
deployment configuration pins the entire file with
`PROVIDER_VERIFIED_GATE_BUNDLE_SHA256` and separately pins the expected RC tag and commit.

The loader rejects the bundle unless all conditions are true:

- the raw bundle SHA-256 matches in constant time;
- G-01, G-02 and G-03 have three distinct `APPROVED` record IDs;
- each approval record's canonical SHA-256 matches its wrapper;
- all three approval records bind exact RC-3 and remain valid for the complete window;
- G-01 binds the exact provider, model, capability and credential-alias hash;
- G-02 binds the exact dated VND envelope hash;
- G-03 binds the exact RightsRecord hash;
- all three records bind the same complete execution-scope hash;
- the RightsRecord is approved, secret-free, unexpired and permits commercial and derivative use;
- exactly two distinct operation IDs bind the same approved asset ID and SHA-256;
- the operation is exactly `vision_analysis`;
- the window is positive, no more than four hours and stays inside one UTC budget day.

At preflight, both the in-memory and durable controllers re-check current time, UTC budget day,
provider, model, capability, alias, operation ID, operation type, asset ID/hash, media kind,
dimensions, frame count, detail, token limits and the exact 500 VND reservation. Expiry, an
unlisted third operation, a repeated operation, another image, another model or any configuration
drift fails closed before the provider adapter.

## G-03-A candidate

One deterministic image was created entirely inside this repository without external media,
people or third-party trademarks:

- asset: [`assets/g03-a-owned-vision-test.png`](assets/g03-a-owned-vision-test.png);
- asset SHA-256: `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e`;
- generator: [`../../../scripts/generate-g03-owned-vision-asset.ps1`](../../../scripts/generate-g03-owned-vision-asset.ps1);
- generator SHA-256: `c2cf9da538709dcf251e769cad17138b6c17d082cd0d052fd5987730aa4a8538`;
- candidate RightsRecord:
  [`rights/V3-01-RIGHTS-G03A-001.json`](rights/V3-01-RIGHTS-G03A-001.json).

The record deliberately remains `decision=BLOCKED` with reviewer `Pending owner G-03-A review`.
This prevents repository preparation from becoming owner approval. It may change to `APPROVED`
only after the owner explicitly grants G-03-A for this exact asset hash and after the decision is
rebound to the future exact RC-3. This image is only acceptance input; it is not human-quality or
commercial creative acceptance evidence and will not be published.

## Checked-in safe state

The default configuration remains:

```text
VISION_PROVIDER=fixture
PROVIDER_VERIFIED_GATE_BUNDLE_ENABLED=false
PROVIDER_EXTERNAL_EXECUTION_ENABLED=false
PROVIDER_PAID_EXECUTION_ENABLED=false
PROVIDER_GLOBAL_KILL_SWITCH_ENGAGED=true
PROVIDER_PER_OPERATION_LIMIT_VND=0
PROVIDER_DAILY_LIMIT_VND=0
OPENAI_API_KEY="" in Compose
```

G-01-A and G-02-A governance records are
[`V3-01-APP-011`](approvals/V3-01-APP-011.json) and
[`V3-01-APP-012`](approvals/V3-01-APP-012.json). They record the owner decisions on RC-2 but grant
no call authority and cannot satisfy the future loader because V3-01-10 changes the candidate.

## Acceptance tests

The zero-network suite validates:

- valid raw and canonical hashes;
- file tampering, internal record tampering and wrong-RC rejection;
- exact G-02-A configuration and drift rejection;
- default no-call state even when a valid fixture bundle is parsed;
- allowlisted operation, asset, dimensions, detail and token limits;
- exact cost reservation, expiry and no-model-fallback behavior;
- two-operation ceiling and duplicate prevention;
- atomic durable reservation and restart persistence;
- checked-in image SHA-256 and intentionally blocked G-03-A decision;
- existing OpenAI adapter malformed-response, timeout, retry, circuit, rights, budget and secret
  tests without any network call.

Test bundles use synthetic approval IDs, hashes, RC and image hash. They are fixtures only and
cannot be promoted into runtime evidence.

The secret-free local evidence bundle is
[`vf-v3-01-20260828T122937Z-e7e9ccc`](../../../evidence/v3-01/vf-v3-01-20260828T122937Z-e7e9ccc)
with evidence ID `EV-V3-VERIFIED-GATE-LOADER-001`, bound to implementation commit
`e7e9ccceeb97830db47d66cfa392c854f8a2e2e4`. It records 28 focused tests, the broader local
regression and Docker deterministic E2E as mock/local evidence only, with 0 external calls and
0 VND actual cost.

## Required sequence after a future G-08

```text
merge V3-01-10
→ exact-main full regression
→ annotated vf-v3-01-rc3 lock
→ owner approves G-03-A for the exact image and RightsRecord hash
→ owner rebinds G-01-A and G-02-A to exact RC-3 and a dated <=4h window
→ bind the two predeclared operation IDs and protected secret-free bundle
→ verify bundle hash and fail-closed preflight with kill switch engaged
→ separate owner execution decision for exactly operation 1
→ one bounded live call
→ evidence review
→ separate decision for operation 2 if operation 1 passes
```

Until that sequence is complete, the verdict remains `NO-GO` and live call authority remains
`NO`.
