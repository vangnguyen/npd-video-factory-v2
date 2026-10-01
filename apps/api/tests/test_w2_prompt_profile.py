"""Offline W2 identity and fail-closed registry tests; no provider boundary."""

from __future__ import annotations

import hashlib
import unicodedata

import pytest

import app.asr_prompt_profile as profiles
from app.asr_prompt_profile import (
    W1_PROFILE_ID,
    W2_CONTEXT_SHA256,
    W2_PROFILE_ID,
    W2_PROMPT,
    W2_PROMPT_SHA256,
    profile_for_id,
    prompt_profile_sha256,
    validate_prompt_profile,
    w1_prompt_profile,
    w2_prompt_profile,
)


W2_RAW_IDS = [
    51, 4228, 371, 43975, 272, 12436, 46880, 262, 31926, 11990, 21198,
    12935, 66, 2623, 24605, 13055, 8217, 25, 691, 10085, 18168, 6969,
    35053, 37773, 383, 18241, 15334, 21270, 11, 258, 335, 19068, 601,
    272, 22476, 10274, 42178, 262, 39569, 272, 7200, 48373, 13,
]
W2_CONTEXT_IDS = [314, *W2_RAW_IDS[1:]]
W2_PROFILE_SHA256 = "ff2063a761247b5d59edbefd2c155c00dff917177fd03f8851805b8ff9d01446"


def test_w2_exact_bytes_hash_counts_context_and_golden_tokens():
    profile = w2_prompt_profile()
    context = " " + W2_PROMPT.strip()
    encoding = profiles._verified_encoding()
    assert profile.profile_id == W2_PROFILE_ID
    assert profile.prompt == W2_PROMPT
    assert len(W2_PROMPT.encode("utf-8")) == profile.prompt_utf8_bytes == 149
    assert hashlib.sha256(W2_PROMPT.encode("utf-8")).hexdigest() == W2_PROMPT_SHA256
    assert hashlib.sha256(context.encode("utf-8")).hexdigest() == W2_CONTEXT_SHA256
    assert encoding.encode_ordinary(W2_PROMPT) == W2_RAW_IDS
    assert encoding.encode_ordinary(context) == W2_CONTEXT_IDS
    assert len(W2_RAW_IDS) == profile.tokenizer_raw_token_count == 43
    assert len(W2_CONTEXT_IDS) == profile.tokenizer_context_token_count == 43
    assert max(len(W2_RAW_IDS), len(W2_CONTEXT_IDS)) <= profiles.WHISPER_PROMPT_LIMIT_TOKENS
    assert encoding.decode_bytes(W2_RAW_IDS) == W2_PROMPT.encode("utf-8")
    assert encoding.decode_bytes(W2_CONTEXT_IDS) == context.encode("utf-8")
    assert prompt_profile_sha256(profile) == W2_PROFILE_SHA256


def test_w0_w1_are_unchanged_and_w2_is_never_a_default_or_fallback():
    assert profile_for_id(None) is None
    assert profile_for_id("") is None
    assert prompt_profile_sha256(w1_prompt_profile()) == (
        "9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1"
    )
    assert profile_for_id(W1_PROFILE_ID) == w1_prompt_profile()
    assert profile_for_id(W2_PROFILE_ID) == w2_prompt_profile()
    with pytest.raises(ValueError, match="NOT_ALLOWLISTED"):
        profile_for_id("asr-whisper-vi-latest")


@pytest.mark.parametrize(
    ("source", "substitute"),
    [(w1_prompt_profile, W2_PROFILE_ID), (w2_prompt_profile, W1_PROFILE_ID)],
)
def test_w1_w2_id_substitution_is_rejected(source, substitute):
    payload = source().model_dump(mode="json")
    payload["profile_id"] = substitute
    with pytest.raises(ValueError):
        validate_prompt_profile(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt", W2_PROMPT + " "),
        ("prompt", unicodedata.normalize("NFD", W2_PROMPT)),
        ("prompt_sha256", "0" * 64),
        ("tokenizer_id", "unverified-tokenizer"),
        ("tokenizer_version", "latest"),
        ("tokenizer_upstream_commit", "0" * 40),
        ("tokenizer_ranks_sha256", "0" * 64),
        ("tokenizer_raw_token_count", 44),
        ("tokenizer_context_token_count", 44),
        ("tokenizer_context_policy", "truncate"),
        ("tokenizer_context_sha256", "0" * 64),
    ],
)
def test_w2_prompt_hash_and_tokenizer_metadata_mutations_are_rejected(field, value):
    payload = w2_prompt_profile().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValueError):
        validate_prompt_profile(payload)


def test_w2_missing_prompt_and_temperature_addition_are_rejected():
    missing = w2_prompt_profile().model_dump(mode="json")
    missing.pop("prompt")
    with pytest.raises(ValueError, match="FIELDS_INVALID"):
        validate_prompt_profile(missing)
    extra = w2_prompt_profile().model_dump(mode="json")
    extra["temperature"] = 0
    with pytest.raises(ValueError, match="FIELDS_INVALID"):
        validate_prompt_profile(extra)
    for duplicate in ("prompt_2", "prompts"):
        extra = w2_prompt_profile().model_dump(mode="json")
        extra[duplicate] = [W2_PROMPT]
        with pytest.raises(ValueError, match="FIELDS_INVALID"):
            validate_prompt_profile(extra)


def test_w2_runtime_count_over_limit_fails_closed(monkeypatch):
    class OverLimitEncoder:
        def encode_ordinary(self, value):
            return [1] * (profiles.WHISPER_PROMPT_LIMIT_TOKENS + 1)

        def decode_bytes(self, value):
            raise AssertionError("limit must fail before round-trip acceptance")

    monkeypatch.setattr(profiles, "_verified_encoding", lambda: OverLimitEncoder())
    with pytest.raises(ValueError, match="TOKENIZATION_INVALID"):
        w2_prompt_profile()


def test_w2_profile_returns_fresh_frozen_instances():
    first = w2_prompt_profile()
    second = w2_prompt_profile()
    assert first == second and first is not second
    with pytest.raises(Exception):
        first.prompt = "changed"
