# AssemblyAI connection preparation

PHASE: 4 — connection prerequisite, not speech ASR certification.

STATUS: Local connection implementation PASS; real account connection AWAITING OWNER CREDENTIAL. The Owner selected AssemblyAI on 2026-10-05. The previous provider-choice blocker is resolved; no real key was supplied or discovered.

HEAD SHA: Parent `9b47e8a80a57977ce3d4080ab67c2100b4ca6827`; implementation is in the subsequent connection commit.

FILES CHANGED: `assemblyai_connection.py`, compatible optional Config secret path, local server connection routes, `assemblyai.html`/`assemblyai.mjs`, Studio navigation and connection security tests/evidence. No project schema or voice preset changed.

TESTS: 66/66 native and 24/24 Studio PASS. Nine connection cases exercise real Windows user-scope DPAPI encryption/decryption, protected ACL, restart-safe receipt binding, no plaintext fallback, no credential overwrite, cipher tamper detection, failed-verification invalidation, one read-only verification request, sanitized auth/network/redirect/rate-limit failures, HTTP session/origin/CSRF/body limits and busy-job refusal. HTTP provider responses and credentials in these unit tests are explicitly fixtures; no test makes a real AssemblyAI request. An actual isolated browser test verifies missing-key state, invalid-format rejection, clearing the password field, disabled autocomplete and refresh persistence.

EVIDENCE: `connection-native-tests.log`, `connection-studio-tests.log`, `connection-ui-verification.json`; Owner handoff screenshot and live-upgrade receipt are recorded after installing the verified increment.

CAPABILITIES ADDED: Local non-CLI connection page at `/settings/assemblyai`. Owner enters the key directly; a single bounded `GET https://api.assemblyai.com/v2/transcript?limit=1` verifies authentication without uploading audio, creating a transcript or decoding/persisting account transcript bodies. No automatic retry, redirect, proxy-env forwarding or response-body logging. On success the credential is encrypted with Windows DPAPI for the current user, stored at `C:\NPD-Video-Factory\secrets\assemblyai.dpapi` outside Git, with file access restricted to that user and LocalSystem. Only a cipher-bound verification receipt/status is exposed. Existing saved credentials can be rechecked without re-entering or returning the value. Failed rechecks revoke verified status and preserve the ciphertext.

REGRESSIONS: Supported native/Studio tests pass. Initial connection tests exposed a verification-script dependency on a Windows PowerShell module that could not load under the inherited module path; the independent ACL check now uses the built-in .NET file-security API and passes. This was test tooling, not a failed key-encryption or ACL operation. No provider adapter/profile duplication, dependency upgrades or real TTS call occurred.

BLOCKERS: The real AssemblyAI key is still absent. Connection verification and actual speech-video transcript/timestamp/restart/failure acceptance are NOT RUN. The existing strict AssemblyAI profile/adapter remains selected for the forthcoming transcription integration; credential setup alone does not enable or certify native ASR.

NEXT ACTION: Owner opens the local connection page, enters their AssemblyAI key and selects “Kiểm tra & lưu kết nối”. Once real verification succeeds, continue native extraction/transcription integration by reusing the existing adapter and run the required real speech-video evidence. Do not ask for a key in chat, record it in evidence, or treat fixture verification as a live connection.

Source verification: [AssemblyAI list-transcripts reference](https://www.assemblyai.com/docs/pre-recorded-audio/api-reference/transcripts/list), [supported languages](https://www.assemblyai.com/docs/pre-recorded-audio/supported-languages). The selected profile/model/language remain `asr-assemblyai-vi-direct-v1` / `universal-3-5-pro` / `vi`; no model fallback was enabled.
