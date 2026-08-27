# Security audit

## Current decision

`NO-GO FOR PUBLIC OR PRODUCTION EXPOSURE`

The baseline is suitable only for localhost/CI. Service-to-service Agent Hub HMAC is implemented,
but ordinary API and Studio routes have no accepted interactive authentication, RBAC or workspace
membership enforcement.

## Control review

| Control | Evidence | Result |
|---|---|---|
| Interactive identity/session | no human auth dependency on normal routers | FAIL |
| RBAC/workspace isolation | role vocabulary exists for bridge, not Studio/API users | FAIL |
| Agent Hub HMAC/replay/skew | dedicated service identity and rotation tests | mock PASS |
| Request correlation/security headers | middleware and tests | mock PASS |
| Input schema/unknown fields | strict models/tests | mock PASS |
| Upload size/MIME/hash/FFprobe | implemented/tests | mock PASS |
| Malware quarantine | no complete scanner/quarantine acceptance | BLOCKED |
| Rate limiting | no accepted public-ingress control | BLOCKED |
| SSRF/path traversal/argument injection suite | incomplete | BLOCKED |
| Object/project authorization | project-scoped paths, no accepted user principal | BLOCKED |
| Secrets in repo/evidence | ignore rules, redaction and pattern scan | PASS for this audit scope |
| Live write controls | publish/external/paid gates false | PASS at configuration boundary |

## Threat-boundary decision

Until `SEC-001` and `SEC-002` pass, API and Studio must stay on localhost with no public reverse
proxy. URL import remains disabled. Uploaded media is untrusted input; extension, MIME and FFprobe
agreement alone are not malware clearance.

The evidence harness reads only checked-in acceptance files and redacted evidence. It does not read
`.env`, contact providers, deploy, publish or rotate credentials. `private/`, `raw/` and HAR evidence
are ignored and must not be committed.

## Required remediation acceptance

- authenticated session lifecycle and denial by default;
- viewer/editor/approver/admin separation and cross-workspace denial tests;
- request/body/rate limits at app and ingress boundaries;
- malicious file, fake extension, archive bomb, traversal, SSRF and command-argument tests;
- secret scan plus dependency/container vulnerability review;
- signed webhook replay/clock-skew/key-rotation tests retained.

Open gaps: `V3-01-GAP-001`, `V3-01-GAP-011`, `V3-01-GAP-012`, `V3-01-GAP-014`.
