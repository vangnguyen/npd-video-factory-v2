# NPD Video Factory V2 API

V2-04 exposes strict workspace/project/version, durable video-job, audit, asset, provider,
VND cost, trend/idea, resumable upload and non-destructive Auto Edit analysis endpoints. PostgreSQL is canonical;
Redis is queue-only and object bytes use the configured local or S3-compatible provider. See
`docs/API.md` at the repository root. It owns no AgentHub integration and contains no publishing
endpoint.
