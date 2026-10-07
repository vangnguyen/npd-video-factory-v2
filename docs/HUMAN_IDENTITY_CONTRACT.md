# Shared human identity contract

The existing Video Factory hashed-token registry, workspace roles, principal and expiry verifier now live in `apps/api/app/human_identity.py`. This module needs only Python and the already pinned Pydantic runtime. It imports no FastAPI, database, Redis, provider SDK or GPU package. The PostgreSQL HTTP adapter reexports the original public names from `human_auth.py`; its authentication, authorization, rate-limiting and workspace lookup behavior is retained.

The `vf1` token format, hash verification, enabled/not-before/expiry checks, maximum lifetime, four human roles, workspace matching and schema stay unchanged. Service identity remains the separate Agent Hub service contract. This extraction does not issue credentials, enable privileged actions, replace approval or provide Native HTTP role enforcement by itself.

The pinned Native runtime now executes the same contract with explicit fixture credentials and no API framework/database/provider import. Exact AST comparisons prove eleven identity symbols moved unchanged and nine API adapter symbols retained unchanged. Existing API ingress tests and Native expiry/scope/import tests pass. Evidence is indexed by `docs/north-star/human-identity-evidence.json`.

The prerequisite regression at `583d9eaf445622f70ae05d52f8fc4ee3311ad284` passed all 381 Native tests and 2,085 Linux API tests with 11 skips. Native HTTP/session/UI integration is tracked separately in `NATIVE_ACCESS.md` and `north-star/native-access-evidence.json`; its fixture acceptance does not certify production identity management, browser UAT or actual Owner/provider authority. Whole platform RBAC remains PARTIAL until those deployment/identity boundaries are accepted.
