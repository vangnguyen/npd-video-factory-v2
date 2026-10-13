"""Atomic SQL transcript word revisions and canonical subtitle synchronization."""
from __future__ import annotations

import copy
import math
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from .auto_edit_db import AutoEditAnalysisORM, TranscriptORM, TranscriptSegmentORM, TranscriptWordORM
from .auto_edit_models import TranscriptRead
from .db import AssetORM, VideoProjectORM
from .timeline_db import TimelineORM, TimelineVersionORM
from .timeline_models import TimelineClip, TimelineSnapshot
from .timeline_repository import TimelineConflictError, TimelineRepository
from .transcript_word_review import WordReview, revised


class TranscriptWordEditConflict(ValueError):
    pass


async def _read_transcript(session, row):
    segments = (await session.scalars(select(TranscriptSegmentORM).where(
        TranscriptSegmentORM.transcript_id == row.transcript_id).order_by(TranscriptSegmentORM.ordinal))).all()
    words = (await session.scalars(select(TranscriptWordORM).where(
        TranscriptWordORM.transcript_id == row.transcript_id).order_by(TranscriptWordORM.ordinal))).all()
    return TranscriptRead(
        transcript_id=row.transcript_id, analysis_id=row.analysis_id, asset_id=row.asset_id,
        version=row.version, is_original_evidence=row.is_original_evidence, provider_key=row.provider_key,
        language=row.language, confidence=row.confidence, provenance=row.provenance_json, created_at=row.created_at,
        segments=[dict(segment_id=s.segment_id, ordinal=s.ordinal, start_seconds=s.start_seconds,
            end_seconds=s.end_seconds, text=s.text, speaker=s.speaker, confidence=s.confidence,
            words=[dict(word_id=w.word_id, ordinal=w.ordinal, start_seconds=w.start_seconds,
                end_seconds=w.end_seconds, text=w.text, confidence=w.confidence)
                for w in words if w.segment_id == s.segment_id]) for s in segments])


def _source_windows(snapshot, asset_id):
    windows = []
    for track in snapshot['tracks']:
        if track['type'] != 'video' or track['kind'] != 'source' or track['disabled']:
            continue
        windows.extend(copy.deepcopy(c) for c in track['clips']
            if c['kind'] == 'source' and c['asset_id'] == asset_id and not c['disabled'])
    merged = []
    for clip in sorted(windows, key=lambda c: (c['timeline_start'], c['clip_id'])):
        if merged:
            prior = merged[-1]
            if (abs(prior['source_end'] - clip['source_start']) < 1e-6
                and abs(prior['timeline_start'] + prior['duration'] - clip['timeline_start']) < 1e-6
                and abs(prior['speed'] - clip['speed']) < 1e-6):
                prior['source_end'] = clip['source_end']
                prior['duration'] += clip['duration']
                continue
        merged.append(clip)
    return merged


