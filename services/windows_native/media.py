"""Immutable local image/video intake and one selected source per storyboard scene."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import uuid

from .contracts import WorkflowError, file_sha

IMAGE_MAX_BYTES = 15 * 1024 * 1024
VIDEO_MAX_BYTES = 250 * 1024 * 1024
MAX_ASSETS = 50
CONTENT_TYPES = {"image/jpeg", "image/png", "video/mp4", "video/quicktime"}


def project_assets(document):
    # Read legacy snapshots without rewriting their approved bytes or audit history.
    assets = document.get("assets")
    if assets is None:
        assets = [document["asset"]] if document.get("asset") else []
    return [{**asset, "kind": asset.get("kind", "image"),
             "filename": asset.get("filename", "Ảnh đã lưu"),
             "rights_confirmed": asset.get("rights_confirmed", True),
             "illustration": asset.get("illustration", False)} for asset in assets]


def scene_bindings(document):
    if "scene_media" in document:
        return document["scene_media"]
    legacy = document.get("asset")
    scenes = (document.get("proposal") or {}).get("visual_brief", [])
    return [{"scene": scene["scene"], "asset_id": legacy["id"]} for scene in scenes] if legacy else []


def validate_bindings(document, *, complete=False):
    assets = project_assets(document)
    identifiers = {asset["id"] for asset in assets}
    if len(identifiers) != len(assets):
        raise WorkflowError("DUPLICATE_MEDIA_ID", 400)
    scenes = {scene["scene"] for scene in (document.get("proposal") or {}).get("visual_brief", [])}
    bindings = scene_bindings(document)
    if not isinstance(bindings, list):
        raise WorkflowError("INVALID_SCENE_MEDIA", 400)
    selected = set()
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {"scene", "asset_id"}:
            raise WorkflowError("INVALID_SCENE_MEDIA", 400)
        scene = binding["scene"]
        if type(scene) is not int or scene not in scenes or scene in selected:
            raise WorkflowError("INVALID_SCENE_MEDIA", 400)
        if not isinstance(binding["asset_id"], str) or binding["asset_id"] not in identifiers:
            raise WorkflowError("SCENE_MEDIA_NOT_IN_PROJECT", 400)
        selected.add(scene)
    if complete and (not scenes or selected != scenes):
        raise WorkflowError("EACH_SCENE_REQUIRES_ONE_IMAGE_OR_VIDEO")
    return bindings


def selected_media(document):
    bindings = validate_bindings(document, complete=True)
    assets = {asset["id"]: asset for asset in project_assets(document)}
    chosen = {binding["scene"]: assets[binding["asset_id"]] for binding in bindings}
    if any(a["kind"] not in {"image", "video"} or a["rights_confirmed"] is not True for a in chosen.values()):
        raise WorkflowError("MEDIA_RIGHTS_CONFIRMATION_REQUIRED", 400)
    return chosen


def media_path(config, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", identifier):
        raise WorkflowError("INVALID_MEDIA_ID", 400)
    return config.data_root / "assets" / identifier


def verify_selected_files(config, document):
    chosen = selected_media(document)
    for asset in {a["id"]: a for a in chosen.values()}.values():
        path = media_path(config, asset["id"])
        if not path.is_file() or file_sha(path) != asset["sha256"]:
            raise WorkflowError("SOURCE_MEDIA_CHANGED_OR_MISSING")
    return chosen


def display_filename(value):
    value = str(value or "Media").replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(c for c in value if c.isprintable())[:200] or "Media"


def discard_media(config, asset):
    # Only files created by this upload, under the generated asset namespace.
    for key in ("id", "thumbnail_id"):
        if asset.get(key):
            media_path(config, asset[key]).unlink(missing_ok=True)


def ingest_media(config, source, content_type, filename, *, rights_confirmed, illustration):
    from PIL import Image, ImageOps
    if rights_confirmed is not True or not isinstance(illustration, bool):
        raise WorkflowError("MEDIA_RIGHTS_CONFIRMATION_REQUIRED", 400)
    if content_type not in CONTENT_TYPES:
        raise WorkflowError("MEDIA_TYPE_NOT_SUPPORTED", 400)
    size = source.stat().st_size
    video = content_type.startswith("video/")
    if not 0 < size <= (VIDEO_MAX_BYTES if video else IMAGE_MAX_BYTES):
        raise WorkflowError("MEDIA_FILE_TOO_LARGE_OR_EMPTY", 400)
    directory = config.data_root / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    asset = {"id": identifier + (".mp4" if video else ".jpg"), "thumbnail_id": identifier + ".thumb.jpg",
             "filename": display_filename(filename), "kind": "video" if video else "image",
             "rights_confirmed": True, "illustration": illustration}
    dest, thumbnail = media_path(config, asset["id"]), media_path(config, asset["thumbnail_id"])
    try:
        if video:
            result = subprocess.run([str(config.ffmpeg_bin / "ffprobe.exe"), "-v", "error",
                "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format", "-of", "json", str(source)],
                capture_output=True, timeout=30)
            if result.returncode:
                raise WorkflowError("INVALID_VIDEO_MP4_MOV", 400)
            probe = json.loads(result.stdout)
            if not {"mov", "mp4"}.intersection(probe.get("format", {}).get("format_name", "").split(",")):
                raise WorkflowError("INVALID_VIDEO_MP4_MOV", 400)
            streams = [s for s in probe["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")]
            if not streams:
                raise WorkflowError("VIDEO_STREAM_REQUIRED", 400)
            stream = streams[0]
            duration = float(probe["format"]["duration"])
            width, height = stream["width"], stream["height"]
            if not 0 < duration <= 600 or not min(width, height) >= 64 or width * height > 40_000_000:
                raise WorkflowError("VIDEO_LIMIT_10_MINUTES_40MP", 400)
            decoded = subprocess.run([str(config.ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-xerror",
                "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", f"0:{stream['index']}", "-an",
                "-f", "null", "-"], capture_output=True, timeout=120)
            if decoded.returncode:
                raise WorkflowError("VIDEO_DECODE_FAILED", 400)
            thumb = subprocess.run([str(config.ffmpeg_bin / "ffmpeg.exe"), "-v", "error", "-nostdin", "-n",
                "-protocol_whitelist", "file,pipe", "-ss", str(min(.5, duration / 2)), "-i", str(source),
                "-map", f"0:{stream['index']}", "-frames:v", "1", "-vf", "scale=480:480:force_original_aspect_ratio=decrease", str(thumbnail)],
                capture_output=True, timeout=30)
            if thumb.returncode or not thumbnail.is_file():
                raise WorkflowError("VIDEO_THUMBNAIL_FAILED", 400)
            source.replace(dest)
            asset.update(width=width, height=height, duration_seconds=duration, video_stream_index=stream["index"], original_audio="muted")
        else:
            try:
                Image.MAX_IMAGE_PIXELS = 40_000_000
                with Image.open(source) as original:
                    if original.format not in {"JPEG", "PNG"} or original.width * original.height > 40_000_000:
                        raise ValueError()
                    original.load()
                    image = ImageOps.exif_transpose(original).convert("RGB")
                    if min(image.size) < 240:
                        raise ValueError()
                image.save(dest, quality=95)
                asset.update(width=image.width, height=image.height)
                image.thumbnail((480, 480), Image.Resampling.LANCZOS)
                image.save(thumbnail, quality=85)
            except Exception:
                raise WorkflowError("INVALID_IMAGE_JPEG_PNG_MAX_15MB_40MP_MIN_240PX", 400) from None
        asset["sha256"] = file_sha(dest)
        asset["bytes"] = dest.stat().st_size
        return asset
    except subprocess.TimeoutExpired:
        discard_media(config, asset)
        raise WorkflowError("MEDIA_VALIDATION_TIMEOUT", 400) from None
    except (KeyError, TypeError, ValueError):
        discard_media(config, asset)
        raise WorkflowError("INVALID_VIDEO_MP4_MOV" if video else "INVALID_IMAGE_JPEG_PNG_MAX_15MB_40MP_MIN_240PX", 400) from None
    except Exception:
        discard_media(config, asset)
        raise
