"""Pure linked source-shot edits, using saved speech intervals and canonical clips.

The existing independent advanced-track engine remains unchanged. This explicit
path follows the Native linked-edit semantics without importing its store or
process contracts. Source/audio windows are matched before changing either.
"""
from __future__ import annotations

import copy
import uuid

from .speech_windows import protected_window
from .timeline_logic import apply_operations, TimelineEditError
from .timeline_models import TimelineClip, TimelineSnapshot
from .transcript_word_review import timing_evidence

EPSILON = 0.000001


class SourceLinkedEditError(TimelineEditError):
    pass


def clock(clip):
    return (clip.asset_id, round(clip.source_start, 6), round(clip.source_end, 6),
            round(clip.timeline_start, 6), round(clip.duration, 6), round(clip.speed, 6), clip.disabled)


def captions(sources, transcript):
    """Preserve measured word times; merge continuous source windows as Native does."""
    if transcript is None:
        return []
    windows = []
    for clip in sorted((c for c in sources if not c.disabled), key=lambda c: c.timeline_start):
        if (windows and abs(windows[-1].source_end - clip.source_start) < EPSILON
                and abs(windows[-1].timeline_start + windows[-1].duration - clip.timeline_start) < EPSILON
                and windows[-1].speed == clip.speed):
            previous = windows[-1]
            windows[-1] = previous.model_copy(update={"source_end": clip.source_end,
                "duration": previous.duration + clip.duration})
        else:
            windows.append(clip.model_copy(deep=True))
    result = []
    for window in windows:
        for segment in transcript.segments:
            start, end = max(window.source_start, segment.start_seconds), min(window.source_end, segment.end_seconds)
            if end - start < .05:
                continue
            words = [w for w in segment.words
                     if start - EPSILON <= w.start_seconds < w.end_seconds <= end + EPSILON]
            partial = start > segment.start_seconds + EPSILON or end < segment.end_seconds - EPSILON
            text = " ".join(w.text for w in words) if partial and segment.words else segment.text
            if not text.strip():
                continue
            # Rounded timeline boundaries may differ from raw ASR by <1us. Keep
            # raw measured words intact and avoid dropping the boundary word.
            if words:
                start, end = min(start, words[0].start_seconds), max(end, words[-1].end_seconds)
            metadata = {"transcript_id": transcript.transcript_id, "segment_id": segment.segment_id,
                "language": transcript.language, "confidence": segment.confidence,
                "source_linked_caption": True,
                "timing_source": "provider_native_word_intervals" if words else "segment_bounds_without_word_alignment",
                "measured_source_words": [dict(text=w.text, start_seconds=w.start_seconds,
                    end_seconds=w.end_seconds) for w in words],
                **(timing_evidence(transcript) if words else {}),
                **({"subtitle_text": text} if not segment.words else {})}
            result.append(TimelineClip(clip_id="clip_" + uuid.uuid4().hex[:24], kind="subtitle", label=text[:120],
                source_start=start, source_end=end, speed=window.speed,
                timeline_start=max(0., round(window.timeline_start + (start - window.source_start) / window.speed, 6)),
                duration=round((end - start) / window.speed, 6), metadata=metadata))
    return result


def _caption_tracks(snapshot, transcript, manual_track_ids):
    selected = []
    binding = transcript.transcript_id if transcript else None
    manual = set(manual_track_ids)
    for key in ("source_caption_edited_tracks", "narrated_caption_edited_tracks"):
        value = snapshot.metadata.get(key, [])
        if not isinstance(value, list) or any(not isinstance(i, str) for i in value):
            raise SourceLinkedEditError("SOURCE_CAPTION_LAYOUT_INVALID")
        manual.update(value)
    for track in snapshot.tracks:
        if track.kind != "subtitles":
            continue
        preserved = track.track_id in manual or any(any(c.metadata.get(k) for k in (
            "human_caption_edit", "native_media_import_id", "audio_binding_id", "source_video_mapping",
            "subtitle_import_id", "media_import_id")) for c in track.clips)
        if preserved:
            continue
        if any(c.metadata.get("transcript_id") != binding for c in track.clips):
            raise SourceLinkedEditError("SOURCE_CAPTION_BINDING_DIVERGED")
        if track.clips and transcript is None:
            raise SourceLinkedEditError("SOURCE_TRANSCRIPT_REQUIRED")
        selected.append(track)
    return selected


