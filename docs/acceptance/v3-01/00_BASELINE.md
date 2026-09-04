# V3-01 baseline

Captured at `2026-08-27T12:02:08Z` (`2026-08-27 19:02:08 Asia/Ho_Chi_Minh`).
Governance state updated after bounded G-00 approval at `2026-08-27T13:29:26Z`.
Current checkpoint status updated after evidence-only PR #39 merged as
`fd0db431d2e3786b6b07dcb4b47b7bc74cfa7aed` and exact-main CI `33703619599` passed 5/5. Operations
1 and 2 are consumed/succeeded, their receipt hashes remain unchanged, and Vision is officially 2/2
consecutive PASS on the real-provider-tested axis. The gate is unmounted and all further standalone
Vision operation authority is retired. PR #40 then merged the Vision closure/ASR design as
`4c74fa18a86b29ae8324885dacc6fdbca74ad066`; exact-main CI `33706971864` passed 5/5 with an
unchanged executable tree. PR #41 then merged V3-01-18 as exact RC-11
`207ff9fee5557eb0976f575c9263b61d995b20a0`; exact-head CI `33711738092` and exact-main CI
`33712762815` passed. The owner has selected `whisper-1` and approved the bounded G-01/G-02/G-03-ASR
inputs. Their exact dated rebind is checked in for G-08 review only: the bundle is unmounted and both
operations remain unauthorized.

PR #42 and PR #43 later merged governance/offline preparation as
`8ad490c02c36aafe9447a3eb0766a1d1f1f122d7` and
`090f9085ccccf8ef30b926d7cc04a6c8a402128e` without changing executable RC-11. A separately
authorized ASR Operation 1 then stopped fail closed in durable rights preflight: the multi-asset
gate supplied `rights_records[]`, while the durable controller still projected the legacy singular
record. The operation made zero credential reads, reservations, ledger rows or provider calls; it
is not consumed, but its authority/window is retired. V3-01-20 remediated that executable contract
and PR #44 merged as `ca5483c889742c27af3368b9b487350d7daa217d`; exact-main CI `33889772222`
passed 5/5 and annotated `vf-v3-01-rc12` now peels to that merge. A fresh RC-12 ASR scope is checked
in for G-08 review only; its bundle is unmounted and both operations remain unauthorized.

## Control state

```text
FEATURE FREEZE: ACTIVE
DEFAULT VERDICT: NO-GO UNTIL PROVEN
CURRENT RC: RC-12 ca5483c889742c27af3368b9b487350d7daa217d; locked NO-GO; not deployed
AUDIT BASE SHA: cae40eda871d0f9c7fc315229361a40032d48967
CURRENT SAFE PHASE: Vision closed; RC-12 ASR governance rebind; zero-call G-08 pending
G-00: APPROVED by V3-01-APP-001
G-08: PR #44 APPROVED/MERGED; RC-12 GOVERNANCE REBIND DRAFT REQUIRES A NEW G-08
G-01/G-02/G-03-ASR: RC-12 SCOPE REBOUND; NO OPERATION AUTHORITY
RC-11 ASR OPERATION 1: BLOCKED PRE-CALL; NOT CONSUMED; 0 CALLS/READS/VND; AUTHORITY RETIRED
RC-11 ASR OPERATION 2: NOT APPROVED; LOCKED; NOT EXECUTED
RC-12 ASR OPERATION 1: NOT APPROVED; NOT EXECUTED
RC-12 ASR OPERATION 2: NOT APPROVED; LOCKED; NOT EXECUTED
G-01-A / G-02-A / G-03-A: CONSUMED BY EXACT RC-10 OPERATIONS 1 AND 2; NO FURTHER OPERATION AUTHORITY
RC-10 OPERATION 1: PASS; CONSUMED / SUCCEEDED
RC-10 OPERATION 2: PASS; CONSUMED / SUCCEEDED; VISION 2/2 CONSECUTIVE PASS
RC-10 FURTHER VISION OPERATION: NOT REQUIRED; NOT AUTHORIZED
RC-9 OPERATION 1: BLOCKED PRE-CALL; NOT CONSUMED; PROVIDER CALLS 0; COST 0 VND; AUTHORITY RETIRED
RC-9 OPERATION 2: LOCKED; NOT EXECUTED
RC-7 OPERATION 1: FAILED PROVIDER_TIMEOUT; REVIEW_REQUIRED; CONSUMED; NO RETRY
RC-7 OPERATION 2: LOCKED; NOT EXECUTED
RC-6 OPERATION 1: BLOCKED PRE-CALL; NOT CONSUMED; PROVIDER CALLS 0; COST 0 VND
RC-6 OPERATION 2: LOCKED; NOT EXECUTED
RC-5 OPERATION 1: PROVIDER SUCCESS; EVIDENCE INCOMPLETE; REVIEW_REQUIRED; CONSUMED
RC-5 OPERATION 2: NOT APPROVED; LOCKED
HISTORICAL RC-3 OPERATION 1: EXECUTED ONCE; FAILED NON-RETRYABLE; NEVER REUSE
NO OTHER MERGE / NO DEPLOY / NO PUBLISH WITHOUT EXPLICIT OWNER APPROVAL
```

