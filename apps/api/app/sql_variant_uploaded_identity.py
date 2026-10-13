"""Pure imported-evidence identity map. Historic raw provider JSON is never rewritten."""
import copy
from .sql_variant_identity import child_ids, center_crop
from .sql_variant_repository import identity, SqlVariantError
from .sql_variant_models import digest
from .timeline_models import TimelineSnapshot
from .content_models import ContentDocument

TABLE_IDS = {'auto_edit_analyses':'analysis_id','transcripts':'transcript_id',
    'transcript_segments':'segment_id','transcript_words':'word_id','scenes':'scene_id',
    'silence_decisions':'decision_id','highlights':'highlight_id',
    'uploaded_audio_transcriptions':'audio_id','uploaded_audio_transcript_versions':'transcript_id'}
PREFIX = {'analysis_id':'ana','transcript_id':'trn','segment_id':'seg','word_id':'wrd',
    'scene_id':'scn','decision_id':'sil','highlight_id':'hig','audio_id':'aud'}

def mapped_id(member, kind, original):
    return PREFIX[kind]+'_'+digest(['sql-variant-import.v1',member,kind,original])[:24]

def rows(value, table):
    return [r for group in value['source_graph'] if group['table']==table for r in group['rows']]

def id_map(value):
    ids = child_ids(value['member_id'], value['source_assets'])
    mapping = dict(ids['assets'])
    for table, key in TABLE_IDS.items():
        for row in rows(value,table):
            mapping[row[key]]=mapped_id(value['member_id'], key,row[key])
    # Audio first-version normalization has a stable identity contract.
    for parent in rows(value,'uploaded_audio_transcriptions'):
        audio=mapping[parent['audio_id']]
        for version in rows(value,'uploaded_audio_transcript_versions'):
            if version['audio_id']!=parent['audio_id'] or version['version']!=1:continue
            body=version['transcript_json'];mapping[body['transcript_id']]='trn_'+digest([audio,'original'])[:24]
            for segment in body['segments']:
                mapping[segment['segment_id']]='seg_'+digest([audio,'segment',segment['ordinal']])[:24]
                for word in segment['words']:
                    mapping[word['word_id']]='wrd_'+digest([audio,'word',word['ordinal']])[:24]
        for version in rows(value,'uploaded_audio_transcript_versions'):
            if version['audio_id']!=parent['audio_id'] or version['version']==1:continue
            body=version['transcript_json']
            for segment in body['segments']:
                mapping[segment['segment_id']]=mapped_id(value['member_id'],'segment_id',segment['segment_id'])
                for word in segment['words']:
                    mapping[word['word_id']]=mapped_id(value['member_id'],'word_id',word['word_id'])
    if len(set(mapping.values()))!=len(mapping):raise SqlVariantError('SQL_VARIANT_IMPORT_ID_COLLISION')
    ids['graph']=mapping
    return ids

def rebind(value,mapping):
    """Only exact known identifiers, including map keys. No regex replacement in raw evidence."""
    if isinstance(value,str):return mapping.get(value,value)
    if isinstance(value,list):return [rebind(v,mapping) for v in value]
    if isinstance(value,dict):return {mapping.get(k,k):rebind(v,mapping) for k,v in value.items()}
    return copy.deepcopy(value)

def audio_versions(value, ids):
    output={}
    for original in rows(value,'uploaded_audio_transcript_versions'):
        body=rebind(original['transcript_json'],ids['graph'])
        body['provenance']=rebind_provenance(original['transcript_json']['provenance'],ids['graph'])
        if original['version']==1:
            # Rebuild the normalized child snapshot with the existing pure
            # normalizer, preserving opaque original provider/safety/clock JSON.
            from types import SimpleNamespace
            from datetime import datetime
            from .uploaded_audio_service import normalize_evidence
            parent=next(p for p in rows(value,'uploaded_audio_transcriptions') if p['audio_id']==original['audio_id'])
            imported=SimpleNamespace(audio_id=ids['graph'][parent['audio_id']],asset_id=ids['assets'][parent['asset_id']],
                source_sha256=parent['source_sha256'],media_metadata_json=parent['media_metadata_json'],
                configuration_json=parent['configuration_json'])
            body=normalize_evidence(parent['original_evidence_json'],imported,
                created_at=datetime.fromisoformat(original['transcript_json']['created_at'])).model_dump(mode='json')
        # Hashes are bindings to normalized child identities, never raw provider JSON.
        output[original['transcript_id']]=body
    return output

def rebind_provenance(original,mapping):
    # Opaque raw model/clock/safety evidence remains byte-equivalent to its origin.
    result=copy.deepcopy(original)
    for key in ('derived_from_transcript_id','changed_segment_ids','reviewed_segment_ids','segment_id_mapping'):
        if key in result:result[key]=rebind(result[key],mapping)
    return result

