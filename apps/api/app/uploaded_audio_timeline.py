"""Explicit uploaded narration binding on the existing canonical timeline.

No inferred word timestamps, source rewrite, implicit approval, or provider call.
"""
from .auto_edit_models import TranscriptRead
from .timeline_models import TimelineClip, TimelineSnapshot, TimelineTrack
from .transcript_word_review import timing_evidence
from .uploaded_audio_repository import AudioConflict, digest, identity

KEY = 'uploaded_audio_bindings_v1'


def captions(transcript, windows, binding_id):
    output = []
    for window in windows:
        for segment in transcript.segments:
            start = max(window.source_start, segment.start_seconds)
            end = min(window.source_end, segment.end_seconds)
            if end <= start:
                continue
            units = segment.words or [segment]
            if any(start < u.end_seconds and end > u.start_seconds
                   and not (window.source_start <= u.start_seconds and u.end_seconds <= window.source_end)
                   for u in units):
                raise AudioConflict('AUDIO_CAPTION_CUT_THROUGH_SPEECH')
            words = [w for w in segment.words if start <= w.start_seconds < w.end_seconds <= end]
            if segment.words and not words:
                continue
            text = ' '.join(w.text for w in words) if words else segment.text
            metadata = dict(audio_transcription_id=transcript.analysis_id,
                audio_binding_id=binding_id, transcript_id=transcript.transcript_id,
                segment_id=segment.segment_id, language=transcript.language,
                confidence=None, timing_independently_measured=False,
                recognition_review_required=True)
            metadata.update(timing_evidence(transcript))
            if words:
                metadata['measured_source_words'] = [dict(text=w.text,
                    start_seconds=w.start_seconds, end_seconds=w.end_seconds) for w in words]
            else:
                metadata['subtitle_text'] = text
                metadata['timing_source'] = 'transcript_segment_intervals'
            output.append(TimelineClip(clip_id=identity('clip'), kind='subtitle', label=text[:120],
                source_start=start, source_end=end, speed=window.speed,
                timeline_start=window.timeline_start+(start-window.source_start)/window.speed,
                duration=(end-start)/window.speed, metadata=metadata))
    if len(output) > 2000:
        raise AudioConflict('AUDIO_CAPTION_LIMIT')
    return output


def binding(snapshot, audio_id):
    value = snapshot.metadata.get(KEY, {}).get(audio_id)
    if value is not None and (not isinstance(value, dict) or value.get('audio_id') != audio_id
        or digest(value.get('transcript')) != value.get('transcript_sha256')):
        raise AudioConflict('AUDIO_CANONICAL_BINDING_CHANGED')
    return value


def sync(snapshot, base, derived, *, manual_tracks=()):
    value = binding(snapshot, base.analysis_id)
    if value is None:
        raise AudioConflict('AUDIO_CANONICAL_CAPTION_REVIEW_REQUIRED')
    if value['transcript_id'] != base.transcript_id or value['transcript'] != base.model_dump(mode='json'):
        raise AudioConflict('AUDIO_CANONICAL_TRANSCRIPT_CHANGED')
    payload = snapshot.model_copy(deep=True)
    voice = next((t for t in payload.tracks if t.track_id == value['voice_track_id']), None)
    target = next((t for t in payload.tracks if t.track_id == value['subtitle_track_id']), None)
    if voice is None or voice.kind != 'voice' or voice.type != 'audio' or target is None or target.kind != 'subtitles':
        raise AudioConflict('AUDIO_CANONICAL_BINDING_CHANGED')
    if target.locked or target.track_id in manual_tracks or any(c.metadata.get('human_caption_edit') for c in target.clips):
        raise AudioConflict('AUDIO_CANONICAL_CAPTION_REVIEW_REQUIRED')
    if any(c.metadata.get('audio_binding_id') != value['binding_id'] for c in target.clips):
        raise AudioConflict('AUDIO_FOREIGN_CAPTION_TRACK')
    if any(c.metadata.get('audio_binding_id') != value['binding_id'] or c.asset_id != base.asset_id for c in voice.clips):
        raise AudioConflict('AUDIO_CANONICAL_BINDING_CHANGED')
    if any(c.metadata.get('audio_binding_id') == value['binding_id'] and c.kind == 'voice'
           for t in payload.tracks if t.track_id != voice.track_id for c in t.clips):
        raise AudioConflict('AUDIO_CANONICAL_BINDING_CHANGED')
    if any(c.source_end > value['source_duration'] or c.metadata.get('source_asset_sha256') != value['source_sha256'] for c in voice.clips):
        raise AudioConflict('AUDIO_SOURCE_WINDOW_INVALID')
    windows = [] if voice.disabled or voice.muted else [c for c in voice.clips if not c.disabled and c.volume > 0]
    target.clips = captions(derived, windows, value['binding_id'])
    body = derived.model_dump(mode='json')
    payload.metadata[KEY][base.analysis_id].update(transcript_id=derived.transcript_id,
        transcript=body, transcript_sha256=digest(body), human_review_required=True)
    return TimelineSnapshot.model_validate(payload.model_dump(mode='json'))


