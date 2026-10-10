"""Retain UI-to-owned-HTTP evidence; not a browser/provider/Owner acceptance run."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'apps/api'),str(ROOT)]
from services.windows_native.tests.test_tiktok_distribution_http import TikTokDistributionHTTPTests
from services.windows_native.tests.test_tiktok_creators import TOKEN
from services.windows_native.tests.test_tiktok_publish_worker import UPLOAD_TOKEN,URI
from services.windows_native.backup import create_backup
from scripts.north_star_native_official_analytics import settings

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve()
    if out.parent!=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007') or not out.name.startswith('tiktok-studio-flow-n') or out.exists():raise ValueError('Fresh owned evidence output required')
    out.mkdir();case=TikTokDistributionHTTPTests('test_owned_startup_binds_same_creator_service_and_signed_private_pipeline');original_response=case.response;reads=[0]
    def response(request):
        if request.url.path=='/v2/post/publish/status/fetch/':
            reads[0]+=1
            if reads[0]==2:case.status='PUBLISH_COMPLETE'
        return original_response(request)
    case.response=response;case.setUp()
    try:
        original=case.server.store.get(case.c.project['id']);draft=case.request('GET',case.base.removesuffix('/official-publications')+'/tiktok-creators/drafts?limit=25')[1]['items'][0]
        assert case.c.factory.client.network_enabled is False and case.c.distribution.client.network_enabled is False
        data={'origin':'http://127.0.0.1:'+str(case.server.server_port),'cookie':case.cookie,'csrf':case.csrf,'workspace_id':case.c.workspace,'project':original,'draft':draft}
        result=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(ROOT/'scripts/north_star_tiktok_studio.mjs')],input=json.dumps(data),capture_output=True,text=True,encoding='utf8',timeout=90,cwd=ROOT)
        if result.returncode:raise AssertionError(result.stderr)
        flow=json.loads(result.stdout);assert flow['status']=='PASS';value=flow['publication']
        final=case.service.get(value['project_id'],value['publication_id']);dispatch=case.state(value);assert final['mock_publication_complete'] is True and final['published'] is False
        assert final==flow['publication'] and dispatch==flow['dispatch'] and reads[0]==2
        assert case.server.store.get(original['id'])==original and case.pipeline.calls==0
        init=sum(x['path'].endswith('/init/') for x in case.publish_wires);chunks=sum(x['method']=='PUT' for x in case.publish_wires);assert init==chunks==1
        with case.server.store.transaction() as con:costs=[dict(x) for x in con.execute('SELECT * FROM native_cost_operations')]
        assert not any(x['paid'] for x in costs)
        evidence={**flow,'final_status_completed_by_ui_owner_mock_poll':True,'final_publication':final,'final_dispatch':dispatch,'project_unchanged':True,'initializations':init,'chunks':chunks,'cost_operations':len(costs),'paid_operations':0,'manual_data_deleted':False,
            'fixture_lifetime':'TemporaryDirectory standard cleanup after public backup; no accepted artifact replaced'}
        raw=json.dumps(evidence,ensure_ascii=False,indent=2)+'\n';assert all(v not in raw for v in (TOKEN,UPLOAD_TOKEN,URI,case.cookie,case.csrf,case.c.raw))
        (out/'flow.json').write_text(raw,encoding='utf8',newline='\n');backup=create_backup(settings(case.c.root),out/'public-state.zip')
        (out/'backup.json').write_text(json.dumps(backup,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'status':'PASS','output':str(out),'ui_http_requests':len(flow['calls']),'final_owner_mock_polls_from_python':0,'init':init,'chunks':chunks,'costs':len(costs),'public_backup_sha256':backup['sha256'],'provider_calls':0,'browser_rendered':False}))
    finally:case.tearDown()

if __name__=='__main__':main()
