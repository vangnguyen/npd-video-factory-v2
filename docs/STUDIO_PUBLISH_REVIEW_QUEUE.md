# Studio publish review and queue

The API Studio now exposes separate actions to prepare a review, grant publish-only
consent, enqueue approved work, refresh status and revoke the selected consent.
Existing dry-run remains available. Default publishing flags stay disabled; no page
load, review read or consent click starts a provider or queues work automatically.
Actual queue execution still requires the explicitly configured runtime and all
current backend gates. This increment does not start a production worker supervisor.

Owner controls use the exact current workspace/global/slug role, never a foreign
workspace's Owner role. Viewers can read public scoped profiles, review and work
status. Backend authorization independently enforces mutations. Buttons require a
current approved/QC-passed final, an explicitly selected configured channel, current
enablement and a checked acknowledgment of the displayed review. Disabled deployments
and missing configuration remain unavailable. Tokens remain in the existing human
session mechanism; the page acquires no provider secrets or keys.

`GET /api/v1/projects/{project_id}/publishing-profiles` returns only the project's
workspace and latest public profile revisions. Missing optional configuration returns
an empty catalog. `GET .../publications/{publication_id}/publish-review` revalidates
the current canonical timeline, production approval, subtitle/audio versions, final
render/QC, rights and target. It returns public binding hashes, exact metadata and
any still-valid consent. Reads grant no consent, lease, queue entry or external
action. Both endpoints use `Cache-Control: no-store` and reject foreign resources.

Consent binds the displayed publication/project/workspace, request fingerprint,
render/asset IDs, artifact SHA256 and target SHA256. Server admission independently
rejects stale versions. A changed artifact invalidates consent without rewriting its
history. Queueing is a second explicit action; revocation concerns that selected
consent and does not delete remote media or undo an in-flight request. Expired,
revoked or mismatched consent cannot enable the queue control.

Review metadata is inserted with `textContent`; render hashes and Vietnamese text
wrap within a bounded scroll area. Switching projects/publications clears review
and acknowledgment. In-flight responses are scoped and cannot update another
selected publication. Unknown queue availability is displayed as unavailable rather
than an empty-success state. Mock receipts retain the explicit mock label.

## Evidence

The Studio suite passed 130 tests. The seven focused console tests passed again
after the final render/asset binding checks. API fixture coverage checks read-only
behavior, workspace isolation, active/revoked consent, changed artifact history and
latest scoped profiles alongside existing runtime/queue contracts.

The expanded runtime contract uses the preserved synthetic 1080x1920/30 H.264/AAC
source, 4,256,257 bytes, SHA256
`80de36cef34e3945a196e32928ee8d77e6a67100810501acfd38c35d99ebca2d`.
Nine authenticated ASGI requests include viewer profile/review reads and revoked
consent observation. Reading sends no provider request. Two real QC scans and two
separate restarted processes reconcile the known mock session and observe completion.
Eight provider calls are MockTransport fixtures, one initialization occurs, actual
costs remain null and the source is unchanged. Nine JSON exports are preserved.

Identity, account, credentials, keys, approvals and timeline/subtitle inputs remain
fixtures. This is local-real media/API evidence with mock provider outcomes, not
real publishing, browser usability at 1366/1920/2560, Owner UAT or final A/B/C
acceptance. Native distribution controls, persistent Owner configuration/secret
administration, cancel/resume administration, production supervision, complete
non-YouTube durable adapters and actual provider acceptance remain incomplete.
