"""Atomic, idempotent unapproved highlight projects from saved Source evidence."""
import copy
import json
from types import SimpleNamespace
from typing import Literal
import uuid
from pydantic import Field
from .contracts import WorkflowError,digest
from .auto_edit_timeline import SCHEMA,_cas,_selected,validate_document,view as timeline_view
from .source_preview import resolve_assets
from .source_duplicate import rebind
from app.highlight_draft_logic import HighlightDraftRequest,build_drafts,HighlightDraftConflict
from app.scene_evidence import combine_scene_evidence

ALGORITHM='native-auto-shorts-v1'
ACTION='auto_shorts_created_unapproved'
MAX_BATCHES=50


class Create(HighlightDraftRequest):
    analysis_id:str=Field(pattern=r'^ana_[a-f0-9]{24}$')
    transcript_id:str|None=Field(default=None,pattern=r'^trn_[a-f0-9]{24}$')
    scene_intelligence_id:None=None
    mode:Literal['auto_shorts']='auto_shorts'
    expected_version:int|None=Field(default=None,ge=1,strict=True)
    request_key:str=Field(pattern=r'^[a-f0-9]{32}$')
    aspect_ratio:Literal['9:16','16:9','1:1','4:5']='9:16'


def records(con,project_id):
    return [json.loads(row['payload']) for row in con.execute(
        'SELECT payload FROM events WHERE project_id=? AND action=? ORDER BY id',(project_id,ACTION))]


def view(store,project_id):
    with store.transaction() as con:
        store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())
        batches=records(con,project_id)
    return {'project_id':project_id,'batches':batches,'provider_calls':0,'recommendation_only':True}


