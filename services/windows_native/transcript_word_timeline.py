"""Manual transcript captions follow existing source windows; media edits stay intact."""
import copy,uuid
from app.timeline_models import TimelineSnapshot,TimelineClip
from .contracts import WorkflowError,digest

def windows(snapshot,asset):
    clips=sorted((copy.deepcopy(c) for t in snapshot['tracks'] if t['type']=='video' and t['kind']=='source' and not t.get('disabled')
        for c in t['clips'] if c.get('asset_id')==asset and c['kind']=='source' and not c.get('disabled')),
        key=lambda c:(c['timeline_start'],c['clip_id']))
    merged=[]
    for clip in clips:
        if merged:
            last=merged[-1]
            if (abs(last['source_end']-clip['source_start'])<1e-6 and abs(last['timeline_start']+last['duration']-clip['timeline_start'])<1e-6
                and abs(last.get('speed',1)-clip.get('speed',1))<1e-6):
                last['source_end']=clip['source_end'];last['duration']+=clip['duration'];continue
        merged.append(clip)
    return merged

def protect_and_sync(document,base,derived):
    from .auto_edit_timeline import validate_document
    from .source_caption_mapping import human_layout
    state=validate_document(document);snapshot=copy.deepcopy(state['snapshot'])
    if snapshot['metadata'].get('source_analysis_id')!=base.analysis_id or (
        snapshot['metadata'].get('transcript_revision') or {}).get('transcript_id')!=base.transcript_id:
        raise WorkflowError('AUTO_EDIT_TRANSCRIPT_BASE_DIFFERS_FROM_TIMELINE')
    spans=windows(snapshot,base.asset_id)
    changed=set(derived.provenance['reviewed_segment_ids'])
    mapping={old.segment_id:new for old,new in zip(base.segments,derived.segments,strict=True)}
    if spans:
        first=min(s['source_start'] for s in spans);last=max(s['source_end'] for s in spans)
        for old,new in zip(base.segments,derived.segments,strict=True):
            if old.segment_id not in changed:continue
            for word in new.words:
                if word.end_seconds<=first or word.start_seconds>=last:continue
                if not any(s['source_start']<=word.start_seconds and word.end_seconds<=s['source_end'] for s in spans):
                    raise WorkflowError('TRANSCRIPT_WORD_REVIEW_EXISTING_SOURCE_CUT_REQUIRES_REVIEW')
    for track in snapshot['tracks']:
        if track['kind']!='subtitles' or human_layout(snapshot,track):continue
        originals=[c for c in track['clips'] if c['metadata'].get('transcript_id')==base.transcript_id]
        if track.get('locked') and (any(c['metadata'].get('segment_id') in changed for c in originals)
            or any(min(mapping[i].end_seconds,s['source_end'])>max(mapping[i].start_seconds,s['source_start']) for i in changed for s in spans)):
            raise WorkflowError('AUTO_EDIT_SUBTITLE_TRACK_LOCKED')
        replacement=[]
        for clip in track['clips']:
            meta=clip['metadata'];old_id=meta.get('segment_id')
            if meta.get('transcript_id')!=base.transcript_id or old_id not in mapping:
                replacement.append(clip);continue
            if old_id not in changed:
                meta.update(segment_id=mapping[old_id].segment_id,transcript_id=derived.transcript_id)
                replacement.append(clip)
        for old_id in changed:
            segment=mapping[old_id]
            prototype=next((c for c in originals if c['metadata'].get('segment_id')==old_id),None)
            if prototype is None:
                prototype=originals[0] if originals else TimelineClip(clip_id='clip_'+uuid.uuid4().hex[:24],kind='subtitle',
                    label=segment.text[:120],timeline_start=0,duration=.1,metadata={'language':derived.language}).model_dump(mode='json')
            for span in spans:
                start=max(segment.start_seconds,span['source_start']);end=min(segment.end_seconds,span['source_end'])
                if end-start<.05:continue
                selected=[w for w in segment.words if start<=w.start_seconds<w.end_seconds<=end]
                if not selected:continue
                item=copy.deepcopy(prototype);speed=span.get('speed',1)
                text=' '.join(w.text for w in selected)
                # Source boundaries retain the explicit word coordinates. Rounding
                # them can exclude the first/last word in strict source containment.
                item.update(clip_id='clip_'+uuid.uuid4().hex[:24],label=text[:120],source_start=start,source_end=end,
                    timeline_start=round(span['timeline_start']+(start-span['source_start'])/speed,6),duration=round((end-start)/speed,6),speed=speed)
                # Text-only edits deliberately discard word alignment. This
                # explicit word review uses the saved word intervals instead.
                item['metadata'].pop('subtitle_text',None)
                item['metadata'].update(transcript_id=derived.transcript_id,segment_id=segment.segment_id,reviewed_word_text=text,
                    measured_source_words=[{'text':w.text,'start_seconds':w.start_seconds,'end_seconds':w.end_seconds} for w in selected],
                    confidence=None,timing_source='human_supplied_source_word_intervals',timing_independently_measured=False,
                    human_word_timing_review=True)
                replacement.append(item)
        if len(replacement)>2000:raise WorkflowError('TRANSCRIPT_WORD_REVIEW_CAPTION_LIMIT')
        if track.get('locked') and replacement!=track['clips']:
            raise WorkflowError('AUTO_EDIT_SUBTITLE_TRACK_LOCKED')
        track['clips']=sorted(replacement,key=lambda c:(c['timeline_start'],c['clip_id']))
    snapshot['metadata']['transcript_revision']={'transcript_id':derived.transcript_id,'version':derived.version,
        'human_edited':True,'review_required':True,'scene_highlight_semantics_stale':True,'human_word_timing_review':True}
    TimelineSnapshot.model_validate(snapshot)
    document['canonical_timeline']={'version':state['version']+1,'snapshot':snapshot,'sha256':digest(snapshot)}
    document['source_timeline_mutations']=document.get('source_timeline_mutations',[])+[{
        'version':state['version']+1,'mutation':{'type':'transcript-word-review'}}]
    validate_document(document)
