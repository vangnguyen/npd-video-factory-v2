from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

from .trend_models import IdeaGenerateRequest, TrendClusterRefreshRequest


class SignalLike(Protocol):
    signal_id: str
    source: str
    source_reference: str
    observed_at: datetime
    keyword: str | None
    topic: str | None
    hashtags_json: list[str]
    format: str | None
    views: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    saves: int | None
    engagement: Any | None
    creator_count: int | None
    content_count: int | None
    velocity: Any | None
    acceleration: Any | None


@dataclass(frozen=True)
class ClusterDraft:
    canonical_key: str
    topic: str
    summary: str
    lifecycle: str
    first_observed_at: datetime
    last_observed_at: datetime
    signal_ids: list[str]
    similarities: dict[str, float]
    platforms: list[str]
    keywords: list[str]
    hashtags: list[str]


@dataclass(frozen=True)
class ScoreDraft:
    profile_hash: str
    total_score: float
    components: dict[str, float]
    weights: dict[str, float]


@dataclass(frozen=True)
class IdeaDraft:
    variant_key: str
    title: str
    angle: str
    hook_concept: str
    format: str
    recommended_duration_seconds: int
    visual_concept: str
    audience: str
    cta_concept: str
    trend_references: list[str]
    originality_notes: str
    brief: dict[str, Any]
    total_score: float
    score_components: dict[str, float]
    rationale: list[str]


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 3)


def normalized_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", normalized, flags=re.UNICODE))


def signal_tokens(signal: SignalLike) -> set[str]:
    values = [signal.topic or "", signal.keyword or "", *signal.hashtags_json]
    tokens: set[str] = set()
    for value in values:
        tokens.update(normalized_text(value.removeprefix("#")).split())
    return {token for token in tokens if len(token) > 1}


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def canonical_topic(signals: Iterable[SignalLike]) -> tuple[str, str]:
    topics = [signal.topic or signal.keyword or "untitled trend" for signal in signals]
    counts = Counter(normalized_text(topic) for topic in topics)
    normalized = sorted(counts, key=lambda item: (-counts[item], item))[0]
    display = sorted((topic for topic in topics if normalized_text(topic) == normalized), key=str.casefold)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode())
    slug = slug.strip("-")[:150] or "trend"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return display, f"{slug}-{digest}"


def _average(signals: Iterable[SignalLike], field: str) -> float | None:
    values = [float(getattr(signal, field)) for signal in signals if getattr(signal, field) is not None]
    return sum(values) / len(values) if values else None


def _saturation(signals: list[SignalLike]) -> float:
    content = _average(signals, "content_count")
    creators = _average(signals, "creator_count")
    content_score = min(100.0, math.log10((content or 0) + 1) * 32)
    creator_score = min(100.0, math.log10((creators or 0) + 1) * 38)
    if content is None and creators is None:
        return 35.0
    if content is None:
        return creator_score
    if creators is None:
        return content_score
    return (content_score * 0.6) + (creator_score * 0.4)


def lifecycle_for(signals: list[SignalLike], as_of: datetime) -> str:
    latest = max(signal.observed_at for signal in signals)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (as_of - latest).total_seconds() / 86_400)
    velocity = _average(signals, "velocity") or 0.0
    acceleration = _average(signals, "acceleration") or 0.0
    spread = len({signal.source for signal in signals})
    saturation = _saturation(signals)
    if age_days > 30 and velocity <= 5:
        return "expired"
    if velocity < 0 or acceleration < 0:
        return "declining"
    if saturation >= 78:
        return "saturated"
    if velocity >= 75 and acceleration >= 55 and spread >= 2:
        return "breakout"
    if velocity >= 55 and spread >= 2 and acceleration < 25:
        return "mainstream"
    if velocity >= 35 or acceleration >= 25:
        return "rising"
    return "discovered"


def cluster_signals(
    signals: list[SignalLike],
    *,
    similarity_threshold: float,
    as_of: datetime,
) -> list[ClusterDraft]:
    groups: list[list[SignalLike]] = []
    for signal in sorted(signals, key=lambda item: (item.observed_at, item.signal_id)):
        tokens = signal_tokens(signal)
        best_index: int | None = None
        best_similarity = 0.0
        for index, group in enumerate(groups):
            group_tokens = set().union(*(signal_tokens(item) for item in group))
            same_topic = any(
                normalized_text(item.topic) == normalized_text(signal.topic) and normalized_text(signal.topic)
                for item in group
            )
            similarity = 1.0 if same_topic else jaccard(tokens, group_tokens)
            if similarity >= similarity_threshold and similarity > best_similarity:
                best_index = index
                best_similarity = similarity
        if best_index is None:
            groups.append([signal])
        else:
            groups[best_index].append(signal)

    drafts: list[ClusterDraft] = []
    for group in groups:
        topic, key = canonical_topic(group)
        group_tokens = set().union(*(signal_tokens(item) for item in group))
        similarities = {
            signal.signal_id: round(jaccard(signal_tokens(signal), group_tokens) or 1.0, 5)
            for signal in group
        }
        platforms = sorted({signal.source for signal in group})
        keywords = sorted({signal.keyword for signal in group if signal.keyword}, key=str.casefold)
        hashtags = sorted({tag for signal in group for tag in signal.hashtags_json}, key=str.casefold)
        drafts.append(
            ClusterDraft(
                canonical_key=key,
                topic=topic,
                summary=(
                    f"{len(group)} normalized signals across {len(platforms)} platform(s) support this topic. "
                    "Scores are estimates derived only from available fixture/provider metrics."
                ),
                lifecycle=lifecycle_for(group, as_of),
                first_observed_at=min(signal.observed_at for signal in group),
                last_observed_at=max(signal.observed_at for signal in group),
                signal_ids=[signal.signal_id for signal in group],
                similarities=similarities,
                platforms=platforms,
                keywords=keywords,
                hashtags=hashtags,
            )
        )
    return sorted(drafts, key=lambda item: (item.topic.casefold(), item.canonical_key))


