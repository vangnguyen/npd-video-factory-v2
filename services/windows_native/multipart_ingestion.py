"""Bounded, durable local intake. Uploaded bytes never authorize publishing."""
import copy,json,os,re,shutil,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest,file_sha
from .media import ingest_media,discard_media,display_filename,project_assets,_verify_library_record
from .music import ingest_music
from .store import now

CHUNK_BYTES=1024*1024
MIMES={'video':{'video/mp4','video/quicktime'},'image':{'image/jpeg','image/png'},'logo':{'image/png'},
       'audio':{'audio/wav','audio/x-wav','audio/mpeg'},'music':{'audio/wav','audio/x-wav','audio/mpeg'},
       'subtitle':{'application/x-subrip','text/vtt'}}
LIMITS={'video':250*CHUNK_BYTES,'image':15*CHUNK_BYTES,'logo':15*CHUNK_BYTES,
        'audio':25*CHUNK_BYTES,'music':25*CHUNK_BYTES,'subtitle':CHUNK_BYTES}
STATES={'receiving','validating','needs_attention','completed','cancelled'}
TABLES=('native_upload_sessions','native_upload_parts')

class Create(StrictModel):
    schema_version:Literal['native-multipart-upload-request-v1']='native-multipart-upload-request-v1'
    revision:StrictInt=Field(ge=1)
    kind:Literal['video','audio','image','logo','music','subtitle']
    content_type:str=Field(min_length=1,max_length=100)
    filename:str=Field(min_length=1,max_length=200)
    total_bytes:StrictInt=Field(ge=1,le=250*CHUNK_BYTES)
    expected_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    rights_confirmed:Literal[True]
    illustration:StrictBool=False
    request_key:str=Field(min_length=16,max_length=160)
    @field_validator('rights_confirmed',mode='before')
    @classmethod
    def confirmed(cls,v):
        if v is not True:raise ValueError('Explicit rights acknowledgement required')
        return v
    @model_validator(mode='after')
    def bounded(self):
        if self.content_type not in MIMES[self.kind] or self.total_bytes>LIMITS[self.kind]:raise ValueError('Supported MIME and size required')
        if display_filename(self.filename)!=self.filename or self.filename in {'.','..'}:raise ValueError('A display filename without a path is required')
        return self

class Complete(StrictModel):
    revision:StrictInt=Field(ge=1)
    expected_parts_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

def subtitle_cues(raw,mime):
    try:text=raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
    except UnicodeError:raise WorkflowError('UPLOAD_SUBTITLE_UTF8_REQUIRED',400) from None
    if '\x00' in text:raise WorkflowError('UPLOAD_SUBTITLE_INVALID',400)
    if mime=='text/vtt':
        if not text.startswith('WEBVTT\n'):raise WorkflowError('UPLOAD_SUBTITLE_MAGIC_MISMATCH',400)
        text=text.split('\n',1)[1].lstrip('\n')
    elif text.startswith('WEBVTT'):raise WorkflowError('UPLOAD_SUBTITLE_MAGIC_MISMATCH',400)
    cues=[];previous=0
    def stamp(v):
        match=re.fullmatch(r'(?:(\d{1,2}):)?([0-5]\d):([0-5]\d)[.,](\d{3})',v)
        if not match:raise WorkflowError('UPLOAD_SUBTITLE_TIMESTAMP_INVALID',400)
        h,m,s,ms=match.groups();return (int(h or 0)*3600+int(m)*60+int(s)+int(ms)/1000)
    for block in re.split(r'\n\s*\n',text.strip()):
        lines=block.splitlines()
        if len(lines)>1 and '-->' not in lines[0]:lines=lines[1:]
        if len(lines)<2 or lines[0].count('-->')!=1:raise WorkflowError('UPLOAD_SUBTITLE_INVALID',400)
        start,end=[stamp(v.strip()) for v in lines[0].split('-->')];caption='\n'.join(lines[1:])
        if not previous<=start<end<=600 or not 1<=len(caption)<=1000 or '<' in caption or '>' in caption or len(cues)>=5000:
            raise WorkflowError('UPLOAD_SUBTITLE_BOUNDS_OR_TEXT_INVALID',400)
        cues.append({'start':start,'end':end,'text':caption});previous=end
    if not cues:raise WorkflowError('UPLOAD_SUBTITLE_EMPTY',400)
    return cues

