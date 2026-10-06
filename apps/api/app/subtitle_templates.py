"""Versioned caption starters. Persist the full chosen style, never a mutable lookup."""
from functools import lru_cache
import json
import unicodedata
from pathlib import Path

from .production_models import SubtitleStyle

WORD_TIMED_MODES = frozenset({"word_highlight", "word_by_word", "karaoke"})
EXTENDED_MODES = frozenset({"word_by_word", "karaoke", "keyword_highlight"})
CATALOG = Path(__file__).resolve().parents[3] / "packages/contracts/subtitle-templates.v1.json"


@lru_cache(maxsize=1)
def load_templates() -> tuple[dict, ...]:
    document = json.loads(CATALOG.read_text(encoding="utf-8"))
    if document["version"] != "1.0":
        raise ValueError("unsupported subtitle template catalog")
    output = []
    seen = set()
    for item in document["templates"]:
        style = SubtitleStyle.model_validate(item["style"])
        if style.template_ref != item["template_ref"] or item["template_ref"] in seen:
            raise ValueError("invalid subtitle template identity")
        seen.add(item["template_ref"])
        output.append({**item, "style": style.model_dump(mode="json"),
                       "requires_word_timestamps": style.animation in WORD_TIMED_MODES})
    return tuple(output)


def template_catalog() -> dict:
    return {"version": "1.0", "render_contract_version": "2.3", "templates": list(load_templates())}


def validate_template_ref(style: SubtitleStyle) -> None:
    if style.template_ref and not any(t["template_ref"] == style.template_ref for t in load_templates()):
        raise ValueError("SUBTITLE_TEMPLATE_UNKNOWN: select a versioned available template")


def extended_subtitle_style(style: SubtitleStyle) -> bool:
    return bool(style.template_ref or style.keywords or style.animation in EXTENDED_MODES)


def render_subtitle_style(style: SubtitleStyle) -> dict:
    output = style.model_dump(mode="json")
    if not extended_subtitle_style(style):
        # Historical v2.0–2.2 manifests must not acquire new fields.
        output.pop("template_ref")
        output.pop("keywords")
    return output


def validate_preserved_alignment(previous: list[dict], cues: list) -> None:
    from .production_logic import ProductionContractError
    by_id = {cue["cue_id"]: cue for cue in previous}
    for cue in cues:
        if not cue.words:
            continue
        source = by_id.get(cue.cue_id)
        if not source or not source.get("words") or (
            unicodedata.normalize("NFC", cue.text) != unicodedata.normalize("NFC", source["text"])
            or cue.start_seconds != source["start_seconds"] or cue.end_seconds != source["end_seconds"]
            or [word.model_dump(mode="json") for word in cue.words] != source["words"]
        ):
            raise ProductionContractError("WORD_ALIGNMENT_STALE: clear word timestamps after editing text or timing")
