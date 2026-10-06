# PHASE10 STUDIO UI CONSISTENCY AUDIT

Task: VF-PHASE10-STUDIO-UX-STANDARDIZATION-02. Final source: **84c0da23f970b82c94f589586aefa9e859e7cad6**. Status: **IMPLEMENTED /79 FRONTEND TESTS PASS /72 RESPONSIVE VIEW-STATE CELLS PASS WITH VISIBLE-SCOPE LIMITS /OWNER UAT PENDING**. Updated 2026-10-06 after the parent CAPTURE CAMPAIGN DONE marker.

This audit distinguishes source and runtime-fixture checks from browser pixel inspection and Owner acceptance. Earlier Phase10 screenshots certify an earlier interface. They do not certify this UX remediation. The new1366×768,1920×1080 and2560×1440 browser capture ledger is owned by the parent task; independent filesystem pixel inspection is recorded below. Original invalid/loading captures remain archived and excluded; coherent final evidence closes the selected visible scopes.

## Shared structure

The capable Native runtime uses one shell through [studio-shell.mjs](C:/NPD-Video-Factory/source/apps/studio-web/studio-shell.mjs) and one token sheet through [studio-shell.css](C:/NPD-Video-Factory/source/apps/studio-web/studio-shell.css). Secondary screens install the same shell only after the existing session response contains the explicit boolean capability native_studio_ux=true. Missing, false or string capabilities cause zero optional imports and zero shell stylesheet requests; the accepted old server keeps its original frontend layout.

The shell supplies stable CREATE, WORK, LIBRARY and SYSTEM groups with icons, labels, current-page state and a skip link. New Video uses /?new=1 to avoid restoring the last project. New research uses /intelligence?new=1; explicit run links remain authoritative. Existing Native #new-project, #project-picker, #runtime-status, #render and .studio-header-actions are reused as original nodes. Existing callback identity is covered by DOM fixtures. CI #ci-new is moved to the page actions as the original button. Runtime/provider information remains available in collapsed Diagnostics.

The persistent topbar contains the Studio name, page context and local storage context. Page-specific actions remain in the PageHeader. Every direct main child uses the same responsive page padding and a 1720px content cap. Cards, inputs, button heights, badges, focus states, empty/loading/error states and dialogs use shared tokens. Long CI and connection forms have an internal reading width while their outer cards and headers remain aligned.

Tokens cover 4/8/12/16/24/32/40px spacing, 6/10/14px radii, surface/background/border/text/muted/accent/status colors, 40px controls, 232px sidebar, page/card padding and inspector width. Narrow breakpoints collapse card grids and wrap action/filter bars. These are **source-level behaviors**, not an overflow measurement.

## Functional screen inventory

“Verified source” below means implemented classes, route/control wiring and relevant frontend checks. It does not mean a screenshot or human review passed.