def magic(source,kind,mime):
    with source.open('rb') as h:head=h.read(64)
    okay=(mime=='image/png' and head.startswith(b'\x89PNG\r\n\x1a\n') or mime=='image/jpeg' and head.startswith(b'\xff\xd8\xff')
        or mime in {'audio/wav','audio/x-wav'} and head[:4]==b'RIFF' and head[8:12]==b'WAVE'
        or mime=='audio/mpeg' and (head.startswith(b'ID3') or len(head)>1 and head[0]==255 and head[1]&224==224)
        or mime=='video/mp4' and head[4:8]==b'ftyp' and head[8:12]!=b'qt  '
        or mime=='video/quicktime' and (head[4:8] in {b'moov',b'mdat',b'wide'} or head[4:8]==b'ftyp' and head[8:12]==b'qt  '))
    if kind!='subtitle' and not okay:raise WorkflowError('UPLOAD_MIME_MAGIC_MISMATCH',400)

def intake(config,source,request):
    magic(source,request.kind,request.content_type)
    if request.kind in {'video','image','logo'}:
        asset=ingest_media(config,source,request.content_type,request.filename,rights_confirmed=True,
                           illustration=request.illustration,preserve_alpha=request.kind=='logo')
    elif request.kind in {'audio','music'}:
        asset=ingest_music(config,source,request.content_type,request.filename,rights_confirmed=True)
        asset.update(kind='audio',has_audio=True,content_type='audio/wav',source_bytes=source.stat().st_size)
    else:
        cues=subtitle_cues(source.read_bytes(),request.content_type);extension='.vtt' if request.content_type=='text/vtt' else '.srt'
        identifier=uuid.uuid4().hex;asset={'id':identifier+'.subtitle'+extension,'original_id':identifier+extension,
            'kind':'subtitle','filename':request.filename,'content_type':request.content_type,'cues':cues,'duration_seconds':cues[-1]['end'],
            'sha256':file_sha(source),'source_sha256':file_sha(source),'bytes':source.stat().st_size,'source_bytes':source.stat().st_size,
            'source_mime':request.content_type,'rights_confirmed':True,'source_type':'user_upload','rights_status':'unknown','license':None,
            'provider':'native-local-upload','source_reference':'upload://'+identifier,'generation_provenance':{},'source':'immutable_user_upload','version':1}
        for folder,key in [('assets','id'),('originals','original_id')]:
            directory=config.data_root/folder;directory.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,directory/asset[key])
    asset.setdefault('illustration',request.illustration)
    asset.update(canonical_role=request.kind,source_mime=request.content_type,source_sha256=file_sha(source),source_bytes=source.stat().st_size)
    return asset

