# Gap register

The canonical, lossless register is [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). This summary is
derived from the audit captured on `2026-08-27`, updated through locked NO-GO RC-13
`1e0146b44b19a5afcef267132d71d36d24a952e4`, merged V3-01-21 PR #46 and the fresh zero-call RC-13
ASR governance proposal. Historical RC-5
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
consumed, but its authority is retired; operation 2 is locked. V3-01-17 is merged and exact-main
tested in RC-10. PR #37 merged governance-only, PR #38 merged the first PASS evidence, and dual-CI
provenance stayed valid. Separately authorized RC-10 Operations 1 and 2 completed with complete
evidence. Both are consumed/succeeded. PR #39 then merged the consecutive evidence as
`fd0db431d2e3786b6b07dcb4b47b7bc74cfa7aed`; exact-main CI `33703619599` passed 5/5 with unchanged
executable and receipt hashes. Vision is officially 2/2 consecutive real-provider PASS.
Production-path and quality acceptance are not promoted. PR #40 then merged the Vision closure/ASR
design as `4c74fa18a86b29ae8324885dacc6fdbca74ad066`; exact-main CI `33706971864` passed 5/5 and the
executable tree stayed unchanged. V3-01-18 now provides source/mock evidence for the fail-closed
OpenAI ASR adapter and compatibility contract only. PR #41 then merged that executable path as
RC-11. RC-11 Operation 1 later blocked pre-call on the durable multi-asset rights mismatch, and
V3-01-20 fixed that path in RC-12. PR #45 merged the exact RC-12 ASR governance scope; the separately
authorized Operation 1 passed safety preflight and reached a real provider response, but strict
mapping/validation failed with `OPENAI_TRANSCRIPTION_RESPONSE_INVALID`. The operation is consumed,
acceptance is `REVIEW_REQUIRED`, actual provider cost is unknown and its 500 VND ledger charge is
only conservative safety accounting. No accepted transcript, usage receipt or exact validation path
was retained. V3-01-21 therefore adds zero-call response diagnostics and alias-aware secret scanning
without reconstructing the failed response. PR #46 merged that remediation, exact-main CI
`33976046393` passed 5/5 and RC-13 was locked. The fresh bundle binds new operation IDs and the
unchanged approved assets, but stays unmounted with both operations unauthorized. RC-12 Operation
2 remains retired/locked; ASR real-provider PASS evidence remains absent.

| Severity | Open | In progress | Remediated, gate pending | Total | Production effect |
|---|---:|---:|---:|---:|---|
| P0 | 1 | 8 | 1 | 10 | all unverified P0 work still blocks release-candidate GO |
| P1 | 2 | 3 | 0 | 5 | blocks production hardening/full acceptance |
| P2 | 1 | 0 | 0 | 1 | tracked maintenance risk |
| Total | 4 | 11 | 1 | 16 | default verdict remains NO-GO |

`V3-01-GAP-001` is technically remediated in local/CI and disposable Docker evidence and is merged
through PR #13. V3-01-02 through V3-01-08 are merged through PR #14 through PR #20. GAP-002,
GAP-003, GAP-004, GAP-005, GAP-006, GAP-008, GAP-009, GAP-010, GAP-011, GAP-013 and GAP-016 remain
`IN_PROGRESS`. RC-10 Vision is 2/2 consecutive real-provider PASS, while ASR/reframe,
production-like safety and broader rights coverage remain open. The bounded G-08 decisions through
PR #46 are consumed. RC-12 Operation 1 is consumed/failed/`REVIEW_REQUIRED`; Operation 2 is retired
and locked. RC-13 is locked with an unmounted proposed gate; the governance PR requires its own
G-08 and grants no operation authority.
Historical RC-3 and RC-5 operation
1 IDs are consumed and permanently locked; RC-5 operation 2 is also locked. RC-6 operation 1 is
not consumed, but its failed-window authority is retired; operation 2 is locked. RC-7 operation 1 is
consumed after one timeout and its authority is retired; operation 2 is locked. RC-8 has no live
  operation authority and is retired from live acceptance. RC-9 is locked; operation 1 is not
  consumed but its failed provenance authority is retired, and operation 2 is locked. RC-10 is locked;
  Operations 1 and 2 are consumed/succeeded with complete PASS records; no further Vision operation
  is required or authorized.
Production remains undeployed and unverified.

## P0 release blockers

