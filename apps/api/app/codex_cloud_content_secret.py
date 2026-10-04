"""Trusted Content-only Codex Cloud Network Secret composition.

The environment value is an opaque proxy placeholder, never a local API key.
Only the platform HTTPS proxy can substitute it at api.openai.com. This module
does not select credentials from Settings, request bodies or provider output.
"""
from __future__ import annotations

import os

from .mvp1_provider_admission import Mvp1AdmissionScope, ProtectedResolverReference, digest

BACKEND_ID = "codex-cloud-network-secret-content-v1"
CONTENT_ALIAS = "secret://openai/video-factory-content-generation"
NETWORK_SECRET_VARIABLE = "NPD_VF_CONTENT_API_KEY"
CONTENT_PROVIDER = "openai-storyboard-content"
HTTPS_HOST = "api.openai.com"


class CodexCloudContentSecretTransport:
    """Fixed, scope-bound placeholder handoff. No selectable mapping or fallback."""
    backend_id = BACKEND_ID
    logical_alias = CONTENT_ALIAS
    network_secret_variable = NETWORK_SECRET_VARIABLE
    provider_key = CONTENT_PROVIDER
    https_host = HTTPS_HOST

    def __init__(self, scope: Mvp1AdmissionScope, *, raw_file_sha256: str):
        scope = Mvp1AdmissionScope.model_validate(scope.model_dump())
        if (scope.capability, scope.provider_key, scope.credential_alias) != (
                "content_generation", CONTENT_PROVIDER, CONTENT_ALIAS):
            raise ValueError("CONTENT_CLOUD_MAPPING_REJECTED")
        if len(raw_file_sha256) != 64 or any(c not in "0123456789abcdef" for c in raw_file_sha256):
            raise ValueError("CONTENT_CLOUD_SCOPE_PIN_REQUIRED")
        self._scope, self._raw_file_sha256 = scope, raw_file_sha256

    def readiness(self):
        # Exactly a presence/non-empty check. No stripping, key shape, hash,
        # logging, SDK initialization, network probe or real-secret validation.
        available = NETWORK_SECRET_VARIABLE in os.environ and os.environ[NETWORK_SECRET_VARIABLE] != ""
        return {"backend_id": BACKEND_ID, "logical_alias": CONTENT_ALIAS,
            "network_secret_variable": NETWORK_SECRET_VARIABLE,
            "provider_key": CONTENT_PROVIDER, "https_host": HTTPS_HOST,
            "logical_mapping": "FIXED_CONTENT_MAPPING",
            "credential_delivery": "PLACEHOLDER_AVAILABLE" if available else "PLACEHOLDER_UNAVAILABLE",
            "raw_secret": "RAW_SECRET_INTENTIONALLY_UNAVAILABLE"}

    def __call__(self, reference):
        # Validate only PUBLIC reference metadata; never inspect the value.
        expected = {"schema": "mvp1-protected-resolver-reference-v1",
            "provider_key": CONTENT_PROVIDER, "credential_alias": CONTENT_ALIAS,
            "scope_sha256": digest(self._scope.model_dump(mode="json")),
            "scope_raw_file_sha256": self._raw_file_sha256,
            "workspace_id": self._scope.workspace_id, "project_id": self._scope.project_id,
            "profile_sha256": self._scope.profile_sha256, "max_resolutions": 1}
        if not isinstance(reference, dict) or set(reference) != set(expected) | {
                "operation_key", "job_id", "input_sha256"}:
            raise RuntimeError("CONTENT_CLOUD_REFERENCE_REJECTED")
        if any(reference[k] != v for k, v in expected.items()):
            raise RuntimeError("CONTENT_CLOUD_REFERENCE_REJECTED")
        item = self._scope.operation_for(reference["operation_key"])
        if item is None or reference["input_sha256"] != item.asset_hash or not reference["job_id"]:
            raise RuntimeError("CONTENT_CLOUD_REFERENCE_REJECTED")
        if self.readiness()["credential_delivery"] != "PLACEHOLDER_AVAILABLE":
            raise RuntimeError("CONTENT_CLOUD_PLACEHOLDER_UNAVAILABLE")
        return self._placeholder_handoff()

    def _placeholder_handoff(self):
        # One unchanged opaque handoff for both GET auth and POST Content paths.
        return os.environ[NETWORK_SECRET_VARIABLE]  # Unchanged, never persisted.

    def resolve_for_auth_probe(self, reference):
        from .codex_cloud_content_http import ContentAuthProbeApproval
        if (not isinstance(reference, dict) or set(reference) != {
                "schema", "approval", "scope_sha256", "scope_raw_file_sha256"}
                or reference["schema"] != "codex-cloud-content-auth-probe-binding-v1"
                or reference["scope_sha256"] != digest(self._scope.model_dump(mode="json"))
                or reference["scope_raw_file_sha256"] != self._raw_file_sha256):
            raise RuntimeError("CONTENT_CLOUD_REFERENCE_REJECTED")
        approval = ContentAuthProbeApproval.model_validate(reference["approval"])
        approval.validate_binding(self._scope, self._raw_file_sha256)
        if self.readiness()["credential_delivery"] != "PLACEHOLDER_AVAILABLE":
            raise RuntimeError("CONTENT_CLOUD_PLACEHOLDER_UNAVAILABLE")
        return self._placeholder_handoff()

    def resolve_for_responses_canary(self, reference):
        from .codex_cloud_content_http import ContentResponsesCanaryApproval
        if (not isinstance(reference, dict) or set(reference) != {
                "schema", "approval", "scope_sha256", "scope_raw_file_sha256"}
                or reference["schema"] != "codex-cloud-content-responses-canary-binding-v1"
                or reference["scope_sha256"] != digest(self._scope.model_dump(mode="json"))
                or reference["scope_raw_file_sha256"] != self._raw_file_sha256):
            raise RuntimeError("CONTENT_CLOUD_REFERENCE_REJECTED")
        approval = ContentResponsesCanaryApproval.model_validate(reference["approval"])
        approval.validate_binding(self._scope, self._raw_file_sha256)
        if self.readiness()["credential_delivery"] != "PLACEHOLDER_AVAILABLE":
            raise RuntimeError("CONTENT_CLOUD_PLACEHOLDER_UNAVAILABLE")
        return self._placeholder_handoff()


