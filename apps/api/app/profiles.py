from __future__ import annotations

from dataclasses import dataclass

from .models import NicheName


@dataclass(frozen=True)
class NicheProfile:
    """Configuration consumed by content adapters, never by the core job engine."""

    name: NicheName
    hook_pattern: str
    body_patterns: tuple[str, str, str, str]
    scene_roles: tuple[str, str, str, str, str, str]


GENERIC_PROFILE = NicheProfile(
    name=NicheName.CUSTOM,
    hook_pattern="{topic}: điều gì đáng chú ý nhất?",
    body_patterns=(
        "Một: xác định vấn đề chính và bối cảnh cần biết.",
        "Hai: đối chiếu bằng chứng trước khi đưa ra kết luận.",
        "Ba: chọn hành động phù hợp với nhu cầu thực tế.",
        "Tóm tắt ngắn gọn giúp người xem quyết định bước tiếp theo.",
    ),
    scene_roles=("hook", "identity", "information", "evidence", "value", "cta"),
)


REAL_ESTATE_PROFILE = NicheProfile(
    name=NicheName.REAL_ESTATE,
    hook_pattern="Quan tâm {project_name}? Đừng chỉ nhìn phối cảnh.",
    body_patterns=(
        "Một: xem mô hình dự án, hiểu quy hoạch và vị trí từng phân khu.",
        "Hai: chọn sản phẩm đúng nhu cầu ở, nghỉ dưỡng hay đầu tư.",
        "Ba: đối chiếu tài liệu chính thức trước khi xuống tiền.",
        "Đến xem thực tế giúp bạn hỏi đúng và so sánh dễ hơn.",
    ),
    scene_roles=("hook", "identity", "information", "evidence", "sales_angle", "cta"),
)


NICHE_PROFILES: dict[NicheName, NicheProfile] = {
    niche: NicheProfile(
        name=niche,
        hook_pattern=GENERIC_PROFILE.hook_pattern,
        body_patterns=GENERIC_PROFILE.body_patterns,
        scene_roles=GENERIC_PROFILE.scene_roles,
    )
    for niche in NicheName
}
NICHE_PROFILES[NicheName.REAL_ESTATE] = REAL_ESTATE_PROFILE


def get_niche_profile(name: NicheName) -> NicheProfile:
    return NICHE_PROFILES[name]
