# Gap register

The canonical, lossless register is [`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). This summary is
derived from the audit captured on `2026-08-27`, updated through RC-5
`26adafb2eeed4b4de1169db73a13e50a683e094c`, governance-only PR #28 main
`8fa96409b0db6ec6d4dc3c04f6e3aaab2f3201ee`, and RC-5 operation 1. Provider execution succeeded,
but request-level acceptance evidence was incomplete after post-call serialization failed. The
operation is consumed/`REVIEW_REQUIRED`; V3-01-13 is a zero-call remediation. No acceptance-axis
promotion occurred.

| Severity | Open | In progress | Remediated, gate pending | Total | Production effect |
|---|---:|---:|---:|---:|---|
| P0 | 1 | 8 | 1 | 10 | all unverified P0 work still blocks release-candidate GO |
| P1 | 2 | 3 | 0 | 5 | blocks production hardening/full acceptance |
| P2 | 1 | 0 | 0 | 1 | tracked maintenance risk |
| Total | 4 | 11 | 1 | 16 | default verdict remains NO-GO |

`V3-01-GAP-001` is technically remediated in local/CI and disposable Docker evidence and is merged
through PR #13. V3-01-02 through V3-01-08 are merged through PR #14 through PR #20. GAP-002,
GAP-003, GAP-004, GAP-005, GAP-006, GAP-008, GAP-009, GAP-010, GAP-011, GAP-013 and GAP-016 remain
`IN_PROGRESS`. The bounded G-08 record for PR #28 is exhausted. Historical RC-3 and RC-5 operation
1 IDs are consumed and permanently locked. RC-5 operation 2 was not approved. A future RC-6 must
use new G-01-A/G-02-A/G-03-A records, IDs, scope and window. Production remains undeployed and
unverified.

## P0 release blockers

| Gap | Short description | Containment |
|---|---|---|
| V3-01-GAP-002 | research/originality/claim-linked script incomplete | measured fixture contract only; no production-ready claim |
| V3-01-GAP-003 | no accepted real ASR/Vision/reframe evidence | RC-5 provider execution succeeded once, but incomplete serialized evidence keeps it `REVIEW_REQUIRED`; V3-01-13 repairs only future evidence writes offline |
| V3-01-GAP-004 | no real stock/AI media/ComfyUI evidence | receipt/decode/relevance fixture contract only; external execution false |
| V3-01-GAP-005 | no accepted Vietnamese voice/music mix | measured fixture audio contract only; eSpeak remains dev/CI |
| V3-01-GAP-006 | no official publish/analytics/Flow C | measured fixture acceptance only; all external actions remain gated |
| V3-01-GAP-007 | no production-like staging or production path | no deployment/route |
| V3-01-GAP-008 | production-like backup/restore/image rollback incomplete | local disposable drill only; no production state touched |
| V3-01-GAP-013 | no accepted real-asset rights coverage | RC-5 exact rights binding held, but its structured output was not retained; the consumed scope cannot authorize reuse or public output |
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
  durable-context fallback, while production-like multi-instance and accepted real-provider
  evidence remain absent.
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
operation 2 `NOT APPROVED` and production `NO-GO`. Missing request-level values stay `null`.
