"""Durable, workspace-scoped Trend Radar feeding the certified Native idea flow."""
import asyncio
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import json,threading,time,uuid
from app.trend_models import TrendCollectionRequest
from app.trend_providers import TrendProviderNotConfigured
from app.personalized_opportunities import rank_estimate
from .contracts import WorkflowError,digest
from .trend_radar_models import RadarRecord,SignalEvidence,CollectRequest,RefreshRequest,HandoffRequest
from .trend_radar_engine import clusters,estimate
from .trend_radar_providers import registry,public_reference
from .channel_profiles import select

VIEWS=('trending-now','rising-fast','breakout','early-signals','cross-platform','low-competition','high-monetization','near-saturation')

class NativeTrendRadar:
    def __init__(self,intelligence,analytics,*,workspace,providers=None,feed_registry=None,owner_enabled=False,clock=lambda:datetime.now(timezone.utc),observer=None):
        self.intelligence,self.store,self.analytics=intelligence,intelligence.store,analytics
        self.workspace,self.clock,self.observer=workspace,clock,observer
        if providers is not None and (feed_registry is not None or owner_enabled):raise WorkflowError('TREND_PROVIDER_CONFIGURATION_CONFLICT',400)
        self.providers=providers or registry(feed_registry,workspace=workspace,owner_enabled=owner_enabled)
        self.stop=threading.Event();self.wake=threading.Event();self.thread=threading.Thread(target=self.work,daemon=True,name='native-trend-radar-worker')
        with self.store.transaction() as con:
            con.execute("CREATE INDEX IF NOT EXISTS native_radar_scope ON records(kind,json_extract(document,'$.workspace_id'),json_extract(document,'$.record_type'))")

    def timestamp(self):
        value=self.clock()
        if not isinstance(value,datetime) or value.tzinfo is None:raise WorkflowError('TREND_TIME_INVALID',400)
        return value.astimezone(timezone.utc)

    def get(self,identifier,record_type=None,con=None):
        value=self.store.get(identifier,'RadarRecord',con)
        if value['workspace_id']!=self.workspace or (record_type and value['record_type']!=record_type):raise WorkflowError('TREND_RECORD_NOT_FOUND',404)
        return value

    def records(self,record_type,con,limit=2001):
        rows=con.execute("SELECT id FROM records WHERE kind='RadarRecord' AND json_extract(document,'$.workspace_id')=? AND json_extract(document,'$.record_type')=? ORDER BY rowid DESC LIMIT ?",(self.workspace,record_type,limit)).fetchall()
        return [self.get(row[0],record_type,con) for row in rows]

    def put(self,record_type,payload,con,identifier=None,previous=None):
        value=RadarRecord(id=identifier or uuid.uuid4().hex,workspace_id=self.workspace,record_type=record_type,payload=payload,
            provenance={'origin':'native-trend-radar-v1','recommendation_only':True,'automatic_production':False}).model_dump(mode='json')
        return self.store.put('RadarRecord',value,previous['version'] if previous else None,con)

    def identity(self,action,key):return uuid.uuid5(uuid.NAMESPACE_URL,'vf-native-trend/'+self.workspace+'/'+action+'/'+digest(key)).hex
    def replay(self,con,action,payload):
        identifier=self.identity(action,payload.request_key)
        prior=con.execute('SELECT id FROM records WHERE id=?',(identifier,)).fetchone()
        request=payload.model_dump(mode='json',exclude={'request_key'})
        if prior:
            value=self.get(identifier,con=con)
            if value['payload'].get('request_sha256')!=digest(request):raise WorkflowError('TREND_IDEMPOTENCY_CONFLICT',409)
            return identifier,request,value
        return identifier,request,None

    def states(self):
        return {'schema_version':'native-trend-radar-providers-v1','workspace_id':self.workspace,'providers':self.providers.definitions(),
            'automatic_collection_enabled':False,'fixture_enabled_by_default':False,'publishing_enabled':False,
            'views':list(VIEWS),'clustering':'native-trend-clustering-v2','scoring':'trend-opportunity-v1',
            'learning_mode':'recommendation_only','real_provider_tested':False,'production_deployed':False}

    def collect(self,payload,*,actor):
        if not isinstance(payload,CollectRequest):payload=CollectRequest.model_validate(payload)
        with self.store.transaction() as con:
            identifier,request,prior=self.replay(con,'collect',payload)
            if prior:return prior
            definition=next((v for v in self.providers.definitions() if v['provider_key']==payload.provider_key),None)
            if definition is None:raise WorkflowError('TREND_PROVIDER_NOT_FOUND',400)
            if definition['source_type']=='fixture' and not payload.fixture_acknowledged:raise WorkflowError('TREND_FIXTURE_ACKNOWLEDGEMENT_REQUIRED',400)
            configured=definition['authorized_access'] and definition['status'] not in ('not_configured','unavailable')
            content={**request};content.pop('refresh');cache_key=digest([content,definition,self.workspace])
            prior_collections=self.records('collection',con,501)
            cached=next((v for v in prior_collections if v['payload'].get('cache_key')==cache_key and v['payload']['status']=='succeeded'
                and self.timestamp()-timedelta(minutes=15)<=datetime.fromisoformat(v['payload']['collected_at'])<=self.timestamp()),None) if not payload.refresh else None
            value=self.put('collection',{'request':request,'request_sha256':digest(request),'provider_definition':definition,
                'provider_definition_sha256':digest(definition),'cache_key':cache_key,'actor_ref':actor,
                'status':'not_configured' if not configured else 'cached' if cached else 'queued','signal_ids':cached['payload']['signal_ids'] if cached else [],
                'cached_collection_id':cached['id'] if cached else None,'collected_at':cached['payload']['collected_at'] if cached else None,
                'failure_code':'TREND_PROVIDER_NOT_CONFIGURED' if not configured else None,
                'mock':definition['source_type']=='fixture','external_call':False,'provider_calls':0},con,identifier)
            self.store.decision(con,identifier,'human_requested_trend_collection',{'actor_ref':actor,'request_sha256':digest(request)})
        self.wake.set();return value

    def cancel(self,identifier,expected,*,actor):
        with self.store.transaction() as con:
            value=self.get(identifier,'collection',con)
            if value['version']!=expected or type(expected) is not int:raise WorkflowError('TREND_STALE_VERSION',409)
            if value['payload']['status'] in ('succeeded','cached'):raise WorkflowError('TREND_COLLECTION_ALREADY_COMPLETE',409)
            result=self.put('collection',{**value['payload'],'status':'cancelled'},con,identifier,value)
            self.store.decision(con,identifier,'human_cancelled_trend_collection',{'actor_ref':actor})
            return result

    def recover(self):
        with self.store.transaction() as con:
            for value in self.records('collection',con):
                if value['payload']['status']=='running':self.put('collection',{**value['payload'],'status':'failed','failure_code':'TREND_INTERRUPTED_NO_AUTOMATIC_REPLAY'},con,value['id'],value)
    def start(self):self.recover();self.thread.start()
    def close(self):
        self.stop.set();self.wake.set()
        if self.thread.is_alive():self.thread.join(timeout=2)
    def work(self):
        while not self.stop.is_set():
            if not self.process():self.wake.wait(1);self.wake.clear()

    def process(self):
        with self.store.transaction() as con:
            queued=[v for v in self.records('collection',con) if v['payload']['status']=='queued']
            if not queued:return False
            value=min(queued,key=lambda v:(v['created_at'],v['id']))
            value=self.put('collection',{**value['payload'],'status':'running'},con,value['id'],value)
        started=time.monotonic();code=None;result=[];receipt=None;called=False
        try:
            provider=self.providers.get(value['payload']['request']['provider_key'])
            if digest(provider.registry_definition())!=value['payload']['provider_definition_sha256']:raise WorkflowError('TREND_PROVIDER_CONFIGURATION_CHANGED')
            request=CollectRequest.model_validate({**value['payload']['request'],'request_key':'internal-trend-collection'})
            provider_request=TrendCollectionRequest.model_validate(request.model_dump(exclude={'request_key','fixture_acknowledged','refresh'}))
            async def execute():return await asyncio.wait_for(provider.collect_signals(provider_request),timeout=60)
            called=True;result=asyncio.run(execute())
            if not isinstance(result,list) or len(result)>request.limit:raise WorkflowError('TREND_PROVIDER_RESULT_INVALID')
            result=[SignalEvidence.model_validate(v.model_dump(mode='json') if hasattr(v,'model_dump') else v).model_dump(mode='json') for v in result]
            for item in result:
                public_reference(item['source_reference'])
                if datetime.fromisoformat(item['observed_at'])>self.timestamp()+timedelta(seconds=5):raise WorkflowError('TREND_FUTURE_OBSERVATION_INVALID')
            receipt=getattr(provider,'last_receipt',None)
        except TrendProviderNotConfigured:code='TREND_PROVIDER_NOT_CONFIGURED'
        except Exception as error:code=error.code if isinstance(error,WorkflowError) else 'TREND_COLLECTION_FAILED'
        with self.store.transaction() as con:
            current=self.get(value['id'],'collection',con)
            if current['payload']['status']!='running':return True
            identifiers=[]
            if not code:
                for item in result:
                    raw_hash=digest(item);identity=self.identity('signal',digest([request.provider_key,raw_hash]))
                    prior=con.execute('SELECT id FROM records WHERE id=?',(identity,)).fetchone()
                    if prior:
                        saved=self.get(identity,'signal',con)
                        if saved['payload']['raw_signal_hash']!=raw_hash:raise WorkflowError('TREND_SIGNAL_INTEGRITY_FAILED')
                    else:self.put('signal',{'signal':item,'raw_signal_hash':raw_hash,'provider_key':request.provider_key,
                        'provider_definition_sha256':value['payload']['provider_definition_sha256'],'mock':value['payload']['mock'],
                        'source_collection_id':value['id'],'reference_only':True,'download_allowed':False},con,identity)
                    identifiers.append(identity)
            completed=self.put('collection',{**current['payload'],'status':'failed' if code else 'succeeded','failure_code':code,
                'signal_ids':identifiers,'collected_at':self.timestamp().isoformat(),'receipt':receipt,'provider_calls':int(called),
                'external_call':bool(called and not value['payload']['mock'])},con,value['id'],current)
            self.store.decision(con,value['id'],'trend_collection_finished',{'status':completed['payload']['status'],'signal_count':len(identifiers),'failure_code':code})
        if self.observer:self.observer.emit('worker_step',job_id=value['id'],stage='trend_collection',provider=value['payload']['request']['provider_key'],duration=time.monotonic()-started)
        return True

    def refresh(self,payload,*,actor):
        if not isinstance(payload,RefreshRequest):payload=RefreshRequest.model_validate(payload)
        selection=select(payload.channel_profile_ref);as_of=self.timestamp()
        with self.store.transaction() as con:
            identifier,request,prior=self.replay(con,'refresh',payload)
            if prior:return prior
            all_signals=self.records('signal',con);latest={}
            for value in all_signals[:2000]:
                item=SignalEvidence.model_validate(value['payload']['signal'])
                if digest(item.model_dump(mode='json'))!=value['payload']['raw_signal_hash']:raise WorkflowError('TREND_SIGNAL_INTEGRITY_FAILED')
                if not as_of-timedelta(days=payload.lookback_days)<=item.observed_at<=as_of:continue
                key=(value['payload']['provider_key'],item.source,str(item.source_reference))
                previous=latest.get(key)
                if previous is None or item.observed_at>datetime.fromisoformat(previous['payload']['signal']['observed_at']):latest[key]=value
            values=sorted(latest.values(),key=lambda v:(v['payload']['signal']['observed_at'],v['id']),reverse=True)[:200]
            existing=self.records('cluster',con);used=set();assessments=[]
            feedback=None
            if payload.learning_snapshot_id:
                learning=self.get(payload.learning_snapshot_id,'learning',con)['payload'];scope=learning['scope']
                if scope['channel_profile_ref']!=payload.channel_profile_ref or scope['channel_profile_sha256']!=selection['profile_sha256'] or scope['platform']!=payload.platform:
                    raise WorkflowError('TREND_LEARNING_SCOPE_MISMATCH',409)
                if scope['mock'] and any(not v['payload']['mock'] for v in values):raise WorkflowError('TREND_MOCK_HISTORY_CANNOT_RANK_REAL_SIGNALS',409)
                feedback={'learning_snapshot_id':payload.learning_snapshot_id,'content_sha256':digest(learning),'scope':scope,'recommendations':learning['recommendations']}
            for draft,members,edges in clusters(values,payload.clustering,as_of):
                references=sorted({v['payload']['signal']['source_reference'] for v in members})
                matching=[v for v in existing if v['id'] not in used and (set(v['payload']['source_references']) & set(references) or v['payload']['canonical_key']==draft.canonical_key)]
                previous=min(matching,key=lambda v:(v['created_at'],v['id'])) if matching else None
                cluster_id=previous['id'] if previous else self.identity('cluster',draft.canonical_key)
                if cluster_id in used:cluster_id=self.identity('cluster',digest([draft.canonical_key,draft.signal_ids]))
                if previous is None and con.execute('SELECT id FROM records WHERE id=?',(cluster_id,)).fetchone():previous=self.get(cluster_id,'cluster',con)
                used.add(cluster_id)
                data=asdict(draft);data['first_observed_at']=draft.first_observed_at.isoformat();data['last_observed_at']=draft.last_observed_at.isoformat()
                cluster=self.put('cluster',{**data,'source_references':references,'similarity_evidence':edges,'clustering_policy':payload.clustering.model_dump(mode='json'),
                    'as_of':as_of.isoformat(),'lifecycle_is_estimate':True,'scope_lookback_days':payload.lookback_days},con,cluster_id,previous)
                score=estimate(draft,members,payload,selection)
                ranking=rank_estimate(score['total_score'],cluster_id,feedback,payload.ranking_policy)
                assessment_id=self.identity('assessment',digest([identifier,cluster_id]))
                assessment=self.put('assessment',{'cluster_id':cluster_id,'cluster_version':cluster['version'],'cluster_sha256':digest(cluster),
                    'cluster_snapshot':cluster,'signal_ids':draft.signal_ids,'signal_hashes':{v['id']:v['payload']['raw_signal_hash'] for v in members},
                    'channel_selection':selection,'platform':payload.platform,'business_objective':payload.business_objective,
                    'score':score,'ranking':ranking,'as_of':as_of.isoformat(),'mock':all(v['payload']['mock'] for v in members),
                    'mixed_source_modes':len({v['payload']['mock'] for v in members})>1,'automatic_production':False},con,assessment_id)
                assessments.append(assessment_id)
            batch=self.put('assessment',{'record_role':'refresh_batch','request':request,'request_sha256':digest(request),
                'assessment_ids':assessments,'as_of':as_of.isoformat(),'latest_signal_count':len(values),'source_scan_truncated':len(all_signals)>2000,
                'selected_signals_truncated':len(latest)>200,'actor_ref':actor,'automatic_production':False},con,identifier)
            self.store.decision(con,identifier,'human_refreshed_trend_estimates',{'actor_ref':actor,'assessment_count':len(assessments)})
            return batch

    def history(self,identifier,con):
        rows=con.execute('SELECT * FROM versions WHERE id=? ORDER BY version DESC LIMIT 101',(identifier,)).fetchall();result=[]
        for row in rows[:100]:
            try:value=RadarRecord.model_validate_json(row['document']).model_dump(mode='json')
            except ValueError:raise WorkflowError('TREND_HISTORY_INTEGRITY_FAILED',409) from None
            if row['kind']!='RadarRecord' or value['workspace_id']!=self.workspace or value['id']!=identifier or value['version']!=row['version'] or digest(value)!=row['sha256']:raise WorkflowError('TREND_HISTORY_INTEGRITY_FAILED',409)
            result.append(value)
        return list(reversed(result)),len(rows)>100

    def detail(self,identifier):
        with self.store.transaction() as con:
            value=self.get(identifier,con=con);payload=value['payload']
            signals=[self.get(i,'signal',con) for i in payload.get('signal_ids',[])]
            history,truncated=self.history(identifier,con);cluster_history=[];cluster_truncated=False;observed={}
            if payload.get('cluster_id'):
                self.get(payload['cluster_id'],'cluster',con);cluster_history,cluster_truncated=self.history(payload['cluster_id'],con)
                for version in reversed(cluster_history):
                    for sid in version['payload']['signal_ids']:
                        if sid not in observed and len(observed)<200:observed[sid]=self.get(sid,'signal',con)
            return {'record':value,'sha256':digest(value),'signals':signals,'history':history,'history_truncated':truncated,
                'cluster_history':cluster_history,'cluster_history_truncated':cluster_truncated,'signal_observation_history':list(observed.values()),
                'signal_history_bounded':True,'automatic_action':False}

    def page(self,*,view='trending-now',channel=None,platform=None,target_platform=None,country=None,language=None,niche=None,format=None,objective=None,days=30,offset=0,limit=25):
        if view not in VIEWS or type(days) is not int or not 1<=days<=365 or type(offset) is not int or not 0<=offset<=2000 or type(limit) is not int or not 1<=limit<=100:raise WorkflowError('TREND_PAGE_INVALID',400)
        with self.store.transaction() as con:
            raw=self.records('assessment',con);latest={};seen=set()
            for value in raw[:2000]:
                p=value['payload']
                if p.get('record_role')=='refresh_batch':continue
                selection=p['channel_selection'];cluster=p['cluster_snapshot']['payload'];score=p['score'];coverage=score['measured_field_coverage']
                key=(p['cluster_id'],selection['profile']['profile_ref'],p['platform'],p['business_objective'])
                if key in seen:continue
                seen.add(key)
                if datetime.fromisoformat(p['as_of'])<self.timestamp()-timedelta(days=days):continue
                if channel and selection['profile']['profile_ref']!=channel:continue
                if platform and platform not in cluster['platforms']:continue
                if target_platform and target_platform!=p['platform']:continue
                if niche and selection['profile']['niche_profile']['niche']!=niche:continue
                if objective and p['business_objective']!=objective:continue
                members=[self.get(i,'signal',con)['payload']['signal'] for i in p['signal_ids']]
                if country and not any(v['country']==country for v in members):continue
                if language and not any(v['language']==language for v in members):continue
                if format and not any(v['format']==format for v in members):continue
                if view=='rising-fast' and cluster['lifecycle'] not in ('rising','breakout'):continue
                if view=='breakout' and cluster['lifecycle']!='breakout':continue
                if view=='early-signals' and cluster['lifecycle'] not in ('discovered','rising'):continue
                if view=='cross-platform' and len(cluster['platforms'])<2:continue
                if view=='low-competition' and (not coverage['creator_count'] or score['components']['competition']>=30):continue
                if view=='high-monetization' and score['components']['monetization_fit']<80:continue
                if view=='near-saturation' and (not (coverage['content_count'] or coverage['creator_count']) or score['components']['saturation']<65):continue
                if key not in latest:latest[key]={**value,'sha256':digest(value)}
            ordered=sorted(latest.values(),key=lambda v:(-v['payload']['ranking']['personalized_planning_score'],v['id']))
            return {'schema_version':'native-trend-radar-page-v1','workspace_id':self.workspace,'view':view,'items':ordered[offset:offset+limit],
                'next_offset':offset+limit if offset+limit<len(ordered) else None,'scan_truncated':len(raw)>2000,
                'estimated':True,'automatic_production':False,'publishing_enabled':False}

    def handoff(self,payload,*,actor):
        if not isinstance(payload,HandoffRequest):payload=HandoffRequest.model_validate(payload)
        with self.store.transaction() as con:
            identifier,request,prior=self.replay(con,'handoff',payload)
            if prior:return prior
            assessment=self.get(payload.assessment_id,'assessment',con)
            if digest(assessment)!=payload.expected_sha256 or assessment['payload'].get('record_role')=='refresh_batch':raise WorkflowError('TREND_ASSESSMENT_BINDING_CHANGED',409)
            p=assessment['payload'];signals=[self.get(i,'signal',con) for i in p['signal_ids']]
            for v in signals:
                if v['payload']['raw_signal_hash']!=p['signal_hashes'][v['id']]:raise WorkflowError('TREND_SIGNAL_INTEGRITY_FAILED')
            context={'schema_version':'native-trend-research-context-v1','workspace_id':self.workspace,'assessment':assessment,
                'assessment_sha256':digest(assessment),'signals':signals,'channel_selection':p['channel_selection'],
                'actor_ref':actor,'reference_only':True,'creator_media_download_allowed':False,'automatic_production':False}
            context['sha256']=digest(context)
            urls=p['cluster_snapshot']['payload']['source_references'][:5]
            bundle=self.intelligence.create(p['cluster_snapshot']['payload']['topic'],p['channel_selection']['profile']['content_profile_id'],urls,
                trend_context=context,channel_profile=p['channel_selection'],con=con)
            value=self.put('handoff',{'request':request,'request_sha256':digest(request),'research_run_id':bundle['run']['id'],
                'opportunity_id':bundle['opportunity']['id'],'context_sha256':context['sha256'],'actor_ref':actor,
                'production_dispatch':False,'provider_calls':0,'next':'human_research_and_idea_review'},con,identifier)
            self.store.decision(con,payload.assessment_id,'human_selected_trend_for_research',{'actor_ref':actor,'handoff_id':identifier,'research_run_id':bundle['run']['id']})
            return value
