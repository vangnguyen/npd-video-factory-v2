# V3-01 consolidation checkpoint verdict

## Executive verdict

```text
VERDICT: NO-GO
SCOPE: V3-01-21 after consumed RC-12 ASR response-validation failure; Vision 2/2 real-provider PASS; ASR real-provider NOT_TESTED
RELEASE CANDIDATE: RC-12 ca5483c889742c27af3368b9b487350d7daa217d LOCKED NO-GO; NOT DEPLOYED
LATEST EVIDENCE: EV-V3-ASR-RESPONSE-DIAGNOSTICS-001; source commit 75f693a; remediation 0 calls/0 credential reads/0 VND
DATE: 2026-09-05
OWNER DECISION: RC-12 OPERATION 1 CONSUMED/FAILED/REVIEW_REQUIRED; OPERATION 2 RETIRED/LOCKED; V3-01-21 REQUIRES NEW G-08
```

Feature freeze is active. The V2-11 baseline is healthy in deterministic CI and has strong
fail-closed publishing/provider boundaries, but it is not production-accepted.

## Summary

| Area | Result |
|---|---|
| Matrix catalog | 60 rows present |
| Implemented axis | 45 PASS, 15 FAIL |
| Mock-tested axis | 54 PASS, 1 FAIL, 5 NOT_TESTED |
| Real-provider-tested axis | 1 PASS, 35 NOT_TESTED, 24 N/A |
| Production-path-tested axis | 60 NOT_TESTED |
| Quality-accepted axis | 36 NOT_TESTED, 24 N/A |
| Flow A | BLOCKED overall; Vision real-provider 2/2 PASS and ASR safety/provider response reach proven, but RC-12 Operation 1 failed strict response validation and is consumed; ASR/reframe real-provider, production and quality axes remain blocked |
| Flow B | BLOCKED overall; measured two-run contract/mock PASS, real/provider/production/quality axes blocked |
| Flow C | BLOCKED overall; measured two-run contract/mock PASS, real-provider/production/quality axes blocked |
| Security | identity/RBAC/isolation local PASS; public/production ingress remains NO-GO |
| Cost | RC-10 Vision recorded `284.343280 VND` actual; RC-11 ASR Op1 cost 0 VND; RC-12 ASR Op1 has actual cost unknown and a 500 VND conservative safety charge, not an actual-cost receipt; V3-01-21 costs 0 VND |
| Rights/provenance | exact Vision asset passed twice; two exact unchanged WAVs, voices, owner-verified transcripts and RightsRecords are rebound to RC-12 only for bounded ASR acceptance; broader real/final-asset coverage absent |
| Backup/restore | local disposable drill PASS with 9/9 hashes, RPO 0s and RTO 33s; production-like DR and accepted RPO/RTO remain blocked |
| Observability/soak | authenticated local snapshot, correlation and seven alert previews PASS; no monitoring backend, alert delivery or 48-hour run |
| Gaps | 4 OPEN, 11 IN_PROGRESS, 1 REMEDIATED; P0=10, P1=5, P2=1 total |
| Allowed scope | LOCAL/CI V3-01-21 zero-call remediation, static/mock tests, redacted evidence and a draft source PR |
| Disabled scope | further provider calls, credential-value access, deploy, public ingress, publish, production analytics, external notifications |

## Critical failures

- identity/RBAC remediation is merged but remains undeployed and lacks production-path verification;
- no production-like target, deployed image digest or owner-accepted production-like DR drill;
- RC-10 Vision Operations 1 and 2 are complete consecutive real-provider PASS results. The Vision
  real-provider axis is officially closed after PR #39 and exact-main CI; real ASR and reframe
  acceptance remain absent, and no production-path or human-quality evidence exists;
- no official publish/analytics acceptance;
- no human full-watch acceptance or 48-hour soak;
- GitHub `main` is not protected.

## Evidence

