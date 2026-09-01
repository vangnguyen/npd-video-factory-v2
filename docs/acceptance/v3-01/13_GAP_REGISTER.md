# Gap register

The canonical, lossless register is [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). This summary is
derived from the audit captured on `2026-08-27`, updated through locked NO-GO RC-9
`256bda59eed028ddd642cdb0988c409c489fd655`, governance merge
`e48d7edebcbfb1bd4113c2e40ab4ce46c186f6e4` and V3-01-17 zero-call remediation. Historical RC-5
operation-1 provider execution succeeded,
but request-level acceptance evidence was incomplete after post-call serialization failed. The
operation is consumed/`REVIEW_REQUIRED`; V3-01-13 is now merged and exact-main tested. RC-6
operation 1 later blocked before provider dispatch with 0 calls/0 VND and remains not consumed; its
authority is retired and operation 2 is locked. RC-7 operation 1 later timed out once after entering
the provider path; it is consumed/`REVIEW_REQUIRED`, actual cost is unknown and operation 2 remains
locked. V3-01-15 is merged and mock-tested in RC-8; V3-01-16 is merged and mock-tested in RC-9,
where it separates provider HTTP timeout at 90 seconds from the controller hard envelope at
120 seconds. RC-9 operation 1 later stopped before credential read, reservation, ledger mutation or
provider dispatch because executable-RC CI and governance-main CI were conflated. It is not
consumed, but its authority is retired; operation 2 is locked. No acceptance-axis promotion
occurred.

| Severity | Open | In progress | Remediated, gate pending | Total | Production effect |
|---|---:|---:|---:|---:|---|
| P0 | 1 | 8 | 1 | 10 | all unverified P0 work still blocks release-candidate GO |
| P1 | 2 | 3 | 0 | 5 | blocks production hardening/full acceptance |
| P2 | 1 | 0 | 0 | 1 | tracked maintenance risk |
| Total | 4 | 11 | 1 | 16 | default verdict remains NO-GO |

`V3-01-GAP-001` is technically remediated in local/CI and disposable Docker evidence and is merged
through PR #13. V3-01-02 through V3-01-08 are merged through PR #14 through PR #20. GAP-002,
GAP-003, GAP-004, GAP-005, GAP-006, GAP-008, GAP-009, GAP-010, GAP-011, GAP-013 and GAP-016 remain
`IN_PROGRESS`. The bounded G-08 decision for PR #35 is consumed; V3-01-17 requires its own G-08.
Historical RC-3 and RC-5 operation
1 IDs are consumed and permanently locked; RC-5 operation 2 is also locked. RC-6 operation 1 is
not consumed, but its failed-window authority is retired; operation 2 is locked. RC-7 operation 1 is
consumed after one timeout and its authority is retired; operation 2 is locked. RC-8 has no live
operation authority and is retired from live acceptance. RC-9 is locked; operation 1 is not
consumed but its failed provenance authority is retired, and operation 2 is locked. V3-01-17 changes
executable contract code, so future live acceptance must use RC-10.
Production remains undeployed and unverified.

## P0 release blockers

| Gap | Short description | Containment |
|---|---|---|
| V3-01-GAP-002 | research/originality/claim-linked script incomplete | measured fixture contract only; no production-ready claim |
| V3-01-GAP-003 | no accepted real ASR/Vision/reframe evidence | RC-5 provider execution succeeded once but incomplete evidence keeps it `REVIEW_REQUIRED`; RC-6 blocked pre-call; RC-7 timed out once; RC-8 is retired; RC-9 blocked pre-call on CI provenance with 0 calls/0 VND; future acceptance requires RC-10 |
| V3-01-GAP-004 | no real stock/AI media/ComfyUI evidence | receipt/decode/relevance fixture contract only; external execution false |
| V3-01-GAP-005 | no accepted Vietnamese voice/music mix | measured fixture audio contract only; eSpeak remains dev/CI |
| V3-01-GAP-006 | no official publish/analytics/Flow C | measured fixture acceptance only; all external actions remain gated |
| V3-01-GAP-007 | no production-like staging or production path | no deployment/route |
| V3-01-GAP-008 | production-like backup/restore/image rollback incomplete | local disposable drill only; no production state touched |
| V3-01-GAP-013 | no accepted real-asset rights coverage | RC-5 exact rights binding held but its structured output was not retained; RC-6 produced no provider artifact; RC-7 produced no accepted provider artifact after timeout and grants no public-output authority |
| V3-01-GAP-016 | no human full-watch quality acceptance | Flow A/B approval hashes and thresholds enforced; no publish-ready claim |

