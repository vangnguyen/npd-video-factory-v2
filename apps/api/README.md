# NPD Video Factory V2 API

V2-02 exposes strict workspace/project/version, durable video-job, audit, asset, provider
and VND cost endpoints. PostgreSQL is canonical; Redis is queue-only and object bytes use
the configured local or S3-compatible provider. See `docs/API.md` at the repository root.
It owns no AgentHub integration and contains no publishing endpoint.