- baseline run: `vf-v3-01-20260827T120208Z-cae40ed`;
- exact merged `main` and locked NO-GO RC-4 blocker evidence: `061ca5d03248d6721ef8dc7a53cf4608e7ebe79e` (`vf-v3-01-rc4`); annotated tag object `b32680a8f6e1bbfbff0dd7425bc5a231ef2ac6a5`;
- V3-01-10 PR #23 exact head: `40149c2b439c78e75fdd3ff8996c2ed8c3ec4575`; exact-main CI `33173094529` PASS; merged into RC-3;
- governance-only PR #24 merged as `a73bad37f1f3aa7c2347e6a76503246a46d3c112`; exact-main CI `33175813324` PASS 5/5; executable RC-3 unchanged;
- evidence/governance-only PR #25 merged as `2ab6b51d63b86c7e4cc9febe347929d8cc3f2e38`; exact-main CI `33182052862` PASS 5/5; executable RC-3 unchanged;
- V3-01-11 PR #26 exact head `a09919db67f23253bc45ff3171b99e220c25c599`; merged as `061ca5d03248d6721ef8dc7a53cf4608e7ebe79e`; exact-main CI `33189441083` PASS 5/5; `V3-01-APP-018` consumed;
- RC-4 post-lock audit: executable allowlist still named RC-3 operation IDs, so RC-4 is retained as fail-closed blocker evidence and prohibited from live acceptance;
- V3-01-12 PR #27 exact head `703fec6931c315b853ee4691aef5ce290510eb8b`; merged as `26adafb2eeed4b4de1169db73a13e50a683e094c`; exact-main CI `33194523231` PASS 5/5; `V3-01-APP-019` consumed;
- annotated `vf-v3-01-rc5` peels to `26adafb2eeed4b4de1169db73a13e50a683e094c`; fresh operation IDs and scope hash are recorded in an unmounted governance bundle;
- governance-only PR #28 merged as `8fa96409b0db6ec6d4dc3c04f6e3aaab2f3201ee`; exact-main CI `33226016184` PASS 5/5; executable RC-5 unchanged; `V3-01-APP-023` consumed;
- separate one-operation authority `V3-01-APP-024` was consumed by RC-5 operation 1 and cannot authorize operation 2 or reuse;
- RC-5 operation 1 evidence: provider execution `SUCCESS`, acceptance evidence `INCOMPLETE`, verdict `REVIEW_REQUIRED`, one attempt/no retry/no fallback, `137.6287 VND` actual cost; request-level missing fields remain `null`;
- V3-01-13 PR #29 exact head `2fc80e511e6ab0382b3a05b141764ea37725d245`; merged as
  `8df74a202dc2160e9358ca4cc9be54d989af2292`; exact-main CI `33261962445` PASS 5/5;
- annotated `vf-v3-01-rc6` peels to `8df74a202dc2160e9358ca4cc9be54d989af2292`; tag object
  `b285bfec8c7f398d56ec513cf35cd6f14fb5c596`; NO-GO and not deployed;
- RC-6 rebind evidence `EV-V3-RC6-VISION-REBIND-001` validates fresh operation IDs, exact
  provider/model/asset/RightsRecord, VND envelope, bundle SHA and scope SHA offline with 0 calls/0 VND;
- RC-6 operation-1 blocker receipt records `BLOCKED_0_CALL`, no provider request, no reservation,
  cost 0 VND and durable ledger `0|0|0|0`; this is fail-closed evidence only, not an acceptance-axis
  promotion;
- V3-01-14 PR #31 exact head `ff67fb05f32e300cdb4daac3fd29d8135a62879f`; merged as
  `94170ed42f6ffba4432f29750402eafe0d922a45`; exact-main CI `33321003243` PASS 5/5;
- annotated tag `vf-v3-01-rc7` peels to `94170ed42f6ffba4432f29750402eafe0d922a45`;
  tag object `14e1c09550aaa92c937e275bbe8d1e38c6ed8b8c`; NO-GO and not deployed;
