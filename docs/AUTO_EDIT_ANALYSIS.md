# Auto Edit Analysis — V2-04

V2-04 implements the analysis backbone of Mode B. It does not implement the editable timeline,
preview, final render or publish path. Those remain later gated PRs.

## Flow

```text
init upload
  -> upload numbered raw parts
  -> complete: size + SHA-256 + magic/MIME + FFprobe
  -> immutable source object + provenance
  -> normalized transcript
  -> shot/audio/transcript scene evidence
  -> reversible silence decisions
  -> explainable Top 3/Top 5 highlights
  -> PostgreSQL recovery
```

Upload sessions and all analysis entities belong to one workspace/project. Parts are staged below
`UPLOAD_STAGING_ROOT`; part numbers, part sizes and upload totals are bounded. Completion streams
parts into one assembled file, verifies the expected checksum and deduplicates an identical source
asset in the same project. Object keys contain only validated segments.

## Transcript contract

`TranscriptionProvider` returns language, confidence, segments and word timestamps. The first
normalized transcript is persisted as `version=1` and `is_original_evidence=true`. V2-04 exposes
no update endpoint, so original evidence cannot be overwritten. Future edits must create a new
version.

Development and CI select `fixture-transcription`, a synthetic Vietnamese provider with no network
or paid call. Production startup rejects fixture mode. The live contract adapter is deliberately
`not_configured` and returns HTTP 503 until separately approved.

## Scene, silence and highlight decisions

The provider-neutral pipeline accepts shot boundaries and audio silence signals, then combines
them with transcript timing/semantics. FFmpeg is the production-capable local signal adapter;
deterministic fixtures make CI repeatable. Vision evidence is explicitly false and deferred to
V2-05.

Every silence item is only a proposed edit decision. Padding is applied, overlap with any spoken
word disables the decision, and the source object is never altered. Highlights rank scene-level
speech semantics, hook keywords, information density and motion/audio proxies with an evidence
breakdown. No recommendation triggers render or publish.

## Persistence

Migration `0003_v2_04` creates upload sessions, analyses, transcripts, transcript segments/words,
scenes, silence decisions and highlights. An analysis fingerprint covers the source checksum,
configuration, provider keys and algorithm version, making replay idempotent. Provider usage is
recorded in VND and fixture operations cost `0 VND`.

## Intentional limits

- no auth/RBAC or public deployment;
- no live transcription adapter/credential;
- no Vision AI or smart reframe (V2-05);
- no subtitle/B-roll/audio processing (V2-06);
- no editable timeline/Studio analysis UI (V2-07);
- no source mutation, automatic approval, render or publish;
- malware scanning/quarantine is a production gate, not claimed in V2-04.
