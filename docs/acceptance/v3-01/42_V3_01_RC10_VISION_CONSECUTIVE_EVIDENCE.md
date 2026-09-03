# RC-10 Vision Consecutive Evidence Review

## Verdict

```text
EXECUTABLE RC: vf-v3-01-rc10 / c2b1aec2d54dd90bcb486f8a68c97746b39963aa
OPERATION 1: PASS / CONSUMED / SUCCEEDED
OPERATION 2: PASS / CONSUMED / SUCCEEDED
VISION CONSECUTIVE STATUS: 2/2 PASS
VISION REAL-PROVIDER-TESTED: PASS WHEN THIS EVIDENCE PR RECEIVES G-08 AND MERGES
FURTHER VISION OPERATION: NOT REQUIRED / NOT AUTHORIZED
PRODUCTION-PATH-TESTED: NOT_TESTED
QUALITY-ACCEPTED: NOT_TESTED
PRODUCTION VERDICT: NO-GO
```

Two separately owner-authorized OpenAI Vision operations completed consecutively on immutable
`vf-v3-01-rc10`. Both used the same provider/model, owned image, RightsRecord, request contract,
execution scope, timeout contract and VND window. Each completed in one attempt with strict
structured output, complete provider/usage/cost evidence, no retry or fallback, a closed circuit,
duplicate blocking and a clean secret scan.

This evidence closes the **Vision real-provider-tested** acceptance axis when the evidence-only PR
receives G-08 and merges. It does not establish production-path or human-quality acceptance, and it
does not authorize another Vision operation.

Machine-readable evidence:

- Operation 1:
  [`vf-v3-01-20260902T143651Z-c2b1aec-op1`](../../../evidence/v3-01/vf-v3-01-20260902T143651Z-c2b1aec-op1/)
- Operation 2 and consecutive assessment:
  [`vf-v3-01-20260902T162324Z-c2b1aec-op2`](../../../evidence/v3-01/vf-v3-01-20260902T162324Z-c2b1aec-op2/)
- Preserved Operation 2 source receipt:
  [`provider/operation-2-result.json`](../../../evidence/v3-01/vf-v3-01-20260902T162324Z-c2b1aec-op2/provider/operation-2-result.json),
  SHA-256 `deed47e573079bd53118859f616991aae42b420992aad84f39cbfb4bdb3df0a2`

No missing field was reconstructed. The two provider responses remain separate artifacts.

## Exact binding

| Field | Evidence |
|---|---|
| Executable RC | `vf-v3-01-rc10` / `c2b1aec2d54dd90bcb486f8a68c97746b39963aa` |
| Current governance main used by Operation 2 | `79b14ded0bbd0cd552420e5964647b6fba16f9b7` |
| Executable RC CI | `33527973264`, completed/success, 5/5 |
| Governance-main CI | `33650857422`, completed/success, 5/5 |
| Dual-CI provenance SHA-256 | `1e4fa76b8d1d42e1b2f84c90ec671d0f122f180df86b44ea4c41cc17e8a9bbff` |
| Executable-tree SHA-256 | `f1f75f632ca3b1380985c5a532c9f4c601e39d45276135666f335cc3d041125c` on RC and governance main |
| Provider/model/capability | `openai-vision` / `gpt-5-mini` / `vision` |
| Bundle SHA-256 | `30f4ffd9353a00b7fdf97d0998dce43798937a2c577ca3fa618c947bbb8040e1` |
| Execution-scope SHA-256 | `a77a2e38d604214dbcaf0933cbdbf6f2fafa6ee258369e1a629ef5b0d55c6cc0` |
| Operation 2 authority SHA-256 | `56056e13c20c57b944d2418b920b22b7896066c21b7c9196f3acab43f29f238f` |
| Asset SHA-256 | `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e` |
| RightsRecord SHA-256 | `f469930a74b477751fc4417774b486ccbf2d7822487478875e099552c83e06ba` |
| Runtime image | `sha256:7beaeb6622201617b0f30ed9f26f8d93845777507d6141d91169cb42936568d6` |
| Timeout contract | provider HTTP `90s`; controller hard envelope `120s` |

G-01-A, G-02-A and G-03-A remain the exact RC-10 records `V3-01-APP-038`,
`V3-01-APP-039` and `V3-01-APP-040`. Operation 2 received a separate authority; its secret-free
record is retained at
[`governance/operation-2-authority.json`](../../../evidence/v3-01/vf-v3-01-20260902T162324Z-c2b1aec-op2/governance/operation-2-authority.json).
Only the credential alias is named; the value is absent.

