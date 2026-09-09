"""Immutable, offline-verified W1 request profile; this module grants no authority.

The ordinary-text counter uses pinned Whisper ranks and its upstream regex, not
a model, hosted tokenizer observation, or a network-backed encoding registry.
The upstream context count is distinct from the exact prompt sent in the request.
"""

from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import tiktoken
from pydantic import BaseModel, ConfigDict, StrictInt, model_validator


W1_PROFILE_ID = "asr-whisper-vi-w1-v1"
W1_PROMPT = (
    "Ngọc Phương Đông, Vinhomes Green Paradise, Cần Giờ, "
    "tham quan sa bàn, chính sách bán hàng."
)
W1_PROMPT_SHA256 = "6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48"
W1_CONTEXT_SHA256 = "7cf8e972dc834af0022b139a1ba123bcefe6fea34f9d8112fc9eee074c5ad035"
TOKENIZER_ID = "openai-whisper-multilingual-ordinary-text-v1"
TOKENIZER_VERSION = "0.12.0"
TOKENIZER_UPSTREAM_COMMIT = "86098128c0b4f24f0e2aa2994de830614b474227"
TOKENIZER_RANKS_SHA256 = "b34b360dbb493e781e479794586d661700670d65564001f23024971d1f2fa126"
TOKENIZER_RANKS_BYTES = 816730
TOKENIZER_RANKS_COUNT = 50257
WHISPER_PROMPT_LIMIT_TOKENS = 224
_RANKS_PATH = Path(__file__).parent / "data" / "whisper" / "multilingual.tiktoken"
_WHISPER_PATTERN = (
    r"'s|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"
)


def _expected_payload() -> dict[str, Any]:
    # A fresh object prevents a caller from changing the allowlist by mutation.
    return {
        "profile_id": W1_PROFILE_ID,
        "prompt": W1_PROMPT,
        "prompt_sha256": W1_PROMPT_SHA256,
        "prompt_utf8_bytes": 105,
        "model": "whisper-1",
        "language": "vi",
        "response_format": "verbose_json",
        "timestamp_granularities": ("segment", "word"),
        "temperature_policy": "omitted",
        "tokenizer_id": TOKENIZER_ID,
        "tokenizer_version": TOKENIZER_VERSION,
        "tokenizer_upstream_commit": TOKENIZER_UPSTREAM_COMMIT,
        "tokenizer_ranks_sha256": TOKENIZER_RANKS_SHA256,
        "tokenizer_raw_token_count": 34,
        "tokenizer_context_token_count": 33,
        "tokenizer_context_policy": "prepend_space_after_strip",
        "tokenizer_context_sha256": W1_CONTEXT_SHA256,
    }


@lru_cache(maxsize=1)
def _encoding_from_verified_bytes(raw: bytes) -> tiktoken.Encoding:
    """Cache only an encoder constructed from hash-verified immutable bytes."""
    if len(raw) != TOKENIZER_RANKS_BYTES or hashlib.sha256(raw).hexdigest() != TOKENIZER_RANKS_SHA256:
        raise ValueError("ASR_PROMPT_TOKENIZER_ARTIFACT_INVALID")
    try:
        ranks: dict[bytes, int] = {}
        for line in raw.splitlines():
            encoded, rank_text = line.split()
            # The pinned upstream artifact has exactly one empty-token sentinel,
            # encoded as '=' at rank 50256. Match it explicitly, not permissive
            # base64 decoding of arbitrary malformed records.
            token = b"" if encoded == b"=" and rank_text == b"50256" else base64.b64decode(encoded, validate=True)
            rank = int(rank_text)
            if (not token and rank != 50256) or token in ranks:
                raise ValueError("duplicate or unexpected empty token")
            ranks[token] = rank
        if (
            len(ranks) != TOKENIZER_RANKS_COUNT
            or set(ranks.values()) != set(range(TOKENIZER_RANKS_COUNT))
            or any(bytes([value]) not in ranks for value in range(256))
        ):
            raise ValueError("invalid vocabulary coverage")
    except (ValueError, TypeError) as exc:
        raise ValueError("ASR_PROMPT_TOKENIZER_ARTIFACT_INVALID") from exc
    # No get_encoding/encoding_for_model/cache URL or model load is used. W1
    # contains ordinary text only; the complete control-token stream is NOT counted.
    return tiktoken.Encoding(
        name=TOKENIZER_ID,
        pat_str=_WHISPER_PATTERN,
        mergeable_ranks=ranks,
        special_tokens={},
        explicit_n_vocab=TOKENIZER_RANKS_COUNT,
    )


def _verified_encoding() -> tiktoken.Encoding:
    if tiktoken.__version__ != TOKENIZER_VERSION:
        raise ValueError("ASR_PROMPT_TOKENIZER_VERSION_INVALID")
    try:
        raw = _RANKS_PATH.read_bytes()
    except OSError as exc:
        raise ValueError("ASR_PROMPT_TOKENIZER_ARTIFACT_UNAVAILABLE") from exc
    # Check on every use, even if the immutable encoder is already cached: replacing
    # or removing the packaged artifact must not silently reuse an old cached one.
    if len(raw) != TOKENIZER_RANKS_BYTES or hashlib.sha256(raw).hexdigest() != TOKENIZER_RANKS_SHA256:
        raise ValueError("ASR_PROMPT_TOKENIZER_ARTIFACT_INVALID")
    return _encoding_from_verified_bytes(raw)


