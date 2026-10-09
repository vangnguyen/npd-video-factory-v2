"""Source-footage editing over Native's one persisted canonical TimelineSnapshot.

An opt-in schema preserves narrated Phase 8–10 projects. Domain edits reuse the
same pure engine as API Studio; persistence remains Native SQLite/history.
"""
from __future__ import annotations
import copy
import json
import math
import re
from types import SimpleNamespace
from typing import Literal

from pydantic import Field, model_validator
from .contracts import WorkflowError, digest
from .media import project_assets
from .source_assets import canonical_assets
from .auto_edit_analysis import (
    asset_reference, downstream, selected_transcript, validate_record,
)
from app.auto_edit_logic import build_silence_decisions
from app.auto_edit_models import SilenceDecisionRead
from app.auto_edit_providers import MediaSignals
from app.models import StrictModel
from app.speech_windows import protected_window as protected_source_window
from app.timeline_logic import apply_operations, build_initial_timeline, TimelineEditError
from app.timeline_models import TimelineOperation, TimelineSnapshot
from .scene_selection import Selection

SCHEMA = 'native-auto-edit-timeline-v1'
MAX_DURATION = 600.
MAX_CLIPS = 2000


class CreateTimeline(StrictModel):
    analysis_id: str = Field(pattern=r'^ana_[a-f0-9]{24}$')
    transcript_id: str | None = Field(default=None, pattern=r'^trn_[a-f0-9]{24}$')
    expected_version: int | None = Field(default=None, ge=1, strict=True)
    silence_decision_ids: list[str] = Field(default_factory=list, max_length=2000)
    source_window: tuple[float, float] | None = None
    aspect_ratio: Literal['9:16', '16:9', '1:1', '4:5'] = '9:16'
    reviewed_scene:Selection|None=None
    reviewed_highlight_id:str|None=Field(default=None,pattern=r'^hig_[a-f0-9]{24}$')

    @model_validator(mode='after')
    def valid_selection(self):
        if (self.reviewed_scene is None)!=(self.reviewed_highlight_id is None) or self.reviewed_scene is not None and self.source_window is not None:
            raise ValueError('Reviewed highlights require original recommendation selection, without client window overrides')
        if len(set(self.silence_decision_ids)) != len(self.silence_decision_ids):
            raise ValueError('duplicate cut selection')
        if self.source_window and (not all(math.isfinite(value) for value in self.source_window)
                or not 0 <= self.source_window[0] < self.source_window[1] <= MAX_DURATION
                or self.source_window[1]-self.source_window[0] < .05):
            raise ValueError('invalid source window')
        return self


class EditTimeline(StrictModel):
    expected_version: int = Field(ge=1, strict=True)
    operations: list[TimelineOperation] = Field(min_length=1, max_length=100)


class RestoreTimeline(StrictModel):
    expected_version: int = Field(ge=1, strict=True)
    restore_revision: int = Field(ge=1, strict=True)


def is_auto_edit(document):
    return (document.get('canonical_timeline') or {}).get('snapshot', {}).get('metadata', {}).get('native_auto_edit_schema') == SCHEMA


def _selected(document, project_id, analysis_id):
    record = next((value for value in document.get('auto_edit_analyses', []) if value['analysis']['analysis_id'] == analysis_id), None)
    asset = next((value for value in project_assets(document) if record and value['id'] == record['native_asset_id']), None)
    if record is None or asset is None:
        raise WorkflowError('AUTO_EDIT_ANALYSIS_NOT_FOUND', 404)
    analysis = validate_record(record, project_id, document, asset)
    transcript = selected_transcript(document, analysis)
    analysis = analysis.model_copy(update={'transcript': transcript})
    signals = MediaSignals((), tuple(tuple(interval) for interval in analysis.provenance['media_signals'].get('silence_intervals', [])), {})
    decisions = build_silence_decisions(signals=signals, transcript=downstream(transcript), config=analysis.configuration) if transcript else []
    for index, decision in enumerate(decisions):
        decision['decision_id'] = 'sil_' + digest([analysis_id, index])[:24]
    return analysis.model_copy(update={'silence_decisions': [SilenceDecisionRead.model_validate(value) for value in decisions]}), asset


