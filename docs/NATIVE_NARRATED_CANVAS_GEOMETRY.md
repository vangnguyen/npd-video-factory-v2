# Narrated render geometry for four aspect ratios

Wave 7 extends the existing narrated renderer to 1080×1920 / 9:16, 1920×1080 / 16:9, 1080×1080 / 1:1 and 1080×1350 / 4:5. This increment is the canvas foundation; narrated variant-family creation/UI and verified cross-project prepared narration reuse remain separate work.

## Implementation

Frozen `VideoTemplate` validates exactly the four supported dimension/aspect pairs. `catalog(include_all_formats=True)` exposes 60 templates: the 15 existing portrait templates remain exact, with corresponding landscape/square/feed forms. Default catalog stays 15 and the historical `include_landscape=True` catalog stays 30. Existing public Studio choices are unchanged in this increment; the resolver can admit a new explicit compact template selection and existing canonical editing/approval rules apply.

`narrated_layout.py` preserves original portrait and landscape margins, media planes, title/label/subtitle sizes, caption regions, illustration labels and footers. Square and feed use bounded geometry with even media heights, scaled safe margins and separate illustration/footer/caption regions. Compact templates require an editable plan, so the old fixed portrait fallback cannot silently draw outside a new canvas. Subtitle font size is bounded by the selected brand size and compact layout ceiling. Hard render-profile validation remains exact; requesting `vertical-short` with square/feed dimensions is rejected.

The existing renderer consumes this layout for scene composition and FFmpeg planes. ASS PlayRes dimensions and effective subtitle size match the actual canvas. Transport QC records the correct square/feed check name, alongside codec/frame rate/audio/decode/A/V duration checks. The same Full QC and actual libass alpha-mask bounds validate the result. Original image/audio bytes, narration rate, timeline source of truth, human approval and historical verified checkpoints are preserved.

## Evidence and limits

Four new Native cases cover opt-in catalog preservation, invalid dimension pairs, refusing an unreviewed compact fallback, preserving old geometry, contained new regions, and actual square/feed MP4/ASS/Full QC with original PCM hashes and Vietnamese subtitle masks. The first new test run passed 4 cases; 18 existing branding/storyboard QC cases also passed. Exact final full regression counts and source hashes are recorded in `docs/north-star/native-narrated-canvas-evidence.json`.

`recovery/20261007/native-narrated-canvas-flow-n2` retains all four actual rendered MP4s, canonical input/timeline, manifests, FFprobe/transport/full QC, measured audio, ASS output, eight libass masks and four decoded review frames. Four frames were inspected: title, illustration disclaimer, footer and Vietnamese caption are readable and separated. It uses explicitly synthetic images, tone PCM and approval fixtures; one fixture PCM hash is preserved in every render. There are zero provider inferences/external calls/paid operations. This proves local render geometry, not genuine voice/speech/rights/source tracking, cross-project PCM reuse, browser/family UI or Owner UAT. Earlier n1 render exports are retained; n2 adds decoded frame evidence without replacing them.

The next dependency is a scoped narration derivation that verifies the source project/job/approval/plan/checkpoints and physical PCM, binds unchanged voice inputs to each child, clears child approval and legal/provider authorities, and requires a fresh audible preview and render approval for each variant. Source Mode B already has its own variant-family implementation and remains unchanged. `MULTI_NICHE_READY`, full Mode A/B and North Star acceptance are still NO.