G-00 accepts the feature freeze, matrix, gaps and remediation sequence. It does not authorize a
merge, deployment, public ingress, credential use, provider execution, spend, external publish,
analytics write or takedown. Those actions remain bound to their separate gates.

G-08 later authorized only the repository merge sequence PR #12, then retarget/retest PR #13, then
PR #13 if all five CI jobs pass. It grants no runtime or external-execution authority.

The bounded remediation sequence completed PR #12 through PR #23. PR #24 then merged governance
rebind only as `a73bad37f1f3aa7c2347e6a76503246a46d3c112`; exact-main CI run `33175813324`
passed 5/5. Executable RC-3 remains immutable at
`adde8d9c5a7f608db80cbd9d21aecd45f721065e`. Operation 1 was mounted ephemerally and dispatched
exactly once inside its approved window. It failed non-retryably with
`OpenAIVisionResponseError`, produced no structured/provider/usage receipt and is not accepted as
real-provider evidence. Operation 2 remains locked and checked-in runtime defaults remain disabled.
PR #25 then merged only this redacted evidence/governance record as
`2ab6b51d63b86c7e4cc9febe347929d8cc3f2e38`; exact-main CI run `33182052862` passed 5/5 and
executable RC-3 remained unchanged.

PR #26 then merged the zero-call V3-01-11 remediation as
`061ca5d03248d6721ef8dc7a53cf4608e7ebe79e`; exact-main CI run `33189441083` passed 5/5 and
annotated tag `vf-v3-01-rc4` peels to that commit. Post-lock audit proved RC-4 still accepted only
the hard-coded RC-3 operation IDs. RC-4 is therefore retained as fail-closed blocker evidence and
is prohibited for live acceptance. PR #27 then merged V3-01-12 as
`26adafb2eeed4b4de1169db73a13e50a683e094c`; exact-main CI run `33194523231` passed 5/5 and
annotated tag `vf-v3-01-rc5` peels to that exact commit. RC-5 operation IDs were derived and
G-01-A/G-02-A/G-03-A were rebound to a new hash-bound window in an unmounted governance bundle.
PR #28 then merged the governance-only RC-5 rebind as
`8fa96409b0db6ec6d4dc3c04f6e3aaab2f3201ee`; exact-main CI run `33226016184` passed 5/5 without
changing executable RC-5. The owner separately authorized operation 1. It executed exactly once:
OpenAI/provider execution and the durable operation/usage/cost ledger succeeded, but the post-call
runner failed to serialize frozen dataclass `ProviderVisionFrame`. Operation 1 is consumed and
permanently `REVIEW_REQUIRED`; operation 2 was not approved and has no ledger row. PR #29 then
merged the zero-call V3-01-13 remediation as
`8df74a202dc2160e9358ca4cc9be54d989af2292`; exact-main CI run `33261962445` passed 5/5.
Annotated tag `vf-v3-01-rc6` peels to that exact merge commit. PR #30 subsequently merged only the
RC-6 governance rebind as `5f6842c022b4ac71893fb251122c5a74aa50ac41`; executable RC-6 stayed
unchanged. The owner separately authorized RC-6 operation 1, but the runner rejected the verified
bundle before credential read, reservation, ledger mutation or provider dispatch because its
private limits dictionary omitted `acceptance_window_limit_vnd`. The result is `BLOCKED PRE-CALL /
NOT CONSUMED`, provider calls 0, cost 0 VND and ledger `0|0|0|0`. The failed-window authority is
retired, operation 2 remains locked and neither RC-6 operation may be retried.