def apply(snapshot, transcript, payload, *, source_duration):
    result = snapshot.model_copy(deep=True)
    if binding(result, transcript.analysis_id) is not None:
        raise AudioConflict('AUDIO_ALREADY_BOUND')
    if payload.source_end <= payload.source_start or payload.source_end > source_duration:
        raise AudioConflict('AUDIO_SOURCE_WINDOW_INVALID')
    duration = (payload.source_end-payload.source_start)/payload.speed
    if payload.timeline_start+duration > result.duration_seconds+.000001:
        raise AudioConflict('AUDIO_TIMELINE_DURATION_EXCEEDED')
    if any(t.kind == 'subtitles' and not t.disabled and any(not c.disabled for c in t.clips) for t in result.tracks):
        raise AudioConflict('AUDIO_EXISTING_CAPTIONS_REVIEW_REQUIRED')
    for track in result.tracks:
        if track.type != 'audio' or track.disabled or track.muted or not any(not c.disabled and c.volume > 0 for c in track.clips):
            continue
        if track.kind == 'original_audio' and payload.mute_original:
            if track.locked:
                raise AudioConflict('AUDIO_ORIGINAL_TRACK_LOCKED')
            track.muted = True
        elif track.kind in {'original_audio', 'voice'}:
            raise AudioConflict('AUDIO_EXISTING_SPEECH_REVIEW_REQUIRED')
    bid = identity('abn')
    voice = TimelineTrack(track_id=identity('trk'), type='audio', kind='voice', label='Uploaded narration',
        order=len(result.tracks), clips=[TimelineClip(clip_id=identity('clip'), kind='voice',
        label='Uploaded narration', asset_id=transcript.asset_id, source_start=payload.source_start,
        source_end=payload.source_end, timeline_start=payload.timeline_start, duration=duration, speed=payload.speed,
        metadata={'audio_binding_id':bid, 'audio_transcription_id':transcript.analysis_id,
                  'source_asset_sha256':payload.source_sha256})])
    target = TimelineTrack(track_id=identity('trk'), type='text', kind='subtitles', label='Audio captions',
        order=len(result.tracks)+1, clips=captions(transcript, voice.clips, bid))
    if not target.clips:
        raise AudioConflict('AUDIO_CAPTION_COVERAGE_REQUIRED')
    body = transcript.model_dump(mode='json')
    result.tracks.extend([voice, target])
    result.metadata.setdefault(KEY, {})[transcript.analysis_id] = dict(binding_id=bid,
        audio_id=transcript.analysis_id, source_sha256=payload.source_sha256, source_duration=source_duration,
        voice_track_id=voice.track_id, subtitle_track_id=target.track_id, transcript_id=transcript.transcript_id,
        transcript=body, transcript_sha256=digest(body), human_review_required=True)
    return TimelineSnapshot.model_validate(result.model_dump(mode='json')), bid


def refresh_after_edit(before, after, operations):
    """Voice edits reflow their saved captions; simultaneous manual caption edits fail closed."""
    result = after
    for audio_id, value in before.metadata.get(KEY, {}).items():
        old = next((t for t in before.tracks if t.track_id == value['voice_track_id']), None)
        new = next((t for t in result.tracks if t.track_id == value['voice_track_id']), None)
        # Track locking does not change the audible source clock or captions.
        # Preserve caption identities during lock/unlock even when they are locked.
        rendered = lambda t: None if t is None else t.model_dump(mode='json', exclude={'locked', 'label', 'order'})
        if rendered(old) == rendered(new):
            continue
        owned_ids = {c.clip_id for t in before.tracks if t.track_id == value['subtitle_track_id'] for c in t.clips}
        if any(o.clip_id in owned_ids or o.target_track_id == value['subtitle_track_id'] for o in operations):
            raise AudioConflict('AUDIO_CANONICAL_CAPTION_REVIEW_REQUIRED')
        # A prior manual edit is detected from the exact expected generated layout,
        # independently of SQL history (including restore and trim operations).
        check = sync(before, TranscriptRead.model_validate(value['transcript']), TranscriptRead.model_validate(value['transcript']))
        actual = next((t for t in before.tracks if t.track_id == value['subtitle_track_id']), None)
        expected = next(t for t in check.tracks if t.track_id == value['subtitle_track_id'])
        strip = lambda t: [{k:v for k,v in c.model_dump(mode='json').items() if k != 'clip_id'} for c in t.clips]
        if actual is None or strip(actual) != strip(expected):
            raise AudioConflict('AUDIO_CANONICAL_CAPTION_REVIEW_REQUIRED')
        result = sync(result, TranscriptRead.model_validate(value['transcript']), TranscriptRead.model_validate(value['transcript']))
    return result
