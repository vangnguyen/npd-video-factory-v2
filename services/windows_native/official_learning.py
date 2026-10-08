"""Frozen descriptive channel learning over qualified Native winner sources only."""
import base64,json,re,uuid
from datetime import datetime
from collections import Counter
from pydantic import ValidationError
from .contracts import WorkflowError,digest
from .official_winners import NativeOfficialWinners
from .official_analytics import typed
from .official_learning_models import Create
from .official_publications import utc
from .store import now
from app.analytics_channel_policy import bucket
from app.learning_models import LearningObservation,aggregate,DIMENSIONS

TABLES=('native_official_learning_snapshots','native_official_learning_events')
LIMITATIONS=['Descriptive associations of qualified relative assessment scores; no causal improvement or future performance guarantee.',
    'Latest compatible assessed distinct posts in a bounded scan are not exhaustive channel history or account totals.',
    'Report intervals do not certify complete coverage or equal publication age. Different duration buckets have their own relative winner baselines.',
    'Project annotations and edit facts are frozen; semantic labels are not independently verified.',
    'Publishing time/windows and unknown costs remain unavailable. No inferred audience window or media budget change.',
    'Protocol mocks remain synthetic and cannot be combined with real observations or used as real audience feedback.']
EXCLUSIONS={'incompatible_scope','incompatible_policy','incompatible_factor_basis','insufficient_assessment','duplicate_remote_post','post_limit'}