PR #31 then merged the zero-call V3-01-14 remediation as
`94170ed42f6ffba4432f29750402eafe0d922a45`; exact-main CI run `33321003243` passed 5/5.
Annotated tag `vf-v3-01-rc7` peels to that exact merge commit. The owner-directed post-merge
sequence produced fresh RC-7 operation IDs and rebound G-01-A/G-02-A/G-03-A to a new dated scope
and bundle. PR #32 merged that governance-only rebind as
`ebe6f91a9ac88364a23871d587ae4564f30283d3` without changing executable RC-7. Under separate owner
authority, operation 1 entered the provider path once and timed out at about 60 seconds. It is
consumed/`REVIEW_REQUIRED`; no retry/fallback occurred, actual provider cost is unknown and the
durable 500 VND amount is a conservative safety charge. Operation 2 remains locked. V3-01-15 now
remediates timeout-phase evidence offline without changing the 60-second envelope.

PR #33 then merged V3-01-15 as `68d4cf90004054075ebf0f33b9311a3419d8af4d`; exact-main CI run
`33412301663` passed 5/5. Annotated tag `vf-v3-01-rc8` has tag object
`aaeefaa31b027fa77aa3bea13a1bbec5cefaefd6` and peels to that merge. RC-8 is locked NO-GO and not
deployed. Audit confirmed its executable contract still used one shared 60-second timeout for the
provider transport and controller envelope. The owner therefore retired RC-8 from live acceptance
and authorized only the zero-call V3-01-16 source remediation with explicit 90-second provider and
120-second controller limits. No RC-8 operation IDs, bundle, credential read or provider call were
created.

The V3-01 source supplied by the owner is document `NPD-VF-V3-01`, version `3.01.0`, SHA-256
`53160020d5d32a5327857c899f3a7cb3cdd2d1292d98e6ec51ba97239cb4fee4`. The source file is
outside the repository; this record stores only its identifier and hash, not an uncontrolled copy.

## Repository and GitHub

| Field | Verified value |
|---|---|
| Repository | `https://github.com/vangnguyen/npd-video-factory-v2.git` |
| Working tree | `C:\Users\VANG NGUYEN\Documents\Codex\2026-08-20\referenced-chatgpt-conversation-this-is-an\work\npd-video-factory-v2` |
| Baseline branch | `main` |
| Audit branch | `audit/v3-01-00-baseline-evidence` |
| Base/HEAD at audit start | `cae40eda871d0f9c7fc315229361a40032d48967` |
| Base commit time | `2026-08-27T10:17:38Z` |
| Open PRs at capture | none |
| Tags/releases | none returned by Git/GitHub |
| Main branch protection | disabled; GitHub API returned `Branch not protected` |
| Executable RC CI | [Video Factory V2 CI run 33449162326](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/33449162326), 5/5 success on exact RC-9 `256bda59eed028ddd642cdb0988c409c489fd655` |
| Governance main CI | [Video Factory V2 CI run 33499392585](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/33499392585), 5/5 success on post-PR #35 main `e48d7edebcbfb1bd4113c2e40ab4ce46c186f6e4` |
| Current executable RC CI | [Video Factory V2 CI run 33527973264](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/33527973264), 5/5 success on exact RC-10 `c2b1aec2d54dd90bcb486f8a68c97746b39963aa` |
| Current governance main CI | [Video Factory V2 CI run 33650857422](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/33650857422), 5/5 success on evidence-only post-PR #38 main `79b14ded0bbd0cd552420e5964647b6fba16f9b7` |
| Required checks observed | Python, renderer, Studio, safety/Compose, Docker deterministic E2E |
| Working tree at capture | clean before the audit branch was created |

