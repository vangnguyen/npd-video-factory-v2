"""Signed Studio rehearsal, immutable evidence and separate keyless recovery; all providers mock."""
import argparse,json,subprocess,sys,threading,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from services.windows_native.tests.test_tiktok_analytics_http import TikTokAnalyticsHTTPTests
from services.windows_native.tests.test_tiktok_analytics import POST,OTHER
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_native_analytics_refresh import settings

ROOT=Path(r'C:\vfns01');LOG=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007')
def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as h:json.dump(value,h,ensure_ascii=False,indent=2);h.write('\n')
def node(server,cookie,csrf,workspace,project,publication,**kw):
    value={'origin':'http://127.0.0.1:'+str(server.server_port),'cookie':cookie,'csrf':csrf,'workspace_id':workspace,'project':project,'publication':publication,**kw}
    result=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(ROOT/'scripts/north_star_tiktok_analytics.mjs')],input=json.dumps(value),capture_output=True,text=True,encoding='utf-8',timeout=90,cwd=ROOT)
    if result.returncode:raise AssertionError(result.stderr)
    data=json.loads(result.stdout);assert data['status']=='PASS' and cookie not in result.stdout and csrf not in result.stdout;return data
def cold(data):
    from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
    from services.windows_native.access import NativeAccess
    from services.windows_native.server import LocalServer
    from services.windows_native.tests.test_phase10_http import NoProviderPipeline
    access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data['registry']),max_token_ttl_seconds=86400),data['workspace_id']);pipeline=NoProviderPipeline()
    with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No cold private decrypt')):
        server=LocalServer(0,settings(Path(data['root'])),pipeline=pipeline,start_worker=False,access=access);cookie,session=access.login(data['raw_human_fixture']);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            result=node(server,cookie,session.csrf,data['workspace_id'],server.store.get(data['project_id']),data['publication'],mode='read_history',read_only=True)
            assert result['selected_sync']==data['selected_sync'] and result['plan']==data['plan']
            assert server.official_analytics.accounts.factories=={} and not server.official_analytics.enabled and not server.official_analytics_refresh.enabled and not server.official_publish_queue.enabled and not server.runner.run_one() and pipeline.calls==0
            counts=database_status(server.store.db);assert counts['active_operations']==0 and counts['counts']==data['database_counts']
            assert server.official_winners.get(data['project_id'],data['winner']['assessment_id'])==data['winner'] and server.official_learning.get(data['project_id'],data['learning']['learning_id'])==data['learning']
            return {'status':'PASS','ui':result,'database_counts':counts['counts'],'private_keys_loaded':False,'automatic_replay':False,'provider_calls':0}
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--fixture-output',type=Path);p.add_argument('--restore-check',action='store_true');a=p.parse_args()
    if a.restore_check:print(json.dumps(cold(json.load(sys.stdin))));return
    out=a.output.absolute() if a.output else None
    if out is None or out.parent!=LOG or not out.name.startswith('tiktok-analytics-flow-n') or out.exists():raise ValueError('Fresh owned evidence output required')
    out.mkdir();case=TikTokAnalyticsHTTPTests('test_current_runtime_route_and_worker_use_exact_cumulative_binding_and_provider_log');case.setUp()
    try:
        project=case.server.store.get(case.project['id']);publication=case.server.official_publications.get(project['id'],case.completed['publication_id'])
        def ui(**kw):return node(case.server,case.cookie,case.csrf,case.c.workspace,project,publication,**kw)
        before_wires=len(case.pub.publish_wires)
        manual=ui(mode='create_manual',remote_post_id=POST);write(out/'ui-manual-created.json',manual);assert case.server.runner.run_one()
        manual_done=case.server.official_analytics.get(project['id'],manual['selected_sync']['sync_id']);assert manual_done['status']=='succeeded'
        start=datetime.now(timezone.utc)+timedelta(seconds=2);case.counts['view_count']=8
        plan_created=ui(mode='create_plan',remote_post_id=OTHER,start_at=start.isoformat(),deadline=(start+timedelta(seconds=300)).isoformat());write(out/'ui-plan-created.json',plan_created)
        while datetime.now(timezone.utc)<datetime.fromisoformat(plan_created['plan']['policy']['request']['start_at']):time.sleep(.05)
        assert case.server.runner.run_one();assert case.server.runner.run_one()
        final=ui(mode='read_history',assess=True);write(out/'ui-final-history.json',final)
        assert final['plan']['status']=='completed' and final['plan']['run_count']==1 and len(case.wires)==4
        assert final['selected_sync']['result']['remote_post_id']==OTHER and final['selected_sync']['result']['metrics']['views']==8
        assert case.server.store.get(project['id'])==project and case.pipeline.calls==0 and len(case.pub.publish_wires)==before_wires
        assert case.token not in json.dumps([manual,plan_created,final])
        def get(path):
            status,value,_=case.call('GET',path);assert status==200,value;return value
        fixture={'schema_version':'native-tiktok-analytics-fixture-v2','scope':'actual_signed_local_HTTP_explicit_protocol_mocks_nonplayable_media_no_real_audience',
            'project':project,'workspace_id':case.c.workspace,'publication':publication,'source':get(case.base+'/source/'+publication['publication_id']),
            'runtime':get('/api/connections/official-analytics'),'refresh_runtime':get('/api/connections/official-analytics-refresh'),
            'manual_created':manual['selected_sync'],'manual_done':manual_done,'plan_created':plan_created['plan'],'plan_done':final['plan'],'latest':final['selected_sync'],
            'winner_source':get('/api/projects/'+project['id']+'/official-winners/source/'+final['selected_sync']['sync_id']),'winner_runtime':get('/api/connections/official-winners'),'winner':final['winner'],
            'learning':final['learning'],'real_provider_acceptance':False,'owner_uat':False}
        write(out/'fixture.json',fixture)
        with case.server.store.transaction() as con:costs=[dict(x) for x in con.execute('SELECT * FROM native_cost_operations')]
        assert all(not row['paid'] and not row['external_call'] for row in costs);write(out/'costs.json',costs)
        backup=create_backup(settings(case.c.root),out/'public-state.zip');write(out/'backup.json',backup);destination=case.c.folder/'tiktok-analytics-restored';restore=restore_backup(out/'public-state.zip',destination,expected_sha256=backup['sha256'])
        payload={'root':str(destination),'registry':case.c.verifier.registry.model_dump(mode='json'),'raw_human_fixture':case.c.raw,'workspace_id':case.c.workspace,'project_id':project['id'],'publication':publication,
            'selected_sync':final['selected_sync'],'plan':final['plan'],'winner':final['winner'],'learning':final['learning'],'database_counts':database_status(case.server.store.db)['counts']}
        result=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).absolute()),'--restore-check'],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',timeout=90,cwd=ROOT)
        if result.returncode:raise AssertionError(result.stderr)
        check=json.loads(result.stdout);assert check['status']=='PASS';write(out/'cold-ui-history.json',{'restore':restore,'verification':check})
        if a.fixture_output:
            path=a.fixture_output.absolute();expected=ROOT/'apps/studio-web/tests/fixtures/native-tiktok-analytics-v2.json'
            if path!=expected or path.exists():raise ValueError('Fresh exact Studio fixture path required')
            write(path,fixture)
        summary={'status':'PASS','signed_ui_requests':sum(len(x['calls']) for x in [manual,plan_created,final]),'cold_ui_get_requests':len(check['ui']['calls']),
            'mock_provider_reads':len(case.wires),'nullable_cost_records':len(costs),'backup_sha256':backup['sha256'],'canonical_project_unchanged':True,
            'actual_receipt_posts_selected':2,'snapshots':2,'finite_plans':1,'winner_state':final['winner']['assessment']['state'],'learning_observations':final['learning']['observation_count'],
            'separate_process_keyless_Studio_history':'PASS','browser_rendered':False,'owner_uat':False,'real_provider_calls':0,'paid_operations':0,'accepted_media_generated':False,'published':False,'production_deployed':False,'manual_old_data_deleted':False}
        write(out/'summary.json',summary);print(json.dumps({'status':'PASS','evidence':str(out),'summary':summary}))
    finally:case.tearDown()
if __name__=='__main__':main()
