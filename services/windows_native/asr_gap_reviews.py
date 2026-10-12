"""Versioned human word corrections over immutable completed ASR candidates."""
import copy,hashlib,json,math,re,unicodedata,uuid
from pydantic import Field,StrictInt,StrictBool,ValidationError,field_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest,file_sha
from .hardening import Artifacts
from .media import project_assets,media_path
from .store import now


class WordEdit(StrictModel):
    ordinal:StrictInt=Field(ge=0)
    text:str=Field(min_length=1,max_length=500)
    start_seconds:float=Field(ge=0,le=600)
    end_seconds:float=Field(gt=0,le=600)
    removed:StrictBool=False
    @field_validator('start_seconds','end_seconds',mode='before')
    @classmethod
    def finite(cls,v):
        if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('finite numeric time required')
        return v
    @field_validator('text')
    @classmethod
    def text_nonempty(cls,v):
        if not v.strip():raise ValueError('nonempty word required')
        return unicodedata.normalize('NFC',v)


class ReviewEdit(StrictModel):
    revision:StrictInt=Field(ge=1)
    candidate_sha256:str=Field(pattern='^[a-f0-9]{64}$')
    expected_version:StrictInt=Field(ge=0,le=49)
    request_key:str=Field(pattern=r'^[A-Za-z0-9_.:-]{8,128}$')
    note:str=Field(default='',max_length=1000)
    acknowledged:StrictBool
    words:list[WordEdit]=Field(min_length=1,max_length=2000)


def make_candidate(job,asset,audio,media,value,provider_calls):
    body={'schema_version':'native-asr-gap-candidate-v1','job_id':job['id'],'project_id':job['project_id'],
          'snapshot_sha256':digest(job['snapshot']),'asset_id':asset['id'],'source_sha256':asset['sha256'],
          'audio_metadata_sha256':digest(audio),'media_metadata_sha256':digest(media),
          'provider_pcm_transcript':copy.deepcopy(value),'provider_calls':provider_calls}
    return {**body,'sha256':digest(body)}


def validate_candidate(candidate,*,job=None,asset=None,audio=None,media=None):
    if candidate.get('schema_version')!='native-asr-gap-candidate-v1' or candidate.get('sha256')!=digest({k:v for k,v in candidate.items() if k!='sha256'}):
        raise WorkflowError('ASR_GAP_CANDIDATE_CHANGED')
    if job is not None and (candidate['job_id']!=job['id'] or candidate['project_id']!=job['project_id'] or candidate['snapshot_sha256']!=digest(job['snapshot'])):
        raise WorkflowError('ASR_GAP_CANDIDATE_SCOPE_CHANGED')
    if asset is not None and (candidate['asset_id']!=asset['id'] or candidate['source_sha256']!=asset['sha256']):raise WorkflowError('ASR_GAP_SOURCE_CHANGED')
    if audio is not None and candidate['audio_metadata_sha256']!=digest(audio):raise WorkflowError('ASR_GAP_AUDIO_CHANGED')
    if media is not None and candidate['media_metadata_sha256']!=digest(media):raise WorkflowError('ASR_GAP_MEDIA_CHANGED')
    return candidate


def source_words(candidate,audio):
    from .asr_audio_clock import validate_padding
    plan=validate_padding(audio);offset=plan['source_origin_sample']/16000;gaps=[(g['pcm_start_sample']/16000+offset,g['pcm_end_sample']/16000+offset) for g in plan['gaps']]
    rows=[]
    for segment in candidate['provider_pcm_transcript']['segments']:
        for word in segment['words']:
            start=word['start_seconds']+offset;end=word['end_seconds']+offset
            rows.append({'ordinal':len(rows),'text':word['text'],'start_seconds':start,'end_seconds':end,
                         'confidence':word['confidence'],'crosses_missing_audio':any(start<b and end>a for a,b in gaps)})
    return rows,gaps