- RC-7 rebind evidence `EV-V3-RC7-VISION-REBIND-001` validates the exact RC identity, fresh
  operation IDs, provider/model/capability, asset/RightsRecord, canonical authority limits,
  bundle SHA `ce772a941766b12a99943b9165cbf588c314e3d1b59543f103c7671a58856a44` and scope SHA
  `60d9898de38f9536ed3391ca81f1d59eca04b61537edad42e85597702c143a56` offline with 0 calls/0 VND;
- RC-7 operation evidence `EV-V3-RC7-VISION-OP1-TIMEOUT-001` freezes one consumed
  `PROVIDER_TIMEOUT`, no retry/fallback, actual cost unknown, 500 VND safety charge and locked
  operation 2; `EV-V3-PROVIDER-TIMEOUT-001` is the later zero-call remediation evidence only;
- V3-01-15 PR #33 merged as `68d4cf90004054075ebf0f33b9311a3419d8af4d`; exact-main CI
  `33412301663` passed 5/5; annotated `vf-v3-01-rc8` tag object
  `aaeefaa31b027fa77aa3bea13a1bbec5cefaefd6` peels to that commit; RC-8 is NO-GO, not deployed,
  has no live-operation authority and is retired from live acceptance;
- V3-01-16 is a zero-call source remediation that replaces the shared timeout field with explicit
  provider 90-second and controller 120-second fields; no real-provider, production-path or quality
  acceptance axis is promoted;
- PR #35 merged governance-only as `e48d7edebcbfb1bd4113c2e40ab4ce46c186f6e4`; governance CI
  `33499392585` passed 5/5 while executable RC-9 CI `33449162326` remained separately bound to
  `256bda59eed028ddd642cdb0988c409c489fd655`; RC-9 operation 1 then blocked pre-call with 0
  calls/0 VND and is not consumed, but its authority is retired;
- V3-01-17 dual-CI evidence SHA-256 is
  `95af692024f6573b839d8df384c02bf08581cef59b255b216c225bbde0b039e0`; both selected executable
  tree hashes equal `b57ef070664067f789424bf58f482f40087160a0e446e3e02aa2b1d45b4d9f53`;
- V3-01-17 PR #36 merged as `c2b1aec2d54dd90bcb486f8a68c97746b39963aa`; exact-main CI run
  `33527973264` passed 5/5; annotated `vf-v3-01-rc10` tag object
  `32bd6a78048a6ae92538a9195a1386318ebd72b8` peels to that commit;
- RC-10 rebind evidence `EV-V3-RC10-VISION-REBIND-001` validates fresh operation IDs, exact
  provider/model/asset/RightsRecord, dual-CI role separation, 90/120 timeout, VND envelope, bundle
  SHA `30f4ffd9353a00b7fdf97d0998dce43798937a2c577ca3fa618c947bbb8040e1` and scope SHA
  `a77a2e38d604214dbcaf0933cbdbf6f2fafa6ee258369e1a629ef5b0d55c6cc0` offline; bundle unmounted;
- governance-only PR #37 merged as `fd78a1690a5a2fd7b07e9e7822deda834f02ea6d`; governance-main
  CI `33532594395` passed, dual-CI provenance SHA is
  `fcc59170f09dcebe5abe8afdb0e2ae76f0509aecdb525a22c652dae64c752a49`, and both executable trees
  hash to `f1f75f632ca3b1380985c5a532c9f4c601e39d45276135666f335cc3d041125c`;
- RC-10 Operation 1 evidence `EV-V3-RC10-VISION-OP1-PASS-001` records provider request
  `req_1384cf2d00534d5f8f23a604cc51a1ee`, request SHA
  `138d70333ff7df29f6c986b30f5c251f6c5b6b3ee7d969846f73e2931a4f22a8`, response SHA
  `02f8efbc3da74ecd8b172dc637fcdfdd96bafb207ef9f8789572e978c2b3d61f`, complete structured
  output, actual `125.181420 VND`, one attempt, duplicate block and secret scan PASS; source evidence
  SHA is `11fd1f7cb8eca120964033aba098e051d2d380713c52ceffec02979a77c9a620`;
