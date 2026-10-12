"""Explicit visual-only rebind on an owned copy; never regenerate source voice."""
import argparse,http.client,json,shutil,subprocess,sys,tempfile,threading,time,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,access,write
from services.windows_native.server import LocalServer
from services.windows_native.backup import restore_backup,create_backup
from services.windows_native.contracts import file_sha
from services.windows_native.narration import identity
from services.windows_native.render_labels import resolve
from services.windows_native.costs import CostLedger

def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True,type=Path);p.add_argument('--evidence-dir',required=True,type=Path);args=p.parse_args()
    bundle=args.bundle.resolve();out=args.evidence_dir.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);e=json.loads((bundle/'evidence.json').read_bytes())
    for name,record in e['exports'].items():assert file_sha(bundle/name)==record['sha256'],name
    archive=bundle/'owned-master-backup.zip';requests=[];success=False
    with tempfile.TemporaryDirectory(prefix='vf-tech-label-',dir='C:/') as temporary:
        root=Path(temporary)/'state';config=settings(root);write(out/'initial-restore.json',restore_backup(archive,root,expected_sha256=e['exports'][archive.name]['sha256']))
        auth,cookie,session=access();server=LocalServer(0,config,start_worker=False,access=auth);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def send(method,path,body=None,expected=200):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=60);connection.request(method,path,
                body=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
            response=connection.getresponse();value=json.loads(response.read());connection.close();requests.append({'method':method,'path':path,'status':response.status})
            assert response.status==expected,(response.status,value);return value
        try:
            base='/api/projects/'+e['project_id'];before=send('GET',base);reference=before['document']['prepared_narration'];before_identity=identity(before['document'])
            raw=root/'jobs'/reference['job_id']/'voice.wav';voice_sha=file_sha(raw);assert voice_sha==e['source_voice_sha256']
            original_assets={a['id']:a['sha256'] for a in before['document']['assets']}
            current=send('POST',base+'/brand-template',{'revision':before['revision'],'brand_id':'vf-ai-education','template_id':'ai-education-30','duration_mode':'fit_narration_preserve_voice_speed'})
            assert resolve(before['document'])=='Phối cảnh minh họa' and resolve(current['document'])=='Minh họa kỹ thuật'
            assert current['document']['brand_template']['template']['purpose']=='education'
            assert identity(current['document'])==before_identity and current['document']['prepared_narration']==reference and current['approval'] is None
            assert {a['id']:a['sha256'] for a in current['document']['assets']}==original_assets
            original_run=subprocess.run
            def without_tts_child(command,*args,**kwargs):
                if isinstance(command,(list,tuple)) and 'services.windows_native.tts_child' in command:raise AssertionError('No fresh TTS child allowed')
                return original_run(command,*args,**kwargs)
            with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new local or remote inference permitted')),patch('subprocess.run',side_effect=without_tts_child):
                send('POST',base+'/approve',{'revision':current['revision'],'reviewer':'EXPLICIT FIXTURE BEFORE NEW PREVIEW','acknowledged':True},400)
                send('POST',base+'/preview',{'revision':current['revision'],'action':'generate'});deadline=time.monotonic()+180
                while time.monotonic()<deadline:
                    preview=send('GET',base+'/preview')
                    if preview['status'] not in {'QUEUED','RUNNING'}:break
                    time.sleep(.2)
                assert preview['status']=='READY' and preview['final_approval_eligible'],preview;write(out/'preview.json',preview)
                shutil.copyfile(server.previews.video_path(e['project_id'],preview['timeline_version']),out/'preview.mp4')
                current=send('POST',base+'/approve',{'revision':current['revision'],'reviewer':'EXPLICIT SIGNED LABEL FIXTURE; NOT OWNER UAT','acknowledged':True})
                queued=send('POST',base+'/jobs',{'revision':current['revision'],'kind':'render','request_key':uuid.uuid4().hex});assert server.runner.run_one()
                job=server.store.get_job(queued['id']);write(out/'render-job.json',job);assert job['status']=='succeeded',job.get('error')
            directory=root/'jobs'/job['id'];qc=job['result']['qc'];assert qc['passed'] and qc['full_quality']['status']=='passed'
            assert not list((directory/'attempts').glob('tts-*'))
            manifest=json.loads((directory/'render-manifest.json').read_bytes());assert manifest['render_labels']==current['document']['render_labels']
            assert file_sha(directory/'voice.wav')==voice_sha==file_sha(raw)
            reuse=json.loads((directory/'voice-reuse.json').read_bytes());assert reuse['new_inference_calls']==0
            for name in ['final.mp4','voice.wav','voice.json','tts-plan.json','timeline.json','subtitles.ass','render-manifest.json','qc-report.json','full-qc-report.json','voice-reuse.json']:
                if (directory/name).exists():shutil.copyfile(directory/name,out/name)
            write(out/'qc.json',qc)
            send('POST','/api/jobs/'+job['id']+'/review',{'revision':job['revision'],'reviewer':'EXPLICIT FINAL LABEL FIXTURE; NOT OWNER UAT','acknowledged':True,
                'decision':'approve','note':'Technical fixture only; Owner/listening/rights and complete modes remain separate.'})
            final=send('GET',base);write(out/'project.json',final);write(out/'canonical-timeline.json',final['document']['canonical_timeline'])
            write(out/'original-master.json',before);write(out/'asset-provenance.json',final['document']['assets']);write(out/'script.json',final['document']['proposal'])
            write(out/'storyboard.json',final['document']['edit_plan']);write(out/'cost.json',CostLedger(server.store).summary(e['project_id']))
            with server.store.transaction() as con:write(out/'job-events.json',[dict(row) for row in con.execute('SELECT * FROM events WHERE project_id=? ORDER BY id',(e['project_id'],))])
            write(out/'http-requests.json',requests);write(out/'backup.json',create_backup(config,out/'owned-master-backup.zip'))
            write(out/'evidence.json',{'schema_version':'native-technology-label-rebind-v1','project_id':e['project_id'],'render_job_id':job['id'],
                'source_voice_sha256':voice_sha,'before_label':'Phối cảnh minh họa','after_label':'Minh họa kỹ thuật','local_preview_render_full_QC':True,
                'source_narration_identity_and_PCM_unchanged':True,'assets_unchanged':True,'prior_artifacts_replaced':False,'new_inference_calls':0,
                'remote_provider_calls':0,'paid_calls':0,'human_HTTP_requests':len(requests),'Owner_UAT':False,'browser_rendered':False,'real_published':False,'production_deployed':False,
                'owned_temporary_data_cleaned_after_export':True,'exports':{f.name:{'sha256':file_sha(f),'bytes':f.stat().st_size} for f in out.iterdir() if f.is_file()}})
            success=True;print(json.dumps({'status':'TECHNOLOGY_FROZEN_LABEL_REBIND_PASS','project_id':e['project_id'],'voice_sha256':voice_sha,'backup_sha256':file_sha(out/'owned-master-backup.zip')}))
        finally:
            server.shutdown();server.server_close();thread.join()
            if not success:write(out/'failure-backup.json',create_backup(config,out/'failed-owned-rebind-backup.zip'))

if __name__=='__main__':main()
