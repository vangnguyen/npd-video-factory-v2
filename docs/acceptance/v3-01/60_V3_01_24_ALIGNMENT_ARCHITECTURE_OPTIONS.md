# V3-01-24 — Alignment Architecture Options

**DESIGN ONLY / PROPOSED, NOT APPROVED. Production: NO-GO.**

Reference date: **2026-09-08**. Base: `5a8c96da6816ad6f424eaaa3952947738d4c49d5`.
This document creates no model selection, implementation, download, runtime authority,
operation, window or RC. Provider calls, credential reads and spend in this work: **0 / 0 / 0 VND**.
No local model inference, model-weight download, audio upload or acoustic listening was performed.

## Decision to prepare, not execute

Separate **what was transcribed**, **where the audio supports it**, and **whether an edit
consumer may use the resulting interval**. The [overall strategy](58_V3_01_24_ASR_QUALITY_STRATEGY.md)
recommends W1, a bounded Whisper vocabulary prompt, as the next proposal within option A.
Only if a separate alignment architecture becomes necessary, prefer investigating option B
over dual-pass C, subject to a commercially usable Vietnamese aligner, acoustic validation
and a new provider/rights/budget decision. Keep unprompted A as the retained baseline; defer C unless
the extra independent comparison justifies its cost and disagreement handling. This is an
engineering recommendation, not proof that B will achieve 8/8 or permission to implement it.

The [retained RC-15 analysis](57_V3_01_23_ASR_CRITICAL_TERM_EVALUATOR.md) establishes
5/8 critical terms and 27 boundary-point words in 412 word objects for Operation 1.
Changing timing does not repair those text substitutions. Historical receipts, reference
transcripts and acceptance verdicts remain immutable; ASR stays **0/2 consecutive PASS**,
Vision **2/2 PASS**, and RC-15 Operation 2 **LOCKED**.

## Three options

| Dimension | A — Whisper ASR + native provider timings | B — Higher-accuracy GPT transcript + separate LOCAL alignment | C — Dual pass + strict cross-consistency |
| --- | --- | --- | --- |
| Proposed flow | Audio → `whisper-1` text/word/segment receipt → existing validators | Audio → one owner-selected GPT transcription model → immutable text; same audio + text → local aligner → separate derived timing artifact | Same audio → GPT text and independently approved timestamp-provider transcript; compare both before any timing association, optionally followed by separately approved local alignment |
| Text accuracy / 8-of-8 potential | NPD retained result is 5/8, not 8/8. Another run is neither authorized nor an accuracy remedy | Plausible improvement to investigate, **UNKNOWN on NPD assets**. Alignment cannot improve lexical recall; GPT must independently satisfy the unchanged critical-term test | Can detect disagreement, not vote it away. Requiring agreement may retain the weaker pass's blocker; 8/8 is not guaranteed |
| Timing integrity | Native response lineage is simplest; boundary points remain evidence, not positive-duration cues | Derived estimates require complete token-to-audio mapping and independent boundary QA; no claim of native GPT word timestamps | Timestamp words must match the text they actually accompany. Never attach Whisper timing for “xác” to GPT “sách”, or transfer by word index after token splits |
| Provenance | One provider request/response pair, raw word timestamps, nullable confidence, usage/cost receipt | Two separate records: raw provider transcript and local alignment with exact model/config/audio/transcript hashes | Separate IDs, hashes, text, timings and cost receipts for each pass plus an explicit disagreement/mapping report; no merged synthetic provider receipt |
| Complexity / production risk | Lowest integration complexity, known unresolved text and downstream timing gates | New model lifecycle, tokenizer/lexicon, resampling, sandbox, CPU/GPU capacity and derived-consumer contract | Highest orchestration risk: two paid boundaries, partial failure, reservations, duplicate control and cross-pass disagreement |
| Latency / determinism | Retained RC-15 latency is about 12.17 s; not an SLA or guaranteed repeatability | Provider latency + local alignment; both **unbenchmarked**. Pin weights, tokenizer, versions, device and precision; do not claim bitwise determinism before tests | Two provider latencies plus comparison/alignment, normally serial under a newly reviewed envelope; cannot reuse one 90/120 s deadline for the whole design |
| Flow A | Existing `PositiveDurationTranscript` still blocks any boundary-point word | Needs a new explicitly reviewed **derived** positive-duration representation; current no-rewrite wrapper cannot certify it as raw provider timing | Same derived/native distinction, plus complete cross-consistency. Any disputed word prevents downstream projection |