- RC-10 consecutive evidence `EV-V3-RC10-VISION-CONSECUTIVE-PASS-001` binds the Operation 1 receipt
  above to Operation 2 provider request `req_8c3597bb115e485ca4252bbe5cd30477`, response SHA
  `ff8a5d4a1200c09bfbda18db557d89c8d3b9763a95f29e69ac62e72460b299b7`, actual
  `159.161860 VND`, one attempt, duplicate block and secret scan PASS. The preserved Operation 2
  source receipt SHA is `deed47e573079bd53118859f616991aae42b420992aad84f39cbfb4bdb3df0a2`;
- both operations used request SHA
  `138d70333ff7df29f6c986b30f5c251f6c5b6b3ee7d969846f73e2931a4f22a8` but retain distinct
  response hashes as independent executions; total actual cost is `284.343280 VND`, durable
  reserved cost is zero, and the ledger contains two succeeded operations and two attempts;
- operation-1 evidence: `EV-V3-OPENAI-VISION-OP1-FAILED-001`, evidence SHA-256 `e94fcafcbab8adefb9506cb91d98010cdb1713ba79ce209ec2dfdb154f97fd2d`;
- locked V3-01-06 code-only commit: `c1f50c4941929120b815fda33acd75acd07f454a`;
- locked V3-01-07 code-only commit: `527fd1f482e4afa80105cb6ebab92545c10a79fc`;
- production image digest: none;
- evidence IDs: `EV-V3-BASE-001`, `EV-V3-STATIC-001`, `EV-V3-CI-001`,
  `EV-V3-SAFETY-001`, `EV-V3-DR-001`, `EV-V3-DR-OBS-001`,
  `EV-V3-RC-CONSOLIDATION-001`, `EV-V3-OPENAI-VISION-ADAPTER-001`,
  `EV-V3-VERIFIED-GATE-LOADER-001`, `EV-V3-OPENAI-VISION-OP1-FAILED-001`,
  `EV-V3-STRUCTURED-ERROR-EVIDENCE-001`, `EV-V3-RC-BOUND-ALLOWLIST-001`,
  `EV-V3-RC5-VISION-OP1-REVIEW-001`, `EV-V3-EVIDENCE-SERIALIZATION-001`,
  `EV-V3-RC6-VISION-REBIND-001`, `EV-V3-RC6-OP1-BLOCKED-001`,
  `EV-V3-AUTHORITY-LIMITS-001`, `EV-V3-RC7-VISION-REBIND-001`,
  `EV-V3-RC7-VISION-OP1-TIMEOUT-001`, `EV-V3-PROVIDER-TIMEOUT-001`,
  `EV-V3-RC10-VISION-OP1-PASS-001`, `EV-V3-RC10-VISION-CONSECUTIVE-PASS-001`;
