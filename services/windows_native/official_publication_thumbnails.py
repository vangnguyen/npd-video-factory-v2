"""One-shot original PNG journal; a known response never renews authority."""
from dataclasses import asdict,dataclass,field
from datetime import datetime
import json,re,uuid
from .contracts import WorkflowError,digest
from .store import now
from app.publishing_models import PublicationMetadata
from app.youtube_thumbnail import ThumbnailSetObservation,MAX_EDGE,MAX_PNG_BYTES,VARIANTS,png_image
from app.youtube_upload import video_id


def sha(value):return isinstance(value,str) and bool(re.fullmatch(r'[a-f0-9]{64}',value))
def requested(snapshot):
    """Validate the immutable original review without consulting a current secret."""
    try:
        metadata=PublicationMetadata.model_validate(snapshot['metadata']);proof=snapshot.get('thumbnail')
        if metadata.thumbnail_asset_id is None:
            if proof is not None:raise ValueError()
            return False
        image=proof['image'];exception=proof['owner_exception']
        if (proof['schema_version']!='native-publication-thumbnail-review-v1' or proof['scope']!='dry_run_metadata_review'
            or any(proof[k]!=snapshot[k] for k in ('workspace_id','project_id','document_sha256','final_sha256'))
            or proof['render_job_id']!=snapshot['final_job_id'] or proof['render_snapshot_sha256']!=snapshot['final_job_snapshot_sha256']
            or proof['thumbnail_asset_id']!=metadata.thumbnail_asset_id or proof['status']!='passed' or not sha(proof['thumbnail_snapshot_sha256'])
            or image['content_type']!='image/png' or not sha(image['sha256']) or image['rights_status']!='unknown' or image['license'] is not None
            or type(image['bytes']) is not int or not 45<=image['bytes']<=MAX_PNG_BYTES
            or any(type(image[k]) is not int or not 3<=image[k]<=MAX_EDGE for k in ('width','height'))
            or proof['original_source_rights_review_still_required'] is not True
            or any(proof[k] is not False for k in ('official_thumbnail_transport_configured','rights_independently_verified','source_asset_rights_granted','final_video_approved','provider_authorized','publishing_authorized','owner_uat_accepted'))
            or type(proof['external_calls']) is not int or proof['external_calls']!=0
            or exception['allow_publishing_review'] is not True or exception['thumbnail_asset_id']!=metadata.thumbnail_asset_id
            or any(exception[k]!=proof[k] for k in ('workspace_id','project_id','thumbnail_snapshot_sha256'))
            or not re.fullmatch(r'nrto_[a-f0-9]{32}',exception['override_id'])
            or any(not sha(exception[k]) for k in ('override_snapshot_sha256','owner_identity_sha256','rights_input_sha256'))):raise ValueError()
        return True
    except (ValueError,TypeError,KeyError,AttributeError):raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_BINDING_CHANGED') from None


def video_metadata(snapshot):
    metadata=PublicationMetadata.model_validate(snapshot['metadata'])
    return metadata.model_copy(update={'thumbnail_asset_id':None}) if requested(snapshot) else metadata


