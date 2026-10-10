"""Immutable local image/video intake and one selected source per storyboard scene."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import shutil
from fractions import Fraction
import uuid
import copy
import sqlite3

from .contracts import WorkflowError, file_sha

IMAGE_MAX_BYTES = 15 * 1024 * 1024
VIDEO_MAX_BYTES = 250 * 1024 * 1024
MAX_ASSETS = 50
CONTENT_TYPES = {"image/jpeg", "image/png", "video/mp4", "video/quicktime"}


def _library_catalog(store, con=None):
    """Derive a durable library from existing immutable history, without a migration.

    Association removal keeps the historical metadata and bytes. Current projects
    only supply usage state; reading the library never upgrades old documents.
    """
    own = con is None
    if own:
        con = sqlite3.connect(store.db.resolve().as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
    try:
        current = con.execute('SELECT id,revision,document,created_at FROM projects ORDER BY id').fetchall()
        history = con.execute('SELECT project_id,revision,document,created_at FROM project_versions ORDER BY project_id,revision').fetchall()
        names, used = {}, {}
        for row in current:
            doc = json.loads(row['document']); names[row['id']] = doc.get('name', '')
            for binding in scene_bindings(doc):
                used.setdefault(binding['asset_id'], set()).add(row['id'])
        records = {}
        # The fallback covers older repositories with incomplete initial history.
        entries = [(r['project_id'], r['revision'], r['document'], r['created_at']) for r in history]
        entries += [(r['id'], r['revision'], r['document'], r['created_at']) for r in current]
        for project_id, revision, encoded, created_at in entries:
            doc = json.loads(encoded)
            for asset in project_assets(doc):
                identifier = asset.get('id')
                if not isinstance(identifier, str):
                    continue
                record = records.setdefault(identifier, {'metadata': copy.deepcopy(asset), 'source_projects': {},
                    'first_seen_at': created_at, 'metadata_conflict': False})
                immutable = ('sha256', 'kind', 'width', 'height', 'original_id', 'source_sha256', 'source_bytes', 'source_mime')
                if any(k in record['metadata'] and k in asset and record['metadata'][k] != asset[k] for k in immutable):
                    record['metadata_conflict'] = True
                record['source_projects'].setdefault(project_id, {'project_id': project_id,
                    'project_name': names.get(project_id, doc.get('name', '')), 'first_revision': revision})
                record['first_seen_at'] = min(record['first_seen_at'], created_at)
        for identifier, record in records.items():
            record['used_in_project_ids'] = sorted(used.get(identifier, set()))
        return records
    finally:
        if own:
            con.close()


def _library_path(root, folder, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', identifier):
        raise WorkflowError('INVALID_MEDIA_ID', 400)
    directory = (Path(root) / folder).resolve()
    path = directory / identifier
    if path.is_symlink() or path.resolve().parent != directory:
        raise WorkflowError('LIBRARY_SOURCE_PATH_INVALID', 400)
    return path


def _verify_library_record(store, record):
    asset = record['metadata']
    if record['metadata_conflict']:
        raise WorkflowError('LIBRARY_SOURCE_METADATA_CONFLICT')
    expected = asset.get('sha256')
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected) or asset.get('kind') not in {'image', 'video', 'audio', 'subtitle'}:
        raise WorkflowError('LIBRARY_SOURCE_METADATA_INVALID')
    path = _library_path(store.root, 'assets', asset['id'])
    if not path.is_file() or file_sha(path) != expected or ('bytes' in asset and asset['bytes'] != path.stat().st_size):
        raise WorkflowError('LIBRARY_SOURCE_CHANGED_OR_MISSING')
    if asset.get('original_id'):
        original = _library_path(store.root, 'originals', asset['original_id'])
        if (not original.is_file() or not asset.get('source_sha256') or file_sha(original) != asset['source_sha256']
                or ('source_bytes' in asset and original.stat().st_size != asset['source_bytes'])):
            raise WorkflowError('LIBRARY_ORIGINAL_CHANGED_OR_MISSING')
    return path


def library_asset(store, identifier, *, con=None):
    record = _library_catalog(store, con).get(identifier)
    if record is None:
        raise WorkflowError('LIBRARY_ASSET_NOT_FOUND', 404)
    _verify_library_record(store, record)
    return record


def library_file(store, identifier, *, thumbnail=False):
    record = library_asset(store, identifier)
    asset = record['metadata']; source = _verify_library_record(store, record)
    if not thumbnail:
        return source, asset['kind'] == 'video'
    if asset.get('thumbnail_id'):
        path = _library_path(store.root, 'assets', asset['thumbnail_id'])
        if not path.is_file():
            raise WorkflowError('LIBRARY_THUMBNAIL_NOT_FOUND', 404)
        return path, False
    if asset['kind'] == 'image':
        return source, False  # Legacy intake did not produce separate thumbnails.
    raise WorkflowError('LIBRARY_THUMBNAIL_NOT_FOUND', 404)


def library_assets(store, *, kind='all', query='', page=1, page_size=24):
    if not isinstance(kind, str) or kind not in {'all', 'visual', 'image', 'video', 'audio', 'subtitle'} or not isinstance(query, str) or len(query) > 200:
        raise WorkflowError('ASSET_LIBRARY_FILTER_INVALID', 400)
    if type(page) is not int or not 1 <= page <= 1_000_000 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise WorkflowError('ASSET_LIBRARY_PAGE_INVALID', 400)
    needle = query.strip().casefold()
    records = [r for r in _library_catalog(store).values() if (kind == 'all' or r['metadata'].get('kind') == kind or kind == 'visual' and r['metadata'].get('kind') in {'image','video'})
               and (not needle or needle in str(r['metadata'].get('filename', '')).casefold()
                    or needle in str(r['metadata'].get('title', '')).casefold())]
    records.sort(key=lambda r: (r['first_seen_at'], r['metadata']['id']), reverse=True)
    items = []
    for record in records[(page-1)*page_size:page*page_size]:
        asset = copy.deepcopy(record['metadata']); identifier = asset['id']
        try:
            source = _verify_library_record(store, record)
            available, issue = True, None
            asset.setdefault('bytes', source.stat().st_size)
        except WorkflowError as error:
            available, issue = False, error.code
        items.append({**asset, 'available': available, 'availability_issue': issue,
            'source_project_ids': sorted(record['source_projects']),
            'used': bool(record['used_in_project_ids']), 'used_in_project_ids': record['used_in_project_ids'],
            'first_seen_at': record['first_seen_at'],
            'provenance': {'origin': 'retained_project_asset_history', 'source_projects': list(record['source_projects'].values()),
                'original_bytes_preserved': bool(asset.get('original_id')), 'metadata_conflict': record['metadata_conflict']},
            'thumbnail_url': f'/api/assets/{identifier}/thumbnail' if asset.get('thumbnail_id') or asset.get('kind') == 'image' else None,
            'file_url': f'/api/assets/{identifier}/file'})
    return {'schema_version': 'windows-native-asset-library-v1', 'items': items, 'total': len(records),
            'page': page, 'page_size': page_size, 'pages': (len(records)+page_size-1)//page_size,
            'project_association_removal_deletes_original': False}


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
    if asset.get("original_id"):
        (config.data_root / "originals" / asset["original_id"]).unlink(missing_ok=True)


def ingest_media(config, source, content_type, filename, *, rights_confirmed, illustration, preserve_alpha=False):
    from PIL import Image, ImageOps
    if rights_confirmed is not True or not isinstance(illustration, bool):
        raise WorkflowError("MEDIA_RIGHTS_CONFIRMATION_REQUIRED", 400)
    if content_type not in CONTENT_TYPES:
        raise WorkflowError("MEDIA_TYPE_NOT_SUPPORTED", 400)
    if type(preserve_alpha) is not bool or preserve_alpha and content_type!="image/png":
        raise WorkflowError("LOGO_PNG_REQUIRED",400)
    size = source.stat().st_size
    video = content_type.startswith("video/")
    if not 0 < size <= (VIDEO_MAX_BYTES if video else IMAGE_MAX_BYTES):
        raise WorkflowError("MEDIA_FILE_TOO_LARGE_OR_EMPTY", 400)
    directory = config.data_root / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    asset = {"id": identifier + (".mp4" if video else ".png" if preserve_alpha else ".jpg"), "thumbnail_id": identifier + ".thumb.jpg",
             "filename": display_filename(filename), "kind": "video" if video else "image",
             "rights_confirmed": True, "illustration": illustration,'source_type':'user_upload','rights_status':'unknown',
             'license':None,'provider':'native-local-upload','source_reference':'upload://'+identifier,'generation_provenance':{}}
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
            shutil.copyfile(source, dest)
            frame_rate = stream.get("avg_frame_rate", "0/0")
            asset.update(width=width, height=height, duration_seconds=duration, video_stream_index=stream["index"], original_audio="muted",
                         has_audio=any(s["codec_type"] == "audio" for s in probe["streams"]),
                         fps=float(Fraction(frame_rate)) if frame_rate != "0/0" else None)
        else:
            try:
                Image.MAX_IMAGE_PIXELS = 40_000_000
                with Image.open(source) as original:
                    if original.format != {"image/jpeg": "JPEG", "image/png": "PNG"}[content_type] or original.width * original.height > 40_000_000:
                        raise ValueError()
                    original.load()
                    has_alpha="A" in original.getbands() or "transparency" in original.info
                    image = ImageOps.exif_transpose(original).convert("RGBA" if preserve_alpha else "RGB")
                    if min(image.size) < (32 if preserve_alpha else 240):
                        raise ValueError()
                image.save(dest,format="PNG" if preserve_alpha else "JPEG",quality=95)
                asset.update(width=image.width, height=image.height)
                if preserve_alpha:asset.update(has_alpha=has_alpha,content_type="image/png")
                image.thumbnail((480, 480), Image.Resampling.LANCZOS)
                image.convert("RGB").save(thumbnail, quality=85)
            except Exception:
                raise WorkflowError("INVALID_IMAGE_JPEG_PNG_MAX_15MB_40MP_MIN_240PX", 400) from None
        asset["sha256"] = file_sha(dest)
        asset["bytes"] = dest.stat().st_size
        original = config.data_root / "originals"
        original.mkdir(parents=True, exist_ok=True)
        extension = {"image/jpeg": ".jpg", "image/png": ".png", "video/mp4": ".mp4", "video/quicktime": ".mov"}[content_type]
        asset["original_id"] = identifier + extension
        shutil.copyfile(source, original / asset["original_id"])
        asset.update(source_sha256=file_sha(source), source_bytes=size, source_mime=content_type,
                     source="immutable_user_upload", version=1)
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
