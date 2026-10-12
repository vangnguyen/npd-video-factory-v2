"""Actual six-role signed ingest with full SHA intent; generated media/fixture actor."""
import argparse,hashlib,json,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.tests.test_multipart_ingestion_http import MultipartHTTPTests
from services.windows_native.contracts import file_sha

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=pathlib.Path,required=True);parser.add_argument('--fixture',type=pathlib.Path);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(exist_ok=False)
    if args.fixture:assert not args.fixture.exists()
    case=MultipartHTTPTests();case.setUp()
    try:
        records=[]
        for kind,mime,raw in case.assets():
            body=case.body(raw,kind,mime);assert body['expected_sha256']==hashlib.sha256(raw).hexdigest()
            status,initial,headers=case.request('POST',case.base,body);assert status==200,initial
            received=initial
            for offset in range(0,len(raw),1048576):
                status,received,_=case.binary(initial,raw,offset);assert status==200,received
            completed=case.finish(received);asset=completed['result']['asset'];assert completed['result']['source_sha256']==body['expected_sha256']
            assert (case.root/'originals'/asset['original_id']).read_bytes()==raw
            duplicate_body=case.body(raw,kind,mime);status,duplicate_initial,_=case.request('POST',case.base,duplicate_body);assert status==200,duplicate_initial
            duplicate_received=duplicate_initial
            for offset in range(0,len(raw),1048576):
                status,duplicate_received,_=case.binary(duplicate_initial,raw,offset);assert status==200,duplicate_received
            duplicate=case.finish(duplicate_received);assert duplicate['result']['duplicate']
            records.append({'kind':kind,'source_hex':raw.hex(),'initial':initial,'received':received,'completed':completed,'duplicate':duplicate})
        fixture={'schema_version':'native-multipart-owned-http-sha-fixture-v1','fixture_kind':'actual_signed_local_six_role_SHA_intent_generated_media_fixture_actor_not_Owner_UAT',
                 'fixture_human':True,'provider_calls':0,'browser_rendered':False,'owner_uat':False,'records':records}
        (out/'wire-fixture.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if args.fixture:
            with args.fixture.open('x',encoding='utf-8') as h:json.dump(fixture,h,ensure_ascii=False,indent=2);h.write('\n')
        # The actual UI controller hashes source bytes and sends signed requests.
        config={'base':'http://127.0.0.1:'+str(case.server.server_port),'workspace_id':case.workspace,'project_id':case.project['id'],
                'revision':case.server.store.get(case.project['id'])['revision'],'cookie':case.cookie,'csrf':case.csrf,
                'subtitle_hex':records[-1]['source_hex'],'filename':records[-1]['initial']['request']['filename']}
        config_path=case.folder/'fixture-controller.json';config_path.write_text(json.dumps(config),encoding='utf-8')
        result=subprocess.check_output([r'C:\Program Files\nodejs\node.exe',str(ROOT/'scripts/native_upload_source_hash_http_ui.mjs'),str(config_path)],text=True,encoding='utf-8',timeout=60)
        controller=json.loads(result);assert controller['distinct_selected_sources']==2 and controller['new_assets']==1 and controller['same_file_replay_verified']
        (out/'controller.json').write_text(json.dumps(controller,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        state=case.server.store.get(case.project['id']);(out/'project.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        from services.windows_native.backup import create_backup,restore_backup
        archive=out/'owned-upload-sha-state.zip';receipt=create_backup(case.config,archive)
        restored=case.folder/'cold-state';restore_backup(archive,restored,expected_sha256=receipt['sha256'])
        cold=subprocess.check_output([sys.executable,'-X','utf8','-c',
            'import json,sys;from pathlib import Path;from services.windows_native.store import Store;from services.windows_native.multipart_ingestion import NativeMultipartIngestion;from services.windows_native.pipeline import Config;p=Path(sys.argv[1]);s=Store(p);c=Config(data_root=p);v=NativeMultipartIngestion(s,c,workspace_id=sys.argv[2]);print(json.dumps({"project":s.get(sys.argv[3]),"uploads":v.page(sys.argv[3])},ensure_ascii=False))',str(restored),case.workspace,case.project['id']],text=True,encoding='utf-8')
        recovered=json.loads(cold);assert recovered['project']==state
        assert recovered['uploads']==case.server.multipart_uploads.page(case.project['id'])
        evidence={'schema_version':'native-upload-source-hash-rehearsal-v1','six_roles_actual_signed_ingest_and_dedup':True,'controller':controller,
                  'cold_new_process_project_upload_receipts_exact':True,'backup_sha256':file_sha(archive),'generated_media':True,'fixture_human':True,
                  'Owner_UAT':False,'full_Mode_B_accepted':False,'external_provider_calls':0,'paid_calls':0,'TTS_inferences':0,'published':False,'production_deployed':False}
        (out/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:case.tearDown()
    print('UPLOAD_SOURCE_SHA_SIX_ROLE_CONTROLLER_AND_COLD_RESTORE_PASS')
if __name__=='__main__':main()
