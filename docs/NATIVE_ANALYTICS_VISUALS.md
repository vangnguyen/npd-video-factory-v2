# Native Analytics time series and comparison

Wave 10 and the original Master Spec analytics requirements remain authoritative. The Native panel now plots saved observations, offers all 15 normalized metrics and compares each video's latest two observations. This is a presentation increment over the existing append-only analytics store and scoped read routes; official Native analytics remain NOT_CONFIGURED.

## Saved evidence and scope

Metric changes redraw loaded history without fetching a provider or altering a project, snapshot, assessment, budget or publication. Existing Owner-only fixture requests, acknowledgement, exact retry keys, workspace/project/publication checks and late-response discard remain. Project switches clear every old plot.

Each publication/platform/fixture-or-API provenance has its own series. Null stays unknown and breaks the path. An actual zero remains a known observation. All-null metrics produce a missing-data explanation and no numeric plot. Collection timestamps define the UTC axis; the panel does not invent video age, hourly velocity, account totals or a channel baseline. Counts from different platforms are not treated as equivalent performance evidence. Fixture scenarios are labelled and do not become audience history.

Comparisons use the latest two observations at distinct collection times, with both values known. Missing latest/previous values or equal timestamps have no inferred delta. A zero denominator has no relative percentage. Nonfinite relative change remains unknown. Rates use percent/percentage-point labels; durations use seconds; revenue uses normalized VND and RPM uses VND per 1,000 views. The panel does not rank, classify winners or perform any automatic action.

The component rejects invalid dates, negative/nonfinite values, out-of-range fractions, contradictory provenance and conflicting duplicate snapshot IDs. Duplicate identical observations are not counted twice. Display retains at most 1,000 loaded observations and plots at most 12 latest video series; scope limits and unread pages are visible. These presentation limits never overwrite persisted history. Exact point IDs, timestamps and values remain available beside the graph.

## Rendering and accessibility

SVG titles, accessible graph labels, per-series legends, literal text, semantic comparison tables and raw-point details accompany the graph. Chart labels retain their scale in narrow panels using contained horizontal scrolling. The comparison table scrolls within its panel. No provider URL, private prompt or secret is included in a chart.

Actual saved HTTP data are rendered through the same chart functions by `scripts/north_star_native_analytics_visuals.mjs`. The retained standalone HTML/SVG/models and PNG raster inspection verify component output and Vietnamese typography; they do not certify browser/non-developer/Owner usability at the required app viewports.

## Verification

Full Studio: 268 passed, including ten new cases for gaps, zero values, separate provenance/video series, units, limits, invalid inputs, extreme finite values, DOM rendering, complete currency axes and redraw/scope isolation. Affected Native analytics/authenticated HTTP/Phase 10 contracts: 26 passed. The unchanged Native runtime's last full regression is 699 passed; no backend implementation changed here.

The signed HTTP rehearsal restores the preserved narrated fixture into a fresh owned root, appends three explicitly acknowledged test scenarios and preserves the prior snapshot, project, jobs and physical assets. It records four synthetic snapshots and an official request with zero attempts/no replacement metrics. The scenario profiles are independent test inputs, not an observed audience trajectory. A fresh backup includes the append-only history. Source originals and accepted videos remain untouched.

The first DOM integration fixture omitted its required external-call marker and was correctly rejected; corrected the fixture. The first retained HTTP helper expected an explicit `snapshot` key in the create receipt; the real contract omits it until a read, and the helper now treats its absence as no snapshot. The initial component export assumed every fixture lacked revenue; the actual winner fixture has a declared revenue value. The export now preserves that value, its three missing observations and a separately labelled all-null insufficient-data subset. Rejected outputs are retained; no guard was relaxed.

Raster inspection found the leading digit of a long revenue axis clipped. Units now occupy the heading and numeric axes have a wider margin; current-source render/raster inspection verifies all digits. Older renders are retained.

Evidence: `docs/north-star/native-analytics-visuals-evidence.json` and external `recovery/20261007/native-analytics-visuals-flow-n4`. Official account/credentials/read runtime, recurring sync, accepted AnalyticsProfile, genuine channel cohorts/history/relative winner calibration, browser/non-developer/Owner and production acceptance remain separate. IMPLEMENTATION_COMPLETE = NO; REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO; PRODUCTION_DEPLOYED = NO.