def score_cluster(
    draft: ClusterDraft,
    signals: list[SignalLike],
    request: TrendClusterRefreshRequest,
) -> ScoreDraft:
    velocity = clamp((_average(signals, "velocity") or 0.0))
    acceleration = clamp((_average(signals, "acceleration") or 0.0))
    spread = clamp(len(draft.platforms) / 4 * 100)
    views = sum(signal.views or 0 for signal in signals)
    engagement_total = sum(
        float(signal.engagement)
        if signal.engagement is not None
        else float((signal.likes or 0) + (signal.comments or 0) + (signal.shares or 0) + (signal.saves or 0))
        for signal in signals
    )
    engagement_quality = clamp((engagement_total / views * 1000) if views else 50.0)
    saturation = clamp(_saturation(signals))
    competition = clamp((_average(signals, "creator_count") or 0.0) * 2.2)
    vertical_ratio = sum(1 for signal in signals if signal.format == "vertical_short") / len(signals)
    channel_fit = 90.0 if "short" in request.channel.casefold() and vertical_ratio else 72.0
    format_fit = clamp(60 + vertical_ratio * 35)
    monetization_fit = 86.0 if request.business_objective in {"lead_generation", "conversion"} else 74.0
    if request.niche.value == "affiliate":
        monetization_fit = 90.0
    components = {
        "velocity": velocity,
        "acceleration": acceleration,
        "cross_platform_spread": spread,
        "engagement_quality": engagement_quality,
        "novelty": clamp(100 - saturation),
        "channel_fit": channel_fit,
        "format_fit": format_fit,
        "monetization_fit": monetization_fit,
        "saturation": saturation,
        "competition": competition,
        "rights_risk": 6.0,
        "policy_risk": 8.0,
    }
    weights = request.weights.model_dump()
    positives = [
        "velocity",
        "acceleration",
        "cross_platform_spread",
        "engagement_quality",
        "novelty",
        "channel_fit",
        "format_fit",
        "monetization_fit",
    ]
    penalties = ["saturation", "competition", "rights_risk", "policy_risk"]
    positive_weight = sum(weights[key] for key in positives) or 1
    penalty_weight = sum(weights[key] for key in penalties) or 1
    positive_score = sum(components[key] * weights[key] for key in positives) / positive_weight
    penalty_score = sum(components[key] * weights[key] for key in penalties) / penalty_weight
    total = clamp(positive_score - (penalty_score * 0.28))
    profile = {
        "algorithm": "trend-opportunity-v1",
        "channel": request.channel,
        "niche": request.niche.value,
        "business_objective": request.business_objective,
        "weights": weights,
    }
    profile_hash = hashlib.sha256(json.dumps(profile, sort_keys=True).encode("utf-8")).hexdigest()
    return ScoreDraft(profile_hash=profile_hash, total_score=total, components=components, weights=weights)