class NativeOfficialLearning:
    def __init__(self,winners):
        if type(winners) is not NativeOfficialWinners:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_CONFIGURATION_INVALID',400)
        self.winners=winners;self.store,self.workspace,self.clock=winners.store,winners.workspace,winners.clock
        self.frozen=(winners,self.store,self.workspace,self.clock,self.store.root.absolute())
        with self.store.transaction() as con:
            self.check();con.executescript('''CREATE TABLE IF NOT EXISTS native_official_learning_snapshots (
                learning_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,publication_id TEXT NOT NULL,
                anchor_assessment_id TEXT NOT NULL,anchor_result_snapshot_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,
                created_by TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
                CREATE INDEX IF NOT EXISTS native_official_learning_history ON native_official_learning_snapshots(workspace_id,project_id,created_at,learning_id);
                CREATE TABLE IF NOT EXISTS native_official_learning_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,learning_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_official_learning_snapshots WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_LEARNING_WORKSPACE_CHANGED')
    def check(self):
        if (self.winners,self.store,self.workspace,self.clock,self.store.root.absolute())!=self.frozen:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_CONFIGURATION_CHANGED')
        self.winners.check()
    def source(self,con,project,identity):return self.winners.read(con,self.winners.row(con,project,identity))
    @staticmethod
    def basis(value):return digest(sorted([{'factor':f['factor'],'weight':f['weight'],'available':f['score'] is not None} for f in value['assessment']['factors']],key=lambda f:f['factor']))
    @staticmethod
    def scope(value):
        # Relative winner scores are independently qualified within their own duration buckets.
        return {**{k:v for k,v in value['snapshot']['candidate']['scope'].items() if k!='duration_bucket'},
            'winner_algorithm_version':value['assessment']['algorithm_version']}
    def compatible(self,anchor,value):
        return self.scope(anchor)==self.scope(value) and utc(datetime.fromisoformat(value['snapshot']['candidate']['collected_at']))<=utc(datetime.fromisoformat(anchor['snapshot']['candidate']['collected_at']))
    def observation(self,value):
        candidate=value['snapshot']['candidate'];features=candidate['features'];evidence=features['evidence'];assessment=value['assessment']
        if assessment['state']=='insufficient_data' or assessment['score'] is None:return None
        if not any(f['factor'] in ('retention','completion') and f['score'] is not None for f in assessment['factors']):return None
        data={k:None for k in DIMENSIONS};data.update(trend_family=features['trend_cluster_id'],hook=features['hook_type'],duration=bucket(features['duration_seconds']),
            visual_strategy=features['visual_strategy'],subtitle_style=features['subtitle_template'],voice_profile=features['voice_profile'])
        try:
            return LearningObservation(snapshot_id=value['result_snapshot_id'],publication_id=value['publication_id'],assessment_id=value['assessment_id'],render_id=evidence['render_job_id'],
                timeline_version_id=evidence['canonical_timeline_sha256'],feature_context_sha256=evidence['feature_context_sha256'],
                remote_post_sha256=digest([self.workspace,candidate['scope']['target_binding_sha256'],candidate['remote_post_id']]),collected_at=datetime.fromisoformat(candidate['collected_at']),
                score=assessment['score'],features=data,winner_policy_sha256=value['snapshot']['policy_sha256'],assessment_basis_sha256=self.basis(value))
        except (ValueError,TypeError):return None
    def reference(self,value):
        return {'project_id':value['project_id'],'assessment_id':value['assessment_id'],'snapshot_sha256':value['snapshot_sha256'],
            'candidate_sha256':digest(value['snapshot']['candidate']),'observation':self.observation(value).model_dump(mode='json')}
    def selection(self,con,anchor,policy):
        rows=con.execute('''SELECT a.* FROM native_official_winner_assessments a
            JOIN native_official_analytics_snapshots r ON a.result_snapshot_id=r.result_snapshot_id AND a.workspace_id=r.workspace_id
            AND a.project_id=r.project_id AND a.publication_id=r.publication_id AND a.sync_id=r.sync_id
            WHERE a.workspace_id=? AND r.collected_at<=? ORDER BY r.collected_at DESC,a.created_at DESC,a.assessment_id DESC LIMIT 501''',
            (self.workspace,anchor['snapshot']['candidate']['collected_at'])).fetchall()
        selected=[];seen=set();excluded=Counter();posts_truncated=False
        for row in rows[:500]:
            value=self.winners.read(con,row)
            if not self.compatible(anchor,value):excluded['incompatible_scope']+=1;continue
            if value['snapshot']['policy_sha256']!=anchor['snapshot']['policy_sha256']:excluded['incompatible_policy']+=1;continue
            candidate=value['snapshot']['candidate'];remote=digest([self.workspace,candidate['scope']['target_binding_sha256'],candidate['remote_post_id']])
            if remote in seen:excluded['duplicate_remote_post']+=1;continue
            # A later insufficient/basis-changed assessment cannot revive a stale sufficient one.
            seen.add(remote)
            if self.basis(value)!=self.basis(anchor):excluded['incompatible_factor_basis']+=1;continue
            if self.observation(value) is None:excluded['insufficient_assessment']+=1;continue
            if len(selected)>=policy.maximum_posts:posts_truncated=True;excluded['post_limit']+=1;continue
            selected.append(self.reference(value))
        return selected,len(rows)>500,posts_truncated,dict(excluded)
    def row(self,con,project,identity):
        self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        row=con.execute('SELECT * FROM native_official_learning_snapshots WHERE learning_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_NOT_FOUND',404)
        return row
    def read(self,con,row):
        self.check();value=dict(row)
        try:
            snapshot=json.loads(value.pop('snapshot_json'));request=Create.model_validate({**snapshot['request'],'request_key':'internal-native-learning-history-key'});refs=snapshot['selected_assessments']
            anchor=self.source(con,value['project_id'],value['anchor_assessment_id']);excluded=snapshot['excluded_rows']
            if (snapshot['schema_version']!='native-official-learning-snapshot-v1' or digest(snapshot)!=value['snapshot_sha256']
                or any(snapshot[k]!=value[k] for k in ('workspace_id','project_id','publication_id','anchor_assessment_id','anchor_result_snapshot_id'))
                or value['workspace_id']!=self.workspace or digest(snapshot['request'])!=value['request_fingerprint'] or request.assessment_id!=value['anchor_assessment_id']
                or request.expected_assessment_sha256!=anchor['snapshot_sha256'] or anchor['publication_id']!=value['publication_id'] or anchor['result_snapshot_id']!=value['anchor_result_snapshot_id']
                or snapshot['anchor_candidate_sha256']!=digest(anchor['snapshot']['candidate']) or snapshot['scope']!=self.scope(anchor)
                or snapshot['winner_policy_sha256']!=anchor['snapshot']['policy_sha256'] or snapshot['winner_factor_basis_sha256']!=self.basis(anchor)
                or request.acknowledged_protocol_mock is not anchor['mock'] or snapshot['authority']['token_id']!=value['created_by']
                or not isinstance(refs,list) or len(refs)>request.policy.maximum_posts or type(snapshot['candidate_rows_truncated']) is not bool or type(snapshot['selected_posts_truncated']) is not bool
                or snapshot['recommendation_only'] is not True or snapshot['automatic_action'] is not False or snapshot['publishing_enabled'] is not False
                or snapshot['limitations']!=LIMITATIONS or not isinstance(excluded,dict) or set(excluded)-EXCLUSIONS
                or any(type(n) is not int or n<0 for n in excluded.values()) or sum(excluded.values())>500):raise ValueError()
            observations=[]
            for ref in refs:
                original=self.source(con,ref['project_id'],ref['assessment_id'])
                if not self.compatible(anchor,original) or original['snapshot']['policy_sha256']!=snapshot['winner_policy_sha256'] or self.basis(original)!=snapshot['winner_factor_basis_sha256'] or self.observation(original) is None or ref!=self.reference(original):raise ValueError()
                observations.append(LearningObservation.model_validate(ref['observation']))
            dimensions=[v.model_dump(mode='json') for v in aggregate(observations,request.policy)]
            if snapshot['observations']!=[v.model_dump(mode='json') for v in observations] or snapshot['dimensions']!=dimensions:raise ValueError()
            value.pop('key_sha256')
            return {**value,'schema_version':'native-official-learning-history-v1','snapshot':snapshot,'dimensions':dimensions,'observation_count':len(observations),
                'mock':anchor['mock'],'real_audience_observation':not anchor['mock'],'recommendation_only':True,'automatic_action':False,'external_call':False,
                'publishing_enabled':False,'token_returned':False,'real_provider_tested':False,'status':'recommendations_available' if any(v['state']=='recommendations_available' for v in dimensions) else 'insufficient_data' if all(v['state']=='insufficient_data' for v in dimensions) else 'no_positive_association'}
        except (ValueError,TypeError,KeyError,ValidationError):raise WorkflowError('NATIVE_OFFICIAL_LEARNING_EVIDENCE_CHANGED') from None
    def create(self,project,payload,*,principal):
        self.check();payload=typed(payload,Create);authority=self.winners.analytics.identity(principal);request=payload.model_dump(mode='json',exclude={'request_key'});key=digest(payload.request_key);fp=digest(request)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_official_learning_snapshots WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fp:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_IDEMPOTENCY_CONFLICT')
                return self.read(con,prior),True
            anchor=self.source(con,project,payload.assessment_id)
            if anchor['snapshot_sha256']!=payload.expected_assessment_sha256:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_ASSESSMENT_CHANGED')
            if payload.acknowledged_protocol_mock is not anchor['mock']:raise WorkflowError('NATIVE_OFFICIAL_LEARNING_MOCK_ACK_REQUIRED')
            candidate=anchor['snapshot']['candidate']
            if not self.winners.known_scope(candidate):raise WorkflowError('NATIVE_OFFICIAL_LEARNING_QUALIFIED_SCOPE_REQUIRED')
            if utc(datetime.fromisoformat(candidate['collected_at']))>utc(self.clock()):raise WorkflowError('NATIVE_OFFICIAL_LEARNING_FUTURE_OBSERVATION')
            selected,truncated,posts_truncated,excluded=self.selection(con,anchor,payload.policy);observations=[LearningObservation.model_validate(r['observation']) for r in selected]
            snapshot={'schema_version':'native-official-learning-snapshot-v1','workspace_id':self.workspace,'project_id':project,'publication_id':anchor['publication_id'],
                'anchor_assessment_id':anchor['assessment_id'],'anchor_result_snapshot_id':anchor['result_snapshot_id'],'anchor_candidate_sha256':digest(candidate),
                'request':request,'authority':authority,'scope':self.scope(anchor),'winner_policy_sha256':anchor['snapshot']['policy_sha256'],'winner_factor_basis_sha256':self.basis(anchor),
                'selected_assessments':selected,'observations':[v.model_dump(mode='json') for v in observations],'dimensions':[v.model_dump(mode='json') for v in aggregate(observations,payload.policy)],
                'candidate_rows_truncated':truncated,'selected_posts_truncated':posts_truncated,'excluded_rows':excluded,
                'recommendation_only':True,'automatic_action':False,'publishing_enabled':False,'limitations':LIMITATIONS}
            self.winners.analytics.identity(authority=authority);identity,stamp='nols_'+uuid.uuid4().hex,now()
            con.execute('INSERT INTO native_official_learning_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,anchor['publication_id'],anchor['assessment_id'],anchor['result_snapshot_id'],key,fp,digest(snapshot),json.dumps(snapshot),authority['token_id'],stamp))
            con.execute('INSERT INTO native_official_learning_events(learning_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
                (identity,self.workspace,project,'analytics.official.learning.saved',authority['token_id'],json.dumps({'observations':len(observations),'mock':anchor['mock'],'recommendation_only':True,'external_call':False}),stamp))
            value=self.read(con,self.row(con,project,identity));bridge=getattr(self.store,'bridge',None)
            if bridge is not None:bridge.capture_qualified(con,'learning',self,project,identity)
            return value,False
    def get(self,project,identity):
        with self.store.transaction() as con:return self.read(con,self.row(con,project,identity))
    def page(self,project,*,publication=None,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100 or publication is not None and (not isinstance(publication,str) or not re.fullmatch(r'nopu_[a-f0-9]{32}',publication)):raise WorkflowError('NATIVE_OFFICIAL_LEARNING_PAGE_INVALID',400)
        after=None
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or len(cursor)>2048:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if (not isinstance(after,list) or len(after)!=5 or after[:3]!=[self.workspace,project,publication] or not isinstance(after[3],str) or len(after[3])>40
                    or datetime.fromisoformat(after[3]).tzinfo is None or not re.fullmatch(r'nols_[a-f0-9]{32}',after[4])):raise ValueError()
            except (ValueError,TypeError,IndexError):raise WorkflowError('NATIVE_OFFICIAL_LEARNING_PAGE_INVALID',400) from None
        with self.store.transaction() as con:
            self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            if publication:self.winners.analytics.publications.get(project,publication,con=con)
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if publication:where+=' AND publication_id=?';params.append(publication)
            if after:where+=' AND (created_at<? OR (created_at=? AND learning_id<?))';params.extend([after[3],after[3],after[4]])
            rows=con.execute('SELECT * FROM native_official_learning_snapshots WHERE '+where+' ORDER BY created_at DESC,learning_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,publication,rows[limit-1]['created_at'],rows[limit-1]['learning_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-official-learning-page-v1','workspace_id':self.workspace,'project_id':project,'publication_id':publication,'items':[self.read(con,r) for r in rows[:limit]],
                'truncated':len(rows)>limit,'next_cursor':next_cursor,'recommendation_only':True,'automatic_action':False,'external_call':False,'publishing_enabled':False,'token_returned':False}
