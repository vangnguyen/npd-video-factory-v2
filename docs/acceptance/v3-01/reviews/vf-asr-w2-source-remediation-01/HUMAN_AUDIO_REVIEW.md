# RC25 Asset 01 human-listening review

Status: **PENDING**

This review is a human-only governance gate. Source preparation may proceed,
but the W2 candidate is not merge-eligible and no live W2 gate may be created
until the Owner records `CONFIRMED_REFERENCE`.

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

Current decision: `PENDING`

If the result is `REFERENCE_AUDIO_CONTRADICTION`, stop W2 acceptance and resolve
asset/reference governance. If it is `UNRESOLVED`, merge and live W2 execution
remain blocked.
