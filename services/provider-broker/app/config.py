from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

SERVICE = "npd-provider-broker"
VERSION = "0.1.0"
MODEL = "gpt-6-luna"
ORIGIN = "https://api.openai.com/v1"


@dataclass(frozen=True, repr=False)
class Config:
    bind_host: str = "127.0.0.1"
    bind_port: int = 18084
    api_key_file: Path = Path("/run/secrets/openai_api_key")
    token_file: Path = Path("/run/secrets/broker_token")
    claims_dir: Path = Path("/var/lib/npd-provider-broker/canary-claims")
    source_head: str = "UNQUALIFIED"
    timeout_seconds: float = 30
    max_body_bytes: int = 1024

    def valid(self):
        return (self.bind_host == "127.0.0.1" and self.bind_port == 18084
            and bool(re.fullmatch(r"[a-f0-9]{40}", self.source_head))
            and 0 < self.timeout_seconds <= 90 and 0 < self.max_body_bytes <= 4096
            and all(p.is_absolute() for p in (self.api_key_file, self.token_file, self.claims_dir)))

    @classmethod
    def runtime(cls):
        # Only public image/source identity is environmental configuration.
        return cls(source_head=os.environ.get("BROKER_SOURCE_HEAD", "UNQUALIFIED"))


def cloud_credential_context_present():
    # Presence only; never read the Network Secret or use it as a key.
    return "NPD_VF_CONTENT_API_KEY" in os.environ or "CODEX_PROXY_CERT" in os.environ