Current repository checkpoint after the bounded merge sequence:

| Field | Verified value |
|---|---|
| Exact `origin/main` before RC-10 consecutive-evidence branch | `79b14ded0bbd0cd552420e5964647b6fba16f9b7` after evidence-only PR #38; executable RC-10 remains identical |
| Exact main tree | re-verify from exact main before any later merge |
| PR #12 | merged at `a9dfe87b479ebdb4e6a757543a7b47e9ac81ffd4` |
| PR #13 | retargeted/retested with 5/5 CI PASS, merged at `9b66d6917d6d58fea995b3a1049fc95198e81bf1` |
| PR #14 through PR #18 | merged sequentially under bounded G-08 records; no runtime authority |
| PR #19 | exact head `4b17fc1352ee4582db9b69f795531ef9b6a4feb4`; CI run `33153548402` PASS; merged before consolidation |
| PR #20 | exact head `a8a2cecc620cae4fc3bd072b53489db8b2acd7ec`; CI run `33155313793` PASS; merged as RC-1 |
| PR #22 / V3-01-09 | exact head `e6651948751fc8789ff83f91e0e7e8f88564e2aa`; CI run `33161662691` PASS; merged as exact current main |
| RC-2 | annotated `vf-v3-01-rc2` peels to exact main `5936aa7a9656d728be751d0ee61011fc1a5abc7a`; planning-only, not deployed |
| PR #23 / V3-01-10 | exact head `40149c2b439c78e75fdd3ff8996c2ed8c3ec4575`; CI run `33171973815` PASS; merged as `adde8d9c5a7f608db80cbd9d21aecd45f721065e` |
| RC-3 | annotated `vf-v3-01-rc3` peels to exact main `adde8d9c5a7f608db80cbd9d21aecd45f721065e`; NO-GO, not deployed |
| PR #24 / RC-3 governance rebind | exact head `c13e78b7afaf852ce0682f8f117138ea34a9297f`; governance-only merge `a73bad37f1f3aa7c2347e6a76503246a46d3c112`; exact-main CI run `33175813324` 5/5 PASS |
| PR #25 / operation-1 evidence | exact head `b0de3903b5e630bcb288074c7939e59248f81490`; evidence/governance-only merge `2ab6b51d63b86c7e4cc9febe347929d8cc3f2e38`; exact-main CI run `33182052862` 5/5 PASS |
| PR #26 / V3-01-11 | exact head `a09919db67f23253bc45ff3171b99e220c25c599`; merge `061ca5d03248d6721ef8dc7a53cf4608e7ebe79e`; exact-main CI run `33189441083` 5/5 PASS |
| RC-4 | annotated `vf-v3-01-rc4` peels to `061ca5d03248d6721ef8dc7a53cf4608e7ebe79e`; NO-GO; retained as blocker evidence; no live acceptance |
| PR #27 / V3-01-12 | exact head `703fec6931c315b853ee4691aef5ce290510eb8b`; merge `26adafb2eeed4b4de1169db73a13e50a683e094c`; exact-main CI run `33194523231` 5/5 PASS |
| PR #28 / RC-5 governance rebind | governance-only merge `8fa96409b0db6ec6d4dc3c04f6e3aaab2f3201ee`; exact-main CI run `33226016184` 5/5 PASS; executable RC-5 unchanged |
| RC-5 | annotated `vf-v3-01-rc5` peels to `26adafb2eeed4b4de1169db73a13e50a683e094c`; NO-GO; not deployed; operation 1 consumed/`REVIEW_REQUIRED`; operation 2 locked |
| PR #29 / V3-01-13 | exact head `2fc80e511e6ab0382b3a05b141764ea37725d245`; merge `8df74a202dc2160e9358ca4cc9be54d989af2292`; exact-main CI run `33261962445` 5/5 PASS; `V3-01-APP-025` consumed |
| RC-6 | annotated `vf-v3-01-rc6` peels to `8df74a202dc2160e9358ca4cc9be54d989af2292`; tag object `b285bfec8c7f398d56ec513cf35cd6f14fb5c596`; NO-GO; not deployed; operation 1 blocked pre-call/not consumed; operation 2 locked; authority retired |
| RC-6 governance rebind | PR #30 governance-only merge `5f6842c022b4ac71893fb251122c5a74aa50ac41`; G-01-A/G-02-A/G-03-A bound by `V3-01-APP-026` through `V3-01-APP-028`; bundle raw SHA `186ce157e94cbb2f321dbdcf59df1eb80d6d6df84fb5eca5422f4f5b94ba38f9`; failed-window authority retired |
| PR #31 / V3-01-14 | exact head `ff67fb05f32e300cdb4daac3fd29d8135a62879f`; merge `94170ed42f6ffba4432f29750402eafe0d922a45`; exact-main CI run `33321003243` 5/5 PASS; `V3-01-APP-029` consumed |
| RC-7 | annotated `vf-v3-01-rc7` peels to `94170ed42f6ffba4432f29750402eafe0d922a45`; tag object `14e1c09550aaa92c937e275bbe8d1e38c6ed8b8c`; NO-GO; not deployed |
| RC-7 governance rebind | PR #32 merged governance-only as `ebe6f91a9ac88364a23871d587ae4564f30283d3`; G-01-A/G-02-A/G-03-A bound by `V3-01-APP-030` through `V3-01-APP-032`; bundle raw SHA `ce772a941766b12a99943b9165cbf588c314e3d1b59543f103c7671a58856a44`; scope SHA `60d9898de38f9536ed3391ca81f1d59eca04b61537edad42e85597702c143a56` |
| PR #33 / V3-01-15 | merge `68d4cf90004054075ebf0f33b9311a3419d8af4d`; exact-main CI run `33412301663` 5/5 PASS |
| RC-8 | annotated `vf-v3-01-rc8` peels to `68d4cf90004054075ebf0f33b9311a3419d8af4d`; tag object `aaeefaa31b027fa77aa3bea13a1bbec5cefaefd6`; NO-GO; not deployed; retired from live acceptance because the executable contract still had one shared 60-second deadline |
| PR #34 / V3-01-16 | exact head `008120e76b37f92927903f3d1a909e257bedcfca`; merge `256bda59eed028ddd642cdb0988c409c489fd655`; exact-main CI run `33449162326` 5/5 PASS; `V3-01-APP-033` consumed |
| RC-9 | annotated `vf-v3-01-rc9` peels to `256bda59eed028ddd642cdb0988c409c489fd655`; tag object `0a6d091eb22b9d313a2e6894e5abf379bfa0d504`; NO-GO; not deployed |
| RC-9 governance rebind | PR #35 merged governance-only as `e48d7edebcbfb1bd4113c2e40ab4ce46c186f6e4`; G-01-A/G-02-A/G-03-A were bound by `V3-01-APP-034` through `V3-01-APP-036`; bundle raw SHA `965ed58e4d1c73e3452aedd90e367ed6ec84d85bff1a9fdd11afe5d7cd64155f`; scope SHA `f3ff461f27537700160b1ec417905c2bb98aeb874c1e39981762bf4ac32970d4`; authority now retired |
| Dual-CI provenance | executable run `33449162326` and governance run `33499392585` each pass 5/5 and bind their separate commits; selected executable-tree SHA is identical at `b57ef070664067f789424bf58f482f40087160a0e446e3e02aa2b1d45b4d9f53` |
| PR #36 / V3-01-17 | exact head `8b3e2f595cbf6b7fd710627487808a674b05a383`; merged as `c2b1aec2d54dd90bcb486f8a68c97746b39963aa`; exact-main CI run `33527973264` 5/5 PASS; `V3-01-APP-037` consumed |
| RC-10 | annotated `vf-v3-01-rc10` peels to `c2b1aec2d54dd90bcb486f8a68c97746b39963aa`; tag object `32bd6a78048a6ae92538a9195a1386318ebd72b8`; NO-GO; not deployed |
| RC-10 governance rebind | PR #37 merged governance-only as `fd78a1690a5a2fd7b07e9e7822deda834f02ea6d`; executable CI `33527973264` and governance CI `33532594395` each passed 5/5; G-01-A/G-02-A/G-03-A bound by `V3-01-APP-038` through `V3-01-APP-040`; bundle raw SHA `30f4ffd9353a00b7fdf97d0998dce43798937a2c577ca3fa618c947bbb8040e1`; scope SHA `a77a2e38d604214dbcaf0933cbdbf6f2fafa6ee258369e1a629ef5b0d55c6cc0` |
| RC-10 Operation 1 evidence | PR #38 merged evidence-only as `79b14ded0bbd0cd552420e5964647b6fba16f9b7`; exact-main CI `33650857422` passed 5/5; executable tree remained `f1f75f632ca3b1380985c5a532c9f4c601e39d45276135666f335cc3d041125c` |
| RC-10 consecutive Vision closure | PR #39 merged evidence-only as `fd0db431d2e3786b6b07dcb4b47b7bc74cfa7aed`; `V3-01-APP-041` consumed; exact-main CI `33703619599` passed 5/5; dual-CI provenance PASS; executable tree remained `f1f75f632ca3b1380985c5a532c9f4c601e39d45276135666f335cc3d041125c`; source receipt SHA values remained `11fd1f7c...` and `deed47e5...` |
| PR #41 / RC-11 | PR #41 exact head `8ebb1cffe8563e49ccf4847ef37209d9644a4e70`; merged as `207ff9fee5557eb0976f575c9263b61d995b20a0`; exact-head CI `33711738092` and exact-main CI `33712762815` passed; annotated `vf-v3-01-rc11` peels to the merge; `V3-01-APP-043` records G-08 |
| RC-11 ASR governance proposal | `whisper-1`; two exact owner-approved WAVs/RightsRecords; G-01/G-02/G-03 records `V3-01-APP-044` through `046`; raw bundle SHA `4f8edd02ec62182404976de16e8d75b39ddbbbbe96c0d78efd46e3a97d6ace46`; scope SHA `7368b506b8971b190a1828ecab588dfe6b46a7e354d00c4d7cf2f35c1cc2c39a`; bundle unmounted; operations not approved |
| Provider acceptance action | RC-3 operation 1 failed and is locked; RC-5 operation 1 completed provider execution once but evidence serialization was incomplete; RC-6 operation 1 blocked pre-call with 0 calls/0 VND; RC-7 operation 1 timed out once and is consumed/`REVIEW_REQUIRED`; RC-9 operation 1 blocked pre-call on CI-provenance ambiguity with 0 calls/0 VND and is not consumed, but its authority is retired; RC-10 Operations 1 and 2 each completed one attempt with complete structured/usage/cost evidence and are consumed/succeeded; Vision is officially 2/2 consecutive real-provider PASS; no Operation 3 is required or authorized; RC-11 ASR remains real-provider `NOT_TESTED` and both operations are unauthorized |
| PR #44 / RC-12 | PR #44 exact head `a5666703fe7d0c0fe9a78deadc7eefd5bd848e61`; merged as `ca5483c889742c27af3368b9b487350d7daa217d`; exact-head CI `33888514088` and exact-main CI `33889772222` passed 5/5; annotated `vf-v3-01-rc12` peels to the merge; `V3-01-APP-047` records G-08 |
| RC-12 ASR governance rebind | fresh operations `v3-01-rc12-openai-transcription-asr-call-01/02`; unchanged exact WAV/transcript/RightsRecord hashes; records `V3-01-APP-048` through `050`; raw bundle SHA `218e06d245f43733a2659aff35f4ea0e7e73dcd17258f663d351b198aebf3db1`; scope SHA `6f0aecf227df30d493566a8d089a6097f83c454993b6ce25eb00eeb887fb9cc4`; bundle unmounted; both operations not approved |
| Deployment/ingress/publish action | none |

