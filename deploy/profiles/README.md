# Isolated Video Factory deployment profiles

This is an opt-in configuration path alongside the preserved legacy Compose
files. It renders `dev`, `ci`, `production-cpu` and `production-gpu` without
starting Docker, reading workstation `.env`, downloading models, or enabling
publishing/provider execution. Production deployment still requires Owner
approval. No deployment approval is created by rendering or checking a profile.

Use the API Python environment, which already includes `jsonschema`:

```text
python deploy/profiles/profile.py --profile dev --instance local01 --api-port 41000 --studio-port 41001 --output /absolute/new-directory/dev.json
python deploy/profiles/profile.py --profile ci --instance ci01 --api-port 41100 --studio-port 41101 --output /absolute/new-directory/ci.json
python deploy/profiles/profile.py --profile production-cpu --instance cpu01 --api-port 41200 --studio-port 41201 --secrets-dir /absolute/protected-secrets --output /absolute/new-directory/cpu.json
python deploy/profiles/profile.py --profile production-gpu --instance gpu01 --api-port 41300 --studio-port 41301 --secrets-dir /absolute/protected-secrets --output /absolute/new-directory/gpu.json
```

The output parent must already exist. Creation is exclusive; existing configs
are never overwritten. Each output is Compose JSON, validated against the
official schema pinned in `compose-spec.PROVENANCE.json`. Source/schema reads
are separate from provider network operations. The vendored source is licensed
under Apache-2.0; its license is retained.

Admission accepts the compiler's complete service contract, with only the
explicit profile, instance, two distinct loopback ports and shared external
secret directory selected by the operator. Generic Compose schema validity
does not grant permission to change a service's mounts, networks, secret
consumers, build source, image, entrypoint, command, health command or execution
flags. Edited configurations are rejected before returning a command plan.
The optional bridge must retain its approved read-only workflow mount and
disabled configuration. All other persistent service mounts are the exact
profile-owned named volumes.

The renderer returns a `docker_config_argv` plan with an explicit Docker
context, project name, Compose file and an empty env file. This defeats ambient
`DOCKER_HOST`, `COMPOSE_PROJECT_NAME`, `COMPOSE_FILE` and `.env` selection when
the operator uses the returned argv. It does not invoke that command. Use a
separately approved Docker context for deployment; do not copy this plan into
the old `v2-11-deploy.sh`, which addresses the legacy stack and backup layout.

The command plan reads the actual bounded single-link configuration and empty
env files, and requires their content to match the admitted model. This check
freezes the caller's model, rereads both files and verifies their original
identities together after the final byte reads. This blocks a configuration
change while the env file is read, including a same-byte path replacement.
It is a point-in-time read; it is neither a lease over those files nor approval to
execute Docker. Keep the reviewed files unchanged before a separately approved
execution.

Every instance/profile gets different Compose-owned containers, networks,
PostgreSQL database, Redis server/AOF volume, S3 bucket and persistent volumes.
No external network/volume or fixed container name is used. Explicit host
ports expose only API and Studio on loopback; the operator must choose unused
ports. The front network does not expose PostgreSQL/Redis/MinIO to Studio, and
renderer traffic uses a separate private network. Schema/graph validation is
configuration evidence, not proof of live firewall enforcement. These rules
follow the [official Compose network model](https://docs.docker.com/reference/compose-file/networks/).

The API waits for the database migration, private object-store initialization,
Redis and renderer health. Studio waits for API readiness. The optional bridge
is never a dependency of CPU services. `production-gpu` adds the existing
ComfyUI bridge on the render network; its backend remains disabled and GPU
inference is `NOT_CONFIGURED`. No GPU server, NVIDIA device, model or arbitrary
workflow graph is installed or enabled here. A failed bridge cannot change
the CPU dependency graph or the API's existing readiness dependencies.

Production expects externally protected files:

| File | Mounted consumers |
| --- | --- |
| `database-password` | PostgreSQL, API, worker, migration |
| `redis-password` | Redis, API, worker |
| `object-access-key` and `object-secret-key` | MinIO, API, worker, storage initialization |
| `human-auth.json` | API only; existing hash-only human registry format |

The files are not generated or read by the Compose renderer; production secret
references must be outside the source checkout and contain no Compose variable
interpolation. API/worker run as
UID/GID 10001; provision readable file ownership/ACLs outside Git before a
deployment. Compose file secrets are read-only bind mounts; this path does not
claim encryption at rest or that Compose enforces requested UID/mode for file
secrets. Use the approved external secret system/host protection. Service grants
follow [Compose secrets](https://docs.docker.com/reference/compose-file/secrets/).

The bootstrap bounds secret files, rejects links and known example passwords,
checks identity/size/mtime during the read, URL-escapes the PostgreSQL password,
and emits only finite errors. Redis passwords require 32–128 ASCII letters,
digits, `_` or `-` to prevent configuration injection. The Redis password is
written into a private temporary configuration, not a command argument.
The [official PostgreSQL entrypoint](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh)
and [MinIO secret-file interface](https://github.com/minio/minio/blob/master/docs/docker/README.md)
provide file-based credentials. Compatibility of the existing pinned MinIO
image with this interface still needs a real Docker acceptance run.

`runtime.py --check` validates bounded bootstrap and actual API/worker Settings
inside the invoking process. It performs no connections, migration, worker
startup, provider inference, renderer or model loading. Application enablement
and credential variables from the parent are discarded; no caller environment
is modified. CI/dev synthetic fixtures remain explicitly synthetic. Production
fixtures, human writes, local model enablement, external/paid operations, Agent
Hub delivery and publishing all remain disabled. There are no real provider
credentials in this profile path.

The `storage-init` container is an explicit bounded one-shot that creates only
the profile's private bucket, after MinIO health. It is not called by `--check`
or the renderer. Migration and this infrastructure initialization execute only
when an operator performs the separately approved deployment.

`backup-data` is a separate scoped destination for future approved backup
execution; no backup/restore service or schedule is advertised. Existing
database/projects/assets restoration evidence remains separate. Worker consumer
heartbeat, real image build, migration graph, PostgreSQL/Redis/S3 behavior,
container vulnerability scan, live secret ACLs, network enforcement, soak and
production recovery remain `NOT_VERIFIED` or incomplete. Docker was unavailable
on the authoring host. Passing offline tests does not close Wave 15, production
hardening, GPU/provider acceptance or Owner UAT.

Run the bounded offline tests using a fresh short temporary root:

```text
python -m pytest -q -c apps/api/pyproject.toml --basetemp /absolute/new-temporary-root deploy/profiles/tests
```
