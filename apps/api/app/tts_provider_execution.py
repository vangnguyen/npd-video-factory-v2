"""Production TTS admission on the existing durable controller, not global flags alone.

Approved unit contexts are supplied by the capability-specific public loader.
Construction/readiness never resolve a credential or perform durable preflight.
"""
from __future__ import annotations

import hashlib

from .content_service import canonical_bytes
from .provider_safety import ProviderCallContext
from .providers import OpenAIVietnameseTTSProvider, TTSNotConfiguredError
from .storyboard_content_provider import ProviderEnablementError
from .tts_evidence import ProductionTTSProfile


TTS_KEY = "openai-tts"
TTS_ALIAS = "secret://openai/video-factory-vietnamese-tts"


def narration_input_sha256(profile: ProductionTTSProfile, text: str) -> str:
    return hashlib.sha256(canonical_bytes({"profile_sha256": profile.sha256,
        "narration": text, "language": "vi"})).hexdigest()


class GovernedVietnameseTTSProvider:
    def __init__(self, profile: ProductionTTSProfile, *, controller, credential_resolver,
                 approved_units: dict[str, ProviderCallContext], transport=None):
        if profile.provider_key != TTS_KEY or profile.alignment_capability != "none":
            raise TTSNotConfiguredError("TTS_PROFILE_UNSUPPORTED_BY_WAV_ADAPTER")
        self.profile, self.model, self.voice = profile, profile.model, profile.voice_id
        self.controller, self.credential_resolver = controller, credential_resolver
        self.approved_units, self.transport = dict(approved_units), transport
        self.before_unit = None

    def bind_render_scope(self, *, workspace_id, project_id, content_version_id, render_id, before_unit):
        bound = {}
        for digest, context in self.approved_units.items():
            if (context.workspace_id, context.project_id, context.asset_id) != (workspace_id, project_id, content_version_id):
                raise TTSNotConfiguredError("TTS_RENDER_VERSION_SCOPE_MISMATCH")
            bound[digest] = context.model_copy(update={"job_id": render_id})
        clone = type(self)(self.profile, controller=self.controller, credential_resolver=self.credential_resolver,
            approved_units=bound, transport=self.transport)
        clone.before_unit = before_unit
        return clone

    def prepare_zero_call(self, *, text, language="vi"):
        from datetime import datetime, timezone
        from .mvp1_provider_admission import Mvp1AdmissionScope
        digest = narration_input_sha256(self.profile, text)
        context = self.approved_units.get(digest)
        scope = self.controller.policy.execution_gate if self.controller else None
        if language != "vi" or context is None or not isinstance(scope, Mvp1AdmissionScope) or scope.profile_sha256 != self.profile.sha256:
            raise TTSNotConfiguredError("TTS_INPUT_PROFILE_ADMISSION_REQUIRED")
        denial = scope.denial_for(context, datetime.now(timezone.utc), require_execution=False)
        if denial: raise TTSNotConfiguredError(denial)
        return {"status": "PUBLIC_ADMISSION_PASS_NOT_LIVE_AUTHORITY", "input_sha256": digest,
            "profile_sha256": self.profile.sha256, "provider_call_performed": False, "credential_read_performed": False,
            "budget_reserved_vnd": 0, "alignment_source": "NONE", "word_alignment": "WORD_ALIGNMENT_OPEN",
            "full_preflight": "NOT_RUN"}

    def readiness(self):
        if self.controller is None or self.credential_resolver is None or not self.approved_units:
            return "TTS_AUTHORITY_REQUIRED"
        if getattr(self.credential_resolver, "backend_admitted", True) is False:
            return "TTS_AUTHORITY_REQUIRED"
        policy = self.controller.policy
        scope = policy.execution_gate
        from .mvp1_provider_admission import Mvp1AdmissionScope
        if isinstance(scope, Mvp1AdmissionScope) and scope.profile_sha256 != self.profile.sha256:
            return "TTS_AUTHORITY_REQUIRED"
        if (not policy.verified_gate_required or scope is None
                or (scope.provider_key, scope.model, scope.capability, scope.credential_alias)
                    != (TTS_KEY, self.model, "tts", TTS_ALIAS)
                or policy.retry.max_attempts != 1 or policy.retry.max_concurrent_calls != 1
                or policy.global_kill_switch_engaged or not policy.external_execution_enabled
                or not policy.paid_execution_enabled):
            return "TTS_AUTHORITY_REQUIRED"
        return "CONFIG_AND_SCOPE_PRESENT"

    async def synthesize(self, *, text, language, output_path):
        if self.before_unit is not None:
            await self.before_unit()  # Cancellation/edit between narration units wins.
        if language != "vi" or self.readiness() != "CONFIG_AND_SCOPE_PRESENT":
            raise TTSNotConfiguredError("TTS_AUTHORITY_REQUIRED")
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > 4096:
            raise TTSNotConfiguredError("TTS_NARRATION_INPUT_INVALID")
        if output_path.is_symlink() or output_path.with_suffix(output_path.suffix+".tmp").is_symlink():
            raise TTSNotConfiguredError("TTS_OUTPUT_SYMLINK_REJECTED")
        digest = narration_input_sha256(self.profile, text)
        context = self.approved_units.get(digest)
        if context is None:
            raise TTSNotConfiguredError("TTS_NARRATION_PROFILE_INPUT_NOT_AUTHORIZED")
        # Revalidate rather than trusting a model_copy()/caller-selected alias.
        context = ProviderCallContext.model_validate(context.model_dump())
        if ((context.provider_key, context.model, context.capability, context.credential_alias)
                != (TTS_KEY, self.model, "tts", TTS_ALIAS)
                or context.asset_hash != digest or context.input_media_kind != "document"
                or not context.asset_id or not context.job_id or not context.project_id
                or not context.rights_required or not context.external_call or not context.paid
                or context.estimated_cost_vnd is None or context.estimated_cost_vnd <= 0):
            raise TTSNotConfiguredError("TTS_UNIT_BINDING_MISMATCH")

        async def call():
            # Only inside durable execute(): rights/window/idempotency/budget
            # admission precedes credential handoff. No automatic retry/fallback.
            try:
                from .mvp1_provider_admission import ProtectedResolverReference
                key = (self.credential_resolver.resolve_for_context(context)
                    if isinstance(self.credential_resolver, ProtectedResolverReference) else self.credential_resolver(TTS_ALIAS))
            except Exception:
                raise ProviderEnablementError("AUTH", "TTS_CREDENTIAL_UNAVAILABLE") from None
            if not isinstance(key, str) or not key.strip():
                raise ProviderEnablementError("AUTH", "TTS_CREDENTIAL_UNAVAILABLE")
            provider = OpenAIVietnameseTTSProvider(api_key=key, model=self.model,
                voice=self.voice, instructions=self.profile.style_instructions,
                speed=self.profile.speed, transport=self.transport)
            return await provider.synthesize(text=text, language=language, output_path=output_path)

        result = await self.controller.execute(context, call)
        return result.value