@dataclass(frozen=True)
class ThumbnailTicket:
    publication_id:str
    workspace_id:str
    project_id:str
    snapshot_sha256:str
    approval_id:str
    version:int
    intent_id:str=field(repr=False)
    def __post_init__(self):
        if (not isinstance(self.publication_id,str) or not re.fullmatch(r'nopu_[a-f0-9]{32}',self.publication_id)
            or not isinstance(self.workspace_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',self.workspace_id)
            or not isinstance(self.project_id,str) or not re.fullmatch(r'[a-f0-9]{32}',self.project_id) or not sha(self.snapshot_sha256)
            or not isinstance(self.approval_id,str) or not re.fullmatch(r'nopa_[a-f0-9]{32}',self.approval_id)
            or type(self.version) is not int or self.version<2 or not isinstance(self.intent_id,str) or not re.fullmatch(r'[a-f0-9]{32}',self.intent_id)):
            raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_TICKET_INVALID',400)


def observation(value,expected_image,remote):
    try:
        if type(value) is not dict or set(value)!={'remote_video_id','original_image','variants','etag_sha256','provider_response_acknowledged','remote_image_bytes_verified','rights_independently_verified','publishing_authorized'}:raise ValueError()
        if (value['remote_video_id']!=remote or value['original_image']!=expected_image or value['provider_response_acknowledged'] is not True
            or any(value[k] is not False for k in ('remote_image_bytes_verified','rights_independently_verified','publishing_authorized'))
            or value['etag_sha256'] is not None and not sha(value['etag_sha256']) or type(value['variants']) is not list or not 1<=len(value['variants'])<=len(VARIANTS)):raise ValueError()
        names=[]
        for variant in value['variants']:
            if (type(variant) is not dict or set(variant)!={'name','url_sha256','width','height'} or variant['name'] not in VARIANTS or not sha(variant['url_sha256'])
                or any(d is not None and (type(d) is not int or not 1<=d<=16384) for d in (variant['width'],variant['height']))):raise ValueError()
            names.append(variant['name'])
        if names!=sorted(set(names)):raise ValueError()
        return value
    except (ValueError,TypeError,KeyError):raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_RESPONSE_CHANGED') from None


class NativeOfficialPublicationThumbnails:
    def __init__(self,journal):
        self.journal=journal;self._frozen=(journal,journal.store,journal.publications,journal.workspace,journal.store.root.absolute())
        with journal.store.transaction() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS native_official_publish_thumbnails (
                publication_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
                approval_id TEXT NOT NULL,intent_id TEXT NOT NULL UNIQUE,version INTEGER NOT NULL,intent_json TEXT NOT NULL,intent_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,response_sha256 TEXT,result_json TEXT,result_sha256 TEXT,failure_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    def check(self):
        j=self.journal
        if self._frozen!=(j,j.store,j.publications,j.workspace,j.store.root.absolute()) or j.thumbnails is not self:
            raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_CONFIGURATION_CHANGED')
        j.accounts.check_workspace()
    def read(self,con,value):
        self.check();row=con.execute('SELECT * FROM native_official_publish_thumbnails WHERE publication_id=?',(value['publication_id'],)).fetchone()
        needed=requested(value['snapshot'])
        if row is None:return None
        try:
            intent=json.loads(row['intent_json']);s=value['snapshot'];p=s['thumbnail'];image={k:p['image'][k] for k in ('sha256','bytes','width','height')}
            if (not needed or any(row[k]!=value[k] for k in ('workspace_id','project_id','snapshot_sha256')) or digest(intent)!=row['intent_sha256']
                or set(intent)!={'schema_version','publication_id','workspace_id','project_id','snapshot_sha256','approval_id','version','intent_id','remote_video_id','image','thumbnail_snapshot_sha256','owner_exception_snapshot_sha256','mock'}
                or intent['schema_version']!='native-official-thumbnail-intent-v1' or any(intent[k]!=row[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256','approval_id','version','intent_id'))
                or intent['image']!=image or intent['thumbnail_snapshot_sha256']!=p['thumbnail_snapshot_sha256']
                or intent['owner_exception_snapshot_sha256']!=p['owner_exception']['override_snapshot_sha256'] or intent['mock'] is not value['mock']):raise ValueError()
            ThumbnailTicket(**{k:intent[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256','approval_id','version','intent_id')});video_id(intent['remote_video_id'])
            for key in ('created_at','updated_at'):
                if datetime.fromisoformat(row[key]).tzinfo is None:raise ValueError()
            grant=con.execute('SELECT * FROM native_official_publish_approvals WHERE approval_id=? AND publication_id=?',(row['approval_id'],value['publication_id'])).fetchone()
            authority=json.loads(grant['grant_json']) if grant is not None else None
            if (grant is None or any(grant[k]!=value[k] for k in ('workspace_id','project_id')) or digest(authority)!=grant['grant_sha256'] or authority['snapshot_sha256']!=value['snapshot_sha256']
                or authority['acknowledged_official_publication'] is not True or authority['mock'] is not value['mock']):raise ValueError()
            dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(value['publication_id'],)).fetchone()
            if dispatch is None or any(dispatch[k]!=value[k] for k in ('workspace_id','project_id','snapshot_sha256')) or dispatch['phase']!='uploaded' or dispatch['remote_post_id']!=intent['remote_video_id'] or dispatch['total_bytes']!=s['final_bytes'] or dispatch['acknowledged_bytes']!=dispatch['total_bytes'] or dispatch['version']<row['version']:raise ValueError()
            if row['status'] not in ('dispatch_intent','response_received','outcome_unknown'):raise ValueError()
            result=json.loads(row['result_json']) if row['result_json'] is not None else None
            if row['status']=='response_received':
                if not sha(row['response_sha256']) or digest(result)!=row['result_sha256'] or row['failure_code'] is not None:raise ValueError()
                observation(result,image,intent['remote_video_id'])
            elif result is not None or row['result_sha256'] is not None or row['response_sha256'] is not None and not sha(row['response_sha256']):raise ValueError()
            if row['status']=='dispatch_intent' and (row['failure_code'] is not None or row['response_sha256'] is not None):raise ValueError()
            if row['status']=='outcome_unknown' and (not isinstance(row['failure_code'],str) or not re.fullmatch(r'[A-Z0-9_]{1,120}',row['failure_code'])):raise ValueError()
            return {**dict(row),'intent':intent,'result':result}
        except (ValueError,TypeError,KeyError,AttributeError,WorkflowError):raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_EVIDENCE_CHANGED') from None
    def state(self,con,value):
        row=self.read(con,value)
        if not requested(value['snapshot']):return None
        return {'schema_version':'native-official-thumbnail-stage-v1','publication_id':value['publication_id'],'workspace_id':value['workspace_id'],'project_id':value['project_id'],
            'snapshot_sha256':value['snapshot_sha256'],'status':row['status'] if row else 'not_started','intent_sha256':row['intent_sha256'] if row else None,
            'response_sha256':row['response_sha256'] if row else None,'result_sha256':row['result_sha256'] if row else None,
            'image_sha256':value['snapshot']['thumbnail']['image']['sha256'],'remote_post_id':row['intent']['remote_video_id'] if row else None,
            'provider_response_acknowledged':bool(row and row['status']=='response_received'),'mock':value['mock'],
            'remote_image_bytes_verified':False,'rights_independently_verified':False,'publishing_authorized':False,'automatic_retry':False,'token_returned':False}
    def confirmed(self,con,value):
        row=self.read(con,value)
        return not requested(value['snapshot']) or bool(row and row['status']=='response_received')
    def begin(self,project,identity,expected_version):
        if type(expected_version) is not int:raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_VERSION_INVALID',400)
        j=self.journal;self.check()
        with j.store.transaction() as con:
            value,_,_,dispatch=j.admission(project,identity,con=con);j.eligible(con,project,identity,value)
            if not requested(value['snapshot']) or dispatch['phase']!='uploaded' or dispatch['version']!=expected_version or dispatch['intent_id'] is not None:
                raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_UPLOAD_REQUIRED')
            if self.read(con,value) is not None:raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_ALREADY_ATTEMPTED')
            video_id(dispatch['remote_post_id']);version=expected_version+1;intent_id=uuid.uuid4().hex;p=value['snapshot']['thumbnail']
            ticket=ThumbnailTicket(identity,j.workspace,project,value['snapshot_sha256'],value['approval_id'],version,intent_id)
            intent={'schema_version':'native-official-thumbnail-intent-v1',**asdict(ticket),'remote_video_id':dispatch['remote_post_id'],
                'image':{k:p['image'][k] for k in ('sha256','bytes','width','height')},'thumbnail_snapshot_sha256':p['thumbnail_snapshot_sha256'],
                'owner_exception_snapshot_sha256':p['owner_exception']['override_snapshot_sha256'],'mock':value['mock']};stamp=now()
            con.execute('INSERT INTO native_official_publish_thumbnails VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,j.workspace,project,value['snapshot_sha256'],value['approval_id'],intent_id,version,json.dumps(intent),digest(intent),'dispatch_intent',None,None,None,None,stamp,stamp))
            con.execute('UPDATE native_official_publish_dispatches SET version=?,updated_at=? WHERE publication_id=?',(version,stamp,identity))
            con.execute("UPDATE native_official_publications SET status='running',updated_at=? WHERE publication_id=?",(stamp,identity))
            j.event(con,j.row(con,project,identity),'official.publication.thumbnail.intent','worker',intent_sha256=digest(intent),image_sha256=intent['image']['sha256'],version=version,external_action=False)
            return ticket
    def fence(self,con,ticket):
        self.check()
        if type(ticket) is not ThumbnailTicket:raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_TICKET_INVALID',400)
        ThumbnailTicket(**asdict(ticket));j=self.journal;value=j.read(j.row(con,ticket.project_id,ticket.publication_id));row=self.read(con,value)
        if (row is None or row['status']!='dispatch_intent' or any(row[k]!=getattr(ticket,k) for k in ('publication_id','workspace_id','project_id','snapshot_sha256','approval_id','version','intent_id'))
            or value['approval_id']!=ticket.approval_id):raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_TICKET_STALE')
        dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(ticket.publication_id,)).fetchone()
        if dispatch['version']!=ticket.version or dispatch['phase']!='uploaded' or dispatch['intent_id'] is not None:raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_TICKET_STALE')
        return value,row
    def content(self,ticket):
        j=self.journal
        with j.store.transaction() as con:
            value,row=self.fence(con,ticket);j.admission(ticket.project_id,ticket.publication_id,con=con)
            job=j.store.job(con.execute('SELECT * FROM jobs WHERE id=?',(value['snapshot']['final_job_id'],)).fetchone(),con)
            binding=j.publications._thumbnail_binding;binding.check()
            data,_=binding.rights.thumbnails.image(ticket.project_id,value['snapshot']['thumbnail']['thumbnail_asset_id'],con=con)
            if asdict(png_image(data,row['intent']['image']['sha256']))!=row['intent']['image']:raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_IMAGE_CHANGED')
            if j.publications.thumbnail_review(job,PublicationMetadata.model_validate(value['snapshot']['metadata']),con=con)!=value['snapshot']['thumbnail']:
                raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_BINDING_CHANGED')
            return data,row['intent']['remote_video_id']
    def finish(self,ticket,observed,response_sha256):
        if type(observed) is not ThumbnailSetObservation or not sha(response_sha256):raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_RESPONSE_INVALID',400)
        j=self.journal
        with j.store.transaction() as con:
            value,row=self.fence(con,ticket);result=asdict(observed);result['variants']=list(result['variants']);observation(result,row['intent']['image'],row['intent']['remote_video_id'])
            stamp=now();current=True
            try:j.admission(ticket.project_id,ticket.publication_id,con=con)
            except WorkflowError:current=False
            con.execute("UPDATE native_official_publish_thumbnails SET status='response_received',response_sha256=?,result_json=?,result_sha256=?,updated_at=? WHERE publication_id=?",(response_sha256,json.dumps(result),digest(result),stamp,ticket.publication_id))
            con.execute('UPDATE native_official_publish_dispatches SET version=version+1,updated_at=? WHERE publication_id=?',(stamp,ticket.publication_id))
            failure=None if current else value.get('failure_code') or 'NATIVE_OFFICIAL_THUMBNAIL_CURRENT_AUTHORITY_REQUIRED'
            con.execute('UPDATE native_official_publications SET status=?,failure_code=?,updated_at=? WHERE publication_id=?',('queued' if current else 'review_required',failure,stamp,ticket.publication_id))
            j.event(con,j.row(con,ticket.project_id,ticket.publication_id),'official.publication.thumbnail.response','worker',response_sha256=response_sha256,result_sha256=digest(result),mock=value['mock'],current_authority_valid=current,remote_image_bytes_verified=False)
        return j.state(ticket.project_id,ticket.publication_id)
    def unknown(self,ticket,failure_code,*,response_sha256=None):
        if not isinstance(failure_code,str) or not re.fullmatch(r'[A-Z0-9_]{1,120}',failure_code):failure_code='NATIVE_OFFICIAL_THUMBNAIL_RESPONSE_UNCONFIRMED'
        if response_sha256 is not None and not sha(response_sha256):raise WorkflowError('NATIVE_OFFICIAL_THUMBNAIL_RESPONSE_INVALID',400)
        j=self.journal
        with j.store.transaction() as con:
            self.fence(con,ticket);stamp=now()
            con.execute("UPDATE native_official_publish_thumbnails SET status='outcome_unknown',response_sha256=?,failure_code=?,updated_at=? WHERE publication_id=?",(response_sha256,failure_code,stamp,ticket.publication_id))
            con.execute('UPDATE native_official_publish_dispatches SET version=version+1,failure_code=?,updated_at=? WHERE publication_id=?',(failure_code,stamp,ticket.publication_id))
            con.execute("UPDATE native_official_publications SET status='review_required',failure_code=?,updated_at=? WHERE publication_id=?",(failure_code,stamp,ticket.publication_id))
            j.event(con,j.row(con,ticket.project_id,ticket.publication_id),'official.publication.thumbnail.unconfirmed','worker',failure_code=failure_code,automatic_retry=False,response_sha256=response_sha256)
        return j.state(ticket.project_id,ticket.publication_id)
    def recover(self):
        j=self.journal;self.check()
        with j.store.transaction() as con:
            rows=con.execute("SELECT * FROM native_official_publish_thumbnails WHERE workspace_id=? AND status='dispatch_intent'",(j.workspace,)).fetchall()
            tickets=[ThumbnailTicket(**{k:row[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256','approval_id','version','intent_id')}) for row in rows]
        for ticket in tickets:self.unknown(ticket,'NATIVE_OFFICIAL_THUMBNAIL_RESTART_OUTCOME_UNKNOWN')
        return len(tickets)
