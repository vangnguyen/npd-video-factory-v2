"""Fresh-process, offline custody proof. No worker or provider is dispatched."""
import argparse,json,socket,sys,tempfile,zipfile
from pathlib import Path
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO),str(REPO/'apps/api')]
from services.windows_native.backup import restore_backup,validate_archive
from services.windows_native.contracts import digest,file_sha
from services.windows_native.store import Store
from services.windows_native.pipeline import Config
from services.windows_native.stock import NativeStock
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_worker import NativeGenerationWorker
from services.windows_native.source_broll_resolution import NativeSourceBrollResolution


def main():
    parser=argparse.ArgumentParser()
    for name in ('evidence','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();folder=Path(args.evidence).resolve();out=Path(args.output).resolve();assert not out.exists()
    backup=json.loads((folder/'backup.json').read_bytes());expected=json.loads((folder/'resolver-rows.json').read_bytes())
    session=json.loads((folder/'resolution-final.json').read_bytes());job=json.loads((folder/'render-job.json').read_bytes())
    assert file_sha(folder/'resolved-broll-state.zip')==backup['sha256']
    with zipfile.ZipFile(folder/'resolved-broll-state.zip') as archive:
        manifest=validate_archive(archive)
    # A short owned root avoids Windows MAX_PATH during normal lifecycle
    # cleanup. Never revisit a previously retained cleanup-failure root.
    with tempfile.TemporaryDirectory(prefix='vfns-broll-cold-',dir='C:/') as temporary:
        root=Path(temporary)/'state'
        assert Path(temporary).resolve().parent==Path('C:/')
        with patch.object(socket.socket,'connect',side_effect=AssertionError('No network during cold custody proof')):
            restored=restore_backup(folder/'resolved-broll-state.zip',root,expected_sha256=backup['sha256'])
            store=Store(root);project=store.get(session['project_id'])
            with store.transaction() as con:
                actual={name:[dict(row) for row in con.execute('SELECT * FROM '+name)] for name in expected}
            assert actual==expected
            stock=NativeStock(store,Config(data_root=root),workspace_id=session['workspace_id'])
            generation=NativeGenerationWorker(NativeGenerationQueue(store,workspace_id=session['workspace_id']),Config(data_root=root))
            try:
                resolver=NativeSourceBrollResolution(store,Config(data_root=root),stock,generation,workspace_id=session['workspace_id'])
                assert resolver.get(project['id'],session['resolution_id'])==session
                assert store.get_job(job['id'])==job and job['result']['qc']['passed'] is True
                for entry in manifest['entries']:
                    if entry['path'].startswith('state/'):
                        assert file_sha(root/entry['path'].removeprefix('state/'))==entry['sha256']
                result={'schema_version':'source-broll-independent-cold-restore.v1','project_id':project['id'],
                    'project_sha256':digest(project),'resolver_history_sha256':digest(actual),'resolver_rows_exact':True,
                    'original_session_exact':True,'completed_render_job_exact':True,'archive_entries':backup['entries'],
                    'archive_sha256':backup['sha256'],'new_model_inferences':0,'provider_dispatches':0,'paid_calls':0,
                    'current_configuration_execution_after_root_change_certified':False,
                    'Owner_UAT':False,'full_Mode_A_B_accepted':False,'fresh_process_restore':True}
            finally:stock.close();generation.close()
    result['owned_new_temporary_root_cleaned']=True
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
