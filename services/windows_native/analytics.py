"""Native historical analytics: explicit fixture worker, unavailable live transport."""
import asyncio
import base64
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
import uuid

from .contracts import WorkflowError,digest
from .analytics_features import capture
from .analytics_models import NativeAnalyticsRequest
from .store import now
from app.analytics_models import NormalizedMetrics,VideoFeatureMetadata
from app.analytics_providers import DeterministicAnalyticsProvider,AnalyticsCollectionContext,AnalyticsRateLimited,OfficialAnalyticsProvider
from app.analytics_logic import assess_winner,metric_points,learning_insights


def utc(value):
    if not isinstance(value,datetime) or value.tzinfo is None: raise WorkflowError('NATIVE_ANALYTICS_TIME_INVALID',400)
    return value.astimezone(timezone.utc)


class NativeAnalytics:
    def __init__(self,store,publications,*,clock=lambda:datetime.now(timezone.utc)):
        self.store,self.publications,self.clock=store,publications,clock
        self.workspace=publications.workspace_id;self.provider=DeterministicAnalyticsProvider()
        with store.transaction() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS native_analytics_syncs (
                    sync_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,publication_id TEXT NOT NULL,
                    request_key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,request_json TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL,next_at TEXT,
                    snapshot_id TEXT,failure_code TEXT,actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    UNIQUE(workspace_id,project_id,request_key_sha256));
                CREATE INDEX IF NOT EXISTS native_analytics_sync_history ON native_analytics_syncs(workspace_id,project_id,created_at,sync_id);
                CREATE TABLE IF NOT EXISTS native_analytics_snapshots (
                    snapshot_id TEXT PRIMARY KEY,sync_id TEXT UNIQUE NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                    publication_id TEXT NOT NULL,collected_at TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS native_analytics_history ON native_analytics_snapshots(workspace_id,project_id,collected_at,snapshot_id);
                CREATE TABLE IF NOT EXISTS native_analytics_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,sync_id TEXT NOT NULL,project_id TEXT NOT NULL,
                    action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);
            ''')

    def states(self):
        return {'schema_version':'native-analytics-providers-v1','workspace_id':self.workspace,'external_calls_enabled':False,
            'official':[OfficialAnalyticsProvider(platform=p,provider_key='native-official-'+p,credential_ref='').state(p).model_dump(mode='json')
                for p in ['youtube','tiktok','instagram_reels','facebook']],
            'fixture':[self.provider.state(p).model_dump(mode='json') for p in ['youtube','tiktok','instagram_reels','facebook']],
            'automatic_sync_enabled':False,'real_provider_tested':False,'production_deployed':False}

    def event(self,con,row,action,actor,**evidence):
        con.execute('INSERT INTO native_analytics_events(sync_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?)',
            (row['sync_id'],row['project_id'],action,actor,json.dumps(evidence),now()))
        bridge=getattr(self.store,'bridge',None)
        if bridge is not None:bridge.capture_analytics(con,row,action,evidence)

    def publication(self,con,project,identity):
        return self.publications.read(self.publications.get_row(con,project,identity))

    def binding(self,pub):
        return digest({'publication_id':pub['publication_id'],'snapshot_sha256':pub['snapshot_sha256'],
            'receipt':pub['receipt'],'approval':pub['approval'],'status':pub['status']})

    def read_sync(self,row):
        value=dict(row);request=json.loads(value.pop('request_json'))
        if digest(request)!=value['request_fingerprint'] or value['workspace_id']!=self.workspace:
            raise WorkflowError('NATIVE_ANALYTICS_REQUEST_EVIDENCE_INVALID')
        NativeAnalyticsRequest.model_validate({**request,'request_key':'internal-native-analytics-key'})
        value.pop('request_key_sha256');value['request']=request
        return {**value,'schema_version':'native-analytics-sync-v1','external_call':False,'mock':request['provider_mode']=='fixture',
            'automatic_action':False,'real_provider_tested':False}

    def row(self,con,project,identity):
        self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        row=con.execute('SELECT * FROM native_analytics_syncs WHERE sync_id=? AND project_id=? AND workspace_id=?',
            (identity,project,self.workspace)).fetchone()
        if row is None:raise WorkflowError('NATIVE_ANALYTICS_SYNC_NOT_FOUND',404)
        return row

    def create(self,project,payload,*,actor):
        request=payload.model_dump(mode='json',exclude={'request_key'});fingerprint=digest(request)
        key=hashlib.sha256(payload.request_key.encode()).hexdigest()
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_analytics_syncs WHERE workspace_id=? AND project_id=? AND request_key_sha256=?',
                (self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_ANALYTICS_IDEMPOTENCY_CONFLICT')
                return self.read_sync(prior),True
            pub=self.publication(con,project,payload.publication_id)
            failure=None;status='queued';scheduled=payload.scheduled_for
            if scheduled and not utc(self.clock())<utc(scheduled)<=utc(self.clock())+timedelta(days=365):
                raise WorkflowError('NATIVE_ANALYTICS_SCHEDULE_INVALID',400)
            if payload.provider_mode=='official':
                status='not_configured';failure='NATIVE_ANALYTICS_OFFICIAL_ACCOUNT_AND_LIVE_PUBLICATION_REQUIRED'
            elif pub['status']!='dry_run_succeeded' or not pub['receipt'] or pub['receipt']['mock'] is not True:
                raise WorkflowError('NATIVE_ANALYTICS_COMPLETED_DRY_RUN_REQUIRED')
            elif scheduled:status='scheduled'
            stamp=now();identity='nasy_'+uuid.uuid4().hex
            con.execute('INSERT INTO native_analytics_syncs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,payload.publication_id,key,fingerprint,json.dumps(request),self.binding(pub),
                 status,0,utc(scheduled).isoformat() if scheduled else None,None,failure,actor,stamp,stamp))
            row=self.row(con,project,identity);self.event(con,row,'analytics.sync.created',actor,status=status,mock=payload.provider_mode=='fixture',external_call=False)
            return self.read_sync(row),False

    def read_snapshot(self,row):
        value=json.loads(row['snapshot_json'])
        if (digest(value)!=row['snapshot_sha256'] or value.get('workspace_id')!=self.workspace
            or any(value.get(k)!=row[k] for k in ['snapshot_id','sync_id','project_id','publication_id','collected_at'])
            or value.get('mock') is not True or value.get('external_call') is not False or value.get('source_kind')!='fixture'
            or value.get('provider_key')!=self.provider.provider_key):
            raise WorkflowError('NATIVE_ANALYTICS_SNAPSHOT_EVIDENCE_INVALID')
        NormalizedMetrics.model_validate(value['metrics']);VideoFeatureMetadata.model_validate(value['features'])
        if (value['features']['project_id']!=value['project_id'] or value['features']['publication_id']!=value['publication_id']
            or value['features']['evidence'].get('publication_snapshot_sha256')!=value['evidence'].get('publication_snapshot_sha256')
            or value['features']['publishing_time'] is not None or value['evidence'].get('real_audience_observation') is not False):
            raise WorkflowError('NATIVE_ANALYTICS_FEATURE_BINDING_CHANGED')
        utc(datetime.fromisoformat(value['collected_at']))
        return {**value,'snapshot_sha256':row['snapshot_sha256']}

    def get(self,project,identity):
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read_sync(row)
            snapshot=con.execute('SELECT * FROM native_analytics_snapshots WHERE sync_id=? AND workspace_id=? AND project_id=?',
                (identity,self.workspace,project)).fetchone()
            if (value['status']=='succeeded')!=(snapshot is not None):raise WorkflowError('NATIVE_ANALYTICS_SNAPSHOT_EVIDENCE_INVALID')
            value['snapshot']=self.read_snapshot(snapshot) if snapshot else None
            events=con.execute('SELECT * FROM native_analytics_events WHERE sync_id=? ORDER BY event_id DESC LIMIT 101',(identity,)).fetchall()
            value['events']=[{**dict(row),'evidence_json':json.loads(row['evidence_json'])} for row in events[:100]]
            value['events_truncated']=len(events)>100;return value

    def process(self,*,project=None,identity=None,fingerprint=None):
        with self.store.transaction() as con:
            if identity:
                row=self.row(con,project,identity)
                if fingerprint!=row['request_fingerprint']:raise WorkflowError('NATIVE_ANALYTICS_BINDING_CHANGED')
                if row['status']=='succeeded':return self.read_sync(row)
                candidates=[row]
            else:
                candidates=con.execute("SELECT * FROM native_analytics_syncs WHERE workspace_id=? AND (status='queued' OR (status IN ('scheduled','retry_scheduled') AND julianday(next_at)<=julianday(?))) ORDER BY created_at,sync_id LIMIT 20",
                    (self.workspace,utc(self.clock()).isoformat())).fetchall()
            for row in candidates:
                if row['status'] not in ('queued','scheduled','retry_scheduled'):continue
                if row['next_at'] and utc(datetime.fromisoformat(row['next_at']))>utc(self.clock()):continue
                attempts=row['attempts']+1
                con.execute('SAVEPOINT native_analytics_attempt')
                try:
                    value=self.read_sync(row);payload=NativeAnalyticsRequest.model_validate({**value['request'],'request_key':'internal-native-analytics-key'})
                    pub=self.publication(con,row['project_id'],row['publication_id'])
                    if payload.provider_mode!='fixture' or not payload.fixture_acknowledged or self.binding(pub)!=row['binding_sha256']:
                        raise WorkflowError('NATIVE_ANALYTICS_BINDING_CHANGED')
                    if type(self.provider) is not DeterministicAnalyticsProvider:raise WorkflowError('NATIVE_ANALYTICS_LIVE_NOT_CONFIGURED')
                    result=asyncio.run(self.provider.collect(AnalyticsCollectionContext(platform=pub['snapshot']['request']['platform'],
                        project_id=row['project_id'],publication_id=row['publication_id'],remote_post_id=None,fixture_profile=payload.fixture_profile,
                        workspace_id=self.workspace,sync_id=row['sync_id'],attempt_count=attempts)))
                    if (result.provider_key!=self.provider.provider_key or result.mock is not True or result.external_call is not False
                        or result.source_kind!='fixture' or result.source!=f'fixture://analytics/{pub["snapshot"]["request"]["platform"]}/{payload.fixture_profile}'):
                        raise WorkflowError('NATIVE_ANALYTICS_COLLECTION_INVALID')
                    stamp=utc(result.collected_at).isoformat();job=self.store.job(con.execute('SELECT * FROM jobs WHERE id=?',(pub['snapshot']['request']['final_job_id'],)).fetchone())
                    if utc(result.collected_at)>utc(self.clock())+timedelta(seconds=5):raise WorkflowError('NATIVE_ANALYTICS_COLLECTION_INVALID')
                    if digest(job['snapshot'])!=pub['snapshot']['job_snapshot_sha256']:raise WorkflowError('NATIVE_ANALYTICS_FEATURE_BINDING_CHANGED')
                    features=capture(pub,job,stamp);metrics=NormalizedMetrics.model_validate(result.metrics)
                    assessment=assess_winner(metrics,video_duration_seconds=features['duration_seconds'],production_cost_vnd=None)
                    snapshot_id='nams_'+uuid.uuid4().hex
                    insights=learning_insights(assessment=assessment,features=VideoFeatureMetadata.model_validate(features),snapshot_ref=snapshot_id)
                    snapshot={'schema_version':'native-analytics-snapshot-v1','snapshot_id':snapshot_id,'sync_id':row['sync_id'],
                        'workspace_id':self.workspace,'project_id':row['project_id'],'publication_id':row['publication_id'],
                        'platform':pub['snapshot']['request']['platform'],'provider_key':result.provider_key,'source':result.source,
                        'source_kind':result.source_kind,'collected_at':stamp,'metrics':metrics.model_dump(mode='json'),'points':metric_points(metrics),
                        'mock':True,'external_call':False,'evidence':{'fixture_acknowledged':True,'request_fingerprint':row['request_fingerprint'],
                            'publication_binding_sha256':row['binding_sha256'],'publication_snapshot_sha256':pub['snapshot_sha256'],
                            'remote_post_id':None,'real_audience_observation':False,'production_cost_vnd':None},
                        'features':features,'assessment':{**asdict(assessment),'factors':[factor.model_dump(mode='json') for factor in assessment.factors],
                            'basis':'explicit_fixture_absolute_reference_only','channel_baseline_verified':False,'automatic_action':False},
                        'insights':[{**asdict(item),'applied':False,'autonomous_execution':False,'mock':True} for item in insights]}
                    con.execute('INSERT INTO native_analytics_snapshots VALUES(?,?,?,?,?,?,?,?)',
                        (snapshot_id,row['sync_id'],self.workspace,row['project_id'],row['publication_id'],stamp,digest(snapshot),json.dumps(snapshot,ensure_ascii=False)))
                    con.execute("UPDATE native_analytics_syncs SET status='succeeded',attempts=?,snapshot_id=?,failure_code=NULL,next_at=NULL,updated_at=? WHERE sync_id=?",
                        (attempts,snapshot_id,now(),row['sync_id']))
                    self.event(con,row,'analytics.fixture.collected','native-fixture-worker',snapshot_id=snapshot_id,mock=True,external_call=False)
                    con.execute('RELEASE native_analytics_attempt')
                except AnalyticsRateLimited as error:
                    con.execute('ROLLBACK TO native_analytics_attempt');con.execute('RELEASE native_analytics_attempt')
                    status='retry_scheduled' if attempts<3 else 'failed'
                    due=(utc(self.clock())+timedelta(seconds=max(error.retry_after_seconds,min(3600,30*2**(attempts-1))))).isoformat() if attempts<3 else None
                    con.execute('UPDATE native_analytics_syncs SET status=?,attempts=?,next_at=?,failure_code=?,updated_at=? WHERE sync_id=?',
                        (status,attempts,due,'NATIVE_ANALYTICS_RATE_LIMITED',now(),row['sync_id']))
                    self.event(con,row,'analytics.fixture.rate_limited','native-fixture-worker',attempts=attempts,status=status,external_call=False)
                except Exception as error:
                    con.execute('ROLLBACK TO native_analytics_attempt');con.execute('RELEASE native_analytics_attempt')
                    code=error.code if isinstance(error,WorkflowError) else 'NATIVE_ANALYTICS_COLLECTION_FAILED'
                    con.execute("UPDATE native_analytics_syncs SET status='failed',attempts=?,failure_code=?,next_at=NULL,updated_at=? WHERE sync_id=?",(attempts,code,now(),row['sync_id']))
                    self.event(con,row,'analytics.sync.failed','native-fixture-worker',failure_code=code,external_call=False)
                return self.read_sync(self.row(con,row['project_id'],row['sync_id']))
            return None

    def cancel(self,project,identity,*,fingerprint,actor):
        with self.store.transaction() as con:
            row=self.row(con,project,identity)
            if fingerprint!=row['request_fingerprint']:raise WorkflowError('NATIVE_ANALYTICS_BINDING_CHANGED')
            if row['status']=='succeeded':raise WorkflowError('NATIVE_ANALYTICS_ALREADY_COMPLETE')
            if row['status']!='cancelled':
                con.execute("UPDATE native_analytics_syncs SET status='cancelled',next_at=NULL,updated_at=? WHERE sync_id=?",(now(),identity))
                self.event(con,row,'analytics.sync.cancelled',actor,external_call=False)
            return self.read_sync(self.row(con,project,identity))

    def page(self,project,*,limit=25,cursor=None,publication=None):
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_ANALYTICS_PAGE_INVALID',400)
        after=None
        if cursor:
            try:
                if not isinstance(cursor,str) or len(cursor)>1000:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(after,list) or len(after)!=5 or after[:3]!=[self.workspace,project,publication]:raise ValueError()
                if not isinstance(after[3],str) or not isinstance(after[4],str):raise ValueError()
                utc(datetime.fromisoformat(after[3]))
            except (ValueError,TypeError,WorkflowError):raise WorkflowError('NATIVE_ANALYTICS_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if publication:self.publication(con,project,publication);where+=' AND publication_id=?';params.append(publication)
            if after:where+=' AND (created_at<? OR (created_at=? AND sync_id<?))';params.extend([after[3],after[3],after[4]])
            rows=con.execute('SELECT * FROM native_analytics_syncs WHERE '+where+' ORDER BY created_at DESC,sync_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            items=[self.read_sync(row) for row in rows[:limit]]
            for value in items:
                snapshot=con.execute('SELECT * FROM native_analytics_snapshots WHERE sync_id=? AND workspace_id=?',(value['sync_id'],self.workspace)).fetchone()
                if (value['status']=='succeeded')!=(snapshot is not None):raise WorkflowError('NATIVE_ANALYTICS_SNAPSHOT_EVIDENCE_INVALID')
                value['snapshot']=self.read_snapshot(snapshot) if snapshot else None
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,publication,rows[limit-1]['created_at'],rows[limit-1]['sync_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-analytics-page-v1','workspace_id':self.workspace,'project_id':project,
                'publication_id':publication,'items':items,'next_cursor':next_cursor,'limit':limit,'automatic_sync_enabled':False,'external_call':False}

    def overview(self,*,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_ANALYTICS_PAGE_INVALID',400)
        after=None
        if cursor:
            try:
                if not isinstance(cursor,str) or len(cursor)>1000:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(after,list) or len(after)!=4 or after[:2]!=[self.workspace,'workspace-overview']:raise ValueError()
                if not isinstance(after[2],str) or not isinstance(after[3],str):raise ValueError()
                utc(datetime.fromisoformat(after[2]))
            except (ValueError,TypeError,WorkflowError):raise WorkflowError('NATIVE_ANALYTICS_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            where='rank=1';params=[self.workspace]
            if after:where+=' AND (collected_at<? OR (collected_at=? AND publication_id<?))';params.extend([after[2],after[2],after[3]])
            rows=con.execute('WITH ranked AS (SELECT *,ROW_NUMBER() OVER (PARTITION BY publication_id ORDER BY collected_at DESC,snapshot_id DESC) AS rank FROM native_analytics_snapshots WHERE workspace_id=?) SELECT * FROM ranked WHERE '+where+' ORDER BY collected_at DESC,publication_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            values=[self.read_snapshot(row) for row in rows[:limit]]
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,'workspace-overview',rows[limit-1]['collected_at'],rows[limit-1]['publication_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-analytics-overview-v1','workspace_id':self.workspace,'items':values,
                'next_cursor':next_cursor,'limit':limit,'basis':'latest_recorded_fixture_per_publication',
                'channel_account_verified':False,'account_totals':None,'external_call':False,'mock':True}
