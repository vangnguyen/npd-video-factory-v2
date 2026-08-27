# Security audit

## Current decision

`V3-01-01 LOCAL/CI SECURITY REMEDIATION PASS; NO-GO FOR PUBLIC OR PRODUCTION EXPOSURE`

Commit `9635fb3ecf5d5fc5ba20aef3486708bad5960b8b` adds the interactive identity boundary that was
missing from the baseline. It passes local/CI and disposable Docker tests, but it is not merged,
deployed or production-path tested. Agent Hub HMAC remains an independent service identity.

## Control review

| Control | Evidence | Result |
|---|---|---|
| Interactive identity/session | hash-only external registry, bounded expiry/revocation and secret-safe session endpoint | local/mock PASS |
| RBAC/workspace isolation | viewer/editor/reviewer/owner plus object-bound 404 denials | local/mock PASS |
| Agent Hub HMAC/replay/skew | dedicated service identity and rotation tests | mock PASS |
| Request correlation/security headers | middleware and tests | mock PASS |
| Input schema/unknown fields | strict models/tests | mock PASS |
| Upload size/MIME/hash/FFprobe | implemented/tests | mock PASS |
| Malware quarantine | no complete scanner/quarantine acceptance | BLOCKED for V3-01-03 |
| Rate limiting | Redis-backed limit per valid human session; unauthenticated ingress/WAF still absent | partial PASS |
| SSRF/path traversal/argument injection suite | URL import rejected; traversal/fake/archive/argv tests pass | local/mock PASS |
| Object/project authorization | workspace resolved through workspace/project/job/upload/cluster/idea and cross-scope objects return 404 | local/mock PASS |
| Secrets in repo/evidence | ignore rules, redaction and pattern scan | PASS for this audit scope |
| Live write controls | publish/external/paid gates false | PASS at configuration boundary |

## Threat-boundary decision

`SEC-001` passes only at local/CI scope. `SEC-002` is partial. API and Studio must therefore stay on
localhost with no public reverse proxy. URL import remains disabled. Uploaded media is untrusted
input; extension, MIME and FFprobe agreement are not malware clearance.

The evidence harness reads only checked-in acceptance files and redacted evidence. It does not read
`.env`, contact providers, deploy, publish or rotate credentials. `private/`, `raw/` and HAR evidence
are ignored and must not be committed.

## Required remediation acceptance

- production identity provisioning/SSO decision and production-path session evidence;
- ingress/WAF request/body/rate limits, including unauthenticated attempts;
- malware scanning/quarantine and decompression-resource acceptance;
- secret scan plus dependency/container vulnerability review;
- signed webhook replay/clock-skew/key-rotation tests retained.

Security state: `V3-01-GAP-001` is `REMEDIATED`; bounded G-08 merge approval is recorded while
production verification remains absent;
`V3-01-GAP-011` is `IN_PROGRESS`; `V3-01-GAP-012` and `V3-01-GAP-014` remain open.