class NativeMultipartIngestion:
    def __init__(self,store,config,*,workspace_id):
        self.store,self.config,self.workspace=store,config,workspace_id;self.root=store.root.absolute();self.frozen_workspace=workspace_id
        self.check()
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_upload_sessions (
                upload_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,request_json TEXT NOT NULL,status TEXT NOT NULL,received_bytes INTEGER NOT NULL,
                actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deadline TEXT NOT NULL,
                claim_id TEXT,result_json TEXT,result_sha256 TEXT,failure_code TEXT,UNIQUE(workspace_id,project_id,key_sha256));
                CREATE TABLE IF NOT EXISTS native_upload_parts (upload_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                offset INTEGER NOT NULL,bytes INTEGER NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(upload_id,ordinal));''')
            con.execute("UPDATE native_upload_sessions SET status='needs_attention',failure_code='UPLOAD_RESTART_REVIEW_REQUIRED',claim_id=NULL WHERE status='validating' AND workspace_id=?",(self.workspace,))
    def check(self):
        if self.workspace!=self.frozen_workspace or self.config.data_root.absolute()!=self.root or self.store.root.absolute()!=self.root or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',self.workspace or ''):
            raise WorkflowError('UPLOAD_STORAGE_SCOPE_INVALID')
    def directory(self,identity):
        self.check()
        if not re.fullmatch(r'nup_[a-f0-9]{32}',identity):raise WorkflowError('UPLOAD_ID_INVALID',400)
        parent=self.root/'multipart_uploads';path=parent/identity
        if parent.is_symlink() or path.is_symlink() or parent.resolve()!=parent.absolute() or path.resolve().parent!=parent.resolve():
            raise WorkflowError('UPLOAD_STORAGE_PATH_INVALID')
        return path
    def file(self,identity,name):
        directory=self.directory(identity);path=directory/name
        if path.is_symlink() or path.resolve().parent!=directory.resolve():raise WorkflowError('UPLOAD_STORAGE_PATH_INVALID')
        from .backup import guard
        guard(path,exists=path.exists())
        return path
    def row(self,con,project,identity):
        self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        row=con.execute('SELECT * FROM native_upload_sessions WHERE upload_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('UPLOAD_NOT_FOUND',404)
        return row
    def read(self,con,row,*,verify=True):
        v=dict(row);request=Create.model_validate({**json.loads(v['request_json']),'request_key':'internal-upload-history-key'})
        if digest(json.loads(v['request_json']))!=v['request_sha256'] or v['status'] not in STATES:raise WorkflowError('UPLOAD_HISTORY_CHANGED')
        parts=[dict(p) for p in con.execute('SELECT ordinal,offset,bytes,sha256 FROM native_upload_parts WHERE upload_id=? ORDER BY ordinal',(v['upload_id'],))]
        offset=0
        for ordinal,p in enumerate(parts):
            if p['ordinal']!=ordinal or p['offset']!=offset or p['bytes']!=min(CHUNK_BYTES,request.total_bytes-offset) or not re.fullmatch(r'[a-f0-9]{64}',p['sha256']):raise WorkflowError('UPLOAD_PART_HISTORY_CHANGED')
            if verify and v['status'] in {'receiving','needs_attention','validating'}:
                path=self.file(v['upload_id'],f'part-{ordinal:04d}.bin')
                if not path.is_file() or path.stat().st_size!=p['bytes'] or file_sha(path)!=p['sha256']:raise WorkflowError('UPLOAD_PART_CHANGED_OR_MISSING')
            offset+=p['bytes']
        if offset!=v['received_bytes'] or offset>request.total_bytes:raise WorkflowError('UPLOAD_PART_HISTORY_CHANGED')
        result=json.loads(v['result_json']) if v['result_json'] else None
        if v['status']=='completed':
            if not isinstance(result,dict) or digest(result)!=v['result_sha256'] or set(result)!={'asset','source_sha256','source_bytes','duplicate','attached_revision','rights_status','publishing_enabled'}:
                raise WorkflowError('UPLOAD_COMPLETION_CHANGED')
            asset=result['asset'];revision=result['attached_revision']
            history=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(v['project_id'],revision)).fetchone()
            if (type(result['duplicate']) is not bool or type(revision) is not int or result['publishing_enabled'] is not False or history is None
                or asset not in project_assets(json.loads(history['document'])) or asset.get('canonical_role')!=request.kind
                or result['source_bytes']!=request.total_bytes or result['source_sha256']!=asset.get('source_sha256') or asset.get('source_mime')!=request.content_type
                or request.expected_sha256 is not None and result['source_sha256']!=request.expected_sha256 or result['rights_status']!=asset.get('rights_status')):
                raise WorkflowError('UPLOAD_COMPLETION_CHANGED')
            _verify_library_record(self.store,{'metadata':asset,'metadata_conflict':False})
        elif result is not None or v['result_sha256'] is not None:raise WorkflowError('UPLOAD_COMPLETION_CHANGED')
        return {'schema_version':'native-multipart-upload-v1','upload_id':v['upload_id'],'workspace_id':self.workspace,'project_id':v['project_id'],
            'request':request.model_dump(mode='json',exclude={'request_key'}),'request_sha256':v['request_sha256'],'status':v['status'],
            'received_bytes':offset,'chunk_bytes':CHUNK_BYTES,'parts':parts,'parts_sha256':digest(parts),'deadline':v['deadline'],
            'created_at':v['created_at'],'updated_at':v['updated_at'],'failure_code':v['failure_code'],'result':result,'publishing_enabled':False}
    def get(self,project,identity):
        with self.store.transaction() as con:return self.read(con,self.row(con,project,identity))
    def page(self,project):
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            rows=con.execute('SELECT * FROM native_upload_sessions WHERE workspace_id=? AND project_id=? ORDER BY created_at DESC,upload_id DESC LIMIT 51',(self.workspace,project)).fetchall()
            return {'schema_version':'native-multipart-upload-page-v1','workspace_id':self.workspace,'project_id':project,'items':[self.read(con,r) for r in rows[:50]],'truncated':len(rows)>50,'publishing_enabled':False}
    def create(self,project,payload,*,actor):
        if type(actor) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',actor):raise WorkflowError('UPLOAD_ACTOR_INVALID')
        request=Create.model_validate(payload);body=request.model_dump(mode='json',exclude={'request_key'});fp=digest(body);key=digest(request.request_key)
        with self.store.transaction() as con:
            self.store.editable(con,project,request.revision)
            prior=con.execute('SELECT * FROM native_upload_sessions WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_sha256']!=fp:raise WorkflowError('UPLOAD_IDEMPOTENCY_CONFLICT')
                return self.read(con,prior),True
            outstanding=con.execute("SELECT request_json FROM native_upload_sessions WHERE workspace_id=? AND status IN ('receiving','validating','needs_attention')",(self.workspace,)).fetchall()
            if len(outstanding)>=20 or sum(json.loads(r[0])['total_bytes'] for r in outstanding)+request.total_bytes>1024*CHUNK_BYTES:
                raise WorkflowError('UPLOAD_LOCAL_STORAGE_QUOTA',409)
            identity,stamp='nup_'+uuid.uuid4().hex,now();self.directory(identity).mkdir(parents=True,exist_ok=False)
            deadline=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
            con.execute('INSERT INTO native_upload_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,key,fp,json.dumps(body),'receiving',0,actor,stamp,stamp,deadline,None,None,None,None))
            return self.read(con,self.row(con,project,identity)),False
    def chunk(self,project,identity,offset,sha,raw):
        if type(offset) is not int or offset<0 or type(sha) is not str or not re.fullmatch(r'[a-f0-9]{64}',sha) or type(raw) is not bytes or not 0<len(raw)<=CHUNK_BYTES:
            raise WorkflowError('UPLOAD_CHUNK_FIELDS_INVALID',400)
        import hashlib
        if hashlib.sha256(raw).hexdigest()!=sha:raise WorkflowError('UPLOAD_CHUNK_CHECKSUM_MISMATCH',400)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);v=self.read(con,row,verify=False);request=v['request'];ordinal=offset//CHUNK_BYTES
            if v['status']!='receiving' or datetime.fromisoformat(v['deadline'])<=datetime.now(timezone.utc):raise WorkflowError('UPLOAD_NOT_RECEIVING')
            if offset%CHUNK_BYTES or len(raw)!=min(CHUNK_BYTES,request['total_bytes']-offset):raise WorkflowError('UPLOAD_CHUNK_RANGE_INVALID',400)
            prior=next((p for p in v['parts'] if p['offset']==offset),None)
            if prior:
                if prior['sha256']!=sha:raise WorkflowError('UPLOAD_CHUNK_CONFLICT')
                path=self.file(identity,f'part-{ordinal:04d}.bin')
                if not path.is_file() or path.stat().st_size!=len(raw) or file_sha(path)!=sha:raise WorkflowError('UPLOAD_PART_CHANGED_OR_MISSING')
                return v,True
            if offset!=v['received_bytes']:raise WorkflowError('UPLOAD_CHUNK_OFFSET_REQUIRED',409)
            path=self.file(identity,f'part-{ordinal:04d}.bin')
            if path.exists():
                if not path.is_file() or path.stat().st_size!=len(raw) or file_sha(path)!=sha:raise WorkflowError('UPLOAD_UNJOURNALED_PART_CONFLICT')
            else:
                with path.open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
            con.execute('INSERT INTO native_upload_parts VALUES(?,?,?,?,?)',(identity,ordinal,offset,len(raw),sha))
            con.execute('UPDATE native_upload_sessions SET received_bytes=?,updated_at=? WHERE upload_id=?',(offset+len(raw),now(),identity))
            return self.read(con,self.row(con,project,identity),verify=False),False
    def complete(self,project,identity,payload):
        request=Complete.model_validate(payload);claim=uuid.uuid4().hex
        with self.store.transaction() as con:
            row=self.row(con,project,identity);v=self.read(con,row)
            if request.expected_parts_sha256!=v['parts_sha256']:raise WorkflowError('UPLOAD_PARTS_CHANGED')
            if v['status']=='completed':return v,True
            if v['status'] not in {'receiving','needs_attention'} or v['received_bytes']!=v['request']['total_bytes']:raise WorkflowError('UPLOAD_INCOMPLETE_OR_BUSY')
            self.store.editable(con,project,request.revision)
            con.execute("UPDATE native_upload_sessions SET status='validating',claim_id=?,failure_code=NULL WHERE upload_id=?",(claim,identity))
        source=self.file(identity,'assembled-'+claim+'.bin');asset=None;committed=False
        try:
            with source.open('xb') as target:
                for part in v['parts']:
                    with self.file(identity,f"part-{part['ordinal']:04d}.bin").open('rb') as h:shutil.copyfileobj(h,target,CHUNK_BYTES)
                target.flush();os.fsync(target.fileno())
            checksum=file_sha(source);create=Create.model_validate({**v['request'],'request_key':'internal-upload-completion-key'})
            if create.expected_sha256 is not None and checksum!=create.expected_sha256:raise WorkflowError('UPLOAD_SOURCE_CHECKSUM_MISMATCH',400)
            magic(source,create.kind,create.content_type)
            with self.store.transaction() as con:
                current=self.store.editable(con,project,request.revision)
                duplicate=next((a for a in project_assets(current['document']) if a.get('source_type')=='user_upload' and a.get('source_sha256')==checksum
                    and a.get('source_bytes')==create.total_bytes and a.get('source_mime')==create.content_type and a.get('canonical_role')==create.kind and a.get('illustration',False)==create.illustration),None)
                if duplicate:_verify_library_record(self.store,{'metadata':duplicate,'metadata_conflict':False})
            if duplicate:asset=copy.deepcopy(duplicate)
            else:asset=intake(self.config,source,create)
            with self.store.transaction() as con:
                row=self.row(con,project,identity)
                if row['status']!='validating' or row['claim_id']!=claim:raise WorkflowError('UPLOAD_CLAIM_CHANGED')
                current=self.store.editable(con,project,request.revision)
                if not duplicate:self.store.append_media_in_transaction(con,project,request.revision,asset)
                result={'asset':asset,'source_sha256':checksum,'source_bytes':create.total_bytes,'duplicate':bool(duplicate),'attached_revision':request.revision+(0 if duplicate else 1),'rights_status':asset['rights_status'],'publishing_enabled':False}
                con.execute("UPDATE native_upload_sessions SET status='completed',claim_id=NULL,result_json=?,result_sha256=?,updated_at=? WHERE upload_id=?",(json.dumps(result,ensure_ascii=False),digest(result),now(),identity))
                completed=self.read(con,self.row(con,project,identity))
            committed=True
            return completed,False
        except Exception as error:
            if asset is not None and not duplicate:discard_media(self.config,asset)
            with self.store.transaction() as con:
                con.execute("UPDATE native_upload_sessions SET status='needs_attention',claim_id=NULL,failure_code=?,updated_at=? WHERE upload_id=? AND claim_id=?",(error.code if isinstance(error,WorkflowError) else 'UPLOAD_VALIDATION_FAILED',now(),identity,claim))
            raise
        finally:
            source.unlink(missing_ok=True)
            if committed:self.discard_parts(identity,v['parts'])
    def discard_parts(self,identity,parts):
        for part in parts:
            try:
                path=self.file(identity,f"part-{part['ordinal']:04d}.bin")
                if path.is_file() and path.stat().st_size==part['bytes'] and file_sha(path)==part['sha256']:path.unlink()
            except (WorkflowError,OSError):
                # Uncertain files remain available for manual inspection; a committed receipt stays valid.
                continue
    def cancel(self,project,identity):
        with self.store.transaction() as con:
            row=self.row(con,project,identity)
            if row['status'] in {'validating','completed'}:raise WorkflowError('UPLOAD_CANCEL_NOT_AVAILABLE')
            prior=self.read(con,row)
            if row['status']=='cancelled':return prior
            con.execute("UPDATE native_upload_sessions SET status='cancelled',updated_at=? WHERE upload_id=?",(now(),identity))
            result=self.read(con,self.row(con,project,identity))
        self.discard_parts(identity,prior['parts']);return result
