"""Independent Native /v1 boundary, immutable local outbox and delivery audit.

Only Video Factory's pure wire helpers are reused. No Agent Hub package,
database, Redis, memory or availability is a dependency of core production.
"""
import asyncio
import base64
from datetime import datetime,timezone
import hashlib
import json
import math
import re
import time
import threading
import uuid
from . import ingestion
from .contracts import WorkflowError,digest
from .backup import guard
from .bridge_models import NativeBridgeDraft
from .bridge_transport import BridgeResponse,FixtureWebhookTransport,HTTPSWebhookTransport
from app.bridge_auth import (ServiceAuthVerifier,ServiceAuthError,SigningKeyring,
    CONTRACT_VERSION_HEADER,SERVICE_ID_HEADER,KEY_ID_HEADER,TIMESTAMP_HEADER,NONCE_HEADER,
    CONTENT_HASH_HEADER,SIGNATURE_HEADER,canonical_json_bytes,ServiceIdentity,_decode_keys)

VERSION='agent-hub-bridge.v1'
EVENTS=('trend.opportunity.detected','idea.shortlist.ready','video.project.created',
    'video.analysis.completed','video.preview.ready','video.approval.required','video.approved',
    'video.render.completed','video.render.failed','video.publish.completed','video.publish.failed',
    'video.analytics.updated','video.winner.detected')
HEADERS=(SERVICE_ID_HEADER,KEY_ID_HEADER,TIMESTAMP_HEADER,NONCE_HEADER,CONTENT_HASH_HEADER,SIGNATURE_HEADER,CONTRACT_VERSION_HEADER)


class ReplayStore:
    def __init__(self,bridge):self.bridge=bridge

    async def set(self,key,value,*,ex,nx):
        bridge=self.bridge;stamp=int(bridge.clock())
        with bridge.store.transaction() as con:
            con.execute('DELETE FROM native_bridge_nonces WHERE expires_at<=?',(stamp,))
            if con.execute('SELECT count(*) FROM native_bridge_nonces WHERE workspace_id=?',(bridge.workspace,)).fetchone()[0]>=10000:
                raise WorkflowError('NATIVE_BRIDGE_AUTH_RATE_LIMIT',429)
            return con.execute('INSERT OR IGNORE INTO native_bridge_nonces VALUES(?,?,?)',
                (bridge.workspace,hashlib.sha256(key.encode()).hexdigest(),stamp+ex)).rowcount==1


