# AssemblyAI connection preparation

PHASE: 4 — connection prerequisite, not speech ASR certification.

STATUS: Local connection implementation and actual AssemblyAI account authentication PASS. The Owner selected AssemblyAI and explicitly authorized computer retrieval of its existing benchmark key on 2026-10-05. Credential setup is complete; speech ASR certification remains pending.

HEAD SHA: `4420a9247ac4a1bd533fa740e0c90435b7f3e7d8` (connection implementation).

FILES CHANGED: `assemblyai_connection.py`, compatible optional Config secret path, local server connection routes, `assemblyai.html`/`assemblyai.mjs`, Studio navigation and connection security tests/evidence. No project schema or voice preset changed.

TESTS: 66/66 native and 24/24 Studio PASS. Nine connection cases exercise real Windows user-scope DPAPI encryption/decryption, protected ACL, restart-safe receipt binding, no plaintext fallback, no credential overwrite, cipher tamper detection, failed-verification invalidation, one read-only verification request, sanitized auth/network/redirect/rate-limit failures, HTTP session/origin/CSRF/body limits and busy-job refusal. HTTP provider responses and credentials in these unit tests are explicitly fixtures; no test makes a real AssemblyAI request. An actual isolated browser test verifies missing-key state, invalid-format rejection, clearing the password field, disabled autocomplete and refresh persistence.

EVIDENCE: `connection-native-tests.log`, `connection-studio-tests.log`, `connection-ui-verification.json`, `connection-live-before.json`, `connection-live-after.json`, `assemblyai-owner-connection.png`. Main Studio has the verified increment; original project/job/event rows are identical to the pre-restart backup, SQLite integrity is `ok`, and the account remains honestly marked missing-key/disconnected. The isolated helper was stopped and its data retained.

CAPABILITIES ADDED: Local non-CLI connection page at `/settings/assemblyai`. Owner enters the key directly; a single bounded `GET https://api.assemblyai.com/v2/transcript?limit=1` verifies authentication without uploading audio, creating a transcript or decoding/persisting account transcript bodies. No automatic retry, redirect, proxy-env forwarding or response-body logging. On success the credential is encrypted with Windows DPAPI for the current user, stored at `C:\NPD-Video-Factory\secrets\assemblyai.dpapi` outside Git, with file access restricted to that user and LocalSystem. Only a cipher-bound verification receipt/status is exposed. Existing saved credentials can be rechecked without re-entering or returning the value. Failed rechecks revoke verified status and preserve the ciphertext.

REGRESSIONS: Supported native/Studio tests pass. Initial connection tests exposed a verification-script dependency on a Windows PowerShell module that could not load under the inherited module path; the independent ACL check now uses the built-in .NET file-security API and passes. This was test tooling, not a failed key-encryption or ACL operation. No provider adapter/profile duplication, dependency upgrades or real TTS call occurred.

BLOCKERS: Actual speech-video transcript/timestamp/restart/failure acceptance is NOT RUN. Real account connection verification is now PASS. The existing strict AssemblyAI profile/adapter remains selected for the forthcoming transcription integration; credential setup alone does not enable or certify native ASR.

NEXT ACTION: Continue native extraction/transcription integration by reusing the existing adapter and run the required real speech-video evidence. Do not ask for a key in chat, record it in evidence, or treat fixture verification as a live connection.

Source verification: [AssemblyAI list-transcripts reference](https://www.assemblyai.com/docs/pre-recorded-audio/api-reference/transcripts/list), [supported languages](https://www.assemblyai.com/docs/pre-recorded-audio/supported-languages). The selected profile/model/language remain `asr-assemblyai-vi-direct-v1` / `universal-3-5-pro` / `vi`; no model fallback was enabled.

Actual account update: `connection-real-account.json` records one real authentication GET with zero audio uploads/transcript creations. `assemblyai-connected.png` shows the local success message. Existing benchmark key retrieved through active Chrome UI under explicit Owner authorization; no new key created, no value printed/logged/persisted in plaintext. Browser clipboard cleared after encrypted saving. Fresh-process decryption succeeds; original projects/jobs/events match the backup exactly and SQLite integrity is `ok`. Historical missing-key receipts remain preserved as earlier checkpoints.
