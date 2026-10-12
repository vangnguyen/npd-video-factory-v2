"""General VI/EN/auto adapter reusing strict provider-native word normalization."""
import time
from decimal import Decimal

from .assemblyai_asr_profile import ASSEMBLYAI_CREDENTIAL_ALIAS
from .assemblyai_studio_profile import (
    AssemblyAIStudioProfile, studio_profile_sha256, studio_request, studio_result_language,
)
from .assemblyai_transcription_provider import AssemblyAITranscriptionProvider, _HttpAssemblyAITransport
from .provider_safety import ProviderTimeoutEnvelope


class AssemblyAIStudioTranscriptionProvider(AssemblyAITranscriptionProvider):
    def __init__(self, *, profile, credential_resolver, transport=None, poll_interval_seconds=1.,
        provider_http_timeout_seconds=90., controller_hard_timeout_seconds=180.,
        vnd_per_minute=None, monotonic_clock=time.perf_counter):
        if type(profile) is AssemblyAIStudioProfile:
            profile = profile.model_dump(mode="python")
        self.asr_prompt_profile = AssemblyAIStudioProfile.model_validate(profile)
        self.model = self.asr_prompt_profile.model
        self.language = self.asr_prompt_profile.language
        self.credential_alias = ASSEMBLYAI_CREDENTIAL_ALIAS
        self.estimated_cost_vnd = Decimal("0")
        if vnd_per_minute is not None and (type(vnd_per_minute) is not Decimal or not vnd_per_minute.is_finite() or vnd_per_minute <= 0):
            raise ValueError("ASSEMBLYAI_COST_INVALID")
        self._vnd_per_minute = vnd_per_minute
        envelope = ProviderTimeoutEnvelope(provider_http_timeout_seconds=provider_http_timeout_seconds,
            controller_hard_timeout_seconds=controller_hard_timeout_seconds)
        self.provider_http_timeout_seconds = envelope.provider_http_timeout_seconds
        self.controller_hard_timeout_seconds = envelope.controller_hard_timeout_seconds
        self.max_file_bytes = 25_000_000
        self.max_duration_seconds = 600.
        self.response_format = "json"
        self.timestamp_granularities = ("word",)
        self._credential_resolver = credential_resolver
        self._transport = transport or _HttpAssemblyAITransport("https://api.assemblyai.com")
        self._poll_interval_seconds = poll_interval_seconds
        self._monotonic = monotonic_clock
        self._upload_started = self._job_creation_started = False
        self._transcript_id = None

    def __repr__(self):
        return "AssemblyAIStudioTranscriptionProvider(credential_alias=<redacted>)"

    def _validated_profile(self, value):
        if type(value) is AssemblyAIStudioProfile:
            value = value.model_dump(mode="python")
        profile = AssemblyAIStudioProfile.model_validate(value)
        if (self.model, self.language, self.credential_alias) != (profile.model, profile.language, ASSEMBLYAI_CREDENTIAL_ALIAS):
            raise ValueError("ASSEMBLYAI_STUDIO_CONFIGURATION_CHANGED")
        return profile

    def _profile_sha256(self, profile):
        return studio_profile_sha256(profile)

    def _transcript_request(self, profile, upload_url):
        return studio_request(profile, upload_url)

    def _result_language(self, profile, result):
        return studio_result_language(profile, result)

    def _estimated_duration_cost(self, duration):
        return None if self._vnd_per_minute is None else super()._estimated_duration_cost(duration)