class NativeBridge:
    def __init__(self,store,*,workspace_id='wsp_native_local',clock=time.time):
        if not re.fullmatch(r'wsp_[A-Za-z0-9_-]{4,64}',workspace_id):raise WorkflowError('NATIVE_BRIDGE_WORKSPACE_INVALID',400)
        self.store,self.workspace,self.clock=store,workspace_id,clock
        marker=guard(store.root/'.vf-auth-workspace.json')
        if marker.exists() and json.loads(marker.read_bytes())!={'schema':'vf-native-workspace-binding-v1','workspace_id':workspace_id}:
            raise WorkflowError('NATIVE_BRIDGE_WORKSPACE_INVALID',400)
        self.verifier=None;self.identities={};self.signing=None;self.transport=None;self.delivery_enabled=False
        self.intelligence=None
        self.stop=threading.Event();self.worker=None
        with store.transaction() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS native_bridge_nonces (
                    workspace_id TEXT NOT NULL,nonce_sha256 TEXT NOT NULL,expires_at INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id,nonce_sha256));
                CREATE TABLE IF NOT EXISTS native_bridge_requests (
                    workspace_id TEXT NOT NULL,service_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,project_id TEXT NOT NULL,result_json TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,service_id,key_sha256));
                CREATE TABLE IF NOT EXISTS native_bridge_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,
                    workspace_id TEXT NOT NULL,envelope_json TEXT NOT NULL,envelope_sha256 TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS native_bridge_history ON native_bridge_events(workspace_id,sequence);
                CREATE TABLE IF NOT EXISTS native_bridge_deliveries (
                    event_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,mode TEXT NOT NULL,destination_sha256 TEXT,
                    next_at REAL,lease_until REAL,claim_id TEXT,updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS native_bridge_attempts (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL,attempt INTEGER NOT NULL,
                    claim_id TEXT UNIQUE NOT NULL,mode TEXT NOT NULL,key_id TEXT NOT NULL,
                    signed_at INTEGER NOT NULL,body_sha256 TEXT NOT NULL,response_status INTEGER,
                    failure_code TEXT,external_call INTEGER NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS native_bridge_cursors (
                    workspace_id TEXT NOT NULL,source TEXT NOT NULL,sequence INTEGER NOT NULL,
                    PRIMARY KEY(workspace_id,source));
            ''')
            existing={r[0] for r in con.execute('SELECT DISTINCT workspace_id FROM native_bridge_events')}
            if existing and existing!={workspace_id}:raise WorkflowError('NATIVE_BRIDGE_WORKSPACE_INVALID',400)
        store.bridge=self

    def start(self,observer):
        def work():
            while not self.stop.is_set():
                try:
                    self.harvest()
                    if self.process() is not None:continue
                except Exception:observer.emit('worker_failed',stage='bridge',duration=0)
                self.stop.wait(1)
        self.worker=threading.Thread(target=work,daemon=True,name='native-independent-webhook-worker');self.worker.start()

    def close(self):
        self.stop.set()
        if self.worker is not None:self.worker.join(timeout=2)

    def configure_auth(self,identities):
        # This Native data root is a single explicit workspace. A registry entry
        # grants only this workspace's draft/event routes, never human approvals.
        if not identities or any(identity.service_id!=key or identity.roles!=('service',)
            or not identity.keys or any(len(secret)<32 for secret in identity.keys.values()) for key,identity in identities.items()):
            raise WorkflowError('NATIVE_BRIDGE_AUTH_CONFIGURATION_INVALID',400)
        self.identities=dict(identities)
        self.verifier=ServiceAuthVerifier(self.identities,ReplayStore(self),now=self.clock)

    def _registry(self,path):
        path=guard(path,exists=True)
        if self.store.root.absolute() in path.parents or path.stat().st_size>262144:
            raise WorkflowError('NATIVE_BRIDGE_REGISTRY_MUST_BE_OUTSIDE_STATE',400)
        def pairs(items):
            value={}
            for key,child in items:
                if key in value:raise ValueError()
                value[key]=child
            return value
        try:
            with path.open('rb') as file:raw=json.loads(file.read(262145),object_pairs_hook=pairs)
            if not isinstance(raw,dict) or raw.get('version')!=1:raise ValueError()
        except ValueError:raise WorkflowError('NATIVE_BRIDGE_REGISTRY_INVALID',400) from None
        if raw.get('native_workspace_id')!=self.workspace:raise WorkflowError('NATIVE_BRIDGE_WORKSPACE_FORBIDDEN',403)
        return raw

    def load_auth_registry(self,path):
        raw=self._registry(path)
        try:
            identities=raw['service_identities']
            if not isinstance(identities,dict):raise ValueError()
            self.configure_auth({key:ServiceIdentity(key,tuple(value['roles']),_decode_keys(value['keys'])) for key,value in identities.items()})
        except (KeyError,ValueError,TypeError):raise WorkflowError('NATIVE_BRIDGE_AUTH_CONFIGURATION_INVALID',400) from None

    def load_webhook_registry(self,path,*,owner_http_enabled=False):
        raw=self._registry(path)
        destination=raw.get('destination',{})
        transport=HTTPSWebhookTransport(destination.get('endpoint',''),approved_host=destination.get('approved_host',''))
        try:
            signing=raw['webhook_signing'];keyring=SigningKeyring(signing['active_key_id'],_decode_keys(signing['keys']))
        except (ValueError,KeyError,TypeError):raise WorkflowError('NATIVE_BRIDGE_SIGNING_CONFIGURATION_INVALID',400) from None
        self.configure_delivery(transport=transport,signing=keyring,enabled=owner_http_enabled,owner_http_enabled=owner_http_enabled)

    def attach_intelligence(self,store):
        if store.root.absolute()!=self.store.root.absolute():raise WorkflowError('NATIVE_BRIDGE_SOURCE_ROOT_INVALID',400)
        with store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS native_bridge_source_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,workspace_id TEXT NOT NULL,envelope_json TEXT NOT NULL,envelope_sha256 TEXT NOT NULL)')
            if any(row[0]!=self.workspace for row in con.execute('SELECT DISTINCT workspace_id FROM native_bridge_source_events')):
                raise WorkflowError('NATIVE_BRIDGE_WORKSPACE_INVALID',400)
        self.intelligence=store;store.bridge=self

    def capture_intelligence(self,con,kind,value):
        event_type=None;payload={'record_id':value['id'],'record_version':value['version'],'record_sha256':digest(value)}
        if kind=='Opportunity' and value.get('supporting_signals') and value.get('status')=='NEW':
            event_type='trend.opportunity.detected'
            payload.update(signal_count=len(value['supporting_signals']),opportunity_score=value.get('opportunity_score'),
                source_kind='research_heuristic',global_platform_metrics_verified=False)
        elif kind=='ResearchRun' and value.get('status')=='IDEAS':
            event_type='idea.shortlist.ready';payload.update(idea_count=len(value.get('idea_ids',[])),generation=value.get('generation'))
        if event_type:
            envelope=self.envelope(event_type,'intelligence:'+kind+':'+value['id']+':'+str(value['version']),payload,value['updated_at'])
            self.validate(envelope)
            con.execute('INSERT INTO native_bridge_source_events(event_id,workspace_id,envelope_json,envelope_sha256) VALUES(?,?,?,?)',
                (envelope['event_id'],self.workspace,canonical_json_bytes(envelope).decode(),digest(envelope)))

    def harvest(self):
        if self.intelligence is None:return 0
        with self.store.transaction() as con:
            row=con.execute("SELECT sequence FROM native_bridge_cursors WHERE workspace_id=? AND source='intelligence'",(self.workspace,)).fetchone()
            after=row[0] if row else 0
        # Independent DB transactions: source commit remains authoritative. The
        # immutable envelope + cursor commit are atomic in the destination, so
        # interruption repeats the same ID rather than losing or duplicating it.
        with self.intelligence.transaction() as source:
            rows=source.execute('SELECT * FROM native_bridge_source_events WHERE workspace_id=? AND sequence>? ORDER BY sequence LIMIT 50',(self.workspace,after)).fetchall()
        if not rows:return 0
        with self.store.transaction() as con:
            for row in rows:
                self.put(con,self.read_event(row))
            con.execute("INSERT INTO native_bridge_cursors VALUES(?,'intelligence',?) ON CONFLICT(workspace_id,source) DO UPDATE SET sequence=max(sequence,excluded.sequence)",(self.workspace,rows[-1]['sequence']))
        return len(rows)

    def capture_publication(self,con,row,action):
        if action not in ('publication.dry_run.completed','publication.dry_run.blocked'):return
        event_type='video.publish.completed' if action=='publication.dry_run.completed' else 'video.publish.failed'
        current=con.execute('SELECT * FROM native_publications WHERE publication_id=?',(row['publication_id'],)).fetchone()
        payload={'project_id':row['project_id'],'publication_id':row['publication_id'],'publication_snapshot_sha256':current['snapshot_sha256'],
            'publication_status':current['status'],'mock':True,'mode':'dry_run','actual_external_publication':False,'remote_post_id':None,
            'rights_gate_passed_for_real_publishing':False}
        self.put(con,self.envelope(event_type,'publication:'+row['publication_id']+':'+action,payload,current['updated_at']))

    def capture_analytics(self,con,row,action,evidence):
        if action!='analytics.fixture.collected':return
        snapshot=con.execute('SELECT * FROM native_analytics_snapshots WHERE snapshot_id=?',(evidence.get('snapshot_id'),)).fetchone()
        if snapshot is None:raise WorkflowError('NATIVE_BRIDGE_ANALYTICS_EVIDENCE_INVALID')
        value=json.loads(snapshot['snapshot_json'])
        if digest(value)!=snapshot['snapshot_sha256']:raise WorkflowError('NATIVE_BRIDGE_ANALYTICS_EVIDENCE_INVALID')
        payload={'project_id':row['project_id'],'snapshot_id':snapshot['snapshot_id'],'snapshot_sha256':snapshot['snapshot_sha256'],
            'publication_id':row['publication_id'],'mock':value['mock'],'source_kind':value['source_kind'],
            'real_audience_observation':False,'automatic_action':False}
        origin='analytics:'+snapshot['snapshot_id']
        self.put(con,self.envelope('video.analytics.updated',origin,payload,snapshot['collected_at']))
        if value['assessment']['state']=='winner_candidate':
            self.put(con,self.envelope('video.winner.detected',origin,{**payload,'assessment_state':'winner_candidate',
                'basis':value['assessment']['basis'],'channel_baseline_verified':False},snapshot['collected_at']))

    def configure_delivery(self,*,transport,signing,enabled=False,owner_http_enabled=False):
        if type(enabled) is not bool or type(owner_http_enabled) is not bool or not isinstance(signing,SigningKeyring):
            raise WorkflowError('NATIVE_BRIDGE_DELIVERY_CONFIGURATION_INVALID',400)
        if type(transport) not in (FixtureWebhookTransport,HTTPSWebhookTransport):
            raise WorkflowError('NATIVE_BRIDGE_DELIVERY_CONFIGURATION_INVALID',400)
        if transport.mode=='http' and enabled and not owner_http_enabled:
            raise WorkflowError('NATIVE_BRIDGE_OWNER_HTTP_ENABLEMENT_REQUIRED',403)
        if signing.active_key_id not in signing.keys or any(len(value)<32 for value in signing.keys.values()):
            raise WorkflowError('NATIVE_BRIDGE_SIGNING_CONFIGURATION_INVALID',400)
        self.transport,self.signing,self.delivery_enabled=transport,signing,enabled

    def authenticate(self,method,path,query,body,headers):
        if self.verifier is None:raise WorkflowError('NATIVE_BRIDGE_SERVICE_AUTH_NOT_CONFIGURED',503)
        if headers.get(CONTRACT_VERSION_HEADER)!=VERSION:raise WorkflowError('NATIVE_BRIDGE_CONTRACT_REQUIRED',400)
        try:return asyncio.run(self.verifier.verify(method=method,path=path,query=query,body=body,headers=headers))
        except ServiceAuthError as error:raise WorkflowError(error.code,401) from None

    def contract(self):
        return {'contract_version':VERSION,'api_version':'v1','backend':'windows_native',
            'native_dto_version':'native-bridge-draft-v1','service_auth':'hmac-sha256','webhook_auth':'hmac-sha256-keyring',
            'inbound_actions':['project.create_draft'],'outbound_events':list(EVENTS),'execution_boundary':'draft_only',
            'service_auth_configured':self.verifier is not None,'webhook_delivery_enabled':self.delivery_enabled,
            'webhook_mode':self.transport.mode if self.transport else 'disabled','historical_backfill':False,
            'shared_database':False,'shared_redis':False,'agent_hub_runtime_dependency':False,
            'production_deployed':False,'live_publishing_enabled':False}

    def project_summary(self,project_id):
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone();project=self.store.project(row)
            latest=con.execute('SELECT id,kind,status,revision FROM jobs WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 1',(project_id,)).fetchone()
            document=project['document'];timeline=document.get('canonical_timeline')
            return {'contract_version':VERSION,'native_dto_version':'native-project-summary-v1','workspace_id':self.workspace,
                'project_id':project_id,'revision':project['revision'],'document_sha256':digest(document),
                'input_kind':document.get('input_kind'),'niche':document.get('niche'),
                'versions':con.execute('SELECT count(*) FROM project_versions WHERE project_id=?',(project_id,)).fetchone()[0],
                'assets':len(document.get('assets',[])),'canonical_timeline_sha256':timeline.get('sha256') if timeline else None,
                'current_human_approval':project['approval'] is not None and project['approval'].get('revision')==project['revision'],
                'latest_job':dict(latest) if latest else None,'external_action':False,'execution_controlled_by_video_factory':True}

    def draft(self,service,body,request_key):
        if service.service_id not in self.identities or service.roles!=('service',):raise WorkflowError('NATIVE_BRIDGE_SERVICE_FORBIDDEN',403)
        try:request=NativeBridgeDraft.model_validate(body)
        except ValueError:raise WorkflowError('NATIVE_BRIDGE_DRAFT_INVALID',400) from None
        if request.workspace_id!=self.workspace:raise WorkflowError('NATIVE_BRIDGE_WORKSPACE_FORBIDDEN',403)
        if request.start_pipeline or request.publish_requested or request.external_action_requested:
            raise WorkflowError('NATIVE_BRIDGE_DRAFT_ONLY',403)
        if not isinstance(request_key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',request_key):
            raise WorkflowError('NATIVE_BRIDGE_REQUEST_KEY_REQUIRED',400)
        # Do not put prompt/private briefs in exported events or audit records.
        sha=digest(request.model_dump(mode='json'));key=hashlib.sha256(request_key.encode()).hexdigest()
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_bridge_requests WHERE workspace_id=? AND service_id=? AND key_sha256=?',
                (self.workspace,service.service_id,key)).fetchone()
            if old:
                if old['request_sha256']!=sha:raise WorkflowError('NATIVE_BRIDGE_IDEMPOTENCY_CONFLICT',409)
                result=json.loads(old['result_json'])
                if digest(result)!=old['result_sha256']:raise WorkflowError('NATIVE_BRIDGE_REQUEST_EVIDENCE_INVALID')
                history=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=1',(old['project_id'],)).fetchone()
                if (history is None or result.get('document_sha256')!=digest(json.loads(history[0]))
                    or result.get('workspace_id')!=self.workspace or result.get('project_id')!=old['project_id']
                    or result.get('execution_started') is not False or result.get('external_action') is not False):
                    raise WorkflowError('NATIVE_BRIDGE_REQUEST_EVIDENCE_INVALID')
                self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(old['project_id'],)).fetchone())
                return {**result,'idempotent_replay':True}
            profile=None
            if request.channel_profile_ref:
                from .channel_profiles import select
                profile=select(request.channel_profile_ref)
                if profile['profile']['niche_profile']['niche']!=request.niche:raise WorkflowError('NATIVE_BRIDGE_PROFILE_NICHE_CONFLICT',400)
            project=self.store.create_in_transaction(con,request.name,request.prompt,request.input_kind,channel_profile=profile,niche=request.niche)
            row=con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone();document=json.loads(row['document'])
            result={'contract_version':VERSION,'native_dto_version':'native-bridge-draft-v1',
                'workspace_id':self.workspace,'project_id':project,'project_revision':1,'document_sha256':digest(document),
                'execution_started':False,'external_action':False,'approval':None,'idempotent_replay':False}
            con.execute('INSERT INTO native_bridge_requests VALUES(?,?,?,?,?,?,?,?)',
                (self.workspace,service.service_id,key,sha,project,json.dumps(result),digest(result),row['created_at']))
            return result

    def envelope(self,event_type,origin,payload,stamp):
        if event_type not in EVENTS:raise WorkflowError('NATIVE_BRIDGE_EVENT_TYPE_INVALID')
        safe={'workspace_id':self.workspace,'backend':'windows_native','origin_ref':origin,**payload,
            'execution_controlled_by_video_factory':True,'automatic_action':False}
        identity='bevt_'+digest({'workspace':self.workspace,'origin':origin,'type':event_type})[:48]
        return {'contract_version':VERSION,'event_id':identity,'event_type':event_type,'occurred_at':stamp,'payload':safe}

    def validate(self,value):
        try:
            if (not isinstance(value,dict) or set(value)!={'contract_version','event_id','event_type','occurred_at','payload'} or value['contract_version']!=VERSION
                or value['event_type'] not in EVENTS or not isinstance(value['event_id'],str) or not re.fullmatch(r'bevt_[a-f0-9]{48}',value['event_id'])
                or not isinstance(value['payload'],dict) or value['payload'].get('workspace_id')!=self.workspace):raise ValueError()
            stamp=datetime.fromisoformat(value['occurred_at'])
            if stamp.tzinfo is None:raise ValueError()
            origin=value['payload']['origin_ref']
            if value['event_id']!='bevt_'+digest({'workspace':self.workspace,'origin':origin,'type':value['event_type']})[:48]:raise ValueError()
        except (ValueError,TypeError,KeyError):raise WorkflowError('NATIVE_BRIDGE_EVENT_EVIDENCE_INVALID') from None
        self._safe(value)

    def _safe(self,value):
        # All producers use identifiers, hashes, numeric counts and explicit
        # evidence flags. Never pass through draft text, notes, paths or bodies.
        forbidden=('secret','token','password','credential','cookie','api_key','prompt','narration','reviewer','note','path','url')
        def check(item):
            if isinstance(item,dict):
                for key,child in item.items():
                    if any(word in key.lower() for word in forbidden):raise WorkflowError('NATIVE_BRIDGE_PRIVATE_PAYLOAD_REJECTED')
                    check(child)
            elif isinstance(item,list):
                if len(item)>100:raise WorkflowError('NATIVE_BRIDGE_PAYLOAD_TOO_LARGE')
                for child in item:check(child)
            elif isinstance(item,str):
                if len(item)>200 or 'Bearer ' in item or 'sk-' in item:raise WorkflowError('NATIVE_BRIDGE_PRIVATE_PAYLOAD_REJECTED')
            elif item is not None and type(item) not in (int,float,bool):raise WorkflowError('NATIVE_BRIDGE_PAYLOAD_INVALID')
            elif type(item) is float and not math.isfinite(item):raise WorkflowError('NATIVE_BRIDGE_PAYLOAD_INVALID')
        check(value['payload'])
        if len(canonical_json_bytes(value))>32768:raise WorkflowError('NATIVE_BRIDGE_PAYLOAD_TOO_LARGE')

    def put(self,con,value):
        # Validate only pure content; never load signing secrets or contact Hub.
        self.validate(value)
        sha=digest(value);old=con.execute('SELECT * FROM native_bridge_events WHERE event_id=?',(value['event_id'],)).fetchone()
        if old:
            if old['envelope_sha256']!=sha:raise WorkflowError('NATIVE_BRIDGE_IMMUTABLE_EVENT_CONFLICT')
            return
        con.execute('INSERT INTO native_bridge_events(event_id,workspace_id,envelope_json,envelope_sha256) VALUES(?,?,?,?)',
            (value['event_id'],self.workspace,canonical_json_bytes(value).decode(),sha))
        enabled=self.delivery_enabled and self.transport is not None and self.signing is not None
        con.execute('INSERT INTO native_bridge_deliveries VALUES(?,?,?,?,?,?,?,?,?,?)',
            (value['event_id'],self.workspace,'queued' if enabled else 'disabled',0,self.transport.mode if enabled else 'disabled',
                self.destination() if enabled else None,self.clock() if enabled else None,None,None,value['occurred_at']))

    def capture(self,con,project,action,payload,sequence,stamp):
        event_type=None;data={'project_id':project,'source_sequence':sequence}
        row=con.execute('SELECT revision,document FROM projects WHERE id=?',(project,)).fetchone() if project else None
        if row:data.update(project_revision=row['revision'],document_sha256=digest(json.loads(row['document'])))
        if action in ('project_created','project_duplicated_unapproved'):event_type='video.project.created'
        elif action=='human_content_approved':event_type='video.approved'
        elif action in ('draft_saved_approval_invalidated','media_analyzed_approval_invalidated','auto_edit_canonical_timeline_created','auto_edit_canonical_timeline_edited','auto_edit_canonical_timeline_restored'):event_type='video.approval.required'
        elif action=='bridge_preview_ready':
            event_type='video.preview.ready';data.update({k:payload.get(k) for k in ('preview_id','revision','timeline_sha256','artifact_sha256','manifest_sha256','current_revision')})
            data.update(final_approval_eligible=False)
        elif action=='job_finished':
            job=con.execute('SELECT * FROM jobs WHERE id=?',(payload.get('job_id'),)).fetchone()
            if job:
                data.update(job_id=job['id'],job_revision=job['revision'],job_kind=job['kind'],job_status=job['status'],job_snapshot_sha256=digest(json.loads(job['snapshot'])))
                if job['kind']=='render':
                    event_type='video.render.completed' if job['status']=='succeeded' else 'video.render.failed'
                    result=json.loads(job['result']) if job['result'] else None
                    data.update(result_sha256=digest(result) if result else None,owner_final_video_accepted=False)
                elif job['kind']=='content' and job['status']=='awaiting_review':event_type='video.approval.required'
                elif job['kind'] in ('asr','auto_edit_analysis','media_frames') and job['status']=='succeeded':event_type='video.analysis.completed'
        if event_type:self.put(con,self.envelope(event_type,'workflow:'+str(sequence),data,stamp))

    def read_event(self,row):
        value=json.loads(row['envelope_json'])
        if digest(value)!=row['envelope_sha256'] or row['workspace_id']!=self.workspace or value['event_id']!=row['event_id']:
            raise WorkflowError('NATIVE_BRIDGE_EVENT_EVIDENCE_INVALID')
        self.validate(value)
        return value

    def page(self,*,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_BRIDGE_PAGE_INVALID',400)
        after=0
        if cursor:
            try:
                raw=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if len(cursor)>512 or not isinstance(raw,list) or raw[:1]!=[self.workspace] or len(raw)!=2 or type(raw[1]) is not int or raw[1]<1:raise ValueError()
                after=raw[1]
            except (ValueError,TypeError):raise WorkflowError('NATIVE_BRIDGE_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            rows=con.execute('SELECT * FROM native_bridge_events WHERE workspace_id=? AND sequence>? ORDER BY sequence LIMIT ?',
                (self.workspace,after,limit+1)).fetchall();items=[]
            for row in rows[:limit]:
                delivery=dict(con.execute('SELECT * FROM native_bridge_deliveries WHERE event_id=?',(row['event_id'],)).fetchone())
                delivery.pop('claim_id');items.append({'sequence':row['sequence'],'envelope':self.read_event(row),'envelope_sha256':row['envelope_sha256'],'delivery':delivery})
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,rows[limit-1]['sequence']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'contract_version':VERSION,'workspace_id':self.workspace,'items':items,'next_cursor':next_cursor,'delivery_enabled':self.delivery_enabled}

    def destination(self):
        if self.transport is None:return None
        return digest({'mode':self.transport.mode,'endpoint':getattr(self.transport,'endpoint','fixture://in-process')})

    def enqueue(self,event_id):
        if not self.delivery_enabled or self.transport is None or self.signing is None:raise WorkflowError('NATIVE_BRIDGE_DELIVERY_DISABLED',409)
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_bridge_events WHERE event_id=? AND workspace_id=?',(event_id,self.workspace)).fetchone()
            if row is None:raise WorkflowError('NATIVE_BRIDGE_EVENT_NOT_FOUND',404)
            self.read_event(row)
            delivery=con.execute('SELECT * FROM native_bridge_deliveries WHERE event_id=?',(event_id,)).fetchone()
            if delivery['status']!='disabled':return
            con.execute("UPDATE native_bridge_deliveries SET status='queued',mode=?,destination_sha256=?,next_at=?,updated_at=? WHERE event_id=?",
                (self.transport.mode,self.destination(),self.clock(),datetime.now(timezone.utc).isoformat(),event_id))

    def process(self):
        if not self.delivery_enabled or self.transport is None or self.signing is None:return None
        stamp=self.clock();claim=uuid.uuid4().hex
        with self.store.transaction() as con:
            # Interrupted/ambiguous wire attempts reuse the exact event ID and
            # body. Receiver must deduplicate that event ID; delivery is at least once.
            con.execute("UPDATE native_bridge_attempts SET failure_code='NATIVE_BRIDGE_INTERRUPTED_RESPONSE_UNCERTAIN' WHERE claim_id IN (SELECT claim_id FROM native_bridge_deliveries WHERE workspace_id=? AND status='running' AND lease_until<=?) AND response_status IS NULL AND failure_code IS NULL",(self.workspace,stamp))
            con.execute("UPDATE native_bridge_deliveries SET status='retry_scheduled',next_at=?,claim_id=NULL,lease_until=NULL WHERE workspace_id=? AND status='running' AND lease_until<=?",(stamp,self.workspace,stamp))
            row=con.execute("SELECT * FROM native_bridge_deliveries WHERE workspace_id=? AND status IN ('queued','retry_scheduled') AND next_at<=? ORDER BY next_at,event_id LIMIT 1",(self.workspace,stamp)).fetchone()
            if row is None:return None
            if row['mode']!=self.transport.mode or row['destination_sha256']!=self.destination():
                con.execute("UPDATE native_bridge_deliveries SET status='failed' WHERE event_id=?",(row['event_id'],));return row['event_id']
            if row['attempts']>=5:
                con.execute("UPDATE native_bridge_deliveries SET status='failed' WHERE event_id=?",(row['event_id'],));return row['event_id']
            event=con.execute('SELECT * FROM native_bridge_events WHERE event_id=?',(row['event_id'],)).fetchone()
            body=canonical_json_bytes(self.read_event(event));attempt=row['attempts']+1
            headers=self.signing.sign(body,timestamp=int(stamp),event_id=row['event_id'])
            headers.update({'Content-Type':'application/json','Idempotency-Key':row['event_id']})
            con.execute("UPDATE native_bridge_deliveries SET status='running',attempts=?,claim_id=?,lease_until=?,next_at=NULL WHERE event_id=?",(attempt,claim,stamp+120,row['event_id']))
            con.execute('INSERT INTO native_bridge_attempts(event_id,attempt,claim_id,mode,key_id,signed_at,body_sha256,response_status,failure_code,external_call,created_at) VALUES(?,?,?,?,?,?,?,NULL,NULL,?,?)',
                (row['event_id'],attempt,claim,self.transport.mode,self.signing.active_key_id,int(stamp),hashlib.sha256(body).hexdigest(),int(self.transport.external_call),datetime.now(timezone.utc).isoformat()))
        status=None;retry=None;failure=None
        try:
            response=self.transport.send(body,headers)
            if not isinstance(response,BridgeResponse) or type(response.status) is not int or not 100<=response.status<=599:raise ValueError()
            status=response.status;retry=response.retry_after
        except Exception:failure='NATIVE_BRIDGE_TRANSPORT_UNAVAILABLE'
        succeeded=status is not None and 200<=status<300
        retryable=status is None or status in (408,425,429) or status>=500
        next_at=self.clock()+min(3600,max(5*2**(attempt-1),retry or 0)) if retryable and attempt<5 else None
        with self.store.transaction() as con:
            con.execute('UPDATE native_bridge_attempts SET response_status=?,failure_code=? WHERE claim_id=?',(status,failure,claim))
            con.execute('UPDATE native_bridge_deliveries SET status=?,next_at=?,claim_id=NULL,lease_until=NULL,updated_at=? WHERE event_id=? AND claim_id=?',
                ('succeeded' if succeeded else 'retry_scheduled' if next_at is not None else 'failed',next_at,datetime.now(timezone.utc).isoformat(),row['event_id'],claim))
        return row['event_id']

    def audit(self,event_id):
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_bridge_events WHERE event_id=? AND workspace_id=?',(event_id,self.workspace)).fetchone()
            if row is None:raise WorkflowError('NATIVE_BRIDGE_EVENT_NOT_FOUND',404)
            self.read_event(row)
            delivery=dict(con.execute('SELECT * FROM native_bridge_deliveries WHERE event_id=?',(event_id,)).fetchone());delivery.pop('claim_id')
            attempts=[dict(r) for r in con.execute('SELECT * FROM native_bridge_attempts WHERE event_id=? ORDER BY sequence LIMIT 6',(event_id,))]
            return {'contract_version':VERSION,'workspace_id':self.workspace,'event_id':event_id,'delivery':delivery,'attempts':attempts,
                'real_hub_receipt_verified':False,'http_response_accepted':delivery['mode']=='http' and delivery['status']=='succeeded',
                'fixture':delivery['mode']=='fixture'}
