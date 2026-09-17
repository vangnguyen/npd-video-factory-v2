# Master Parallel Directive — Lane C Flow A/B/C offline readiness

WORKSTREAM: Video Factory V3-01
LANE: C — Flow A/B/C
MILESTONE: RC-21 source/mock/offline readiness
VERDICT: PASS_OFFLINE_READINESS / REAL_FLOWS_BLOCKED
BASE GOVERNANCE MAIN: `6a0b7a52400458e4e91691251b0a42d827b4aa48`
RC: `vf-v3-01-rc21` → `6dcf144a4e3830e27fd617e52bc8eeab0952126e`
EXECUTABLE-TREE SHA-256: `e75e284a8cebb9864ed441c93cafea17717f247729fe0f3635e1a4f106795bd0`

This is a new evaluation of the existing, historical fixture contracts using
the RC-21 executable code. The fixture bundles still name their original
locked commits. Passing them again does **not** convert them into RC-21 real
media, real-provider, production-path or human-quality evidence. No RC-20 or
RC-21 Operation 1 execution material is used in this lane.

## Exact baseline

- Remote `main` equals the governance main above. Main CI
  [35197139061](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35197139061)
  and RC CI
  [35194969154](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/35194969154)
  each remain PASS 5/5, including deterministic Docker E2E.
- The unmodified dual-CI validator independently returns PASS, provenance
  SHA-256 `f57b4d2e6e7ea7b369b3cf1b6d63935725024723572d82fb173de19f50b81d5a`.
- The canonical 12-path executable-tree SHA recomputes to the value above on
  both governance main and RC-21. This lane changes no executable path.
- The expected fresh RC-21 ledger identity is only a plan in this lane. Lane C
  neither creates nor reads the RC-21 execution ledger.

## Offline stage matrix

| Flow | Stage/axis demonstrable without external action | Result | Remaining boundary |
| --- | --- | --- | --- |
| A | Upload checks, source preservation, deterministic ASR fixture, edit/scene/silence, reframe, timeline, subtitles, audio mix, final render, technical QC, rights/evidence contract | Implemented and mock-tested PASS; two fixture runs technically PASS | Accepted real ASR `0/2`; real-media reframe, accepted production voice, production path and artifact-bound full-watch remain blocked. |
| B | Business/creative brief hash, source/claim/script/originality, storyboard/media plan, fixture media generation, Vision QC, TTS/subtitles/audio, timeline/approval, render/QC, cost/rights receipts | Implemented and mock-tested PASS; two fixture runs technically PASS | Real research/source and media providers, production voice, production path and human quality remain blocked. |
| C | Trend provenance/cluster/score, idea/project lineage, hash-bound dry-run publish contract, idempotent replay, duplicate prevention, normalized nullable analytics, winner/learning lineage | Implemented and mock-tested PASS; two fixture runs technically PASS | Official trend/publish/analytics adapters and live post/readback are absent; G-05/G-06 and production/human gates remain blocked. |

Flow C rollback is deliberately a **no-automatic-external-rollback** policy:
ambiguous timeout or remote mismatch stops, requires official read/reconcile,
and any takedown/edit needs a new Owner-gated external write. The offline
publishing tests prove dry-run idempotency/recovery and fail-closed live
boundaries, not remote rollback. Flow C attribution presently means auditable
trend → idea → project → publication → snapshot → recommendation lineage.
Cross-platform identity and revenue attribution are explicitly outside the
implemented analytics contract; they are **not** claimed as PASS.

## Reproduction and acceptance axes

The three checked-in offline evaluators were rerun with their unchanged
two-run fixture bundles and `--expect-verdict BLOCKED`:

| Flow | Contract result | Mock axis | Overall | Fixture input SHA-256 |
| --- | --- | --- | --- | --- |
| A | Two runs technically PASS | PASS | BLOCKED | `5a2e375d6da149ff92d04051f305bc93709818e03ca4ff188df2b13d3c07ad2f` |
| B | Two runs technically PASS | PASS | BLOCKED | `d6cb7fb94032d964a32f52276efe7ba4374ec1ae9da4c50820761cda89c04c81` |
| C | Two runs technically PASS | PASS | BLOCKED | `bf39f1688a496f27f854ca823c66db66c71075dcb02b6ae39c563bcac653b2cc` |

Focused contract tests: **45/45 PASS**. Related API/worker/bridge
regression: **83/83 PASS**. Studio: **14/14 PASS**. Renderer:
**14/14 PASS**, with typecheck and bundle check PASS. The V3-01 repository
validator also passed (60 matrix rows, 16 gaps, 13 schemas, 74 approvals,
39 historical evidence runs). Current canonical CI covers the Docker E2E;
this lane did not perform a new local Docker run.

The machine-readable [readiness record](flow-readiness.json) fixes exact
contract/fixture hashes and separates offline PASS from every blocked real
axis. This is not an execution authority, release candidate or production
GO. No provider credential was read, budget reserved, provider called,
external post made or production business record written. Kill-switch
checked-in default remains engaged; no runtime transition occurred.

## Next boundary

Lane A owns fresh RC-21 custody and the ASR real-provider chain. Lane B owns
production Vietnamese TTS readiness and human voice acceptance. Lane C can
prepare fixture and review material in parallel, but Flow A real E2E must
wait for accepted real ASR; Flow B real E2E requires separately authorized
provider/source evidence; Flow C real E2E requires separately authorized
publish and analytics integrations. No executable-changing merge or external
action is authorized by this readiness milestone.
