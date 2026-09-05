# Owner gate register

G-00 and the completed bounded G-08 actions through PR #46 have approval records or recorded owner
decisions. RC-4 remains
evidence of a fail-closed executable-contract blocker. RC-5 operation 1 consumed its exact G-01-A,
G-02-A, G-03-A and separate operation authority; provider execution succeeded but acceptance
evidence is incomplete, so the result is permanently `REVIEW_REQUIRED`. Operation 2 is not
approved. RC-6 is locked; its separately authorized operation 1 stopped pre-call/not consumed on a
limits-contract mismatch, and that authority is retired. Operation 2 is locked. Historical RC-3,
RC-5 and RC-6 authorities grant no further call. RC-7 operation 1 later ran once, timed out and is
consumed/`REVIEW_REQUIRED`; its authority is retired and operation 2 is locked. RC-8 is locked
NO-GO and retired from live acceptance because its provider/controller timeout
architecture remained shared. It has no operation authority. RC-9 operation 1 later received a
separate bounded authority but stopped before credential read, reservation, ledger mutation or
provider dispatch on an ambiguous single-CI bootstrap field. It is not consumed, but that authority
is retired; operation 2 remains locked. V3-01-17 is merged in locked RC-10. Fresh G-01-A/G-02-A/
G-03-A records, governance-only PR #37, evidence-only PR #38, both post-merge governance-main CI
runs and separate exact authorities for Operations 1 and 2 were verified. Both operations succeeded
with complete evidence and are consumed. PR #39 merged the consecutive evidence and exact-main CI
`33703619599` passed 5/5 with unchanged executable and receipt hashes. Vision is officially 2/2
consecutive PASS; no further standalone Vision operation is authorized. Use
`schemas/approval-record.schema.json` for each later decision; no approval is implied by CI success,
an RC tag or the failed attempt.

PR #40's bounded G-08 is recorded as `V3-01-APP-042` and consumed by merge commit
`4c74fa18a86b29ae8324885dacc6fdbca74ad066`; exact-main CI `33706971864` passed 5/5 and no RC-11
was created by that docs-only merge because the executable tree did not change. PR #41 subsequently
merged V3-01-18 as exact RC-11 `207ff9fee5557eb0976f575c9263b61d995b20a0`; its G-08 is recorded
as `V3-01-APP-043`, and exact-head/exact-main CI passed. The owner has now selected `whisper-1`,
approved G-02-ASR v1.1, and approved two exact WAV/RightsRecord inputs. `V3-01-APP-044` through
`V3-01-APP-046` bind those decisions to the dated scope. PR #42 merged governance-only as
`8ad490c02c36aafe9447a3eb0766a1d1f1f122d7`; the executable candidate remains RC-11. The owner
subsequently granted one separate authority for Operation 1 only within its exact acceptance
window. This offline-preparation package neither executes nor extends that authority. The bundle
remains unmounted outside execution; Operation 2 is not approved.

PR #43 later merged the offline evaluator/TTS/G-11 preparation as governance/tests only at
`090f9085ccccf8ef30b926d7cc04a6c8a402128e`. RC-11 ASR Operation 1 subsequently stopped
`BLOCKED_PRE_CALL` before credential, reservation, ledger and provider boundaries on the durable
multi-asset RightsRecord mismatch. It is not consumed, but its dated authority/window is retired;
Operation 2 remains locked. At that checkpoint V3-01-20 was a new source/mock remediation requiring
its own G-08. No earlier G-01/G-02/G-03-ASR record or operation authority authorizes an RC-12 call.

The owner then approved PR #44 under G-08. It merged as exact RC-12
`ca5483c889742c27af3368b9b487350d7daa217d`; exact-main CI `33889772222` passed 5/5 and annotated
`vf-v3-01-rc12` peels to that commit. Records `V3-01-APP-048` through `050` rebind the exact
provider/budget/unchanged-rights scope to fresh RC-12 operation IDs and a proposed new window.
PR #45 later merged that governance bundle as `f765f216f90b0d05071cc7c873a2edb6d5bdcec4`; its bounded
G-08 is recorded as `V3-01-APP-051` and governance-main CI `33894628759` passed. The owner then
granted a separate one-attempt authority for Operation 1. It reached a provider response but failed
strict response validation, is consumed/`REVIEW_REQUIRED`, and cannot be reused. Actual cost is
unknown; 500 VND is only the conservative safety charge. Operation 2 is locked and retired.
PR #46 then merged V3-01-21 as locked RC-13
`1e0146b44b19a5afcef267132d71d36d24a952e4`; exact-main CI `33976046393` passed 5/5 and its
source G-08 is recorded as `V3-01-APP-052`. Fresh records `V3-01-APP-053` through
`V3-01-APP-055` rebind provider, budget and unchanged rights to new RC-13 operation IDs and a
proposed window. This governance bundle is unmounted, neither operation is approved or executed,
and its draft PR requires a new G-08 before merge.

