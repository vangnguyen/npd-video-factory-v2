"""Native semantic Vision intent/results, separate from real CPU pixel facts."""
import asyncio
import base64
from datetime import datetime,timezone
import hashlib
import json
import uuid

from .contracts import WorkflowError,digest
from .media import project_assets
from .media_frame_analysis import validate,frame_path,checked_path
from .vision_models import NativeVisionRequest
from .vision_provider import NativeFixtureVisionProvider
from .store import now
from app.auto_edit_models import MediaMetadata,SceneRead
from app.vision_logic import normalize_frames,build_vision_scenes,build_reframe_plans,rank_best_frames
from app.vision_models import VisionFrameRead,VisionSceneRead,ReframePlanRead


class NativeVision:
    def __init__(self,store,config,*,workspace_id='wsp_native_local'):
        self.store,self.config,self.workspace=store,config,workspace_id
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_vision_intents (
                vision_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,revision INTEGER NOT NULL,
                request_key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,status TEXT NOT NULL,result_sha256 TEXT,result_json TEXT,failure_code TEXT,
                actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                UNIQUE(workspace_id,project_id,request_key_sha256));
                CREATE INDEX IF NOT EXISTS native_vision_history ON native_vision_intents(workspace_id,project_id,created_at,vision_id);
                CREATE TABLE IF NOT EXISTS native_vision_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,vision_id TEXT NOT NULL,project_id TEXT NOT NULL,
                action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')

    def sources(self,project,payload):
        doc=project['document'];assets={asset['id']:asset for asset in project_assets(doc)};selected=[]
        records={record['observation']['observation_id']:record for record in doc.get('media_frame_analyses',[])}
        for identity in payload.observation_ids:
            record=records.get(identity)
            if record is None:raise WorkflowError('NATIVE_VISION_FRAME_OBSERVATION_NOT_FOUND',404)
            asset=assets.get(record['observation']['asset_id'])
            if asset is None:raise WorkflowError('NATIVE_VISION_ASSET_NOT_FOUND',404)
            value=validate(record,project['id'],asset);checked_path(self.config,asset)
            for frame in value['frames']:frame_path(self.store.root,frame)
            with checked_path(self.config,asset).open('rb') as file:header=file.read(16)
            content_type=('image/png' if header.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if header.startswith(b'\xff\xd8\xff')
                else ('video/quicktime' if header[8:12]==b'qt  ' else 'video/mp4') if header[4:8]==b'ftyp' else None)
            if content_type is None or content_type.split('/')[0]!=asset['kind']:raise WorkflowError('NATIVE_VISION_SOURCE_MAGIC_UNSUPPORTED')
            metadata=MediaMetadata(media_kind=asset['kind'],detected_content_type=content_type,duration_seconds=asset.get('duration_seconds'),
                width=asset.get('width'),height=asset.get('height'),fps=asset.get('fps'),video_codec=asset.get('video_codec'),audio_codec=asset.get('audio_codec'))
            scenes=[]
            from .auto_edit_analysis import validate_record,selected_transcript
            transcript_ref=None
            for analysis in reversed(doc.get('auto_edit_analyses',[])):
                if analysis['native_asset_id']==asset['id']:
                    parsed=validate_record(analysis,project['id'],doc,asset)
                    scenes=[scene.model_dump(mode='json') for scene in parsed.scenes]
                    transcript=selected_transcript(doc,parsed)
                    transcript_ref={'transcript_id':transcript.transcript_id,'version':transcript.version,'sha256':digest(transcript.model_dump(mode='json'))} if transcript else None
                    break
            selected.append({'asset':asset,'source_observation':record,'source_media':metadata.model_dump(mode='json'),'scenes':scenes,'transcript_ref':transcript_ref})
        return selected

    def event(self,con,row,action,actor,**evidence):
        con.execute('INSERT INTO native_vision_events(vision_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?)',
            (row['vision_id'],row['project_id'],action,actor,json.dumps(evidence),now()))

    def read(self,row):
        value=dict(row);snapshot=json.loads(value.pop('snapshot_json'));raw=value.pop('result_json');result=json.loads(raw) if raw else None
        if (digest(snapshot)!=value['snapshot_sha256'] or snapshot.get('workspace_id')!=self.workspace
            or snapshot.get('project_id')!=value['project_id'] or snapshot.get('request_fingerprint')!=value['request_fingerprint']
            or digest(snapshot.get('request'))!=value['request_fingerprint']):raise WorkflowError('NATIVE_VISION_SNAPSHOT_EVIDENCE_INVALID')
        if (value['status']=='succeeded')!=(result is not None) or (result is not None and (not isinstance(result,dict) or digest(result)!=value['result_sha256'])):
            raise WorkflowError('NATIVE_VISION_RESULT_EVIDENCE_INVALID')
        if result is not None:
            if (result.get('schema_version')!='native-semantic-vision-fixture-v1' or result.get('mock') is not True or result.get('semantic_inference_performed') is not False or result.get('external_provider_calls')!=0
                or result.get('automatic_planning_eligible') is not False or result.get('canonical_timeline_mutated') is not False
                or result.get('measured_cpu_observations_mutated') is not False or result.get('source_media_mutated') is not False
                or result.get('owner_uat_accepted') is not False or result.get('paid_operations')!=0 or result.get('actual_provider_cost_vnd') is not None
                or snapshot['request'].get('provider_mode')!='fixture' or snapshot['request'].get('fixture_acknowledged') is not True
                or snapshot.get('provider_key')!=NativeFixtureVisionProvider.key or snapshot.get('model')!=NativeFixtureVisionProvider.model):
                raise WorkflowError('NATIVE_VISION_RESULT_EVIDENCE_INVALID')
            expected=[(source['asset']['id'],source['asset']['sha256'],source['source_observation']['sha256']) for source in snapshot['sources']]
            if [(item['asset_id'],item['source_sha256'],item['source_observation_sha256']) for item in result['assets']]!=expected:
                raise WorkflowError('NATIVE_VISION_RESULT_EVIDENCE_INVALID')
            for item,source in zip(result['assets'],snapshot['sources']):
                observation=validate(source['source_observation'],value['project_id'],source['asset'])
                frames=[VisionFrameRead.model_validate(frame) for frame in item['frames']]
                scenes=[VisionSceneRead.model_validate(scene) for scene in item['scenes']]
                provenance=item.get('provenance',{})
                if (item.get('source_observation_id')!=observation['observation_id'] or item.get('source_frame_evidence')!=observation['frames']
                    or item.get('source_media')!=source['source_media'] or item.get('provider')!=NativeFixtureVisionProvider.key or item.get('model')!=NativeFixtureVisionProvider.model
                    or item.get('tracking_available') is not False or item.get('subject_tracks')!=[] or item.get('broll_relevance') is not None
                    or item.get('broll_relevance_status')!='NOT_INFERRED' or item.get('candidate_basis')!='explicit_fixture_quality_only'
                    or provenance.get('fixture') is not True or provenance.get('semantic_model_saw_pixels') is not False
                    or provenance.get('external_call') is not False or provenance.get('paid') is not False
                    or provenance.get('source_checksum')!=source['asset']['sha256'] or provenance.get('asset_id')!=source['asset']['id']
                    or [(frame.timestamp_seconds,frame.evidence_frame_reference) for frame in frames]
                        !=[(frame['timestamp_seconds'],frame['reference']) for frame in observation['frames']]
                    or any(frame.provider_key!=item['provider'] or frame.model!=item['model'] for frame in frames)
                    or not set(item['best_frame_ids']+item['thumbnail_candidate_ids'])<={frame.frame_id for frame in frames}
                    or any(not set(scene.evidence_frame_ids)<={frame.frame_id for frame in frames} for scene in scenes)):
                    raise WorkflowError('NATIVE_VISION_RESULT_EVIDENCE_INVALID')
                if {plan['aspect_ratio'] for plan in item['reframe_plans']}!={'9:16','16:9','1:1','4:5'} or len(item['reframe_plans'])!=4:
                    raise WorkflowError('NATIVE_VISION_RESULT_EVIDENCE_INVALID')
                binding=digest([value['snapshot_sha256'],source['asset']['id'],source['source_observation']['sha256']])
                expected_plans=build_reframe_plans(frames=frames,tracks=[],metadata=MediaMetadata.model_validate(source['source_media']),
                    aspect_ratios=['9:16','16:9','1:1','4:5'],manual_overrides=[],minimum_tracking_confidence=.7,
                    subtitle_safe_area_bottom=.2,maximum_jump=.15,fingerprint=binding)
                if item['reframe_plans']!=[plan.model_dump(mode='json') for plan in expected_plans]:
                    raise WorkflowError('NATIVE_VISION_RESULT_EVIDENCE_INVALID')
                for plan in item['reframe_plans']:
                    parsed=ReframePlanRead.model_validate(plan)
                    if parsed.fallback!='center_crop' or parsed.strategy!='center_crop' or not parsed.needs_attention or parsed.confidence!=0 or parsed.manual_override_applied:
                        raise WorkflowError('NATIVE_VISION_FIXTURE_REFRAME_NOT_ATTENTION_BOUND')
        value.pop('request_key_sha256')
        return {**value,'schema_version':'native-vision-intent-v1','snapshot':snapshot,'result':result,'external_provider_calls':0,
            'real_provider_tested':False,'official_adapter_state':'NOT_CONFIGURED','production_deployed':False}

    def row(self,con,project,identity):
        self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        row=con.execute('SELECT * FROM native_vision_intents WHERE vision_id=? AND project_id=? AND workspace_id=?',(identity,project,self.workspace)).fetchone()
        if row is None:raise WorkflowError('NATIVE_VISION_NOT_FOUND',404)
        return row

    def create(self,project_id,payload,*,actor):
        request=payload.model_dump(mode='json',exclude={'request_key'});fingerprint=digest(request);key=hashlib.sha256(payload.request_key.encode()).hexdigest()
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_vision_intents WHERE workspace_id=? AND project_id=? AND request_key_sha256=?',(self.workspace,project_id,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_VISION_IDEMPOTENCY_CONFLICT')
                return self.read(prior),True
            project=self.store.editable(con,project_id,payload.revision);sources=self.sources(project,payload)
            snapshot={'schema_version':'native-vision-snapshot-v1','workspace_id':self.workspace,'project_id':project_id,'revision':payload.revision,
                'document_sha256':digest(project['document']),'request':request,'request_fingerprint':fingerprint,'sources':sources,
                'provider_key':NativeFixtureVisionProvider.key if payload.provider_mode=='fixture' else 'vision-not-configured',
                'model':NativeFixtureVisionProvider.model if payload.provider_mode=='fixture' else 'not-configured',
                'paid_authorization':False,'automatic_planning_eligible':False}
            status='queued' if payload.provider_mode=='fixture' else 'not_configured';identity='nvis_'+uuid.uuid4().hex;stamp=now()
            with_count=con.execute('SELECT COUNT(*) FROM native_vision_intents WHERE workspace_id=? AND project_id=?',(self.workspace,project_id)).fetchone()[0]
            if with_count>=256:raise WorkflowError('NATIVE_VISION_HISTORY_LIMIT')
            con.execute('INSERT INTO native_vision_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project_id,payload.revision,key,fingerprint,digest(snapshot),json.dumps(snapshot,ensure_ascii=False),status,None,None,
                 'NATIVE_VISION_OFFICIAL_PROVIDER_AND_BUDGET_NOT_CONFIGURED' if status=='not_configured' else None,actor,stamp,stamp))
            row=self.row(con,project_id,identity);self.event(con,row,'vision.intent.created',actor,status=status,external_calls=0)
            return self.read(row),False

    def process(self,*,project=None,identity=None,fingerprint=None):
        with self.store.transaction() as con:
            if identity:
                row=self.row(con,project,identity)
                if fingerprint!=row['request_fingerprint']:raise WorkflowError('NATIVE_VISION_BINDING_CHANGED')
                if row['status']=='succeeded':return self.read(row)
                candidates=[row]
            else:candidates=con.execute("SELECT * FROM native_vision_intents WHERE workspace_id=? AND status='queued' ORDER BY created_at,vision_id LIMIT 20",(self.workspace,)).fetchall()
            for row in candidates:
                if row['status']!='queued':continue
                con.execute('SAVEPOINT native_vision_fixture')
                try:
                    value=self.read(row);snapshot=value['snapshot'];payload=NativeVisionRequest.model_validate({**snapshot['request'],'request_key':'internal-native-vision-key'})
                    current=self.store.editable(con,row['project_id'],row['revision'])
                    if payload.provider_mode!='fixture' or not payload.fixture_acknowledged or digest(current['document'])!=snapshot['document_sha256'] or self.sources(current,payload)!=snapshot['sources']:
                        raise WorkflowError('NATIVE_VISION_REVISION_OR_FRAME_BINDING_CHANGED')
                    output=[]
                    for source in snapshot['sources']:
                        observation=source['source_observation']['observation'];asset=source['asset'];metadata=MediaMetadata.model_validate(source['source_media'])
                        provider=NativeFixtureVisionProvider(observation['frames']);scenes=[SceneRead.model_validate(scene) for scene in source['scenes']]
                        prediction=asyncio.run(provider.analyze(checked_path(self.config,asset),metadata=metadata,scenes=scenes,
                            asset_id=asset['id'],checksum_sha256=asset['sha256'],sample_interval_seconds=1))
                        if (prediction.provenance.get('fixture') is not True or prediction.provenance.get('external_call') is not False
                            or prediction.provenance.get('paid') is not False or prediction.provenance.get('semantic_model_saw_pixels') is not False
                            or prediction.provenance.get('source_checksum')!=asset['sha256'] or prediction.actual_cost_vnd is not None
                            or [(frame.timestamp_seconds,frame.evidence_frame_reference) for frame in prediction.frames]
                               !=[(frame['timestamp_seconds'],frame['reference']) for frame in observation['frames']]):
                            raise WorkflowError('NATIVE_VISION_FIXTURE_PROVIDER_REQUIRED')
                        binding=digest([row['snapshot_sha256'],asset['id'],source['source_observation']['sha256']])
                        frames=normalize_frames(prediction.frames,provider_key=provider.key,model=provider.model,fingerprint=binding)
                        # Fixture semantic tracks are deliberately unavailable for actual crop/planning decisions.
                        plans=build_reframe_plans(frames=frames,tracks=[],metadata=metadata,aspect_ratios=['9:16','16:9','1:1','4:5'],manual_overrides=[],
                            minimum_tracking_confidence=.7,subtitle_safe_area_bottom=.2,maximum_jump=.15,fingerprint=binding)
                        best,thumbs=rank_best_frames(frames)
                        output.append({'asset_id':asset['id'],'source_sha256':asset['sha256'],'source_observation_id':observation['observation_id'],
                            'source_observation_sha256':source['source_observation']['sha256'],'source_frame_evidence':observation['frames'],
                            'source_media':source['source_media'],'provider':provider.key,'model':provider.model,'confidence':.6,
                            'frames':[frame.model_dump(mode='json') for frame in frames],
                            'scenes':[scene.model_dump(mode='json') for scene in build_vision_scenes(scenes=scenes,frames=frames,fingerprint=binding)],
                            'subject_tracks':[],'tracking_available':False,'reframe_plans':[plan.model_dump(mode='json') for plan in plans],
                            'best_frame_ids':best,'thumbnail_candidate_ids':thumbs,'candidate_basis':'explicit_fixture_quality_only',
                            'broll_relevance':None,'broll_relevance_status':'NOT_INFERRED','provenance':prediction.provenance})
                    result={'schema_version':'native-semantic-vision-fixture-v1','mock':True,'semantic_inference_performed':False,
                        'external_provider_calls':0,'paid_operations':0,'actual_provider_cost_vnd':None,'actual_local_compute_cost_vnd':None,
                        'assets':output,'automatic_planning_eligible':False,'canonical_timeline_mutated':False,'measured_cpu_observations_mutated':False,
                        'source_media_mutated':False,'owner_uat_accepted':False,'created_at':now()}
                    con.execute("UPDATE native_vision_intents SET status='succeeded',result_sha256=?,result_json=?,updated_at=? WHERE vision_id=?",
                        (digest(result),json.dumps(result,ensure_ascii=False),now(),row['vision_id']))
                    self.event(con,row,'vision.fixture.completed','native-vision-fixture-worker',mock=True,automatic_planning_eligible=False,external_calls=0)
                    con.execute('RELEASE native_vision_fixture')
                except Exception as error:
                    con.execute('ROLLBACK TO native_vision_fixture');con.execute('RELEASE native_vision_fixture')
                    code=error.code if isinstance(error,WorkflowError) else 'NATIVE_VISION_FIXTURE_FAILED'
                    con.execute("UPDATE native_vision_intents SET status='failed',failure_code=?,updated_at=? WHERE vision_id=?",(code,now(),row['vision_id']))
                    self.event(con,row,'vision.intent.failed','native-vision-fixture-worker',failure_code=code,external_calls=0)
                return self.read(self.row(con,row['project_id'],row['vision_id']))
            return None

    def get(self,project,identity):
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity));events=con.execute('SELECT * FROM native_vision_events WHERE vision_id=? ORDER BY event_id DESC LIMIT 101',(identity,)).fetchall()
            return {**value,'events':[{**dict(event),'evidence_json':json.loads(event['evidence_json'])} for event in events[:100]],'events_truncated':len(events)>100}

    def cancel(self,project,identity,*,fingerprint,actor):
        with self.store.transaction() as con:
            row=self.row(con,project,identity)
            if row['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_VISION_BINDING_CHANGED')
            if row['status']=='succeeded':raise WorkflowError('NATIVE_VISION_ALREADY_COMPLETE')
            if row['status']!='cancelled':
                con.execute("UPDATE native_vision_intents SET status='cancelled',updated_at=? WHERE vision_id=?",(now(),identity))
                self.event(con,row,'vision.intent.cancelled',actor,external_calls=0)
            return self.read(self.row(con,project,identity))

    def page(self,project,*,limit=25,cursor=None):
        if type(limit)is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_VISION_PAGE_INVALID',400)
        after=None
        if cursor:
            try:
                if not isinstance(cursor,str) or len(cursor)>1000:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(after,list) or len(after)!=4 or after[:2]!=[self.workspace,project]:raise ValueError()
                if not isinstance(after[2],str) or not isinstance(after[3],str) or datetime.fromisoformat(after[2]).tzinfo is None:raise ValueError()
            except (ValueError,TypeError):raise WorkflowError('NATIVE_VISION_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone());where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if after:where+=' AND (created_at<? OR (created_at=? AND vision_id<?))';params.extend([after[2],after[2],after[3]])
            rows=con.execute('SELECT * FROM native_vision_intents WHERE '+where+' ORDER BY created_at DESC,vision_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,rows[limit-1]['created_at'],rows[limit-1]['vision_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-vision-page-v1','workspace_id':self.workspace,'project_id':project,'items':[self.read(row) for row in rows[:limit]],
                'next_cursor':next_cursor,'limit':limit,'official_adapter_state':'NOT_CONFIGURED','automatic_planning_eligible':False,'external_provider_calls':0}
