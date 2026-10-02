"""Exact ASR quality guards shared by direct-provider acceptance fixtures."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def _normalized_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def _occurrences(text: str, phrase: str) -> int:
    haystack, needle = _normalized_tokens(text), _normalized_tokens(phrase)
    if not needle:
        return 0
    return sum(haystack[index:index + len(needle)] == needle for index in range(len(haystack) - len(needle) + 1))


@dataclass(frozen=True)
class PromptInsertionGuardResult:
    reference_counts: dict[str, int]
    provider_counts: dict[str, int]
    excess_counts: dict[str, int]
    passed: bool


@dataclass(frozen=True)
class DirectAsrQualityResult:
    wer: float
    critical_term_recall: float
    critical_terms_passed: int
    critical_terms_required: int
    insertion_guard: PromptInsertionGuardResult
    passed: bool


def _edit_distance(reference: tuple[str, ...], hypothesis: tuple[str, ...]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, start=1):
        current = [row]
        for column, actual in enumerate(hypothesis, start=1):
            current.append(min(
                current[column - 1] + 1,
                previous[column] + 1,
                previous[column - 1] + (expected != actual),
            ))
        previous = current
    return previous[-1]


def evaluate_prompt_insertion_guard(
    *, reference: str, provider_transcript: str, prompted_terms: tuple[str, ...],
) -> PromptInsertionGuardResult:
    reference_counts = {term: _occurrences(reference, term) for term in prompted_terms}
    provider_counts = {term: _occurrences(provider_transcript, term) for term in prompted_terms}
    excess = {
        term: max(0, provider_counts[term] - reference_counts[term])
        for term in prompted_terms
    }
    return PromptInsertionGuardResult(
        reference_counts=reference_counts,
        provider_counts=provider_counts,
        excess_counts=excess,
        passed=not any(excess.values()),
    )


def evaluate_direct_asr_quality(
    *,
    reference: str,
    provider_transcript: str,
    critical_terms: tuple[str, ...],
    prompted_terms: tuple[str, ...],
) -> DirectAsrQualityResult:
    """Canonical direct-provider text gate; never rewrites either transcript."""

    reference_tokens = _normalized_tokens(reference)
    hypothesis_tokens = _normalized_tokens(provider_transcript)
    wer = _edit_distance(reference_tokens, hypothesis_tokens) / max(1, len(reference_tokens))
    passed_terms = sum(_occurrences(provider_transcript, term) > 0 for term in critical_terms)
    recall = passed_terms / max(1, len(critical_terms))
    insertion = evaluate_prompt_insertion_guard(
        reference=reference,
        provider_transcript=provider_transcript,
        prompted_terms=prompted_terms,
    )
    return DirectAsrQualityResult(
        wer=wer,
        critical_term_recall=recall,
        critical_terms_passed=passed_terms,
        critical_terms_required=len(critical_terms),
        insertion_guard=insertion,
        passed=wer <= 0.15 and recall == 1.0 and insertion.passed,
    )
