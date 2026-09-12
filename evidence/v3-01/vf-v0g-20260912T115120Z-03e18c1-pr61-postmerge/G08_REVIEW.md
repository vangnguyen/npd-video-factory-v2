# VF-V0G — PR #61 exact-head Case B G-08 review

Owner approval: controlled merge only if head remains exactly
`d7852b682b3042caebe6dfe280fc89591d4874df` and this review passes.

Observed 2026-09-12: PR #61 open/draft/mergeable, base main
`5fef0ecf4dde0c99ec1b220ffd1dc36dcfee6045`; zero unresolved review threads.
Exact-head CI `34683338030`: completed/success, all five jobs and all required
validation steps successful. No gate is bypassed or weakened.

## Exact diff classification

- Runtime: `docker-compose.yml` only; one line replaces the existing MinIO
  release with verified same-release Quay immutable digest
  `sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.
  No configuration, ports, credentials, healthcheck, storage, command, buckets,
  business logic or provider execution semantics are edited.
- Test: `apps/api/tests/test_minio_quay_digest_contract.py`; eight deterministic
  tests pin the reference and preserve consumed runtime/overlay contracts.
- Handoff: `docs/acceptance/v3-01/HANDOFF.md` and `handoff.json`.
- Engineering evidence: thirteen files under
  `evidence/v3-01/vf-v0f-20260912T081435Z-5fef0ec-minio-quay-pin/`.
  Historical provider evidence is not changed. PR #60 remains separate.

`git diff --check`, all twelve committed evidence checksums, handoff cross-hash,
JSON parsing, local Markdown links and supplemental secret scan: PASS.
The observed old cached image and Quay pin have identical image ID and all
rootfs layers. Consumed linux/amd64 server, health, bucket/object, persistence,
restart and shutdown capabilities passed; no all-feature/signature claim.

## Case B / immutable RC boundary

RC-17 tag object: `ea67843635dddf94ee25d38111fc06782ad9fd74`.
`vf-v3-01-rc17` peels to `d08ffc005d7f3ad517d355977b0bc3cc8d686906`.

Old RC/main executable SHA-256:
`ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.
Approved candidate executable SHA-256:
`ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5`.
Only the Compose blob changes the canonical executable hash.

G-08 review: PASS for the explicitly Owner-approved Case B controlled merge.
This is NOT a governance-only runtime-equality finding against RC-17.
The candidate is not RC-17. RC-17 operation provenance MUST remain blocked
against the changed tree. A fresh RC is required later, only after exact-main
CI/regression verification and a separately assigned VF-V0H.

No RC/tag, credential read, live reservation, provider call, authority
activation, production deployment or publish is authorized by this review.
Operation 1 remains PREPARED_NOT_AUTHORIZED; Operation 2 locked; kill switch
ENGAGED. Production NO-GO.