## P1/P2 work

- `V3-01-GAP-009` (`IN_PROGRESS`): authenticated local operations snapshot, correlation,
  secret-redacted logs, alert previews and retention contracts exist; monitoring backend, accepted
  external alert delivery and the 48-hour locked-RC soak remain.
- `V3-01-GAP-010` (`IN_PROGRESS`): VND budgets, retry/poll/concurrency, circuit breaker, rights hook,
  artifact verification and global cost kill switch pass locally. V3-01-03 adds a PostgreSQL ledger,
  atomic cross-instance reservation, durable circuit/duplicate state, restart recovery and
  retention/health metrics. RC-5 operation 1 proved one successful durable attempt, atomic
  reservation, duplicate blocking, a closed circuit and `137.6287 VND` actual cost. Its structured
  payload/request IDs/hashes were not retained. V3-01-13 adds canonical serialization and a
  durable-context fallback in locked RC-6. V3-01-14 and the RC-7 gate bundle validate the corrected
  shared limits path; RC-7 operation 1 then proved durable one-attempt timeout/charge/duplicate
  behavior but did not retain provider receipt/usage or actual cost. V3-01-15 adds timeout-phase
  evidence offline, while
  production-like multi-instance and accepted real-provider evidence remain absent.
- `V3-01-GAP-011` (`IN_PROGRESS`): auth rate limiting, URL-import denial and bounded malicious-input
  tests pass. V3-01-03 adds quarantine-before-decoder, archive-signature denial, EICAR contract
  tests, clean-verdict promotion and an internal clamd/WAF design contract; approved internal
  scanner deployment and production public-ingress/WAF evidence remain. Local evidence is
  `EV-V3-MEDIA-SECURITY-001`.
- `V3-01-GAP-012`: GitHub `main` branch protection is disabled.
- `V3-01-GAP-014`: real Agent Hub HTTP bridge acceptance is absent.
- `V3-01-GAP-015`: GitHub Actions runtime deprecation warning.

V3-01-04 adds `EV-V3-FLOW-A-CONTRACT-001`: two distinct redacted fixture runs on one locked commit
pass the measured contract while the real-provider, production-path and human-quality axes remain
`BLOCKED`. It does not close GAP-003, GAP-005 or GAP-016.

V3-01-05 adds `EV-V3-FLOW-B-CONTRACT-001`, and V3-01-06 adds
`EV-V3-FLOW-C-CONTRACT-001`. The Flow C evidence measures provenance, deterministic scoring,
cross-stage hashes, publication safety, nullable analytics, explainable winner scoring and learning
lineage with zero external calls and zero VND spend. It moves GAP-006 to `IN_PROGRESS` only.

V3-01-09 adds `EV-V3-OPENAI-VISION-ADAPTER-001`: exact `gpt-5-mini` request/schema mapping,
bounded image/video frame evidence, request/response/artifact hashes, secret-safe alias resolution,
VND-only cost receipts and central timeout/retry/circuit/duplicate/rights/budget tests pass using
MockTransport. This moves GAP-003 from `OPEN` to `IN_PROGRESS`; ASR, a real Vision call,
production-path evidence and human quality remain absent.

V3-01-10 adds a hash-pinned verified gate loader, exact RC/approval/rights binding, a two-operation
allowlist, exact G-02-A limits, expiry checks and durable restart/atomic-reservation tests. Its one
internally generated RightsRecord was narrowly approved for RC-3 Vision acceptance. Operation 1
was executed once and failed non-retryably; `EV-V3-OPENAI-VISION-OP1-FAILED-001` retains the
secret-free result. The gate/rights/ledger boundaries held, but no structured/provider/usage receipt
was produced. GAP-003, GAP-010 and GAP-013 stay `IN_PROGRESS`; no real-provider axis changes.

No gap is `VERIFIED` or newly closed by V3-01-07 through V3-01-10. `REMEDIATED` means its code and prescribed local/mock
evidence pass on the locked commit; it still needs any applicable
production-path evidence before `VERIFIED`. Owner exceptions must name an expiry and approval record; no implicit
exception exists.

