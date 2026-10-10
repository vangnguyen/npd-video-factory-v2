# Native Meta publishing runtime and signed media API

The existing versioned Meta executor now runs through the Native server, its shared worker and finite publication queue. Media disclosure has its own protected configuration, scoped API and worker. Two actual local authenticated HTTP flows cover Facebook and Instagram Reels, with explicitly mocked Meta/S3 providers, human authority, platform eligibility and nonplayable media. This does not establish real provider, Studio, browser, Owner UAT or full Mode A/B acceptance.

## Protected configuration and startup

The CLI accepts `--meta-distribution-registry`, `--enable-meta-distribution`, `--publishing-media-registry` and `--enable-publishing-media`. Both enable flags default false. The existing Meta account registry/read enablement, signed human access, publishing capability file, separate private session directory and publication queue enablement remain independent. A manifest's enabled flag cannot enable the runtime by itself.

`native-publishing-media-registry-v1` binds a workspace, S3-compatible storage profile, private lease directory, optional DPAPI credential file with aware expiry and nullable estimated operation cost. Manifests and private paths must be outside source and State. Duplicate keys, unknown fields, boolean integers, insecure endpoints and arbitrary endpoint paths/queries are rejected. Its exact byte digest and private credential ciphertext digest are pinned before operation. No token, lease URL or private path is returned in its public configuration.

`native-meta-distribution-registry-v2` binds the existing scoped Meta account configuration to a publication profile, default-off gates and the exact media configuration digest. Legacy v1 remains execution-disabled. Configuration dependencies and injected-client scope are checked before allocating a listening socket; injectable clients must be explicit offline mocks. Protected registry startup does not decrypt credentials or construct an S3 SDK client. Missing credentials retain NOT_CONFIGURED capability and leave core work available.

## Signed API and separate consent

All routes use existing Native authentication and workspace/project scope. Writes require a current human Owner and their own CSRF token before body processing. Public responses have `Cache-Control: no-store` and do not return signed URLs.

| Route | Purpose |
| --- | --- |
| `GET /api/connections/publishing-media` | Read safe configured/default-off capability. |
| `GET /api/projects/{project}/official-publications/{publication}/media-deliveries` | Read bounded, scoped delivery history with an opaque scoped cursor. |
| `GET .../media-deliveries/{delivery}` | Read one exact original delivery and its public proofs. |
| `POST .../media-deliveries` | Create a finite, explicitly acknowledged media-disclosure request bound to publication, original final, grant and configuration. |
| `POST .../media-deliveries/{delivery}/process` | Process that original request with its expected snapshot digest. |
| `POST .../media-deliveries/{delivery}/cancel` | Cancel that original request with its expected snapshot digest. |
| `POST .../media-selection` | Acknowledge an exact completed delivery and current dispatch version for the Meta executor. |

Creating a delivery does not perform an SDK request. The worker can subsequently claim that authorized delivery atomically. Delivery approval, exact selection, publication approval and bounded queue scheduling are distinct. They cannot authorize one another. Existing immutable final, metadata, rights, platform, cost and current Owner checks remain in the shared journals and worker; both Studio editing views keep the same canonical timeline.

Startup recovery first recovers media delivery intents, then the existing publication worker and queue. Recovery performs no credential decryption, storage request or publication replay. A keyless default-off server still returns exact historical publication state, media delivery and cost proofs. Exact idempotent delivery replay can return the saved request after configuration is removed; it cannot create new work without configuration and fresh authority.

## Evidence and remaining work

Related Native regression: 185 PASS, 367.843 seconds. Final runtime/registry scope: 26 PASS, 71.698 seconds, including four security/CLI cases added after the related run. These suites overlap and must not be added as independent counts. The CLI help interface is exercised in a subprocess; actual HTTP runtime flows instantiate the real LocalServer on isolated loopback ports.

Retained `meta-runtime-flow-n1` contains 22 Instagram and 28 Facebook signed HTTP requests, three and five publication worker steps, one mock storage write per platform and 15 nullable cost records per platform. Two public backups restore into separate default-off processes and return identical signed HTTP history without keys or replay. Evidence, hashes and scope are indexed in `docs/north-star/meta-runtime-evidence.json`.

Next safe work: connect exact Meta review/media-disclosure/selection/status controls to Studio, complete platform analytics and multipart delivery, and continue every remaining original Master Spec requirement. Genuine storage/Meta permissions, credentials, app/version eligibility, actual browser/non-developer use, Owner UAT, real media and production acceptance remain separate. No real external request, paid operation, external post, historical data deletion, main merge or production deployment occurred. Counts remain 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED: 59 broad groups unclosed. All full North Star completion flags remain NO.