def protected_window(window, transcript, duration):
    return protected_source_window(window[0], window[1], transcript, duration)


def validate_document(document):
    state = document.get('canonical_timeline')
    if not isinstance(state, dict) or set(state) != {'version', 'snapshot', 'sha256'} or type(state['version']) is not int or state['version'] < 1:
        raise WorkflowError('AUTO_EDIT_TIMELINE_STATE_INVALID')
    if state['sha256'] != digest(state['snapshot']):
        raise WorkflowError('AUTO_EDIT_TIMELINE_CHANGED')
    from .channel_profiles import resolve
    selected_channel=resolve(document)
    if selected_channel is not None and state['snapshot']['metadata'].get('channel_selection_sha256')!=selected_channel['selection_sha256']:
        raise WorkflowError('CHANNEL_PROFILE_TIMELINE_BINDING_CHANGED')
    snapshot = TimelineSnapshot.model_validate(state['snapshot'])
    from .scene_selection import validate_timeline
    validate_timeline(document)
    from .source_reframe_vision import validate_timeline as validate_reframe
    validate_reframe(document)
    if snapshot.metadata.get('native_auto_edit_schema') != SCHEMA or document.get('proposal') is not None:
        raise WorkflowError('AUTO_EDIT_TIMELINE_SCHEMA_INVALID')
    if snapshot.metadata.get('source_audio_processing') is not None:
        from app.timeline_audio_processing import AudioProcessing
        try:AudioProcessing.model_validate(snapshot.metadata['source_audio_processing'])
        except ValueError:raise WorkflowError('AUTO_EDIT_AUDIO_PROCESSING_INVALID',400) from None
    identifier = snapshot.metadata.get('native_project_id')
    if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9]{32}',identifier):
        raise WorkflowError('AUTO_EDIT_TIMELINE_PROJECT_MISMATCH')
    root = next((value for value in document.get('auto_edit_analyses', [])
        if value['analysis']['analysis_id'] == snapshot.metadata.get('source_analysis_id')), None)
    root_asset = next((value for value in project_assets(document) if root and value['id'] == root['native_asset_id']), None)
    if root is None or root_asset is None:raise WorkflowError('AUTO_EDIT_ANALYSIS_NOT_FOUND', 404)
    validate_record(root, snapshot.metadata.get('native_project_id'), document, root_asset, require_current=False)
    if snapshot.duration_seconds > MAX_DURATION or sum(len(track.clips) for track in snapshot.tracks) > MAX_CLIPS:
        raise WorkflowError('AUTO_EDIT_TIMELINE_LIMIT')
    assets = {asset_reference(value): value for value in canonical_assets(document)}
    for track in snapshot.tracks:
        for clip in track.clips:
            if clip.asset_id is None:
                if clip.kind not in {'subtitle', 'overlay', 'metadata'}:
                    raise WorkflowError('AUTO_EDIT_TIMELINE_MEDIA_REQUIRED')
                continue
            asset = assets.get(clip.asset_id)
            if asset is None or clip.metadata.get('native_asset_id') != asset['id'] or clip.metadata.get('source_checksum_sha256') != asset['sha256']:
                raise WorkflowError('AUTO_EDIT_TIMELINE_SOURCE_CHANGED')
            if asset['kind'] == 'image':
                if clip.kind != 'image':raise WorkflowError('AUTO_EDIT_TIMELINE_SOURCE_KIND_INVALID')
            elif asset['kind'] == 'video':
                if clip.kind == 'image' or clip.source_end is None or clip.source_end > asset['duration_seconds'] + .05:
                    raise WorkflowError('AUTO_EDIT_TIMELINE_SOURCE_WINDOW_INVALID')
                if track.type == 'audio' and not asset.get('has_audio'):
                    raise WorkflowError('AUTO_EDIT_TIMELINE_AUDIO_STREAM_REQUIRED')
            elif asset['kind']=='audio':
                if track.type!='audio' or clip.source_end is None or clip.source_end>asset['duration_seconds']+.05:
                    raise WorkflowError('AUTO_EDIT_TIMELINE_SOURCE_WINDOW_INVALID')
            else:raise WorkflowError('AUTO_EDIT_TIMELINE_SOURCE_KIND_INVALID')
    return state