def _caption_layout(clips):
    result = []
    for clip in clips:
        value = clip.model_dump(mode="json", exclude={"clip_id"})
        for name in ("source_start", "source_end", "timeline_start", "duration", "speed"):
            value[name] = round(value[name], 6)
        for name in ("source_linked_caption", "native_linked_caption", "editable_in"):
            value["metadata"].pop(name, None)
        result.append(value)
    return result


def apply_linked_operations(snapshot, operations, *, transcript, source_asset_id, source_duration,
                            has_audio, manual_caption_track_ids=()):
    """Validate and apply an entire request in RAM; the caller owns one SQL commit."""
    result = snapshot.model_copy(deep=True)
    applied = []
    for operation in operations:
        tracks = [t for t in result.tracks if t.type == "video" and t.kind == "source"]
        if len(tracks) != 1 or tracks[0].disabled:
            raise SourceLinkedEditError("SOURCE_TRACK_REQUIRED")
        main = tracks[0]
        selected = next((c for c in main.clips if c.clip_id == operation.clip_id), None)
        if selected is None or selected.kind != "source" or selected.asset_id != source_asset_id:
            raise SourceLinkedEditError("SOURCE_CLIP_NOT_FOUND")
        if any(c.kind != "source" or c.asset_id != source_asset_id
               or not 0 <= c.source_start < c.source_end <= source_duration + EPSILON for c in main.clips):
            raise SourceLinkedEditError("SOURCE_WINDOW_INVALID")
        visual_only = operation.type == "set_clip_properties" and operation.speed is None
        if visual_only:
            result = apply_operations(result, [operation])
            applied.append(operation.model_dump(mode="json", exclude_none=True))
            continue
        audio_tracks = [t for t in result.tracks if t.kind == "original_audio"]
        if len(audio_tracks) > 1 or any(t.type != "audio" for t in audio_tracks):
            raise SourceLinkedEditError("SOURCE_AUDIO_TRACKS_DIVERGED")
        audio = audio_tracks[0] if audio_tracks else None
        if has_audio and (audio is None or not audio.clips):
            raise SourceLinkedEditError("SOURCE_AUDIO_MISSING")
        if not has_audio and audio is not None and audio.clips:
            raise SourceLinkedEditError("SOURCE_AUDIO_UNEXPECTED")
        linked_captions = _caption_tracks(result, transcript, manual_caption_track_ids)
        sound = {}
        if audio and audio.clips:
            for clip in main.clips:
                matches = [c for c in audio.clips if clock(c) == clock(clip)]
                if len(matches) != 1:
                    raise SourceLinkedEditError("SOURCE_AUDIO_DIVERGED")
                sound[clip.clip_id] = matches[0]
            if len(sound) != len(audio.clips):
                raise SourceLinkedEditError("SOURCE_AUDIO_DIVERGED")
        if operation.type == "trim":
            start = operation.source_start if operation.source_start is not None else selected.source_start
            end = operation.source_end if operation.source_end is not None else selected.source_end
            if not 0 <= start < end <= source_duration:
                raise SourceLinkedEditError("SOURCE_WINDOW_INVALID")
            start, end = protected_window(start, end, transcript, source_duration)
            operation = operation.model_copy(update={"source_start": start, "source_end": end})
        if operation.type == "split" and transcript:
            point = selected.source_start + (operation.at_seconds - selected.timeline_start) * selected.speed
            for segment in transcript.segments:
                intervals = [(w.start_seconds, w.end_seconds) for w in segment.words] or [(segment.start_seconds, segment.end_seconds)]
                if any(a + EPSILON < point < b - EPSILON for a, b in intervals):
                    raise SourceLinkedEditError("SOURCE_SPLIT_TOUCHES_SPEECH")
        if operation.type == "delete" and len(main.clips) <= 1:
            raise SourceLinkedEditError("SOURCE_LAST_CLIP_REQUIRED")
        prepared = result.model_copy(deep=True)
        prepared_main = next(t for t in prepared.tracks if t.track_id == main.track_id)
        marker = "_source_link_origin_" + uuid.uuid4().hex
        for clip in prepared_main.clips:
            clip.metadata[marker] = clip.clip_id
        changed = apply_operations(prepared, [operation])
        changed_main = next(t for t in changed.tracks if t.track_id == main.track_id)
        if operation.type == "move":
            changed_main.clips.sort(key=lambda c: c.timeline_start)
        elif operation.type == "duplicate":
            original_ids = {c.clip_id for c in main.clips}
            # An explicit destination is a ripple insertion position. At an
            # existing boundary put the copy before that next shot, instead of
            # silently appending it at the end of the source sequence.
            changed_main.clips.sort(key=lambda c: (c.timeline_start, c.clip_id in original_ids))
        cursor = 0.
        for clip in changed_main.clips:
            clip.timeline_start = round(cursor, 6)
            if not clip.disabled:
                cursor += clip.duration
        if operation.type in {"move", "duplicate"}:
            affected = next(c for c in changed_main.clips if
                (c.clip_id == operation.clip_id if operation.type == "move" else c.clip_id not in original_ids))
            operation = operation.model_copy(update={"timeline_start": affected.timeline_start})
        clocks_changed = [(c.clip_id, clock(c)) for c in main.clips] != [(c.clip_id, clock(c)) for c in changed_main.clips]
        captions_changed = False
        if clocks_changed:
            caption_updates = {t.track_id: captions(changed_main.clips, transcript) for t in linked_captions}
            caption_updates = {t.track_id: caption_updates[t.track_id] for t in linked_captions
                               if _caption_layout(caption_updates[t.track_id]) != _caption_layout(t.clips)}
            captions_changed = bool(caption_updates)
            if (audio and sound and audio.locked) or any(t.locked and t.track_id in caption_updates for t in linked_captions):
                raise SourceLinkedEditError("SOURCE_LINKED_TRACK_LOCKED")
            if audio and sound:
                target = next(t for t in changed.tracks if t.track_id == audio.track_id)
                target.clips = []
                for clip in changed_main.clips:
                    origin = clip.metadata[marker]
                    original = sound[origin]
                    if any(t.duration_seconds > clip.duration + EPSILON for t in (original.transition_in, original.transition_out)):
                        raise SourceLinkedEditError("SOURCE_AUDIO_TRANSITION_REVIEW_REQUIRED")
                    target.clips.append(original.model_copy(deep=True, update={
                        "clip_id": original.clip_id if clip.clip_id == origin else "clip_" + uuid.uuid4().hex[:24],
                        "source_start": clip.source_start, "source_end": clip.source_end,
                        "timeline_start": clip.timeline_start, "duration": clip.duration,
                        "speed": clip.speed, "disabled": clip.disabled,
                        "metadata": {**copy.deepcopy(original.metadata), "linked_source_clip_id": clip.clip_id}}))
            for track in linked_captions:
                if track.track_id not in caption_updates:
                    continue
                target = next(t for t in changed.tracks if t.track_id == track.track_id)
                target.clips = caption_updates[track.track_id]
        for clip in changed_main.clips:
            clip.metadata.pop(marker, None)
        changed.duration_seconds = max(.1, round(max((c.timeline_start + c.duration for t in changed.tracks
            if not t.disabled for c in t.clips if not c.disabled), default=.1), 6))
        changed.metadata["linked_source_edit"] = {"schema_version": "source-linked-edit-v1",
            "captions_retimed_from_saved_transcript": captions_changed,
            "source_audio_synchronized": bool(audio and sound), "source_move_behavior": "ripple_reorder",
            "imported_and_human_caption_layouts_preserved": True, "other_tracks_preserved": True,
            "broll_placement_review_required": True, "provider_calls": 0}
        result = TimelineSnapshot.model_validate(changed.model_dump(mode="json"))
        applied.append(operation.model_dump(mode="json", exclude_none=True))
    return result, applied
