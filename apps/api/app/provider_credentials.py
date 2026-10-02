"""Sealed provider-to-credential identities used before any secret read.

This module contains public identifiers only.  It never loads credentials and
does not grant execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCredentialBinding:
    provider_key: str
    credential_alias: str
    systemd_credential_id: str


_BINDINGS = {
    "openai-transcription": ProviderCredentialBinding(
        provider_key="openai-transcription",
        credential_alias="secret://openai/codex-video",
        systemd_credential_id="openai-codex-video",
    ),
    "assemblyai-transcription": ProviderCredentialBinding(
        provider_key="assemblyai-transcription",
        credential_alias="secret://assemblyai/stt-video-factory-benchmark",
        systemd_credential_id="assemblyai-stt-video-factory-benchmark",
    ),
}


def provider_credential_binding(provider_key: str) -> ProviderCredentialBinding:
    try:
        return _BINDINGS[provider_key]
    except KeyError:
        raise ValueError("PROVIDER_CREDENTIAL_BINDING_NOT_ALLOWLISTED") from None


def verify_provider_credential_binding(
    *, provider_key: str, credential_alias: str, systemd_credential_id: str | None = None,
) -> ProviderCredentialBinding:
    binding = provider_credential_binding(provider_key)
    if credential_alias != binding.credential_alias:
        raise ValueError("PROVIDER_CREDENTIAL_ALIAS_MISMATCH")
    if systemd_credential_id is not None and systemd_credential_id != binding.systemd_credential_id:
        raise ValueError("PROVIDER_SYSTEMD_CREDENTIAL_ID_MISMATCH")
    return binding