def _verify_w1_tokenization() -> None:
    raw = W1_PROMPT.encode("utf-8")
    context = " " + W1_PROMPT.strip()
    if len(raw) != 105 or hashlib.sha256(raw).hexdigest() != W1_PROMPT_SHA256:
        raise ValueError("ASR_PROMPT_FIXED_TEXT_INVALID")
    if hashlib.sha256(context.encode("utf-8")).hexdigest() != W1_CONTEXT_SHA256:
        raise ValueError("ASR_PROMPT_CONTEXT_TEXT_INVALID")
    encoding = _verified_encoding()
    raw_ids = encoding.encode_ordinary(W1_PROMPT)
    context_ids = encoding.encode_ordinary(context)
    if (
        len(raw_ids) != 34
        or len(context_ids) != 33
        or max(len(raw_ids), len(context_ids)) > WHISPER_PROMPT_LIMIT_TOKENS
        or encoding.decode_bytes(raw_ids) != raw
        or encoding.decode_bytes(context_ids) != context.encode("utf-8")
    ):
        raise ValueError("ASR_PROMPT_TOKENIZATION_INVALID")


class AsrPromptProfile(BaseModel):
    """One allowlisted request profile, never a budget or execution approval."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always"
    )

    profile_id: Literal["asr-whisper-vi-w1-v1"]
    prompt: str
    prompt_sha256: str
    prompt_utf8_bytes: StrictInt
    model: Literal["whisper-1"]
    language: Literal["vi"]
    response_format: Literal["verbose_json"]
    timestamp_granularities: tuple[Literal["segment"], Literal["word"]]
    temperature_policy: Literal["omitted"]
    tokenizer_id: Literal["openai-whisper-multilingual-ordinary-text-v1"]
    tokenizer_version: Literal["0.12.0"]
    tokenizer_upstream_commit: str
    tokenizer_ranks_sha256: str
    tokenizer_raw_token_count: StrictInt
    tokenizer_context_token_count: StrictInt
    tokenizer_context_policy: Literal["prepend_space_after_strip"]
    tokenizer_context_sha256: str

    @model_validator(mode="before")
    @classmethod
    def _exact_profile(cls, value: Any) -> dict[str, Any]:
        if type(value) is not dict:
            raise ValueError("ASR_PROMPT_PROFILE_OBJECT_REQUIRED")
        expected = _expected_payload()
        if set(value) != set(expected):
            raise ValueError("ASR_PROMPT_PROFILE_FIELDS_INVALID")
        payload = value.copy()
        for key, wanted in expected.items():
            supplied = payload[key]
            if key == "timestamp_granularities":
                # JSON arrays and the immutable model's tuple are the two explicit
                # representations; sets, generators and coercions are not accepted.
                if type(supplied) not in (list, tuple) or any(type(item) is not str for item in supplied):
                    raise ValueError("ASR_PROMPT_PROFILE_FIELD_TYPE_INVALID")
                supplied = tuple(supplied)
                payload[key] = supplied
            elif type(supplied) is not type(wanted):
                raise ValueError("ASR_PROMPT_PROFILE_FIELD_TYPE_INVALID")
            if supplied != wanted:
                raise ValueError("ASR_PROMPT_PROFILE_NOT_ALLOWLISTED")
        _verify_w1_tokenization()
        return payload


def validate_prompt_profile(value: AsrPromptProfile | dict[str, Any] | None) -> AsrPromptProfile | None:
    """Always reconstruct: model_copy/model_construct are not validation bypasses."""
    if value is None:
        return None
    if type(value) is AsrPromptProfile:
        payload = dict(object.__getattribute__(value, "__dict__"))
        extra = object.__getattribute__(value, "__pydantic_extra__")
        if extra:
            raise ValueError("ASR_PROMPT_PROFILE_FIELDS_INVALID")
    elif type(value) is dict:
        payload = value.copy()
    else:
        raise ValueError("ASR_PROMPT_PROFILE_OBJECT_REQUIRED")
    return AsrPromptProfile.model_validate(payload)


def w1_prompt_profile() -> AsrPromptProfile:
    return AsrPromptProfile.model_validate(_expected_payload())


def profile_for_id(profile_id: str | None) -> AsrPromptProfile | None:
    if profile_id is None:
        return None
    if type(profile_id) is not str:
        raise ValueError("ASR_PROMPT_PROFILE_ID_INVALID")
    if profile_id == "":
        return None
    if profile_id != W1_PROFILE_ID:
        raise ValueError("ASR_PROMPT_PROFILE_ID_NOT_ALLOWLISTED")
    return w1_prompt_profile()


def prompt_profile_sha256(value: AsrPromptProfile | dict[str, Any] | None) -> str | None:
    profile = validate_prompt_profile(value)
    if profile is None:
        return None
    canonical = json.dumps(
        profile.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