No `AGENTS.md` file exists in the repository. Repository instructions are therefore the checked-in
README, architecture, security, deployment, testing, V2 acceptance and runbook documents.

## Product and schema baseline

| Field | Verified value |
|---|---|
| API/worker/renderer/Studio version | `0.12.0` |
| API title | `NPD Video Factory V2 API` |
| Latest Alembic migration on `main` | `0012_v3_01_11_provider_error_evidence` |
| V3-01-07 schema change | none; public API and Redis key formats remain compatible |
| Compose project | `npd-video-factory-v2` |
| Default services | PostgreSQL, Redis, MinIO, migrate, API, Studio, renderer, worker |
| Optional service | `comfyui-bridge` behind disabled `gpu` profile |
| Canonical metadata | V2-owned PostgreSQL |
| Transient delivery/replay | V2-owned Redis |
| Binary objects | MinIO in local/CI; S3-compatible contract for production |
| API/Studio/renderer exposure | localhost by default |

## Runtime evidence

The successful main CI used Python `3.12` and Node `22`. The local audit host exposes the bundled
Python `3.12.13`, bundled Node `24.19.0`, Docker Engine/Client `29.5.3` and Docker Compose `5.1.4`.
Host FFmpeg/FFprobe and a global Node/npm command are not installed; deterministic media execution
runs inside the pinned containers. The host operating system is Windows NT `10.0.26220.0`.

