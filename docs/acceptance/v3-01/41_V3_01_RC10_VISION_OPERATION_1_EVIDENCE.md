# RC-10 Vision Operation 1 Evidence Review

## Verdict

```text
OPERATION: v3-01-rc10-openai-vision-call-01
PROVIDER EXECUTION: SUCCESS
ACCEPTANCE EVIDENCE: COMPLETE
OPERATION VERDICT: PASS
REAL-PROVIDER-TESTED, OPERATION 1: PASS
VISION CONSECUTIVE STATUS: 1/2 PASS
OPERATION 1: CONSUMED / SUCCEEDED
OPERATION 2: NOT APPROVED / LOCKED / NOT EXECUTED
PRODUCTION VERDICT: NO-GO
```

Exactly one separately owner-authorized OpenAI Vision operation ran on immutable
`vf-v3-01-rc10` at `c2b1aec2d54dd90bcb486f8a68c97746b39963aa`. It completed with one
attempt, no retry, no fallback, strict structured output, complete request/response and usage/cost
evidence, durable safety state and a clean secret scan. This is valid real-provider evidence for
Operation 1. It is not production-path or human-quality acceptance and does not authorize a second
operation.

The complete machine-readable run is
[`vf-v3-01-20260902T143651Z-c2b1aec-op1`](../../../evidence/v3-01/vf-v3-01-20260902T143651Z-c2b1aec-op1/).
Its preserved source receipt is
[`provider/operation-1-result.json`](../../../evidence/v3-01/vf-v3-01-20260902T143651Z-c2b1aec-op1/provider/operation-1-result.json),
SHA-256 `11fd1f7cb8eca120964033aba098e051d2d380713c52ceffec02979a77c9a620`.
No missing field was reconstructed.

## Exact authority and runtime binding

| Field | Evidence |
|---|---|
| Executable RC | `vf-v3-01-rc10` / `c2b1aec2d54dd90bcb486f8a68c97746b39963aa` |
| Governance main | `fd78a1690a5a2fd7b07e9e7822deda834f02ea6d` |
| Executable RC CI | `33527973264`, completed/success |
| Governance-main CI | `33532594395`, completed/success |
| Dual-CI provenance SHA-256 | `fcc59170f09dcebe5abe8afdb0e2ae76f0509aecdb525a22c652dae64c752a49` |
| Executable-tree SHA-256 | `f1f75f632ca3b1380985c5a532c9f4c601e39d45276135666f335cc3d041125c` on both RC and governance main |
| Provider/model/capability | `openai-vision` / `gpt-5-mini` / `vision` |
| Bundle SHA-256 | `30f4ffd9353a00b7fdf97d0998dce43798937a2c577ca3fa618c947bbb8040e1` |
| Execution-scope SHA-256 | `a77a2e38d604214dbcaf0933cbdbf6f2fafa6ee258369e1a629ef5b0d55c6cc0` |
| Operation authority SHA-256 | `c47fc135155bf985af9f5a16f6f921ecb1879fecbd563a660d1cfe4a3551658d` |
| Asset SHA-256 | `a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e` |
| RightsRecord SHA-256 | `f469930a74b477751fc4417774b486ccbf2d7822487478875e099552c83e06ba` |
| Runtime image | `sha256:7beaeb6622201617b0f30ed9f26f8d93845777507d6141d91169cb42936568d6` |

G-01-A, G-02-A and G-03-A are `V3-01-APP-038`, `V3-01-APP-039` and
`V3-01-APP-040`. The exact operation authority is retained at
[`governance/operation-1-authority.json`](../../../evidence/v3-01/vf-v3-01-20260902T143651Z-c2b1aec-op1/governance/operation-1-authority.json).
The credential value is absent; only its approved alias is named.

## Provider and structured-output evidence

| Field | Result |
|---|---|
| Provider request ID | `req_1384cf2d00534d5f8f23a604cc51a1ee` |
| Client request ID | `vf-276955d628ad4e12a3b5e06bdebe7222` |
| Provider response ID SHA-256 | `2fa8473b49ecf408685b90cb84fca83ae767e0c1852b40dfe9737fd0bbd32961` |
| Request SHA-256 | `138d70333ff7df29f6c986b30f5c251f6c5b6b3ee7d969846f73e2931a4f22a8` |
| Response SHA-256 | `02f8efbc3da74ecd8b172dc637fcdfdd96bafb207ef9f8789572e978c2b3d61f` |
| Structured output | PASS; one frame |
| Evidence writer | primary file written; fallback not used |
| Provider timeout | none |
| Latency | `27,790.325 ms` |

The structured frame contains the expected scene, OCR, object, crop, quality and confidence fields.
The receipt reports `structured_schema_pass=true`, request and response hashes present, and no
secret recorded.

## Usage and VND reconciliation

| Field | Result |
|---|---:|
| Input tokens | 1,996 |
| Cached input tokens | 0 |
| Output tokens | 2,134 |
| Atomic reservation | 500 VND |
| Actual provider cost | `125.181420 VND` |
| Durable charged cost | `125.1814 VND` |
| Reserved after reconciliation | `0.0000 VND` |
| Acceptance-window envelope | 1,250 VND |

The actual cost is supported by the provider usage receipt and is below the reservation. This
evidence PR performs zero provider calls, reads zero credentials and incurs 0 VND.

## Durable safety and containment

| Control | Result |
|---|---|
| Durable ledger | 1 operation / 1 attempt / 1 budget day / 1 circuit |
| Operation 1 | `succeeded`, consumed, one attempt |
| Retry / fallback | `0 / 0` |
| Circuit | `closed`, consecutive failures `0` |
| Duplicate re-preflight | `DUPLICATE_OPERATION_BLOCKED` |
| Operation 2 ledger row | absent |
| Secret scan | PASS; zero real-key-pattern matches |
| Post-run | runner stopped; gate unmounted; PostgreSQL stopped cleanly; ledger volume preserved |
| RC worktree | exact RC-10 clean |

## Acceptance impact

- `EV-V3-RC10-VISION-OP1-PASS-001` is a PASS record on the `real-provider-tested` axis for this
  exact operation.
- `VIS-01`, `OPS-01`, `OPS-03`, `OPS-04` and `OPS-09` gain the operation evidence ID.
- The aggregate `VIS-01` real-provider column stays `NOT_TESTED` until a separately approved
  Operation 2 produces a second consecutive PASS on the same RC-bound contract.
- Vision status is therefore **1/2 consecutive PASS**, not complete.
- `V3-01-GAP-003`, `V3-01-GAP-010` and `V3-01-GAP-013` remain `IN_PROGRESS`; this run narrows them
  but does not close ASR/reframe, production-like multi-instance, broader rights/retention,
  production-path or human-quality work.
- Operation 1 is consumed and cannot be repeated. Operation 2 remains not approved and locked.
- Production stays `NO-GO`; no deployment, public ingress, publishing or production analytics was
  performed.

## Next owner gate

This evidence-only PR must receive a new G-08 before merge. A G-08 merge decision does not authorize
Operation 2. Only after the evidence PR merges and exact-main checks stay green may the owner review
this evidence and decide separately whether to authorize RC-10 Operation 2.