def _save(store, con, project, snapshot, action, *, restored_from_version=None):
    from .store import now
    previous = project['document'].get('canonical_timeline')
    document = copy.deepcopy(project['document'])
    snapshot.metadata['native_auto_edit_schema'] = SCHEMA
    document['canonical_timeline'] = {'version': (previous['version'] if previous else 0) + 1,
        'snapshot': snapshot.model_dump(mode='json'), 'sha256': digest(snapshot.model_dump(mode='json'))}
    document['source_timeline_mutations']=document.get('source_timeline_mutations',[])+[{
        'version':document['canonical_timeline']['version'],'mutation':{
            'type':'restore' if restored_from_version is not None else 'edit',
            **({'restored_from_version':restored_from_version} if restored_from_version is not None else {})}}]
    validate_document(document)
    con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',
        (project['revision']+1, json.dumps(document, ensure_ascii=False), now(), project['id']))
    store.version(con, project['id'])
    store.event(con, project['id'], action, {'revision': project['revision']+1,
        'timeline_version': document['canonical_timeline']['version'], 'timeline_sha256': document['canonical_timeline']['sha256'],
        'actor_ref': 'native-session-owner', 'provider_calls': 0, 'source_media_mutated': False,
        'preview_invalidated': True, 'approval_invalidated': True, 'full_render_requested': False})


def _cas(project, expected_version, *, create=False):
    state = project['document'].get('canonical_timeline')
    if state:
        if not is_auto_edit(project['document']):raise WorkflowError('AUTO_EDIT_SEPARATE_MEDIA_PROJECT_REQUIRED', 400)
        validate_document(project['document'])
        if expected_version != state['version']:raise WorkflowError('AUTO_EDIT_TIMELINE_VERSION_CHANGED')
    elif not create or expected_version is not None:
        raise WorkflowError('AUTO_EDIT_TIMELINE_VERSION_CHANGED')
    return state


