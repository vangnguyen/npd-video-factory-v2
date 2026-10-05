"""Canonical input projection using the existing content contract and native media intake."""
import hashlib
import json
from pathlib import Path
import re
import uuid
import sys
import zipfile
import xml.etree.ElementTree as ET

# Reuse the existing pure Pydantic contract. The installed voice SDK owns an
# unrelated `apps` package, so use the API's actual `app` namespace explicitly.
API_ROOT = Path(__file__).resolve().parents[2] / "apps/api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
from app.content_models import ContentDocument
from .contracts import Proposal, WorkflowError, digest, file_sha, normalize
from .media import display_filename, project_assets

DOCUMENT_TYPES = {"text/plain", "text/markdown", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
DOCUMENT_MAX_BYTES = 5 * 1024 * 1024


def validate_text(kind, text):
    if kind == "media":
        if text is not None and text != "":
            raise WorkflowError("MEDIA_INPUT_HAS_TEXT_SELECT_PROMPT_OR_SCRIPT", 400)
        return ""
    try:
        return ContentDocument(input_kind=kind, original_text=text).original_text
    except ValueError:
        raise WorkflowError("INPUT_KIND_OR_TEXT_INVALID_MAX_20000", 400) from None


def project_input(doc, version):
    from .asr import analysis_for_asset
    kind = doc.get("input_kind", "prompt")
    text = doc.get("prompt", "")
    texts = [] if not text else [{"kind": kind, "text": text, "source": "user",
                "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(), "version": version}]
    assets = project_assets(doc)
    result = {"schema_version": "project-input-v1", "version": version, "source": "local_user_intake",
              "text_inputs": texts, "image_assets": [a for a in assets if a["kind"] == "image"],
              "video_assets": [a for a in assets if a["kind"] == "video"],
              "document_assets": doc.get("documents", []), "metadata": {}}
    if kind == "script":
        workflow = "REVIEW_EXISTING_SCRIPT"
    elif texts or result["document_assets"]:
        workflow = "GENERATE_CONTENT_WITH_HUMAN_REVIEW"
    elif any((a.get("has_audio") or a.get("audio_present")) and not (analysis_for_asset(doc, a) or {}).get("transcript") for a in result["video_assets"]):
        workflow = "ASR_REQUIRED"
    elif any((analysis_for_asset(doc, a) or {}).get("transcript") for a in result["video_assets"]):
        workflow = "REVIEW_TRANSCRIPT"
    else:
        workflow = "MEDIA_REQUIRES_BRIEF"
    result["metadata"] = {"workflow": workflow, "mixed": sum(bool(result[k]) for k in
                ("text_inputs", "image_assets", "video_assets", "document_assets")) > 1,
                "untranscribed_video_audio": any((a.get("has_audio") or a.get("audio_present")) and not (analysis_for_asset(doc, a) or {}).get("transcript") for a in result["video_assets"]),
                "media_analysis": [{"asset_id": a["id"], "analysis_sha256": r["analysis_sha256"], "transcript_linked": bool(r.get("transcript"))}
                                   for a in assets if (r := analysis_for_asset(doc, a))]}
    result["hash"] = digest(result)
    return result


def provider_context(doc):
    from .asr import analysis_for_asset
    inputs = project_input(doc, 0)
    workflow = inputs["metadata"]["workflow"]
    if workflow == "ASR_REQUIRED":
        raise WorkflowError("ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT", 503)
    if workflow == "MEDIA_REQUIRES_BRIEF":
        raise WorkflowError("MEDIA_ONLY_CONTENT_REQUIRES_BRIEF_OR_SCRIPT", 400)
    parts = [doc.get("prompt", "")]
    for document in inputs["document_assets"]:
        parts.append("Tài liệu người dùng, chưa xác minh:\n" + document["extracted_text"])
    for asset in inputs["video_assets"]:
        record = analysis_for_asset(doc, asset)
        if record and record.get("transcript"):
            parts.append("Lời nói từ video nguồn do AssemblyAI nhận diện, có thể sai và chưa xác minh dữ kiện:\n" +
                         " ".join(s["text"] for s in record["transcript"]["segments"]))
    if inputs["image_assets"] or inputs["video_assets"]:
        parts.append("Media chỉ có mô tả kỹ thuật và transcript được nêu rõ nếu đã nhận diện. Không suy đoán nội dung từ tên file hoặc thông số ảnh/video.")
        parts.append(json.dumps([{k: a[k] for k in ("id", "kind", "width", "height", "duration_seconds") if k in a}
                      for a in inputs["image_assets"] + inputs["video_assets"]], ensure_ascii=False))
    text = "\n\n".join(p for p in parts if p)
    if len(text) > 20000:
        raise WorkflowError("INPUT_CONTEXT_EXCEEDS_20000_EDIT_EXPLICITLY", 400)
    return text


def transcript_script(doc):
    """Exact provider text is prepared for review without a generation call."""
    if doc.get("input_kind") != "media" or doc.get("prompt") or doc.get("documents"):
        return None
    from .asr import analysis_for_asset, pending_speech
    if pending_speech(doc):
        return None
    values = []
    for asset in project_assets(doc):
        record = analysis_for_asset(doc, asset)
        if record and record.get("transcript"):
            values.extend(s["text"] for s in record["transcript"]["segments"])
    return " ".join(values) if values else None


def existing_script(doc):
    text = normalize(doc["prompt"])
    units = re.split(r"(?<=[.!?])\s+", text)
    groups = [[] for _ in range(min(5, len(units)))]
    for index, unit in enumerate(units):
        groups[min(index * len(groups) // len(units), len(groups)-1)].append(unit)
    try:
        return Proposal.model_validate({"narration": text, "visual_brief": [
            {"scene": i+1, "visual": "Chọn media nguồn phù hợp và kiểm tra quyền sử dụng.",
             "on_screen_text": f"Đoạn {i+1:02}", "narration_excerpt": " ".join(group)}
            for i, group in enumerate(groups)], "facts_needing_source": ["Nội dung kịch bản do người dùng cung cấp cần được kiểm chứng trước khi duyệt."]}).model_dump()
    except ValueError:
        raise WorkflowError("EXISTING_SCRIPT_EXCEEDS_CURRENT_NARRATION_LIMIT_EDIT_EXPLICITLY", 400) from None


def ingest_document(config, source, content_type, filename):
    source = Path(source)
    if content_type not in DOCUMENT_TYPES or not 0 < source.stat().st_size <= DOCUMENT_MAX_BYTES:
        raise WorkflowError("DOCUMENT_TYPE_OR_SIZE_INVALID_MAX_5MB", 400)
    raw = source.read_bytes()
    try:
        if content_type.startswith("text/"):
            text = raw.decode("utf-8-sig")
            if "\x00" in text or any(ord(c) < 32 and c not in "\n\r\t" for c in text):
                raise ValueError()
            suffix = ".txt" if content_type == "text/plain" else ".md"
        else:
            if not zipfile.is_zipfile(source):
                raise ValueError()
            with zipfile.ZipFile(source) as archive:
                members = archive.infolist()
                if len(members) > 1000 or sum(m.file_size for m in members) > 25 * 1024 * 1024:
                    raise ValueError()
                if any(m.flag_bits & 1 for m in members):
                    raise ValueError()
                package = archive.read("[Content_Types].xml")
                xml = archive.read("word/document.xml")
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml or b"wordprocessingml.document.main+xml" not in package:
                    raise ValueError()
                tree = ET.fromstring(xml)
                namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                text = "\n".join("".join(n.text or "" for n in p.findall(".//w:t", namespace))
                                for p in tree.findall(".//w:p", namespace))
            suffix = ".docx"
        if not 1 <= len(text.strip()) <= 20000:
            raise ValueError()
    except (ValueError, UnicodeError, KeyError, zipfile.BadZipFile, ET.ParseError, RuntimeError):
        raise WorkflowError("DOCUMENT_CONTENT_INVALID_UTF8_TXT_MD_OR_DOCX_MAX_20000_CHARS", 400) from None
    directory = config.data_root / "documents"; directory.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex + suffix
    destination = directory / identifier
    with destination.open("xb") as dest:
        dest.write(raw)
    return {"id": identifier, "kind": "document", "filename": display_filename(filename),
            "mime_type": content_type, "sha256": file_sha(destination), "bytes": len(raw),
            "extracted_text": text, "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source": "immutable_user_upload", "version": 1}
