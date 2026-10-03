"""Public metadata-only validation of resolver systemd credential mounts.

Never reads encrypted/plaintext credential bytes, starts services or resolves
a secret. Source PASS does not attest the installed unit or actual host load.
"""
from __future__ import annotations

from .provider_credentials import verify_provider_credential_binding


def effective_encrypted_mounts(unit_text: str, dropins: tuple[str, ...] = ()) -> dict[str, str]:
    mounts: dict[str, str] = {}
    for text in (unit_text, *dropins):
        section = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("["):
                section = line
                continue
            directive, separator, value = line.partition("=")
            directive, value = directive.strip(), value.strip()
            if section == "[Service]" and separator and directive == "LoadCredentialEncrypted":
                if not value:
                    mounts.clear()
                    continue
                if ":" not in value or any(ch in value for ch in (" ", "%", "$", "\\", "*")):
                    raise ValueError("CREDENTIAL_MOUNT_FORMAT_INVALID")
                credential_id, source = value.split(":", 1)
                if credential_id in mounts:
                    raise ValueError("CREDENTIAL_MOUNT_DUPLICATE_ID")
                mounts[credential_id] = source
            elif section == "[Service]" and separator and directive in {"LoadCredential", "SetCredential", "SetCredentialEncrypted"}:
                raise ValueError("UNAPPROVED_CREDENTIAL_DIRECTIVE")
    return mounts


def validate_provider_systemd_mount(*, provider_key: str, credential_alias: str,
                                   unit_text: str, dropins: tuple[str, ...] = ()) -> dict:
    binding = verify_provider_credential_binding(provider_key=provider_key, credential_alias=credential_alias)
    mounts = effective_encrypted_mounts(unit_text, dropins)
    source = "/etc/credstore.encrypted/" + binding.systemd_credential_id
    if mounts != {binding.systemd_credential_id: source}:
        raise ValueError("PROVIDER_SYSTEMD_CREDENTIAL_MOUNT_MISMATCH")
    return {"provider_key": provider_key, "credential_alias": credential_alias,
        "systemd_credential_id": binding.systemd_credential_id, "encrypted_source": source,
        "verdict": "SOURCE_MAPPING_PASS", "credential_bytes_read": False,
        "live_load_validation": "NOT_RUN", "execution_authority": False}
