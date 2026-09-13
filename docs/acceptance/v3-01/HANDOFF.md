# NPD Video Factory Handoff

Canonical machine record: [handoff.json](handoff.json).
Only these two acceptance-docs handoff paths are current; no root duplicates.
This checkpoint replaces the current handoff view, never historical receipts.

## Current checkpoint — VF-V0J

**PASS — existing RC-18 provenance closed; no execution authority.**

- [PR #63](https://github.com/vangnguyen/npd-video-factory-v2/pull/63) merged
  exact Owner-reviewed head `b9988d968feafcea04bf3e0e78d540bcb8eb5fe9`.
- Merge commit / verified actual main: `553be01336e41ad1b145a5e1806ec565a658c6d7`.
- RC-18 remains `vf-v3-01-rc18` -> `03e18c1f0c56fff8a13f167af74f34894c2db811`.
- Annotated tag object: `30ca09c4201cd6aea5e733c26ba4dfa1f30d5021`.
- Main = RC-18 canonical executable-tree SHA-256:
  `ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
- [RC CI 34744690232](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34744690232):
  independently dispatched on immutable tag, completed/success 5/5.
- [Actual exact-main CI 34747898704](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34747898704):
  push on the actual merge commit, completed/success 5/5.
- Canonical dual-CI provenance: **PASS**,
  SHA-256 `68f6f583fc16bdeb3dcffdd85b983e8ad0ab229f51f4e4c13579b305a9697811`.
- ASR **0/2 PASS**, Vision **2/2 PASS**, production **NO-GO**.

## RC-18 origin and preservation

RC-18 was created in the earlier bounded Owner-authorized VF-V0H task, not
recreated by VF-V0J. Its checksummed pre-tag absence proof at
2026-09-13T07:12:55.794309+00:00 precedes live tagger metadata
2026-09-13T07:13:12Z (vangnguyen). The annotation snapshot matches the live tag,
all 18 source/rights/media/reference bindings match the exact target commit,
and independently tag-bound CI passed.

The tag is **annotated but unsigned**. Origin is established from the bounded
task/tool history and matching Git/GitHub engineering evidence; this is not a
claim of cryptographic signature attestation. Source was not mutated while
tagging; no new executable commit, new RC or retag was created in this task.

The original VF-V0H same-commit provenance block is historical and retained.
After this separately approved governance merge, actual main and executable RC
are distinct, successful CI roles are distinct, governance diff is complete and
allowlisted, and selected executable trees match. No validator/allowlist/hash
algorithm or CI gate was bypassed.

## Immutable contracts and no transferred authority

MinIO remains same-release immutable
`quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.

W1 remains `asr-whisper-vi-w1-v1`.
Profile SHA-256:
`9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1`.
Prompt SHA-256:
`6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48`.
No asset, transcript, RightsRecord, budget, timeout or quality threshold changed.

RC-17 remains immutable:
`vf-v3-01-rc17` -> `d08ffc005d7f3ad517d355977b0bc3cc8d686906`.
Tag object `ea67843635dddf94ee25d38111fc06782ad9fd74`; old tree
`ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.

RC-17 Operation 1 package is **HISTORICAL_REFERENCE_ONLY / INVALID_FOR_RC18**.
Old operation IDs, scope/bundle, window, authority and reservation state are
not copied or transferred. No historical provider result, usage/cost,
transcript or timing is reconstructed or retrospectively upgraded.

## Authority boundary

- **RC18_AUTHORITY = NONE.**
- **OPERATION_1_AUTHORITY = NOT_CREATED.**
- Operation 2 **NOT_APPROVED / LOCKED / NOT_TRANSFERRED**.
- Kill switch **ENGAGED**; bundle **UNMOUNTED**.
- Checked-in runtime: fixture, blank transcription model, external/paid false,
  provider budget 0 VND.
- New lineage/operation IDs, scope, bundle, window and approvals: **NOT_CREATED**.
- No live provider ledger or credential mechanism accessed.
- Task credential reads / live reservations / real provider calls /
  production writes / actual provider cost: **0 / 0 / 0 / 0 / 0 VND**.

Provenance closure is not an operation approval. This task stops before
Operation 1 rebind or authority creation.

## Regression and historical evidence

Exact-main local regression: **958 Python/API/worker/ComfyUI-bridge PASS**;
focused provenance/W1/lineage checks: **168 PASS**.
Actual exact-main CI: **958 Python, 14 Studio, 14 Renderer PASS**,
renderer typecheck/bundle, safety/Compose, migration upgrade/down/replay
through `0014_v3_01_27`, acceptance/evidence, offline ASR compatibility
and Docker deterministic E2E PASS. Flow A/B/C/DR fixture boundaries remain
**BLOCKED_AS_EXPECTED**, not production-path evidence.

All 13 prior VF-V0H bundle manifest entries remain valid.
Its sealed handoff checksums refer to the Git version at PR #63's approved
head, not this updated current handoff.

[PR #62](https://github.com/vangnguyen/npd-video-factory-v2/pull/62) stays open/draft,
unchanged. Its older canonical handoff is superseded; unique historical VF-V0G
engineering evidence should be retained through a separate Owner-reviewed
import before deciding whether to close without merge. Do not merge the old
handoff blindly or silently delete evidence.

## Publication, evidence and stop

[Fresh VF-V0J evidence](../../../evidence/v3-01/vf-v0j-20260913T083120Z-pr63-rc18-closure/README.md)
seals origin, exact-head review, controlled merge, actual-main CI,
canonical dual-CI, tree equality, regression and historical integrity.

This handoff/evidence update lives on separate governance branch
`handoff/vf-v0j-rc18-provenance-closure` and requires its own Owner review before merge.
Actual-main closure is anchored to `553be01336e41ad1b145a5e1806ec565a658c6d7` and CI 34747898704,
never to a later draft head. Head/CI self-reference is reported externally.

Canonical handoff JSON SHA-256: `5d0af7ec54e4f4e17b0ef309861bb97d7e9f7615d11c6dcfc0dacededcf2601c`.

**NEXT_SAFE_ACTION:** Owner review of this separate governance-only handoff/
evidence update. A future ASR RC-18 rebind requires a separately assigned task.

**STOP before Operation 1 rebind, authority creation/activation, credential
access, budget reservation or provider execution.** No Operation 2, new RC,
deployment, publishing, public ingress, analytics, TTS or Images 2.5.
Do not execute NEXT_SAFE_ACTION automatically.