## Consecutive provider results

| Evidence | Operation 1 | Operation 2 |
|---|---:|---:|
| Provider execution | PASS | PASS |
| Evidence completeness | COMPLETE | COMPLETE |
| Attempts | 1 | 1 |
| Retry / fallback | 0 / 0 | 0 / 0 |
| Input tokens | 1,996 | 1,996 |
| Cached input tokens | 0 | 0 |
| Output tokens | 2,134 | 2,781 |
| Actual cost | `125.181420 VND` | `159.161860 VND` |
| Latency | `27,790.325 ms` | `33,284.965 ms` |
| Timeout | none | none |
| Consumed | yes | yes |

Operation 2 provider evidence:

| Field | Result |
|---|---|
| Provider request ID | `req_8c3597bb115e485ca4252bbe5cd30477` |
| Client request ID | `vf-66e4466b132949b5b05c8267771144d3` |
| Provider response ID SHA-256 | `49f1a390f6d52315b7963f20f5afb20ea2541e9d9398d41762bc383f58e82689` |
| Request SHA-256 | `138d70333ff7df29f6c986b30f5c251f6c5b6b3ee7d969846f73e2931a4f22a8` |
| Response SHA-256 | `ff8a5d4a1200c09bfbda18db557d89c8d3b9763a95f29e69ac62e72460b299b7` |
| Structured output | PASS; one frame |
| Evidence writer | primary file written; fallback not used |

Both operations have the same request SHA-256 because they exercised the same immutable input and
request contract. Their response SHA-256 values differ, which preserves the two independent model
responses. The evidence does not deduplicate or overwrite either response.

## VND reconciliation and durable safety

| Control | Result |
|---|---|
| Operation 1 actual cost | `125.181420 VND` |
| Operation 2 actual cost | `159.161860 VND` |
| Window actual total | `284.343280 VND` |
| Durable committed total | `284.3433 VND` |
| Acceptance-window envelope | `1,250 VND` |
| Window utilization | `22.7474624%` |
| Reserved after reconciliation | `0.0000 VND` |
| Durable ledger | 2 operations / 2 attempts / 1 budget day / 1 circuit |
| Circuit | `closed`, consecutive failures `0` |
| Duplicate re-preflight | `DUPLICATE_OPERATION_BLOCKED` |
| Unexpected operation rows | `0` |
| Secret scan | PASS; key absent; zero real-key-pattern matches |
| Post-run | runner stopped; gate unmounted; PostgreSQL stopped cleanly; ledger volume preserved |
| Worktrees | exact RC and governance worktrees clean |

This evidence PR itself performs zero provider calls, reads zero credentials and incurs `0 VND`.

## Acceptance impact

- `EV-V3-RC10-VISION-CONSECUTIVE-PASS-001` binds both source receipts and records 2/2 consecutive
  real-provider PASS on immutable RC-10.
- `VIS-01` advances from `NOT_TESTED` to `PASS` on the `real-provider-tested` axis in this PR.
- `V3-01-GAP-003` remains `IN_PROGRESS` because real ASR, real reframe accuracy, production path and
  human full-watch/listen evidence are still missing; only its Vision real-provider sub-scope closes.
- `V3-01-GAP-010` remains `IN_PROGRESS` because production-like multi-instance reservation,
  recovery, retention and monitoring evidence is still missing.
- `V3-01-GAP-013` remains `IN_PROGRESS` because the approval covers one owned Vision-only image,
  not the complete final-render asset set or public-output rights.
- Both RC-10 operations are consumed and cannot be reused. No Operation 3 is required or authorized.
- RC-10 remains immutable; this evidence-only PR does not create RC-11.
- Production stays `NO-GO`; no deployment, public ingress, publishing or production analytics was
  performed.

## Next owner gate

This evidence-only PR requires G-08 before merge. After merge, exact-main regression must stay green
before Vision real-provider acceptance is treated as officially closed on `main`. The next program
milestone is an offline plan and separately gated acceptance sequence for real ASR and the remaining
Flow A transcript/scene/reframe/TTS/subtitle/audio/human-review path. This PR grants no ASR call,
credential, spend, deployment or publishing authority.