def create(store,config,project_id,revision,body):
    try:payload=Create.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_SHORTS_REQUEST_INVALID',400) from None
    request_sha=digest({'revision':revision,'payload':payload.model_dump(mode='json')})
    with store.transaction() as con:
        batches=records(con,project_id)
        cached=next((item for item in batches if item['request_key']==payload.request_key),None)
        if cached:
            if cached['request_sha256']!=request_sha:raise WorkflowError('AUTO_SHORTS_IDEMPOTENCY_CONFLICT')
            result=cached
        else:
            if len(batches)>=MAX_BATCHES:raise WorkflowError('AUTO_SHORTS_BATCH_LIMIT',400)
            project=store.editable(con,project_id,revision);document=project['document']
            if document.get('input_kind')!='media' or document.get('proposal') is not None:
                raise WorkflowError('AUTO_EDIT_SEPARATE_MEDIA_PROJECT_REQUIRED',400)
            _cas(project,payload.expected_version,create=True)
            analysis,asset=_selected(document,project_id,payload.analysis_id)
            if payload.transcript_id!=(analysis.transcript.transcript_id if analysis.transcript else None):
                raise WorkflowError('AUTO_EDIT_TRANSCRIPT_VERSION_CHANGED')
            reference=SimpleNamespace(asset_id=analysis.asset_id,checksum_sha256=asset['sha256'],
                content_type='video/mp4',object_key=asset['id'])
            scenes=combine_scene_evidence(analysis,reference)
            assessment=SimpleNamespace(scenes=scenes,assessment_id='sci_'+digest([analysis.analysis_id,payload.transcript_id])[:24],
                fingerprint=digest([scene.model_dump(mode='json') for scene in scenes]))
            try:prepared=build_drafts(analysis,reference,payload.model_copy(update={'count':5}),assessment)
            except (HighlightDraftConflict,ValueError):raise WorkflowError('AUTO_SHORTS_SELECTION_INVALID',400) from None
            if not prepared:raise WorkflowError('AUTO_SHORTS_NO_COMPLETE_SPEECH_WINDOW_FITS',400)
            from .store import now
            timestamp=now();children=[];seen=set();parent_sha=digest(document)
            for fingerprint,snapshot,evidence in prepared:
                if len(children)>=payload.count:break
                window=(round(evidence['source_start'],6),round(evidence['source_end'],6))
                if window in seen:continue
                seen.add(window);rank=len(children)+1
                identifier=uuid.uuid5(uuid.NAMESPACE_URL,ALGORITHM+'/'+project_id+'/'+request_sha+'/'+fingerprint).hex
                width,height={'9:16':(1080,1920),'16:9':(1920,1080),'1:1':(1080,1080),'4:5':(1080,1350)}[payload.aspect_ratio]
                snapshot.width,snapshot.height,snapshot.aspect_ratio=width,height,payload.aspect_ratio
                snapshot.metadata.update(native_auto_edit_schema=SCHEMA,native_project_id=project_id,
                    reframe_review={'fallback':'center_crop','needs_attention':True,'tracking_confidence':None,
                        'reason':'no subject tracking evidence; review crop before approval'},
                    human_review_required=True,source_selection={'requested_window':list(window),
                        'word_safe_window':list(window),'silence_decision_ids':[]},
                    source_short={'algorithm':ALGORITHM,'rank':rank,'parent_project_id':project_id,
                        'parent_revision':revision,'parent_document_sha256':parent_sha,'evidence':evidence,
                        'human_approval_required':True,'provider_calls':0,'source_media_mutated':False})
                for track in snapshot.tracks:
                    for clip in track.clips:
                        if clip.asset_id:clip.metadata['native_asset_id']=asset['id']
                seed=copy.deepcopy(document);seed['music']=None;seed['source_broll_plans']=[]
                seed['canonical_timeline']={'version':1,'snapshot':snapshot.model_dump(mode='json'),
                    'sha256':digest(snapshot.model_dump(mode='json'))}
                validate_document(seed)
                child_document=rebind(seed,project_id,identifier,revision,timestamp,parent_document_sha256=parent_sha)
                # Ranking lineage identifies the actual parent, not the rebound child.
                child_document['canonical_timeline']['snapshot']['metadata']['source_short']=copy.deepcopy(snapshot.metadata['source_short'])
                child_document['canonical_timeline']['sha256']=digest(child_document['canonical_timeline']['snapshot'])
                validate_document(child_document)
                child_document['name']=document['name'][:110]+' — Short '+str(rank)
                resolve_assets(config,{'id':identifier,'document':child_document})
                con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',
                    (identifier,1,json.dumps(child_document,ensure_ascii=False),None,timestamp,timestamp))
                store.version(con,identifier)
                store.event(con,identifier,'auto_short_created_review_required',{
                    'parent_project_id':project_id,'parent_revision':revision,'request_key':payload.request_key,
                    'source_window':list(window),'provider_calls':0,'paid_operations':0,'approval_created':False})
                children.append({'project_id':identifier,'rank':rank,'name':child_document['name'],
                    'source_window':list(window),'duration_seconds':snapshot.duration_seconds,
                    'timeline_sha256':child_document['canonical_timeline']['sha256'],'evidence':evidence})
            result={'algorithm':ALGORITHM,'request_key':payload.request_key,'request_sha256':request_sha,
                'source_project_id':project_id,'source_revision':revision,'source_document_sha256':parent_sha,
                'analysis_id':analysis.analysis_id,'transcript_id':payload.transcript_id,'aspect_ratio':payload.aspect_ratio,
                'requested_count':payload.count,'generated_count':len(children),
                'fewer_candidates_than_requested':len(children)<payload.count,
                'maximum_duration_seconds':payload.maximum_duration_seconds,'drafts':children,
                'scene_evidence':{'assessment_id':assessment.assessment_id,'fingerprint':assessment.fingerprint,
                    'scenes':[scene.model_dump(mode='json') for scene in scenes]},
                'provider_calls':0,'paid_operations':0,'parent_document_mutated':False,
                'human_approval_required':True,'created_at':timestamp}
            store.event(con,project_id,ACTION,result)
    # No nested write transaction while materializing canonical projections.
    return {'batch':result,'projects':[timeline_view(store,item['project_id']) for item in result['drafts']]}