- remote publication ID/URL: none;
- analytics snapshot IDs: none;
- restore report: local disposable `EV-V3-DR-OBS-001` PASS; production-like restore remains absent;
- owner approval IDs: `V3-01-APP-001` for G-00, `V3-01-APP-002` for only PR #12/#13,
  `V3-01-APP-003` for only PR #14, `V3-01-APP-004` for only PR #15,
  `V3-01-APP-005` for only PR #16, `V3-01-APP-006` for only PR #17,
  `V3-01-APP-007` for only PR #18, `V3-01-APP-008` for only PR #19,
  `V3-01-APP-009` for only PR #20, `V3-01-APP-010` for only PR #22,
  `V3-01-APP-013` for only PR #23, `V3-01-APP-014` for RC-3 G-01-A,
  `V3-01-APP-015` for RC-3 G-02-A, `V3-01-APP-016` for narrow RC-3 G-03-A,
  `V3-01-APP-017` for evidence-only PR #25, `V3-01-APP-018` for PR #26/RC-4,
  `V3-01-APP-019` for PR #27/RC-5, `V3-01-APP-020` through `V3-01-APP-022` for the exact RC-5
  G-01-A/G-02-A/G-03-A scope, `V3-01-APP-023` for governance-only PR #28,
  `V3-01-APP-024` for the single consumed RC-5 operation-1 authority, `V3-01-APP-025` for PR #29,
  `V3-01-APP-026` through `V3-01-APP-028` for the unmounted RC-6 G-01-A/G-02-A/G-03-A scope,
  `V3-01-APP-029` for PR #31, and `V3-01-APP-030` through `V3-01-APP-032` for the bounded
  RC-7 G-01-A/G-02-A/G-03-A scope. Those three records alone did not authorize an operation; the
  later one-operation authority was consumed by the timed-out operation and grants no further use.
  `V3-01-APP-033` authorized only PR #34; `V3-01-APP-034` through `V3-01-APP-036` bound the now
  retired RC-9 G-01-A/G-02-A/G-03-A scope. PR #35's merge decision and its separately bounded
  operation-1 authority are consumed/retired. `V3-01-APP-037` authorizes only PR #36; `V3-01-APP-038`
  through `V3-01-APP-040` bound the RC-10 scope. PR #37's G-08 and the separately granted exact
  Operation 1 and Operation 2 authorities are consumed by two successful attempts. Neither grants
  another operation or any broader provider authority.

V3-01-01 evidence is stored in `vf-v3-01-20260827T141431Z-9635fb3` as
`EV-V3-SEC-001` and `EV-V3-SEC-002-PARTIAL`. It records zero external calls and zero spend and does
not supersede the baseline run.

V3-01-02 evidence is stored in `vf-v3-01-20260827T153608Z-0629592` as
`EV-V3-PROVIDER-SAFETY-001`. It proves contract/mock controls only, records zero external calls and
zero spend, and does not establish a release candidate.

V3-01-03 evidence is stored in `vf-v3-01-20260827T165813Z-0f08544` as
`EV-V3-DURABLE-SAFETY-001` and `EV-V3-MEDIA-SECURITY-001`. It proves local/CI and disposable-Docker
remediation only, records zero external calls and zero spend, leaves GAP-010/GAP-011
`IN_PROGRESS`, and grants no merge or runtime permission.

V3-01-04 evidence is stored in `vf-v3-01-20260828T010641Z-88e6bcc` as
`EV-V3-FLOW-A-CONTRACT-001`. It proves the pre-call ASR/Vision safety boundary and a strict measured
two-run fixture contract. It records 0 VND, zero external calls and no publishing. Implemented and
mock-tested axes pass; real-provider, production-path and quality axes are explicitly `BLOCKED`.
At the V3-01-04 checkpoint GAP-003 remained `OPEN`; V3-01-09 now moves it to `IN_PROGRESS` through
adapter-only mock evidence. GAP-005 and GAP-016 remain `IN_PROGRESS`.

V3-01-05 evidence is stored in `vf-v3-01-20260828T033515Z-2563dfd` as
`EV-V3-FLOW-B-CONTRACT-001`. It proves a strict measured two-run Flow B fixture contract for
research/claims/originality, media coverage, rights/receipts, visual relevance, TTS/subtitle/audio,
approval, render QC, restart recovery and 0 VND cost. Real-provider, production-path and quality
axes remain `BLOCKED`; no G-01/G-02/G-03/G-04/G-11 authority was granted.

V3-01-06 evidence is stored in `vf-v3-01-20260828T043714Z-c1f50c4` as
`EV-V3-FLOW-C-CONTRACT-001`. It proves two deterministic fixture runs covering trend provenance,
cluster/score reproducibility, idea/project/video approval bindings, rights/platform validation,
publication idempotency and receipt integrity, nullable normalized analytics, explainable winner
assessment, recommendation-only learning lineage, restart recovery and 0 VND cost. No credential,
external call, remote post or production analytics was used. Real-provider, production-path and
quality axes remain `BLOCKED`; G-01 through G-06 and G-11 remain pending.