def corrected(candidate,audio,media,words,*,actor_ref,version):
    original=candidate['provider_pcm_transcript'];rows,gaps=source_words(candidate,audio)
    if len(words)!=len(rows) or [w['ordinal'] for w in words]!=list(range(len(rows))):raise WorkflowError('ASR_GAP_WORD_COVERAGE_INVALID',400)
    offset=audio['decoded_source_clock']['source_start_seconds'];previous=0.;index=0;segments=[]
    for segment in original['segments']:
        chosen=[]
        for word in segment['words']:
            edit=words[index];index+=1
            if edit['removed']:continue
            start,end=edit['start_seconds'],edit['end_seconds']
            if start<previous or end<=start or end>media['duration_seconds'] or start<offset or end-offset>audio['duration_seconds'] or any(start<b and end>a for a,b in gaps):
                raise WorkflowError('ASR_GAP_WORD_INTERVAL_REVIEW_REQUIRED',400)
            chosen.append({**copy.deepcopy(word),'text':edit['text'],'start_seconds':start-offset,'end_seconds':end-offset,'confidence':None});previous=end
        if chosen:segments.append({**copy.deepcopy(segment),'start_seconds':chosen[0]['start_seconds'],'end_seconds':chosen[-1]['end_seconds'],
                                   'text':' '.join(w['text'] for w in chosen),'words':chosen,'confidence':None})
    if not segments:raise WorkflowError('ASR_GAP_REVIEW_EMPTY_TRANSCRIPT',400)
    value=copy.deepcopy(original);value.update(segments=segments,confidence=None)
    proof=value['provenance'];proof.update(human_edit=True,actor_ref=actor_ref,human_gap_review_version=version,
        original_evidence=False,provider_transcript_immutable=False,word_timing_source='human_reviewed_source_timestamps',
        timestamp_source='human_reviewed_source_timestamps',original_provider_words_sha256=original['provenance'].get('words_sha256'),
        original_provider_transcript_sha256=original['provenance'].get('transcript_sha256'),
        words_sha256=digest([w for s in segments for w in s['words']]),transcript_sha256=hashlib.sha256(' '.join(s['text'] for s in segments).encode()).hexdigest(),
        source_media_mutated=False,remote_calls=0,provider_original_candidate_sha256=candidate['sha256'])
    return value


def receipt_value(candidate,audio,media,receipt):
    if receipt.get('sha256')!=digest({k:v for k,v in receipt.items() if k!='sha256'}) or receipt.get('schema_version')!='native-asr-gap-review-receipt-v1' or receipt.get('job_id')!=candidate['job_id'] or receipt.get('asset_id')!=candidate['asset_id'] or receipt.get('candidate_sha256')!=candidate['sha256'] or receipt.get('acknowledged') is not True:
        raise WorkflowError('ASR_GAP_REVIEW_CHANGED')
    value=corrected(candidate,audio,media,receipt['words'],actor_ref=receipt['actor_ref'],version=receipt['version'])
    if digest(value)!=receipt['reviewed_pcm_transcript_sha256']:raise WorkflowError('ASR_GAP_REVIEW_CHANGED')
    return value


def validate_embedded(record):
    candidate=validate_candidate(record['source_gap_candidate'],audio=record['audio'],media=record['media'])
    if candidate['asset_id']!=record['asset_id'] or candidate['source_sha256']!=record['source_sha256'] or digest(candidate['provider_pcm_transcript'])!=digest(record['provider_pcm_transcript']):raise WorkflowError('ASR_GAP_REVIEW_CHANGED')
    return receipt_value(candidate,record['audio'],record['media'],record['source_gap_review'])


def latest(store,job_id,asset_id,candidate,audio,media):
    with store.transaction() as con:
        row=con.execute('SELECT receipt FROM asr_gap_reviews WHERE job_id=? AND asset_id=? ORDER BY version DESC LIMIT 1',(job_id,asset_id)).fetchone()
    if row is None:return None,None
    receipt=json.loads(row['receipt']);return receipt_value(candidate,audio,media,receipt),receipt


def candidate_for(store,config,job,asset):
    if config.data_root.resolve()!=store.root.resolve():raise WorkflowError('ASR_GAP_WORKSPACE_MISMATCH')
    directory=store.root/'jobs'/job['id']/'analysis'/asset['id'];artifacts=Artifacts(directory,job)
    candidate=artifacts.load('transcript-candidate')
    if not candidate:return None
    audio=artifacts.load('audio')['result'];candidate=candidate['result']
    validate_candidate(candidate,job=job,asset=asset,audio=audio)
    source=media_path(config,asset['id'])
    if not source.is_file() or file_sha(source)!=asset['sha256']:raise WorkflowError('ASR_GAP_SOURCE_CHANGED')
    # The immutable candidate checkpoint binds measured media and raw transcript.
    return candidate,audio,job['snapshot']['document'],directory


