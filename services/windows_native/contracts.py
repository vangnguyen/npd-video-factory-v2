from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL = "gpt-6-luna"
PROFILE_SHA = "f2d848766784e7bd892680f933a799ec812c1c8acff62b019ac777aa1292c4d3"
RUNTIME_VERSIONS = {"vieneu": "3.8.3", "onnxruntime": "1.30.0", "numpy": "2.5.3", "sea-g2p": "0.9.1"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(canonical(value))
    temp.replace(path)


def normalize(text):
    return " ".join(text.split())


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene: int = Field(ge=1, le=5)
    visual: str = Field(min_length=1, max_length=1200)
    on_screen_text: str = Field(min_length=1, max_length=150)
    narration_excerpt: str = Field(min_length=1, max_length=1500)


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narration: str = Field(min_length=1, max_length=4000)
    visual_brief: list[Scene] = Field(min_length=1, max_length=5)
    facts_needing_source: list[str] = Field(max_length=40)

    @model_validator(mode="after")
    def exact_coverage(self):
        if [s.scene for s in self.visual_brief] != list(range(1, len(self.visual_brief) + 1)):
            raise ValueError("Scene order invalid")
        if normalize(" ".join(s.narration_excerpt for s in self.visual_brief)) != normalize(self.narration):
            raise ValueError("Scene excerpts must cover the narration exactly")
        if any(len(f) > 2000 for f in self.facts_needing_source):
            raise ValueError("Source note too long")
        return self


class WorkflowError(Exception):
    def __init__(self, code, status=409, *, http_status=None):
        self.code, self.status, self.http_status = code, status, http_status
        super().__init__(code)
