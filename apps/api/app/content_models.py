"""Multi-input authoring, not provider output or execution authority."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field, model_validator
from .models import StrictModel


class StoryboardScene(StrictModel):
    scene_id: str = Field(pattern=r"^scene_[A-Za-z0-9_-]{2,60}$")
    narration: str = Field(default="", max_length=180)
    visual_brief: str = Field(default="", max_length=500)
    duration_seconds: float = Field(default=4, ge=0.5, le=30)
    media_strategy: Literal["user_asset", "motion_graphic", "ai_image", "ai_video"] = "motion_graphic"
    asset_id: str | None = Field(default=None, pattern=r"^ast_[A-Za-z0-9_-]{4,60}$")
    analysis_id: str | None = Field(default=None, pattern=r"^ana_[A-Za-z0-9_-]{4,60}$")
    source_start: float = Field(default=0, ge=0)
    fit: Literal["cover", "contain"] = "contain"
    transition: Literal["cut", "fade"] = "cut"
    architectural_render: bool = False
    official_render: bool = False
    original_audio: Literal["keep", "mute"] = "mute"
    script_start: int | None = Field(default=None, ge=0)
    script_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def media_choice(self):
        if self.media_strategy == "user_asset" and not self.asset_id:
            raise ValueError("user_asset requires an asset reference")
        if self.media_strategy != "user_asset" and (self.asset_id or self.analysis_id):
            raise ValueError("generation plans cannot contain an uploaded asset/analysis")
        if self.official_render and not self.architectural_render:
            raise ValueError("official render requires architectural render metadata")
        if (self.script_start is None) != (self.script_end is None):
            raise ValueError("script offsets must be paired")
        if self.script_start is not None and self.script_end <= self.script_start:
            raise ValueError("script interval must be positive")
        return self


class ContentDocument(StrictModel):
    schema_version: Literal["mvp1-content-v1"] = "mvp1-content-v1"
    input_kind: Literal["idea", "prompt", "script"]
    original_text: str = Field(min_length=1, max_length=20000)
    creative_instructions: str = Field(default="", max_length=20000)
    script: str = Field(default="", max_length=20000)
    scenes: list[StoryboardScene] = Field(default_factory=list, max_length=40)
    facts_needing_source: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(default_factory=list, max_length=40)
    approved: bool = False
    generator: Literal["deterministic-user-draft", "fixture-storyboard-v1"] = "deterministic-user-draft"
    supplied_facts: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def bounds(self):
        if not self.original_text.strip():
            raise ValueError("input text must not be blank")
        ids = [s.scene_id for s in self.scenes]
        if len(set(ids)) != len(ids):
            raise ValueError("scene identities must be unique")
        if sum(s.duration_seconds for s in self.scenes) > 180:
            raise ValueError("storyboard exceeds the existing 180-second render contract")
        for scene in self.scenes:
            if scene.script_start is not None and self.script[scene.script_start:scene.script_end] != scene.narration:
                raise ValueError("scene script offsets do not match immutable source narration")
        if self.approved and (not self.scenes or not any(s.narration.strip() for s in self.scenes)):
            raise ValueError("approve an explicit script/storyboard, not creative instructions alone")
        return self


class ContentSaveRequest(StrictModel):
    expected_content_version_id: str | None = Field(default=None, pattern=r"^pver_[A-Za-z0-9_-]{4,60}$")
    document: ContentDocument
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)


class ContentGenerateRequest(StrictModel):
    expected_content_version_id: str = Field(pattern=r"^pver_[A-Za-z0-9_-]{4,60}$")
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class ContentApplyRequest(StrictModel):
    expected_content_version_id: str = Field(pattern=r"^pver_[A-Za-z0-9_-]{4,60}$")


class ContentGenerationResult(StrictModel):
    """Validated adapter output; proposal is not approved content or factual evidence."""
    script: str = Field(min_length=1, max_length=20000)
    scenes: list[StoryboardScene] = Field(min_length=1, max_length=40)
    facts_needing_source: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def narration_matches_script(self):
        document = ContentDocument(input_kind="script", original_text=self.script, script=self.script, scenes=self.scenes)
        if " ".join(document.script.split()) != " ".join(" ".join(s.narration.split()) for s in self.scenes):
            raise ValueError("generation must preserve complete script order/coverage")
        return self
