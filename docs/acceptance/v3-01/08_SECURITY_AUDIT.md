# Security audit

## Current decision

`V3-01-03 LOCAL/CI MEDIA-INGRESS SECURITY CONTRACT PASS; NO-GO FOR PUBLIC OR PRODUCTION EXPOSURE`

V3-01-01 identity/RBAC is merged. V3-01-03 adds local quarantine and malware/archive controls on an
isolated branch. The new edge/WAF document is a contract, not a deployed route. No public ingress,
scanner service, provider credential, deployment or production-path test is authorized.

## Control review

| Control | Evidence | Result |
|---|---|---|
| Interactive identity/session | hash-only external registry, bounded expiry/revocation and secret-safe session endpoint | local/mock PASS |
| RBAC/workspace isolation | viewer/editor/reviewer/owner plus object-bound 404 denials | local/mock PASS |
| Agent Hub HMAC/replay/skew | dedicated service identity and rotation tests | mock PASS |
| Request correlation/security headers | middleware and tests | mock PASS |
| Input schema/unknown fields | strict models/tests | mock PASS |
| Upload size/MIME/hash/FFprobe | implemented/tests | mock PASS |
| Malware quarantine | assembled media enters quarantine; clean scan is required before trusted storage; EICAR is rejected | local/mock PASS; production scanner NOT_CONFIGURED |
| Rate limiting | Redis-backed limit per valid human session; unauthenticated ingress/WAF still absent | partial PASS |
| SSRF/path traversal/argument injection suite | URL import rejected; traversal/fake/archive/argv tests pass; archive containers never decompress | local/mock PASS |
| Edge WAF/body/rate controls | `ingress-media-security.v1` defines route/body/rate/TLS requirements | DESIGN ONLY; no public route |
| Object/project authorization | workspace resolved through workspace/project/job/upload/cluster/idea and cross-scope objects return 404 | local/mock PASS |
| Secrets in repo/evidence | ignore rules, redaction and pattern scan | PASS for this audit scope |
| Live write controls | publish/external/paid gates false | PASS at configuration boundary |

## Threat-boundary decision

`SEC-001` passes only at local/CI scope. `SEC-002` remains partial. API and Studio must therefore stay
on localhost with no public reverse proxy. URL import and archive ingestion remain disabled. An
upload is not trusted until the configured scanner returns `clean`; unavailable/error/infected
verdicts fail closed and cannot create an asset.

The evidence harness reads only checked-in acceptance files and redacted evidence. It does not read
`.env`, contact providers, deploy, publish or rotate credentials. `private/`, `raw/` and HAR evidence
are ignored and must not be committed.

## Required remediation acceptance

- production identity provisioning/SSO decision and production-path session evidence;
- ingress/WAF request/body/rate limits, including unauthenticated attempts;
- approved internal clamd deployment, signature-update evidence and quarantine retention operation;
- secret scan plus dependency/container vulnerability review;
- signed webhook replay/clock-skew/key-rotation tests retained.

Security state: `V3-01-GAP-001` is `REMEDIATED`; bounded G-08 approvals through PR #14 are consumed
while production verification remains absent;
`V3-01-GAP-011` is `IN_PROGRESS`; `V3-01-GAP-012` and `V3-01-GAP-014` remain open.
