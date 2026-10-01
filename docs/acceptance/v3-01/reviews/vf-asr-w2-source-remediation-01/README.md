# VF-ASR-W2-SOURCE-REMEDIATION-01

This bounded source candidate adds one explicit, immutable Whisper Vietnamese
request profile: `asr-whisper-vi-w2-v1`. It grants no provider authority, creates
no operation, and performs no provider or credential action.

W0 remains the empty profile selection. W1 remains byte- and hash-identical. W2
must be selected explicitly by a future gate and binds its prompt, tokenizer,
scope, request manifest, cache fingerprint, provenance and evaluator expectation.
There is no W1→W2 fallback.

The W2 prompt is 149 UTF-8 bytes, has SHA-256
`25137205335eb4e5717e2d2c38c2e7a89208e55061a63c03fd20b6eb7faec578`,
and produces 43 raw and 43 context tokens under the pinned local Whisper ranks.
Its canonical profile SHA-256 is
`ff2063a761247b5d59edbefd2c155c00dff917177fd03f8851805b8ff9d01446`.

Quality thresholds and normalization remain unchanged: WER ≤ 0.15, critical-term
recall 8/8, exact contiguous normalized tokens, and Vietnamese diacritics
preserved. Asset 02 remains an offline negative-insertion control only; no real
provider safety claim is made.

Human review is tracked in [HUMAN_AUDIO_REVIEW.md](HUMAN_AUDIO_REVIEW.md) and is
currently `PENDING`. Therefore `MERGE_ELIGIBLE = FALSE` even if source CI passes.
