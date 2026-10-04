# NPD Provider Broker

Standalone Linux VPS service, version 0.1.0. It does not import Video Factory,
access its Content ledger, or integrate with proposals, ASR, TTS, n8n, EspoCRM or
other protected services. Content generation is always disabled in this version.

## Runtime boundaries

- The compose project contains only `provider-broker`. Linux host networking and
  Uvicorn's fixed `127.0.0.1:18084` bind keep the service on VPS loopback; no
  Docker port is published. Access from another host needs a separate task.
- The official OpenAI Python SDK uses one factory, the official
  `https://api.openai.com/v1` origin, verified TLS, a 30-second timeout and
  `max_retries=0`. Direct VPS networking uses `trust_env=False`, preventing
  ambient proxy, Cloud placeholder and alternate origin substitution. Presence
  of Codex Cloud credential/proxy context blocks the runtime before key reads.
- Only the public source SHA is configured through the environment. API key
  and client token are read from root-owned regular files with mode `0600`.
  Secret symlinks and changed file custody are rejected. Readiness uses file
  metadata only and does not read key content or inspect key shape.
- The container uses root solely to read the required root-owned secret files;
  its filesystem is read-only, all capabilities are dropped, and privilege
  escalation is disabled. Only its own durable canary claim directory is writable.
- SDK/HTTP client diagnostics and Uvicorn access logging are disabled to prevent
  header/error disclosure. Broker logs contain fixed endpoint, generated
  correlation ID, status, latency, safe provider request ID and usage only.

## API

| Endpoint | Authentication | Action |
|---|---|---|
| `GET /healthz` | None | Service/version; no OpenAI call |
| `GET /readyz` | None | Secret-present and configuration booleans; no OpenAI call |
| `POST /internal/canary/openai-model` | Internal Bearer token | One retrieve of `gpt-6-luna` |
| `POST /internal/canary/openai-responses` | Internal Bearer token | One fixed minimal Responses request, after model PASS |
| `POST /internal/content/generate` | Internal Bearer token | `BROKER_CONTENT_EXECUTION_DISABLED` |

Canary bodies accept only `owner_decision_id`. Model, endpoint, prompt, tools,
provider headers and caller API keys are not accepted. The default maximum body
is 1,024 bytes. Unknown paths and duplicate authentication headers are rejected;
validation errors never echo caller input. The fixed Responses payload is:

```json
{"model":"gpt-6-luna","reasoning":{"effort":"none"},"input":"Return exactly OK.","max_output_tokens":16,"store":false}
```

Claims are consumed durably before SDK dispatch, even on error or ambiguity.
Atomic exclusive files prevent a repeated decision/endpoint from dispatching
again after a restart. No automatic retry or fallback exists. If HTTP model
canary fails, the Responses endpoint refuses execution. Successful Responses
requires completed status, exact model, one `OK` output without refusal/tool
calls, and valid token usage within the 16-token limit.

`BROKER_CANARY_OBSERVED_USAGE` records token counts separately with
`provider_billing_observed=false`. It is not Content ledger accounting or
confirmed billed spend. Historical Cloud accounting remains sealed at
committed 10,000 VND / reserved 0; this service never opens that database.

## Offline qualification

From the repository root:

```bash
python -m pip install -e 'services/provider-broker[dev]'
python -m pytest services/provider-broker/tests -q
python services/provider-broker/scripts/docker-smoke.py \
  --source-head "$(git rev-parse HEAD)" --output /tmp/broker-offline-smoke.json
```

The container smoke uses synthetic fixture files, an internal Docker network
with no external route, no published ports, and only loopback diagnostics.
Neither test suite performs an OpenAI request.

## VPS deployment bundle

Export the committed, review-approved source outside Git:

```bash
python services/provider-broker/scripts/export-bundle.py \
  --output-dir /workspace/shared/npd-provider-broker-deploy/<SOURCE_HEAD>
```

Transfer `provider-broker-source.tar.gz` and `SHA256SUMS` to the authorized VPS
using its approved SSH access, verify `sha256sum -c SHA256SUMS`, and extract into
a new deployment directory. The deterministic bundle includes public source
only; it does not include secrets, credentials or runtime accounting state.

Use the review-approved source SHA supplied with the deployment bundle. Extract
the standalone bundle into a new directory such as
`/opt/npd-provider-broker/<SOURCE_HEAD>/`. `SOURCE_MANIFEST.json` binds all public
source files to that SHA; the controller rejects changed or extra bundle files.
Run commands below **on the authorized Linux VPS**, as root. Do not copy any
Codex Cloud Network Secret into the VPS or include secrets in the bundle.

Install the Owner-provided OpenAI key interactively on the VPS terminal:

```bash
sudo python3 scripts/vps.py install-secrets --owner-authorized
```

This refuses overwrite, accepts hidden input locally, generates an independent
internal broker token, and writes only:

- `/etc/npd-video-factory/provider-broker/openai_api_key`
- `/etc/npd-video-factory/provider-broker/broker_token`

Both files are `root:root 0600`; their directory is `0700`. Do not send the key
or token through chat, argv, environment variables or logs. Existing properly
installed files can be used without running installation. Compose mounts them
read-only under `/run/secrets/`.

```bash
sudo python3 scripts/vps.py preflight --source-head <SOURCE_HEAD>
sudo python3 scripts/vps.py deploy --source-head <SOURCE_HEAD>
```

Preflight checks only required files, Docker/Compose availability, source identity
and loopback port availability. It returns `BROKER_SECRET_NOT_INSTALLED`,
`BROKER_SECRET_PERMISSIONS_INVALID`, `BROKER_CONTAINER_RUNTIME_UNAVAILABLE` or
`BROKER_PORT_CONFLICT` and stops. It never replaces an unrelated service.
Deploy builds/starts only this compose project, without restarting dependencies,
then checks `/healthz` and `/readyz`. These commands make **zero OpenAI calls**.

Only after health/readiness pass, under task21's exact two-call authority:

```bash
sudo python3 scripts/vps.py live-canaries --source-head <SOURCE_HEAD> \
  --owner-authorized \
  --owner-decision-id VF-MVP1-VPS-PROVIDER-BROKER-BOOTSTRAP-21 \
  --output-dir /var/lib/npd-provider-broker/task21-canary-evidence
```

The evidence directory is create-only. The controller sends one internal model
canary request; only model HTTP 200/PASS permits one Responses canary request.
No third call, retry, fallback, Content operation or Content budget reservation
is permitted. Provider HTTP status is recorded separately from the internal
broker's HTTP 502 for terminal provider errors. Safe evidence includes source
SHA, image/container identity, service version, request IDs, token usage and
latency. Ambiguous internal transport leaves call count unknown and consumes
the attempt; inspect the broker's durable claim/result files without retrying.

401 means invalid key; model 403 means project permissions; Responses 403 means
Responses permissions; 429 means quota/rate; 5xx means provider failure;
Responses 400 means minimal request contract error. Correct permissions or
request contract under separate Owner authority; never silently switch clients.

Compatibility PASS does not enable Content generation. Content integration and
a new broker-backed accounting epoch require later Owner-approved tasks.
