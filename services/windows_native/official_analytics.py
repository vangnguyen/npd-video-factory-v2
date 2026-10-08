"""Receipt-bound, finite, read-only YouTube analytics with immutable observations.

No credential acquisition, publishing operation, fixture fallback, or recurring plan.
The default operator gate is off. Protocol mocks remain non-audience observations.
"""
import asyncio
import base64
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError
from .contracts import WorkflowError, digest
from .costs import CostLedger
from .official_analytics_models import Collect, Cancel
from .official_publications import NativeOfficialPublications, utc
from .official_account_registry import AccountFactory
from .analytics_features import capture
from .store import now
from app.analytics_models import NormalizedMetrics, VideoFeatureMetadata
from app.analytics_official import (AnalyticsOfficialError, AnalyticsRateLimited, account_request,
    confirm_account, youtube_video_request, confirm_youtube_video, youtube_report_request,
    youtube_metrics, response_digest, YT_MAPPING, resolve_credential)
from app.publishing_wire import PublishingWireError
from app.publishing_models import PublishingTargetBinding
from app.publishing_credentials import target_digest


TABLES = ('native_official_analytics_syncs', 'native_official_analytics_attempts',
    'native_official_analytics_responses', 'native_official_analytics_snapshots', 'native_official_analytics_events')


def typed(value, cls):
    try:
        if type(value) is not cls:
            raise TypeError()
        return cls.model_validate(value.model_dump(mode='python', warnings=False))
    except (TypeError, ValidationError):
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_FIELDS_INVALID', 400) from None


