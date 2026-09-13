# VF-V0H — RC-18 materialization and provenance stop

## Outcome and stop boundary

**REVIEW_REQUIRED.** The Owner-authorized annotated executable candidate
`vf-v3-01-rc18` was created without creating or changing an executable commit.
The tag points to exact verified main
`03e18c1f0c56fff8a13f167af74f34894c2db811` and canonical executable-tree SHA-256
`ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.

The fresh [RC-bound CI](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34744690232)
is dispatched explicitly on the annotated tag; a tag push alone does not
trigger the current workflow. Its exact observed result is sealed in
[rc-ci.json](rc-ci.json). The previous
[main CI](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34691861788)
is recorded independently in [baseline-main-ci.json](baseline-main-ci.json);
it is not substituted for RC-bound CI.

The existing canonical dual-CI contract requires **different executable-RC and
governance-main commits**, different successful run IDs, an exact complete
allowlisted governance diff, and equal selected executable trees. Current
actual main is the RC-18 commit itself. Thus the existing same-commit main cannot
satisfy post-materialization dual-CI, even after an independently successful
tag-bound run. See [blocked post-materialization provenance](dual-ci-blocked.json).

A separate governance-only **draft** handoff PR is prepared for Owner G-08.
Its branch/head/CI is a candidate only, **not merged governance main**.
It is not merged by this task. No validator, workflow, runtime, provider
configuration, budget, quality threshold or safety envelope is weakened.

## Exact materialization anchors

- Tag: `vf-v3-01-rc18`.
- Annotated tag object: `30ca09c4201cd6aea5e733c26ba4dfa1f30d5021`.
- Commit: `03e18c1f0c56fff8a13f167af74f34894c2db811`.
- Canonical executable-tree SHA-256: `ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
- Next-identifier proof: canonical positive-integer RC tag pattern plus the
  Owner sequential rule, contiguous public identifiers RC-1 through RC-17,
  and absence of RC-18 immediately before creation. This is not an invented
  automatic sequencing validator.
- Existing RC-17 tag object:
  `ea67843635dddf94ee25d38111fc06782ad9fd74`.
- Existing RC-17 commit:
  `d08ffc005d7f3ad517d355977b0bc3cc8d686906`, immutable and unchanged.
- Original blocked VF-V0H / hash-reconciliation records remain historical;
  the independently reconciled 64-character canonical SHA is used exactly.
  No historical receipt is silently repaired.

[Pre-tag preflight](pre-tag-preflight.json),
[annotation snapshot](tag-annotation.json),
[materialization receipt](materialization.json), and
[canonical input manifest](executable-tree-manifest.json) provide the exact
commit/tree/profile/rights/media/MinIO bindings. The annotation pins existing
contracts; it grants no operation authority.

## Canonical hashing and source preservation

The unchanged collector is `scripts/v3_01_ci_provenance.py::_git_object_map`;
the unchanged algorithm is
`apps/api/app/provider_ci_provenance.py::executable_tree_sha256`.
It resolves the 12 canonical POSIX paths into Git object IDs, sorts keys
lexicographically, and hashes compact UTF-8 JSON without a BOM or final newline.
Files outside that explicit path set do not enter this hash.

Two fresh pre-tag computations and post-tag computation agree.
The selected source objects and all 18 annotation-bound blobs remain exact.
The clean detached RC worktree was not edited; handoff changes are isolated in
a different governance branch. No new executable commit or RC-17 mutation
occurred.

Pinned same-release MinIO reference:
`quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.

W1 profile: `asr-whisper-vi-w1-v1`.
Profile SHA-256:
`9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1`.
Prompt SHA-256:
`6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48`.

## Authority and future rebind inventory

**OPERATION_1_AUTHORITY = NOT_CREATED.** Because post-merge RC-18 dual-CI is
still gated, no executable Operation 1 package, fresh lineage ID, operation ID,
approval, scope hash, bundle hash, window or reservation is created here.

The future separately assigned rebind task must regenerate, after provenance
PASS:

1. RC-18-bound lineage v2 and two distinct slot identities.
2. Exact commit and executable-tree binding.
3. Execution-scope hash, scope SHA and bundle SHA.
4. Asset/reference-transcript hashes and exact asset-specific RightsRecords.
5. W1 profile/prompt binding and provider/model/capability/language binding.
6. Separately approved fresh dated window and unchanged 500 VND/operation,
   1,250 VND/window, 90-second provider / 120-second controller envelope,
   concurrency 1, one attempt, no retry and no fallback.
7. Kill-switch binding and a separate Owner operation-authority receipt.

Existing WAVs, reference transcripts and RightsRecords are inspected as
committed artifacts only, not inherited runtime approval. Their exact hashes
are retained in the annotation; future expiry/consent/scope revalidation remains
required. No transcript, word timing, historical provider verdict or actual
provider cost is reconstructed or changed.

RC-17 Operation 1 package: **HISTORICAL_REFERENCE_ONLY / INVALID_FOR_RC18**.
RC-17 Operation 2: **NOT_APPROVED / LOCKED / NOT_TRANSFERRED**.
No old operation ID, approval receipt, window, scope, bundle or reservation state
is copied to a fresh executable operation.

Kill switch **ENGAGED**; bundle **UNMOUNTED**; checked-in external/paid execution
**false**, transcription provider **fixture**, model **blank**, budget **0 VND**.
No credential material or live provider ledger is accessed.
Task credential reads, provider calls, live reservations, production writes
and actual provider cost are **0 / 0 / 0 / 0 / 0 VND**.
ASR remains **0/2 PASS**, Vision **2/2 PASS**, production **NO-GO**.

## Historical PR #62 disposition

[Draft PR #62](https://github.com/vangnguyen/npd-video-factory-v2/pull/62) retains
historical VF-V0G post-PR-61 evidence and its earlier handoff view.
Observed head: `d435f06a0ae74fa8e51e77b589f81d845b95179c`.
Its nine changed files are governance-only. It is not modified, merged, closed
or deleted by this task; its evidence is not mislabeled as new RC-18 provenance.
Before any later merge, Owner must coordinate the two overlapping canonical
handoff paths so the older snapshot cannot overwrite the newer RC state.
No evidence history is silently removed.

## Validation and next safe action

[Validation receipt](validation.json) distinguishes new local focused checks,
fresh tag-bound full CI, checksum verification of VF-V0F/VF-V0G engineering
evidence, and the intentionally blocked actual-main dual-CI gate.
Any governance draft-head CI/provenance remains a **candidate observation**;
after Owner-authorized merge, fresh exact-main CI and canonical provenance
must be collected on the actual merged main.

Canonical current handoff:
[HANDOFF.md](../../../docs/acceptance/v3-01/HANDOFF.md) and
[handoff.json](../../../docs/acceptance/v3-01/handoff.json).
Their final raw hashes are sealed in [handoff checksums](handoff-checksums.json);
the bundle is sealed by [SHA256SUMS.txt](SHA256SUMS.txt).

**STOP at Owner G-08 for the separate governance-only handoff PR.**
Do not auto-merge, retag RC-18/RC-17, create RC-19, create/activate Operation 1
authority, read a credential, reserve budget, call a provider, deploy, publish
or enable ingress/analytics. Do not execute the next safe action automatically.