V3-01-07 evidence is stored in `vf-v3-01-20260828T073400Z-527fd1f` as
`EV-V3-DR-OBS-001`. The guarded disposable Docker drill restored PostgreSQL and object storage,
rebuilt Redis queues from canonical PostgreSQL state, resumed pending work and verified 9/9
recovery target hashes with RPO 0 seconds and RTO 33 seconds. Authenticated operations snapshots,
request/job/project correlation, secret-redacted logs and seven external-notification-disabled alert
previews also pass locally. Production-path DR, monitoring delivery and the 48-hour soak remain
`BLOCKED`; PR #19 is merged, but G-04/G-09/G-10/G-12 are pending for runtime acceptance.

V3-01-08 consolidates the evidence without changing an acceptance axis. The detailed RC decision,
gate dependency map and future provider/staging/cost/rights plans are in
[`24_V3_01_08_CONSOLIDATION_RC_GATE.md`](24_V3_01_08_CONSOLIDATION_RC_GATE.md). The RC review is
`CONDITIONAL-RC` for controlled acceptance planning only while the production verdict stays
`NO-GO`.

V3-01-09 adds `EV-V3-OPENAI-VISION-ADAPTER-001` for the implemented/mock-tested axis only. The
adapter is locked to OpenAI `gpt-5-mini`, uses strict Responses structured output, records hashes,
latency and a VND-only cost receipt, and is covered by malformed-response, timeout, retry, circuit,
duplicate, missing-credential, rights and budget tests through MockTransport. External calls and
actual spend are both zero. GAP-003 moves from `OPEN` to `IN_PROGRESS`; every real/provider,
production-path and quality axis remains unchanged.

V3-01-10 adds a verified acceptance gate loader and one internally generated G-03-A asset.
The loader binds raw/canonical hashes, exact RC, G-01/G-02/G-03 records, a dated VND envelope,
exactly two operation IDs and the asset SHA-256; it checks expiry and reserves cost atomically in
the durable ledger. The owner approved this exact RightsRecord only for Vision acceptance, and all
three gate records bind RC-3 plus the same complete scope hash. Governance-only PR #24 preserved the
executable RC. Operation 1 was dispatched once, failed non-retryably, and produced no structured,
provider or usage receipt. Atomic reservation, one-attempt/no-retry semantics, duplicate blocking,
rights binding and secret containment held. Operation 2 remains locked and no acceptance axis changed.

V3-01-11 is merged zero-call remediation. It corrects required-nullable Structured Outputs,
recursively validates nested strict objects and stores only bounded, redacted provider error
metadata in the durable attempt ledger. Exact-head and exact-main CI passed, and RC-4 was locked.
It changes no real-provider, production-path or quality axis. RC-4 post-lock audit then found a
different executable-contract blocker: its allowed operation IDs remained hard-coded to RC-3.

V3-01-12 is a merged zero-call remediation locked in RC-5. It derives operation IDs from exact RC tag, provider,
capability and slot and binds them to exact commit/tag/model, execution-scope hash, asset hash and
acceptance window. Its tests reject stale RC-3 bundles, commit/tag/provider/model/capability drift,
invalid ordinals, consumed duplicates, tampering and expired windows. Local evidence
`EV-V3-RC-BOUND-ALLOWLIST-001` records focused 59/59, full Python 259/259, Studio 14/14 and Renderer
14/14 plus typecheck/bundle PASS with zero credential reads, zero external calls and zero VND.
PR #27 exact-head and exact-main CI passed 5/5, and RC-5 was locked. At that checkpoint the fresh
governance rebind had no merge or runtime authority and changed no acceptance axis.

