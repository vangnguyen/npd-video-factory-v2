"""Owned loopback browser fixture; stop marker exports exact immutable upload state."""
import argparse,json,pathlib,sys,tempfile,time,wave,math,array
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.tests.test_multipart_ingestion_http import MultipartHTTPTests
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.multipart_ingestion import NativeMultipartIngestion

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False)
    case=MultipartHTTPTests()
    # Use the established fixture server/auth helpers; this root is newly owned.
    with tempfile.TemporaryDirectory(prefix='vf-upload-hash-browser-',dir='C:/') as temporary:
        owned=pathlib.Path(temporary);case.folder=owned;case.root=owned/'state'
        case.config=Config(data_root=case.root,runtime_root=owned/'runtime',secret_file=owned/'secrets/absent.env',assemblyai_secret_file=owned/'secrets/absent.dpapi')
        case.store=Store(case.root);case.project=case.store.create('Upload SHA browser fixture — generated media','','media')
        case.start_server()
        try:
            from services.windows_native.tests.test_human_identity import fixture
            token,_=fixture('editor',workspace=case.workspace)
            inputs=[]
            for kind,mime,raw in case.assets():
                folder=owned/'inputs'/kind;folder.mkdir(parents=True);path=folder/'Source không phụ thuộc đuôi.bin';path.write_bytes(raw)
                inputs.append({'kind':kind,'mime':mime,'path':str(path),'bytes':len(raw)})
            raw=path.read_bytes();alternate=owned/'inputs/alternate/Source không phụ thuộc đuôi.bin';alternate.parent.mkdir();alternate.write_bytes(raw[:-2]+b'?'+raw[-1:]);assert alternate.stat().st_size==len(raw)
            large=owned/'inputs/large/Large audio nguồn.bin';large.parent.mkdir()
            samples=array.array('h',(round(3000*math.sin(2*math.pi*440*i/16000)) for i in range(34*16000)))
            with wave.open(str(large),'wb') as audio:audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000);audio.writeframes(samples.tobytes())
            changed=owned/'inputs/changed/Large audio nguồn.bin';changed.parent.mkdir();data=large.read_bytes();changed.write_bytes(data[:-1]+bytes([data[-1]^1]));assert len(data)>1048576
            original_chunk=case.server.multipart_uploads.chunk;delayed=[]
            def delayed_chunk(project,identity,offset,sha,raw):
                result=original_chunk(project,identity,offset,sha,raw)
                if offset==0 and result[0]['request']['total_bytes']>1048576 and identity not in delayed:
                    delayed.append(identity);(out/'first-large-chunk.json').write_text(json.dumps({'upload_id':identity,'received_bytes':result[0]['received_bytes'],'intent_sha256':result[0]['request']['expected_sha256'],'fixture_response_delay_seconds':5}),encoding='utf-8');time.sleep(5)
                return result
            case.server.multipart_uploads.chunk=delayed_chunk
            witness={'url':'http://127.0.0.1:'+str(case.server.server_port)+'/?project='+case.project['id'],'token':token,'project_id':case.project['id'],
                     'workspace_id':case.workspace,'owned_root':str(owned),'inputs':inputs,'same_name_size_subtitle_alternate':str(alternate),
                     'large_audio':str(large),'changed_tail_audio':str(changed),'fixture_first_large_chunk_response_delay_seconds':5,
                     'fixture_human':True,'generated_media':True,'Owner_UAT':False,'worker_started':False}
            (out/'browser.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('BROWSER_FIXTURE_READY',flush=True)
            deadline=time.monotonic()+1500
            while not (out/'stop').exists():
                if time.monotonic()>deadline:raise TimeoutError('Owned browser fixture deadline reached')
                time.sleep(.2)
            project=case.server.store.get(case.project['id']);uploads=case.server.multipart_uploads.page(case.project['id'])
            (out/'project.json').write_text(json.dumps(project,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(out/'uploads.json').write_text(json.dumps(uploads,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            archive=out/'owned-browser-upload-state.zip';backup=create_backup(case.config,archive)
            restored=owned/'restored';restore_backup(archive,restored,expected_sha256=backup['sha256'])
            restored_store=Store(restored);restored_uploads=NativeMultipartIngestion(restored_store,Config(data_root=restored),workspace_id=case.workspace)
            assert restored_store.get(case.project['id'])==project and restored_uploads.page(case.project['id'])==uploads
            (out/'helper.json').write_text(json.dumps({'backup_sha256':backup['sha256'],'restored_state_exact':True,'owned_root_cleaned_by_lifecycle':True,
                'fixture_human':True,'Owner_UAT':False,'provider_calls':0,'paid_calls':0,'published':False,'production_deployed':False},indent=2)+'\n',encoding='utf-8')
        finally:case.stop_server()
    print('BROWSER_OWNED_STATE_BACKUP_RESTORE_AND_CLEANUP_PASS',flush=True)
if __name__=='__main__':main()