class IdeaEngine:
    _strategies = (
        {
            "key": "myth_reframe",
            "label": "Hiểu đúng thay vì chạy theo đám đông",
            "angle": "Tách điều đang được quan tâm khỏi ngộ nhận phổ biến, rồi giải thích bằng bằng chứng.",
            "hook": "Điều nhiều người đang hiểu sai về {topic} là gì?",
            "visual": "Mở bằng hai vế đúng/sai, sau đó chuyển sang ba thẻ bằng chứng và kết luận.",
            "hook_score": 90,
            "originality": 91,
        },
        {
            "key": "data_explainer",
            "label": "Giải mã tín hiệu đang tăng",
            "angle": "Dùng các chỉ số được cung cấp để giải thích vì sao chủ đề tăng và đâu là giới hạn dữ liệu.",
            "hook": "Ba tín hiệu cho thấy {topic} đang thay đổi ngay lúc này.",
            "visual": "Biểu đồ động, nhãn nguồn và bảng so sánh đa nền tảng; không chèn video của creator.",
            "hook_score": 84,
            "originality": 86,
        },
        {
            "key": "action_checklist",
            "label": "Checklist hành động thực tế",
            "angle": "Chuyển chủ đề thành checklist ngắn có thể áp dụng, kèm điều kiện và cảnh báo.",
            "hook": "Trước khi áp dụng {topic}, hãy kiểm tra bốn điểm này.",
            "visual": "Checklist theo nhịp, icon tự tạo và cảnh quay thương hiệu được cấp quyền.",
            "hook_score": 87,
            "originality": 84,
        },
        {
            "key": "before_after",
            "label": "Trước và sau khi thay đổi cách làm",
            "angle": "So sánh hai quy trình hoặc kết quả để làm rõ giá trị thực tế của chủ đề.",
            "hook": "Khác biệt trước và sau khi dùng đúng {topic} nằm ở đâu?",
            "visual": "Bố cục chia đôi với tài sản thương hiệu hoặc đồ họa tự tạo, không sao chép treatment nguồn.",
            "hook_score": 82,
            "originality": 88,
        },
        {
            "key": "mini_case",
            "label": "Tình huống giả định có kiểm soát",
            "angle": "Dùng một tình huống minh họa được ghi rõ là giả định để diễn giải quyết định.",
            "hook": "Nếu gặp {topic} trong một tình huống thực tế, nên quyết định theo thứ tự nào?",
            "visual": "Dòng thời gian tình huống, dữ liệu giả định được gắn nhãn và CTA cuối video.",
            "hook_score": 85,
            "originality": 93,
        },
        {
            "key": "expert_questions",
            "label": "Năm câu hỏi cần hỏi chuyên gia",
            "angle": "Biến chủ đề thành bộ câu hỏi giúp khán giả tự đánh giá thông tin và rủi ro.",
            "hook": "Đừng hành động với {topic} trước khi có câu trả lời cho năm câu hỏi này.",
            "visual": "Question cards, progress marker và nguồn tham khảo dạng metadata.",
            "hook_score": 88,
            "originality": 89,
        },
    )

    def generate(
        self,
        *,
        topic: str,
        trend_score: ScoreDraft,
        lifecycle: str,
        source_references: list[str],
        evidence_summaries: list[str],
        request: IdeaGenerateRequest,
    ) -> list[IdeaDraft]:
        duration = 40 if "short" in request.channel.casefold() else 60
        results: list[IdeaDraft] = []
        for strategy in self._strategies[: request.count]:
            visual_potential = 90.0 if strategy["key"] in {"data_explainer", "before_after"} else 84.0
            feasibility = 92.0 if request.budget_vnd in {None, 0} else 88.0
            components = {
                "hook_strength": float(strategy["hook_score"]),
                "trend_relevance": trend_score.total_score,
                "originality": float(strategy["originality"]),
                "audience_fit": 86.0 if request.audience != "general audience" else 74.0,
                "visual_potential": visual_potential,
                "production_feasibility": feasibility,
                "expected_retention": float(strategy["hook_score"]) - 4,
                "shareability": 82.0 if strategy["key"] in {"myth_reframe", "action_checklist"} else 76.0,
                "monetization_potential": trend_score.components["monetization_fit"],
                "production_cost": 12.0 if request.budget_vnd in {None, 0} else 18.0,
                "saturation": trend_score.components["saturation"],
                "policy_risk": trend_score.components["policy_risk"],
            }
            positives = [
                "hook_strength",
                "trend_relevance",
                "originality",
                "audience_fit",
                "visual_potential",
                "production_feasibility",
                "expected_retention",
                "shareability",
                "monetization_potential",
            ]
            penalties = ["production_cost", "saturation", "policy_risk"]
            total = clamp(
                sum(components[key] for key in positives) / len(positives)
                - (sum(components[key] for key in penalties) / len(penalties) * 0.2)
            )
            results.append(
                IdeaDraft(
                    variant_key=str(strategy["key"]),
                    title=f"{strategy['label']}: {topic}",
                    angle=str(strategy["angle"]),
                    hook_concept=str(strategy["hook"]).format(topic=topic),
                    format="vertical_short" if "short" in request.channel.casefold() else "explainer",
                    recommended_duration_seconds=duration,
                    visual_concept=str(strategy["visual"]),
                    audience=request.audience,
                    cta_concept=request.cta,
                    trend_references=source_references,
                    originality_notes=(
                        "Generate a new script, structure, narration and visual treatment. "
                        "References are research metadata only; do not download or reproduce creator media."
                    ),
                    brief={
                        "lifecycle": lifecycle,
                        "verified_evidence": evidence_summaries,
                        "creative_framing": strategy["angle"],
                        "uncertain_claims": [],
                        "production_mode": "draft_only",
                    },
                    total_score=total,
                    score_components=components,
                    rationale=[
                        f"Trend estimate: {trend_score.total_score:.1f}/100.",
                        f"Originality estimate: {components['originality']:.1f}/100.",
                        "No observed performance is claimed; all scores are planning estimates.",
                    ],
                )
            )
        return results
