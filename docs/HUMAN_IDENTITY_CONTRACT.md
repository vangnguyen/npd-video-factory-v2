# Shared human identity contract

The existing Video Factory hashed-token registry, workspace roles, principal and expiry verifier now live in `apps/api/app/human_identity.py`. This module needs only Python and the already pinned Pydantic runtime. It imports no FastAPI, database, Redis, provider SDK or GPU package. The PostgreSQL HTTP adapter reexports the original public names from `human_auth.py`; its authentication, authorization, rate-limiting and workspace lookup behavior is retained.

The `vf1` token format, hash verification, enabled/not-before/expiry checks, maximum lifetime, four human roles, workspace matching and schema stay unchanged. Service identity remains the separate Agent Hub service contract. This extraction does not issue credentials, enable privileged actions, replace approval or provide Native HTTP role enforcement by itself.

The pinned Native runtime now executes the same contract with explicit fixture credentials and no API framework/database/provider import. Exact AST comparisons prove eleven identity symbols moved unchanged and nine API adapter symbols retained unchanged. Existing API ingress tests and Native expiry/scope/import tests pass. Evidence is indexed by `docs/north-star/human-identity-evidence.json`.

Next integration must bind an operator-configured registry to a Native workspace, authenticate per-user sessions, authorize every route before body processing/dispatch, preserve session/CSRF and Owner/provider gates, and provide Studio login/permission behavior. Until that runs with evidence, Native RBAC remains PARTIAL and `NATIVE_RBAC_READY = NO`.