def _sync_captions(snapshot, base, derived, *, manual_tracks):
    payload = copy.deepcopy(snapshot)
    active = (payload['metadata'].get('transcript_revision') or {}).get('transcript_id')
    inferred = {c['metadata'].get('transcript_id') for t in payload['tracks'] for c in t['clips']
        if c['metadata'].get('transcript_id')}
    if (active and active != base.transcript_id) or (not active and inferred and base.transcript_id not in inferred):
        raise TranscriptWordEditConflict('canonical timeline selects another transcript; reload its version')
    spans = _source_windows(payload, base.asset_id)
    changed = set(derived.provenance['reviewed_segment_ids'])
    mapping = dict(zip((s.segment_id for s in base.segments), derived.segments, strict=True))
    if not spans:
        raise TranscriptWordEditConflict('canonical timeline has no enabled source coverage')
    if not any(t['kind']=='subtitles' for t in payload['tracks']):
        raise TranscriptWordEditConflict('canonical subtitle track is unavailable')
    subtitle_tracks = [t for t in payload['tracks'] if t['kind']=='subtitles']
    # Audio caption ownership must never become a fallback destination for
    # revisions of an unrelated video transcript.
    subtitle_tracks = [t for t in subtitle_tracks if not any(c['metadata'].get('audio_binding_id') for c in t['clips'])
        and t['track_id'] not in {b['subtitle_track_id'] for b in payload['metadata'].get('uploaded_audio_bindings_v1', {}).values()}]
    if not subtitle_tracks:
        raise TranscriptWordEditConflict('canonical video subtitle track is unavailable')
    targets = {old_id: ({t['track_id'] for t in subtitle_tracks for c in t['clips']
        if c['metadata'].get('transcript_id')==base.transcript_id and c['metadata'].get('segment_id')==old_id}
        or {subtitle_tracks[0]['track_id']}) for old_id in changed}
    first = min(s['source_start'] for s in spans)
    last = max(s['source_end'] for s in spans)
    for old_id in changed:
        for word in mapping[old_id].words:
            if word.end_seconds <= first or word.start_seconds >= last:
                continue  # Fully excluded outer trims do not create new captions.
            if not any(s['source_start'] <= word.start_seconds and word.end_seconds <= s['source_end'] for s in spans):
                raise TranscriptWordEditConflict('reviewed word crosses or occupies an existing source cut')
            if any(min(word.end_seconds, s['source_end']) > max(word.start_seconds, s['source_start'])
                   and not (s['source_start'] <= word.start_seconds and word.end_seconds <= s['source_end']) for s in spans):
                raise TranscriptWordEditConflict('reviewed word crosses an existing source boundary')
    for track in payload['tracks']:
        if track['kind'] != 'subtitles':
            continue
        if track not in subtitle_tracks:
            continue
        prior_clips = copy.deepcopy(track['clips'])
        originals = [c for c in track['clips'] if c['metadata'].get('transcript_id') == base.transcript_id]
        selected_changes = {old_id for old_id in changed if track['track_id'] in targets[old_id]}
        affected = any(c['metadata'].get('segment_id') in changed for c in originals) or any(
            min(mapping[old_id].end_seconds, span['source_end']) > max(mapping[old_id].start_seconds, span['source_start'])
            for old_id in selected_changes for span in spans)
        # Explicit subtitle layout/text decisions need a separate review. Never
        # silently replace them with automatically reflowed transcript captions.
        if track['track_id'] in manual_tracks or any(c['metadata'].get('human_caption_edit') for c in track['clips']):
            if affected:
                raise TranscriptWordEditConflict('canonical subtitle layout was manually edited; review captions before word synchronization')
            continue
        replacement = []
        for clip in track['clips']:
            old_id = clip['metadata'].get('segment_id')
            if clip['metadata'].get('transcript_id') != base.transcript_id or old_id not in mapping:
                replacement.append(clip)
            elif old_id not in changed:
                clip['metadata'].update(transcript_id=derived.transcript_id, segment_id=mapping[old_id].segment_id)
                replacement.append(clip)
        for old_id in selected_changes:
            segment = mapping[old_id]
            prototype = next((c for c in originals if c['metadata'].get('segment_id') == old_id), None)
            if prototype is None:
                prototype = TimelineClip(clip_id='clip_' + uuid.uuid4().hex[:24], kind='subtitle',
                    label=segment.text[:120], source_end=.1, timeline_start=0, duration=.1,
                    metadata={'language':derived.language}).model_dump(mode='json')
            for span in spans:
                start = max(segment.start_seconds, span['source_start'])
                end = min(segment.end_seconds, span['source_end'])
                if end - start < .05:
                    continue
                selected = [w for w in segment.words if start <= w.start_seconds < w.end_seconds <= end]
                if not selected:
                    continue
                item = copy.deepcopy(prototype)
                text = ' '.join(w.text for w in selected)
                speed = span['speed']
                item.update(clip_id='clip_' + uuid.uuid4().hex[:24], label=text[:120], source_start=start, source_end=end,
                    timeline_start=round(span['timeline_start'] + (start - span['source_start']) / speed, 6),
                    duration=round((end - start) / speed, 6), speed=speed)
                item['metadata'].pop('subtitle_text', None)
                item['metadata'].update(transcript_id=derived.transcript_id, segment_id=segment.segment_id,
                    measured_source_words=[dict(text=w.text, start_seconds=w.start_seconds, end_seconds=w.end_seconds) for w in selected],
                    timing_source='human_supplied_source_word_intervals', timing_independently_measured=False,
                    human_word_timing_review=True, confidence=None)
                replacement.append(item)
        replacement.sort(key=lambda c: (c['timeline_start'], c['clip_id']))
        if len(replacement) > 2000:
            raise TranscriptWordEditConflict('caption limit exceeded')
        if track['locked'] and replacement != prior_clips:
            raise TranscriptWordEditConflict('subtitle track is locked; unlock before editing')
        track['clips'] = replacement
    payload['metadata']['transcript_revision'] = dict(transcript_id=derived.transcript_id,
        version=derived.version, human_edited=True, review_required=True,
        scene_highlight_semantics_stale=True, human_word_timing_review=True)
    return TimelineSnapshot.model_validate(payload)


