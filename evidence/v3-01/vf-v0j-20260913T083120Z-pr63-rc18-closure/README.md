# VF-V0J — RC-18 post-merge provenance closure

## Result

**PASS — authoritative executable candidate only, no execution authority.**
PR [#63](https://github.com/vangnguyen/npd-video-factory-v2/pull/63) merged exact
reviewed head `b9988d968feafcea04bf3e0e78d540bcb8eb5fe9` into actual main `553be01336e41ad1b145a5e1806ec565a658c6d7`.
RC-18 still targets `03e18c1f0c56fff8a13f167af74f34894c2db811`; no new RC was created.

## Evidence

- [G-08 review](G08_REVIEW.md), [classified diff / candidate proof](pr63-g08-review.json)
  and [controlled merge receipt](controlled-merge.json).
- [RC-18 origin](rc18-origin.json): created in prior Owner-bounded VF-V0H;
  annotated tag object `30ca09c4201cd6aea5e733c26ba4dfa1f30d5021`, unsigned, not retagged here.
- [Exact-main verification](post-merge-verification.json):
  [CI 34747898704](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34747898704)
  completed/success 5/5 on the actual merge commit, not a draft head.
- [Independent RC CI 34744690232](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34744690232):
  completed/success 5/5 on immutable tag `vf-v3-01-rc18`.
- [Canonical dual-CI](dual-ci-provenance.json):
  `68f6f583fc16bdeb3dcffdd85b983e8ad0ab229f51f4e4c13579b305a9697811`.
- [Executable-tree manifest](executable-tree-manifest.json):
  main = RC-18 = `ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
- [Selected exact CI log excerpt](exact-main-ci-excerpt.json) and
  [regression](regression.json): 958 Python/API/worker/ComfyUI-bridge,
  14 Studio, 14 Renderer, typecheck/bundle, migration replay, safety/Compose,
  acceptance/evidence, offline compatibility, expected Flow A/B/C/DR fixture
  blocks and Docker deterministic E2E PASS. Focused local checks: 168 PASS.
- [Historical integrity](historical-lineage-integrity.json) preserves VF-V0H
  and RC-17 receipts. Old handoff hashes refer to their Git version at the
  approved PR #63 head, not the refreshed handoff.
- Current canonical [HANDOFF.md](../../../docs/acceptance/v3-01/HANDOFF.md) and
  [handoff.json](../../../docs/acceptance/v3-01/handoff.json);
  [raw handoff hashes](handoff-checksums.json) and [manifest](SHA256SUMS.txt).

## Historical PR #62

[#62](https://github.com/vangnguyen/npd-video-factory-v2/pull/62) is still open/draft,
unchanged. Its old canonical handoff is superseded, but the unique historical
VF-V0G engineering evidence remains useful. Recommend preserving that bundle
through a separate Owner-reviewed import before deciding whether to close #62
without merge. Do not merge its stale handoff or silently remove evidence.

## Authority boundary

`RC18_AUTHORITY = NONE`; `OPERATION_1_AUTHORITY = NOT_CREATED`.
No new lineage ID, operation ID, scope, bundle, window or approval was generated.
RC-17 package remains historical/invalid for RC-18; Operation 2 locked and not
transferred. Kill switch engaged; bundle unmounted; checked-in runtime fixture,
blank model, external/paid false and budget 0 VND.

Task credential reads, live reservations, real provider calls, production writes
and actual provider cost: **0 / 0 / 0 / 0 / 0 VND**.
ASR **0/2 PASS**, Vision **2/2 PASS**, production **NO-GO**.

The refreshed handoff/evidence is a separate governance-only draft update
requiring its own Owner review before merge. Actual-main closure is anchored
to the already merged PR #63 main/CI, never to that later draft's CI.

**STOP before Operation 1 rebind or authority creation.**
No provider/credential/budget action, operation, new RC, deployment,
publishing, public ingress or analytics.
