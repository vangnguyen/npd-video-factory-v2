"""Qualified synthetic planning feedback/recovery; never real audience or media UAT."""
import argparse,copy,json,re,sys,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_learning import TABLES,rows,services as source_services,settings,write
from services.windows_native.tests.test_qualified_learning_feedback import QualifiedFeedbackTests
from services.windows_native.qualified_learning_feedback import NativeQualifiedLearningFeedback,context
from services.windows_native.trend_radar import NativeTrendRadar
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.analytics import NativeAnalytics
from services.windows_native.pipeline import Config
from services.windows_native.contracts import file_sha,digest
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.studio_media_planner import NativeStudioMediaPlanner

def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-qualified-learning-feedback-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned qualified feedback root required')
    return path

def services(root,out):
    store,journal,queue,analytics,winners,learning=source_services(root,out)
    config=Config(data_root=root);intelligence=IntelligenceService(config,store)
    radar=NativeTrendRadar(intelligence,NativeAnalytics(store,journal.publications),workspace=learning.workspace)
    feedback=NativeQualifiedLearningFeedback(learning,radar);radar.qualified_learning=feedback;intelligence.qualified_learning=feedback;store.qualified_learning=feedback
    planner=NativeStudioMediaPlanner(store,config,workspace_id=learning.workspace,providers=lambda:{'workspace_id':learning.workspace,'stock':{'items':[]},'generation':{'items':[]}})
    return store,journal,queue,analytics,winners,learning,intelligence,radar,feedback,planner

def intelligence_rows(store):
    with store.transaction() as con:return {name:[dict(r) for r in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in ('records','versions','decisions','operations')}

def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve()
    store,journal,queue,analytics,winners,learning,intelligence,radar,feedback,planner=services(root,out)
    try:
        assert rows(store)==json.loads((out/'expected-journals.json').read_bytes())
        assert intelligence_rows(intelligence.store)==json.loads((out/'expected-intelligence-journals.json').read_bytes())
        for name,service,field in [('publications',journal,'publication_id'),('analytics-history',analytics,'sync_id'),('winner-history',winners,'assessment_id'),('learning-history',learning,'learning_id')]:
            for value in json.loads((out/('expected-'+name+'.json')).read_bytes()):assert service.get(value['project_id'],value[field])==value
        projections=json.loads((out/'expected-projections.json').read_bytes())
        for value in projections:assert feedback.get(value['id'])==value
        assert feedback.suggestions(projections[0]['id'])==json.loads((out/'expected-template-suggestions.json').read_bytes())
        for value in json.loads((out/'expected-projects.json').read_bytes()):assert store.get(value['id'])==value
        for value in json.loads((out/'expected-jobs.json').read_bytes()):assert store.get_job(value['id'])==value
        plan=json.loads((out/'expected-media-plan.json').read_bytes());assert planner.page(plan['project_id'])==plan['page']
        physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
        status=database_status(store.db);assert status['active_operations']==0 and not queue.configured() and queue.process() is None
        assert not analytics.states()['enabled'] and analytics.states()['accounts']==[] and analytics.process() is None and journal.states()['profiles']==[]
        assert len(projections)==2 and len(json.loads((out/'expected-publications.json').read_bytes()))==7
        assert len(json.loads((out/'expected-analytics-history.json').read_bytes()))==11 and len(json.loads((out/'expected-winner-history.json').read_bytes()))==8
        assert len(json.loads((out/'expected-learning-history.json').read_bytes()))==3
        write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
            'seven_receipts_eleven_observations_eight_assessments_three_learning_two_projections_twenty_four_workflow_and_four_intelligence_journals_exact':True,
            'original_project_job_physical_media_template_and_media_plan_history_exact':True,
            'credential_registry_publish_queue_analytics_or_trend_providers_enabled':False,'new_provider_media_or_paid_operations':0,'real_audience_observations':0})
    finally:radar.close()