## Deployment baseline

| Field | State |
|---|---|
| Production deployment | no live deployment evidence; repository docs explicitly say not approved/deployed |
| Production commit/image digest | unavailable |
| Production ingress/TLS/Caddy route | absent by design |
| Production database/storage | not provisioned or evidenced |
| Latest production backup | none evidenced |
| Restore/rollback drill | local disposable V3-01-07 data recovery PASS; production-like/image rollback not performed |
| Production incident | none applicable because V2 is not deployed |

This audit does not infer any Video Factory deployment from the separate Agent Hub/SaleHub VPS.

## Provider/configuration baseline

Only variable names and safe policy values were inspected. The ignored local `.env` was not printed,
hashed or copied. It is a development configuration with fixtures and publishing disabled; it is
not production evidence. Credential presence is not permission to call a provider.

Current checked-in production override deliberately selects contract-only or disabled providers:

- trend, Auto Edit, Vision, media and analytics fixtures: false;
- transcription, Vision, stock, image generation, video generation and TTS: `contract`;
- external audio/media/paid media/ComfyUI/analytics execution: false;
- scheduled analytics refresh: false;
- `PUBLISH_ENABLED=false`;
- `PUBLISH_EXTERNAL_EXECUTION_ENABLED=false`;
- `PUBLISH_OWNER_GATE_ENABLED=false`;
- `HUMAN_APPROVAL_REQUIRED=true`;
- Agent Hub bridge and HTTP webhook delivery: disabled unless separately configured.

