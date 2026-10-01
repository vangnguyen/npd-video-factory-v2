# RC25 Asset 01 human-listening review

Status: **CONFIRMED_REFERENCE**

This review is a human-only governance gate. The Owner has now recorded
`CONFIRMED_REFERENCE`; merge eligibility remains subject to fresh exact-head CI
and the controlled-merge checks. This decision does not create a live W2 gate.

## Immutable input

- Asset ID: `asset-g03-asr-vi-owned-01`
- Original WAV SHA-256: `fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef`
- Reference transcript SHA-256: `585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e`
- Expected phrase under review: `chính sách bán hàng`

Listen to the exact original WAV at both targets. Do not use ASR output or an
automated judgment as the decision.

1. `51.180000s → 55.840000s`
2. `84.080002s → 88.879997s`

## Owner decision

Choose exactly one:

- `CONFIRMED_REFERENCE`
- `REFERENCE_AUDIO_CONTRADICTION`
- `UNRESOLVED`

Current decision: `CONFIRMED_REFERENCE`

Owner decision UTC: `2026-10-01T10:31:42Z`

The Owner listened to both exact original-WAV ranges listed above and confirmed
that the reference phrase is `chính sách bán hàng`. This is a human listening
decision; no automated acoustic review was used to reach it.

If the result is `REFERENCE_AUDIO_CONTRADICTION`, stop W2 acceptance and resolve
asset/reference governance. If it is `UNRESOLVED`, merge and live W2 execution
remain blocked.
