"""Scoped narrated families reuse verified source PCM, never source authority."""
import base64,copy,json,re,sqlite3,uuid
from .backup import guard
from .contracts import WorkflowError,digest
from .narrated_variants_models import Create,Derivation
from .source_variants import catalog as source_catalog,Profile,Catalog as SourceCatalog
from .store import now

SCHEMA='native-narrated-variants-v1'

def catalog():
    source=source_catalog()
    value={'schema_version':'native-narrated-variant-catalog-v1','catalog_ref':'narrated-platform-formats@1','profiles':source['profiles']}
    return {**value,'sha256':digest(value),'provider_dispatches':0,'publishing_enabled':False}

def check_workspace(root,workspace):
    marker=guard(root/'.vf-auth-workspace.json')
    try:
        if not marker.exists():
            if workspace!='wsp_native_local':raise ValueError()
        elif not marker.is_file() or marker.stat().st_size>512 or json.loads(marker.read_bytes())!={'schema':'vf-native-workspace-binding-v1','workspace_id':workspace}:
            raise ValueError()
    except (ValueError,OSError,TypeError):raise WorkflowError('NARRATED_VARIANT_WORKSPACE_CHANGED') from None

class NativeNarratedVariants:
    def __init__(self,store,*,workspace_id='wsp_native_local',initialize=True):
        self.store,self.workspace=store,workspace_id;check_workspace(store.root,workspace_id)
        if not initialize:return
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_narrated_variant_batches (
                batch_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,master_project_id TEXT NOT NULL,
                request_key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(workspace_id,master_project_id,request_key_sha256));
                CREATE INDEX IF NOT EXISTS native_narrated_variant_history ON native_narrated_variant_batches(workspace_id,master_project_id,created_at,batch_id);''')

    def read(self,row,con):
        try:
            value=dict(row);snapshot=json.loads(value.pop('snapshot_json'));result=json.loads(value.pop('result_json'))
            check_workspace(self.store.root,self.workspace)
            request=Create.model_validate({**snapshot['request'],'request_key':'internal-narrated-variant-key'})
            if (digest(snapshot)!=value['snapshot_sha256'] or digest(result)!=value['result_sha256']
                or snapshot['workspace_id']!=self.workspace or value['workspace_id']!=self.workspace
                or snapshot['master_project_id']!=value['master_project_id'] or digest(snapshot['request'])!=value['request_fingerprint']
                or [v['profile']['profile_ref'] for v in result['variants']]!=request.profile_refs
                or result['publishing_enabled'] is not False or result['master_project_mutated'] is not False
                or result['external_provider_calls']!=0 or result['new_inference_calls']!=0):raise ValueError()
            frozen=snapshot['catalog']
            parsed=SourceCatalog.model_validate({'schema_version':'native-source-variant-catalog-v1',
                'catalog_ref':frozen['catalog_ref'],'profiles':frozen['profiles']}).model_dump(mode='json')
            catalog_value={**parsed,'schema_version':'native-narrated-variant-catalog-v1'}
            if (frozen['schema_version']!=catalog_value['schema_version'] or digest(catalog_value)!=frozen['sha256']
                or frozen['provider_dispatches']!=0 or frozen['publishing_enabled'] is not False
                or result['schema_version']!=SCHEMA or result['human_approval_required_per_variant'] is not True
                or result['rights_authority_inherited'] is not False
                or snapshot['schema_version']!='native-narrated-variant-snapshot-v1'
                or snapshot['master_revision']!=request.revision):raise ValueError()
            profiles={p['profile_ref']:p for p in parsed['profiles']}
            parent=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',
                (value['master_project_id'],snapshot['master_revision'])).fetchone()
            parent_doc=json.loads(parent['document']) if parent else None
            from .shot_adapter import validate_document
            if (parent_doc is None or digest(parent_doc)!=snapshot['master_document_sha256']
                or digest(parent_doc['prepared_narration'])!=snapshot['source_prepared_reference_sha256']
                or snapshot['source_prepared_reference_sha256']!=request.expected_prepared_reference_sha256
                or parent_doc['canonical_timeline']['sha256']!=snapshot['master_timeline_sha256']
                or parent_doc['canonical_timeline']['version']!=request.expected_version):raise ValueError()
            validate_document(parent_doc)
            if len({c['project_id'] for c in result['variants']})!=len(result['variants']):raise ValueError()
            for child in result['variants']:
                derivation=Derivation.model_validate(child['derivation']).model_dump(mode='json')
                Profile.model_validate(child['profile'])
                if (derivation!=child['derivation'] or child['profile']!=profiles.get(child['profile']['profile_ref'])
                    or derivation['child_project_id']!=child['project_id'] or derivation['batch_id']!=value['batch_id']
                    or derivation['workspace_id']!=self.workspace or derivation['master_project_id']!=value['master_project_id']
                    or any(derivation[k]!=snapshot[k] for k in ('source_project_id','source_narration_job_id','source_plan_sha256','source_prepared_reference_sha256'))):
                    raise ValueError()
                version=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=1',(child['project_id'],)).fetchone()
                if version is None or digest(json.loads(version['document']))!=child['initial_document_sha256']:raise ValueError()
                initial=json.loads(version['document'])
                if (initial['prepared_narration']['derivation']!=child['derivation'] or initial['canonical_timeline']['sha256']!=child['initial_timeline_sha256']
                    or initial['narrated_variant']['request_fingerprint']!=value['request_fingerprint']
                    or initial['narrated_variant']['profile']!=child['profile'] or child['approval_inherited'] is not False
                    or initial['narrated_variant']['batch_id']!=value['batch_id'] or initial['narrated_variant']['master_project_id']!=value['master_project_id']
                    or initial['narrated_variant']['master_revision']!=snapshot['master_revision']
                    or any(initial['narrated_variant'].get(k) is not False for k in ('approval_inherited','rights_authority_inherited'))
                    or initial['narrated_variant'].get('human_review_required') is not True
                    or initial['narrated_variant'].get('crop_needs_attention') is not True
                    or initial['narrated_variant'].get('subject_tracking_confidence') is not None
                    or child['render_dispatched'] is not False):raise ValueError()
                validate_document(initial)
            value.pop('request_key_sha256')
            return {**value,'schema_version':'native-narrated-variant-batch-v1','snapshot':snapshot,'result':result,'external_provider_calls':0}
        except (ValueError,KeyError,TypeError):raise WorkflowError('NARRATED_VARIANT_EVIDENCE_CHANGED') from None

    def create(self,project_id,payload,*,actor):
        from .narration import identity,SCHEMA as NARRATION_SCHEMA
        from .narration_preview import prepared
        from .branding import Selection,resolve
        from .shot_adapter import validate_document,shots,snapshot_from_shots
        from .auto_edit_timeline import is_auto_edit
        from .media import verify_selected_files
        from types import SimpleNamespace
        from .media_frame_analysis import rebind_records
        request=payload.model_dump(mode='json',exclude={'request_key'});fp=digest(request);key=digest(payload.request_key)
        with self.store.transaction() as con:
            check_workspace(self.store.root,self.workspace)
            prior=con.execute('SELECT * FROM native_narrated_variant_batches WHERE workspace_id=? AND master_project_id=? AND request_key_sha256=?',
                (self.workspace,project_id,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fp:raise WorkflowError('NARRATED_VARIANT_IDEMPOTENCY_CONFLICT')
                return self.read(prior,con),True
            master=self.store.editable(con,project_id,payload.revision);document=master['document']
            if is_auto_edit(document):raise WorkflowError('NARRATED_VARIANT_STORYBOARD_REQUIRED',400)
            canonical=validate_document(document)
            if canonical is None:raise WorkflowError('NARRATED_VARIANT_CANONICAL_TIMELINE_REQUIRED',400)
            if canonical['version']!=payload.expected_version:raise WorkflowError('NARRATED_VARIANT_TIMELINE_STALE')
            reference=document.get('prepared_narration')
            if not reference or digest(reference)!=payload.expected_prepared_reference_sha256:raise WorkflowError('NARRATED_VARIANT_PREPARED_REFERENCE_CHANGED')
            source,source_out,source_result=prepared(self.store,master,con=con)
            brand,template=resolve(document)
            if template is None:raise WorkflowError('NARRATED_VARIANT_FROZEN_TEMPLATE_REQUIRED',400)
            verify_selected_files(SimpleNamespace(data_root=self.store.root),document)
            from .narrated_music import verify_source
            verify_source(SimpleNamespace(data_root=self.store.root),document)
            available=catalog();profiles={v['profile_ref']:v for v in available['profiles']}
            if any(ref not in profiles for ref in payload.profile_refs):raise WorkflowError('NARRATED_VARIANT_PROFILE_UNKNOWN',400)
            if con.execute('SELECT COUNT(*) FROM native_narrated_variant_batches WHERE workspace_id=? AND master_project_id=?',(self.workspace,project_id)).fetchone()[0]>=50:
                raise WorkflowError('NARRATED_VARIANT_BATCH_LIMIT',400)
            batch_id='nnvb_'+uuid.uuid4().hex;stamp=now();children=[]
            for ref in payload.profile_refs:
                profile=profiles[ref];child_id=uuid.uuid5(uuid.NAMESPACE_URL,SCHEMA+'/'+self.workspace+'/'+project_id+'/'+fp+'/'+key+'/'+ref).hex
                child=copy.deepcopy(document)
                if 'media_rights_declarations' in child or 'media_rights_overrides' in child:
                    from .rights import clear_project_claims
                    clear_project_claims(child)
                for field in ['studio_media_plans','narration_rights_exceptions','auto_edit_analyses','auto_edit_transcripts']:
                    prior_value=child.pop(field,None)
                    if prior_value:child[field+'_origin']={'source_project_id':project_id,'source_sha256':digest(prior_value),'authority_transferred':False,'new_review_required':True}
                child['media_frame_analyses']=rebind_records(document,project_id,child_id)
                # Canvas is the only template change; original brand/duration/voice stay frozen.
                base_id=template.id
                for suffix in ('-landscape','-square','-feed'):
                    if base_id.endswith(suffix):base_id=base_id[:-len(suffix)];break
                suffix={'9:16':'','16:9':'-landscape','1:1':'-square','4:5':'-feed'}[profile['aspect_ratio']]
                shape={**template.model_dump(),'id':base_id+suffix,'name':template.name[:105]+' · '+profile['aspect_ratio'],
                    'width':profile['width'],'height':profile['height'],'aspect_ratio':profile['aspect_ratio']}
                selected=Selection(brand=brand,template=shape,brand_sha256=digest(brand.model_dump()),template_sha256=digest(shape)).model_dump()
                child['brand_template']=selected;child['render_profile']={'9:16':'vertical-short','16:9':'landscape','1:1':'square','4:5':'portrait-feed'}[profile['aspect_ratio']]
                timeline=snapshot_from_shots(shots(document),child,canvas=canonical['snapshot'])
                child['canonical_timeline']={'version':1,'snapshot':timeline,'sha256':digest(timeline)}
                from .editor import build_plan,SceneOptions
                prior_plan=document.get('edit_plan');options=[{k:s[k] for k in SceneOptions.model_fields} for s in prior_plan['scenes']] if prior_plan else None
                child['edit_plan']=build_plan(child,options)
                derivation=Derivation(batch_id=batch_id,workspace_id=self.workspace,master_project_id=project_id,child_project_id=child_id,
                    source_project_id=source['project_id'],source_narration_job_id=source['id'],source_snapshot_sha256=digest(source['snapshot']),
                    source_approval_sha256=digest(source['snapshot']['approval']),source_plan_sha256=source_result['plan_sha256'],
                    source_voice_sha256=source_result['plan']['voice_audio_sha256'],voice_input_sha256=identity(child),
                    source_prepared_reference_sha256=digest(reference)).model_dump(mode='json')
                child['prepared_narration']={'schema_version':NARRATION_SCHEMA,'job_id':source['id'],'plan_sha256':source_result['plan_sha256'],
                    'voice_input_sha256':identity(child),'voice_audio_sha256':source_result['plan']['voice_audio_sha256'],
                    'review_required':True,'automatic_render':False,'derivation':derivation}
                child['name']=document['name'][:100]+' · '+profile['label'][:45]
                child['narrated_variant']={'schema_version':SCHEMA,'batch_id':batch_id,'master_project_id':project_id,'master_revision':master['revision'],
                    'profile':profile,'request_fingerprint':fp,'crop_needs_attention':True,'subject_tracking_confidence':None,
                    'approval_inherited':False,'rights_authority_inherited':False,'human_review_required':True}
                validate_document(child)
                if identity(child)!=source_result['plan']['voice_input_sha256']:raise WorkflowError('NARRATED_VARIANT_VOICE_INPUT_CHANGED')
                con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(child_id,1,json.dumps(child,ensure_ascii=False),None,stamp,stamp));self.store.version(con,child_id)
                self.store.event(con,child_id,'narrated_variant_created_unapproved',{'batch_id':batch_id,'master_project_id':project_id,'profile_ref':ref,'provider_calls':0})
                children.append({'project_id':child_id,'name':child['name'],'profile':profile,'initial_document_sha256':digest(child),
                    'initial_timeline_sha256':digest(timeline),'derivation':derivation,'approval_inherited':False,'render_dispatched':False})
            snapshot={'schema_version':'native-narrated-variant-snapshot-v1','workspace_id':self.workspace,'master_project_id':project_id,
                'master_revision':master['revision'],'master_document_sha256':digest(document),'master_timeline_sha256':canonical['sha256'],
                'request':request,'catalog':available,'source_narration_job_id':source['id'],'source_project_id':source['project_id'],
                'source_plan_sha256':source_result['plan_sha256'],'source_prepared_reference_sha256':digest(reference)}
            result={'schema_version':SCHEMA,'variants':children,'master_project_mutated':False,'external_provider_calls':0,'new_inference_calls':0,
                'human_approval_required_per_variant':True,'rights_authority_inherited':False,'publishing_enabled':False}
            con.execute('INSERT INTO native_narrated_variant_batches VALUES(?,?,?,?,?,?,?,?,?,?,?)',(batch_id,self.workspace,project_id,key,fp,digest(snapshot),json.dumps(snapshot),digest(result),json.dumps(result),actor,stamp))
            self.store.event(con,project_id,'narrated_variant_batch_created_unapproved',{'batch_id':batch_id,'variants':len(children),'provider_calls':0})
            return self.read(con.execute('SELECT * FROM native_narrated_variant_batches WHERE batch_id=?',(batch_id,)).fetchone(),con),False

    def page(self,project_id,*,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NARRATED_VARIANT_PAGE_INVALID',400)
        after=None
        if cursor:
            try:
                if not isinstance(cursor,str) or len(cursor)>1000:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(after,list) or len(after)!=3 or after[:2]!=[self.workspace,project_id] or not isinstance(after[2],str) or not re.fullmatch(r'nnvb_[a-f0-9]{32}',after[2]):raise ValueError()
            except (ValueError,TypeError):raise WorkflowError('NARRATED_VARIANT_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            check_workspace(self.store.root,self.workspace)
            master=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone())
            where='workspace_id=? AND master_project_id=?';params=[self.workspace,project_id]
            if after:where+=' AND batch_id>?';params.append(after[2])
            rows=con.execute('SELECT * FROM native_narrated_variant_batches WHERE '+where+' ORDER BY batch_id LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project_id,rows[limit-1]['batch_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-narrated-variant-page-v1','workspace_id':self.workspace,'master_project_id':project_id,
                'current_master':{'revision':master['revision'],'timeline_version':master['document'].get('canonical_timeline',{}).get('version'),
                    'prepared_reference_sha256':digest(master['document']['prepared_narration']) if master['document'].get('prepared_narration') else None},
                'items':[self.read(row,con) for row in rows[:limit]],'next_cursor':next_cursor,'limit':limit,'external_provider_calls':0}

def resolve_reference(store,con,project_id,document):
    """Resolve a child reference only through immutable family and source proofs."""
    from .narration import SCHEMA as NARRATION_SCHEMA,identity,load
    try:
        reference=document['prepared_narration'];derivation=Derivation.model_validate(reference['derivation'])
        if reference['derivation']!=derivation.model_dump(mode='json'):raise ValueError()
        if any(reference['derivation'].get(k) is not False for k in ('approval_inherited','rights_authority_inherited')):raise ValueError()
        if (reference.get('schema_version')!=NARRATION_SCHEMA or derivation.child_project_id!=project_id
            or reference.get('review_required') is not True or reference.get('automatic_render') is not False
            or derivation.voice_input_sha256!=identity(document)
            or reference.get('job_id')!=derivation.source_narration_job_id
            or reference.get('plan_sha256')!=derivation.source_plan_sha256
            or reference.get('voice_input_sha256')!=derivation.voice_input_sha256
            or reference.get('voice_audio_sha256')!=derivation.source_voice_sha256):raise ValueError()
        service=NativeNarratedVariants(store,workspace_id=derivation.workspace_id,initialize=False)
        row=con.execute('SELECT * FROM native_narrated_variant_batches WHERE batch_id=? AND workspace_id=? AND master_project_id=?',
            (derivation.batch_id,derivation.workspace_id,derivation.master_project_id)).fetchone()
        if row is None:raise ValueError()
        batch=service.read(row,con);children=[c for c in batch['result']['variants'] if c['project_id']==project_id]
        if len(children)!=1 or children[0]['derivation']!=derivation.model_dump(mode='json'):raise ValueError()
        lineage=document.get('narrated_variant',{})
        if (lineage.get('batch_id')!=derivation.batch_id or lineage.get('master_project_id')!=derivation.master_project_id
            or lineage.get('schema_version')!=SCHEMA or lineage.get('rights_authority_inherited') is not False
            or lineage.get('approval_inherited') is not False or lineage.get('human_review_required') is not True
            or lineage.get('profile')!=children[0]['profile'] or lineage.get('request_fingerprint')!=batch['request_fingerprint']
            or lineage.get('master_revision')!=batch['snapshot']['master_revision']):raise ValueError()
        job,out,result=load(store,con,derivation.source_project_id,derivation.source_narration_job_id)
        approval=job['snapshot'].get('approval')
        if (digest(job['snapshot'])!=derivation.source_snapshot_sha256 or digest(approval)!=derivation.source_approval_sha256
            or not approval or approval.get('revision')!=job['revision'] or approval.get('snapshot_sha256')!=digest(job['snapshot']['document'])
            or result['plan_sha256']!=derivation.source_plan_sha256 or result['plan']['voice_audio_sha256']!=derivation.source_voice_sha256
            or result['plan']['voice_input_sha256']!=derivation.voice_input_sha256):raise ValueError()
        return job,out,result
    except (ValueError,KeyError,TypeError,sqlite3.OperationalError):raise WorkflowError('NARRATED_VARIANT_NARRATION_REFERENCE_INVALID') from None
