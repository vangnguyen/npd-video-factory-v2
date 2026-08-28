# V3-01 RC-3 Vision acceptance window

## Current decision

```text
PRODUCTION VERDICT: NO-GO
RC: vf-v3-01-rc3 / adde8d9c5a7f608db80cbd9d21aecd45f721065e
PROVIDER / MODEL / CAPABILITY: openai-vision / gpt-5-mini / vision
CREDENTIAL: alias secret://openai/codex-video only; value not read
G-01-A / G-02-A / G-03-A: hash-bound to exact RC-3 scope
GOVERNANCE BUNDLE: verified, not mounted
OPERATION 1: PENDING SEPARATE OWNER DECISION
LIVE CALLS: 0
ACTUAL COST: 0 VND
DEPLOY / PUBLIC INGRESS / PUBLISH / PRODUCTION ANALYTICS: NOT AUTHORIZED
```

PR #23 merged at `2026-08-28T12:55:13Z` after exact-head CI run `33171973815` passed all five
jobs. Merge commit `adde8d9c5a7f608db80cbd9d21aecd45f721065e` passed exact-main GitHub CI run
`33173094529` and the local regression below. Annotated tag `vf-v3-01-rc3` peels to that exact
commit and explicitly remains a `NO-GO` candidate with no provider execution.

## Exact-main regression

| Gate | Result |
|---|---|
| Python compile | PASS |
| API/worker/bridge Python tests | 245 passed |
| Acceptance repository validation | PASS; 60 rows, 16 gaps, all evidence hashes valid |
| Flow A / B / C evaluators | expected `BLOCKED` verdicts confirmed |
| DR/observability evaluator | expected `BLOCKED` production/soak verdict confirmed |
| Studio | 14 passed; JavaScript syntax PASS |
| Renderer | 14 passed; TypeScript and bundle checks PASS |
| Migration replay | upgrade → downgrade → upgrade PASS through `0011_v3_01_03` |
| Compose/deployment contract | PASS |
| Secret scan and `git diff --check` | PASS |
| Docker deterministic E2E | PASS, including disposable DR and no-duplicate recovery |
| Exact-main GitHub CI | run `33173094529`, 5/5 PASS |

The regression made no provider call, read no credential and spent 0 VND.

## Rebound execution scope

The dated window is `2026-08-28T14:00:00Z` through `2026-08-28T18:00:00Z`. It is at most four
hours, remains inside one UTC budget day and expires fail-closed. Expiry does not authorize an
extension; a later window needs a new exact scope and owner records.

| Binding | Exact value |
|---|---|
| Provider-scope SHA-256 | `f1cff1c8370caf6218577cdabfbd06c0665dfabb2407ec320b4668f7bf50072a` |
| Dated budget SHA-256 | `bbc90bcb6b29f5e28bdfd8c0fa2857a0b69ff072538edfbfd3e37e7293e228e8` |
| RightsRecord SHA-256 | `f469930a74b477751fc4417774b486ccbf2d7822487478875e099552c83e06ba` |
| Complete execution-scope SHA-256 | `a5ba3e0e1e39384cb1d6beb892b3c85a2266ea30be436faed529d6fdfe8aa9a0` |
| Raw governance-bundle SHA-256 | `da4450ce9f3c6f2015d2fbea3af8ca2ffb108c13dd53daafdad294570ecf4d83` |
| G-01-A record | `V3-01-APP-014`, canonical SHA-256 `53c882317bea811f8fd24b12094991250c864415ed399065aa2c0ab3be73e785` |
| G-02-A record | `V3-01-APP-015`, canonical SHA-256 `4a581048aa00cca3572cf6a03b6eb6e7de1d0286f0004b297fec7adb527cc052` |
| G-03-A record | `V3-01-APP-016`, canonical SHA-256 `545139d6e81d5fbdfaf9938addd423ac7c2810a7a4a45499c7fdf19a6c176885` |

The secret-free bundle is
[`V3-01-GATE-RC3-OPENAI-VISION-A.json`](V3-01-GATE-RC3-OPENAI-VISION-A.json). It is intentionally
stored as governance evidence only. It is not copied to the protected runtime path, and
`PROVIDER_VERIFIED_GATE_BUNDLE_ENABLED` remains `false`.

## Asset and rights boundary

Only [`g03-a-owned-vision-test.png`](assets/g03-a-owned-vision-test.png), SHA-256
`a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e`, is approved. The owner
permission is limited to this Vision acceptance input. It does not permit publishing, training,
resale or any other use. The decision is recorded in
[`V3-01-RIGHTS-G03A-001`](rights/V3-01-RIGHTS-G03A-001.json) and `V3-01-APP-016`.

## Immutable operations and budget

1. `v3-01-g03a-openai-vision-call-01`
2. `v3-01-g03a-openai-vision-call-02`

The envelope is 500 VND atomic reservation per operation and 1,250 VND for the full window. Each
operation is limited to one image, 2048×2048, detail `high`, 16,384 accounted input tokens, 4,096
output tokens, 60 seconds, concurrency 1 and one attempt. There is no automatic retry and no model
fallback. Operation 2 is not authorized merely because operation 1 is later approved.

## Runtime state remains fail-closed

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

No deployment or environment file was changed. The credential alias was not resolved and the key
value was not read, copied, logged or committed.

## Exact next owner decision

The only next execution decision is whether to authorize exactly operation
`v3-01-g03a-openai-vision-call-01` within the unexpired window and bound scope above. Approval must
not be inferred from this document, CI, bundle validation, credential presence or the prior gate
records. If operation 1 is not separately approved before `2026-08-28T18:00:00Z`, the window
expires and no call may occur. Operation 2 always requires a later, separate decision after review
of operation-1 evidence.
