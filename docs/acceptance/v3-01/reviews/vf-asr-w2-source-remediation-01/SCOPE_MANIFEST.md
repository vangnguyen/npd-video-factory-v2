# Scope manifest

Task: `VF-ASR-W2-SOURCE-REMEDIATION-01`

Base: `d42cb40753c9491cb24bf4177d47f7db63e4adb4`

Authorized candidate paths:

1. `apps/api/app/asr_prompt_profile.py`
2. `apps/api/app/data/whisper/README.md`
3. `apps/api/tests/test_asr_prompt_profile.py`
4. `apps/api/tests/test_w2_prompt_profile.py`
5. `apps/api/tests/test_w1_prompt_gate_binding.py`
6. `apps/api/tests/test_w1_prompt_provider_path.py`
7. `apps/api/tests/test_w1_prompt_quality_guard.py`
8. `docs/acceptance/v3-01/schemas/asr-post-run-input.schema.json`
9. `docs/acceptance/v3-01/tools/v3_01_25_w1_quality_guard.py`
10. `docs/acceptance/v3-01/reviews/vf-asr-w2-source-remediation-01/README.md`
11. `docs/acceptance/v3-01/reviews/vf-asr-w2-source-remediation-01/HUMAN_AUDIO_REVIEW.md`
12. `docs/acceptance/v3-01/reviews/vf-asr-w2-source-remediation-01/SCOPE_MANIFEST.md`
13. `docs/acceptance/v3-01/V3-01-OFFLINE-PREPARATION-MANIFEST.json`

This scope adds an explicit W2 registry entry and only the downstream schema,
tests, deterministic checksum refresh and review material needed to prove its
fail-closed behavior. It does not
change provider/model selection, quality thresholds, operation identity,
authority, budget, credentials, execution windows or runtime activation.

Excluded and absent: RC tag, lineage, operation, approval record, gate bundle,
operation authority, O2, runtime binding, resolver policy, execution catalog,
provider call, credential read, reservation, publish, production mutation.
