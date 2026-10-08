# Guided narrated project creation

New Studio storyboard projects use the versioned
`native-narrated-storyboard-workflow-v1` policy when the server advertises both
production quality and guided narration support. Approved-idea imports use the
same capability-gated creation preferences. Existing documents and older clients
keep their stored behavior. Creating or reading a project never dispatches TTS,
rendering or publishing.

## Saved editing and human review

The first saved or completed script persists a version-1 canonical timeline and
its derived projections in the same existing project transaction. The user does
not need to make an arbitrary shot edit before preparing narration. Subsequent
script, asset, brand and shot edits use the existing canonical synchronization.
Read endpoints do not write or initialize edits. Legacy project behavior and
Source Mode B's own audio/preview workflow remain applicable.

The guided storyboard sequence is:

1. Review the saved script and select each scene's media.
2. Explicitly approve the content for narration preparation.
3. Request narration, listen to it and review measured scene durations.
4. Explicitly apply measured timings to the canonical timeline; approval clears.
5. Generate and watch/listen to the current combined audible preview.
6. Approve production against that exact preview and render.
7. Watch/listen to and approve the final video separately before publication.

Production approval and new render execution reject a guided document without
its measured narration reference. Narration-only approval cannot render. Current
preview/document/timeline/audio binding and all physical QC/source checks remain
required. Version/hash drift rejects; no automatic inference fallback occurs.
Duplicated guided projects retain the review policy and require their own scoped
preparation and approval. An approved-brief retry cannot silently change the
project's initial creation policies.

Studio provides the current next step, distinct narration/production approval
copy and a final-render label for guided projects. The underlying preparation,
audio review, timing apply and preview controls remain explicit. The policy
does not select a new voice or grant paid-provider authority.

## Actual local TTS rehearsal

`scripts/north_star_native_storyboard_qc.py --narration-preparation --local-tts`
uses the installed locked VieNeu model and SDK in a fresh owned data root.
External credential paths must be absent. The reviewed `scene-context-v1`
policy uses the existing local inference child and outbound-network block;
the paid-ASR warm-context policy is not selected. Model downloads are disabled.
The script verifies locked model/SDK bytes before and after the flow.

The authored technology teaching script includes Vang Nguyễn, Vinhomes Green
Paradise Cần Giờ and Vinhomes Saigon Park. Actual generated PCM and model inference
counts are retained. Measured canonical apply, current-preview approval, full
effects, final original-PCM reuse, actual media/subtitle QC, frozen-preview
rejection and backup/restore are exercised. Exact new-process source/restored
checkpoint replay must perform no new inference.

Images and content are explicitly authored fixtures; the signed human approvals
are test identities. Real local model execution does not establish speech
intelligibility, pronunciation acceptance, word alignment, independent research,
semantic Vision, stock licensing, browser usability or Owner UAT. External
provider calls and paid operations are reported separately from local inference.
No accepted video, SDK/model file or live project is replaced.

See `north-star/native-guided-narration-evidence.json` and
`NORTH_STAR_WAVE_REPORTS.md` for exact final-source verification. Provider-neutral
language/style support and the original full Mode A/B, Trend, distribution,
analytics, learning, Agent Hub, production and A/B/C acceptance remain program
requirements; this increment does not declare North Star completion.
