# VF-V0F — Same-release MinIO Quay digest candidate

## Decision for Owner G-08

**REVIEW_REQUIRED — Case B.** The local compatibility checks and Docker E2E
pass, but the Compose image reference is part of the canonical executable tree.
This candidate is not RC-17. No merge, new RC, retag or operation authority is
performed by this task.

Source main: `5fef0ecf4dde0c99ec1b220ffd1dc36dcfee6045`.
Immutable RC-17: `vf-v3-01-rc17` →
`d08ffc005d7f3ad517d355977b0bc3cc8d686906`.

## Minimal patch and verified provenance

Only the MinIO image reference in `docker-compose.yml:32` changes:

- Old: `minio/minio:RELEASE.2025-09-07T16-13-09Z`.
- New: `quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.

No alternate release, floating tag, mirror, MinIO configuration, credentials,
port, health-check, command, bucket, storage topology or business logic change.
The production overlay inherits this base reference; it has no image override.
The regression test protects the digest and consumed Compose contract.

The Quay manifest response is HTTP 200. Its raw SHA-256 and registry digest
header match the pin. The index includes linux/amd64 (the required runner
architecture), arm64 and ppc64le; only amd64 behavior is tested here.
The cached original Hub release and the anonymously pulled Quay digest have
identical observed Docker image ID and every rootfs layer. This is stronger
than a release-name comparison, but is not a new signature or vulnerability
attestation. MinIO's existing AGPL/maintenance risk is unchanged.

Primary sources: [official release](https://github.com/minio/minio/releases/tag/RELEASE.2025-09-07T16-13-09Z),
[release source README with official Quay reference](https://github.com/minio/minio/blob/07c3a429bfed433e49018cb0f78a52145d4bedeb/README.md),
[exact Quay manifest](https://quay.io/v2/minio/minio/manifests/sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e).

## Compatibility evidence

[Image identity](image-identity.json), [registry verification](registry-diagnostics.json)
and [integration receipt](compatibility.json) distinguish observation from inference.

Tests covered server startup with `server /data --console-address :9001`,
API health, console, create bucket, put/head/get/list/delete object, same-volume
persistence across the old/new references, restart persistence and clean
shutdown. Ports remain 9000/9001 inside the container; task-local host bindings
were ephemeral loopback ports. Fixture containers/volume were removed.

The unmodified deterministic E2E additionally verified MinIO artifact recovery,
a final rendered video, and disposable backup/failure/restore/restart checks.
[DR receipt](local-dr-drill.json) preserves observed restore hashes and
[render QC](local-render-qc.json) preserves measured output. This is local/CI
engineering evidence, **not production-path acceptance**.

## Executable-tree / RC impact

| Item | SHA-256 |
| --- | --- |
| RC-17 / source main | `ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40` |
| Patched candidate | `ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5` |

[Lineage impact](lineage-impact.json) identifies `docker-compose.yml` as the
only hashed path that changed. Tests/docs/evidence do not enter this hash.
The runtime behavior exercised above is equivalent, but Git-object identity
is not; the current RC contract therefore requires a new executable
candidate/RC after separately authorized merge and regression. None is
created here.

Do not substitute successful candidate PR CI for the failed exact-main run
`34670260472`, or present the patched tree as identical to RC-17.
RC-17 operation provenance remains blocked against a runtime-changing
candidate; the validator must keep rejecting that mismatch.

## Validation / evidence boundaries

[Candidate CI](candidate-ci.json) is completed/success, 5/5 on
`ed976c0e222ef2d732bd5bf6b822ba845b2a56de`; the
[E2E excerpt](candidate-ci-e2e-excerpt.txt) shows a successful fresh MinIO pull,
artifact recovery, disposable DR and final render QC. The
[provenance record](candidate-ci-provenance.json) binds that run to that commit
and separately preserves the expected RC-17 operation-eligibility rejection.
The text excerpt normalizes line endings/trailing whitespace for Git hygiene;
the original provider-free CI logs remain available on GitHub.
The final docs/evidence head must receive its own exact-head CI; its observation
is recorded in the PR body/task receipt, not substituted from this earlier run.

[Local validation](local-validation.json) records 958 Python tests, 32 focused
tests, 14 Studio tests, 14 Renderer tests, 36 safety steps, acceptance/Flow A–C
boundary checks, migration replay, MinIO integration and Docker E2E.

Environmental failed attempts are retained as diagnostic notes: E2E fixture
activation overlapped the first Python run; the subsequent exact restored
configuration passed all tests. The external MinIO harness needed to
rediscover Docker's ephemeral port after restart. Neither was resolved by
changing product behavior or weakening a gate.

This engineering bundle has its own checksum manifest. It does not add or
upgrade a real-provider/quality acceptance row. Historical receipts and
the original MinIO pull failure remain immutable. PR #60 stays separate.

## Safety / stop

Operation 1 remains `PREPARED_NOT_AUTHORIZED`; Operation 2 remains
`NOT_APPROVED / LOCKED`; kill switch remains engaged and the gate bundle
unmounted. ASR remains 0/2 PASS; Vision remains 2/2 PASS; production remains
**NO-GO**.

This task: 0 owned credential reads, 0 paid-provider calls, 0 live budget
reservation, 0 VND provider cost, 0 production writes. Local development
database/object writes are isolated disposable fixtures only.

Next safe action: Owner reviews Draft PR #61's final exact head and executable
impact under G-08. Stop before merge, RC creation or Operation 1 authority.