def uses_codex_cloud_content_proxy(resolver):
    return (isinstance(resolver, ProtectedResolverReference)
        and type(resolver.transport) is CodexCloudContentSecretTransport)


def compose_disabled_content_cloud_candidate(scope, *, raw_file_sha256, repository):
    """Explicit trusted source entrypoint; default API/worker never call it.

    This source task installs only a DISABLED candidate. Live runtime composition,
    host custody and execution approval are separate from placeholder delivery.
    No settings/env switch or HTTP API can select this composition.
    """
    from .provider_safety import ProviderSafetyPolicy, ProviderBudgetPolicy, ProviderRetryPolicy
    from .provider_safety_durable import DurableProviderSafetyController
    from .storyboard_content_provider import ContentProviderProfile, ResponsesStoryboardContentProvider
    scope = Mvp1AdmissionScope.model_validate(scope.model_dump())
    if scope.execution_authorized:
        raise ValueError("CONTENT_CLOUD_DISABLED_CANDIDATE_REQUIRED")
    backend = CodexCloudContentSecretTransport(scope, raw_file_sha256=raw_file_sha256)
    policy = ProviderSafetyPolicy(execution_gate=scope, verified_gate_required=True,
        external_execution_enabled=False, paid_execution_enabled=False,
        global_kill_switch_engaged=True, credential_gate_approved=True, rights_gate_approved=True,
        budget=ProviderBudgetPolicy(approved=False, owner_approval_id=scope.owner_approval_id,
            per_operation_limit_vnd=scope.per_operation_limit_vnd,
            daily_limit_vnd=scope.acceptance_window_limit_vnd, expires_at=scope.expires_at_utc),
        retry=ProviderRetryPolicy(max_attempts=1, max_concurrent_calls=1))
    controller = DurableProviderSafetyController(policy, repository=repository)
    resolver = ProtectedResolverReference(scope, transport=backend, raw_file_sha256=raw_file_sha256)
    return ResponsesStoryboardContentProvider(ContentProviderProfile.model_validate(scope.profile),
        controller=controller, credential_resolver=resolver)
