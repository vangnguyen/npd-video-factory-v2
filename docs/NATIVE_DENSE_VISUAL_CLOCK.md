# Native dense motion and scene clocks

This Wave 3C/3E/4/8/15 component gives new motion and scene measurements actual normalized decoder timestamps. Audio/ASR clocks, semantic understanding, continuous tracking, full Mode A/B, original A/B/C and Owner/production acceptance remain separate.

Motion sampling no longer creates an FPS grid and labels it source time. A bounded single decode selects actual source frames at requested threshold crossings, preserving integer PTS/time base through `copyts/start_at_zero` and passthrough output. VFR sources can produce fewer, nonuniform samples. Pixel differences remain a motion proxy; they do not become optical flow, object tracking or calibrated quality. The result identifies requested sampling density separately from actual clocks.

Stdout pixels and stderr clock records drain concurrently under timeout/count/byte limits. Only showinfo clock/config rows are retained; source filenames and arbitrary SEI payloads are excluded. Frame count/dimensions and rational timestamps are validated before measurements are returned. [FFmpeg timestamp options](https://ffmpeg.org/ffmpeg.html#Advanced-options) and [showinfo](https://ffmpeg.org/ffmpeg-filters.html#showinfo) document the underlying clock behavior.

Shot-boundary detection now preserves normalized source PTS and pairs each measured scene score with its own decoder clock. It retains bounded decoded stamps and sanitized clock lines. No-scene input remains valid. Speech/silence/waveform methods are unchanged and are not certified by this video-clock increment.

The signal recipe is `scene-silence-waveform-visual-v4`. New Native analyses record this recipe in provenance and their fingerprints. Historical v3 fingerprints are verified against their former recipe, without rewriting evidence, hiding existing timelines or automatically remeasuring. The PostgreSQL analysis fingerprint already includes its signal algorithm and therefore separates new cache entries from previous results.

Evidence is indexed in [dense-visual-clock-evidence.json](north-star/dense-visual-clock-evidence.json). Native real-media tests cover VFR timing, an offset-four-second black/white shot boundary at normalized second 1, sanitized logs, v3 compatibility, source preservation and downstream analysis/preview/tracking/ASR regression paths. Linux tests separate the missing-FFmpeg media skip from executed cases. Retained rehearsals export two generated sources, normalized analysis, motion records, independent FFprobe comparisons, project state and a backup restored in a separate process. They do not call ASR, semantic Vision or paid providers, create human approval or mutate the canonical timeline. Owned temporary rehearsal/restore roots are cleaned after export.

Dense source audio timing, original ASR-to-source clock mapping, genuine source/provider/semantic acceptance, complete browser/non-developer/Owner Mode A/B and production remain open. Original accepted artifacts are preserved separately; no main merge, real publishing or deployment occurs.

Run `python scripts/north_star_native_dense_visual.py --output <fresh-external-folder>` in the existing Native runtime.