Governance-only PR #28 subsequently merged the exact RC-5 rebind without changing executable
RC-5. Under a separate bounded owner decision, operation 1 executed exactly once. The provider and
durable safety transaction succeeded with 1,996 input tokens, 2,371 output tokens and
`137.6287 VND` actual cost, but the runner then failed to serialize dataclass
`ProviderVisionFrame`. V3-01-13 adds a canonical dataclass/Pydantic serializer, deterministic
JSON/SHA and a separate secret-free `REVIEW_REQUIRED` fallback that preserves durable
operation/usage/cost context. It performs zero external calls and cannot reconstruct or promote the
missing RC-5 structured payload, request IDs or hashes. PR #29 merged it, exact-main CI passed 5/5
and RC-6 was locked. The fresh RC-6 scope validated offline. Its separately approved operation 1
later failed closed before provider dispatch because the runner's private limits dictionary omitted
the owner-approved window cap; operation 1 is not consumed, but the authority is retired and
operation 2 remains locked. V3-01-14 replaces future private runner dictionaries with one canonical
strict authority/bundle adapter and makes zero calls. PR #31 merged after exact-head approval,
exact-main CI passed 5/5, and RC-7 was locked. The new RC-7 scope binds fresh operation IDs,
canonical per-operation and acceptance-window VND limits, the approved asset/RightsRecord and a
new four-hour window. PR #32 merged the scope governance-only. Under separate authority, RC-7
operation 1 ran exactly once and timed out at about 60 seconds. It is consumed, no retry/fallback
occurred, actual provider cost is unknown, the 500 VND ledger amount is a safety charge, and
operation 2 remains locked. V3-01-15 adds future phase-specific timeout evidence without changing
the 60-second envelope or making an external call. PR #33 merged it, exact-main CI passed 5/5 and
RC-8 was locked. RC-8 retains the shared deadline and is therefore retired from live acceptance.
V3-01-16 now splits provider HTTP timeout 90 seconds from controller hard envelope 120 seconds,
with virtual boundary and strict legacy/missing/mismatch rejection tests; it remains zero-call.

## Open gaps and remediation

The lossless owner/impact/containment/test/rollback/PR mapping is in
[`13_GAP_REGISTER.csv`](13_GAP_REGISTER.csv). The revised V3-01-01 through V3-01-18 sequence is defined in
[`14_REMEDIATION_PR_PLAN.md`](14_REMEDIATION_PR_PLAN.md). No exception or expiry is recorded.

## Allowed actions

- **Merge:** decisions through PR #45 and both RC-10 operation authorities are consumed. The current
  V3-01-21 response-diagnostics remediation requires a new G-08.
- **Deploy:** no; RC-12 is locked NO-GO, not deployed and G-09 is pending.
- **Providers/platforms enabled:** none now. RC-10 Operations 1 and 2 each used the bounded
  process-local scope, which was disabled/unmounted after each successful attempt.
- **Volume/concurrency/budget:** RC-5 operation 1 consumed exactly one attempt with no retry/fallback
  and recorded `137.6287 VND` actual cost; all RC-5 IDs are locked. RC-6 operation 1 is not consumed
  but its failed-window authority is retired and both RC-6 IDs are prohibited. RC-7 operation 1 is
  consumed after one timeout, operation 2 is locked and RC-8 has no operation authority. RC-9
  operation 1 blocked pre-call with 0 calls/0 VND and is not consumed, but its authority is retired;
  operation 2 is locked. RC-10 Operations 1 and 2 are consumed/succeeded with `125.181420 VND` and
  `159.161860 VND` actual cost respectively; no Operation 3 is required or authorized, the bundle is
  unmounted and checked-in budget remains 0. RC-11 ASR Operation 1 is blocked/not consumed with
  retired authority and Operation 2 is locked. RC-12 ASR Operation 1 is consumed after one provider
  response failed strict mapping/validation; actual cost is unknown, its 500 VND charge is only
  conservative safety accounting, and its authority is retired. RC-12 Operation 2 is retired/locked.
- **Publish visibility/channel:** none; no remote publication.
- **Still prohibited by this package:** any ASR operation or provider call, credential-value read, production-path writes, public route, publish,
  delete/takedown, customer contact and representing mock evidence as real-provider evidence.