| Gate | Decision | Current state | Minimum evidence/decision |
|---|---|---|---|
| G-00 | production acceptance scope and remediation sequence | APPROVED — `V3-01-APP-001` | local/CI remediation and draft PRs only; no merge/deploy/provider/publish authority |
| G-01 | real-provider credential aliases/scopes | RC-13 ASR `V3-01-APP-053` binds only `openai-transcription / whisper-1 / asr / vi` and the credential alias; it grants no credential read or call | governance merge, dual-CI/equality proof and a separate exact Operation 1 authority are still required |
| G-02 | VND provider budgets and cost controls | RC-13 ASR `V3-01-APP-054` proposes 500 VND/op and 1,250 VND/window with checked-in budget 0; no reservation/spend occurred | any scope/window mutation invalidates the rebind; a separate operation decision remains mandatory |
| G-03 | owned inputs, rights and provenance policy | RC-13 ASR `V3-01-APP-055` revalidates both unchanged WAV/transcript/RightsRecord hashes without extending publishing/training/resale rights | broader final-output rights remain open; this record is not runtime authority |
| G-04 | production-like staging execution | PENDING | locked commit/images, isolated topology and rollback plan |
| G-05 | exact final video/caption/thumbnail | PENDING | exact artifact hashes and completed quality report |
| G-06 | one official external publication | PENDING | target, visibility, time, idempotency and takedown plan |
| G-07 | takedown/delete if needed | PENDING | remote ID, reason and impact; otherwise no deletion |
| G-08 | remediation/evidence PR merge | PR #46 source decision is consumed and recorded as `V3-01-APP-052`; the RC-13 governance rebind is a separate draft PR | a new explicit G-08 decision is required before merging the RC-13 gate; it grants no runtime authority |
| G-09 | deploy locked RC | PENDING | image digest, migrations, backup and rollback |
| G-10 | accept backup/restore/RPO/RTO | PENDING | completed isolated restore report and measured result |
| G-11 | accept final quality | PENDING; schema, 27-check template and full-watch/listen checklist prepared offline | exact final video and dependent artifact hashes, named reviewer, UTC timestamps, desktop/mobile full watch, headphone/phone-speaker full listen and all checks PASS |
| G-12 | sign GO, CONDITIONAL GO or NO-GO | PENDING | final bundle, complete matrix and gap register |

## Approval semantics

An approval must identify the gate, owner, UTC time, commit/RC, environment, bounded scope, evidence
IDs, expiry and decision. Changing commit, artifact, provider, platform target, budget, environment or
time window invalidates or narrows the approval.

The current allowed scope is repository inspection, LOCAL/CI validation, redacted evidence and a
draft zero-call RC-13 ASR governance PR. The PR #12/#13 sequence and PR #14/#15/#16/#17/
#18/#19/#20/#22/#23/#24/#25/#26/#27/#28/#29/#30/#31/#32/#33/#34/#35/#36/#37/#38/#39/#40/#41/#42/#43/#44/#45/#46 merges are complete and their G-08 decisions cannot be
reused. RC-3 IDs are locked, RC-4 remains blocker evidence, and RC-5 operation 1 is consumed/
`REVIEW_REQUIRED`; RC-5 operation 2 is locked. RC-6 operation 1 is blocked pre-call/not consumed,
its failed-window authority is retired, and operation 2 is locked. RC-7 operation 1 is consumed after
one timeout, its authority is retired, and operation 2 is locked. RC-8 is retired from live
acceptance and has no operation authority. RC-9 operation 1 is blocked pre-call/not consumed, its
  authority and G-01-A/G-02-A/G-03-A scope are retired, and operation 2 remains locked. RC-10
  Operations 1 and 2 each received one exact authority, succeeded once with complete evidence, and
  are consumed. The runner stopped and bundle was unmounted after each execution. No further Vision
  operation is required or authorized. Runtime defaults remain disabled.