V3-01-11 makes `track_hint` required-nullable, recursively validates strict object schemas and adds
secret-free durable provider error evidence for HTTP, transport, parse, refusal/incomplete,
validation and usage failures. PR #26 merged under `V3-01-APP-018`; exact-main CI passed and RC-4
was locked with 0 remediation calls and 0 VND spend. Audit then found that the executable operation
allowlist still hard-coded RC-3 IDs. This blocker is retained as RC-4 evidence and prevents live use.

V3-01-12 replaces that hard-coded contract with deterministic IDs derived from exact RC tag,
provider, capability and ordinal, while the verified loader also binds commit, model,
execution-scope hash, asset hash and acceptance window. Its required regression matrix is mock-only;
PR #27 merged and `vf-v3-01-rc5` was locked. Governance-only PR #28 later rebound the scope without
changing executable RC-5. Neither merge alone authorized a call or changed an acceptance axis.

V3-01-13 adds `EV-V3-EVIDENCE-SERIALIZATION-001` and
`EV-V3-RC5-VISION-OP1-REVIEW-001`. The first proves the canonical dataclass/Pydantic serializer,
deterministic SHA and secret-free durable fallback offline. The second permanently records provider
execution `SUCCESS`, acceptance evidence `INCOMPLETE`, operation 1 `CONSUMED/REVIEW_REQUIRED`,
operation 2 `NOT APPROVED` and production `NO-GO`. Missing request-level values stay `null`. PR #29
merged that remediation and exact-main CI passed 5/5 before `vf-v3-01-rc6` was locked.
`EV-V3-RC6-VISION-REBIND-001` then proves the fresh RC-6 IDs, approval/rights hashes, dated VND
envelope and unmounted bundle offline. It grants no operation authority and closes no gap.

RC-6 operation 1 subsequently received a separate bounded authority but stopped fail-closed before
credential read, reservation, ledger creation or provider dispatch. The result is permanently
classified `BLOCKED PRE-CALL / NOT CONSUMED`: provider calls 0, cost 0 VND, ledger `0|0|0|0`,
operation 2 locked and production `NO-GO`. The RC-6 authority is retired despite the unconsumed ID.
V3-01-14 adds the shared strict `ProviderOperationAuthorityLimits` contract/adapter and rejects
missing, legacy, extra, wrong-type or wrong-amount fields offline. It fixes only the future pre-call
contract; GAP-003, GAP-010 and GAP-013 remain `IN_PROGRESS`. RC-7 operation 1 later timed out once,
is consumed and cannot be retried; operation 2 remains locked.

PR #31 merged V3-01-14 as exact RC-7 and exact-main CI passed 5/5. Evidence
`EV-V3-RC7-VISION-REBIND-001` proves the fresh RC-7 IDs, canonical per-operation/window limits,
approval/rights hashes and new dated scope offline. PR #32 merged the governance rebind without
changing RC-7. The separately authorized operation 1 later timed out once; evidence
`EV-V3-RC7-VISION-OP1-TIMEOUT-001` preserves the consumed/`REVIEW_REQUIRED` result, unknown actual
cost and locked operation 2. `EV-V3-PROVIDER-TIMEOUT-001` covers only the zero-call V3-01-15
remediation. GAP-003, GAP-010 and GAP-013 remain `IN_PROGRESS`.

PR #34 merged V3-01-16 as exact RC-9 and exact-main CI passed 5/5. Evidence
`EV-V3-SPLIT-TIMEOUT-ENVELOPE-001` proves the canonical 90-second provider / 120-second controller
contract offline. `EV-V3-RC9-VISION-REBIND-001` proves the fresh RC-9 IDs, unchanged 500/1,250 VND
limits, split timeout envelope, approval/rights hashes and dated execution-scope hash in an
unmounted bundle. PR #35 merged the governance scope and a separate owner decision authorized only
operation 1. It then blocked before provider dispatch on ambiguous CI provenance with 0 calls/0 VND;
the operation is not consumed, its authority is retired and operation 2 remains locked. V3-01-17
validates both CI roles offline. GAP-003, GAP-010 and GAP-013 stay `IN_PROGRESS`.
