"""Fresh local playable source render -> Native review/four-platform dry runs -> process restore."""
import argparse
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.contracts import file_sha
from services.windows_native.pipeline import Config
from services.windows_native.publications import NativePublications
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier


def write(root,name,value):
    with (root/name).open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2)


def read(root,project):
    store=Store(root);service=NativePublications(store,ROOT/'packages/contracts/publishing-capabilities.json',workspace_id='wsp_native_publication_fixture')
    page=service.page(project,limit=100)
    return {'project':store.get(project),'page':page,'details':[service.get(project,row['publication_id']) for row in page['items']]}


class NoProvider:
    def run(self,*_):raise AssertionError('No production provider dispatch in publication rehearsal')


def run(args):
    root=Path(args.data_root).resolve();out=Path(args.output).resolve();media=Path(args.media_evidence).resolve()
    if root.parent!=Path('C:/') or not root.name.startswith('vf-native-fixture-publication-') or not root.is_dir():raise ValueError('Owned publication fixture required')
    evidence=json.loads((media/'evidence.json').read_text(encoding='utf-8'))
    if not evidence.get('explicit_fixture_owned_provenance') or not evidence.get('local_real_full_qc') or evidence.get('owner_uat'):raise ValueError('Fresh synthetic playable proof required')
    out.mkdir(parents=True,exist_ok=False);project=evidence['project_id'];job=evidence['job_id']
    before_hash=file_sha(root/'jobs'/job/'final.mp4');source_hashes={str(path.relative_to(root)):file_sha(path) for folder in ['assets','originals'] for path in (root/folder).iterdir() if path.is_file()}
    absent=root.parent/(root.name+'-absent-secrets');config=Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
    raw,registry=fixture('owner',workspace='wsp_native_publication_fixture');access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),'wsp_native_publication_fixture')
    server=LocalServer(0,config,pipeline=NoProvider(),start_worker=False,access=access)
    cookie,session=access.login(raw);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();calls=[];results=[]
    def request(method,path,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=20)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();headers=dict(response.getheaders());value=json.loads(response.read());connection.close()
        calls.append({'method':method,'path':path,'status':response.status});assert response.status==200,(response.status,value)
        assert headers['Cache-Control']=='no-store';return value
    try:
        revision=server.store.get(project)['revision']
        request('POST',f'/api/jobs/{job}/review',{'revision':revision,'reviewer':'EXPLICIT MOCK FINAL REVIEW — NOT OWNER UAT',
            'acknowledged':True,'decision':'approve','note':'Automated synthetic tone/source binding fixture, not Owner acceptance.'})
        baseline=server.store.get(project)
        base=f'/api/projects/{project}/publications'
        for platform in ['youtube','tiktok','instagram_reels','facebook']:
            body={'revision':revision,'final_job_id':job,'platform':platform,'mode':'dry_run',
                'metadata':{'title':'Native synthetic video — mô phỏng','description':'Generated testsrc and tone; saved ASR fixture.','privacy':'private'},
                'request_key':'native-real-media-dry-run-fixture-'+platform}
            prepared=request('POST',base,body);assert prepared['status']=='awaiting_publish_approval',prepared['snapshot']['validation']
            duplicate=request('POST',base,body);assert duplicate['idempotent_replay'] and duplicate['publication_id']==prepared['publication_id']
            route=base+'/'+prepared['publication_id'];approved=request('POST',route+'/approve',{'expected_fingerprint':prepared['request_fingerprint'],
                'expected_artifact_sha256':before_hash,'acknowledged':True});assert approved['status']=='queued'
            done=request('POST',route+'/dry-run',{'expected_fingerprint':prepared['request_fingerprint']});assert done['status']=='dry_run_succeeded'
            assert done['receipt']['mock'] and done['receipt']['remote_post_id'] is None and not done['receipt']['external_action']
            repeat=request('POST',route+'/dry-run',{'expected_fingerprint':prepared['request_fingerprint']});assert repeat==done
            results.append(done)
        history=request('GET',base+'?limit=2');assert len(history['items'])==2 and history['next_cursor']
        from urllib.parse import quote
        second=request('GET',base+'?limit=2&cursor='+quote(history['next_cursor']));assert len(second['items'])==2 and second['next_cursor'] is None
        assert server.store.get(project)==baseline and file_sha(root/'jobs'/job/'final.mp4')==before_hash
        assert all(file_sha(root/name)==sha for name,sha in source_hashes.items())
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    expected=read(root,project)
    restored=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root),'--project',project],timeout=60));assert restored==expected
    write(out,'publication-results.json',results);write(out,'first-history-page.json',history);write(out,'second-history-page.json',second)
    write(out,'restored-state.json',restored);write(out,'requests.json',{'authenticated_native_requests':calls,'actual_external_calls':0})
    write(out,'contract.json',{'status':'PASS','authenticated_native_requests':len(calls),'platforms':4,'dry_run_receipts':4,
        'fresh_process_exact_restore':True,'metadata_review_and_publish_approval_separate':True,'duplicate_requests_and_dispatch_replay_preserved':True,
        'keyset_history_two_pages':True,'canonical_project_unchanged_after_final_review':True,'final_and_source_bytes_unchanged':True,
        'final_sha256':before_hash,'playable_media_evidence':str(media),'local_real_full_media_qc':True,
        'source_is_synthetic_testsrc_and_tone':True,'transcript_is_saved_asr_fixture':True,'real_provider_calls':0,
        'mock_human_final_and_publish_reviews':True,'owner_uat_accepted':False,'actual_external_calls':0,'real_credentials_read':0,'paid_calls':0,
        'real_platform_validation_accepted':False,'live_native_adapter':'NOT_CONFIGURED','external_publication':False,
        'accepted_media_replaced':False,'publishing_ready':False,'implementation_complete':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','output':str(out),'platforms':4,'dry_run_receipts':4,'native_requests':len(calls),'fresh_process_restore':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root');parser.add_argument('--media-evidence');parser.add_argument('--output');parser.add_argument('--read-root');parser.add_argument('--project');args=parser.parse_args()
    if args.read_root:print(json.dumps(read(args.read_root,args.project),ensure_ascii=True))
    elif args.output:run(args)
    else:parser.error('--output or --read-root required')