- **Rollback trigger:** no runtime change exists; revert the isolated governance/docs PR if it regresses
  CI or evidence integrity.

## V3-01-18 source checkpoint

PR #40 merged the Vision closure/ASR gate design as
`4c74fa18a86b29ae8324885dacc6fdbca74ad066`; exact-main CI `33706971864` passed 5/5 and that
docs-only merge did not create an RC. PR #41 then merged the fail-closed OpenAI ASR adapter,
canonical gate and offline compatibility matrix as exact RC-11
`207ff9fee5557eb0976f575c9263b61d995b20a0`; exact-head CI `33711738092` and exact-main CI
`33712762815` passed. `ASR-01` remains only implemented/mock-tested PASS. The owner has since
approved `whisper-1`, G-02-ASR v1.1 and two exact owner-cleared inputs. PR #42 merged the unmounted
governance bundle as `8ad490c02c36aafe9447a3eb0766a1d1f1f122d7` without changing executable RC-11. The owner later
approved Operation 1 only for its exact future window; this offline package does not execute or
extend it, and Operation 2 remains locked. Real-provider, production-path and quality remain
`NOT_TESTED`. The current preparation branch stops at a new G-08 with zero calls, credential reads
and VND.

## Offline post-run and quality-gate preparation

That historical draft added a deterministic ASR post-run evaluator, a two-run Flow A real-media contract,
a Vietnamese TTS candidate/acceptance design and a strict artifact-bound G-11 review template. It
does not change the acceptance matrix or gap register because no provider, production-path or human
quality operation occurred. Executable RC-11 remained immutable at that checkpoint.

## RC-12 checkpoint

PR #44 merged V3-01-20 as `ca5483c889742c27af3368b9b487350d7daa217d`; exact-main CI
`33889772222` passed 5/5 and annotated `vf-v3-01-rc12` peels to the merge. The fresh ASR scope uses
new RC-derived operation IDs and a new dated window while preserving exact WAV, transcript and
RightsRecord hashes. The raw bundle SHA is
`218e06d245f43733a2659aff35f4ea0e7e73dcd17258f663d351b198aebf3db1` and the execution-scope SHA
is `6f0aecf227df30d493566a8d089a6097f83c454993b6ce25eb00eeb887fb9cc4`. PR #45 merged this
governance scope as `f765f216f90b0d05071cc7c873a2edb6d5bdcec4`; governance-main CI `33894628759`
passed. The separately authorized Operation 1 passed preflight and reached a provider response, but
strict response mapping/validation failed. It is consumed/failed/`REVIEW_REQUIRED`; actual cost is
unknown, 500 VND is only the conservative ledger charge, and absent transcript/request-hash/usage
evidence is not reconstructed. Operation 2 is retired/locked.

## V3-01-21 checkpoint

V3-01-21 is a zero-call source remediation for future ASR failures. It stores value-free validation
issue paths/codes, deterministic request/response hashes when available, provider/client request IDs,
elapsed/dispatch state and strictly allowlisted response metadata under phase
`structured_output_validation`; raw response values are not persisted. The representative synthetic
missing-words fixture is explicitly not evidence of the unknown RC-12 response shape. The shared
secret scanner now accepts canonical credential-reference aliases while continuing to reject actual
OpenAI-style keys, bearer tokens and assigned secret values. The durable RC-12 result remains
immutable and is not promoted. This remediation performed zero provider calls, zero credential
reads and zero VND spend, and requires its own G-08 before merge. A merge would require full
exact-main regression and a new RC-13 plus fresh scope/window/operation IDs before any later ASR
execution decision. Production remains `NO-GO`.

## Decision rule

Every real-provider, production-path and human-quality axis lacking evidence remains `NOT_TESTED`,
`BLOCKED` or `FAIL`, never inferred as PASS. Final GO requires G-12 after all critical axes pass on
one locked RC and every P0 is verified or covered by an explicit unexpired owner exception.