“Higher-accuracy” is the provider's model positioning, not measured NPD performance.
OpenAI describes `gpt-transcribe` as a high-accuracy transcription model with context,
keyword and language hints; that does not establish native word-timestamp compatibility
or an 8/8 result here. Model selection and hint content remain owner-gated, and the full
reference transcript must not be injected to manufacture acceptance. [Official model page](https://developers.openai.com/api/docs/models/gpt-transcribe).

### Cost comparison — planning arithmetic only

The consulted official prices are `whisper-1` **USD 0.006/minute** and `gpt-transcribe`
**USD 0.0045/minute**. [Whisper pricing](https://developers.openai.com/api/docs/models/whisper-1),
[GPT-Transcribe pricing](https://developers.openai.com/api/docs/models/gpt-transcribe).

Using the prior fixed accounting assumption **27,000 VND/USD**, not a newly verified FX
quote or approval: A models **162 VND/minute**, B's GPT-only component **121.5 VND/minute**,
and C with both providers **283.5 VND/minute**. At the existing 180-second asset cap these
are **486**, **364.5**, and **850.5 VND**, respectively, before local compute/operational cost.
Thus C exceeds the old 500 VND per-operation envelope at that cap and introduces two
provider requests; it cannot be hidden inside the old one-attempt authority. B's lower
API estimate does not authorize a new model or make local compute free. Actual end-to-end
latency, hardware cost and revised reservations remain **UNKNOWN / NEW G-02 REQUIRED**.
No old reservation, window or operation ID is reusable by any option.

## Local alignment candidates: capability is not deployment approval

### B1 — Montreal Forced Aligner (MFA)

The upstream registry explicitly lists a **Vietnamese MFA acoustic model v3.0.0**,
GMM-HMM with MFCC + pitch, for Vietnamese forced alignment. Its model license is
**CC BY 4.0**. The paired **Vietnamese MFA dictionary v3.0.0** is also explicitly
Vietnamese and **CC BY 4.0**. This verifies published Vietnamese artifacts, not NPD quality
or deployment rights clearance. [Acoustic model card](https://mfa-models.readthedocs.io/en/latest/acoustic/Vietnamese/Vietnamese%20MFA%20acoustic%20model%20v3_0_0.html),
[maintainer dictionary card](https://raw.githubusercontent.com/MontrealCorpusTools/mfa-models/main/dictionary/vietnamese/mfa/v3.0.0/README.md).

The toolkit uses an MIT license; that does **not** replace the separate acoustic-model,
dictionary, training-data and dependency review. Attribution and any other applicable
conditions must be recorded in a future model manifest. [Toolkit license](https://raw.githubusercontent.com/MontrealCorpusTools/Montreal-Forced-Aligner/main/LICENSE).

MFA aligns supplied audio/transcription using an acoustic model and pronunciation
dictionary. Its current docs describe evolving model/command formats and optional
tokenization, G2P and TextGrid cleanup; therefore pin an exact compatible engine/model
pair, not a floating “latest” setup. [Maintainer alignment workflow](https://montreal-forced-aligner.readthedocs.io/en/latest/user_guide/workflows/alignment.html).

**Proposed operating approach:** CPU-first feasibility investigation; no GPU is assumed
available or required for this particular proposed GMM-HMM path, and measured CPU/RAM/
disk/latency requirements are unknown. NPD project names, English code-switches and tones
need an explicit OOV/pronunciation coverage report. Never convert unknown words to silence,
ignore a file, remove phones, or guess project-name pronunciation to obtain PASS. Any
lexicon addition is a versioned derived artifact with independent review, not an edit to
the reference transcript. The model card's language label does not prove these names work.

### B2 — WhisperX alignment-only investigation

Upstream `alignment.py` explicitly maps `vi` to
`nguyenvulebinh/wav2vec2-base-vi-vlsp2020`. The model author's card identifies Vietnamese
16 kHz speech and **CC BY-NC 4.0 / non-commercial model parameters**. WhisperX's own code
is **BSD-2-Clause**. Do not infer commercial model permission from the code license:
this default is **BLOCKED for proposed NPD commercial use pending separate rights clearance
or a different cleared model**. No model was downloaded or selected. [Language mapping](https://raw.githubusercontent.com/m-bain/whisperX/main/whisperx/alignment.py),
[model-author card and parameter license](https://huggingface.co/nguyenvulebinh/wav2vec2-base-vi-vlsp2020),
[toolkit license](https://raw.githubusercontent.com/m-bain/whisperX/main/LICENSE).

The inspected alignment source includes nearest interpolation for missing timing,
wildcard handling and an automatic NLTK-data download path. These are **not accepted
NPD defaults**: a future pinned wrapper must expose/disable unsupported imputation,
reject unaligned words, prevent implicit network access and preserve every original
token. A generic WhisperX result cannot be relabeled a fully evidenced positive interval.
Source inspection is not execution or proof that one configuration removes every risk.
[Inspected alignment implementation](https://raw.githubusercontent.com/m-bain/whisperX/main/whisperx/alignment.py).

WhisperX documents CPU operation as well as GPU acceleration; its advertised full-pipeline
speed/GPU figures are not measurements for NPD's alignment-only workload. Hardware,
precision and language-specific accuracy must be benchmarked after separate approval.
Diarization is excluded: do not add its token, model agreement or pipeline implicitly.
[Maintainer README](https://raw.githubusercontent.com/m-bain/whisperX/main/README.md).

### Why forced alignment cannot validate a hallucinated word

Forced alignment fits a **supplied transcript** to audio; obtaining an interval does not
independently prove that the supplied word was spoken. The WhisperX research describes
VAD plus forced phoneme alignment, and MFA separately documents comparison with gold
alignments. Neither source proves NPD's critical terms. [WhisperX primary paper](https://arxiv.org/abs/2303.00747),
[MFA gold-alignment evaluation](https://montreal-forced-aligner.readthedocs.io/en/latest/user_guide/implementations/alignment_evaluation.html).

**Required policy, not a claimed observation:** blind transcript scoring against the
owner-confirmed reference and independent acoustic spot/full review must remain separate
from alignment. Silence, wrong transcript, missing critical word and hallucinated-term
negative controls must be rejected even if the aligner returns high scores or positive
durations. Confidence from an aligner is not ASR confidence, calibrated certainty or G-11
human acceptance. Keep absent confidence null.

## Proposed derived representation and consumer boundary

The current [provider types and no-rewrite wrapper](../../../apps/api/app/auto_edit_providers.py)
must remain unchanged in this strategy PR. `PositiveDurationTranscript` proves existing
provider words have positive intervals and carries
`provider_timestamps_validated_without_rewrite`; it cannot truthfully certify local
alignment as unchanged provider timing. Boundary points still raise
`POSITIVE_DURATION_TRANSCRIPT_REQUIRED` for subtitle/reframe/scene/silence/edit consumers.

A later separately reviewed design would introduce an **AlignedTranscriptArtifact**
(conceptual, not implemented), then an explicit consumer adapter. It must retain:

- Raw provider response/text/timestamps/receipt hashes, provider operation ID and immutable
  token indexes; the original provider object is never mutated.
- Source audio SHA, bytes, sample rate, channel count, duration and consent/RightsRecord
  binding; any resampled waveform has its own SHA and exact sample-time mapping.
- Exact alignment engine revision, model-weight hash, tokenizer/lexicon/G2P hashes,
  separate code/model licenses, configuration, device/precision and environment digest.
- Separate raw provider and derived start/end fields, per-token source indexes, segment
  anchors, alignment status/score, derivation reason and all rejected/unmapped tokens.
- Full token coverage and order, segment/source bounds, no unexplained overlap, finite
  nonnegative timestamps and strictly positive durations for downstream intervals.
- Independent acoustic-boundary review plus text/WER/critical-term results; 8/8 is unchanged.
  The derived artifact's own checksum and approval are distinct from provider acceptance.

**Forbidden:** epsilon, endpoint swap, clamping, silent interpolation, dropping or merging
words to hide an error, overwriting raw timestamps, moving boundaries without provenance,
or borrowing another transcript's intervals merely because counts are similar. Algorithmic
alignment estimates may be reviewed as derived evidence; they are not repairs to the old
receipt. Missing/zero/inverted/unsupported alignment remains `REVIEW_REQUIRED` and blocks
Flow A. No existing native-timestamp acceptance row is silently redefined as derived PASS.

## Gate checklist before any future implementation or run

1. Owner chooses **one** architecture/model plan, not all three. Evidence-only strategy
   approval does not authorize local inference, weight acquisition or paid calls.
2. Record the exact Vietnamese model/dictionary/license provenance, OOV policy and a
   dependency/security/resource review. Unknown licensing or missing assets is a blocker.
3. Review a source-only contract/mock implementation: separate raw/derived types, strict
   8/8 matching, no reference leakage, timing/coverage rejection, downstream parity,
   deterministic serialization and no implicit download/network behavior.
4. Approve separate rights for each use and processing location; prior OpenAI acceptance
   consent is not blanket authorization for training, publishing, resale or another service.
5. Only after G-08, regression and the required fresh executable RC may new G-01/G-02/G-03,
   budget/timeout/model/asset bindings and a separate operation authority be proposed.
6. A future bounded evaluation must report lexical accuracy, alignment completeness,
   human boundary errors, time/cost and downstream readiness separately. No automatic
   second provider pass, retry, fallback or Operation 2 on failure.

This checkpoint stops at **strategy review / OWNER G-08**. No alignment implementation,
new credential mechanism, runtime authority, live operation, deploy, publish or public
ingress is created. Production remains **NO-GO**.
