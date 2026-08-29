# V3-01 RC-5 Vision acceptance window

## Decision boundary

```text
RC: vf-v3-01-rc5 / 26adafb2eeed4b4de1169db73a13e50a683e094c
RC STATUS: LOCKED, NO-GO, NOT DEPLOYED
G-08 PR #27: CONSUMED
G-01-A / G-02-A / G-03-A: REBOUND TO RC-5 WINDOW
GOVERNANCE BUNDLE: VERIFIED OFFLINE, NOT MOUNTED
OPERATION 1 AUTHORITY: PENDING
OPERATION 2 AUTHORITY: NOT GRANTED
EXTERNAL EXECUTION: false
PAID EXECUTION: false
CHECKED-IN BUDGET: 0 VND
GLOBAL KILL SWITCH: engaged
OPENAI CALLS IN THIS CHECKPOINT: 0
```

PR #27 merged V3-01-12 as
`26adafb2eeed4b4de1169db73a13e50a683e094c`. Exact-main CI run
`33194523231` passed Python, Studio, Renderer, Safety/Compose and Docker deterministic E2E.
Annotated tag `vf-v3-01-rc5` peels to that exact merge commit. RC-4 remains immutable evidence of
the earlier fail-closed executable blocker and is not eligible for live acceptance.

The governance records in this checkpoint do not modify executable RC-5. They prepare a new
hash-bound, dated scope and remain inactive until a separate owner decision authorizes operation 1.

## Exact RC-5 scope

| Field | Bound value |
|---|---|
| Provider | `openai-vision` |
| Model | `gpt-5-mini` |
| Capability | `vision` |
| Credential reference | `secret://openai/codex-video` only; no value is stored |
| RC tag | `vf-v3-01-rc5` |
| RC commit | `26adafb2eeed4b4de1169db73a13e50a683e094c` |
| Asset | `g03-a-owned-vision-test.png` |
| Asset SHA-256 | `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e` |
| RightsRecord canonical SHA-256 | `f469930a74b477751fc4417774b486ccbf2d7822487478875e099552c83e06ba` |
| Execution-scope SHA-256 | `6a5955943f0b8291ee02c3d10fbf60fe627b9968b75171dfa2a2c730264f58ae` |
| Raw bundle SHA-256 | `e4c4604bbbfa4331d8fccf7c7ca41b23d3f1aff0472fddfa71fca3d9cb040e7f` |
| UTC window | `2026-08-29T14:00:00Z` through `2026-08-29T18:00:00Z` |
| Vietnam time | `21:00 29/08/2026` through `01:00 30/08/2026` |

The verified bundle is
[`V3-01-GATE-RC5-OPENAI-VISION-A.json`](V3-01-GATE-RC5-OPENAI-VISION-A.json).
It embeds exact copies and canonical hashes of the three rebound approval records:

- G-01-A: `V3-01-APP-020`, SHA-256
  `85b758205e0b10b0adddd180297d5316bce475d5ea2e51f7040a5cff261eb5f6`;
- G-02-A: `V3-01-APP-021`, SHA-256
  `292beee52ae110975c5ad54719d07f173346dc673bda0201a66875f25f0eab09`;
- G-03-A: `V3-01-APP-022`, SHA-256
  `4f35a6de5e11bd8c49f4ac6ffc0fbf65a1d378253613512fa8a55871e494e034`.

## Immutable operations

The executable derivation helper produced exactly:

1. `v3-01-rc5-openai-vision-call-01`
2. `v3-01-rc5-openai-vision-call-02`

Neither operation is authorized by this document. All RC-3 and RC-4 operation identifiers remain
locked and cannot validate against RC-5. Operation 2 requires its own later decision even if
operation 1 passes.

## Budget and execution envelope

- 500 VND atomic reservation per operation;
- 1,250 VND maximum for the entire window;
- one image, maximum 2048 by 2048, detail `high`;
- input accounting ceiling 16,384 tokens;
- output ceiling 4,096 tokens;
- timeout 60 seconds;
- concurrency one;
- one attempt, no automatic retry;
- no fallback model or provider;
- window and budget day must both be 2026-08-29 UTC.

Checked-in runtime defaults remain zero-budget and disabled. The envelope becomes usable only for
the exact operation separately authorized by the owner and only after all loader, hash, time,
rights, budget and duplicate-operation checks pass.

## Activation conditions for operation 1

Every condition must hold simultaneously, otherwise execution remains at zero calls:

1. the governance-only rebind PR is merged and exact-main governance regression passes;
2. the runtime executes exact immutable RC-5;
3. the raw bundle hash, exact tag, exact commit and execution-scope hash match;
4. G-01-A, G-02-A and G-03-A records verify and are unexpired;
5. current UTC time is inside the bound four-hour window;
6. the exact RC-5 operation-1 ID is separately approved by the owner;
7. operation 1 is unconsumed and a 500 VND atomic reservation succeeds;
8. the exact asset and RightsRecord hashes match;
9. no retry, fallback, second operation, publish, deploy or analytics action is enabled.

## Current verdict and next decision

This checkpoint performed no credential read, provider request, deployment, ingress change,
publication or analytics write. It spent 0 VND. Overall remains **NO-GO**.

The next owner decisions are separate:

1. G-08 for the governance-only rebind PR;
2. only after that merge and exact-main governance verification, authority for
   `v3-01-rc5-openai-vision-call-01` within the stated window.
