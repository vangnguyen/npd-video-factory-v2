# V3-01-10 — Verified Acceptance Gate Loader

## Decision summary

```text
PRODUCTION VERDICT: NO-GO
LOCKED RC: vf-v3-01-rc3 / adde8d9c5a7f608db80cbd9d21aecd45f721065e
G-01-A: REBOUND TO EXACT RC-3 SCOPE
G-02-A: REBOUND TO DATED RC-3 VND ENVELOPE
G-03-A: APPROVED FOR THE EXACT TEST ASSET ONLY
VERIFIED GOVERNANCE BUNDLE: CREATED AND HASH-VERIFIED; NOT MOUNTED
OPERATION 1 DECISION: PENDING
EXTERNAL EXECUTION: false
PAID EXECUTION: false
GLOBAL KILL SWITCH: engaged
EXTERNAL CALLS IN V3-01-10: 0
ACTUAL COST IN V3-01-10: 0 VND
```

V3-01-10 implements a secret-free, fail-closed loader for a bounded Vision acceptance window. PR
#23 is merged and RC-3 is locked. The governance-only bundle is hash-verified, but it is not mounted
and this work does not activate the OpenAI adapter, read the credential, call a provider, deploy,
open ingress, publish or collect production analytics.

RC-2 must never be used for live acceptance. Exact-main regression passed on merge commit
`adde8d9c5a7f608db80cbd9d21aecd45f721065e`, and annotated tag `vf-v3-01-rc3` peels to that exact
commit. Every rebound approval and the governance bundle binds this RC-3.

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

## G-03-A exact asset

One deterministic image was created entirely inside this repository without external media,
people or third-party trademarks:

- asset: [`assets/g03-a-owned-vision-test.png`](assets/g03-a-owned-vision-test.png);
- asset SHA-256: `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e`;
- generator: [`../../../scripts/generate-g03-owned-vision-asset.ps1`](../../../scripts/generate-g03-owned-vision-asset.ps1);
- generator SHA-256: `c2cf9da538709dcf251e769cad17138b6c17d082cd0d052fd5987730aa4a8538`;
- approved-for-acceptance RightsRecord:
  [`rights/V3-01-RIGHTS-G03A-001.json`](rights/V3-01-RIGHTS-G03A-001.json).

The owner explicitly granted G-03-A for this exact hash and the record is rebound to RC-3 through
`V3-01-APP-016`. The permission is only for Vision acceptance input. Publishing, training, resale
and every other use remain prohibited; it is not human-quality or commercial creative acceptance.

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

Historical preparation records are `V3-01-APP-011` and `V3-01-APP-012`. The exact RC-3 records are
[`V3-01-APP-014`](approvals/V3-01-APP-014.json),
[`V3-01-APP-015`](approvals/V3-01-APP-015.json), and
[`V3-01-APP-016`](approvals/V3-01-APP-016.json). The verified secret-free bundle is
[`V3-01-GATE-RC3-OPENAI-VISION-A.json`](V3-01-GATE-RC3-OPENAI-VISION-A.json), raw SHA-256
`da4450ce9f3c6f2015d2fbea3af8ca2ffb108c13dd53daafdad294570ecf4d83`. It remains unmounted and
grants no call authority by itself.

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
- checked-in image SHA-256 and exact narrow G-03-A decision;
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

## Current sequence

```text
merge V3-01-10                                      DONE
→ exact-main full regression                        DONE
→ annotated vf-v3-01-rc3 lock                       DONE
→ owner approves exact G-03-A asset                 DONE
→ rebind G-01-A/G-02-A/G-03-A to RC-3/window       DONE
→ bind two operation IDs and verify bundle hash     DONE, BUNDLE UNMOUNTED
→ separate owner execution decision for operation 1 PENDING
→ one bounded live call
→ evidence review
→ separate decision for operation 2 if operation 1 passes
```

Until that sequence is complete, the verdict remains `NO-GO` and live call authority remains
`NO`.
