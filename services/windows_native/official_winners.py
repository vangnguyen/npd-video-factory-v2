"""Frozen Native channel-relative assessments over qualified analytics only.

No provider call, automatic action, media deletion, budget change or fixture fallback.
Original sources and selected peers are validated in one SQLite transaction.
"""
import base64,json,re,uuid
from datetime import datetime
from collections import Counter
from pydantic import ValidationError
from .contracts import WorkflowError,digest
from .official_analytics import NativeOfficialAnalytics,typed
from .official_analytics_models import Collect
from .official_winner_models import Create
from .official_publications import utc
from .store import now
from app.analytics_models import NormalizedMetrics
from app.analytics_channel_policy import WinnerChannelPolicy,values,bucket,assess_channel

TABLES=('native_official_winner_assessments','native_official_winner_events')

class NativeOfficialWinners:
    def __init__(self,analytics):
        if type(analytics) is not NativeOfficialAnalytics:raise WorkflowError('NATIVE_OFFICIAL_WINNER_CONFIGURATION_INVALID',400)
        self.analytics=analytics;self.store,self.workspace,self.clock=analytics.store,analytics.workspace,analytics.clock
        self.frozen=(analytics,self.store,self.workspace,self.clock,self.store.root.absolute())
        with self.store.transaction() as con:
            self.check()
            con.executescript('''CREATE TABLE IF NOT EXISTS native_official_winner_assessments (
                assessment_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,publication_id TEXT NOT NULL,
                sync_id TEXT NOT NULL,result_snapshot_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,
                snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(workspace_id,project_id,key_sha256));
                CREATE INDEX IF NOT EXISTS native_official_winner_history ON native_official_winner_assessments(workspace_id,project_id,created_at,assessment_id);
                CREATE TABLE IF NOT EXISTS native_official_winner_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,assessment_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_official_winner_assessments WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_WINNER_WORKSPACE_CHANGED')

    def check(self):
        if (self.analytics,self.store,self.workspace,self.clock,self.store.root.absolute())!=self.frozen:raise WorkflowError('NATIVE_OFFICIAL_WINNER_CONFIGURATION_CHANGED')
        self.analytics.check()

    def proof(self,con,project,identity):
        value=self.analytics.get(project,identity,con=con);result=value['result']
        if value['status']!='succeeded' or result is None:raise WorkflowError('NATIVE_OFFICIAL_WINNER_QUALIFIED_OBSERVATION_REQUIRED')
        request=Collect.model_validate({**value['snapshot']['request'],'request_key':'internal-native-winner-source-key'})
        publication,source=self.analytics.source(project,request,result['features']['captured_at'],con=con)
        if source!=value['snapshot']['source']:raise WorkflowError('NATIVE_OFFICIAL_WINNER_SOURCE_CHANGED')
        job=self.store.job(con.execute('SELECT * FROM jobs WHERE id=? AND project_id=?',(publication['snapshot']['final_job_id'],project)).fetchone(),con)
        qc=job['result']['qc'];format={k:qc.get(k) for k in ('width','height','fps','video_codec','audio_codec')}
        features=result['features'];evidence=features['evidence'];query=value['snapshot']['request']['query']
        scope={'workspace_id':self.workspace,'target_binding_sha256':value['snapshot']['target_binding_sha256'],'platform':result['platform'],
            'provider_key':result['provider_key'],'source_kind':result['source_kind'],'mock':result['mock'],'source_external_call':result['external_call'],
            'query':query,'format':format,'duration_bucket':bucket(features['duration_seconds']),'niche':features['niche'],
            'channel_profile_ref':evidence.get('channel_profile_ref'),'channel_profile_sha256':evidence.get('channel_profile_sha256')}
        return {'project_id':project,'publication_id':value['publication_id'],'sync_id':identity,'result_snapshot_id':value['result_snapshot_id'],
            'result_sha256':digest(result),'consent_sha256':value['snapshot_sha256'],'source_sha256':digest(source),'publication_receipt_sha256':source['receipt_sha256'],
            'remote_post_id':result['remote_post_id'],'collected_at':result['collected_at'],'scope':scope,'metrics':result['metrics'],
            'features':features,'production_cost_vnd':features['evidence']['production_cost_vnd']}

    @staticmethod
    def known_scope(candidate):
        scope=candidate['scope'];format=scope['format']
        return bool(scope['niche'] and scope['duration_bucket'] and all(type(format[k]) is int and format[k]>0 for k in ('width','height'))
            and isinstance(format['video_codec'],str) and format['video_codec'])

    @staticmethod
    def compatible(candidate,peer):
        return (peer['scope']==candidate['scope'] and peer['remote_post_id']!=candidate['remote_post_id']
            and utc(datetime.fromisoformat(peer['collected_at']))<=utc(datetime.fromisoformat(candidate['collected_at'])))

    def context(self,con,candidate,policy):
        rows=con.execute('''SELECT r.project_id,r.sync_id,r.result_snapshot_id,r.collected_at FROM native_official_analytics_snapshots r
            JOIN native_official_analytics_syncs s ON s.sync_id=r.sync_id AND s.workspace_id=r.workspace_id AND s.project_id=r.project_id
            AND s.publication_id=r.publication_id AND s.snapshot_sha256=r.snapshot_sha256 AND s.result_snapshot_id=r.result_snapshot_id
            WHERE r.workspace_id=? AND s.status='succeeded' AND r.collected_at<=?
            ORDER BY r.collected_at DESC,s.updated_at DESC,r.result_snapshot_id DESC LIMIT 501''',(self.workspace,candidate['collected_at'])).fetchall()
        selected={};excluded=Counter()
        if self.known_scope(candidate):
            for row in rows[:500]:
                peer=self.proof(con,row['project_id'],row['sync_id'])
                if not self.compatible(candidate,peer):excluded['incompatible_scope_or_anchor']+=1;continue
                remote=peer['remote_post_id']
                if remote in selected:excluded['duplicate_remote_post']+=1;continue
                if len(selected)>=policy.maximum_peer_posts:excluded['peer_limit']+=1;continue
                selected[remote]=peer
        else:excluded['candidate_scope_incomplete']=1
        return list(selected.values()),len(rows)>500,dict(excluded)

    def assessment(self,candidate,peers,policy,truncated):
        context={'peers':[{'snapshot_id':p['result_snapshot_id'],'values':values(NormalizedMetrics.model_validate(p['metrics']),p['features']['duration_seconds'],p['production_cost_vnd'])} for p in peers],
            'candidate_rows_truncated':truncated,'counter_growth':None,'scope_verified':self.known_scope(candidate),'policy_sha256':policy.digest()}
        draft=assess_channel(NormalizedMetrics.model_validate(candidate['metrics']),duration=candidate['features']['duration_seconds'],production_cost=candidate['production_cost_vnd'],context=context,policy=policy)
        return {'state':draft.state,'score':draft.score,'data_coverage':draft.data_coverage,'algorithm_version':draft.algorithm_version,
            'factors':[f.model_dump(mode='json') for f in draft.factors],'evidence':draft.evidence,'recommendations':draft.recommendations,
            'basis':'matching_native_official_channel_report_scope','peer_scope_verified':context['scope_verified'],
            'channel_baseline_verified':not candidate['scope']['mock'] and context['scope_verified'] and len(peers)>=policy.minimum_peer_posts,
            'view_velocity_supported':False,'publishing_age_hours':None,'actual_publication_time':None,
            'mock':candidate['scope']['mock'],'source_kind':candidate['scope']['source_kind'],'source_external_call':candidate['scope']['source_external_call'],
            'real_audience_observation':not candidate['scope']['mock'],'external_call':False,'automatic_action':False,'publishing_enabled':False,
            'limitations':['Requested report dates do not prove complete coverage or equal publication age.',
                'Report updates are not cumulative video-counter velocity; velocity and publication time remain unavailable.',
                'Frozen niche/channel annotations and selected compatible posts do not prove complete channel history or causal improvement.',
                'Protocol mocks are synthetic; their relative assessments cannot enter real audience learning.']}

    def row(self,con,project,identity):
        self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        row=con.execute('SELECT * FROM native_official_winner_assessments WHERE assessment_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_OFFICIAL_WINNER_NOT_FOUND',404)
        return row

    def read(self,con,row):
        self.check();value=dict(row)
        try:
            snapshot=json.loads(value.pop('snapshot_json'));request=Create.model_validate({**snapshot['request'],'request_key':'internal-native-winner-history-key'});policy=request.policy
            candidate=snapshot['candidate'];peers=snapshot['peers'];truncated=snapshot['candidate_rows_truncated'];excluded=snapshot['excluded_rows']
            if (snapshot['schema_version']!='native-official-winner-snapshot-v1' or digest(snapshot)!=value['snapshot_sha256']
                or any(snapshot[k]!=value[k] for k in ('workspace_id','project_id','publication_id','sync_id','result_snapshot_id'))
                or value['workspace_id']!=self.workspace or digest(snapshot['request'])!=value['request_fingerprint']
                or request.sync_id!=candidate['sync_id'] or request.expected_result_sha256!=candidate['result_sha256']
                or snapshot['policy_sha256']!=policy.digest() or request.acknowledged_protocol_mock is not candidate['scope']['mock']
                or type(truncated) is not bool or not isinstance(peers,list) or len(peers)>policy.maximum_peer_posts
                or len({p['remote_post_id'] for p in peers})!=len(peers) or snapshot['recommendation_only'] is not True
                or snapshot['automatic_action'] is not False or snapshot['publishing_enabled'] is not False
                or snapshot['authority']['token_id']!=value['created_by'] or not isinstance(excluded,dict)
                or set(excluded)-{'incompatible_scope_or_anchor','duplicate_remote_post','peer_limit','candidate_scope_incomplete'}
                or any(type(v) is not int or v<0 for v in excluded.values()) or sum(excluded.values())>500):raise ValueError()
            actual=self.proof(con,value['project_id'],value['sync_id'])
            if candidate!=actual or any(not self.compatible(candidate,p) or p!=self.proof(con,p['project_id'],p['sync_id']) for p in peers):raise ValueError()
            expected=self.assessment(candidate,peers,policy,truncated)
            if snapshot['assessment']!=expected:raise ValueError()
            value.pop('key_sha256')
            return {**value,'schema_version':'native-official-winner-assessment-v1','snapshot':snapshot,'assessment':expected,
                'peer_count':len(peers),'mock':candidate['scope']['mock'],'real_audience_observation':not candidate['scope']['mock'],
                'recommendation_only':True,'automatic_action':False,'external_call':False,'publishing_enabled':False,'token_returned':False,'real_provider_tested':False}
        except (ValueError,TypeError,KeyError,ValidationError):raise WorkflowError('NATIVE_OFFICIAL_WINNER_EVIDENCE_CHANGED') from None

    def create(self,project,payload,*,principal):
        self.check();payload=typed(payload,Create);authority=self.analytics.identity(principal)
        request=payload.model_dump(mode='json',exclude={'request_key'});key=digest(payload.request_key);fingerprint=digest(request)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_official_winner_assessments WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_OFFICIAL_WINNER_IDEMPOTENCY_CONFLICT')
                return self.read(con,prior),True
            candidate=self.proof(con,project,payload.sync_id)
            if candidate['result_sha256']!=payload.expected_result_sha256:raise WorkflowError('NATIVE_OFFICIAL_WINNER_OBSERVATION_CHANGED')
            if payload.acknowledged_protocol_mock is not candidate['scope']['mock']:raise WorkflowError('NATIVE_OFFICIAL_WINNER_MOCK_ACK_REQUIRED')
            if utc(datetime.fromisoformat(candidate['collected_at']))>utc(self.clock()):raise WorkflowError('NATIVE_OFFICIAL_WINNER_FUTURE_OBSERVATION')
            peers,truncated,excluded=self.context(con,candidate,payload.policy)
            assessment=self.assessment(candidate,peers,payload.policy,truncated)
            snapshot={'schema_version':'native-official-winner-snapshot-v1','workspace_id':self.workspace,'project_id':project,
                'publication_id':candidate['publication_id'],'sync_id':payload.sync_id,'result_snapshot_id':candidate['result_snapshot_id'],
                'request':request,'authority':authority,'policy_sha256':payload.policy.digest(),'candidate':candidate,'peers':peers,
                'candidate_rows_truncated':truncated,'excluded_rows':excluded,'assessment':assessment,
                'recommendation_only':True,'automatic_action':False,'publishing_enabled':False}
            self.analytics.identity(authority=authority);identity,stamp='nowa_'+uuid.uuid4().hex,now()
            con.execute('INSERT INTO native_official_winner_assessments VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,candidate['publication_id'],payload.sync_id,candidate['result_snapshot_id'],key,fingerprint,digest(snapshot),json.dumps(snapshot),authority['token_id'],stamp))
            con.execute('INSERT INTO native_official_winner_events(assessment_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
                (identity,self.workspace,project,'analytics.official.winner.assessed',authority['token_id'],json.dumps({'state':assessment['state'],'mock':candidate['scope']['mock'],'recommendation_only':True,'external_call':False}),stamp))
            value=self.read(con,self.row(con,project,identity));bridge=getattr(self.store,'bridge',None)
            if bridge is not None:bridge.capture_qualified(con,'winner',self,project,identity)
            return value,False

    def get(self,project,identity):
        with self.store.transaction() as con:return self.read(con,self.row(con,project,identity))

    def page(self,project,*,publication=None,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100 or publication is not None and (not isinstance(publication,str) or not re.fullmatch(r'nopu_[a-f0-9]{32}',publication)):
            raise WorkflowError('NATIVE_OFFICIAL_WINNER_PAGE_INVALID',400)
        after=None
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or len(cursor)>2048:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if (not isinstance(after,list) or len(after)!=5 or after[:3]!=[self.workspace,project,publication]
                    or not isinstance(after[3],str) or len(after[3])>40 or datetime.fromisoformat(after[3]).tzinfo is None
                    or not re.fullmatch(r'nowa_[a-f0-9]{32}',after[4])):raise ValueError()
            except (ValueError,TypeError,IndexError):raise WorkflowError('NATIVE_OFFICIAL_WINNER_PAGE_INVALID',400) from None
        with self.store.transaction() as con:
            self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            if publication:self.analytics.publications.get(project,publication,con=con)
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if publication:where+=' AND publication_id=?';params.append(publication)
            if after:where+=' AND (created_at<? OR (created_at=? AND assessment_id<?))';params.extend([after[3],after[3],after[4]])
            rows=con.execute('SELECT * FROM native_official_winner_assessments WHERE '+where+' ORDER BY created_at DESC,assessment_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,publication,rows[limit-1]['created_at'],rows[limit-1]['assessment_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-official-winner-page-v1','workspace_id':self.workspace,'project_id':project,'publication_id':publication,
                'items':[self.read(con,row) for row in rows[:limit]],'truncated':len(rows)>limit,'next_cursor':next_cursor,
                'recommendation_only':True,'automatic_action':False,'external_call':False,'publishing_enabled':False,'token_returned':False}
