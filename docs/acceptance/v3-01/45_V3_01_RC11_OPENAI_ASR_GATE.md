# RC-11 OpenAI ASR acceptance gate

## Checkpoint

```text
DATE: 2026-09-03
EXECUTABLE RC: vf-v3-01-rc11 -> 207ff9fee5557eb0976f575c9263b61d995b20a0
PROVIDER / MODEL / CAPABILITY: openai-transcription / whisper-1 / asr
LANGUAGE: vi
G-01-ASR: APPROVED AND REBOUND IN THIS GOVERNANCE PROPOSAL
G-02-ASR v1.1: APPROVED AND REBOUND IN THIS GOVERNANCE PROPOSAL
G-03-ASR: APPROVED AND REBOUND IN THIS GOVERNANCE PROPOSAL
OPERATION 1 AUTHORITY: NOT APPROVED
OPERATION 2 AUTHORITY: NOT APPROVED / LOCKED
BUNDLE: CHECKED IN BUT UNMOUNTED
PROVIDER CALLS IN THIS CHANGE: 0
CREDENTIAL READS IN THIS CHANGE: 0
COST IN THIS CHANGE: 0 VND
PRODUCTION: NO-GO
```

This checkpoint records the exact two-input RC-11 ASR acceptance scope after V3-01-18 merged. It
does not execute that scope. The checked-in application defaults remain fixture-only, external and
paid execution remain disabled, the runtime budget remains zero and the global kill switch remains
engaged. A later operation requires a separate owner decision after this governance PR merges and
dual-CI/exact-RC preflight succeeds.

## Source and CI provenance

| Item | Exact evidence |
|---|---|
| PR #41 source head | `8ebb1cffe8563e49ccf4847ef37209d9644a4e70` |
| PR #41 base | `4c74fa18a86b29ae8324885dacc6fdbca74ad066` |
| Exact-head CI | `33711738092`, completed/success |
| Merge / exact RC-11 | `207ff9fee5557eb0976f575c9263b61d995b20a0` |
| Exact-main CI | `33712762815`, completed/success |
| Annotated tag | `vf-v3-01-rc11` peels to the exact merge commit |
| PR #41 G-08 record | [`V3-01-APP-043`](approvals/V3-01-APP-043.json) |

PR #41 supplied the executable ASR adapter and gate contract. This PR changes only allowlisted
governance, test and evidence paths, so it must not create RC-12 if the executable-tree hash remains
identical to RC-11.

## Compatibility and model decision

RC-11 compatibility evidence compared `whisper-1`, `gpt-transcribe` and `gpt-4o-transcribe`
offline. The owner approved `whisper-1` only for this first acceptance because it satisfies the
strict Flow A contract for native transcript text plus segment and word timestamps. This is not a
claim that it is the best general ASR model and grants no fallback to either GPT transcription
model.

Official materials were refreshed on 2026-09-03:

- [Whisper model](https://developers.openai.com/api/docs/models/whisper-1)
- [Speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text)

The approved accounting rate remains `0.006 USD/minute` converted at the owner-fixed acceptance FX
of `27,000 VND/USD`, yielding `162 VND/minute`. Provider availability and price must be rechecked at
execution preflight; a mismatch fails closed and does not authorize a silent budget or model change.

## G-02-ASR v1.1 envelope

| Control | Bound value |
|---|---:|
| Target duration | 90-120 seconds per operation |
| Minimum acceptance duration | 90 seconds |
| Hard duration cap | 180 seconds |
| Hard file cap | 25,000,000 bytes |
| Response format | `verbose_json` |
| Timestamp granularities | `segment`, `word` |
| Provider HTTP timeout | 90 seconds |
| Controller hard envelope | 120 seconds |
| Accounting rate | 162 VND/minute |
| Maximum modeled cost at 180 seconds | 486 VND |
| Atomic reservation | 500 VND per operation |
| Acceptance-window ceiling | 1,250 VND |
| Attempts / concurrency | 1 / 1 |
| Retry / fallback | 0 / 0 |

The two exact WAVs are slightly above the 120-second target but below the hard 180-second cap. The
owner explicitly accepted their exact measured durations. The target is an input-design preference;
the hard cap is the enforced safety boundary.

## Owner G-03-ASR decision

The owner confirms that NPD owns or is permitted to use both exact recordings and their voices for
this bounded OpenAI ASR acceptance. The speaker consents to that processing. The owner listened to
each exact WAV and confirmed its actual spoken content matches the corresponding checked-in
reference transcript. No publishing, training, resale or other use is authorized.

| Slot | WAV | SHA-256 | Bytes | Measured duration | Transcript SHA-256 | Modeled cost |
|---:|---|---|---:|---:|---|---:|
| 1 | [`g03-asr-vi-owned-01.wav`](assets/g03-asr-vi-owned-01.wav) | `fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef` | 5,800,940 | 120.852 s | `585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e` | 326.300400 VND |
| 2 | [`g03-asr-vi-owned-02.wav`](assets/g03-asr-vi-owned-02.wav) | `dce36c5246c17e0385842006dcb0088a8c97a79d3009796815c2564c075cf20b` | 6,460,396 | 134.590667 s; owner-accepted rounded value 134.591 s | `0bff8c2b403cee452fac00f71b84759988ea515027fda6bd49be76ae382c1fef` | 363.394800 VND |

The combined modeled cost is `689.695200 VND`, below the `1,250 VND` acceptance-window ceiling.
Modeled cost is not actual cost and creates no reservation. The complete technical and critical-term
record is [`V3-01-RC11-ASR-ASSET-MANIFEST.json`](assets/V3-01-RC11-ASR-ASSET-MANIFEST.json).
RightsRecords are:

- [`V3-01-RIGHTS-ASR-001`](rights/V3-01-RIGHTS-ASR-001.json), canonical SHA-256
  `5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091`;
- [`V3-01-RIGHTS-ASR-002`](rights/V3-01-RIGHTS-ASR-002.json), canonical SHA-256
  `972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323`.

## Hash-pinned gate

| Binding | Exact value |
|---|---|
| Gate bundle | [`V3-01-GATE-RC11-OPENAI-ASR-A.json`](V3-01-GATE-RC11-OPENAI-ASR-A.json) |
| Raw bundle SHA-256 | `4f8edd02ec62182404976de16e8d75b39ddbbbbe96c0d78efd46e3a97d6ace46` |
| Execution-scope SHA-256 | `7368b506b8971b190a1828ecab588dfe6b46a7e354d00c4d7cf2f35c1cc2c39a` |
| Provider-scope SHA-256 | `4d88c5c59c9b5ca9e8c126f0798356eb6ef82a8db2fe16045434af1d69048349` |
| Budget SHA-256 | `778af29ad50dc2f7018c86604dba72a6ad4d212af6a92b409b9c4dcaf9a9934f` |
| G-01 record | [`V3-01-APP-044`](approvals/V3-01-APP-044.json), canonical SHA-256 `d4c5ad7b9fb33ee6eba107bc85b0c9b22db0a1c7fa859dfdabd59ef3cb80cd4f` |
| G-02 record | [`V3-01-APP-045`](approvals/V3-01-APP-045.json), canonical SHA-256 `a82024fb4433ed56bd8da49ec1aaefd7515b1e796664b3e1eb7fe61cfd8199ed` |
| G-03 record | [`V3-01-APP-046`](approvals/V3-01-APP-046.json), canonical SHA-256 `7e604d838dd0b0f0f55d379b69c02856ddbd7f21e109d7601ab0aadd1bd79f34` |

The proposed gate window is `2026-09-04T14:00:00Z` through `2026-09-04T18:00:00Z`, equivalent to
21:00 on 4 September through 01:00 on 5 September 2026 in Asia/Ho_Chi_Minh. This proposal alone does
not activate the window. If G-08 review, governance-main CI and operation authority are not complete
before expiry, the bundle must be rebound; the window must not be extended silently.

The two derived operations are:

1. `v3-01-rc11-openai-transcription-asr-call-01`, bound to asset slot 1;
2. `v3-01-rc11-openai-transcription-asr-call-02`, bound to asset slot 2.

Both are currently `NOT APPROVED`. Operation 2 stays locked even if Operation 1 later receives a
separate authority.

## Required preflight and evidence

Before any call, a later runner must fail closed unless it proves exact RC/tag, dual-CI provenance,
unchanged executable tree, raw bundle and scope hashes, approval and RightsRecord hashes, WAV and
transcript hashes, file size/duration, language/format/timestamp contract, unconsumed operation,
no duplicate ledger row, atomic VND reservation, concurrency one and an active UTC window. The
credential may be resolved only from its approved alias after all non-secret checks pass.

After one authorized attempt, evidence must preserve provider execution separately from acceptance:
provider/request ID when supplied, transcript and native timing payload, request/response hashes,
duration/usage, actual VND cost, latency/timeout phase, RightsRecord binding, durable ledger,
circuit state, duplicate protection, evidence SHA and secret scan. A missing field is not inferred.
There is no automatic retry, fallback or Operation 2 activation.

## Acceptance effect and next owner gate

This governance record does not change `ASR-01` real-provider, production-path or human-quality
status: all remain `NOT_TESTED`. It advances only gate readiness. After G-08 merge, exact-main CI
must pass, the executable tree must remain RC-11-identical, the bundle must remain unmounted and
zero credential reads/reservations/calls must be verified. The next owner decision is a separate
authority for `v3-01-rc11-openai-transcription-asr-call-01`.

Production remains `NO-GO`.
