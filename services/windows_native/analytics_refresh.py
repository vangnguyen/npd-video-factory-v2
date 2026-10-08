"""Durable Native refresh plans append to the existing analytics queue only.

All external providers remain unavailable. Explicit fixture plans may run in
the single Native worker; report history, approval and publication are separate.
"""
import base64
from datetime import datetime, timedelta
import hashlib
import json
import uuid
from pydantic import ValidationError
from .analytics import utc
from .analytics_models import NativeAnalyticsRequest
from .analytics_refresh_models import NativeAnalyticsRefreshCreate, NativeRuntimeAnalyticsProfile
from .channel_profiles import resolve
from .contracts import WorkflowError, digest


class NativeAnalyticsRefresh:
    def __init__(self, analytics):
        self.analytics = analytics
        self.store, self.workspace, self.clock = analytics.store, analytics.workspace, analytics.clock
        with self.store.transaction() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS native_analytics_refresh_plans (
                    plan_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,publication_id TEXT NOT NULL,
                    request_key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,policy_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,enabled INTEGER NOT NULL,run_count INTEGER NOT NULL,next_due_at TEXT NOT NULL,
                    failure_code TEXT,created_by TEXT NOT NULL,updated_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    UNIQUE(workspace_id,project_id,request_key_sha256));
                CREATE INDEX IF NOT EXISTS native_analytics_refresh_due ON native_analytics_refresh_plans(workspace_id,enabled,next_due_at);
                CREATE TABLE IF NOT EXISTS native_analytics_refresh_occurrences (
                    occurrence_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,sync_id TEXT UNIQUE NOT NULL,
                    workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                    occurrence_sha256 TEXT NOT NULL,occurrence_json TEXT NOT NULL,UNIQUE(plan_id,ordinal));
                CREATE TABLE IF NOT EXISTS native_analytics_refresh_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,plan_id TEXT NOT NULL,workspace_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,revision INTEGER NOT NULL,action TEXT NOT NULL,actor_ref TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);
            ''')
        analytics.refresh = self

    def event(self, con, row, action, actor, **evidence):
        con.execute('INSERT INTO native_analytics_refresh_events(plan_id,workspace_id,project_id,revision,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (row['plan_id'], self.workspace, row['project_id'], row['revision'], action, actor, json.dumps(evidence), utc(self.clock()).isoformat()))

    def row(self, con, project, identity):
        self.store.project(con.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone())
        row = con.execute('SELECT * FROM native_analytics_refresh_plans WHERE plan_id=? AND project_id=? AND workspace_id=?',
            (identity, project, self.workspace)).fetchone()
        if row is None: raise WorkflowError('NATIVE_ANALYTICS_REFRESH_NOT_FOUND', 404)
        return row

    def read(self, row):
        try:
            value = dict(row); policy = json.loads(value.pop('policy_json'))
            config = NativeAnalyticsRefreshCreate.model_validate({**policy['config'], 'request_key': 'internal-native-refresh-key'})
            profile = NativeRuntimeAnalyticsProfile.model_validate(policy['analytics_profile'])
            if (digest(policy) != value['request_fingerprint'] or value['workspace_id'] != self.workspace
                or any(policy[k] != value[k] for k in ('workspace_id', 'project_id', 'publication_id'))
                or config.publication_id != value['publication_id'] or profile.provider_mode != config.provider_mode
                or type(value['enabled']) is not int or value['enabled'] not in (0, 1)
                or type(value['revision']) is not int or value['revision'] < 1
                or type(value['run_count']) is not int or not 0 <= value['run_count'] <= config.max_runs
                or (value['enabled'] and (config.provider_mode != 'fixture' or value['run_count'] >= config.max_runs))): raise ValueError()
            utc(datetime.fromisoformat(value['next_due_at']))
            value.pop('request_key_sha256'); value['enabled'] = bool(value['enabled'])
            status = 'not_configured' if config.provider_mode == 'official' else 'exhausted' if value['run_count'] == config.max_runs else 'active' if value['enabled'] else 'paused'
            if value['failure_code']: status = 'needs_attention'
            return {**value, **policy, 'schema_version': 'native-analytics-refresh-plan-v1', 'status': status,
                'max_runs': config.max_runs, 'recommendation_only': True, 'external_call': False,
                'real_provider_tested': False, 'publishing_enabled_by_plan': False}
        except (ValueError, KeyError, TypeError, ValidationError):
            raise WorkflowError('NATIVE_ANALYTICS_REFRESH_EVIDENCE_INVALID') from None

    def create(self, project, payload, *, actor):
        payload = NativeAnalyticsRefreshCreate.model_validate(payload.model_dump())
        key = hashlib.sha256(payload.request_key.encode()).hexdigest()
        config = payload.model_dump(mode='json', exclude={'request_key'})
        with self.store.transaction() as con:
            prior = con.execute('SELECT * FROM native_analytics_refresh_plans WHERE workspace_id=? AND project_id=? AND request_key_sha256=?',
                (self.workspace, project, key)).fetchone()
            if prior:
                value = self.read(prior)
                if value['config'] != config: raise WorkflowError('NATIVE_ANALYTICS_REFRESH_IDEMPOTENCY_CONFLICT')
                return value, True
            pub = self.analytics.publication(con, project, payload.publication_id)
            if payload.provider_mode == 'fixture' and (pub['status'] != 'dry_run_succeeded' or not pub['receipt'] or pub['receipt']['mock'] is not True):
                raise WorkflowError('NATIVE_ANALYTICS_COMPLETED_DRY_RUN_REQUIRED')
            if payload.provider_mode == 'official' and payload.enabled:
                raise WorkflowError('NATIVE_ANALYTICS_REFRESH_OFFICIAL_NOT_CONFIGURED')
            instant = utc(self.clock())
            if not instant - timedelta(days=365) <= payload.first_run_at <= instant + timedelta(days=365):
                raise WorkflowError('NATIVE_ANALYTICS_REFRESH_TIME_INVALID', 400)
            job = self.store.job(con.execute('SELECT * FROM jobs WHERE id=?', (pub['snapshot']['request']['final_job_id'],)).fetchone())
            if digest(job['snapshot']) != pub['snapshot']['job_snapshot_sha256']:
                raise WorkflowError('NATIVE_ANALYTICS_FEATURE_BINDING_CHANGED')
            document = job['snapshot']['document']; channel = resolve(document) if document.get('channel_profile') else None
            fixture = payload.provider_mode == 'fixture'
            profile = NativeRuntimeAnalyticsProfile(profile_ref='native-recorded-fixture-analytics@1' if fixture else 'native-official-analytics@1',
                provider_mode=payload.provider_mode, provider_key=self.analytics.provider.provider_key if fixture else 'native-official-'+pub['snapshot']['request']['platform'],
                provider_status='EXPLICIT_FIXTURE' if fixture else 'NOT_CONFIGURED',
                channel_profile_ref=channel['profile']['profile_ref'] if channel else None,
                channel_selection_sha256=channel['selection_sha256'] if channel else None,
                channel_analytics_profile=channel['profile']['analytics_profile'] if channel else None,
                publication_binding_sha256=self.analytics.binding(pub)).model_dump(mode='json')
            policy = {'workspace_id': self.workspace, 'project_id': project, 'publication_id': payload.publication_id,
                'config': config, 'analytics_profile': profile}
            identity = 'narp_'+uuid.uuid4().hex; stamp = instant.isoformat()
            con.execute('INSERT INTO native_analytics_refresh_plans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,payload.publication_id,key,digest(policy),json.dumps(policy,ensure_ascii=False),
                 1,int(payload.enabled),0,payload.first_run_at.isoformat(),None,actor,actor,stamp,stamp))
            row = self.row(con,project,identity); self.event(con,row,'analytics.refresh.created',actor,enabled=payload.enabled,external_call=False)
            return self.read(row),False

    def occurrence(self, con, row):
        try:
            value = json.loads(row['occurrence_json'])
            if (digest(value) != row['occurrence_sha256'] or value['workspace_id'] != self.workspace
                or any(value[k] != row[k] for k in ('plan_id','sync_id','workspace_id','project_id','ordinal','occurrence_id'))
                or type(value['plan_revision']) is not int or value['plan_revision'] < 1
                or type(value['skipped_slots']) is not int or value['skipped_slots'] < 0): raise ValueError()
            utc(datetime.fromisoformat(value['scheduled_for'])); utc(datetime.fromisoformat(value['planned_for']))
            return {**value,'occurrence_sha256':row['occurrence_sha256']}
        except (ValueError,TypeError,KeyError): raise WorkflowError('NATIVE_ANALYTICS_REFRESH_OCCURRENCE_INVALID') from None

    def evidence(self, con, sync):
        row=con.execute('SELECT * FROM native_analytics_refresh_occurrences WHERE sync_id=?',(sync['sync_id'],)).fetchone()
        if row is None:return None
        value=self.occurrence(con,row)
        if value['project_id']!=sync['project_id'] or value['sync_request_fingerprint']!=sync['request_fingerprint']:
            raise WorkflowError('NATIVE_ANALYTICS_REFRESH_OCCURRENCE_INVALID')
        return value

    def admit(self,con,sync):
        occurrence=self.evidence(con,sync)
        if occurrence is None:return True
        plan=self.read(self.row(con,sync['project_id'],occurrence['plan_id']))
        if plan['request_fingerprint']!=occurrence['plan_request_fingerprint']:
            raise WorkflowError('NATIVE_ANALYTICS_REFRESH_OCCURRENCE_INVALID')
        if not plan['enabled'] or plan['revision']!=occurrence['plan_revision']:
            # The final occurrence is admitted after the bounded plan exhausts.
            if plan['status']=='exhausted' and plan['revision']==occurrence['plan_revision']:return True
            self.analytics.cancel(sync['project_id'],sync['sync_id'],fingerprint=sync['request_fingerprint'],actor='native-analytics-scheduler',con=con)
            return False
        return True

    def cancel_pending(self,con,row,actor):
        pending=con.execute("SELECT s.* FROM native_analytics_syncs s JOIN native_analytics_refresh_occurrences o ON o.sync_id=s.sync_id WHERE o.plan_id=? AND s.status IN ('queued','scheduled','retry_scheduled')",(row['plan_id'],)).fetchall()
        for sync in pending:
            self.evidence(con,sync)
            self.analytics.cancel(row['project_id'],sync['sync_id'],fingerprint=sync['request_fingerprint'],actor=actor,con=con)

    def state(self,project,identity,payload,*,actor):
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(row)
            if value['revision']!=payload.expected_revision:raise WorkflowError('NATIVE_ANALYTICS_REFRESH_REVISION_CONFLICT')
            if payload.enabled:
                if value['config']['provider_mode']!='fixture':raise WorkflowError('NATIVE_ANALYTICS_REFRESH_OFFICIAL_NOT_CONFIGURED')
                if not payload.fixture_acknowledged:raise WorkflowError('NATIVE_ANALYTICS_REFRESH_FIXTURE_ACK_REQUIRED',400)
                if value['run_count']>=value['max_runs']:raise WorkflowError('NATIVE_ANALYTICS_REFRESH_EXHAUSTED')
                pub=self.analytics.publication(con,project,value['publication_id'])
                if self.analytics.binding(pub)!=value['analytics_profile']['publication_binding_sha256']:
                    raise WorkflowError('NATIVE_ANALYTICS_REFRESH_BINDING_CHANGED')
            elif payload.fixture_acknowledged:raise WorkflowError('NATIVE_ANALYTICS_REFRESH_FIELDS_INVALID',400)
            self.cancel_pending(con,row,actor)
            con.execute('UPDATE native_analytics_refresh_plans SET enabled=?,revision=revision+1,failure_code=NULL,updated_by=?,updated_at=? WHERE plan_id=?',
                (int(payload.enabled),actor,utc(self.clock()).isoformat(),identity))
            row=self.row(con,project,identity);self.event(con,row,'analytics.refresh.enabled' if payload.enabled else 'analytics.refresh.disabled',actor,external_call=False)
            return self.read(row)

    def tick(self,*,project=None,actor='native-analytics-scheduler'):
        instant=utc(self.clock());created=[]
        with self.store.transaction() as con:
            params=[self.workspace,instant.isoformat()];where='workspace_id=? AND enabled=1 AND julianday(next_due_at)<=julianday(?)'
            if project:
                self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
                where+=' AND project_id=?';params.append(project)
            rows=con.execute('SELECT * FROM native_analytics_refresh_plans WHERE '+where+' ORDER BY next_due_at,plan_id LIMIT 20',params).fetchall()
            for row in rows:
                failure=None
                try:
                    value=self.read(row);pub=self.analytics.publication(con,row['project_id'],row['publication_id'])
                    if self.analytics.binding(pub)!=value['analytics_profile']['publication_binding_sha256']:
                        failure='NATIVE_ANALYTICS_REFRESH_BINDING_CHANGED'
                except WorkflowError as error:failure=error.code
                if failure:
                    try:self.cancel_pending(con,row,actor)
                    except WorkflowError:pass  # Corrupt jobs fail closed at worker admission.
                    con.execute('UPDATE native_analytics_refresh_plans SET enabled=0,revision=revision+1,failure_code=?,updated_at=? WHERE plan_id=?',(failure,instant.isoformat(),row['plan_id']))
                    self.event(con,self.row(con,row['project_id'],row['plan_id']),'analytics.refresh.blocked',actor,failure_code=failure,external_call=False)
                    continue
                # Never create another occurrence while its rate-limited job is pending.
                if con.execute("SELECT 1 FROM native_analytics_syncs s JOIN native_analytics_refresh_occurrences o ON o.sync_id=s.sync_id WHERE o.plan_id=? AND s.status IN ('queued','scheduled','retry_scheduled') LIMIT 1",(row['plan_id'],)).fetchone():continue
                config=value['config'];ordinal=row['run_count']+1;planned=utc(datetime.fromisoformat(row['next_due_at']))
                payload=NativeAnalyticsRequest(publication_id=row['publication_id'],provider_mode='fixture',fixture_profile=config['fixture_profile'],
                    fixture_acknowledged=True,trigger='scheduled_refresh',scheduled_for=instant,request_key='native-refresh-'+row['plan_id']+'-'+str(ordinal))
                sync,replay=self.analytics.create(row['project_id'],payload,actor=row['created_by'],con=con,due_refresh=True)
                if replay:raise WorkflowError('NATIVE_ANALYTICS_REFRESH_OCCURRENCE_CONFLICT')
                occurrence={'schema_version':'native-analytics-refresh-occurrence-v1','occurrence_id':'naro_'+uuid.uuid4().hex,
                    'plan_id':row['plan_id'],'sync_id':sync['sync_id'],'workspace_id':self.workspace,'project_id':row['project_id'],
                    'ordinal':ordinal,'plan_revision':row['revision'],'plan_request_fingerprint':row['request_fingerprint'],
                    'sync_request_fingerprint':sync['request_fingerprint'],'planned_for':planned.isoformat(),'scheduled_for':instant.isoformat(),
                    'skipped_slots':max(0,int((instant-planned).total_seconds()//(config['interval_hours']*3600))),
                    'mock':True,'external_call':False,'recommendation_only':True}
                con.execute('INSERT INTO native_analytics_refresh_occurrences VALUES(?,?,?,?,?,?,?,?)',
                    (occurrence['occurrence_id'],row['plan_id'],sync['sync_id'],self.workspace,row['project_id'],ordinal,digest(occurrence),json.dumps(occurrence)))
                con.execute('UPDATE native_analytics_refresh_plans SET run_count=?,enabled=?,next_due_at=?,updated_at=? WHERE plan_id=?',
                    (ordinal,int(ordinal<config['max_runs']),(instant+timedelta(hours=config['interval_hours'])).isoformat(),instant.isoformat(),row['plan_id']))
                self.event(con,self.row(con,row['project_id'],row['plan_id']),'analytics.refresh.occurrence_created',actor,sync_id=sync['sync_id'],ordinal=ordinal,skipped_slots=occurrence['skipped_slots'],external_call=False)
                created.append(sync['sync_id'])
        return {'schema_version':'native-analytics-refresh-tick-v1','workspace_id':self.workspace,'project_id':project,
            'created_sync_ids':created,'bounded_plan_limit':20,'external_call':False,'provider_calls':0,'publishing_enabled':False}

    def get(self,project,identity):
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity))
            rows=con.execute('SELECT * FROM native_analytics_refresh_occurrences WHERE plan_id=? ORDER BY ordinal DESC LIMIT 101',(identity,)).fetchall()
            value['occurrences']=[self.occurrence(con,row) for row in rows[:100]];value['occurrences_truncated']=len(rows)>100
            events=con.execute('SELECT * FROM native_analytics_refresh_events WHERE plan_id=? ORDER BY event_id DESC LIMIT 101',(identity,)).fetchall()
            value['events']=[{**dict(row),'evidence_json':json.loads(row['evidence_json'])} for row in events[:100]];value['events_truncated']=len(events)>100
            return value

    def page(self,project,*,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_ANALYTICS_REFRESH_PAGE_INVALID',400)
        after=None
        if cursor:
            try:
                if not isinstance(cursor,str) or len(cursor)>1000:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(after,list) or len(after)!=3 or after[:2]!=[self.workspace,project] or not isinstance(after[2],str):raise ValueError()
            except (ValueError,TypeError):raise WorkflowError('NATIVE_ANALYTICS_REFRESH_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if after:where+=' AND plan_id>?';params.append(after[2])
            rows=con.execute('SELECT * FROM native_analytics_refresh_plans WHERE '+where+' ORDER BY plan_id LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,rows[limit-1]['plan_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-analytics-refresh-page-v1','workspace_id':self.workspace,'project_id':project,
                'items':[self.read(row) for row in rows[:limit]],'next_cursor':next_cursor,'limit':limit,'external_call':False}