| Gap | Short description | Containment |
|---|---|---|
| V3-01-GAP-002 | research/originality/claim-linked script incomplete | measured fixture contract only; no production-ready claim |
| V3-01-GAP-003 | aggregate real ASR/reframe acceptance incomplete; Vision sub-scope complete | RC-10 Vision is officially 2/2 consecutive real-provider PASS; RC-12 Operation 1 remains consumed/`REVIEW_REQUIRED`; RC-13 contains the diagnostic remediation and an unmounted fresh gate, but neither operation is approved and no accepted real ASR/reframe result exists |
| V3-01-GAP-004 | no real stock/AI media/ComfyUI evidence | receipt/decode/relevance fixture contract only; external execution false |
| V3-01-GAP-005 | no accepted Vietnamese voice/music mix | measured fixture audio contract only; eSpeak remains dev/CI |
| V3-01-GAP-006 | no official publish/analytics/Flow C | measured fixture acceptance only; all external actions remain gated |
| V3-01-GAP-007 | no production-like staging or production path | no deployment/route |
| V3-01-GAP-008 | production-like backup/restore/image rollback incomplete | local disposable drill only; no production state touched |
| V3-01-GAP-013 | broader real-asset rights coverage incomplete | both RC-10 operations retained narrow Vision rights; RC-12 preflight proved exact asset-specific selection for WAV 01 and RC-13 revalidates both unchanged ASR RightsRecords offline, while accepted real ASR, final-render retention and public-output rights remain absent |
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
  evidence offline. RC-10 operations 1 and 2 now prove two complete real-provider operations with
  atomic reservation, actual VND reconciliation, a closed circuit, duplicate blocking and complete
  primary evidence. Vision is 2/2 consecutive PASS. RC-12 ASR Operation 1 additionally proves that
  durable multi-asset rights and provider dispatch no longer block the path, but strict response
  mapping failed, actual cost stayed unknown, and the primary writer fell back because the legacy
  scanner treated an approved credential alias as a secret value. V3-01-21 records value-free
  validation issue paths/codes, allowlisted response metadata and request/response hashes for future
  failures, and distinguishes aliases from real credential values. Production-like multi-instance
  safety remains unaccepted.
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

RC-11 ASR Operation 1 later passed all earlier non-secret bootstrap checks but stopped at durable
rights preflight because the two-asset gate used `rights_records[]` and the durable controller still
projected legacy `rights_record`. The immutable receipt records `BLOCKED_PRE_CALL`, not consumed,
zero provider calls, zero credential reads, zero VND and ledger `0|0|0|0`; that authority is
retired and Operation 2 remains locked. Evidence `EV-V3-DURABLE-MULTI-ASSET-RIGHTS-001` proves the
V3-01-20 source/mock correction and durable/non-durable parity only. GAP-003 and GAP-013 remain
`IN_PROGRESS`; no real-provider, production-path or quality axis changes.

PR #44 then merged V3-01-20 as locked RC-12 `ca5483c889742c27af3368b9b487350d7daa217d` after
exact-main CI `33889772222` passed 5/5. `EV-V3-RC12-ASR-GATE-001` binds fresh RC-derived operation
IDs, a new dated scope and the unchanged exact assets/transcripts/RightsRecords. PR #45 merged that
governance scope as `f765f216f90b0d05071cc7c873a2edb6d5bdcec4`; governance-main CI `33894628759`
passed. The separately authorized Operation 1 passed preflight, resolved the credential once and
reached a provider response, then failed strict response validation. The immutable review record
keeps request ID/response hash and durable counts but no accepted transcript, request hash, usage or
actual-cost receipt; those missing values remain missing. The operation is consumed/failed and
`REVIEW_REQUIRED`; its 500 VND charge is not actual cost. Operation 2 is retired/locked.

V3-01-21 adds `EV-V3-ASR-RESPONSE-DIAGNOSTICS-001` as zero-call source/mock evidence. It introduces
a shared value-free diagnostic contract for `structured_output_validation`, allowlists safe provider
metadata, preserves deterministic request/response hashes when available and records precise
validation paths/codes without raw values. A representative synthetic missing-words fixture is
explicitly not presented as the unknown RC-12 response shape. The canonical secret scanner now
permits recognized credential-reference aliases while still rejecting OpenAI-style keys, bearer
tokens and assigned secret values. RC-12 evidence is not reconstructed or promoted. GAP-003,
GAP-010 and GAP-013 remain `IN_PROGRESS`; ASR real-provider remains `NOT_TESTED` and production is
`NO-GO`.
