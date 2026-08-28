# V3-01 baseline

Captured at `2026-08-27T12:02:08Z` (`2026-08-27 19:02:08 Asia/Ho_Chi_Minh`).
Governance state updated after bounded G-00 approval at `2026-08-27T13:29:26Z`.

## Control state

```text
FEATURE FREEZE: ACTIVE
DEFAULT VERDICT: NO-GO UNTIL PROVEN
CURRENT RC: RC-2 5936aa7a9656d728be751d0ee61011fc1a5abc7a; locked for controlled acceptance planning only; not deployed
AUDIT BASE SHA: cae40eda871d0f9c7fc315229361a40032d48967
CURRENT SAFE PHASE: V3-01-10 verified gate loader in LOCAL/CI; unmerged; no current merge or call authority
G-00: APPROVED by V3-01-APP-001
G-08: V3-01-APP-002 through V3-01-APP-010 CONSUMED by PR #12 through PR #22
G-01-A / G-02-A: APPROVED FOR PREPARATION ONLY; MUST BE REBOUND TO RC-3
G-03-A: PENDING; CANDIDATE RIGHTS RECORD REMAINS BLOCKED
NO OTHER MERGE / NO DEPLOY / NO PUBLISH WITHOUT EXPLICIT OWNER APPROVAL
```

G-00 accepts the feature freeze, matrix, gaps and remediation sequence. It does not authorize a
merge, deployment, public ingress, credential use, provider execution, spend, external publish,
analytics write or takedown. Those actions remain bound to their separate gates.

G-08 later authorized only the repository merge sequence PR #12, then retarget/retest PR #13, then
PR #13 if all five CI jobs pass. It grants no runtime or external-execution authority.

The bounded remediation sequence completed PR #12 through PR #22. The latest merge is PR #22 at
`5936aa7a9656d728be751d0ee61011fc1a5abc7a`, after exact-head CI run `33161662691` and exact-main
CI run `33162305543` both passed 5/5. `V3-01-APP-010` is exhausted. Annotated tag
`vf-v3-01-rc2` peels to that exact main commit and means controlled acceptance planning only; it
does not authorize any runtime action. V3-01-10 requires a new G-08 before merge.

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
| Latest verified exact-main CI | [Video Factory V2 CI run 33162305543](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/33162305543), 5/5 success on `5936aa7a9656d728be751d0ee61011fc1a5abc7a` |
| Required checks observed | Python, renderer, Studio, safety/Compose, Docker deterministic E2E |
| Working tree at capture | clean before the audit branch was created |

Current repository checkpoint after the bounded merge sequence:

| Field | Verified value |
|---|---|
| Exact `origin/main` | `5936aa7a9656d728be751d0ee61011fc1a5abc7a` |
| Exact main tree | re-verify from exact main before any later merge |
| PR #12 | merged at `a9dfe87b479ebdb4e6a757543a7b47e9ac81ffd4` |
| PR #13 | retargeted/retested with 5/5 CI PASS, merged at `9b66d6917d6d58fea995b3a1049fc95198e81bf1` |
| PR #14 through PR #18 | merged sequentially under bounded G-08 records; no runtime authority |
| PR #19 | exact head `4b17fc1352ee4582db9b69f795531ef9b6a4feb4`; CI run `33153548402` PASS; merged before consolidation |
| PR #20 | exact head `a8a2cecc620cae4fc3bd072b53489db8b2acd7ec`; CI run `33155313793` PASS; merged as RC-1 |
| PR #22 / V3-01-09 | exact head `e6651948751fc8789ff83f91e0e7e8f88564e2aa`; CI run `33161662691` PASS; merged as exact current main |
| RC-2 | annotated `vf-v3-01-rc2` peels to exact main `5936aa7a9656d728be751d0ee61011fc1a5abc7a`; planning-only, not deployed |
| V3-01-10 | local/CI remediation branch; verified loader and G-03-A candidate only; unmerged and not RC-3 |
| Exact-main regression | CI run `33162305543` on `5936aa7a9656d728be751d0ee61011fc1a5abc7a`, all five jobs PASS |
| Deployment/provider/ingress action | none |

No `AGENTS.md` file exists in the repository. Repository instructions are therefore the checked-in
README, architecture, security, deployment, testing, V2 acceptance and runbook documents.

## Product and schema baseline

| Field | Verified value |
|---|---|
| API/worker/renderer/Studio version | `0.12.0` |
| API title | `NPD Video Factory V2 API` |
| Latest Alembic migration on `main` | `0011_v3_01_03_security_durable_safety` |
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
`EV-V3-DR-001`, `EV-V3-OPENAI-VISION-ADAPTER-001`.

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
through PR #20; V3-01-09 is merged through PR #22; RC-2 is locked for planning. Production verdict
remains `NO-GO`.

V3-01-09 implements a disabled OpenAI `gpt-5-mini` Vision adapter on RC-2. Its strict
Responses-schema, timeout/retry/circuit, duplicate, missing-credential, rights, budget, provenance
and VND receipt tests use MockTransport. External calls and actual spend are zero. V3-01-10 now
adds only a hash-pinned verified gate loader and an owner-review-pending G-03-A asset/rights
candidate. Because it changes code after RC-2, a future approved merge must be followed by
exact-main regression and an RC-3 lock before any runtime gate can be rebound.