def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external qualified feedback evidence required')
    out.mkdir(parents=True);fixture=QualifiedFeedbackTests();fixture.setUp()
    try:
        from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue
        from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
        from services.windows_native.official_winner_models import Create as WinnerCreate
        from services.windows_native.research import PublicWebResearchProvider
        from services.windows_native.tests.test_intelligence_engines import receipt
        from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
        from services.windows_native.tests.test_workflow import proposal
        from services.windows_native.studio_media_models import Create as PlanCreate
        from PIL import Image
        NativeOfficialPublicationQueue(NativeOfficialPublicationWorker(fixture.service,fixture.vault))
        fixture.positive_family=fixture.radar_ready()['payload']['cluster_id'];fixture.cohort_learning()
        sparse=fixture.saved;fixture.saved=fixture.learn(request_key='explicit-retained-qualified-family-learning');first_learning=fixture.saved
        first,_=fixture.project_feedback();replayed,exact=fixture.project_feedback();assert exact and replayed==first
        item,bundle=fixture.handoff_with_feedback(first);assert item['payload']['ranking']['history_adjustment_points']>0
        assert item['payload']['learning_feedback']==context(first);assert not first['payload']['real_audience_observation']
        def education_receipt(url):
            value=receipt();value['html']=value['html'].replace('housing','AI educational video');return value
        fixture.intelligence.research_provider=PublicWebResearchProvider(fixture.root/'research-sources',fetch=education_receipt)
        fixture.intelligence.idea_provider=FixtureIdeas()
        for action in ('research','ideas'):
            fixture.intelligence.enqueue(bundle['run']['id'],bundle['run']['version'],action,uuid.uuid4().hex);assert fixture.intelligence.run_one()
            bundle=fixture.intelligence.bundle(bundle['run']['id']);assert bundle['operations'][0]['status']=='SUCCEEDED'
        idea=bundle['ideas'][0];fixture.intelligence.select(idea['id'],idea['version'],bundle['opportunity']['version'],'EXPLICIT RETAINED HUMAN FIXTURE')
        bundle=fixture.intelligence.bundle(bundle['run']['id']);brief=fixture.intelligence.approve_brief(bundle['brief']['id'],bundle['brief']['version'],'EXPLICIT RETAINED HUMAN FIXTURE',True)
        project=fixture.intelligence.send(brief['id'],brief['version'],production_quality=True,narrated_workflow=True)
        project=fixture.store.save(project['id'],project['revision'],proposal=proposal('Explicit synthetic planning script'))
        image=fixture.root/'assets'/(uuid.uuid4().hex+'.jpg');image.parent.mkdir(exist_ok=True);Image.new('RGB',(320,240),(17,122,201)).save(image)
        project=fixture.store.append_media(project['id'],project['revision'],{'id':image.name,'kind':'image','sha256':file_sha(image),'filename':'EXPLICIT SYNTHETIC AI education illustration','rights_confirmed':True,'illustration':True})
        planner=NativeStudioMediaPlanner(fixture.store,fixture.config,workspace_id=fixture.workspace,providers=lambda:{'workspace_id':fixture.workspace,'stock':{'items':[]},'generation':{'items':[]}})
        view=fixture.store.shot_view(project['id']);before=copy.deepcopy(view['shot_timeline']['snapshot'])
        plan=planner.create(project['id'],PlanCreate(revision=project['revision'],expected_timeline_version=view['shot_timeline']['version']))
        advice=plan['items'][-1]['plan']['input']['channel_history_recommendations'];assert advice['dimensions']==first['payload']['consumers']['media_planner'] and not advice['automatic_application']
        assert fixture.store.shot_view(project['id'])['shot_timeline']['snapshot']==before
        templates=fixture.feedback.suggestions(first['id']);assert templates['suggestions'] and not templates['suggestions'][0]['historical_full_style_verified']
        target=fixture.learning_sources[1];candidate=target['snapshot']['candidate'];fixture.project=fixture.store.get(target['project_id'])
        fixture.job=fixture.store.get_job(candidate['features']['evidence']['render_job_id']);fixture.completed=fixture.service.get(target['project_id'],target['publication_id']);fixture.rows=False
        observation=fixture.run_collection(request_key='explicit-retained-qualified-later-null-read')
        newest=fixture.winners.create(target['project_id'],WinnerCreate(sync_id=observation['sync_id'],expected_result_sha256=digest(observation['result']),acknowledged_recommendation_only=True,
            acknowledged_protocol_mock=True,request_key='explicit-retained-qualified-later-null-assessment'),principal=fixture.principal)[0]
        assert newest['assessment']['state']=='insufficient_data';fixture.saved=fixture.learn(request_key='explicit-retained-qualified-later-learning')
        second,_=fixture.project_feedback(request_key='explicit-retained-qualified-later-projection');assert second['payload']['observation_count']==5 and second['payload']['status']=='insufficient_data'
        assert fixture.feedback.get(first['id'])==first and fixture.feedback.suggestions(first['id'])==templates
        with fixture.store.transaction() as con:
            pubrows=con.execute("SELECT project_id,publication_id FROM native_official_publications WHERE status='completed' ORDER BY rowid").fetchall()
            syncrows=con.execute("SELECT project_id,sync_id FROM native_official_analytics_syncs WHERE status='succeeded' ORDER BY rowid").fetchall()
            winnerrows=con.execute('SELECT project_id,assessment_id FROM native_official_winner_assessments ORDER BY rowid').fetchall()
        publications=[fixture.service.get(r['project_id'],r['publication_id']) for r in pubrows];analytics=[fixture.analytics.get(r['project_id'],r['sync_id']) for r in syncrows]
        winners=[fixture.winners.get(r['project_id'],r['assessment_id']) for r in winnerrows];projects=[fixture.store.get(p['id']) for p in fixture.store.list()];jobs=[j for p in projects for j in p['jobs']]
        assert len(publications)==7 and len(analytics)==11 and len(winners)==8 and len(fixture.wire)==70 and len(fixture.read_wire)==39
        fixture.accounts.factories.clear();fixture.service.factories.clear()
        for name,value in [('publications',publications),('analytics-history',analytics),('winner-history',winners),('learning-history',[sparse,first_learning,fixture.saved]),
            ('projections',[first,second]),('template-suggestions',templates),('projects',projects),('jobs',jobs),('media-plan',{'project_id':project['id'],'page':planner.page(project['id'])})]:write(out/('expected-'+name+'.json'),value)
        write(out/'expected-journals.json',rows(fixture.store));write(out/'expected-intelligence-journals.json',intelligence_rows(fixture.intelligence.store))
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()));write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire)
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for name in ('jobs','assets') for p in (fixture.root/name).rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs={p['id']:fixture.analytics.costs.summary(p['id']) for p in projects};write(out/'cost-summary.json',costs)
        assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for s in costs.values() for r in s['records'])
        backup=create_backup(settings(fixture.root),out/'owned-qualified-learning.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-qualified-learning.zip') as archive:
            assert all(not n.endswith(('.dpapi','.part')) for n in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(n) and fixture.read_credential.token.encode() not in archive.read(n)
                and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(n) for n in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-qualified-learning.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-official-learning-controls-flow-n1')
        old_store,old_journal,_,old_analytics,old_winners,old_learning=source_services(Path('C:/vf-native-fixture-official-learning-controls-restore-01'),prior)
        assert rows(old_store)==json.loads((prior/'expected-journals.json').read_bytes())
        for name,service,field in [('publications',old_journal,'publication_id'),('analytics-history',old_analytics,'sync_id'),('winner-history',old_winners,'assessment_id'),('learning-history',old_learning,'learning_id')]:
            for value in json.loads((prior/('expected-'+name+'.json')).read_bytes()):assert service.get(value['project_id'],value[field])==value
        write(out/'legacy-signed-learning-controls-replay.json',{'prior_one_receipt_two_observations_two_assessments_three_learning_twenty_four_journals_exact':True,'external_calls':0})
        sources=['services/windows_native/'+name for name in ('qualified_learning_feedback.py','trend_radar.py','trend_radar_routes.py','trend_radar_lineage.py','intelligence_service.py','idea_engine.py','studio_media_planner.py',
            'server.py','access.py','tests/test_qualified_learning_feedback.py','tests/test_qualified_learning_feedback_http.py')]+['scripts/north_star_native_qualified_learning.py']
        write(out/'evidence.json',{'schema_version':'native-qualified-learning-feedback-rehearsal-v1','explicit_synthetic_nonplayable_qc_rights_oauth_account_metrics_research_ideas_and_script_fixtures':True,
            'mock_publication_wire_requests':70,'mock_analytics_read_requests':33,'mock_peer_account_requests':6,'mock_initial_account_requests':1,
            'six_distinct_posts_three_group_three_controls_all_four_consumers_qualified':True,'positive_mock_trend_ranking_bound_idea_handoff_media_plan_template_suggestions_recommendation_only':True,
            'later_null_source_five_posts_insufficient_original_six_post_projection_exact':True,'workflow_and_intelligence_recovery_exact':True,'prior_signed_controls_exact':True,'archive_excludes_secrets':True,
            'real_publications':0,'real_audience_observations':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'signed_http_requests':0,
            'browser_owner_or_real_provider_acceptance':False,'production_deployed':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_QUALIFIED_LEARNING_FEEDBACK_RECOVERY_PASS','mock_analytics_read_requests':33,'external_provider_calls':0,'real_audience_observations':0}))
    finally:fixture.tearDown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