## Known state at freeze

- CI proves deterministic/local behavior only.
- Interactive Studio/API SSO, RBAC and workspace membership are not implemented/accepted.
- Real providers, real production path, human quality acceptance and public publishing are unproven.
- No external cost was incurred during baseline capture.
- No production write, deploy, publish, credential rotation or provider call was performed.
- The OpenAI Vision credential exists only in the ignored workstation secret file; its presence is
  not authority to use it, and local/CI Compose explicitly receives an empty key.

Evidence: `EV-V3-BASE-001`, `EV-V3-STATIC-001`, `EV-V3-CI-001`, `EV-V3-SAFETY-001`,
`EV-V3-DR-001`, `EV-V3-OPENAI-VISION-ADAPTER-001`,
`EV-V3-STRUCTURED-ERROR-EVIDENCE-001`, `EV-V3-RC6-OP1-BLOCKED-001`,
`EV-V3-AUTHORITY-LIMITS-001`.

## Remediation checkpoints

V3-01-01 human identity/ingress remediation is now merged through PR #13 at exact `main`
`9b66d6917d6d58fea995b3a1049fc95198e81bf1`. Its local/CI and disposable Docker evidence
passes for external hash-only sessions, RBAC, workspace isolation, Studio session handling and
valid-session rate limiting. It remains undeployed and has no public-ingress acceptance.

