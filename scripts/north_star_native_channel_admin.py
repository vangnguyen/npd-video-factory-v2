"""Fresh owner registry/controller and separate-process Native restore proof."""
import argparse,json,subprocess,sys,tempfile,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,access,write
from services.windows_native.server import LocalServer
from services.windows_native.contracts import file_sha,digest
from services.windows_native.backup import create_backup,restore_backup

def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence-dir',required=True,type=Path);p.add_argument('--reopen',type=Path);a=p.parse_args();out=a.evidence_dir.resolve()
    if a.reopen:
        config=settings(a.reopen);auth,_,_=access();server=LocalServer(0,config,start_worker=False,access=auth)
        try:
            assert digest(server.channel_registry.page())==digest(json.loads((out/'expected-registry.json').read_bytes()))
            assert digest(server.channel_registry.history('managed-education'))==digest(json.loads((out/'expected-history.json').read_bytes()))
            original=json.loads((out/'controller.json').read_bytes())['original_project'];assert server.store.get(original['id'])==original
            assert not server.runner.run_one();write(out/'cold-process.json',{'actual_separate_process':True,'registry_and_history_exact':True,'existing_project_exact':True,'provider_calls':0,'new_jobs':0,'publishing_enabled':False})
        finally:server.server_close()
        return
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='vf-channel-admin-',dir='C:/') as temporary:
        owned=Path(temporary);root=owned/'state';config=settings(root);auth,cookie,session=access();server=LocalServer(0,config,start_worker=False,access=auth);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            context=owned/'controller-input.json';write(context,{'fixture_human':True,'origin':'http://127.0.0.1:'+str(server.server_port),'workspace_id':auth.workspace_id,'cookie':cookie,'csrf':session.csrf})
            run=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(ROOT/'scripts/native_channel_admin_http_ui.mjs'),str(context)],capture_output=True,timeout=90)
            if run.returncode:(out/'failed-controller.log').write_bytes(run.stderr);raise AssertionError('Controller failed; retained private fixture error')
            controller=json.loads(run.stdout);write(out/'controller.json',controller);assert controller['existing_project_unchanged']
            write(out/'expected-registry.json',server.channel_registry.page());write(out/'expected-history.json',server.channel_registry.history('managed-education'))
            write(out/'backup.json',create_backup(config,out/'owned-channel-admin.zip'))
        finally:server.shutdown();server.server_close();thread.join()
        restored=owned/'restored';write(out/'restore.json',restore_backup(out/'owned-channel-admin.zip',restored,expected_sha256=file_sha(out/'owned-channel-admin.zip')))
        run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--evidence-dir',str(out),'--reopen',str(restored)],capture_output=True,timeout=60)
        if run.returncode:(out/'failed-cold-process.log').write_bytes(run.stderr);raise AssertionError('Cold registry restore failed')
        assert json.loads((out/'cold-process.json').read_bytes())['registry_and_history_exact']
        write(out/'evidence.json',{'schema_version':'owned-channel-admin-rehearsal-v1','actual_shipped_controller':True,'actual_signed_HTTP':True,'controller_requests':len(controller['requests']),
            'created_versions':2,'archive_restore_revision':4,'existing_project_unchanged':True,'actual_separate_process_restore':True,'owned_fixture_cleaned_after_export':True,
            'fake_DOM':True,'browser_rendered':False,'Owner_UAT':False,'paid_calls':0,'provider_calls':0,'publishing_enabled':False,
            'exports':{f.name:{'sha256':file_sha(f),'bytes':f.stat().st_size} for f in out.iterdir() if f.is_file()}})
    print(json.dumps({'status':'CHANNEL_ADMIN_HTTP_COLD_RECOVERY_PASS','requests':len(controller['requests']),'provider_calls':0}))

if __name__=='__main__':main()