def view(store,config,project_id,workspace_id):
    project=store.get(project_id);items=[]
    with store.transaction() as con:jobs=[store.job(row,con) for row in con.execute("SELECT * FROM jobs WHERE project_id=? AND kind='asr' ORDER BY created_at DESC LIMIT 50",(project_id,)).fetchall()]
    for job in jobs:
        for asset in project_assets(job['snapshot']['document']):
            found=candidate_for(store,config,job,asset)
            if not found:continue
            candidate,audio,_,directory=found;rows,gaps=source_words(candidate,audio)
            if not any(w['crosses_missing_audio'] for w in rows):continue
            with store.transaction() as con:history=[json.loads(r['receipt']) for r in con.execute('SELECT receipt FROM asr_gap_reviews WHERE job_id=? AND asset_id=? ORDER BY version',(job['id'],asset['id'])).fetchall()]
            media=json.loads((directory/'transcript-candidate.json').read_bytes())['media']
            validate_candidate(candidate,media=media)
            for i,receipt in enumerate(history):
                if receipt['version']!=i+1:raise WorkflowError('ASR_GAP_REVIEW_HISTORY_CHANGED')
                receipt_value(candidate,audio,media,receipt)
            items.append({'job_id':job['id'],'asset_id':asset['id'],'filename':asset['filename'],'source_sha256':asset['sha256'],
                'candidate_sha256':candidate['sha256'],'status':job['status'],'original_words':rows,'gaps':[{'start_seconds':a,'end_seconds':b} for a,b in gaps],
                'version':len(history),'history':history,'current_words':history[-1]['words'] if history else [{k:w[k] for k in ('ordinal','text','start_seconds','end_seconds')}|{'removed':False} for w in rows],
                'editable':job['status']=='failed' and job['error'].get('code')=='ASR_WORD_OVER_SOURCE_AUDIO_GAP_REVIEW_REQUIRED' and project['revision']==job['revision'],
                'can_resume':bool(history) and job['status']=='failed' and job['resume_count']<3 and project['revision']==job['revision'],'source_kind':asset['kind'],
                'source_url':f'/api/projects/{project_id}/asr-gap-reviews/{job["id"]}/{asset["id"]}/source'})
    return {'schema_version':'native-asr-gap-review-v1','workspace_id':workspace_id,'project_id':project_id,'revision':project['revision'],
            'items':items,'provider_calls':0,'publishing_enabled':False,'source_media_mutated':False,'human_review_required':True}


def save(store,config,project_id,job_id,asset_id,body,*,actor_ref):
    try:payload=ReviewEdit.model_validate(body)
    except (ValidationError,TypeError,ValueError):raise WorkflowError('ASR_GAP_REVIEW_INVALID',400) from None
    if payload.acknowledged is not True or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',actor_ref):raise WorkflowError('ASR_GAP_REVIEW_ACKNOWLEDGEMENT_REQUIRED',400)
    job=store.get_job(job_id);asset=next((a for a in project_assets(job['snapshot']['document']) if a['id']==asset_id),None)
    if job['project_id']!=project_id or job['kind']!='asr' or asset is None:raise WorkflowError('ASR_GAP_REVIEW_NOT_FOUND',404)
    found=candidate_for(store,config,job,asset)
    if not found:raise WorkflowError('ASR_GAP_CANDIDATE_NOT_FOUND',404)
    candidate,audio,_,directory=found;media=json.loads((directory/'transcript-candidate.json').read_bytes())['media']
    if candidate['media_metadata_sha256']!=digest(media) or candidate['sha256']!=payload.candidate_sha256:raise WorkflowError('ASR_GAP_CANDIDATE_CHANGED')
    request_sha=digest(payload.model_dump(mode='json'));words=[w.model_dump(mode='json') for w in payload.words]
    with store.transaction() as con:
        project=store.editable(con,project_id,payload.revision);fresh=store.job(con.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone(),con)
        if fresh['status']!='failed' or fresh['error'].get('code')!='ASR_WORD_OVER_SOURCE_AUDIO_GAP_REVIEW_REQUIRED' or digest({'document':project['document'],'approval':project['approval']})!=digest({k:fresh['snapshot'][k] for k in ('document','approval')}):raise WorkflowError('ASR_GAP_REVIEW_STALE_OR_LOCKED')
        replay=con.execute('SELECT request_sha FROM asr_gap_reviews WHERE job_id=? AND asset_id=? AND request_key=?',(job_id,asset_id,payload.request_key)).fetchone()
        if replay:
            if replay['request_sha']!=request_sha:raise WorkflowError('ASR_GAP_REVIEW_IDEMPOTENCY_CONFLICT')
            return False
        version=con.execute('SELECT coalesce(max(version),0) FROM asr_gap_reviews WHERE job_id=? AND asset_id=?',(job_id,asset_id)).fetchone()[0]
        if version!=payload.expected_version:raise WorkflowError('ASR_GAP_REVIEW_VERSION_CHANGED')
        value=corrected(candidate,audio,media,words,actor_ref=actor_ref,version=version+1)
        receipt={'schema_version':'native-asr-gap-review-receipt-v1','review_id':uuid.uuid4().hex,'job_id':job_id,'asset_id':asset_id,
            'candidate_sha256':candidate['sha256'],'version':version+1,'words':words,'actor_ref':actor_ref,'created_at':now(),'note':payload.note,
            'acknowledged':True,'reviewed_pcm_transcript_sha256':digest(value),'source_media_mutated':False,'provider_calls':0}
        receipt['sha256']=digest(receipt)
        con.execute('INSERT INTO asr_gap_reviews VALUES(?,?,?,?,?,?,?)',(job_id,asset_id,version+1,payload.request_key,request_sha,json.dumps(receipt,ensure_ascii=False),now()))
        store.event(con,project_id,'asr_gap_review_version_saved',{'job_id':job_id,'asset_id':asset_id,'version':version+1,'actor_ref':actor_ref,'provider_calls':0,'source_media_mutated':False,'timeline_mutated':False})
    return True
