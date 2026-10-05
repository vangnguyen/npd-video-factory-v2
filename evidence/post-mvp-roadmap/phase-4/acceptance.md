# Phase 4 — ASR credential/provider gate

PHASE: 4 — ASR + Media Understanding

STATUS: BLOCKED — Owner decision required. Speech-video ASR acceptance is NOT RUN.

HEAD SHA: `177ea75606b6f9ced09b2810979c415a07ec2186` (implementation at readiness check).

FILES CHANGED: `provider-readiness.json`, this report. No ASR implementation or provider configuration has been changed in this phase.

TESTS: Read-only provider/profile/credential-presence check. The current supported regression results remain 57/57 native and 24/24 Studio. No actual ASR call, transcript or timestamp acceptance run occurred.

EVIDENCE: `provider-readiness.json`; existing `apps/api/app/assemblyai_asr_profile.py`, `assemblyai_transcription_provider.py`, `openai_transcription_provider.py`; Phase 3 explicit unavailable-provider test.

CAPABILITIES ADDED: Readiness evidence only. Phase 3 already returns `ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT` for speech-video input requiring an unavailable native ASR provider. No placeholder transcript is persisted.

REGRESSIONS: No application changes in Phase 4; native/Studio passing results stand. Legacy Windows baseline failures remain open.

BLOCKERS: The existing selected AssemblyAI profile `asr-assemblyai-vi-direct-v1` refers to `secret://assemblyai/stt-video-factory-benchmark`. This Windows runtime has neither an AssemblyAI environment credential nor an `assemblyai.env` file. Native ASR is not configured. The existing OpenAI transcription adapter is an alternative requiring an explicit provider decision; the saved OpenAI content key is present but was not automatically repurposed for paid ASR.

NEXT ACTION: Owner chooses (a) OpenAI ASR with the existing locally saved key and ASR charges, or (b) secure connection of the existing AssemblyAI provider using its own credential. Then reuse the chosen existing adapter, validate extraction/transcript/timestamps/lineage/restart/failure handling, and perform an actual speech-video test before marking Phase 4 PASS.

The stop comes directly from the task's STOP CONDITIONS: **“cần secret/credential chưa có”** and **“cần trả phí provider mới”**. The choice has been requested. No dependent ASR work proceeds without the answer; no credential values were read or printed during readiness checks.
