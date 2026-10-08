# Native music crossfades and measured loudness

Master Spec section 38 and Waves 5B/6C/6D/6E remain the acceptance authority. This increment closes three technical gaps without claiming complete audio, legal, speech or Owner acceptance.

## Canonical Source music loops

Source music intake accepts optional `X-VF-Music-Loop-Crossfade`, zero by default. Studio exposes it only for Source projects when the server advertises `native_source_music_loop_crossfade`. Values are finite, 0–1 seconds, at most three decimal places, and cannot exceed half the measured music duration. Unsupported narrated projects reject a nonzero request before intake. Existing upload size/type/rights/revision/role guards remain.

Repeated music clips overlap by the requested interval. Existing canonical transition-in/out values produce linear fades in the shared audio graph. The same canonical timeline feeds Source preview and final rendering; Advanced Timeline can edit these clips and history can restore the prior version. No second edit model or source modification is introduced. Music replacement clears approval. Locked tracks and the 128 audio clip limit remain enforced. Zero preserves the existing repeat timings, transitions and behavior.

The retained synthetic rehearsal includes linked Source trim/split, Vietnamese karaoke subtitles, portrait output, original/music normalization, energy-based ducking, crossfades and limiter. Full-effects preview and final share the exact canonical PCM hash. Synthetic tone and saved ASR are labelled fixtures, not speech recognition or voice/music balance acceptance.

## Actual final-output measurements

Fresh Source final QC and narrated storyboard full QC perform a bounded local FFmpeg loudnorm input scan. The receipt stores integrated LUFS, true peak dBFS, loudness range LU and relative threshold LUFS, with the exact measured input SHA256. Silence produces null unmeasurable values; invalid/nonfinite/out-of-range results, tool failure, timeout, excessive diagnostic output and changed physical input fail closed. Scan errors produce `failed_qc`; no ready final checkpoint is registered.

The scan discards its filtered output and does not change the input. Its `input_*` values measure the delivered file; normalization targets are not reported as achieved values. Speech detection, voice/music balance and human acceptance remain false. Source `audio-analysis.json` includes `final_output_loudness`; narrated full-QC evidence includes `measured_audio_loudness`. Existing clipping/silence/decode/A-V/resolution/subtitle/asset checks remain. Historical verified checkpoints replay their original evidence without new scans or inference. Legacy transport-only output does not acquire a retrospective full-QC claim.

The actual Source rehearsal measured −15.73 LUFS / −12.66 dBFS true peak. A separate genuine installed VieNeu scene-narration rehearsal passed current audible preview, final full QC, frozen-preview rejection, backup/restore and new-process checkpoint replay. These measurements do not accept pronunciation or listening quality; Owner deferred the optional listening review and instructed implementation to continue.

## Music provenance review

Music ingest registers decoded audio as `<32 lowercase hexadecimal characters>.music.wav`. Rights models, HTTP routes, RBAC route matching and Studio review forms now accept that exact existing suffix. No arbitrary extension/path is admitted. The physical PCM and original file hashes remain bound to review.

Upload attestation and a rights declaration do not independently verify a license. A declaration keeps effective rights unknown or restricted. An explicit Owner exception remains default-disabled, separately scoped to workspace/project/asset/physical hash/rights digest, expiring and revocable; publishing approval and all other validation gates remain separate. Copies drop declaration and exception authority. A restricted declaration cannot be elevated by the exception mechanism. Role/CSRF guards execute before unauthorized bodies are read.

The retained signed HTTP music review rehearsal records declaration/grant exact retries, revoke after disabling the exception setting, copied-project isolation, unchanged canonical timeline/physical bytes, both-database backup/restore and historical render checkpoint replay. All legal decisions are explicit synthetic identity fixtures; no real publication or Owner legal clearance occurred.

## Evidence and remaining work

Machine index: `docs/north-star/native-audio-quality-evidence.json`. External recovery contains `native-music-crossfade-flow-n1`, `native-music-review-flow-n1` and `native-audio-quality-narration-n1`; none replaces accepted videos.

Remaining audio scope includes narrated-mode loop crossfades, independent stem-level perceptual balance/speech audibility acceptance, expanded provider-neutral voices/languages, measured BPM/mood/energy for uploaded music, and actual rights/browser/non-developer/Owner acceptance. Final output loudness is a measurement, not a complete audio-quality certificate. Original Mode A/B, publishing/analytics/learning, integration, production and final acceptance requirements remain active.

Subsequent narrated-mode implementation is documented in [Native narrated music loops](NATIVE_NARRATED_MUSIC_LOOPS.md). The statements above describe this earlier preserved increment; its evidence and artifacts remain unchanged.