async def _manual_caption_tracks(session, timeline):
    """Read existing mutation history; avoid adding a parallel canonical edit model."""
    versions = (await session.scalars(select(TimelineVersionORM).where(
        TimelineVersionORM.timeline_id == timeline.timeline_id,
        TimelineVersionORM.version <= timeline.current_version).order_by(TimelineVersionORM.version))).all()
    manual = set()
    manual_by_version = {}
    previous = None
    for version in versions:
        mutation = version.mutation_json
        if mutation.get('type') in {'initialize', 'silence-review-rebuild'}:
            manual.clear()
        if mutation.get('type') == 'restore':
            manual = set(manual_by_version.get(mutation.get('restored_from_version'), manual))
        if mutation.get('type') == 'edit' and previous:
            clips = {c['clip_id']:t for t in previous['tracks'] for c in t['clips']}
            for operation in mutation.get('operations', []):
                track = clips.get(operation.get('clip_id'))
                if track and track['kind'] == 'subtitles' and operation.get('type') != 'set_track_state':
                    manual.add(track['track_id'])
                    if operation.get('target_track_id'):
                        manual.add(operation['target_track_id'])
        previous = version.snapshot_json
        manual_by_version[version.version] = set(manual)
    return manual


def _declared_gaps(base, duration):
    """Reject gaps explicitly retained by an ASR provider; infer no silence."""
    clock = base.provenance.get('decoded_source_clock')
    if clock is None:
        return []
    if not isinstance(clock, dict) or clock.get('contiguous') is not True:
        raise TranscriptWordEditConflict('discontinuous source clock requires a verified gap map before editing')
    start = clock.get('source_start_seconds', 0.)
    end = clock.get('source_end_seconds', duration)
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0 <= start < end <= duration:
        raise TranscriptWordEditConflict('source clock bounds are invalid')
    return [(0., start), (end, duration)]


