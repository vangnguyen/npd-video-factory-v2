"""Offline W1 identity/count and strict immutable request-profile regression."""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import tomllib
import unicodedata
import urllib.request
from pathlib import Path

import pytest
import requests
import tiktoken
import tiktoken.load
from pydantic import ValidationError

import app.asr_prompt_profile as profiles
from app.asr_prompt_profile import (
    AsrPromptProfile,
    W1_PROFILE_ID,
    W1_PROMPT,
    profile_for_id,
    prompt_profile_sha256,
    validate_prompt_profile,
    w1_prompt_profile,
)


RAW_IDS = [
    45, 70, 12935, 66, 2623, 24605, 13055, 8217, 11, 691, 10085,
    18168, 6969, 35053, 11, 383, 18241, 15334, 21270, 11, 258, 335,
    19068, 601, 272, 22476, 11, 42178, 262, 39569, 272, 7200, 48373, 13,
]
CONTEXT_IDS = [21198, *RAW_IDS[2:]]
PROFILE_SHA = "9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1"
FIELDS = tuple(profiles._expected_payload())


@pytest.fixture(autouse=True)
def forbid_network_and_registry(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network/encoding registry must not be used")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setattr(tiktoken, "get_encoding", forbidden)
    monkeypatch.setattr(tiktoken, "encoding_for_model", forbidden)
    monkeypatch.setattr(tiktoken.load, "read_file", forbidden)
    monkeypatch.setattr(tiktoken.load, "read_file_cached", forbidden)


def payload():
    return w1_prompt_profile().model_dump(mode="json")


def test_exact_profile_counts_and_golden_token_ids_round_trip_without_network():
    profile = w1_prompt_profile()
    encoding = profiles._verified_encoding()
    context = " " + profile.prompt.strip()
    assert encoding.encode_ordinary(profile.prompt) == RAW_IDS
    assert encoding.encode_ordinary(context) == CONTEXT_IDS
    assert len(RAW_IDS) == profile.tokenizer_raw_token_count == 34
    assert len(CONTEXT_IDS) == profile.tokenizer_context_token_count == 33
    assert max(len(RAW_IDS), len(CONTEXT_IDS)) <= 224
    assert encoding.decode_bytes(RAW_IDS) == W1_PROMPT.encode("utf-8")
    assert encoding.decode_bytes(CONTEXT_IDS) == context.encode("utf-8")
    assert len(profile.prompt.encode("utf-8")) == profile.prompt_utf8_bytes == 105
    assert len(context.encode("utf-8")) == 106
    assert hashlib.sha256(profile.prompt.encode("utf-8")).hexdigest() == profile.prompt_sha256
    assert hashlib.sha256(context.encode("utf-8")).hexdigest() == profile.tokenizer_context_sha256
    assert profile.prompt != context  # Count preprocessing does not rewrite request.


def test_profile_has_every_required_field_and_no_hidden_authority():
    model = w1_prompt_profile()
    assert set(model.model_dump()) == set(FIELDS)
    assert all(field.is_required() for field in AsrPromptProfile.model_fields.values())
    assert model.timestamp_granularities == ("segment", "word")
    assert model.temperature_policy == "omitted"
    assert not {"temperature", "budget", "credential", "authority", "prompt_tokens"} & set(FIELDS)


def test_canonical_hash_stable_across_json_order_tuple_list_and_fresh_instances():
    model = w1_prompt_profile()
    raw = model.model_dump(mode="json")
    snapshot = json.dumps(raw, ensure_ascii=False)
    reversed_keys = dict(reversed(tuple(raw.items())))
    assert prompt_profile_sha256(model) == PROFILE_SHA
    assert prompt_profile_sha256(raw) == PROFILE_SHA
    assert prompt_profile_sha256(reversed_keys) == PROFILE_SHA
    assert prompt_profile_sha256(AsrPromptProfile.model_validate_json(snapshot)) == PROFILE_SHA
    assert json.dumps(raw, ensure_ascii=False) == snapshot
    fresh = validate_prompt_profile(model)
    assert fresh == model and fresh is not model
    assert w1_prompt_profile() is not model


@pytest.mark.parametrize("value", [None, ""])
def test_no_profile_remains_legacy_w0_without_tokenizer_use(value, monkeypatch):
    def forbidden():
        raise AssertionError("W0 must not load tokenizer")

    monkeypatch.setattr(profiles, "_verified_encoding", forbidden)
    assert profile_for_id(value) is None
    assert validate_prompt_profile(None) is None
    assert prompt_profile_sha256(None) is None


def test_only_exact_w1_id_resolves_to_profile():
    assert profile_for_id(W1_PROFILE_ID) == w1_prompt_profile()


@pytest.mark.parametrize("value", ["w1", "W1", "asr-whisper-vi-w2-v1", " ", W1_PROFILE_ID + " ", 1, True, [], {}])
def test_unknown_or_non_string_profile_id_rejected(value):
    with pytest.raises(ValueError):
        profile_for_id(value)


@pytest.mark.parametrize("field", FIELDS)
def test_every_metadata_field_is_required(field):
    raw = payload()
    raw.pop(field)
    with pytest.raises(ValueError):
        validate_prompt_profile(raw)


@pytest.mark.parametrize("field", FIELDS)
def test_every_metadata_field_is_exact_type_not_coerced(field):
    raw = payload()
    raw[field] = True if type(raw[field]) is int else 1
    with pytest.raises(ValueError):
        validate_prompt_profile(raw)


@pytest.mark.parametrize("field", FIELDS)
def test_every_metadata_field_is_bound_to_exact_value(field):
    raw = payload()
    original = raw[field]
    raw[field] = original + 1 if type(original) is int else (
        list(reversed(original)) if type(original) is list else original + "-changed"
    )
    with pytest.raises(ValueError):
        validate_prompt_profile(raw)


@pytest.mark.parametrize("field", ["temperature", "prompt_tokens", "extra", "execution_enabled", "credential_alias"])
def test_extra_field_rejected(field):
    raw = payload()
    raw[field] = "not-authorized"
    with pytest.raises(ValueError):
        validate_prompt_profile(raw)


@pytest.mark.parametrize("value", [[], (), "", W1_PROFILE_ID, 34, True])
def test_wrong_profile_container_rejected(value):
    with pytest.raises(ValueError):
        validate_prompt_profile(value)


@pytest.mark.parametrize("value", [34.0, "34", True, None, -1, 225])
def test_token_count_wrong_type_or_amount_rejected(value):
    raw = payload()
    raw["tokenizer_raw_token_count"] = value
    with pytest.raises(ValueError):
        validate_prompt_profile(raw)


@pytest.mark.parametrize("value", [{"segment", "word"}, "segment,word", ["word", "segment"], ["word"], ["segment", "word", "word"], [1, 2]])
def test_granularity_container_order_and_contents_rejected(value):
    raw = payload()
    raw["timestamp_granularities"] = value
    with pytest.raises(ValueError):
        validate_prompt_profile(raw)


@pytest.mark.parametrize("text", [
    " "+W1_PROMPT, W1_PROMPT+" ", W1_PROMPT.replace("Ngọc", "Ngoc"),
    unicodedata.normalize("NFD", W1_PROMPT), W1_PROMPT.lower(),
    W1_PROMPT+" <|endoftext|>", "synthetic.private@example.invalid",
    "Một transcript/reference thay cho glossary", "W2 " + W1_PROMPT,
    "x" * 10000,
])
def test_non_exact_prompt_pii_control_tag_or_overlong_rejected_before_tokenizer(text, monkeypatch):
    raw = payload()
    raw["prompt"] = text

    def forbidden():
        raise AssertionError("arbitrary text must fail before tokenization")

    monkeypatch.setattr(profiles, "_verify_w1_tokenization", forbidden)
    with pytest.raises(ValueError):
        validate_prompt_profile(raw)
    assert raw["prompt"] == text


def test_frozen_model_cannot_be_mutated():
    model = w1_prompt_profile()
    with pytest.raises(ValidationError):
        model.prompt = "changed"


@pytest.mark.parametrize("field", FIELDS)
def test_unvalidated_model_copy_tampering_revalidated(field):
    model = w1_prompt_profile().model_copy(update={field: None})
    with pytest.raises(ValueError):
        validate_prompt_profile(model)
    with pytest.raises(ValueError):
        prompt_profile_sha256(model)


def test_model_construct_missing_fields_rejected():
    forged = AsrPromptProfile.model_construct(profile_id=W1_PROFILE_ID)
    with pytest.raises(ValueError):
        validate_prompt_profile(forged)


def test_model_construct_changed_value_rejected():
    raw = payload()
    raw["tokenizer_context_token_count"] = 32
    forged = AsrPromptProfile.model_construct(**raw)
    with pytest.raises(ValueError):
        validate_prompt_profile(forged)


def test_model_copy_extra_and_object_mutation_rejected():
    with pytest.raises(ValueError):
        validate_prompt_profile(w1_prompt_profile().model_copy(update={"extra": True}))
    forged = w1_prompt_profile()
    object.__setattr__(forged, "prompt_sha256", "0" * 64)
    with pytest.raises(ValueError):
        validate_prompt_profile(forged)


def test_packaged_data_provenance_license_and_all_bytes_are_exact():
    data_dir = profiles._RANKS_PATH.parent
    raw = profiles._RANKS_PATH.read_bytes()
    provenance = json.loads((data_dir / "provenance.json").read_text(encoding="utf-8"))
    assert len(raw) == provenance["rank_file_bytes"] == 816730
    assert hashlib.sha256(raw).hexdigest() == provenance["rank_file_sha256"] == profiles.TOKENIZER_RANKS_SHA256
    assert provenance["upstream_commit"] == profiles.TOKENIZER_UPSTREAM_COMMIT
    assert provenance["tiktoken_version"] == tiktoken.__version__ == "0.12.0"
    assert provenance["runtime_network_required"] is False
    assert provenance["model_weights"] is False
    assert provenance["model_inference"] is False
    assert provenance["provider_authority"] is False
    license_bytes = (data_dir / "LICENSE").read_bytes()
    assert hashlib.sha256(license_bytes).hexdigest() == provenance["license_upstream_sha256"]
    assert b"MIT License" in license_bytes
    ranks = {base64.b64decode(token): int(rank) for token, rank in (line.split() for line in raw.splitlines())}
    assert len(ranks) == 50257
    assert set(ranks.values()) == set(range(50257))
    assert all(bytes([item]) in ranks for item in range(256))
    assert ranks[b""] == 50256  # Exact upstream empty-token sentinel, not input.
    assert "multilingual.tiktoken -text" in (data_dir / ".gitattributes").read_text()
    config = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert "tiktoken==0.12.0" in config["project"]["dependencies"]
    assert "data/whisper/*" in config["tool"]["setuptools"]["package-data"]["app"]


def test_artifact_changed_after_encoder_cache_warm_is_rejected(tmp_path, monkeypatch):
    raw = profiles._RANKS_PATH.read_bytes()
    assert w1_prompt_profile()
    altered = tmp_path / "multilingual.tiktoken"
    altered.write_bytes(raw[:-1] + b"!")
    monkeypatch.setattr(profiles, "_RANKS_PATH", altered)
    with pytest.raises(ValueError, match="ARTIFACT_INVALID"):
        w1_prompt_profile()


def test_missing_artifact_after_cache_warm_is_rejected(tmp_path, monkeypatch):
    assert w1_prompt_profile()
    monkeypatch.setattr(profiles, "_RANKS_PATH", tmp_path / "not-present.tiktoken")
    with pytest.raises(ValueError, match="ARTIFACT_UNAVAILABLE"):
        w1_prompt_profile()


def test_unpinned_tiktoken_version_rejected(monkeypatch):
    monkeypatch.setattr(tiktoken, "__version__", "0.13.0")
    with pytest.raises(ValueError, match="VERSION_INVALID"):
        w1_prompt_profile()


def test_direct_unverified_bytes_cannot_reach_encoding_constructor():
    with pytest.raises(ValueError, match="ARTIFACT_INVALID"):
        profiles._encoding_from_verified_bytes(b"bad data")


def test_bad_count_or_round_trip_from_encoder_is_rejected(monkeypatch):
    class WrongEncoder:
        def encode_ordinary(self, value):
            return [1]

        def decode_bytes(self, value):
            return b"wrong"

    monkeypatch.setattr(profiles, "_verified_encoding", lambda: WrongEncoder())
    with pytest.raises(ValueError, match="TOKENIZATION_INVALID"):
        w1_prompt_profile()


def test_correct_counts_but_wrong_round_trip_is_rejected(monkeypatch):
    class WrongEncoder:
        def encode_ordinary(self, value):
            return RAW_IDS if value == W1_PROMPT else CONTEXT_IDS

        def decode_bytes(self, value):
            return b"wrong"

    monkeypatch.setattr(profiles, "_verified_encoding", lambda: WrongEncoder())
    with pytest.raises(ValueError, match="TOKENIZATION_INVALID"):
        w1_prompt_profile()


def test_model_json_round_trip_revalidates_constructed_object():
    model = w1_prompt_profile()
    assert AsrPromptProfile.model_validate(model) == model
    raw = model.model_dump(mode="json")
    raw["prompt_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        AsrPromptProfile.model_validate_json(json.dumps(raw))


def test_module_has_no_network_provider_model_or_credential_imports():
    source = Path(profiles.__file__).read_text(encoding="utf-8")
    assert "import openai" not in source
    assert "import whisper" not in source
    assert "import torch" not in source
    assert "os.environ" not in source
    assert "getenv(" not in source
    assert "load_model(" not in source
    assert "get_encoding(" not in source
    assert "encoding_for_model(" not in source