| Screen / route | Shell and header | Controls and next action | Empty / loading / error behavior | Responsive behavior in source | Verification |
| --- | --- | --- | --- | --- | --- |
| Production overview · /production?view=dashboard | Shared shell, PageHeader, read-only overview | Project/review cards; New Video; links to queue and final videos | Useful first-project / no-review states; named loading state; refresh error message | 4 stats, 3 shortcuts, 2 project columns; reduced at narrow widths; bounded main | Verified source + actual module boot fixture |
| Projects · /production?view=projects | Shared shell and PageHeader | Search, exact/grouped status, archived opt-in; open project; New Video | No-match state with create action; project loading; refresh retry | Project grid 2 columns → 1; safe title wrapping | Verified source + actual module boot fixture |
| Production queue · /production?view=queue | Same shared shell/header/cards | Search/profile/stage; review/ready/producing/video/approved/error chips; human gated batch controls; planning/open-project actions | Filter empty state points to research; named loading; errors point to refresh; pending batch recovery retained | Queue columns reduce; filter/actions wrap; internal dialog scroll | Verified source + actual module boot fixture and existing batch binding checks |
| Planning dialog · queue/calendar/dashboard | Shared dialog tokens and form vocabulary | Existing date/campaign/priority/assignment/reviewer/source/similarity controls retained | Existing dirty-close confirmation, version checks and human decisions retained | Bounded 760px/viewport height; form grid and internal scroll | Verified source; actual modal scope listed below |
| Content calendar · /production?view=calendar | Shared shell and PageHeader | Month; date/campaign/project/brand/profile/format/priority grouping; existing planning action | Empty month links to queue; undated work remains visible; named loading and refresh | Reuses responsive queue cards | Verified source + deterministic calendar test |
| Content Intelligence · /intelligence | Shared shell, PageHeader, cards, filters/status badges | Existing research → ideas → brief → Studio controls, reviewer and acknowledgment; New Research; refresh | Useful empty queue; named loading; plain retry message; existing explicit operation progress | Main/card cap; form reading width; shared controls and wrap | Verified source + real module legacy/current approval fixtures |
| CI findings / ideas / brief | Same shared cards/header; workflow steps retained | Source links, idea selection/edit/reject, brief edit/approve/send; preflight only when supported | Panels hidden until relevant data exists; localized idea/status labels; technical weights/raw source in details | Shared card spacing, form reading width and controls | Verified source; actual selected-run pixel scope listed below |
| Final videos · /production?view=library | Shared shell/PageHeader/video cards | Approved-only filter; search title/profile/project/campaign; guarded View Video/Open File; Open Project; lineage details | No-video state points to projects; named loading; refresh retry; unapproved cards cannot expose approved-file playback | 3 → 2 → 1 cards, contained thumbnails, wrap actions | Verified source + actual module boot and approved local URL/metadata tests |
| Content profiles · /production?view=profiles | Shared shell/PageHeader/cards | Existing 5 profiles and research links; priority configuration retained | Catalog fetch uses shared error/refresh flow | 2 → 1 profile cards; shared padding | Verified source |
| Connection settings · /settings/assemblyai | Shared shell/PageHeader and connection card | Existing credential submit/verify actions; added read-only refresh | Named state read; credentials disabled while state unknown; recover through refresh; secret clearing retained | Outer content aligns with shell; form has internal reading width | Verified source + actual module startup/refresh/error fixtures |
| New Project · /?new=1 | Root-owned Native workspace under shared shell; CREATE selected | Original creation IDs/handlers; profile/format/brand/template fields | Native workspace implementation and tests are owned by root | Common shell cap; root workspace breakpoints | Shared node preservation + root workspace tests in full suite; new pixel scope listed below |
| Script stage · project | Same Native PageHeader/stages | Existing generation/edit/script-only and combined approval controls | Original review/generation guards retained by root | Root stage-reading layout under shared shell | Root workspace source/tests; new pixel scope listed below |
| Project Assets / global Assets · project / ?view=assets | Same shell; root-owned Assets workspace/picker | Upload, library select, preview, attach/remove/replace; original library remains protected | Useful empty project/global-library states | Root asset grid/picker breakpoints | Root source/tests; new pixel scope listed below |
| Storyboard stage · project | Same shell/stages/cards | Root-owned selected shot/asset actions reuse picker | Existing generation/asset availability states | Root responsive storyboard grid | Root source/tests; new pixel scope listed below |
| Video editor · project | Same shell, header/stages, shared inspector vocabulary | Root-owned centered format-aware preview, strip, selected shot, categorized controls | Explicit preview/final actions and stale states retained | Root preview height/ratio and inspector breakpoints | Root preview/asset tests in full suite; new pixel scope listed below |
| Video review · project | Same shell and dedicated root review layout | Existing human accept/request changes controls; metadata and collapsible details | Render/QC/current approval gates retained | Root ratio-aware review canvas, reduced clutter | Root source/tests; new pixel scope listed below |
| Brands / templates · /?view=brands | Same shell; root retains Native configuration details | Existing deliberate brand/template selection and apply controls | Existing revision/approval invalidation semantics | Root settings under shared outer cap | Source integration present; new pixel scope listed below |
| Advanced timeline / Diagnostics | Shared optional hierarchy | Existing engineering controls/runtime IDs preserved | Details remain available without foregrounding hashes/providers | Intentional timeline/shot scrollers permitted | Key DOM identity tested; Advanced Timeline pixel scope listed below; Diagnostics expansion uninspected |

## Frontend verification

The final complete Studio suite passed **79/79, 0 failures/cancellations/skips/todo**, exit0, elapsed0.429s. The receipt records the43-file source fingerprint `151c9d2b1dd124e15daa914560c1fd826f098b571da6e9145a60cb276c71ba5d` unchanged before/after testing. Independent read-only comparison found **43/43 current files match** that manifest. Evidence: [final summary](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/tests/full-studio/20261006T154653648027Z/summary.json), [exact final log](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/tests/full-studio/20261006T154653648027Z/test-output.log). Log SHA256:4146d74832d389c8d43fd47d51f2098fc79365260d8893df5d4f041d825727a1.