def derive_uploaded(value,copies):
    ids=id_map(value);mapping=ids['graph'];profile=value['profile']
    content=None
    if value['source_content'] is not None:
        content=copy.deepcopy(value['source_content']['snapshot']['content']);content['approved']=False
        for scene in content['scenes']:
            scene['scene_id']=identity('scene_',value['member_id']+'/scene/'+scene['scene_id'])
            for field in ('asset_id','analysis_id'):
                if scene.get(field):scene[field]=mapping[scene[field]]
            scene['official_render']=False
        content=ContentDocument.model_validate(content).model_dump(mode='json')
    source=value['source_timeline'];snapshot=copy.deepcopy(source);metadata=snapshot['metadata']
    # Keep exact parent-only semantic/approval evidence in the frozen receipt.
    archive={}
    for key in ('approval','approved','reviewed_scene_selection','reviewed_local_scene_selection',
            'highlight_draft','highlight_draft_id','selected_highlight_id','scene_assessment','scene_intelligence',
            'scene_intelligence_assessment','vision','vision_review','vision_analysis_id','reframe_plan_id',
            'source_media_plan_id','narration_reflow'):
        if key in metadata:archive[key]=metadata.pop(key)
    snapshot=rebind(snapshot,mapping);metadata=snapshot['metadata']
    metadata['inherited_review_evidence']={'original':archive,'sha256':digest(archive),'authority_transferred':False}
    metadata['sql_variant_derivative']={'schema_version':'sql-variant-evidence-lineage.v1',
        'family_id':value['family_id'],'member_id':value['member_id'],'master_project_id':value['master_project_id'],
        'source_mode':value['source_mode'],'source_timeline_sha256':digest(source),
        'family_snapshot_sha256':value['family_snapshot_sha256'],'approval_inherited':False,
        'rights_override_inherited':False,'new_inference_calls':0,'human_review_required':True}
    if content is not None:
        metadata.update(content_version_id=ids['content_version_id'],content_sha256=digest(content))
        # Content scene IDs are semantic storyboard IDs, separate from detected scene IDs.
        scene_map={old['scene_id']:new['scene_id'] for old,new in zip(value['source_content']['snapshot']['content']['scenes'],content['scenes'])}
        snapshot=rebind(snapshot,scene_map);metadata=snapshot['metadata']
    versions=audio_versions(value,ids)
    for old,value_binding in (source['metadata'].get('uploaded_audio_bindings_v1') or {}).items():
        child=metadata['uploaded_audio_bindings_v1'][mapping[old]]
        child['binding_id']=identity('abnd_',value['member_id']+'/audio-binding/'+value_binding['binding_id'])
        child['transcript']=versions[value_binding['transcript_id']]
        child['transcript_sha256']=digest(child['transcript']);child['human_review_required']=True
        binding_map={value_binding['binding_id']:child['binding_id']}
        snapshot=rebind(snapshot,binding_map);metadata=snapshot['metadata']
    metadata['reframe']={'aspect_ratio':profile['aspect_ratio'],'fallback':'center_crop','needs_attention':True,'confidence':None}
    for track in snapshot['tracks']:
        for clip in track['clips']:
            clip['clip_id']=identity('clip_',value['member_id']+'/clip/'+clip['clip_id'])
            meta=clip['metadata']
            if clip.get('asset_id'):
                old=next(k for k,v in ids['assets'].items() if v==clip['asset_id'])
                source_asset=value['source_assets'][old]
                meta.update(rights_status='unknown',official_render=False)
                if meta.get('object_key'):meta['object_key']=copies[old]['object_key']
                if track['type']=='video':
                    dims=copies[old]['dimensions'] or [source_asset['provenance']['media_metadata'].get('width'),source_asset['provenance']['media_metadata'].get('height')]
                    if any(type(n)is not int or n<=0 for n in dims):raise SqlVariantError('SQL_VARIANT_COPY_MEDIA_INVALID')
                    crop=center_crop(*dims,profile['width'],profile['height']);clip['crop']=crop
                    meta['reframe']={'schema_version':1,'keyframes':[{'time':clip['source_start'] or 0.,**crop}],
                        'aspect_ratio':profile['aspect_ratio'],'confidence':None,'fallback':'center_crop','needs_attention':True,
                        'subject_tracking':'NOT_CONFIGURED','source_width':dims[0],'source_height':dims[1],'time_space':'source_seconds'}
    if isinstance(metadata.get('media_plan'),list):metadata['media_plan_sha256']=digest(metadata['media_plan'])
    snapshot.update(width=profile['width'],height=profile['height'],aspect_ratio=profile['aspect_ratio'],source_media_mutated=False,publish_requested=False)
    return ids,content,TimelineSnapshot.model_validate(snapshot).model_dump(mode='json')