RC-12 ASR Operation 1 remains consumed/failed/`REVIEW_REQUIRED`; RC-12 Operation 2 is retired and
locked. RC-13 Operation 1 is not approved/not executed and Operation 2 is not approved/locked.
This package includes no authority for a merge, ASR operation, credential-value read, provider call,
deployment, public route, publishing, analytics collection or production write. Records:
[`V3-01-APP-001`](approvals/V3-01-APP-001.json) and
[`V3-01-APP-002`](approvals/V3-01-APP-002.json),
[`V3-01-APP-003`](approvals/V3-01-APP-003.json), and
[`V3-01-APP-004`](approvals/V3-01-APP-004.json), and
[`V3-01-APP-005`](approvals/V3-01-APP-005.json), and
[`V3-01-APP-006`](approvals/V3-01-APP-006.json), and
[`V3-01-APP-007`](approvals/V3-01-APP-007.json), and
[`V3-01-APP-008`](approvals/V3-01-APP-008.json), and
[`V3-01-APP-009`](approvals/V3-01-APP-009.json),
[`V3-01-APP-010`](approvals/V3-01-APP-010.json),
[`V3-01-APP-011`](approvals/V3-01-APP-011.json), and
[`V3-01-APP-012`](approvals/V3-01-APP-012.json),
[`V3-01-APP-013`](approvals/V3-01-APP-013.json),
[`V3-01-APP-014`](approvals/V3-01-APP-014.json),
[`V3-01-APP-015`](approvals/V3-01-APP-015.json), and
[`V3-01-APP-016`](approvals/V3-01-APP-016.json), and
[`V3-01-APP-017`](approvals/V3-01-APP-017.json), and
[`V3-01-APP-018`](approvals/V3-01-APP-018.json),
[`V3-01-APP-019`](approvals/V3-01-APP-019.json),
[`V3-01-APP-020`](approvals/V3-01-APP-020.json),
[`V3-01-APP-021`](approvals/V3-01-APP-021.json),
[`V3-01-APP-022`](approvals/V3-01-APP-022.json),
[`V3-01-APP-023`](approvals/V3-01-APP-023.json),
[`V3-01-APP-024`](approvals/V3-01-APP-024.json),
[`V3-01-APP-025`](approvals/V3-01-APP-025.json),
[`V3-01-APP-026`](approvals/V3-01-APP-026.json),
[`V3-01-APP-027`](approvals/V3-01-APP-027.json),
[`V3-01-APP-028`](approvals/V3-01-APP-028.json),
[`V3-01-APP-029`](approvals/V3-01-APP-029.json),
[`V3-01-APP-030`](approvals/V3-01-APP-030.json),
[`V3-01-APP-031`](approvals/V3-01-APP-031.json),
[`V3-01-APP-032`](approvals/V3-01-APP-032.json),
[`V3-01-APP-033`](approvals/V3-01-APP-033.json),
[`V3-01-APP-034`](approvals/V3-01-APP-034.json),
[`V3-01-APP-035`](approvals/V3-01-APP-035.json),
[`V3-01-APP-036`](approvals/V3-01-APP-036.json),
[`V3-01-APP-037`](approvals/V3-01-APP-037.json),
[`V3-01-APP-038`](approvals/V3-01-APP-038.json),
[`V3-01-APP-039`](approvals/V3-01-APP-039.json),
[`V3-01-APP-040`](approvals/V3-01-APP-040.json), and
[`V3-01-APP-041`](approvals/V3-01-APP-041.json), and
[`V3-01-APP-042`](approvals/V3-01-APP-042.json),
[`V3-01-APP-043`](approvals/V3-01-APP-043.json),
[`V3-01-APP-044`](approvals/V3-01-APP-044.json),
[`V3-01-APP-045`](approvals/V3-01-APP-045.json), and
[`V3-01-APP-046`](approvals/V3-01-APP-046.json),
[`V3-01-APP-047`](approvals/V3-01-APP-047.json),
[`V3-01-APP-048`](approvals/V3-01-APP-048.json),
[`V3-01-APP-049`](approvals/V3-01-APP-049.json),
[`V3-01-APP-050`](approvals/V3-01-APP-050.json),
[`V3-01-APP-051`](approvals/V3-01-APP-051.json),
[`V3-01-APP-052`](approvals/V3-01-APP-052.json),
[`V3-01-APP-053`](approvals/V3-01-APP-053.json),
[`V3-01-APP-054`](approvals/V3-01-APP-054.json), and
[`V3-01-APP-055`](approvals/V3-01-APP-055.json). The secret-free consumed RC-10 operation
authorities are retained in
[`operation-1-authority.json`](../../../evidence/v3-01/vf-v3-01-20260902T143651Z-c2b1aec-op1/governance/operation-1-authority.json)
and
[`operation-2-authority.json`](../../../evidence/v3-01/vf-v3-01-20260902T162324Z-c2b1aec-op2/governance/operation-2-authority.json).
