"""Read-only W1 context-insertion guard. This is not runtime authority or quality evidence."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[4]
MANIFEST = REPO / "docs/acceptance/v3-01/assets/V3-01-RC11-ASR-ASSET-MANIFEST.json"
MANIFEST_SHA256 = "0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0"
TERMS = (
    "Ngọc Phương Đông", "Vinhomes Green Paradise", "Cần Giờ",
    "tham quan sa bàn", "chính sách bán hàng",
)
PROFILE_KEYS = ("asr_prompt_profile", "asr_prompt_profile_sha256")


def active(payload: dict[str, Any]) -> bool:
    binding = payload.get("binding") or {}
    provenance = (payload.get("provider_transcript") or {}).get("provenance") or {}
    # Presence (even null) means a W1 claim. Missing both keys on both sides is W0.
    return any(key in source for source in (binding, provenance) for key in PROFILE_KEYS)


def _count(words: list[str], term: list[str]) -> int:
    return sum(words[i:i + len(term)] == term for i in range(len(words) - len(term) + 1))


def check(
    payload: dict[str, Any], *, normalize: Callable[[str], list[str]],
    maximum_wer: float, minimum_critical_recall: float,
    expected_profile_id: str | None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Require immutable profile/reference bindings; never normalize provider data in place."""
    api = str(REPO / "apps/api")
    if api not in sys.path:
        sys.path.insert(0, api)
    from app.asr_prompt_profile import profile_for_id, prompt_profile_sha256, validate_prompt_profile

    failures: list[str] = []
    reviews: list[str] = []
    binding = payload["binding"]
    reference = payload["reference"]
    transcript = payload.get("provider_transcript")
    provenance = (transcript or {}).get("provenance") or {}
    report: dict[str, Any] = {
        "profile_sha256": None,
        "asset_slot": None,
        "reference_sha256": None,
        "hypothesis_sha256": None,
        "terms": [],
        "negative_control": False,
        "profile_binding_valid": False,
        "reference_binding_valid": False,
        "quality_thresholds_unchanged": maximum_wer <= 0.15 and minimum_critical_recall == 1.0,
        "insertion_guard_passed": False,
        "expected_profile_id": expected_profile_id,
        "human_audio_review": "NOT_PERFORMED_BY_MACHINE_GUARD",
        "transcript_modified": False,
    }
    if not report["quality_thresholds_unchanged"]:
        failures.append("W1_QUALITY_THRESHOLD_RELAXATION_FORBIDDEN")
    try:
        profile = profile_for_id(expected_profile_id)
        if profile is None or validate_prompt_profile(binding.get("asr_prompt_profile")) != profile:
            raise ValueError("missing trusted expected profile or binding")
        expected_hash = prompt_profile_sha256(profile)
        if binding.get("asr_prompt_profile_sha256") != expected_hash:
            raise ValueError("binding profile hash")
        if (binding.get("provider"), binding.get("model"), binding.get("capability"), binding.get("language")) != (
            "openai-transcription", "whisper-1", "asr", "vi",
        ):
            raise ValueError("profile capability")
        report["profile_sha256"] = expected_hash
        if transcript is not None:
            observed = validate_prompt_profile(provenance.get("asr_prompt_profile"))
            if observed != profile or provenance.get("asr_prompt_profile_sha256") != expected_hash:
                raise ValueError("provider provenance profile hash")
        report["profile_binding_valid"] = True
    except (ValueError, TypeError, OSError):
        failures.append("W1_PROFILE_BINDING_INVALID")
    try:
        manifest_bytes = MANIFEST.read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
            raise ValueError("manifest changed")
        manifest = json.loads(manifest_bytes)
        asset = next(row for row in manifest["assets"] if row["sha256"] == binding["asset_sha256"])
        reference_bytes = (REPO / asset["reference_transcript_path"]).read_bytes()
        reference_hash = hashlib.sha256(reference_bytes).hexdigest()
        if (
            reference_hash != asset["reference_transcript_sha256"]
            or reference.get("transcript_sha256") != reference_hash
            or reference.get("transcript_path") != asset["reference_transcript_path"]
            or reference["transcript"] != reference_bytes.decode("utf-8")
            or reference["critical_terms"] != asset["critical_terms"]
            or len(reference["critical_terms"]) != 8
        ):
            raise ValueError("immutable reference mismatch")
        report.update(asset_slot=asset["slot"], reference_sha256=reference_hash,
                      reference_binding_valid=True, negative_control=asset["slot"] == 2)
    except (ValueError, TypeError, KeyError, StopIteration, OSError):
        failures.append("W1_APPROVED_REFERENCE_BINDING_INVALID")
    if transcript is None:
        reviews.append("W1_PROVIDER_TRANSCRIPT_UNAVAILABLE")
    elif report["reference_binding_valid"]:
        actual = transcript["text"]
        expected_words = normalize(reference["transcript"])
        actual_words = normalize(actual)
        report["hypothesis_sha256"] = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        for term in TERMS:
            expected = _count(expected_words, normalize(term))
            observed = _count(actual_words, normalize(term))
            report["terms"].append({
                "term": term, "reference_count": expected, "hypothesis_count": observed,
                "excess_count": max(0, observed - expected),
            })
            if observed > expected:
                failures.append("W1_PROMPT_TERM_INSERTION")
        if report["negative_control"] and any(row["reference_count"] for row in report["terms"]):
            failures.append("W1_NEGATIVE_CONTROL_REFERENCE_INVALID")
    report["insertion_guard_passed"] = not failures and not reviews
    return report, sorted(set(failures)), sorted(set(reviews))