def create(store, project_id, revision, body,*,config=None,official_vision=None):
    try:payload = CreateTimeline.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_TIMELINE_REQUEST_INVALID', 400) from None
    from .scene_selection import reader,selected,lineage
    from .pipeline import Config
    config=config or Config(data_root=store.root)
    getter=reader(store,config,project_id,payload.reviewed_scene,official_vision)
    with store.transaction() as con:
        project = store.editable(con, project_id, revision)
        document = project['document']
        if document.get('input_kind') != 'media' or document.get('proposal') is not None:
            raise WorkflowError('AUTO_EDIT_SEPARATE_MEDIA_PROJECT_REQUIRED', 400)
        _cas(project, payload.expected_version, create=True)
        analysis, asset = _selected(document, project_id, payload.analysis_id)
        if payload.transcript_id != (analysis.transcript.transcript_id if analysis.transcript else None):
            raise WorkflowError('AUTO_EDIT_TRANSCRIPT_VERSION_CHANGED')
        reviewed=None;window=payload.source_window
        if payload.reviewed_scene is not None:
            reviewed=selected(store,config,project,payload.reviewed_scene,payload.analysis_id,con,getter)
            highlight=next((v for v in reviewed['recommendation']['result']['scene_ranking'] if v['highlight_id']==payload.reviewed_highlight_id),None)
            if highlight is None:raise WorkflowError('NATIVE_SCENE_SELECTION_HIGHLIGHT_CHANGED')
            window=(highlight['recommended_start'],highlight['recommended_end'])
        if window:
            if window[1] > analysis.source_media.duration_seconds:
                raise WorkflowError('AUTO_EDIT_TIMELINE_SOURCE_WINDOW_INVALID', 400)
            start, end = protected_window(window, analysis.transcript, analysis.source_media.duration_seconds)
            scenes = [scene.model_copy(update={'start_seconds': max(start, scene.start_seconds), 'end_seconds': min(end, scene.end_seconds)})
                for scene in analysis.scenes if min(end, scene.end_seconds)-max(start, scene.start_seconds) >= .05]
            if not scenes:raise WorkflowError('AUTO_EDIT_TIMELINE_SELECTION_INVALID', 400)
            analysis = analysis.model_copy(update={'scenes': scenes})
        reference = SimpleNamespace(asset_id=asset_reference(asset), checksum_sha256=asset['sha256'],
            content_type='video/mp4', object_key=asset['id'])
        try:snapshot = build_initial_timeline(analysis=analysis, source_asset=reference, media_plan=None, media_assets={}, silence_decision_ids=payload.silence_decision_ids)
        except TimelineEditError:raise WorkflowError('AUTO_EDIT_TIMELINE_SELECTION_INVALID', 400) from None
        for track in snapshot.tracks:
            for clip in track.clips:
                if clip.asset_id:
                    clip.metadata['native_asset_id'] = asset['id']
        width, height = {'9:16': (1080,1920), '16:9': (1920,1080), '1:1': (1080,1080), '4:5': (1080,1350)}[payload.aspect_ratio]
        snapshot.width, snapshot.height, snapshot.aspect_ratio = width, height, payload.aspect_ratio
        snapshot.metadata.update(source_selection={'requested_window':window,
            'word_safe_window':(start,end) if window else None,
            'silence_decision_ids':payload.silence_decision_ids}, human_review_required=True,
            timing_source='measured_source_footage_and_saved_transcript', native_project_id=project_id)
        if reviewed is not None:snapshot.metadata.update(reviewed_scene_selection=lineage(reviewed),reviewed_highlight_id=payload.reviewed_highlight_id)
        from .channel_profiles import bind_source
        snapshot=bind_source(snapshot,project['document'])
        _save(store, con, project, snapshot, 'auto_edit_canonical_timeline_created')
    return view(store, project_id)


def edit(store, project_id, revision, body):
    try:payload = EditTimeline.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_TIMELINE_REQUEST_INVALID', 400) from None
    with store.transaction() as con:
        project = store.editable(con, project_id, revision)
        state = _cas(project, payload.expected_version)
        try:snapshot = apply_operations(TimelineSnapshot.model_validate(state['snapshot']), payload.operations)
        except (TimelineEditError, ValueError):raise WorkflowError('AUTO_EDIT_TIMELINE_OPERATION_INVALID', 400) from None
        _save(store, con, project, snapshot, 'auto_edit_canonical_timeline_edited')
    return view(store, project_id)


def restore(store, project_id, revision, body):
    try:payload = RestoreTimeline.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_TIMELINE_REQUEST_INVALID', 400) from None
    with store.transaction() as con:
        project = store.editable(con, project_id, revision)
        _cas(project, payload.expected_version)
        row = con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?', (project_id,payload.restore_revision)).fetchone()
        if row is None or payload.restore_revision >= project['revision']:
            raise WorkflowError('AUTO_EDIT_TIMELINE_RESTORE_NOT_FOUND', 404)
        prior = json.loads(row[0])
        if not is_auto_edit(prior):raise WorkflowError('AUTO_EDIT_TIMELINE_RESTORE_SCHEMA_INVALID', 400)
        validate_document(prior)
        _save(store, con, project, TimelineSnapshot.model_validate(prior['canonical_timeline']['snapshot']),
            'auto_edit_canonical_timeline_restored',restored_from_version=prior['canonical_timeline']['version'])
    return view(store, project_id)