class NativeOfficialAnalytics:
    def __init__(self, publications, *, enabled=False):
        if type(publications) is not NativeOfficialPublications or type(enabled) is not bool:
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CONFIGURATION_INVALID', 400)
        self.publications = publications
        self.accounts, self.store, self.workspace, self.clock = publications.accounts, publications.store, publications.workspace, publications.clock
        self.enabled = self.frozen_enabled = enabled
        self.frozen = (publications, self.accounts, self.store, self.workspace, self.clock, self.store.root.absolute())
        self.costs = CostLedger(self.store)
        self.frozen_costs = self.costs
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_official_analytics_syncs (
                sync_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,publication_id TEXT NOT NULL,
                key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,
                status TEXT NOT NULL,attempts INTEGER NOT NULL,claim_id TEXT,next_at TEXT,failure_code TEXT,result_snapshot_id TEXT,
                actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
                CREATE TABLE IF NOT EXISTS native_official_analytics_attempts (
                attempt_id TEXT PRIMARY KEY,sync_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                snapshot_sha256 TEXT NOT NULL,ordinal INTEGER NOT NULL,status TEXT NOT NULL,failure_code TEXT,
                created_at TEXT NOT NULL,finished_at TEXT,UNIQUE(sync_id,ordinal));
                CREATE TABLE IF NOT EXISTS native_official_analytics_responses (
                response_id TEXT PRIMARY KEY,attempt_id TEXT NOT NULL,sync_id TEXT NOT NULL,workspace_id TEXT NOT NULL,
                project_id TEXT NOT NULL,operation TEXT NOT NULL,response_sha256 TEXT NOT NULL,summary_sha256 TEXT NOT NULL,
                summary_json TEXT NOT NULL,cost_operation_id TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(attempt_id,operation));
                CREATE TABLE IF NOT EXISTS native_official_analytics_snapshots (
                result_snapshot_id TEXT PRIMARY KEY,sync_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                publication_id TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,result_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,collected_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS native_official_analytics_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,sync_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_official_analytics_syncs WHERE workspace_id!=? LIMIT 1', (self.workspace,)).fetchone():
                raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_WORKSPACE_CHANGED')

    def check(self):
        if (self.enabled is not self.frozen_enabled or type(self.enabled) is not bool
            or self.costs is not self.frozen_costs or self.costs.store is not self.store
            or (self.publications, self.accounts, self.store, self.workspace, self.clock, self.store.root.absolute()) != self.frozen):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CONFIGURATION_CHANGED')
        self.accounts.check_workspace()

    def states(self):
        self.check()
        return {'schema_version': 'native-official-analytics-capabilities-v1', 'workspace_id': self.workspace,
            'enabled': self.enabled, 'default_enabled': False, 'supported_platforms': ['youtube'],
            'accounts': [f.public() for _, f in sorted(self.accounts.factories.items()) if f.account.target.platform == 'youtube'],
            'separate_read_consent_required': True, 'automatic_refresh': False, 'publishing_enabled': False,
            'fixture_fallback': False, 'real_provider_tested': False, 'token_returned': False}

    def identity(self, principal=None, *, authority=None):
        try:
            current = self.publications.identity(principal, **({'token_id': authority['token_id'], 'subject': authority['subject']} if authority else {}))
        except WorkflowError:
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CURRENT_OWNER_REQUIRED', 403) from None
        if authority is not None and current != authority:
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_OWNER_CHANGED', 403)
        return current

    def event(self, con, row, action, actor, **evidence):
        con.execute('INSERT INTO native_official_analytics_events(sync_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
            (row['sync_id'], self.workspace, row['project_id'], action, actor, json.dumps(evidence), now()))

    def row(self, con, project, identity):
        self.check()
        if con.execute('SELECT 1 FROM projects WHERE id=?', (project,)).fetchone() is None:
            raise WorkflowError('PROJECT_NOT_FOUND', 404)
        row = con.execute('SELECT * FROM native_official_analytics_syncs WHERE sync_id=? AND workspace_id=? AND project_id=?', (identity, self.workspace, project)).fetchone()
        if row is None:
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_NOT_FOUND', 404)
        return row

    def source(self, project, request, stamp, *, con=None):
        from contextlib import nullcontext
        publication = self.publications.get(project, request.publication_id, con=con)
        receipt, snapshot = publication['receipt'], publication['snapshot']
        if (publication['status'] != 'completed' or receipt is None
            or publication['snapshot_sha256'] != request.expected_publication_snapshot_sha256
            or digest(receipt) != request.expected_receipt_sha256):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_QUALIFIED_RECEIPT_REQUIRED')
        with (self.store.transaction() if con is None else nullcontext(con)) as con:
            parent = self.publications.publications.read(self.publications.publications.get_row(con, project, snapshot['request']['dry_run_publication_id']))
            job = self.store.job(con.execute('SELECT * FROM jobs WHERE id=? AND project_id=?', (snapshot['final_job_id'], project)).fetchone(), con)
            if (parent['snapshot_sha256'] != snapshot['dry_run_snapshot_sha256'] or parent['status'] != 'dry_run_succeeded'
                or digest(job['snapshot']) != snapshot['final_job_snapshot_sha256'] or job['status'] != 'succeeded'
                or job['result']['qc']['final_sha256'] != snapshot['final_sha256']):
                raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PUBLISHED_SOURCE_CHANGED')
            features = capture(parent, job, stamp)
        features.update(publication_id=publication['publication_id'], feature_snapshot_id='noftr_'+digest([publication['publication_id'], publication['snapshot_sha256']])[:32])
        features['evidence'].update(publication_snapshot_sha256=publication['snapshot_sha256'], source_is_dry_run=False,
            official_receipt_sha256=digest(receipt), publication_protocol_mock=publication['mock'])
        features = VideoFeatureMetadata.model_validate(features).model_dump(mode='json')
        return publication, {'publication_snapshot_sha256': publication['snapshot_sha256'], 'receipt_sha256': digest(receipt),
            'dry_run_snapshot_sha256': parent['snapshot_sha256'], 'job_snapshot_sha256': digest(job['snapshot']),
            'job_result_sha256': digest(job['result']), 'final_sha256': snapshot['final_sha256'], 'features': features,
            'remote_post_id':receipt['remote_post_id'],'receipt_mock':publication['mock']}

    def read(self, row):
        value = dict(row)
        try:
            snapshot = json.loads(value.pop('snapshot_json'))
            request = Collect.model_validate({**snapshot['request'], 'request_key': 'internal-official-analytics-key'})
            target = PublishingTargetBinding.model_validate(snapshot['target'])
            features = VideoFeatureMetadata.model_validate(snapshot['source']['features'])
            created, deadline = utc(datetime.fromisoformat(snapshot['consented_at'])), utc(datetime.fromisoformat(snapshot['deadline']))
            if (digest(snapshot) != value['snapshot_sha256'] or snapshot['schema_version'] != 'native-official-analytics-consent-v1'
                or any(snapshot[k] != value[k] for k in ('workspace_id', 'project_id', 'publication_id')) or value['workspace_id'] != self.workspace
                or request.publication_id != value['publication_id'] or digest(snapshot['request']) != value['request_fingerprint']
                or snapshot['account_ref'] != request.account_ref or snapshot['configuration_sha256'] != request.expected_configuration_sha256
                or snapshot['source']['publication_snapshot_sha256'] != request.expected_publication_snapshot_sha256
                or snapshot['source']['receipt_sha256'] != request.expected_receipt_sha256 or target.workspace_id != self.workspace
                or target.platform != 'youtube' or target.provider_key != 'youtube-data-api-publishing' or target_digest(target) != snapshot['target_binding_sha256']
                or type(snapshot['mock']) is not bool or request.acknowledged_protocol_mock is not snapshot['mock']
                or features.project_id != value['project_id'] or features.publication_id != value['publication_id']
                or features.publishing_time is not None or features.evidence['source_is_dry_run'] is not False
                or features.evidence['publication_protocol_mock'] is not snapshot['mock']
                or snapshot['source']['receipt_mock'] is not snapshot['mock'] or not re.fullmatch(r'[A-Za-z0-9_-]{11}',snapshot['source']['remote_post_id'])
                or snapshot['publishing_authority'] is not False or snapshot['recurring_authority'] is not False
                or deadline != min(created+timedelta(seconds=request.valid_for_seconds), utc(datetime.fromisoformat(snapshot['authority']['expires_at'])))
                or deadline <= created or type(value['attempts']) is not int or not 0 <= value['attempts'] <= request.max_attempts
                or value['status'] not in {'not_configured','queued','running','retry_scheduled','succeeded','failed','cancelled','outcome_unknown'}
                or (value['status'] == 'running') != (value['claim_id'] is not None)
                or (value['status'] == 'succeeded') != (value['result_snapshot_id'] is not None)):
                raise ValueError()
            for name in ('publication_snapshot_sha256','receipt_sha256','dry_run_snapshot_sha256','job_snapshot_sha256','job_result_sha256','final_sha256'):
                if not re.fullmatch(r'[a-f0-9]{64}', snapshot['source'][name]): raise ValueError()
            if (value['status']=='retry_scheduled') != (value['next_at'] is not None):raise ValueError()
            if value['next_at'] is not None and not created < utc(datetime.fromisoformat(value['next_at'])) < deadline:raise ValueError()
            value.pop('key_sha256'); value.pop('claim_id')
            return {**value, 'schema_version': 'native-official-analytics-sync-v1', 'snapshot': snapshot,
                'mock': snapshot['mock'], 'publishing_enabled': False, 'token_returned': False, 'real_provider_tested': False}
        except (ValueError, TypeError, KeyError):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_EVIDENCE_CHANGED') from None

    def create(self, project, payload, *, principal):
        self.check(); payload = typed(payload, Collect); authority = self.identity(principal)
        request = payload.model_dump(mode='json', exclude={'request_key'}); key, fp = digest(payload.request_key), digest(request)
        with self.store.transaction() as con:
            prior = con.execute('SELECT * FROM native_official_analytics_syncs WHERE workspace_id=? AND project_id=? AND key_sha256=?', (self.workspace, project, key)).fetchone()
            if prior:
                if prior['request_fingerprint'] != fp: raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_IDEMPOTENCY_CONFLICT')
                return self.read(prior), True
        instant = utc(self.clock()); publication, source = self.source(project, payload, instant.isoformat())
        factory = self.accounts.factories.get(payload.account_ref)
        if type(factory) is not AccountFactory: raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_ACCOUNT_NOT_CONFIGURED')
        public = factory.public()
        if (public['target'] != publication['snapshot']['target'] or factory.sha256 != payload.expected_configuration_sha256
            or factory.client.mock is not publication['mock'] or payload.acknowledged_protocol_mock is not publication['mock']):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_ACCOUNT_BINDING_CHANGED')
        deadline = min(instant+timedelta(seconds=payload.valid_for_seconds), utc(datetime.fromisoformat(authority['expires_at'])))
        snapshot = {'schema_version': 'native-official-analytics-consent-v1', 'workspace_id': self.workspace, 'project_id': project,
            'publication_id': payload.publication_id, 'account_ref': payload.account_ref, 'request': request, 'authority': authority,
            'source': source, 'target': public['target'], 'target_binding_sha256': public['target_binding_sha256'],
            'configuration_sha256': factory.sha256, 'mock': publication['mock'], 'consented_at': instant.isoformat(),
            'deadline': deadline.isoformat(), 'publishing_authority': False, 'recurring_authority': False}
        status = 'queued' if self.enabled and public['status'] == 'CONFIGURED' else 'not_configured'
        identity, stamp = 'noas_'+uuid.uuid4().hex, now()
        with self.store.transaction() as con:
            # Race-safe exact-key replay after the source reads, before journal insertion.
            prior = con.execute('SELECT * FROM native_official_analytics_syncs WHERE workspace_id=? AND project_id=? AND key_sha256=?', (self.workspace, project, key)).fetchone()
            if prior:
                if prior['request_fingerprint'] != fp: raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_IDEMPOTENCY_CONFLICT')
                return self.read(prior), True
            self.identity(authority=authority)
            con.execute('INSERT INTO native_official_analytics_syncs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,payload.publication_id,key,fp,digest(snapshot),json.dumps(snapshot),status,0,None,None,
                 'NATIVE_OFFICIAL_ANALYTICS_READ_NOT_CONFIGURED' if status=='not_configured' else None,None,authority['token_id'],stamp,stamp))
            row = self.row(con, project, identity); self.event(con, row, 'analytics.official.read.created', authority['token_id'], status=status, mock=snapshot['mock'], external_call=False)
            return self.read(row), False

    def get(self, project, identity, *, con=None):
        from contextlib import nullcontext
        with (self.store.transaction() if con is None else nullcontext(con)) as con:
            value = self.read(self.row(con, project, identity))
            value['result'] = self.result(con, value) if value['result_snapshot_id'] else None
            return value

    def admission(self, project, identity, claim):
        self.check()
        with self.store.transaction() as con:
            row = self.row(con, project, identity); value = self.read(row)
            if row['status'] != 'running' or row['claim_id'] != claim:
                raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CLAIM_STOPPED')
        snapshot = value['snapshot']; self.identity(authority=snapshot['authority'])
        if (not self.enabled or utc(self.clock()) >= utc(datetime.fromisoformat(snapshot['deadline']))
            or utc(self.clock()) < utc(datetime.fromisoformat(snapshot['consented_at']))):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_READ_CONSENT_EXPIRED')
        request = Collect.model_validate({**snapshot['request'], 'request_key': 'internal-official-analytics-key'})
        _, source = self.source(project, request, snapshot['consented_at'])
        factory = self.accounts.factories.get(request.account_ref)
        if (source != snapshot['source'] or type(factory) is not AccountFactory or factory.public()['status'] != 'CONFIGURED'
            or factory.sha256 != snapshot['configuration_sha256'] or factory.account.target.model_dump(mode='json') != snapshot['target']
            or factory.client.mock is not snapshot['mock']):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CURRENT_BINDING_REQUIRED')
        return value, request, factory

    def local_fence(self, con, value, claim):
        """Recheck frozen source and consent inside the same write transaction."""
        row=self.row(con,value['project_id'],value['sync_id']);snapshot=value['snapshot'];source=snapshot['source']
        if row['status']!='running' or row['claim_id']!=claim or row['snapshot_sha256']!=value['snapshot_sha256']:
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CLAIM_STOPPED')
        self.identity(authority=snapshot['authority'])
        if not self.enabled or not utc(datetime.fromisoformat(snapshot['consented_at']))<=utc(self.clock())<utc(datetime.fromisoformat(snapshot['deadline'])):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_READ_CONSENT_EXPIRED')
        factory=self.accounts.factories.get(snapshot['account_ref'])
        if (type(factory) is not AccountFactory or factory.public()['status']!='CONFIGURED' or factory.sha256!=snapshot['configuration_sha256']
            or factory.account.target.model_dump(mode='json')!=snapshot['target'] or factory.client.mock is not snapshot['mock']):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CURRENT_BINDING_REQUIRED')
        publication=self.publications.read(self.publications.row(con,value['project_id'],value['publication_id']))
        receipt=con.execute('SELECT * FROM native_official_publish_receipts WHERE publication_id=?',(value['publication_id'],)).fetchone()
        dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(value['publication_id'],)).fetchone()
        parent=self.publications.publications.read(self.publications.publications.get_row(con,value['project_id'],publication['snapshot']['request']['dry_run_publication_id']))
        job=self.store.job(con.execute('SELECT * FROM jobs WHERE id=? AND project_id=?',(publication['snapshot']['final_job_id'],value['project_id'])).fetchone(),con)
        if (publication['status']!='completed' or publication['snapshot_sha256']!=source['publication_snapshot_sha256']
            or receipt is None or any(receipt[k]!=value[k] for k in ('workspace_id','project_id'))
            or receipt['snapshot_sha256']!=source['publication_snapshot_sha256'] or receipt['receipt_sha256']!=source['receipt_sha256']
            or digest(json.loads(receipt['receipt_json']))!=source['receipt_sha256'] or dispatch is None
            or any(dispatch[k]!=value[k] for k in ('workspace_id','project_id')) or dispatch['snapshot_sha256']!=source['publication_snapshot_sha256']
            or dispatch['approval_id']!=publication['approval_id'] or dispatch['phase']!='uploaded' or dispatch['acknowledged_bytes']!=dispatch['total_bytes']
            or dispatch['remote_post_id']!=source['remote_post_id'] or parent['snapshot_sha256']!=source['dry_run_snapshot_sha256']
            or parent['status']!='dry_run_succeeded' or job['status']!='succeeded' or digest(job['snapshot'])!=source['job_snapshot_sha256']
            or digest(job['result'])!=source['job_result_sha256']):raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PUBLISHED_SOURCE_CHANGED')
        return row

    def claim(self):
        self.check()
        if not self.enabled: return None
        with self.store.transaction() as con:
            rows = con.execute("SELECT * FROM native_official_analytics_syncs WHERE workspace_id=? AND status IN ('queued','retry_scheduled') ORDER BY created_at,sync_id", (self.workspace,)).fetchall()
            for row in rows:
                value = self.read(row); instant = utc(self.clock()); deadline = utc(datetime.fromisoformat(value['snapshot']['deadline']))
                if instant >= deadline:
                    con.execute("UPDATE native_official_analytics_syncs SET status='failed',next_at=NULL,failure_code='NATIVE_OFFICIAL_ANALYTICS_READ_CONSENT_EXPIRED',updated_at=? WHERE sync_id=?", (now(),row['sync_id']))
                    self.event(con,row,'analytics.official.read.expired','worker',external_call=False); continue
                if row['next_at'] and utc(datetime.fromisoformat(row['next_at'])) > instant: continue
                claim, stamp, ordinal = 'noaa_'+uuid.uuid4().hex, now(), row['attempts']+1
                if ordinal > value['snapshot']['request']['max_attempts']: raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_ATTEMPT_LIMIT')
                con.execute("UPDATE native_official_analytics_syncs SET status='running',attempts=?,claim_id=?,next_at=NULL,updated_at=? WHERE sync_id=?", (ordinal,claim,stamp,row['sync_id']))
                con.execute('INSERT INTO native_official_analytics_attempts VALUES(?,?,?,?,?,?,?,?,?,?)', (claim,row['sync_id'],self.workspace,row['project_id'],row['snapshot_sha256'],ordinal,'running',None,stamp,None))
                self.event(con,row,'analytics.official.read.claimed','worker',attempt_id=claim,ordinal=ordinal,external_call=False)
                return row['project_id'], row['sync_id'], claim
        return None

    def fetch(self, project, identity, claim, operation, builder, parser):
        value, request, factory = self.admission(project, identity, claim)
        credential = factory.credential(request.query, now=self.clock()); wire_request = builder(credential)
        cost = self.costs.begin(project_id=project, provider='official-youtube-analytics', model=None,
            operation='analytics_read.'+claim+'.'+operation,
            request_sha256=digest({'sync_id':identity,'snapshot_sha256':value['snapshot_sha256'],'attempt_id':claim,'operation':operation}),
            estimated_cost=None, external_call=not factory.client.mock, paid=False)
        sent = False
        try:
            self.admission(project, identity, claim)
            # Resolve afresh after the final local fence; no cached bearer survives expiry.
            fresh = factory.credential(request.query, now=self.clock())
            if fresh != credential: raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CREDENTIAL_CHANGED')
            self.admission(project,identity,claim)
            resolve_credential(lambda _:fresh,factory.account.target,request.query,now=self.clock())
            sent = True; response = asyncio.run(factory.client.request(wire_request))
            self.costs.settle(cost, status='response_received', response_sha256=response_digest(response))
            summary = parser(response, credential, request)
            self.admission(project, identity, claim)
            response_id = 'noar_'+uuid.uuid4().hex
            summary = {'schema_version':'native-official-analytics-response-v1','operation':operation,'mock':value['mock'],
                'external_call':not value['mock'],'read_only':True,'response_status':response.status,'evidence':summary}
            with self.store.transaction() as con:
                self.local_fence(con,value,claim)
                con.execute('INSERT INTO native_official_analytics_responses VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (response_id,claim,identity,self.workspace,project,operation,response_digest(response),digest(summary),json.dumps(summary),cost,now()))
            return response_id, summary['evidence']
        except Exception as error:
            with self.store.transaction() as con: prior = con.execute('SELECT status FROM native_cost_operations WHERE id=?', (cost,)).fetchone()
            if prior['status'] == 'dispatch_intent':
                code = error.code if isinstance(error,(WorkflowError,AnalyticsOfficialError,PublishingWireError)) else 'NATIVE_OFFICIAL_ANALYTICS_READ_FAILED'
                self.costs.settle(cost,status='outcome_unknown' if sent else 'rejected',error_code=code)
            raise

    def process(self):
        claimed = self.claim()
        if claimed is None: return None
        project, identity, claim = claimed
        try:
            value, request, _ = self.admission(project, identity, claim)
            remote = value['snapshot']['source']['remote_post_id']
            account_id, _ = self.fetch(project,identity,claim,'account_lookup',account_request,lambda response,credential,_:confirm_account(response,credential.target))
            video_id, _ = self.fetch(project,identity,claim,'video_ownership',lambda credential:youtube_video_request(credential,remote),
                lambda response,credential,_: self.video_proof(response,credential.target,remote))
            report_id, report = self.fetch(project,identity,claim,'report',lambda credential:youtube_report_request(credential,remote,request.query),
                lambda response,_,payload:self.metrics_report(response,payload.query))
            value, _, _ = self.admission(project, identity, claim)
            result_id, stamp = 'noam_'+uuid.uuid4().hex, utc(self.clock()).isoformat()
            result = {'schema_version':'native-official-analytics-snapshot-v1','result_snapshot_id':result_id,'sync_id':identity,
                'workspace_id':self.workspace,'project_id':project,'publication_id':request.publication_id,'snapshot_sha256':value['snapshot_sha256'],
                'platform':'youtube','provider_key':'youtube-analytics-api','source_kind':'official_protocol_mock' if value['mock'] else 'official_provider',
                'mock':value['mock'],'external_call':not value['mock'],'real_audience_observation':not value['mock'],
                'metrics':report['metrics'],'evidence':report['evidence'],'features':value['snapshot']['source']['features'],
                'publication_receipt_sha256':request.expected_receipt_sha256,'remote_post_id':remote,'response_refs':[account_id,video_id,report_id],
                'attempt_id':claim,'collected_at':stamp,'publishing_time':None,'automatic_action':False,'real_provider_tested':False}
            with self.store.transaction() as con:
                row=self.local_fence(con,value,claim)
                con.execute('INSERT INTO native_official_analytics_snapshots VALUES(?,?,?,?,?,?,?,?,?)',
                    (result_id,identity,self.workspace,project,request.publication_id,value['snapshot_sha256'],digest(result),json.dumps(result),stamp))
                con.execute("UPDATE native_official_analytics_attempts SET status='succeeded',finished_at=? WHERE attempt_id=?",(stamp,claim))
                con.execute("UPDATE native_official_analytics_syncs SET status='succeeded',claim_id=NULL,result_snapshot_id=?,failure_code=NULL,updated_at=? WHERE sync_id=?",(result_id,now(),identity))
                self.event(con,row,'analytics.official.collected','worker',result_snapshot_id=result_id,mock=value['mock'],external_call=not value['mock'])
                bridge=getattr(self.store,'bridge',None)
                if bridge is not None:bridge.capture_qualified(con,'analytics',self,project,identity)
        except Exception as error:
            self.failure(project,identity,claim,error)
        return self.get(project, identity)

    @staticmethod
    def video_proof(response, target, remote):
        confirm_youtube_video(response,target,remote)
        return {'video_ownership_confirmed':True,'remote_post_id':remote,'target_binding_sha256':target_digest(target)}

    @staticmethod
    def metrics_report(response, query):
        metrics,evidence=youtube_metrics(response,query)
        return {'metrics':metrics.model_dump(mode='json'),'evidence':evidence}

    def failure(self, project, identity, claim, error):
        code = error.code if isinstance(error,(WorkflowError,AnalyticsOfficialError,PublishingWireError)) else 'NATIVE_OFFICIAL_ANALYTICS_COLLECTION_FAILED'
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(row);due=None;status='failed'
            if isinstance(error,AnalyticsRateLimited):
                code='NATIVE_OFFICIAL_ANALYTICS_PROVIDER_BACKOFF'
                due=(utc(self.clock())+timedelta(seconds=max(error.retry_after_seconds,min(3600,30*2**(row['attempts']-1))))).isoformat()
                if row['attempts']<value['snapshot']['request']['max_attempts'] and utc(datetime.fromisoformat(due))<utc(datetime.fromisoformat(value['snapshot']['deadline'])):
                    status='retry_scheduled'
                else:due=None
            elif code=='PUBLISHING_NETWORK_OUTCOME_UNKNOWN':status='outcome_unknown'
            con.execute('UPDATE native_official_analytics_attempts SET status=?,failure_code=?,finished_at=? WHERE attempt_id=? AND status=\'running\'',(status,code,now(),claim))
            if row['status']=='running' and row['claim_id']==claim:
                con.execute('UPDATE native_official_analytics_syncs SET status=?,claim_id=NULL,next_at=?,failure_code=?,updated_at=? WHERE sync_id=?',(status,due,code,now(),identity))
                self.event(con,row,'analytics.official.read.stopped','worker',status=status,failure_code=code,automatic_retry=status=='retry_scheduled')

    def result(self, con, value):
        try:
            row=con.execute('SELECT * FROM native_official_analytics_snapshots WHERE result_snapshot_id=?',(value['result_snapshot_id'],)).fetchone()
            if row is None: raise ValueError()
            result=json.loads(row['result_json']);metrics=NormalizedMetrics.model_validate(result['metrics'])
            if (digest(result)!=row['result_sha256'] or result['schema_version']!='native-official-analytics-snapshot-v1'
                or any(row[k]!=value[k] or result[k]!=value[k] for k in ('sync_id','workspace_id','project_id','publication_id','snapshot_sha256'))
                or result['result_snapshot_id']!=row['result_snapshot_id'] or result['collected_at']!=row['collected_at']
                or datetime.fromisoformat(result['collected_at']).tzinfo is None or result['mock'] is not value['mock']
                or result['external_call'] is not (not value['mock']) or result['real_audience_observation'] is not (not value['mock'])
                or result['source_kind']!=('official_protocol_mock' if value['mock'] else 'official_provider')
                or result['platform']!='youtube' or result['provider_key']!='youtube-analytics-api'
                or result['features']!=value['snapshot']['source']['features'] or result['publishing_time'] is not None
                or result['automatic_action'] is not False or result['real_provider_tested'] is not False
                or result['publication_receipt_sha256']!=value['snapshot']['request']['expected_receipt_sha256']
                or result['remote_post_id']!=value['snapshot']['source']['remote_post_id']
                or len(result['response_refs'])!=3 or len(set(result['response_refs']))!=3
                or any(getattr(metrics,k) is not None for k in ('impressions','reach','completion_rate','saves','clicks','ctr','rpm','observation_window_hours'))):raise ValueError()
            attempt=con.execute('SELECT * FROM native_official_analytics_attempts WHERE attempt_id=?',(result['attempt_id'],)).fetchone()
            if attempt is None or attempt['status']!='succeeded' or any(attempt[k]!=value[k] for k in ('sync_id','workspace_id','project_id','snapshot_sha256')):raise ValueError()
            for response_id,operation in zip(result['response_refs'],('account_lookup','video_ownership','report')):
                response=con.execute('SELECT * FROM native_official_analytics_responses WHERE response_id=?',(response_id,)).fetchone()
                if response is None or response['attempt_id']!=result['attempt_id'] or response['operation']!=operation or any(response[k]!=value[k] for k in ('sync_id','workspace_id','project_id')):raise ValueError()
                summary=json.loads(response['summary_json'])
                if (digest(summary)!=response['summary_sha256'] or summary['schema_version']!='native-official-analytics-response-v1'
                    or summary['operation']!=operation or summary['mock'] is not value['mock'] or summary['external_call'] is not (not value['mock'])
                    or summary['read_only'] is not True or type(summary['response_status']) is not int or summary['response_status']!=200
                    or not re.fullmatch(r'[a-f0-9]{64}',response['response_sha256'])):raise ValueError()
                evidence=summary['evidence'];binding=value['snapshot']['target_binding_sha256']
                if operation=='account_lookup' and (evidence['account_match'] is not True or evidence['target_binding_sha256']!=binding):raise ValueError()
                if operation=='video_ownership' and (evidence['video_ownership_confirmed'] is not True or evidence['target_binding_sha256']!=binding or evidence['remote_post_id']!=result['remote_post_id']):raise ValueError()
                if operation=='report' and (evidence['metrics']!=result['metrics'] or evidence['evidence']!=result['evidence']):raise ValueError()
                cost=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(response['cost_operation_id'],)).fetchone()
                if (cost is None or cost['project_id']!=value['project_id'] or cost['provider']!='official-youtube-analytics'
                    or cost['operation']!='analytics_read.'+result['attempt_id']+'.'+operation or cost['paid']!=0
                    or cost['external_call']!=int(not value['mock']) or cost['status']!='response_received'
                    or cost['request_sha256']!=digest({'sync_id':value['sync_id'],'snapshot_sha256':value['snapshot_sha256'],'attempt_id':result['attempt_id'],'operation':operation})
                    or json.loads(cost['receipt'])['provider_response_sha256']!=response['response_sha256']):raise ValueError()
            report=result['evidence'];query=value['snapshot']['request']['query']
            if (report['query']!=query or report['coverage_end_date'] is not None or report['observed_window_hours'] is not None
                or report['completion_rate_supported'] is not False or report['rpm_derived'] is not False
                or type(report['row_count']) is not int or report['row_count'] not in (0,1)
                or report['currency']!=('VND' if query['include_revenue'] else None)
                or report['revenue_basis']!=('provider_estimate' if query['include_revenue'] else None)
                or report['watch_time_conversion']!='minutes * 60'
                or report['metric_mapping']!={**YT_MAPPING,**({'estimatedRevenue':'revenue'} if query['include_revenue'] else {})}
                or (not query['include_revenue'] and metrics.revenue is not None)
                or (report['row_count']==0 and any(v is not None for v in result['metrics'].values()))):raise ValueError()
            return result
        except (ValueError,TypeError,KeyError):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_RESULT_CHANGED') from None

    def cancel(self, project, identity, payload, *, principal):
        payload=typed(payload,Cancel);authority=self.identity(principal)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(row)
            if payload.expected_snapshot_sha256!=value['snapshot_sha256']:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_BINDING_CHANGED')
            if row['status'] not in {'succeeded','cancelled'}:
                if row['claim_id']:
                    con.execute("UPDATE native_official_analytics_attempts SET status='cancelled',finished_at=? WHERE attempt_id=? AND status='running'",(now(),row['claim_id']))
                con.execute("UPDATE native_official_analytics_syncs SET status='cancelled',claim_id=NULL,next_at=NULL,updated_at=? WHERE sync_id=?",(now(),identity))
                self.event(con,row,'analytics.official.read.cancelled',authority['token_id'],external_call=False,remote_action=False)
        return self.get(project,identity)

    def recover(self):
        self.check();count=0;costs=[]
        with self.store.transaction() as con:
            for row in con.execute("SELECT * FROM native_official_analytics_syncs WHERE workspace_id=? AND status='running'",(self.workspace,)).fetchall():
                self.read(row);code='NATIVE_OFFICIAL_ANALYTICS_RESTART_REVIEW_REQUIRED'
                con.execute("UPDATE native_official_analytics_attempts SET status='outcome_unknown',failure_code=?,finished_at=? WHERE attempt_id=? AND status='running'",(code,now(),row['claim_id']))
                con.execute("UPDATE native_official_analytics_syncs SET status='outcome_unknown',claim_id=NULL,next_at=NULL,failure_code=?,updated_at=? WHERE sync_id=?",(code,now(),row['sync_id']))
                self.event(con,row,'analytics.official.read.interrupted','recovery',automatic_retry=False,external_call=False);count+=1
            # A crash after journal recovery but before cost settlement must remain recoverable.
            for attempt in con.execute("SELECT a.* FROM native_official_analytics_attempts a JOIN native_official_analytics_syncs s ON s.sync_id=a.sync_id AND s.project_id=a.project_id AND s.workspace_id=a.workspace_id AND s.snapshot_sha256=a.snapshot_sha256 WHERE a.workspace_id=? AND a.status IN ('outcome_unknown','cancelled')",(self.workspace,)).fetchall():
                if not re.fullmatch(r'noaa_[a-f0-9]{32}',attempt['attempt_id']):raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_EVIDENCE_CHANGED')
                costs.extend(cost['id'] for cost in con.execute("SELECT * FROM native_cost_operations WHERE project_id=? AND provider='official-youtube-analytics' AND paid=0 AND status='dispatch_intent' AND operation IN (?,?,?)",
                    (attempt['project_id'],*('analytics_read.'+attempt['attempt_id']+'.'+op for op in ('account_lookup','video_ownership','report')))).fetchall())
        for cost in costs:self.costs.settle(cost,status='outcome_unknown',error_code='NATIVE_OFFICIAL_ANALYTICS_RESTART_REVIEW_REQUIRED')
        return {'recovered':count,'unfinished_costs_marked_unknown':len(costs),'automatic_retry':False,'token_returned':False}

    def page(self, project, *, publication=None, limit=25, cursor=None):
        if type(limit) is not int or not 1<=limit<=100 or publication is not None and (not isinstance(publication,str) or not re.fullmatch(r'nopu_[a-f0-9]{32}',publication)):
            raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PAGE_INVALID',400)
        after=None
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or len(cursor)>2048:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if (not isinstance(after,list) or len(after)!=5 or after[:3]!=[self.workspace,project,publication]
                    or not isinstance(after[3],str) or len(after[3])>40 or not re.fullmatch(r'noas_[a-f0-9]{32}',after[4])
                    or datetime.fromisoformat(after[3]).tzinfo is None):raise ValueError()
            except (ValueError,TypeError,IndexError):raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PAGE_INVALID',400) from None
        if publication:self.publications.get(project,publication)
        with self.store.transaction() as con:
            self.check()
            if con.execute('SELECT 1 FROM projects WHERE id=?',(project,)).fetchone() is None:raise WorkflowError('PROJECT_NOT_FOUND',404)
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if publication:where+=' AND publication_id=?';params.append(publication)
            if after:where+=' AND (created_at<? OR (created_at=? AND sync_id<?))';params.extend([after[3],after[3],after[4]])
            rows=con.execute('SELECT * FROM native_official_analytics_syncs WHERE '+where+' ORDER BY created_at DESC,sync_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            for row in rows:self.read(row)
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,publication,rows[limit-1]['created_at'],rows[limit-1]['sync_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
        return {'schema_version':'native-official-analytics-page-v1','workspace_id':self.workspace,'project_id':project,'publication_id':publication,
            'items':[self.get(project,row['sync_id']) for row in rows[:limit]],'truncated':len(rows)>limit,'next_cursor':next_cursor,
            'publishing_enabled':False,'token_returned':False}
