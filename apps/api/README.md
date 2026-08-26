# NPD Video Factory V2 API

V2-03 exposes strict workspace/project/version, durable video-job, audit, asset, provider,
VND cost, trend, evidence, idea and opportunity-queue endpoints. PostgreSQL is canonical;
Redis is queue-only and object bytes use the configured local or S3-compatible provider. See
`docs/API.md` at the repository root. It owns no AgentHub integration and contains no publishing
endpoint.