def source_shots(snapshot):
    return [{'shot_id': clip['clip_id'], 'id': clip['clip_id'], 'scene': index+1, 'number': index+1,
        'visual': clip['label'], 'prompt': clip['label'], 'narration': '', 'narration_enabled': False,
        'subtitle': '', 'on_screen_text': clip['label'], 'duration': clip['duration'], 'requested_duration': None,
        'duration_requested': None, 'source_start': clip['source_start'], 'source_end': clip['source_end'],
        'timeline_start': clip['timeline_start'], 'asset_id': clip['metadata'].get('native_asset_id'),
        'asset_type': 'video', 'crop_strategy': clip['metadata'].get('fit','contain'), 'motion': 'none',
        'transition': clip['transition_in']['kind'], 'timing_measured': True, 'status': 'SOURCE_READY',
        'source_audio': 'canonical_audio_track'} for index,clip in enumerate(
            clip for track in snapshot['tracks'] if track['type']=='video' and track['kind']=='source' for clip in track['clips'])]


def view(store, project_id):
    project = store.get(project_id)
    if project['document'].get('source_reframe_reviews'):
        from .source_reframe_vision import history as reframe_history
        from .pipeline import Config
        reframe_history(store,Config(data_root=store.root),project)
    if project['document'].get('source_scene_recommendations'):
        from .scene_review import page
        from .pipeline import Config
        page(store,Config(data_root=store.root),project_id)
    if any(record.get('plan',{}).get('provenance',{}).get('algorithm')=='native-source-broll-v2'
        or 'reviewed_vision' in record.get('plan',{}).get('provenance',{}) or 'reviewed_input' in record.get('plan',{}).get('provenance',{})
        for record in project['document'].get('source_broll_plans',[])):
        from .source_broll_vision import history
        history(store,project)
    state = validate_document(project['document'])
    if state['snapshot']['metadata'].get('native_project_id') != project_id:
        raise WorkflowError('AUTO_EDIT_TIMELINE_PROJECT_MISMATCH')
    assets = {value['id']:value for value in project_assets(project['document'])}
    shots = source_shots(state['snapshot'])
    for shot in shots:shot['asset'] = copy.deepcopy(assets.get(shot['asset_id']))
    return {**project, 'shot_timeline': {**copy.deepcopy(state), 'shots': shots, 'persisted': True,
        'editing_mode': 'source_footage', 'preview_valid': False, 'scope': {'provider_calls':0, 'full_render_requested':False}}}


def sync_transcript(document, base, derived):
    """Same revision updates canonical cues, retaining media/audio edit decisions."""
    state = validate_document(document)
    snapshot = copy.deepcopy(state['snapshot'])
    if snapshot['metadata'].get('source_analysis_id') != base.analysis_id or (
            snapshot['metadata'].get('transcript_revision') or {}).get('transcript_id') != base.transcript_id:
        raise WorkflowError('AUTO_EDIT_TRANSCRIPT_BASE_DIFFERS_FROM_TIMELINE')
    mapping = {old.segment_id: new for old,new in zip(base.segments, derived.segments, strict=True)}
    changed = set(derived.provenance['changed_segment_ids'])
    for track in snapshot['tracks']:
        for clip in track['clips']:
            metadata = clip['metadata']
            segment_id = metadata.get('segment_id')
            if metadata.get('transcript_id') != base.transcript_id or segment_id not in mapping:continue
            segment = mapping[segment_id]
            if segment_id in changed:
                if track['locked']:raise WorkflowError('AUTO_EDIT_SUBTITLE_TRACK_LOCKED')
                clip['label'] = segment.text[:120]
                metadata.update(subtitle_text=segment.text, measured_source_words=[], confidence=None,
                    timing_source='human_edited_segment_bounds_no_word_alignment')
            metadata.update(segment_id=segment.segment_id, transcript_id=derived.transcript_id)
    snapshot['metadata']['transcript_revision'] = {'transcript_id':derived.transcript_id,
        'version':derived.version, 'human_edited':True, 'review_required':True, 'scene_highlight_semantics_stale':True}
    TimelineSnapshot.model_validate(snapshot)
    document['canonical_timeline'] = {'version':state['version']+1, 'snapshot':snapshot, 'sha256':digest(snapshot)}
    document['source_timeline_mutations']=document.get('source_timeline_mutations',[])+[{
        'version':state['version']+1,'mutation':{'type':'edit'}}]
    validate_document(document)
