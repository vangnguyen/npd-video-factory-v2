# V3-01-26 — RC-16 ASR W1 quota-failure evidence and re-acceptance decision

**DRAFT / OWNER G-08 PENDING / EVIDENCE-ONLY / ZERO-CALL. Production: NO-GO.**

Base governance main: `5ba7107ba414893467f5e0236ca8a965bdbb8f91`.
Executable candidate remains `vf-v3-01-rc16` at
`55b22f773dc108f6c51a1b52db825b1caa8e8a51`; executable-tree SHA-256 remains
`5025279241fb0b55e6fa26cc850c82a1fd5e4dc9fc4e15c43f716f50441e6ecd`.
This package changes only governance, evidence and focused validation. It performs no credential
read, reservation or provider call and creates no RC, operation, execution window or authority.

## Result frozen from the bounded operation

The separately authorized operation
`v3-01-rc16-openai-transcription-asr-call-01` passed exact-RC, dual-CI, executable-tree,
profile/prompt, bundle/scope, asset/RightsRecord, time, budget and duplicate preflight. It then made
exactly one request. OpenAI returned HTTP 429 with the safe classification
`insufficient_quota / credit_balance_exhausted` before a transcript or usage receipt existed.

| Field | Immutable result |
| --- | --- |
| Provider execution | FAILED — `PROVIDER_RATE_LIMITED` |
| Acceptance | `REVIEW_REQUIRED` |
| Provider request ID | `req_5665217b25ae455aa9dafc5ec5903c1b` |
| Request SHA-256 | `80c4b6c283bc17fabb97a2bbe63f21cea6564ee8e6db1d31be4c99b911c2129a` |
| Response SHA-256 | `23e8ca3925c70e8ae7d69cdbbf0d418ced372632868df81515bfece393f5b639` |
| Latency | `3955.547 ms`; no timeout |
| Attempts / retry / fallback | `1 / 0 / 0` |
| Transcript / WER / critical terms | unavailable; W1 quality was not evaluated |
| Actual provider cost | **UNKNOWN**; no usage/cost receipt |
| Safety-ledger charge | `500.0000 VND`; not an actual-cost claim |
| Reservation after reconciliation | `0.0000 VND` |
| Durable counts | `1 operation / 1 attempt / 1 budget day / 1 circuit` |
| Circuit / duplicate protection | closed, one consecutive failure / duplicate blocked |
| Secret containment | PASS; zero real-key findings |

Operation 1 is **CONSUMED / FAILED** and cannot be retried or reused. Operation 2 is
**NOT APPROVED / LOCKED** and has no ledger row. ASR stays **0/2 consecutive PASS**; Vision stays
**2/2 PASS**; production stays **NO-GO**. The machine-readable
[quota review](evidence/rc16-asr-w1-operation-1/operation-1-quota-review.json) binds all retained
hashes and the exact audit boundary.

## Credit follow-up

At `2026-09-10T14:57:17.6763135Z`, the owner reported that OpenAI API credit had been replenished.
This is recorded as `OWNER_REPORTED_NOT_LIVE_VERIFIED`: the evidence package does not read the
credential or call a provider merely to test billing. The statement resolves the owner-side action
in principle but does not revive a consumed operation, authorize Operation 2 or create a new
acceptance window.

The quota response is external billing evidence, not an ASR recognition-quality failure and not a
W1 prompt result. No WER, critical-term, timestamp, negative-insertion or transcript-completeness
status may be inferred from it.

## Fresh-lineage decision required

The canonical loader derives exactly two operation IDs from RC tag, provider, capability and slots
1/2. Flow A requires two consecutive accepted runs on one locked RC. Because RC-16 slot 1 is now
consumed/failed, authorizing slot 2 alone could produce at most one successful RC-16 run and cannot
close 2/2 consecutive acceptance.

Therefore this PR deliberately does **not**:

- reuse Operation 1;
- unlock or execute Operation 2;
- create `vf-v3-01-rc17` while the executable tree is unchanged;
- mutate the existing bundle/window; or
- change operation-ID derivation or runtime code.

After this evidence PR and exact-main regression, the owner must select and separately approve a
fresh two-slot lineage. The smallest operational option is a new acceptance identity pointing to
the unchanged executable commit/tree, but it is an explicit exception to the prior “no new RC when
the executable tree is unchanged” rule. The alternative is a source change adding an independently
versioned acceptance-series identity; that would itself require a new executable RC. Neither choice
is made implicitly here.

## Evidence integrity and validation

Local source receipts remain outside the repository and immutable. Their exact byte hashes are:

- operation result: `2778757191b29c6e35a6d238449a1b40bfa4622df99e81b6820a8e6798d19751`;
- evaluator input: `6b754d7d28226ae09d76334f162d357875a58a1e6bd1ca46860a1ace74426664`;
- post-run evaluation: `79d7acfe84b9e98010a49f13bab40b81297b4ba5dde8218e813e9ab64baa11be`;
- post-run verification: `618cd79440b65b1c27cd140aff7754a62ac1b182d57612f01c6b964c837e36bd`.

The PR must pass JSON/schema/link/checksum/secret validation, focused evidence tests, full repository
CI and `git diff --check`. Its own accounting is **0 provider calls / 0 credential reads / 0 live
reservations / 0 VND**. Stop at Owner G-08; no merge, RC, operation or runtime authority follows
from opening the draft.
