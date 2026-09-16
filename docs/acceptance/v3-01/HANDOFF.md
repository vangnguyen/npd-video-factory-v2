# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B12R
VERDICT: SOURCE CANDIDATE / G-08 AND CANDIDATE CI REQUIRED
REPO: vangnguyen/npd-video-factory-v2

The exact source baseline is governance main
`7ad25cb039c712d450486778d2981d9ef8175385`. Historical
`vf-v3-01-rc19` remains immutable at
`dc8ff55322267dfe54674fa6c4003a899bf235ab`, with executable-tree SHA
`432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
This source candidate changes the executable tree to
`25829c155f00c3e9aded66b7c57695c9b364aa2d237e4a8c9bbb0ef6247b68ef`.
It is **not** RC-19 and cannot reuse its Operation 1 authority, bundle,
scope, window or ledger schema. A fresh RC is required only after a separately
approved merge and exact-main verification. No RC or authority was created in
this task.

The proposed canonical entrypoint is
`app.provider_single_dispatch.run_single_dispatch`. It binds a future fresh RC,
bundle, G-01/G-02/G-03 authority, provenance, lineage-specific PostgreSQL
custody, immutable W1 inputs and a fail-closed runtime policy. An opt-in
durable marker distinguishes unconsumed pre-transport failures from terminal
possibly-sent operations. Exclusive evidence is armed before dispatch; the
operation-scoped one-shot kill switch re-engages on all tested paths. The
historical controller remains unchanged for historical evidence. See the
[source candidate review](reviews/vf-v0s-b12r/README.md).

Current handoff safety state: Operation 1 under RC-19 is historical only for
this candidate; Operation 2 remains locked. Bundle unmounted; kill switch
engaged; production provider credential reads 0; live reservations 0 VND;
real provider calls 0; actual spend 0 VND; production business writes 0.
ASR `0/2 PASS`; Vision `2/2 PASS`; Production `NO-GO`.

Earlier B6 custody evidence and later unmerged governance work remain in Git
history/separate drafts; this candidate does not rewrite their receipts. The
source candidate requires exact-head G-08 and candidate CI review. The next
safe action is Owner review of the Draft PR; do not merge or create a new RC
under this task.
