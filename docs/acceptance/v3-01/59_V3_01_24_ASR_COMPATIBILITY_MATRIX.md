# V3-01-24 — ASR compatibility matrix

Reference date: 2026-09-08. Official capability inspection plus existing contract/evidence;
**not three live model tests**. All new candidates are PROPOSED / NOT APPROVED.
See [decision and gates](58_V3_01_24_ASR_QUALITY_STRATEGY.md) and
[alignment options](60_V3_01_24_ALIGNMENT_ARCHITECTURE_OPTIONS.md).

## Source-backed capabilities versus untested claims

| Axis | whisper-1 | gpt-transcribe | gpt-4o-transcribe |
| --- | --- | --- | --- |
| Vietnamese/NPD quality | RC-15 WER9.6618%, terms5/8; W1/W2 UNKNOWN | Provider positions it for high-accuracy general transcription; NPD/Vietnamese8/8 UNKNOWN | Provider claims improved recognition over original Whisper; NPD8/8 UNKNOWN |
| Native word timing | Documented; retained RC-15 words/points observed | NOT PROVEN for strict contract | NOT PROVEN for strict contract |
| Native segment timing | Documented; retained RC-15 segments observed | NOT PROVEN for strict contract | NOT PROVEN for strict contract |
| Format/schema | verbose_json supports text, language, duration, segments/words | Guide JSON example is text + languages[]; languages may be empty | Reference restricts this model to json, not verbose_json |
| Usage/cost receipt | Retained RC-15 cost/usage exists; future receipt still required | Optional usage mapping/rounding must be separately verified, example text/languages insufficient | Token/duration usage union must be mapped; no invented missing usage |
| Request ID | Header metadata when returned; existing adapter retains it | Capture header independently; no claim example JSON contains it | Same; client ID is not returned provider ID |
| Latency | RC-15 ~12.17s on asset01; no candidate guarantee | NPD timing UNKNOWN | NPD timing UNKNOWN |
| Published pricing | 0.006 USD/minute | 0.0045 USD/minute | Estimated0.006 USD/minute; 2.50 input/10 output USD per1M tokens |
| Context | prompt; singular language=vi | prompt, keywords, plural languages; do not send singular language too | prompt; language hint |
| Determinism | No exact repeatability guarantee; temperature0 may trigger internal decoding adjustments | No inspected deterministic-output guarantee | No inspected deterministic-output guarantee |
| ProviderTranscript | Current adapter observed structured PASS at RC-15; nullable confidence kept | Not drop-in: language shape, timing and receipt adapter needed | Not drop-in: missing strict timing and receipt mapping |
| Strict Flow A | Provider evidence compatible, **interval downstream still positive-duration gated** | STRICT_FLOW_A_INCOMPATIBLE without separately reviewed alignment | STRICT_FLOW_A_INCOMPATIBLE without separately reviewed alignment |
| Migration complexity | Low-to-medium for canonical prompt profile; no runtime wiring now | High: model/request/receipt + alignment/provenance | High: model/format/accounting + alignment |
| Acceptance risk | Prompt bias, term errors, boundary points; no presumed PASS | Unknown actual quality, derived timing, model/account availability unverified | Unknown actual quality, native timing gap and token envelope |

Capability sources: [file transcription guide](https://developers.openai.com/api/docs/guides/speech-to-text),
[create transcription reference](https://developers.openai.com/api/reference/python/resources/audio/subresources/transcriptions/methods/create).
Model positioning: [GPT-Transcribe](https://developers.openai.com/api/docs/models/gpt-transcribe),
[GPT-4o-Transcribe](https://developers.openai.com/api/docs/models/gpt-4o-transcribe).
Pricing: [Whisper](https://developers.openai.com/api/docs/models/whisper-1),
[pricing table](https://developers.openai.com/api/docs/pricing).
Request provenance: [API overview](https://developers.openai.com/api/reference/overview).

## Conservative interpretation of documentation differences

The current file guide explicitly limits timestamp granularities to Whisper. The generic
endpoint parameter reference only explicitly excludes diarization and exposes broader
format enums/examples. A generic enum/example is **not proof of support by each model**.
The project therefore does not route GPT transcription outputs into strict Flow A.
This is a dated compatibility decision, not a claim that future provider support is impossible.
If documentation or an explicitly authorized bounded compatibility operation later supplies
the missing evidence, update the matrix in a new review; never discover it by three unapproved calls.

The recommended GPT-Transcribe fields also differ from the old adapter: `languages` replaces
`language`, while `keywords` are hints rather than required output. Keyword validation and
prompt limits need their own canonical request contract. The inspected documentation rejects
invalid keyword characters (`<`, `>`, CR/LF) and overly long context; no unverified exact
GPT prompt cap is invented here. None of these GPT-specific fields is wired.

A successful HTTP response does not guarantee complete accounting. Preserve media duration,
usage duration/token fields and ledger precision separately; optional/missing usage stays
unknown and fails acceptance when required. No proposed model inherits the Whisper duration
receipt adapter by assumption.

## What this review does not establish

No live Vietnamese benchmark, NPD8/8 success probability, latency SLA, guaranteed native
positive-duration words, account/model availability, paid-call permission or production
readiness has been verified for a new candidate. Source inspection is capability evidence;
mock fixtures are implementation evidence; neither substitutes for real-provider or human quality.

Vision remains2/2 PASS. ASR remains0/2 PASS. Production NO-GO.