The earlier75/75 runs and focused shell/runtime runs remain history. Four added real-module fixture cases verify explicit Refresh recovery after local session rotation using GET and updated session credentials, preserving user write intent without automatically replaying a write.
New checks cover shared navigation/fresh project selection, Native node and callback preservation, shell idempotence, strict optional capability handling, safe fallback after optional import failure, exact review status filtering, historical resolution without FullHD inference, approved local file URLs, four real Production view boots, zero automatic Production POSTs, read-only connection refresh and unknown-state credential guards. Existing legacy/current CI approval transport tests remain passing. Root-owned creation/picker/preview tests also run in the full suite.

The tests use DOM/HTTP fixtures and local files. This subtask made no real provider requests, application data writes, browser actions or commits. Native/Phase8/Phase9 persistence and accepted historical output verification belong to the separate parent regression evidence; they are not inferred from this frontend test result.

## Final responsive evidence matrix

**72/72 selected visible-scope cells PASS**:24 view/state rows at1366×768,1920×1080 and2560×1440. Every selected source file was actually opened through tools.view_image and its SHA256 matches the parent capture ledger. The JSON maps exact files, scopes, formats and hashes to each cell. Static PASS does not certify every lower pane, moving audio/video or personal Owner UAT. [Per-file JSON and selected matrix](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/screenshots/20261006-actual-ui/pixel-audit.json), [pixel notes](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/screenshots/20261006-actual-ui/pixel-audit.md).

|View/state|1366×768|1920×1080|2560×1440|
|---|---|---|---|
|Dashboard|PASS stats/cards|PASS loaded cards; older planning caption|PASS surface-safe stats/cards|
|Production Queue|PASS filters/cards; Kế hoạch|PASS recovered-session closed queue; Kế hoạch|PASS filters/cards; Kế hoạch|
|Content Intelligence overview|PASS loaded overview|PASS loaded overview|PASS centered workflow strip/overview|
|New Project|PASS settled upper form/CREATE selected|PASS upper form/CREATE selected|PASS full form/submit/CREATE selected|
|Script|PASS upper form|PASS upper form|PASS script/source upper regions|
|Project Assets empty|PASS visible empty actions|PASS visible empty actions|PASS visible empty actions|
|Project Assets populated|PASS loaded first-row cards/actions|PASS loaded cards/actions|PASS loaded cards/actions|
|Storyboard|PASS painted first row; Dự kiến|PASS five cards; Dự kiến|PASS five cards; Dự kiến|
|Portrait Video editor|PASS full398px canvas/upper inspector|PASS settled640px canvas/upper inspector|PASS settled1000px canvas/inspector|
|Portrait Video review|PASS settled canvas/review; panel scroll|PASS settled canvas/disabled review form|PASS settled canvas/form and scroll0 header|
|Landscape Video review|PASS full685×385 frame; native JPEG|PASS full1138×640 frame/review|PASS full1250×703 frame/player/review|
|Final Videos|PASS approved visible cards|PASS approved historical visible cards|PASS approved historical visible cards|
|Projects|PASS visible cards/filters|PASS visible cards/filters|PASS visible cards/filters|
|Calendar|PASS visible date group|PASS visible date group|PASS visible date cards|
|Profiles|PASS settled visible cards|PASS settled visible cards|PASS settled catalog; fifth lower card scroll|
|Connection Settings|PASS connected state only|PASS connected state only|PASS connected state only|
|Planning modal|PASS upper + scrolled reviewer/Save footer; native JPEG|PASS upper + scrolled reviewer/Save footer|PASS full modal/footer|
|Global asset Library|PASS decoded first-row thumbs/actions|PASS decoded cards/actions|PASS decoded cards/actions|
|Brands/templates|PASS no-project disabled state|PASS no-project reference values|PASS selected-project enabled Apply state|
|Asset Picker/selection preview|PASS visible-confirm footer/preview|PASS selected preview/footer|PASS selected preview/footer|
|CI findings|PASS scrolled source/excerpts|PASS scrolled source/excerpts|PASS scrolled source/excerpts|
|CI ideas|PASS first idea/labels; further ideas scroll|PASS first full idea; further ideas scroll|PASS first idea and next card start|
|CI brief and guarded footer|PASS upper fields + separate lower controls|PASS upper fields + separate lower controls|PASS upper fields + separate lower controls|
|Shot strip/Advanced Timeline|PASS stacked cards/upper tracks; native JPEG and intentional scroll|PASS five stacked cards/all labels; native JPEG|PASS five stacked cards/metadata/all labels; surface-safe PNG|

