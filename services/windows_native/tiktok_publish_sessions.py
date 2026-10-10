"""Distinct DPAPI custody for known TikTok FILE_UPLOAD initialization responses."""
import hashlib,json,os,uuid
from datetime import timedelta,timezone
from app.tiktok_upload import UploadSession,ChunkPlan
from .contracts import WorkflowError,digest,file_sha
from .official_publication_dispatch import Ticket
from .store import now
from . import tiktok_publishing as journal
PREFIX=b'VF-NATIVE-TIKTOK-UPLOAD-SESSION-1\n'
ENTROPY=b'NPD-Video-Factory/native-scoped-tiktok-upload-session/v1'
def save(vault,ticket,session,*,cost_operation_id,response_sha256):
    from .assemblyai_connection import _dpapi,_restrict_file
    if not vault.configured():raise WorkflowError('NATIVE_OFFICIAL_SESSION_NOT_CONFIGURED')
    if type(ticket) is not Ticket or ticket.operation!='init' or type(session) is not UploadSession:raise WorkflowError('NATIVE_TIKTOK_SESSION_REQUEST_INVALID',400)
    session=UploadSession(session.publish_id,session.uri,session.plan,session.expires_at)
    with vault.journal.store.transaction() as con:
        value,dispatch,intent=vault.journal.fence(con,ticket);s=value['snapshot']
        if s['target']['platform']!='tiktok' or session.plan!=ChunkPlan(dispatch['total_bytes'],s['chunk_size']) or dispatch['private_session_ref'] is not None:raise WorkflowError('NATIVE_TIKTOK_SESSION_BINDING_CHANGED')
        proof=journal.init_proof(con,value,intent);request=journal.metadata_request(value,journal.parsed_creator(proof['proof']['creator']))
        journal.cost(con,value,cost_operation_id,ticket.version,'upload_initialize',hashlib.sha256(request.body).hexdigest(),response_sha256,intent_id=ticket.intent_id)
        if con.execute('SELECT 1 FROM native_official_publish_sessions WHERE publication_id=?',(ticket.publication_id,)).fetchone() or con.execute('SELECT 1 FROM '+journal.JOBS+' WHERE publication_id=?',(ticket.publication_id,)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_SESSION_ALREADY_REGISTERED')
        issued=(session.expires_at-timedelta(hours=1)).astimezone(timezone.utc);expires=session.expires_at.astimezone(timezone.utc);reference='nups_'+uuid.uuid4().hex
        if issued>vault.journal.clock():raise WorkflowError('NATIVE_TIKTOK_SESSION_TIME_INVALID')
        binding={'session_ref':reference,'publication_id':ticket.publication_id,'workspace_id':vault.workspace,'project_id':ticket.project_id,'snapshot_sha256':ticket.snapshot_sha256,
            'target_binding_sha256':s['target_binding_sha256'],'configuration_sha256':s['configuration_sha256'],'mock':value['mock'],'total_bytes':session.plan.total_bytes,'created_at':issued.isoformat(),'expires_at':expires.isoformat()}
        job={'schema_version':'native-tiktok-provider-job-v1','provider_job_id':session.publish_id,'session_ref':reference,'total_bytes':session.plan.total_bytes,'init_intent_id':ticket.intent_id,
            'init_response_sha256':response_sha256,'init_cost_operation_id':cost_operation_id,'creator_preflight_id':proof['proof']['check_id'],'creator_preflight_sha256':proof['sha256'],
            'target_binding_sha256':s['target_binding_sha256'],'configuration_sha256':s['configuration_sha256'],'created_at':issued.isoformat(),'expires_at':expires.isoformat(),
            'mock':value['mock'],'token_returned':False,'upload_url_returned':False}
    envelope={'schema_version':'native-tiktok-upload-session-v1','binding':binding,'uri':session.uri,'publish_id':session.publish_id,'chunk_size':session.plan.chunk_bytes,'job':job}
    raw=json.dumps(envelope,sort_keys=True,separators=(',',':')).encode();encrypted=PREFIX+_dpapi(raw,entropy=ENTROPY,description='Video Factory scoped TikTok upload session')
    target=vault.path(reference);vault.directory.mkdir(parents=True,exist_ok=True);temporary=vault.path('nups_'+uuid.uuid4().hex).with_suffix('.part')
    try:
        with temporary.open('xb') as out:_restrict_file(temporary);out.write(encrypted);out.flush();os.fsync(out.fileno())
        os.rename(temporary,target)
    except FileExistsError:raise WorkflowError('NATIVE_OFFICIAL_SESSION_ALREADY_REGISTERED') from None
    finally:temporary.unlink(missing_ok=True)
    with vault.journal.store.transaction() as con:
        value,_,_=vault.journal.fence(con,ticket)
        try:vault.journal.admission(ticket.project_id,ticket.publication_id,con=con);needs_approval=False
        except WorkflowError:needs_approval=True
        if file_sha(target)!=hashlib.sha256(encrypted).hexdigest():raise WorkflowError('NATIVE_OFFICIAL_SESSION_CIPHERTEXT_CHANGED')
        con.execute('INSERT INTO native_official_publish_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(reference,ticket.publication_id,vault.workspace,ticket.project_id,ticket.snapshot_sha256,
            binding['target_binding_sha256'],binding['configuration_sha256'],int(binding['mock']),session.plan.total_bytes,file_sha(target),binding['created_at'],binding['expires_at']))
        con.execute('INSERT INTO '+journal.JOBS+' VALUES(?,?,?,?,?,?,?)',(ticket.publication_id,vault.workspace,ticket.project_id,ticket.snapshot_sha256,json.dumps(job),digest(job),binding['created_at']))
        con.execute("UPDATE native_official_publish_intents SET status='response_received' WHERE intent_id=?",(ticket.intent_id,))
        con.execute("UPDATE native_official_publish_dispatches SET private_session_ref=?,phase='uploading',version=version+1,intent_id=NULL,updated_at=? WHERE publication_id=?",(reference,now(),ticket.publication_id))
        con.execute('UPDATE native_official_publications SET status=?,updated_at=? WHERE publication_id=?',('review_required' if needs_approval else 'queued',now(),ticket.publication_id))
        vault.journal.event(con,vault.journal.row(con,ticket.project_id,ticket.publication_id),'official.tiktok.session.registered','worker',session_ref=reference,provider_job_id=session.publish_id,init_response_sha256=response_sha256,
            cipher_sha256=file_sha(target),provider_job_sha256=digest(job),uri_returned=False,needs_current_approval=needs_approval,external_action=False)
        journal.job(con,value)
    return {'schema_version':'native-official-session-receipt-v1','session_ref':reference,'publication_id':ticket.publication_id,'cipher_sha256':file_sha(target),'uri_returned':False,'oauth_token_stored':False,'needs_current_approval':needs_approval}