async def edit_transcript_words(repository, project_id, analysis_id, payload:WordReview, actor_ref):
    """Same SQL transaction preserves the original and invalidates dependent approval."""
    if not isinstance(actor_ref, str) or not actor_ref or len(actor_ref)>160 or any(ord(c)<32 for c in actor_ref):
        raise TranscriptWordEditConflict('verified actor identity is invalid')
    try:
        async with repository.session_factory() as session:
            async with session.begin():
                analysis = await session.scalar(select(AutoEditAnalysisORM).where(
                    AutoEditAnalysisORM.analysis_id == analysis_id,
                    AutoEditAnalysisORM.project_id == project_id).with_for_update())
                if analysis is None:
                    raise KeyError(analysis_id)
                project = await session.get(VideoProjectORM, project_id)
                asset = await session.get(AssetORM, analysis.asset_id)
                if (project is None or asset is None or project.workspace_id != analysis.workspace_id
                    or asset.workspace_id != analysis.workspace_id or asset.project_id != project_id):
                    raise KeyError(analysis_id)
                if analysis.status != 'succeeded':
                    raise TranscriptWordEditConflict('analysis is not ready')
                row = await session.scalar(select(TranscriptORM).where(
                    TranscriptORM.analysis_id == analysis_id).order_by(TranscriptORM.version.desc()).with_for_update())
                if row is None or row.asset_id != asset.asset_id:
                    raise TranscriptWordEditConflict('source transcript is unavailable')
                if row.version != payload.expected_version:
                    raise TranscriptWordEditConflict('transcript version changed; reload')
                base_row = await session.get(TranscriptORM, payload.expected_transcript_id)
                if base_row is None or base_row.analysis_id != analysis_id or base_row.asset_id != asset.asset_id:
                    raise TranscriptWordEditConflict('base transcript belongs to another source')
                base = await _read_transcript(session, base_row)
                if any(base.provenance.get(key) is not None and base.provenance[key] != asset.checksum_sha256
                       for key in ('source_checksum', 'source_asset_sha256')):
                    raise TranscriptWordEditConflict('transcript source checksum differs from the registered asset')
                duration = analysis.source_media_json.get('duration_seconds')
                try:
                    derived = revised(base, payload.model_copy(update={'expected_version':base.version}), duration=duration, actor_ref=actor_ref,
                        gaps=_declared_gaps(base, duration))
                    # Restoring a canonical timeline selects its immutable older
                    # transcript. Branch from that selection, while CAS and the
                    # persisted sequence still use the latest SQL version.
                    derived = derived.model_copy(update={'version':row.version+1,
                        'provenance':{**derived.provenance,'derived_from_version':base.version}})
                except (ValueError, TypeError) as exc:
                    raise TranscriptWordEditConflict(str(exc)) from exc
                timeline = await session.scalar(select(TimelineORM).where(
                    TimelineORM.project_id == project_id).with_for_update())
                snapshot = None
                if timeline is not None:
                    if timeline.source_analysis_id != analysis_id or timeline.workspace_id != analysis.workspace_id:
                        raise TranscriptWordEditConflict('active timeline uses another source')
                    if payload.expected_timeline_version != timeline.current_version:
                        raise TranscriptWordEditConflict('timeline version changed or was omitted; reload')
                    version = await session.get(TimelineVersionORM, timeline.current_version_id)
                    if version is None or version.timeline_id != timeline.timeline_id:
                        raise TranscriptWordEditConflict('canonical timeline version is unavailable')
                    snapshot = _sync_captions(version.snapshot_json, base, derived,
                        manual_tracks=await _manual_caption_tracks(session, timeline))
                elif payload.expected_timeline_version is not None:
                    raise TranscriptWordEditConflict('timeline does not exist')
                session.add(TranscriptORM(transcript_id=derived.transcript_id, analysis_id=analysis_id,
                    asset_id=derived.asset_id, version=derived.version, is_original_evidence=False,
                    provider_key=derived.provider_key, language=derived.language, confidence=None,
                    provenance_json={**derived.provenance, 'source_asset_sha256':asset.checksum_sha256},
                    created_at=derived.created_at))
                # Explicit parent ordering also works when FK enforcement is
                # enabled and the existing ORM models have no relationships.
                await session.flush()
                for segment in derived.segments:
                    session.add(TranscriptSegmentORM(segment_id=segment.segment_id, transcript_id=derived.transcript_id,
                        ordinal=segment.ordinal, start_seconds=segment.start_seconds, end_seconds=segment.end_seconds,
                        text=segment.text, speaker=segment.speaker, confidence=segment.confidence))
                await session.flush()
                for segment in derived.segments:
                    for word in segment.words:
                        session.add(TranscriptWordORM(word_id=word.word_id, transcript_id=derived.transcript_id,
                            segment_id=segment.segment_id, ordinal=word.ordinal, start_seconds=word.start_seconds,
                            end_seconds=word.end_seconds, text=word.text, confidence=word.confidence))
                if snapshot is not None:
                    await TimelineRepository(repository.session_factory).commit_mutation_in_session(session=session,
                        project_id=project_id, expected_version=timeline.current_version, snapshot=snapshot,
                        mutation={'type':'transcript-word-review','from_transcript_id':base.transcript_id,
                            'transcript_id':derived.transcript_id,'source_media_mutated':False}, actor_ref=actor_ref)
                analysis.provenance_json = {**analysis.provenance_json, 'human_transcript_revision':derived.version,
                    'semantic_analysis_refresh_required':True}
        return await repository.get_analysis(analysis_id, transcript_id=derived.transcript_id)
    except (IntegrityError, OperationalError, TimelineConflictError) as exc:
        if isinstance(exc, OperationalError) and 'locked' not in str(exc).lower():
            raise
        raise TranscriptWordEditConflict('concurrent transcript/timeline write; reload') from exc
