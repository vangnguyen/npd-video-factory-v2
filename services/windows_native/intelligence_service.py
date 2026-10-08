"""Explicit local intelligence workflow; approved briefs reuse native production."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
import uuid
from .contracts import WorkflowError, canonical, digest, file_sha
from .intelligence_models import ContentBrief, ContentIdea, Opportunity, ResearchFinding, ResearchRun, ResearchSource, TrendSignal
from .intelligence_store import IntelligenceStore
from .idea_engine import CandidateDraft, OpenAIIdeaProvider, validate_candidates
from .idea_scoring import configuration, score
from .research import PublicWebResearchProvider, validate_findings
from .observability import Observer

IDEA_EDITABLE=set(CandidateDraft.model_fields)-{'supporting_research','evidence_references'}
BRIEF_EDITABLE={'objective','audience','angle','hook','talking_points','cta','constraints'}


def brief_content(brief):
    return {k:v for k,v in brief.items() if k not in {'version','created_at','updated_at','status','approval','provenance'}}


def draft_brief_fields(idea,findings):
    by_id={f['id']:f for f in findings}
    return {'objective':'Giải thích chủ đề có nguồn và mời người xem đặt câu hỏi','audience':idea['target_audience'],
            'key_facts':[by_id[fid]['claim'] for fid in idea['supporting_research']],'angle':idea['angle'],'hook':idea['hook'],
            'talking_points':idea['key_points'],'cta':idea['cta'],'source_references':idea['evidence_references'],
            'constraints':['Chỉ dùng dữ kiện nguồn đã trích; ghi rõ thời điểm và giới hạn.','Suy luận biên tập chưa phải dữ kiện đã xác minh.',
                           'Không cam kết giá, tiến độ, pháp lý hoặc lợi nhuận.','Không xuất bản tự động.',
                           'Thời lượng đề xuất: '+str(idea['estimated_duration'])+' giây; giọng đọc giữ preset đã nghiệm thu.']}


class IntelligenceService:
    def __init__(self,config,production,*,research_provider=None,idea_provider=None,observer=None):
        self.config=config; self.production=production
        self.observer = observer or Observer()
        self.store=IntelligenceStore(config.data_root)
        self.catalog=configuration()
        self.research_provider=research_provider or PublicWebResearchProvider(config.data_root/'research-sources')
        self.idea_provider=idea_provider or OpenAIIdeaProvider(config)
        self.stop=threading.Event(); self.wake=threading.Event()
        self.thread=threading.Thread(target=self.work,daemon=True,name='native-intelligence-worker')

    def start(self):
        with self.store.transaction() as con:
            for row in con.execute("SELECT * FROM operations WHERE status='RUNNING'").fetchall():
                error={'code':'INTELLIGENCE_INTERRUPTED_OUTCOME_UNKNOWN_NO_REPLAY','automatic_replay':False}
                con.execute("UPDATE operations SET status='FAILED',error=? WHERE id=?",(canonical(error).decode(),row['id']))
                run=self.store.get(row['run_id'],'ResearchRun',con)
                self.store.put('ResearchRun',{**run,'status':'FAILED','error':error},run['version'],con)
        self.thread.start()

    def profiles(self): return {'profiles':self.catalog['profiles'],'scoring':self.catalog['scoring'],'scoring_type':'HEURISTIC_SCORING','research_provider':self.research_provider.key}

    def fork_research_snapshot(self,identifier,version,reviewer,note):
        """Reuse retained research for a new human-directed production; never replay providers."""
        human=self.human(reviewer,note=note)
        bundle=self.bundle(identifier); original=bundle['run']
        if original['version']!=version: raise WorkflowError('INTELLIGENCE_STALE_VERSION_RELOAD')
        candidates=[i for i in bundle['ideas'] if i['generation']==original['generation'] and i['status'] not in {'REJECTED','SUPERSEDED'}]
        if len(candidates)!=5: raise WorkflowError('INTELLIGENCE_FIVE_CURRENT_CANDIDATES_REQUIRED')
        self.verify_sources(bundle['sources'],bundle['findings'])
        fields=lambda value:{k:v for k,v in value.items() if k not in {'id','created_at','updated_at','version','provenance','score'}}
        run=ResearchRun(query=original['query'],context=original['context'],provider=original['provider'],model=original['model'],status='IDEAS',
            generation=1,source_ids=original['source_ids'],provider_metadata={'cached_research_snapshot':True,'actual_provider_calls':0,'source_retrievals_this_run':0,'originating_metadata':original['provider_metadata']},
            provenance={'origin':'human_directed_cached_research_fork','original_run_id':identifier,'original_run_version':version,'decision':human})
        opportunity=Opportunity(**{**fields(bundle['opportunity']),'run_id':run.id,'status':'NEW','selected_idea_id':None,'brief_id':None,'production_project_id':None},provenance={'origin':'human_directed_research_fork','original_opportunity_id':bundle['opportunity']['id']})
        findings=[ResearchFinding(**{**fields(f),'run_id':run.id},provenance={'origin':'retained_finding_reused','original_finding_id':f['id'],'original_finding_version':f['version'],'original_provenance':f['provenance']}) for f in bundle['findings']]
        mapping={old['id']:new.id for old,new in zip(bundle['findings'],findings)}
        ideas=[ContentIdea(**{**fields(i),'run_id':run.id,'opportunity_id':opportunity.id,'generation':1,'status':'CANDIDATE','supporting_research':[mapping[f] for f in i['supporting_research']]},
            provenance={'origin':'reused_actual_candidate_snapshot','original_idea_id':i['id'],'original_idea_version':i['version'],'actual_provider_calls_this_fork':0,'original_provenance':i['provenance']}) for i in candidates]
        signals=[]
        for sid in original['signal_ids']:
            signal=self.store.get(sid,'TrendSignal')
            signals.append(TrendSignal(**{**fields(signal),'run_id':run.id,'finding_ids':[mapping[f] for f in signal['finding_ids']]},provenance={'origin':'retained_signal_reused','original_signal_id':sid,'observed_at_preserved':True}))
        with self.store.transaction() as con:
            current=self.store.get(identifier,'ResearchRun',con)
            if current['version']!=version or con.execute("SELECT 1 FROM operations WHERE run_id=? AND status IN ('QUEUED','RUNNING')",(identifier,)).fetchone(): raise WorkflowError('INTELLIGENCE_OPERATION_BUSY_OR_STALE')
            for finding in findings:self.store.put('ResearchFinding',finding.model_dump(mode='json'),con=con)
            for signal in signals:self.store.put('TrendSignal',signal.model_dump(mode='json'),con=con)
            for idea in ideas:
                value=self.store.put('ContentIdea',idea.model_dump(mode='json'),con=con)
                scored=score(value,[f.model_dump(mode='json') for f in findings],bundle['sources'],original['context']['profile'],{'scoring':original['context']['scoring']},[])
                self.store.put('IdeaScore',scored.model_dump(mode='json'),con=con)
            self.store.put('Opportunity',{**opportunity.model_dump(mode='json'),'supporting_signals':[s.id for s in signals]},con=con)
            self.store.put('ResearchRun',{**run.model_dump(mode='json'),'opportunity_id':opportunity.id,'finding_ids':[f.id for f in findings],'signal_ids':[s.id for s in signals],'idea_ids':[i.id for i in ideas]},con=con)
            self.store.decision(con,run.id,'human_reused_research_for_new_production',{**human,'original_run_id':identifier,'source_hashes':{s['id']:s['content_sha256'] for s in bundle['sources']},'provider_calls':0})
        return self.bundle(run.id)

    def create(self,query,profile_id,urls,*,trend_context=None,channel_profile=None,con=None):
        profile=next((p for p in self.catalog['profiles'] if p['id']==profile_id),None)
        if profile is None: raise WorkflowError('INTELLIGENCE_PROFILE_NOT_FOUND',400)
        if not isinstance(urls,list) or not 1<=len(urls)<=5 or any(not isinstance(u,str) or len(u)>2000 for u in urls): raise WorkflowError('RESEARCH_SOURCE_URLS_REQUIRED_1_TO_5',400)
        context={'profile':profile,'profile_sha256':digest(profile),'source_urls':urls,'scoring':self.catalog['scoring']}
        if trend_context is not None:
            from .trend_radar_lineage import validate
            validate(trend_context)
            if channel_profile!=trend_context['channel_selection'] or channel_profile['profile']['content_profile_id']!=profile_id:raise WorkflowError('TREND_CHANNEL_PROFILE_MISMATCH',400)
            context.update(trend_radar=trend_context,channel_profile=channel_profile)
        elif channel_profile is not None:raise WorkflowError('TREND_CONTEXT_REQUIRED',400)
        run=ResearchRun(query=query,context=context,provider=self.research_provider.key,
                        provenance={'origin':'explicit_research_input','source_discovery':'human supplied public URLs or configured references'})
        opportunity=Opportunity(run_id=run.id,topic=run.query[:300],related_project=profile['related_project'],target_audience=profile['target_audience'],reason_now='Yêu cầu nghiên cứu mới; chưa có dữ liệu đo mức độ thịnh hành.',
            supporting_signals=[],proposed_angle='Chờ nghiên cứu và ý tưởng',research_freshness='Chưa nghiên cứu',provenance={'origin':'explicit_content_signal','not_measured_market_trend':True})
        def persist(conn):
            saved_opportunity=self.store.put('Opportunity',opportunity.model_dump(mode='json'),con=conn)
            saved_run=self.store.put('ResearchRun',{**run.model_dump(mode='json'),'opportunity_id':opportunity.id},con=conn)
            return {'run':saved_run,'opportunity':saved_opportunity}
        if con is not None:return persist(con)
        with self.store.transaction() as conn:persist(conn)
        return self.bundle(run.id)

    def bundle(self,identifier):
        with self.store.transaction() as con:
            run=self.store.get(identifier,'ResearchRun',con)
            sources=[self.store.get(i,'ResearchSource',con) for i in run['source_ids']]
            findings=[self.store.get(i,'ResearchFinding',con) for i in run['finding_ids']]
            ideas=[self.store.get(i,'ContentIdea',con) for i in run['idea_ids']]
            opportunity=self.store.get(run['opportunity_id'],'Opportunity',con)
            scores=[self.store.get(r[0],'IdeaScore',con) for r in con.execute("SELECT id FROM records WHERE kind='IdeaScore'").fetchall()]
            for idea in ideas:
                linked=[s for s in scores if s['idea_id']==idea['id'] and s['idea_version']==idea['version']]
                idea['score']=linked[-1] if linked else None
            ideas.sort(key=lambda i: (i['generation'],i['score']['final_score'] if i['score'] else -1),reverse=True)
            operations=[{**dict(row),'error':json.loads(row['error']) if row['error'] else None} for row in con.execute('SELECT * FROM operations WHERE run_id=? ORDER BY created_at DESC',(identifier,))]
            brief=self.store.get(opportunity['brief_id'],'ContentBrief',con) if opportunity['brief_id'] else None
        return {'run':run,'sources':sources,'findings':findings,'ideas':ideas,'opportunity':self.sync_opportunity(opportunity),'brief':brief,'operations':operations,'scoring_type':'HEURISTIC_SCORING'}

    def sync_opportunity(self,opportunity):
        identifier=opportunity['production_project_id']
        if identifier:
            project=self.production.get(identifier)
            finals=[j for j in project['jobs'] if j['kind']=='render' and j['status']=='succeeded' and j['revision']==project['revision'] and j['final_review'] and j['final_review']['decision']=='approve']
            produced=False
            for job in finals:
                try: self.production.final_video(job['id']); produced=True
                except WorkflowError: pass
            desired='PRODUCED' if produced else 'IN_PRODUCTION'
            if opportunity['status']!=desired:
                opportunity=self.store.put('Opportunity',{**opportunity,'status':desired},opportunity['version'])
        return opportunity

    def queue(self): return [self.sync_opportunity(o) for o in self.store.list('Opportunity')]

    def enqueue(self,identifier,version,action,request_key):
        if action not in {'research','ideas'} or not isinstance(request_key,str) or not 16<=len(request_key)<=100: raise WorkflowError('INTELLIGENCE_OPERATION_INVALID',400)
        with self.store.transaction() as con:
            run=self.store.get(identifier,'ResearchRun',con)
            request_sha=digest({'run_id':identifier,'version':version,'action':action})
            existing=con.execute('SELECT * FROM operations WHERE request_key=?',(request_key,)).fetchone()
            if existing:
                if existing['request_sha256']!=request_sha: raise WorkflowError('INTELLIGENCE_REQUEST_KEY_CONFLICT')
                return dict(existing)
            if type(version) is not int or run['version']!=version: raise WorkflowError('INTELLIGENCE_STALE_VERSION_RELOAD')
            if con.execute("SELECT 1 FROM operations WHERE run_id=? AND status IN ('QUEUED','RUNNING')",(identifier,)).fetchone(): raise WorkflowError('INTELLIGENCE_OPERATION_BUSY')
            opportunity=self.store.get(run['opportunity_id'],'Opportunity',con)
            if opportunity['status'] in {'IN_PRODUCTION','PRODUCED'}: raise WorkflowError('INTELLIGENCE_ALREADY_IN_PRODUCTION_CREATE_NEW_RUN')
            if action=='research' and run['status']!='NEW': raise WorkflowError('INTELLIGENCE_RESEARCH_IMMUTABLE_CREATE_NEW_RUN')
            if action=='ideas' and (not run['finding_ids'] or run['status'] not in {'FINDINGS','IDEAS','FAILED'}): raise WorkflowError('INTELLIGENCE_RESEARCH_REQUIRED')
            operation={'id':uuid.uuid4().hex,'run_id':identifier,'action':action,'status':'QUEUED','request_key':request_key,'request_sha256':request_sha,'error':None,'created_at':datetime.now(timezone.utc).isoformat()}
            con.execute('INSERT INTO operations VALUES(:id,:run_id,:action,:status,:request_key,:request_sha256,:error,:created_at)',operation)
            self.store.decision(con,identifier,'explicit_'+action+'_request',operation)
        self.wake.set()
        return operation

    def run_one(self):
        with self.store.transaction() as con:
            row=con.execute("SELECT * FROM operations WHERE status='QUEUED' ORDER BY created_at LIMIT 1").fetchone()
            if not row: return False
            operation=dict(row); con.execute("UPDATE operations SET status='RUNNING' WHERE id=?",(operation['id'],))
        out=self.config.data_root/'intelligence-operations'/operation['id']
        started = time.monotonic()
        completed = False
        try:
            out.mkdir(parents=True,exist_ok=False)
            run=self.store.get(operation['run_id'],'ResearchRun')
            if operation['action']=='research':
                run=self.store.put('ResearchRun',{**run,'status':'RESEARCHING','error':None},run['version'])
                sources,findings,metadata=self.research_provider.research(run['query'],{**run['context'],'run_id':run['id']})
                validate_findings(sources,findings)
                with self.store.transaction() as con:
                    for s in sources: self.store.put('ResearchSource',s.model_dump(mode='json'),con=con)
                    for f in findings: self.store.put('ResearchFinding',f.model_dump(mode='json'),con=con)
                    signals=[]
                    for source in sources:
                        freshness=('Công bố '+source.timestamp.isoformat()) if source.timestamp else 'Không rõ ngày công bố; ngày lấy không chứng minh độ mới'
                        signal=TrendSignal(run_id=run['id'],topic=run['query'][:300],related_project=run['context']['profile']['related_project'],signal_type='source_update',source_id=source.id,finding_ids=[f.id for f in findings if any(c.source_id==source.id for c in f.source_references)],observed_at=source.retrieved_at,strength=.5,freshness=freshness,provenance={'origin':'actual_source_retrieval','strength_is_editorial_heuristic':True,'not_social_velocity':True})
                        signals.append(self.store.put('TrendSignal',signal.model_dump(mode='json'),con=con))
                    opportunity=self.store.get(run['opportunity_id'],'Opportunity',con)
                    self.store.put('Opportunity',{**opportunity,'supporting_signals':[s['id'] for s in signals],'research_freshness':' | '.join(s['freshness'] for s in signals),'reason_now':'Nguồn được lấy cho yêu cầu này. Đối chiếu ngày công bố trước khi gọi là tin mới.'},opportunity['version'],con)
                    self.store.put('ResearchRun',{**run,'status':'FINDINGS','source_ids':[s.id for s in sources],'finding_ids':[f.id for f in findings],'signal_ids':[s['id'] for s in signals],'provider_metadata':metadata},run['version'],con)
            else:
                findings=[self.store.get(i,'ResearchFinding') for i in run['finding_ids']]; sources=[self.store.get(i,'ResearchSource') for i in run['source_ids']]
                self.verify_sources(sources,findings)
                candidates,metadata=self.idea_provider.generate(run['query'],run['context'],findings,sources,out)
                validate_candidates(candidates,findings,sources)
                with self.store.transaction() as con:
                    run=self.store.get(run['id'],'ResearchRun',con); opportunity=self.store.get(run['opportunity_id'],'Opportunity',con)
                    previous=[]
                    for identifier in run['idea_ids']:
                        old=self.store.get(identifier,'ContentIdea',con); previous.append(old)
                        if old['status']!='REJECTED': self.store.put('ContentIdea',{**old,'status':'SUPERSEDED'},old['version'],con)
                    if opportunity['brief_id']:
                        old=self.store.get(opportunity['brief_id'],'ContentBrief',con)
                        self.store.put('ContentBrief',{**old,'status':'SUPERSEDED','approval':None},old['version'],con)
                    generation=run['generation']+1; ideas=[]; scores=[]
                    for candidate in candidates:
                        idea=ContentIdea(**candidate,run_id=run['id'],opportunity_id=opportunity['id'],generation=generation,related_project=run['context']['profile']['related_project'],provenance={'origin':'provider_editorial_candidate','facts_verified':False,**metadata})
                        ideas.append(self.store.put('ContentIdea',idea.model_dump(mode='json'),con=con))
                    for idea in ideas:
                        value=score(idea,findings,sources,run['context']['profile'],{'scoring':run['context']['scoring']},previous+[i for i in ideas if i['id']!=idea['id']])
                        scores.append(self.store.put('IdeaScore',value.model_dump(mode='json'),con=con))
                    best=max(scores,key=lambda s:s['final_score']); ranked=next(i for i in ideas if i['id']==best['idea_id'])
                    self.store.put('Opportunity',{**opportunity,'status':'NEW','selected_idea_id':None,'brief_id':None,'opportunity_score':best['final_score'],'suggested_hook':ranked['hook'],'candidate_format':ranked['format'],'proposed_angle':ranked['angle']},opportunity['version'],con)
                    self.store.put('ResearchRun',{**run,'status':'IDEAS','error':None,'generation':generation,'idea_ids':run['idea_ids']+[i['id'] for i in ideas],'provider_metadata':{**run['provider_metadata'],'last_idea_generation':metadata}},run['version'],con)
            with self.store.transaction() as con: con.execute("UPDATE operations SET status='SUCCEEDED' WHERE id=?",(operation['id'],))
            completed = True
        except Exception as exc:
            error={'code':exc.code if isinstance(exc,WorkflowError) else type(exc).__name__,'automatic_replay':False}
            if isinstance(exc,WorkflowError) and exc.http_status: error['http_status']=exc.http_status
            try: (out/'failure.json').write_bytes(canonical(error))
            except OSError: error['failure_file_unavailable']=True
            with self.store.transaction() as con:
                con.execute("UPDATE operations SET status='FAILED',error=? WHERE id=?",(canonical(error).decode(),operation['id']))
                run=self.store.get(operation['run_id'],'ResearchRun',con)
                self.store.put('ResearchRun',{**run,'status':'FAILED','error':error},run['version'],con)
        finally:
            self.observer.emit('intelligence_completed' if completed else 'intelligence_failed',
                request_id=operation['id'], job_id=operation['id'], run_id=operation['run_id'],
                stage=operation['action'], provider=None, duration=time.monotonic() - started)
        return True

    def work(self):
        while not self.stop.is_set():
            if not self.run_one(): self.wake.wait(1); self.wake.clear()

    def verify_sources(self,sources,findings):
        validate_findings([ResearchSource.model_validate(s) for s in sources],[ResearchFinding.model_validate(f) for f in findings])
        for source in sources:
            if source['source_type']=='web':
                directory=self.config.data_root/'research-sources'/source['id']
                receipt=json.loads((directory/'retrieval.json').read_bytes())
                text=(directory/'source-text.txt').read_bytes().decode('utf-8')
                html=(directory/'source.html').read_bytes().decode('utf-8')
                def matches(value,expected):
                    if digest(value)==expected: return True
                    # Early Phase 9 files used Windows text-mode writes. Reconstruct exactly
                    # that LF->CRLF conversion only when the original recorded hash proves it.
                    # Never rewrite their original files or provenance; v2 sources require exact bytes.
                    return 'storage_format' not in receipt and digest(value.replace('\r\n','\n'))==expected
                if not matches(text,source['content_sha256']) or receipt!=source['raw_provenance'] or not matches(html,receipt['retained_html_sha256']): raise WorkflowError('RESEARCH_PERSISTED_SOURCE_CHANGED')

    def human(self,reviewer,ack=True,note=''):
        if not isinstance(reviewer,str) or not 1<=len(reviewer.strip())<=100 or ack is not True: raise WorkflowError('INTELLIGENCE_HUMAN_REVIEW_REQUIRED',400)
        if not isinstance(note,str) or len(note)>2000: raise WorkflowError('INTELLIGENCE_REVIEW_NOTE_INVALID',400)
        return {'reviewer':reviewer.strip(),'note':note.strip(),'created_at':datetime.now(timezone.utc).isoformat()}

    def editable(self,con,idea,version):
        if type(version) is not int or idea['version']!=version: raise WorkflowError('INTELLIGENCE_STALE_VERSION_RELOAD')
        run=self.store.get(idea['run_id'],'ResearchRun',con); opportunity=self.store.get(idea['opportunity_id'],'Opportunity',con)
        if idea['generation']!=run['generation'] or idea['status']=='SUPERSEDED': raise WorkflowError('INTELLIGENCE_IDEA_SUPERSEDED')
        if opportunity['status'] in {'IN_PRODUCTION','PRODUCED'}: raise WorkflowError('INTELLIGENCE_ALREADY_IN_PRODUCTION_CREATE_NEW_RUN')
        if con.execute("SELECT 1 FROM operations WHERE run_id=? AND status IN ('QUEUED','RUNNING')",(run['id'],)).fetchone(): raise WorkflowError('INTELLIGENCE_OPERATION_BUSY')
        return run,opportunity

    def rescore(self,con,run,idea):
        findings=[self.store.get(i,'ResearchFinding',con) for i in run['finding_ids']]
        sources=[self.store.get(i,'ResearchSource',con) for i in run['source_ids']]
        previous=[self.store.get(i,'ContentIdea',con) for i in run['idea_ids'] if i!=idea['id']]
        value=score(idea,findings,sources,run['context']['profile'],{'scoring':run['context']['scoring']},previous)
        self.store.put('IdeaScore',value.model_dump(mode='json'),con=con)

    def select(self,identifier,version,opportunity_version,reviewer):
        human=self.human(reviewer)
        with self.store.transaction() as con:
            idea=self.store.get(identifier,'ContentIdea',con); run,opportunity=self.editable(con,idea,version)
            if opportunity['version']!=opportunity_version: raise WorkflowError('INTELLIGENCE_STALE_VERSION_RELOAD')
            if idea['status']=='REJECTED': raise WorkflowError('INTELLIGENCE_IDEA_REJECTED_EDIT_FIRST')
            if opportunity['selected_idea_id']==identifier and opportunity['brief_id']: return self.store.get(opportunity['brief_id'],'ContentBrief',con)
            if opportunity['selected_idea_id']:
                old=self.store.get(opportunity['selected_idea_id'],'ContentIdea',con)
                old=self.store.put('ContentIdea',{**old,'status':'CANDIDATE'},old['version'],con)
                self.rescore(con,run,old)
            if opportunity['brief_id']:
                old=self.store.get(opportunity['brief_id'],'ContentBrief',con)
                self.store.put('ContentBrief',{**old,'status':'SUPERSEDED','approval':None},old['version'],con)
            idea=self.store.put('ContentIdea',{**idea,'status':'SELECTED'},idea['version'],con)
            self.rescore(con,run,idea)
            findings=[self.store.get(fid,'ResearchFinding',con) for fid in idea['supporting_research']]
            brief=ContentBrief(run_id=run['id'],idea_id=idea['id'],idea_version=idea['version'],**draft_brief_fields(idea,findings),provenance={'origin':'human_idea_selection','selection':human,'profile_sha256':run['context']['profile_sha256']})
            value=self.store.put('ContentBrief',brief.model_dump(mode='json'),con=con)
            self.store.put('Opportunity',{**opportunity,'status':'REVIEWING','selected_idea_id':identifier,'brief_id':brief.id},opportunity['version'],con)
            self.store.decision(con,identifier,'human_selected_idea',{**human,'idea_version':idea['version'],'brief_id':brief.id})
        return value

    def edit_idea(self,identifier,version,changes,reviewer,decision='edit'):
        if not isinstance(changes,dict): raise WorkflowError('INTELLIGENCE_IDEA_EDIT_FIELDS_INVALID',400)
        human=self.human(reviewer,note=changes.get('note',''))
        with self.store.transaction() as con:
            idea=self.store.get(identifier,'ContentIdea',con); run,opportunity=self.editable(con,idea,version)
            if decision=='reject':
                if not human['note']: raise WorkflowError('INTELLIGENCE_REJECTION_REASON_REQUIRED',400)
                updates={'status':'REJECTED'}
            else:
                if not changes or not set(changes)<=IDEA_EDITABLE: raise WorkflowError('INTELLIGENCE_IDEA_EDIT_FIELDS_INVALID',400)
                updates={**changes,'status':'CANDIDATE'}
            value=self.store.put('ContentIdea',{**idea,**updates},version,con)
            if opportunity['selected_idea_id']==identifier:
                brief=self.store.get(opportunity['brief_id'],'ContentBrief',con)
                self.store.put('ContentBrief',{**brief,'status':'SUPERSEDED','approval':None},brief['version'],con)
                self.store.put('Opportunity',{**opportunity,'selected_idea_id':None,'brief_id':None,'status':'REJECTED' if decision=='reject' else 'REVIEWING'},opportunity['version'],con)
            if decision!='reject':
                self.rescore(con,run,value)
            self.store.decision(con,identifier,'human_'+decision+'_idea',{**human,'version':value['version'],'changes':updates})
        return value

    def edit_brief(self,identifier,version,changes,reviewer):
        human=self.human(reviewer)
        if not isinstance(changes,dict) or not changes or not set(changes)<=BRIEF_EDITABLE: raise WorkflowError('INTELLIGENCE_BRIEF_EDIT_FIELDS_INVALID',400)
        with self.store.transaction() as con:
            brief=self.store.get(identifier,'ContentBrief',con); idea=self.store.get(brief['idea_id'],'ContentIdea',con)
            _,opportunity=self.editable(con,idea,idea['version'])
            if brief['status']=='SUPERSEDED' or opportunity['brief_id']!=identifier: raise WorkflowError('INTELLIGENCE_BRIEF_SUPERSEDED')
            value=self.store.put('ContentBrief',{**brief,**changes,'status':'DRAFT','approval':None},version,con)
            self.store.put('Opportunity',{**opportunity,'status':'REVIEWING'},opportunity['version'],con)
            self.store.decision(con,identifier,'human_edited_brief',{**human,'version':value['version']})
        return value

    def approve_brief(self,identifier,version,reviewer,acknowledged,note=''):
        human=self.human(reviewer,acknowledged,note)
        with self.store.transaction() as con:
            brief=self.store.get(identifier,'ContentBrief',con); idea=self.store.get(brief['idea_id'],'ContentIdea',con)
            run,opportunity=self.editable(con,idea,idea['version'])
            if type(version) is not int or brief['version']!=version: raise WorkflowError('INTELLIGENCE_STALE_VERSION_RELOAD')
            if brief['status']=='SUPERSEDED' or opportunity['brief_id']!=identifier or brief['idea_version']!=idea['version']: raise WorkflowError('INTELLIGENCE_BRIEF_SUPERSEDED')
            sources=[self.store.get(i,'ResearchSource',con) for i in run['source_ids']]; findings=[self.store.get(i,'ResearchFinding',con) for i in run['finding_ids']]
            self.verify_sources(sources,findings)
            approval={**human,'brief_content_sha256':digest(brief_content(brief)),'idea_id':idea['id'],'idea_version':idea['version'],'source_hashes':{s['id']:s['content_sha256'] for s in sources}}
            value=self.store.put('ContentBrief',{**brief,'status':'APPROVED','approval':approval},version,con)
            self.store.put('Opportunity',{**opportunity,'status':'APPROVED'},opportunity['version'],con)
            self.store.decision(con,identifier,'human_approved_brief',approval)
        return value

    def send(self,identifier,version,*,production_quality=False,narrated_workflow=False):
        from .narrated_workflow import selections
        selections(production_quality=production_quality,narrated_workflow=narrated_workflow)
        with self.store.transaction() as con:
            brief=self.store.get(identifier,'ContentBrief',con)
            if type(version) is not int or brief['version']!=version: raise WorkflowError('INTELLIGENCE_STALE_VERSION_RELOAD')
            if brief['status']!='APPROVED' or not brief['approval'] or brief['approval']['brief_content_sha256']!=digest(brief_content(brief)): raise WorkflowError('INTELLIGENCE_APPROVED_BRIEF_REQUIRED')
            idea=self.store.get(brief['idea_id'],'ContentIdea',con); run=self.store.get(brief['run_id'],'ResearchRun',con); opportunity=self.store.get(idea['opportunity_id'],'Opportunity',con)
            if opportunity['brief_id']!=identifier or opportunity['selected_idea_id']!=idea['id'] or idea['version']!=brief['idea_version']: raise WorkflowError('INTELLIGENCE_BRIEF_SUPERSEDED')
            sources=[self.store.get(i,'ResearchSource',con) for i in run['source_ids']]; findings=[self.store.get(i,'ResearchFinding',con) for i in run['finding_ids']]
            self.verify_sources(sources,findings)
            lineage={'schema_version':'content-intelligence-lineage-v1','run':run,'idea':idea,'brief':brief,'sources':sources,'findings':findings,'approved_brief_sha256':digest(brief_content(brief))}
            lineage['sha256']=digest(lineage)
            project=self.production.create_from_brief(idea['title'],lineage,production_quality=production_quality,narrated_workflow=narrated_workflow)
            self.store.put('Opportunity',{**opportunity,'status':'IN_PRODUCTION','production_project_id':project['id']},opportunity['version'],con)
            self.store.decision(con,identifier,'explicit_send_to_native_script_review',{'project_id':project['id'],'lineage_sha256':lineage['sha256'],'no_tts_render_dispatch':True})
        return project