Final inventory: **148 images(140 PNG+8 JPEG);121 actually pixel-inspected;94 bound per-file visible-region PASS;11 partial and12 invalid inspected diagnostics excluded**. Four further inspected diagnostics have superseded/provisional dispositions. Uninspected originals are explicitly superseded or byte-identical invalid diagnostics. Zero binding mismatches, post-review file changes or pending first inspections. These per-file counts are distinct from the selected72 cells; repeated captures do not broaden a visible scope.

All three mandatory portrait PNGs remain coherent, actually inspected and bound to the latest ledger:

- 1366:6757280e9a57863e243fe5f3bd9d3d5902ca26a196b3bd7556bddf03ffb0278a
- 1920:30397f53d5194cbf51d66d405f412113c76d4a4f2c57591fe029c8b9ed07737b
- 2560:edb7496f834d3f93f5dc9b858e49005ef2803ca8af8ce117f4562d789f013154

The portrait1366 player is224×398px and1920 is360×640px;2560 contains a1000px-high portrait frame. Native fullscreen is visible. Fine caption judgement at224px inline width is limited. Landscape shows the complete16:9 frame at all three requested DOM viewports.

The1366 landscape, after-fix strip and modal footer use **authentic, unedited native JPEG** files with1351×760 source pixels bound to a1366×768 DOM viewport. The1920 after-fix strip JPEG is1905×1072 bound to1920×1080. Source pixels and viewport dimensions are recorded separately; these are not mislabeled exact-size PNGs or edited/transcoded replacements. The2560 native JPEG cuts the right inspector/lower cards and remains partial. The coherent final2560 stacked PNG supplies full after-fix strip/track evidence. CDP tiled, blank31px-sidebar and host-desktop diagnostics remain excluded.

Three observed P2 layout faults are resolved: CI2560 step-strip centering;1366 picker confirmation footer visibility; and landscape shot-card overlap caused by a generic inline-flex button rule. The specific shared display:block shot-card override preserves widths and horizontal strip scrolling. The final1366/1920 native stills and2560 PNG verify stacked labels/thumbnails/metadata. Dự kiến and Kế hoạch distinguish estimated/planned timings from measured current output. Global Library replacements show decoded, contained portrait/landscape thumbnails at all sizes.

CI lower regions wrap labeled source/model statements correctly. Separate footer captures show acknowledgment unchecked, reviewer blank and guarded approval/Studio transfer disabled. The [keyboard receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/screenshots/20261006-actual-ui/keyboard-focus-receipt.json) records Escape closing the actual picker and returning focus to shot-choose-asset with a solid outline. The [real Refresh receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/screenshots/20261006-actual-ui/actual-refresh-after-restart-receipt.json) records an existing-tab explicit Refresh recovering after an actual idle8030 restart without navigation/reload or application mutation. These are parent runtime observations, not screenshot-derived keyboard/session claims.

The supplemental [Planning scroll receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/studio-ux-02/screenshots/20261006-actual-ui/planning-scroll-runtime-receipt.json) records normal internal dialog scrolling to the empty reviewer field and visible Save plan footer:233px scroll at1920(footer y947..987),545px at1366(footer y635..675). Separate footer images verify these pixels. The dialog was then closed without Save; zero dialogs/five VIDEO_REVIEW rows remained and no app mutation or human acceptance was created.

**No open verified P0/P1/P2 layout fault remains in the selected coherent visible regions.** Intentional page/panel/strip scrolling is permitted. All five1366 Timeline labels, expanded Diagnostics, every optional disclosure, disconnected/error Settings and whole moving-video/audio review are not inferred from these stills. Loading/error handling is covered in source and fixtures; archived busy/loading images do not receive settled PASS. The misleading historical filename final-videos-approved-empty-1920x1080.png contains populated approved historical cards, not an empty state or approval of the repaired five.

## Gates and remaining acceptance

PRODUCTION_INTELLIGENCE_READY = YES (existing parent gate).

DRAMAGIC_STUDIO_READY = NO.

PHASE10_READY = NO.

OWNER_UAT_REQUIRED = YES.

The parent capture campaign is complete for the bounded technical matrix. Explicit Owner acceptance of both the repaired five videos and the redesigned Studio flow remains pending. No frontend fixture or technical screenshot substitutes for that Owner UAT.