V3-01-02 provider safety merged through PR #14 at exact `main`
`dee8ac279b9ae5f4f94fbb654efb41bfdaf38ae3`. Exact-main regression passed all five CI jobs with
zero external requests and zero VND cost. The code is undeployed and is not a release candidate;
credentials, real providers, public ingress and publishing remain prohibited.

V3-01-03 development is isolated on branch `remediation/v3-01-03-ingress-durable-safety`. Its
bounded scope is upload quarantine/malware and archive-denial controls, a non-deployed WAF/ingress
contract, and PostgreSQL-backed provider budget/operation/circuit state. It may create a draft PR
after local/CI evidence, but has no merge or runtime authority. The locked code checkpoint is
`0f0854466655d2f36cfa8b57785000097b220c4c`; evidence run
`vf-v3-01-20260827T165813Z-0f08544` records zero calls and zero VND while retaining `NO-GO`.

V3-01-04 through V3-01-07 are merged Flow A, Flow B, Flow C and local DR/observability acceptance
planes. They prove deterministic fixture and disposable local/CI behavior only. V3-01-08 is merged
through PR #20; V3-01-09 is merged through PR #22; V3-01-10 is merged through PR #23; RC-3 is
locked for controlled acceptance. Production verdict remains `NO-GO`.

V3-01-09 implements a disabled OpenAI `gpt-5-mini` Vision adapter. Its strict
Responses-schema, timeout/retry/circuit, duplicate, missing-credential, rights, budget, provenance
and VND receipt tests use MockTransport. V3-01-10 adds a hash-pinned verified gate loader. RC-3 was
locked, the exact asset and approvals were rebound through governance-only PR #24, and operation 1
was executed once. The failed attempt is retained as `EV-V3-OPENAI-VISION-OP1-FAILED-001`; actual
provider cost is unknown because no usage receipt was returned, while the safety ledger conservatively
committed the 500 VND reservation. All RC-3 operation IDs remain locked.

V3-01-11 merged through PR #26 and is locked as RC-4. It makes the OpenAI strict schema recursively
complete and persists only bounded, redacted provider failure metadata. Post-lock audit found the
RC-3 operation IDs were still hard-coded in the executable loader, so RC-4 cannot be used for a new
operation. V3-01-12 removed that RC-specific constant, merged through PR #27 and is locked as RC-5.
It derives IDs from exact RC/provider/capability/slot and keeps all execution/budget defaults
fail-closed. Evidence `EV-V3-RC-BOUND-ALLOWLIST-001` and `EV-V3-RC5-VISION-REBIND-001` pass only
implemented/mock-tested governance axes. Governance-only PR #28 merged the RC-5 rebind without
changing executable RC-5. RC-5 operation 1 then executed once: provider execution and actual
`137.6287 VND` cost were recorded, but the evidence runner lost request-level artifacts after a
dataclass serialization error. `EV-V3-RC5-VISION-OP1-REVIEW-001` therefore keeps the operation
consumed and `REVIEW_REQUIRED`, with operation 2 locked. V3-01-13 adds only an offline canonical
serializer and failure fallback; it does not reconstruct the missing fields or promote an
acceptance axis. See
[`29_V3_01_11_STRUCTURED_OUTPUT_ERROR_EVIDENCE.md`](29_V3_01_11_STRUCTURED_OUTPUT_ERROR_EVIDENCE.md)
[`30_V3_01_12_RC_BOUND_OPERATION_ALLOWLIST.md`](30_V3_01_12_RC_BOUND_OPERATION_ALLOWLIST.md), and
[`31_V3_01_RC5_VISION_ACCEPTANCE_WINDOW.md`](31_V3_01_RC5_VISION_ACCEPTANCE_WINDOW.md), and
[`32_V3_01_13_EVIDENCE_SERIALIZATION_REMEDIATION.md`](32_V3_01_13_EVIDENCE_SERIALIZATION_REMEDIATION.md).
