"""Native adapter for shared Auto Edit evidence, in the existing project store.

Local measurements reuse API domain/provider code, never its database or worker.
ASR consumes an already saved, hash-bound Native receipt. This job never calls a
speech/AI provider. Missing speech evidence disables silence decisions.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
import json
import math
import unicodedata
import uuid
from types import SimpleNamespace

from .contracts import WorkflowError, digest, file_sha
from .hardening import Artifacts, durable_json
from .media import media_path, project_assets
from .asr import analysis_for_asset
from .ingestion import API_ROOT  # Installs the existing pure-contract namespace.
from app.auto_edit_logic import build_highlights, build_scenes, build_silence_decisions
from app.auto_edit_models import (
    AutoEditAnalysisRead, AutoEditAnalysisRequest, TranscriptEditRequest, TranscriptRead,
)
from app.auto_edit_providers import (
    FFmpegMediaSignalProvider, FFprobeMediaProbe, MediaSignals,
    ProviderSegment, ProviderTranscript, ProviderWord, require_positive_duration_transcript,
)
from app.scene_evidence import combine_scene_evidence

ALGORITHM = "native-auto-edit-evidence-v1"
MAX_ANALYSES = 200
MAX_TRANSCRIPT_VERSIONS = 300


def stamp():
    return datetime.now(timezone.utc).isoformat()


def asset_reference(asset):
    return "ast_" + digest(asset["id"])[:32]


def fingerprint(project_id, document, asset):
    record = analysis_for_asset(document, asset)
    return digest({"algorithm": ALGORITHM, "project_id": project_id,
        "asset_id": asset["id"], "source_sha256": asset["sha256"],
        "asr_analysis_sha256": record["analysis_sha256"] if record else None,
        "signals": FFmpegMediaSignalProvider.algorithm_version,
        "configuration": AutoEditAnalysisRequest(asset_id=asset_reference(asset)).model_dump(mode="json")})


def pending(document, project_id):
    saved = document.get("auto_edit_analyses", [])
    return [asset for asset in project_assets(document) if asset.get("kind") == "video"
        and not any(item.get("native_asset_id") == asset["id"] and
            item.get("analysis", {}).get("fingerprint") == fingerprint(project_id, document, asset)
            for item in saved)]


def _provider_transcript(raw, duration):
    """Validate saved provider intervals; do not invent or silently fix timing."""
    segments = []
    previous_end = 0.
    for value in raw["segments"]:
        words = tuple(ProviderWord(**word) for word in value["words"])
        segment = ProviderSegment(**{**value, "words": words})
        times = [segment.start_seconds, segment.end_seconds,
                 *(time for word in words for time in (word.start_seconds, word.end_seconds))]
        if any(type(time) not in (int, float) or not math.isfinite(time) for time in times):
            raise ValueError("nonfinite transcript timestamp")
        if segment.start_seconds < previous_end - 1e-6 or segment.end_seconds > duration + .05:
            raise ValueError("transcript segment is outside ordered source bounds")
        previous_end = segment.end_seconds
        segments.append(segment)
    transcript = ProviderTranscript(language=raw["language"], confidence=raw["confidence"],
        segments=tuple(segments), provenance=copy.deepcopy(raw["provenance"]))
    require_positive_duration_transcript(transcript)
    return transcript


def normalize_transcript(raw, *, analysis_id, asset_id, duration, created_at):
    value = _provider_transcript(raw, duration)
    segments, ordinal = [], 0
    for index, segment in enumerate(value.segments):
        words = []
        for word in segment.words:
            words.append({"word_id": "wrd_" + digest([analysis_id, ordinal])[:24],
                "ordinal": ordinal, "start_seconds": word.start_seconds, "end_seconds": word.end_seconds,
                "text": unicodedata.normalize("NFC", word.text), "confidence": word.confidence})
            ordinal += 1
        segments.append({"segment_id": "seg_" + digest([analysis_id, index])[:24], "ordinal": index,
            "start_seconds": segment.start_seconds, "end_seconds": segment.end_seconds,
            "text": unicodedata.normalize("NFC", segment.text), "speaker": segment.speaker,
            "confidence": segment.confidence, "words": words})
    return TranscriptRead(transcript_id="trn_" + digest(analysis_id)[:24], analysis_id=analysis_id,
        asset_id=asset_id, version=1, is_original_evidence=True,
        provider_key=str(value.provenance.get("provider") or "saved-native-asr"),
        language=value.language, confidence=value.confidence, segments=segments,
        provenance={**value.provenance, "native_saved_receipt_reused": True,
            "source_media_mutated": False, "remote_calls": 0, "timing_rewrite_applied": False},
        created_at=created_at)


def downstream(transcript):
    if transcript is None:
        return None
    raw = {"language": transcript.language, "confidence": transcript.confidence,
        "provenance": transcript.provenance, "segments": [
            {"start_seconds": segment.start_seconds, "end_seconds": segment.end_seconds,
                "text": segment.text, "speaker": segment.speaker, "confidence": segment.confidence,
                "words": [{"start_seconds": word.start_seconds, "end_seconds": word.end_seconds,
                    "text": word.text, "confidence": word.confidence} for word in segment.words]}
            for segment in transcript.segments]}
    return require_positive_duration_transcript(_provider_transcript(raw, float("inf")))


def make_analysis(project_id, document, asset, metadata, signals):
    key = fingerprint(project_id, document, asset)
    analysis_id = "ana_" + key[:24]
    record = analysis_for_asset(document, asset)
    created_at = stamp()
    configuration = AutoEditAnalysisRequest(asset_id=asset_reference(asset))
    try:
        transcript = normalize_transcript(record["transcript"], analysis_id=analysis_id,
            asset_id=configuration.asset_id, duration=float(metadata.duration_seconds), created_at=created_at
            ) if record and record.get("transcript") else None
    except (ValueError, TypeError, KeyError):
        raise WorkflowError("AUTO_EDIT_SAVED_TRANSCRIPT_INVALID") from None
    scenes = build_scenes(duration=float(metadata.duration_seconds), signals=signals, transcript=downstream(transcript))
    for scene in scenes:
        scene["scene_id"] = "scn_" + digest([analysis_id, scene["ordinal"]])[:24]
    decisions = build_silence_decisions(signals=signals, transcript=downstream(transcript), config=configuration) if transcript else []
    for index, decision in enumerate(decisions):
        decision["decision_id"] = "sil_" + digest([analysis_id, index])[:24]
    highlights = build_highlights(scenes=scenes, top_k=configuration.top_highlights)
    for item in highlights:
        item["highlight_id"] = "hig_" + digest([analysis_id, item["rank"]])[:24]
        item["scene_id"] = scenes[item.pop("scene_ordinal")]["scene_id"]
    value = AutoEditAnalysisRead(analysis_id=analysis_id, workspace_id="native-local",
        project_id="prj_" + project_id, project_version_id=None, asset_id=configuration.asset_id,
        status="succeeded", fingerprint=key, configuration=configuration, source_media=metadata,
        transcript=transcript, scenes=scenes, silence_decisions=decisions, highlights=highlights,
        error_code=None, provenance={"algorithm": ALGORITHM, "source_asset_checksum": asset["sha256"],
            "native_asset_id": asset["id"], "saved_asr_analysis_sha256": record["analysis_sha256"] if record else None,
            "media_signals": {**signals.provenance, "waveform": signals.waveform, "visual": signals.visual,
                "silence_intervals": signals.silence_intervals},
            "transcript_status": "saved_receipt" if transcript else "NOT_CONFIGURED_OR_NOT_ANALYZED",
            "silence_cuts_blocked_without_transcript": bool(metadata.audio_codec and not transcript),
            "provider_calls": 0, "paid_external_call": False, "human_review_required": True,
            "source_media_mutated": False, "canonical_timeline_mutated": False},
        created_at=created_at, updated_at=created_at)
    result = {"native_asset_id": asset["id"], "analysis": value.model_dump(mode="json")}
    result["sha256"] = digest(result)
    return result


def validate_sources(config, job):
    for asset in pending(job['snapshot']['document'], job['project_id']):
        source = media_path(config, asset['id'])
        if not source.is_file() or file_sha(source) != asset['sha256']:
            raise WorkflowError('SOURCE_MEDIA_CHANGED_OR_MISSING')


def analyze(config, job, out, stage):
    document = job["snapshot"]["document"]
    validate_sources(config, job)
    records = []
    for asset in pending(document, job["project_id"]):
        source = media_path(config, asset["id"])
        if not source.is_file() or file_sha(source) != asset["sha256"]:
            raise WorkflowError("SOURCE_MEDIA_CHANGED_OR_MISSING")
        stage("auto_edit_local_measurements")
        async def measure():
            metadata = await FFprobeMediaProbe(str(config.ffmpeg_bin / "ffprobe.exe")).probe(
                source, detected_content_type="video/mp4", media_kind="video")
            if not metadata.duration_seconds or not 0 < metadata.duration_seconds <= 600:
                raise WorkflowError("AUTO_EDIT_SOURCE_DURATION_INVALID")
            signals = await FFmpegMediaSignalProvider(str(config.ffmpeg_bin / "ffmpeg.exe")).analyze(
                source, metadata=metadata, silence_threshold_db=-35., minimum_silence_duration=.5)
            return metadata, signals
        metadata, signals = asyncio.run(measure())
        if file_sha(source) != asset["sha256"]:
            raise WorkflowError("SOURCE_MEDIA_CHANGED_OR_MISSING")
        records.append(make_analysis(job["project_id"], document, asset, metadata, signals))
    result = {"auto_edit_analyses": records, "provider_calls": 0,
        "source_media_mutated": False, "human_review_required": True}
    path = out / "auto-edit-analysis.json"
    durable_json(path, result)
    Artifacts(out, job).commit("auto_edit_analysis", [path], result)
    return result


def validate_record(record, project_id, document, asset, *, require_current=True):
    if set(record) != {"native_asset_id", "analysis", "sha256"} or record["sha256"] != digest(
            {key: value for key, value in record.items() if key != "sha256"}):
        raise WorkflowError("AUTO_EDIT_ANALYSIS_CHANGED")
    value = AutoEditAnalysisRead.model_validate(record["analysis"])
    if value.project_id != "prj_" + project_id or record["native_asset_id"] != asset["id"] or value.asset_id != asset_reference(asset):
        raise WorkflowError("AUTO_EDIT_ANALYSIS_SOURCE_MISMATCH")
    if value.provenance.get("source_asset_checksum") != asset["sha256"] or (require_current and
            value.fingerprint != fingerprint(project_id, document, asset)):
        raise WorkflowError("AUTO_EDIT_ANALYSIS_STALE")
    return value


def selected_transcript(document, analysis):
    versions = [TranscriptRead.model_validate(value) for value in document.get("auto_edit_transcripts", [])
        if value.get("analysis_id") == analysis.analysis_id]
    if analysis.transcript:
        versions.append(analysis.transcript)
    return max(versions, key=lambda value: value.version) if versions else None


def view(store, project_id):
    project = store.get(project_id)
    document = project["document"]
    assets = {asset["id"]: asset for asset in project_assets(document)}
    result = []
    for record in document.get("auto_edit_analyses", []):
        asset = assets.get(record["native_asset_id"])
        if asset is None:
            continue
        analysis = validate_record(record, project_id, document, asset, require_current=False)
        if analysis.fingerprint != fingerprint(project_id, document, asset):
            continue
        transcript = selected_transcript(document, analysis)
        selected = analysis.model_copy(update={"transcript": transcript})
        if transcript:
            signals = MediaSignals((), tuple(tuple(interval) for interval in
                analysis.provenance['media_signals'].get('silence_intervals', [])), {})
            decisions = build_silence_decisions(signals=signals, transcript=downstream(transcript), config=analysis.configuration)
            for index, decision in enumerate(decisions):
                decision['decision_id'] = 'sil_' + digest([analysis.analysis_id, index])[:24]
            from app.auto_edit_models import SilenceDecisionRead
            selected = selected.model_copy(update={'silence_decisions': [SilenceDecisionRead.model_validate(value) for value in decisions]})
        fused = combine_scene_evidence(selected, SimpleNamespace(checksum_sha256=asset["sha256"]))
        scenes = [value.model_dump(mode="json") for value in fused]
        for scene in scenes:
            scene["evidence"]["transcript_segment_count"] = len(scene["evidence"]["transcript_segment_ids"])
        result.append({"native_asset_id": asset["id"], "filename": asset["filename"],
            "analysis": selected.model_dump(mode="json"), "scenes": scenes,
            "highlights": build_highlights(scenes=scenes, top_k=5),
            "transcript_history": [value.model_dump(mode="json") for value in
                ([analysis.transcript] if analysis.transcript else []) + [TranscriptRead.model_validate(value)
                    for value in document.get("auto_edit_transcripts", []) if value["analysis_id"] == analysis.analysis_id]],
            "timeline_application_required": True})
    return {"project_id": project_id, "revision": project["revision"], "analyses": result,
        "pending_asset_ids": [asset["id"] for asset in pending(document, project_id)],
        "provider_calls": 0, "canonical_timeline_mutated": False,
        "source_timeline_version": (document.get('canonical_timeline') or {}).get('version') if
            (document.get('canonical_timeline') or {}).get('snapshot', {}).get('metadata', {}).get('native_auto_edit_schema') else None}


def save_result(store, con, project, result):
    """Called inside the existing job-finish transaction; original evidence is append-only."""
    document = project["document"]
    assets = {asset["id"]: asset for asset in project_assets(document)}
    incoming = result["auto_edit_analyses"]
    ids = [value["analysis"]["analysis_id"] for value in incoming]
    if len(set(ids)) != len(ids):
        raise WorkflowError("AUTO_EDIT_DUPLICATE_ANALYSIS_RESULT")
    for record in incoming:
        asset = assets.get(record["native_asset_id"])
        if asset is None:
            raise WorkflowError("AUTO_EDIT_ANALYSIS_SOURCE_MISMATCH")
        validate_record(record, project["id"], document, asset)
    old = document.get("auto_edit_analyses", [])
    existing = {value["analysis"]["analysis_id"]: value for value in old}
    for record in incoming:
        if record["analysis"]["analysis_id"] in existing and record != existing[record["analysis"]["analysis_id"]]:
            raise WorkflowError("AUTO_EDIT_IMMUTABLE_ANALYSIS_CONFLICT")
    added = [record for record in incoming if record["analysis"]["analysis_id"] not in existing]
    if len(old) + len(added) > MAX_ANALYSES:
        raise WorkflowError("AUTO_EDIT_ANALYSIS_HISTORY_LIMIT")
    document["auto_edit_analyses"] = old + added
    _save(store, con, project, document, "auto_edit_analysis_saved", {"analysis_ids": ids})


def _save(store, con, project, document, action, details, *, timeline_mutated=False):
    from .store import now
    con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
        (project["revision"] + 1, json.dumps(document, ensure_ascii=False), now(), project["id"]))
    store.version(con, project["id"])
    store.event(con, project["id"], action, {**details, "revision": project["revision"] + 1,
        "provider_calls": 0, "approval_invalidated": True, "canonical_timeline_mutated": timeline_mutated})


def edit_transcript(store, project_id, revision, analysis_id, body):
    try:
        payload = TranscriptEditRequest.model_validate(body)
    except ValueError:
        raise WorkflowError("AUTO_EDIT_TRANSCRIPT_EDIT_INVALID", 400) from None
    with store.transaction() as con:
        project = store.editable(con, project_id, revision)
        document = project["document"]
        from .auto_edit_timeline import is_auto_edit, validate_document, sync_transcript
        source_timeline = is_auto_edit(document)
        if source_timeline:
            state = validate_document(document)
            if payload.expected_timeline_version != state['version']:
                raise WorkflowError('AUTO_EDIT_TIMELINE_VERSION_CHANGED')
        elif payload.expected_timeline_version is not None:
            raise WorkflowError("AUTO_EDIT_TIMELINE_APPLICATION_NOT_AVAILABLE", 400)
        record = next((value for value in document.get("auto_edit_analyses", [])
            if value["analysis"]["analysis_id"] == analysis_id), None)
        asset = next((asset for asset in project_assets(document)
            if record and asset["id"] == record["native_asset_id"]), None)
        if record is None or asset is None:
            raise WorkflowError("AUTO_EDIT_ANALYSIS_NOT_FOUND", 404)
        analysis = validate_record(record, project_id, document, asset)
        current = selected_transcript(document, analysis)
        if current is None:
            raise WorkflowError("AUTO_EDIT_TRANSCRIPT_NOT_AVAILABLE", 400)
        if payload.expected_version != current.version:
            raise WorkflowError("AUTO_EDIT_TRANSCRIPT_VERSION_CHANGED")
        versions = ([analysis.transcript] if analysis.transcript else []) + [TranscriptRead.model_validate(value)
            for value in document.get("auto_edit_transcripts", []) if value["analysis_id"] == analysis_id]
        base = next((value for value in versions if value.transcript_id == payload.base_transcript_id), None) if payload.base_transcript_id else current
        if base is None:
            raise WorkflowError("AUTO_EDIT_TRANSCRIPT_BASE_NOT_FOUND", 400)
        edits = {value.segment_id: unicodedata.normalize("NFC", value.text) for value in payload.segments}
        if not set(edits) <= {value.segment_id for value in base.segments}:
            raise WorkflowError("AUTO_EDIT_TRANSCRIPT_SEGMENT_NOT_FOUND", 400)
        segments = []
        changed = []
        for segment in base.segments:
            value = segment.model_dump(mode="json")
            text = edits.get(segment.segment_id, segment.text)
            if text != segment.text:
                changed.append(segment.segment_id)
                value.update(text=text, words=[], confidence=None)
            value["segment_id"] = "seg_" + uuid.uuid4().hex[:24]
            for word in value["words"]:
                word["word_id"] = "wrd_" + uuid.uuid4().hex[:24]
            segments.append(value)
        if changed or base.transcript_id != current.transcript_id:
            history = document.get("auto_edit_transcripts", [])
            if len(history) >= MAX_TRANSCRIPT_VERSIONS:
                raise WorkflowError("AUTO_EDIT_TRANSCRIPT_HISTORY_LIMIT")
            derived = TranscriptRead(transcript_id="trn_" + uuid.uuid4().hex[:24], analysis_id=analysis_id,
                asset_id=current.asset_id, version=current.version + 1, is_original_evidence=False,
                provider_key=base.provider_key, language=base.language, confidence=None, segments=segments,
                provenance={**copy.deepcopy(base.provenance), "human_edit": True, "actor_ref": "native-session-owner",
                    "derived_from_transcript_id": base.transcript_id, "changed_segment_ids": changed,
                    "word_timestamp_policy": "discard_for_changed_text", "edit_note": payload.note,
                    "source_media_mutated": False, "remote_calls": 0, "timeline_application_required": True},
                created_at=stamp())
            document["auto_edit_transcripts"] = history + [derived.model_dump(mode="json")]
            if source_timeline:
                sync_transcript(document, base, derived)
            _save(store, con, project, document, "auto_edit_transcript_version_saved", {
                "analysis_id": analysis_id, "transcript_id": derived.transcript_id, "version": derived.version}, timeline_mutated=source_timeline)
    return view(store, project_id)
