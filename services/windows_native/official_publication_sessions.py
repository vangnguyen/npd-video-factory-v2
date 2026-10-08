"""DPAPI-sealed opaque resumable sessions outside source/state/backups.

No OAuth, provider request, startup decryption or upload retry is performed.
"""
from datetime import datetime,timedelta,timezone
import json,os,re,uuid
from pathlib import Path
from .official_account_tokens import protected_path,unique_pairs
from .official_publication_dispatch import Ticket
from .contracts import WorkflowError,digest,file_sha
from .store import now
from app.youtube_upload import UploadSession
from app.publishing_wire import PublishingWireError

PREFIX=b'VF-NATIVE-YOUTUBE-UPLOAD-SESSION-1\n'
ENTROPY=b'NPD-Video-Factory/native-scoped-youtube-upload-session/v1'

class SessionVault:
    def __init__(self,journal,directory=None):
        self.journal=journal;self.root=journal.store.root;self.workspace=journal.workspace
        self.frozen_journal=journal;self.frozen_root=self.root.absolute();self.frozen_workspace=self.workspace
        self.directory=protected_path(directory,self.root) if directory is not None else None;self.frozen_directory=self.directory
        with journal.store.transaction() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS native_official_publish_sessions (
                session_ref TEXT PRIMARY KEY,publication_id TEXT UNIQUE NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                snapshot_sha256 TEXT NOT NULL,target_binding_sha256 TEXT NOT NULL,configuration_sha256 TEXT NOT NULL,
                mock INTEGER NOT NULL,total_bytes INTEGER NOT NULL,cipher_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL)''')
    def configured(self):
        if (self.journal is not self.frozen_journal or self.root.absolute()!=self.frozen_root or self.workspace!=self.frozen_workspace
            or self.journal.workspace!=self.workspace or self.journal.store.root.absolute()!=self.frozen_root or self.directory!=self.frozen_directory):raise WorkflowError('NATIVE_OFFICIAL_SESSION_CONFIGURATION_CHANGED')
        self.journal.accounts.check_workspace()
        if self.directory is None or os.name!='nt':return False
        if protected_path(self.directory,self.root)!=self.directory or self.directory.exists() and not self.directory.is_dir():raise WorkflowError('NATIVE_OFFICIAL_SESSION_CONFIGURATION_CHANGED')
        return True
    def public(self):
        return {'schema_version':'native-official-session-vault-v1','workspace_id':self.workspace,'status':'CONFIGURED' if self.configured() else 'NOT_CONFIGURED',
            'session_uri_returned':False,'oauth_token_stored':False,'external_calls':0,'startup_decryption':False}
    def path(self,reference):
        if not self.configured() or not isinstance(reference,str) or not re.fullmatch(r'nups_[a-f0-9]{32}',reference):raise WorkflowError('NATIVE_OFFICIAL_SESSION_UNAVAILABLE')
        return protected_path(self.directory/(reference+'.dpapi'),self.root)
    def save(self,ticket,session,*,ttl_seconds=3600):
        from .assemblyai_connection import _dpapi,_restrict_file
        if not self.configured():raise WorkflowError('NATIVE_OFFICIAL_SESSION_NOT_CONFIGURED')
        if type(ticket) is not Ticket or ticket.operation!='init' or type(session) is not UploadSession or type(ttl_seconds) is not int or not 60<=ttl_seconds<=86400:raise WorkflowError('NATIVE_OFFICIAL_SESSION_REQUEST_INVALID',400)
        try:session=UploadSession(session.uri,session.total_bytes)
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_SESSION_REQUEST_INVALID',400) from None
        with self.journal.store.transaction() as con:
            value,dispatch,_=self.journal.fence(con,ticket)
            if session.total_bytes!=dispatch['total_bytes'] or dispatch['private_session_ref'] is not None:raise WorkflowError('NATIVE_OFFICIAL_SESSION_BINDING_CHANGED')
            if con.execute('SELECT 1 FROM native_official_publish_sessions WHERE publication_id=?',(ticket.publication_id,)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_SESSION_ALREADY_REGISTERED')
            instant=self.journal.clock()
            if instant.tzinfo is None:raise WorkflowError('NATIVE_OFFICIAL_SESSION_TIME_INVALID')
            instant=instant.astimezone(timezone.utc);reference='nups_'+uuid.uuid4().hex
            binding={'session_ref':reference,'publication_id':ticket.publication_id,'workspace_id':self.workspace,'project_id':ticket.project_id,'snapshot_sha256':ticket.snapshot_sha256,
                'target_binding_sha256':value['snapshot']['target_binding_sha256'],'configuration_sha256':value['snapshot']['configuration_sha256'],'mock':value['snapshot']['mock'],
                'total_bytes':session.total_bytes,'created_at':instant.isoformat(),'expires_at':(instant+timedelta(seconds=ttl_seconds)).isoformat()}
        envelope={'schema_version':'native-youtube-upload-session-v1','binding':binding,'uri':session.uri}
        encrypted=PREFIX+_dpapi(json.dumps(envelope,sort_keys=True,separators=(',', ':')).encode(),entropy=ENTROPY,description='Video Factory scoped YouTube upload session')
        target=self.path(reference);self.directory.mkdir(parents=True,exist_ok=True);temporary=self.path('nups_'+uuid.uuid4().hex).with_suffix('.part')
        try:
            with temporary.open('xb') as handle:_restrict_file(temporary);handle.write(encrypted);handle.flush();os.fsync(handle.fileno())
            os.rename(temporary,target)
        except FileExistsError:raise WorkflowError('NATIVE_OFFICIAL_SESSION_ALREADY_REGISTERED') from None
        finally:temporary.unlink(missing_ok=True)
        # A known response may be retained after consent expires; it cannot
        # authorize more bytes. Lost-response recovery never starts another init.
        with self.journal.store.transaction() as con:
            self.journal.fence(con,ticket)
            try:self.journal.admission(ticket.project_id,ticket.publication_id,con=con);needs_approval=False
            except WorkflowError:needs_approval=True
            if file_sha(target)!=digest_bytes(encrypted):raise WorkflowError('NATIVE_OFFICIAL_SESSION_CIPHERTEXT_CHANGED')
            con.execute('INSERT INTO native_official_publish_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(reference,ticket.publication_id,self.workspace,ticket.project_id,ticket.snapshot_sha256,
                binding['target_binding_sha256'],binding['configuration_sha256'],int(binding['mock']),session.total_bytes,file_sha(target),binding['created_at'],binding['expires_at']))
            con.execute("UPDATE native_official_publish_dispatches SET private_session_ref=?,phase='uploading',version=version+1,intent_id=NULL,updated_at=? WHERE publication_id=?",(reference,now(),ticket.publication_id))
            con.execute("UPDATE native_official_publish_intents SET status='response_received' WHERE intent_id=?",(ticket.intent_id,))
            con.execute('UPDATE native_official_publications SET status=?,updated_at=? WHERE publication_id=?',('review_required' if needs_approval else 'queued',now(),ticket.publication_id))
            self.journal.event(con,self.journal.row(con,ticket.project_id,ticket.publication_id),'official.publication.session.registered','worker',session_ref=reference,cipher_sha256=file_sha(target),uri_returned=False,external_action=False,needs_current_approval=needs_approval)
        return {'schema_version':'native-official-session-receipt-v1','session_ref':reference,'publication_id':ticket.publication_id,'cipher_sha256':file_sha(target),'uri_returned':False,'oauth_token_stored':False,'needs_current_approval':needs_approval}
    def load(self,project,identity):
        from .assemblyai_connection import _dpapi
        try:
            with self.journal.store.transaction() as con:
                value,_,_,dispatch=self.journal.admission(project,identity,con=con)
                row=con.execute('SELECT * FROM native_official_publish_sessions WHERE session_ref=? AND publication_id=? AND workspace_id=? AND project_id=?',(dispatch['private_session_ref'],identity,self.workspace,project)).fetchone()
                if row is None:raise ValueError()
                binding={k:row[k] for k in ('session_ref','publication_id','workspace_id','project_id','snapshot_sha256','target_binding_sha256','configuration_sha256','total_bytes','created_at','expires_at')}
                if row['mock'] not in (0,1):raise ValueError()
                binding['mock']=bool(row['mock']);instant=self.journal.clock();created=datetime.fromisoformat(binding['created_at']);expires=datetime.fromisoformat(binding['expires_at'])
                if (instant.tzinfo is None or created.tzinfo is None or expires.tzinfo is None or not created<=instant<expires or not 60<=(expires-created).total_seconds()<=86400
                    or binding['snapshot_sha256']!=value['snapshot_sha256'] or binding['target_binding_sha256']!=value['snapshot']['target_binding_sha256']
                    or binding['configuration_sha256']!=value['snapshot']['configuration_sha256'] or binding['mock'] is not value['snapshot']['mock'] or binding['total_bytes']!=dispatch['total_bytes']):raise ValueError()
                path=self.path(binding['session_ref'])
                if not path.is_file() or not 1<=path.stat().st_size<=16384 or file_sha(path)!=row['cipher_sha256']:raise ValueError()
                raw=path.read_bytes()
            if not raw.startswith(PREFIX):raise ValueError()
            decoded=_dpapi(raw[len(PREFIX):],decrypt=True,entropy=ENTROPY);value=json.loads(decoded,object_pairs_hook=unique_pairs)
            if (not isinstance(value,dict) or set(value)!={'schema_version','binding','uri'} or value['schema_version']!='native-youtube-upload-session-v1'
                or not isinstance(value['binding'],dict) or value['binding']!=binding or type(value['binding'].get('mock')) is not bool
                or type(value['binding'].get('total_bytes')) is not int):raise ValueError()
            # Revalidate current consent after decryption, before returning a URI to the worker.
            self.journal.admission(project,identity)
            return UploadSession(value['uri'],binding['total_bytes'])
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_SESSION_UNAVAILABLE') from None

def digest_bytes(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()
