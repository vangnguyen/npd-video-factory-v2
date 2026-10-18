"""Bounded, explicit local auditions. GET never dispatches inference or retries."""
import json,re,threading,uuid
from pathlib import Path
from .backup import guard
from .contracts import WorkflowError,digest,file_sha,normalize
from .hardening import durable_json
from .store import now

SAMPLE_TEXT='Xin chào, mình rất vui được gặp bạn. Hẹn gặp lại trong câu chuyện tiếp theo.'
SAMPLE_ID=r'nsample_[a-f0-9]{32}'

class NativeVoiceAuditions:
    def __init__(self,library,config,adapter_factory=None):
        self.library,self.store,self.config=library,library.store,config
        if adapter_factory is None:
            from .dialogue_vieneu import VieNeuDialoguePresetAdapter
            adapter_factory=lambda:VieNeuDialoguePresetAdapter(config)
        self.adapter_factory=adapter_factory;self.lock=threading.Lock();self.worker=None
        with self.store.transaction() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS native_voice_auditions (
                workspace_id TEXT NOT NULL,sample_id TEXT NOT NULL,input_sha256 TEXT NOT NULL,request_json TEXT NOT NULL,
                state TEXT NOT NULL,attempt INTEGER NOT NULL,relative_directory TEXT,error_code TEXT,manifest_sha256 TEXT,created_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id,sample_id),UNIQUE(workspace_id,input_sha256))''')
            # Process startup does not replay potentially completed inference.
            con.execute("UPDATE native_voice_auditions SET state='outcome_unknown',error_code='INTERRUPTED_SAMPLE_RETRY_REQUIRED' WHERE workspace_id=? AND state IN ('queued','running')",(library.workspace,))
    def public(self,row):
        request=json.loads(row['request_json'])
        return {'sample_id':row['sample_id'],'voice_id':request['voice_id'],'voice_version':request['voice_version'],'kind':request['kind'],
            'state':row['state'],'error_code':row['error_code'],'attempt':row['attempt'],'text':request['text'],
            'audio_url':'/api/voice-auditions/'+row['sample_id']+'/audio' if row['state']=='ready' else None,
            'installed':True,'rights_basis':'pinned_source_license','evidence_mode':'local-real','human_listening_accepted':False}
    def page(self):
        self.library.scope()
        with self.store.transaction() as con:rows=con.execute('SELECT * FROM native_voice_auditions WHERE workspace_id=? ORDER BY created_at DESC LIMIT 200',(self.library.workspace,)).fetchall()
        return {'items':[self.public(row) for row in rows],'inference_dispatched':False,'human_voice_uat_complete':False}
    def submit(self,body,*,authorization_check=lambda:None):
        self.library.scope();authorization_check()
        if (not isinstance(body,dict) or set(body)-{'voice_id','voice_version','kind','text','retry'} or not {'voice_id','voice_version','kind'}<=set(body)
            or body['kind'] not in ('sample','dialogue') or type(body.get('retry',False)) is not bool):raise WorkflowError('VOICE_SAMPLE_REQUEST_INVALID',400)
        if body['kind']=='dialogue' and not isinstance(body.get('text'),str):raise WorkflowError('VOICE_SAMPLE_TEXT_REQUIRED',400)
        text=SAMPLE_TEXT if body['kind']=='sample' else normalize(body.get('text',''))
        if not isinstance(text,str) or not 1<=len(text)<=300:raise WorkflowError('VOICE_SAMPLE_TEXT_REQUIRED',400)
        voice=self.library.get(body['voice_id'],version=body['voice_version'],for_generation=True)
        if voice['definition']['rights_status']!='source_licensed':raise WorkflowError('VOICE_SAMPLE_LICENSED_PRESET_REQUIRED',400)
        adapter=self.adapter_factory();adapter.validate(voice['definition'],{'speed':1.0,'style':'neutral'})
        request={'voice_id':voice['voice_id'],'voice_version':voice['version'],'voice_sha256':voice['definition_sha256'],
            'adapter_sha256':adapter.configuration_sha256,'text':text,'kind':body['kind']}
        fingerprint=digest(request)
        with self.lock,self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_voice_auditions WHERE workspace_id=? AND input_sha256=?',(self.library.workspace,fingerprint)).fetchone()
            if row and row['state']=='ready':
                try:self._audio_path(row);return self.public(row)
                except (OSError,ValueError,WorkflowError):
                    if not body.get('retry'):raise WorkflowError('VOICE_SAMPLE_BYTES_CHANGED') from None
            elif row and (row['state'] in ('queued','running') or not body.get('retry')):return self.public(row)
            if row and row['attempt']>=3:raise WorkflowError('VOICE_SAMPLE_RETRY_LIMIT',409)
            if con.execute("SELECT count(*) FROM native_voice_auditions WHERE workspace_id=? AND state IN ('queued','running')",(self.library.workspace,)).fetchone()[0]>=10:raise WorkflowError('VOICE_SAMPLE_QUEUE_FULL',409)
            if con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]:raise WorkflowError('VOICE_SAMPLE_WAIT_FOR_PROJECT_JOB',409)
            authorization_check()
            if row:
                con.execute("UPDATE native_voice_auditions SET state='queued',attempt=attempt+1,error_code=NULL,relative_directory=NULL,manifest_sha256=NULL WHERE workspace_id=? AND sample_id=?",(self.library.workspace,row['sample_id']))
                identifier=row['sample_id']
            else:
                identifier='nsample_'+uuid.uuid4().hex
                con.execute('INSERT INTO native_voice_auditions VALUES(?,?,?,?,?,?,?,?,?,?)',(self.library.workspace,identifier,fingerprint,json.dumps(request,ensure_ascii=False),'queued',1,None,None,None,now()))
        self.start()
        with self.store.transaction() as con:row=con.execute('SELECT * FROM native_voice_auditions WHERE workspace_id=? AND sample_id=?',(self.library.workspace,identifier)).fetchone()
        return self.public(row)
    def start(self):
        with self.lock:
            if self.worker and self.worker.is_alive():return
            self.worker=threading.Thread(target=self.run,name='native-local-voice-auditions',daemon=True);self.worker.start()
    def run(self):
        while True:
            with self.lock,self.store.transaction() as con:
                row=con.execute("SELECT * FROM native_voice_auditions WHERE workspace_id=? AND state='queued' ORDER BY created_at,sample_id LIMIT 1",(self.library.workspace,)).fetchone()
                if row is None:self.worker=None;return
                con.execute("UPDATE native_voice_auditions SET state='running' WHERE workspace_id=? AND sample_id=?",(self.library.workspace,row['sample_id']))
            try:
                self.generate(row)
            except Exception as error:
                code=error.code if isinstance(error,WorkflowError) else 'VOICE_SAMPLE_FAILED'
                with self.store.transaction() as con:con.execute("UPDATE native_voice_auditions SET state='failed',error_code=? WHERE workspace_id=? AND sample_id=?",(code,self.library.workspace,row['sample_id']))
    def generate(self,row):
        request=json.loads(row['request_json']);voice=self.library.get(request['voice_id'],version=request['voice_version'],for_generation=True)
        if voice['definition_sha256']!=request['voice_sha256']:raise WorkflowError('VOICE_VERSION_CHANGED')
        adapter=self.adapter_factory()
        if adapter.configuration_sha256!=request['adapter_sha256'] or adapter.paid or adapter.evidence_mode!='local-real':raise WorkflowError('VOICE_SAMPLE_RUNTIME_CHANGED')
        with self.store.transaction() as con:
            if con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]:raise WorkflowError('VOICE_SAMPLE_WAIT_FOR_PROJECT_JOB')
        directory=guard(self.store.root/'voice-auditions'/digest(self.library.workspace)/uuid.uuid4().hex);directory.mkdir(parents=True)
        receipt=adapter.synthesize(text=request['text'],voice=voice['definition'],line={'speed':1.0,'style':'neutral'},take=None,request_key=row['input_sha256'],target=directory/'line.wav')
        from .dialogue_audio import measure,ProviderReceipt
        pcm=measure(directory/'line.wav');receipt=ProviderReceipt.model_validate(receipt).model_dump(mode='json')
        if self.library.get(request['voice_id'],version=request['voice_version'],for_generation=True)['definition_sha256']!=request['voice_sha256']:raise WorkflowError('VOICE_VERSION_CHANGED')
        manifest={'schema_version':'native-voice-audition.v1','input_sha256':row['input_sha256'],'voice':request,'pcm':pcm,'provider_receipt':receipt,
            'evidence_mode':'local-real','owner_listening_accepted':False,'created_at':now()}
        durable_json(directory/'manifest.json',manifest)
        with self.store.transaction() as con:con.execute("UPDATE native_voice_auditions SET state='ready',relative_directory=?,manifest_sha256=?,error_code=NULL WHERE workspace_id=? AND sample_id=?",
            (directory.relative_to(self.store.root).as_posix(),file_sha(directory/'manifest.json'),self.library.workspace,row['sample_id']))
    def audio(self,identifier):
        self.library.scope()
        if not re.fullmatch(SAMPLE_ID,identifier):raise WorkflowError('VOICE_SAMPLE_NOT_FOUND',404)
        with self.store.transaction() as con:row=con.execute('SELECT * FROM native_voice_auditions WHERE workspace_id=? AND sample_id=?',(self.library.workspace,identifier)).fetchone()
        if row is None or row['state']!='ready':raise WorkflowError('VOICE_SAMPLE_NOT_READY',409)
        return self._audio_path(row)
    def _audio_path(self,row):
        directory=guard(self.store.root/row['relative_directory'],exists=True)
        if directory.parent!=guard(self.store.root/'voice-auditions'/digest(self.library.workspace),exists=True):raise WorkflowError('VOICE_SAMPLE_SCOPE_CHANGED')
        manifest=guard(directory/'manifest.json',exists=True)
        if file_sha(manifest)!=row['manifest_sha256']:raise WorkflowError('VOICE_SAMPLE_BYTES_CHANGED')
        saved=json.loads(manifest.read_bytes());target=guard(directory/'line.wav',exists=True)
        if saved.get('input_sha256')!=row['input_sha256'] or file_sha(target)!=saved['pcm']['sha256']:raise WorkflowError('VOICE_SAMPLE_BYTES_CHANGED')
        return target
