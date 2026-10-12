"""Owned known-motion and occlusion footage; real local tracking/preview/render/recovery."""
import argparse,http.client,json,subprocess,sys,threading,time,uuid,tempfile,shutil
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw
import numpy as np
from scripts.north_star_native_channel_profiles import config as settings
from scripts.north_star_native_analytics_refresh import access,write
from services.windows_native.server import LocalServer
from services.windows_native.pipeline import Pipeline
from services.windows_native.contracts import file_sha,digest
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native import auto_edit_analysis
from services.windows_native.backup import create_backup,restore_backup


def movie(config,directory,lost):
    directory.mkdir();rng=np.random.default_rng(27);marker=np.stack([rng.integers(10,80,(40,40)),rng.integers(150,250,(40,40)),rng.integers(10,80,(40,40))],axis=2).astype('uint8');patch_image=Image.fromarray(marker)
    truth=[]
    for frame in range(30):
        image=Image.new('RGB',(320,240),(30,30,30));x=40+2*frame
        if not lost or frame<10:image.paste(patch_image,(x,72))
        ImageDraw.Draw(image).rectangle((0,224,319,239),fill=(70+frame*5,20,120-frame*2));image.save(directory/f'{frame:03d}.png')
        truth.append({'timestamp_seconds':frame/10,'source_box':None if lost and frame>=10 else {'x':x/320,'y':.3,'width':.125,'height':1/6}})
    target=directory/'source.mp4'
    subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-framerate','10','-i',str(directory/'%03d.png'),'-f','lavfi','-i','sine=frequency=660:duration=3',
        '-c:v','libx264','-crf','0','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-t','3',str(target)],check=True,capture_output=True,timeout=30)
    return target,truth


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence-dir',type=Path,required=True);parser.add_argument('--reopen',type=Path);args=parser.parse_args();out=args.evidence_dir.resolve()
    if args.reopen:
        config=settings(args.reopen);auth,_,_=access();server=LocalServer(0,config,start_worker=False,access=auth)
        try:
            expected=json.loads((out/'expected-projects.json').read_bytes())
            for project in expected:
                assert server.store.get(project['id'])==project
                from services.windows_native.source_tracking import read_saved
                record=project['document']['source_tracking_analyses'][0]
                with server.store.transaction() as con:assert read_saved(server.store,con,project,record['analysis']['tracking_id'],record['sha256'])==record
            assert not server.runner.run_one();write(out/'cold-process.json',{'actual_separate_process':True,'exact_projects_and_tracking_frames':True,'provider_calls':0,'new_jobs':0,'owner_UAT':False})
        finally:server.server_close()
        return
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external output required')
    out.mkdir(parents=True);bundles=[]
    with tempfile.TemporaryDirectory(prefix='vf-subject-tracking-',dir='C:/') as temporary:
        owned=Path(temporary);config=settings(owned/'state');auth,cookie,session=access();server=LocalServer(0,config,pipeline=Pipeline(config),start_worker=False,access=auth);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[]
        def request(method,path,body=None,binary=None,headers=None,status=200):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30);connection.request(method,path,body=binary if binary is not None else json.dumps(body) if body is not None else None,
                headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf,**(headers or {})});response=connection.getresponse();v=json.loads(response.read());connection.close();requests.append({'method':method,'path':path,'status':response.status});assert response.status==status,v;return v
        try:
            for label,lost in [('tracked',False),('lost',True)]:
                folder=out/label;folder.mkdir();source,truth=movie(config,owned/label,lost);original=file_sha(source);write(folder/'ground-truth.json',{'synthetic_known_motion':True,'face_inference':False,'frames':truth})
                project=request('POST','/api/projects',{'name':'EXPLICIT SYNTHETIC LOCAL TRACKING '+label,'prompt':'','input_kind':'media','channel_profile_ref':'ai-education-reference@1'},status=201)
                project=request('POST',f'/api/projects/{project["id"]}/media',binary=source.read_bytes(),headers={'Content-Type':'video/mp4','X-VF-Revision':str(project['revision']),'X-VF-Rights':'confirmed','X-VF-Illustration':'false','X-VF-Filename':'explicit-synthetic-known-motion.mp4'},status=201)
                asset=project['document']['assets'][0];job=server.store.enqueue(project['id'],project['revision'],'asr',uuid.uuid4().hex);claimed=server.store.claim();assert claimed['id']==job['id'];server.store.finish(claimed,result={'media_analysis':[saved_asr(asset)]})
                current=server.store.get(project['id']);request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':current['revision'],'kind':'auto_edit_analysis','request_key':uuid.uuid4().hex});assert server.runner.run_one()
                analyzed=auto_edit_analysis.view(server.store,project['id']);analysis=analyzed['analyses'][0]['analysis'];project=request('POST',f'/api/projects/{project["id"]}/auto-edit/timeline',{'revision':analyzed['revision'],'action':'create','payload':{'analysis_id':analysis['analysis_id'],'transcript_id':analysis['transcript']['transcript_id']}})
                stopped=threading.Event();errors=[]
                def drain():
                    try:
                        while not stopped.wait(.02):server.runner.run_one()
                    except BaseException as error:errors.append(type(error).__name__)
                worker=threading.Thread(target=drain,daemon=True);worker.start();context=owned/(label+'-controller-input.json');write(context,{'fixture_human':True,'origin':'http://127.0.0.1:'+str(server.server_port),'workspace_id':auth.workspace_id,'cookie':cookie,'csrf':session.csrf,'project_id':project['id'],'expected_status':'fallback_required' if lost else 'tracked','request_key':uuid.uuid4().hex})
                try:run=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(ROOT/'scripts/native_subject_tracking_http_ui.mjs'),str(context)],capture_output=True,timeout=90)
                finally:stopped.set();worker.join(timeout=15)
                assert not errors and not worker.is_alive(),errors
                if run.returncode:
                    (folder/'failed-controller.log').write_bytes(run.stderr)
                    write(folder/'failed-project.json',server.store.get(project['id']))
                    write(folder/'failed-backup.json',create_backup(config,folder/'failed-owned-state.zip'))
                    raise AssertionError('Controller failed; retained evidence')
                controller=json.loads(run.stdout);write(folder/'controller.json',controller);project=controller['project'];record=controller['record'];frames=record['analysis']['frames'];assert file_sha(source)==original
                if not lost:
                    errors_px=[]
                    for frame in frames:
                        observation=frame['observation'];expected=truth[min(29,round(observation['timestamp_seconds']*10))]['source_box'];actual=observation['bounding_box'];errors_px.append(abs(actual['x']-expected['x'])*320)
                    assert max(errors_px)<2.1,errors_px;write(folder/'independent-position-check.json',{'known_source_motion':True,'maximum_source_x_error_pixels':max(errors_px),'compared_samples':len(errors_px),'not_semantic_inference':True})
                else:assert any(frame['observation']['status']=='lost' for frame in frames)
                request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':project['revision'],'kind':'render','request_key':uuid.uuid4().hex},status=409)
                request('POST',f'/api/projects/{project["id"]}/preview',{'revision':project['revision'],'action':'generate'});deadline=time.monotonic()+180
                while time.monotonic()<deadline:
                    preview=server.previews.status(project['id'])
                    if preview['status'] not in ['QUEUED','RUNNING']:break
                    time.sleep(.1)
                assert preview['status']=='READY',preview
                request('POST',f'/api/projects/{project["id"]}/approve',{'revision':project['revision'],'reviewer':'EXPLICIT TRACKING FIXTURE — NOT OWNER UAT','acknowledged':True})
                final=request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':project['revision'],'kind':'render','request_key':uuid.uuid4().hex})
                with patch('services.windows_native.pipeline.verify_runtime',side_effect=AssertionError('No TTS/provider')):assert server.runner.run_one()
                final=server.store.get_job(final['id']);source_folder=config.data_root/'jobs'/final['id']
                if lost:
                    assert final['status']=='failed_qc' and final['error']['code']=='AUTO_EDIT_MEDIA_QC_FAILED',final
                    failed_folders=[p.parent for p in source_folder.glob('attempts/*/qc-report.json') if json.loads(p.read_bytes()).get('passed') is False]
                    assert len(failed_folders)==1;failed=failed_folders[0];qc=json.loads((failed/'qc-report.json').read_bytes())
                    assert qc['publishing_blocked'] is True and qc['failures']==['freeze-frame ratio exceeds 15 percent'],qc['failures']
                    write(folder/'failed-render-job.json',final)
                    for name in ['final.mp4','qc-report.json','render-manifest.json','timeline.json','timeline-render.json','audio-analysis.json','cost.json']:
                        if (failed/name).is_file():shutil.copyfile(failed/name,folder/('candidate-failed-qc.mp4' if name=='final.mp4' else name))
                    denied=request('POST',f'/api/jobs/{final["id"]}/review',{'revision':project['revision'],'reviewer':'EXPLICIT NEGATIVE QC FIXTURE','acknowledged':True,'decision':'approve'},status=409)
                    write(folder/'negative-final-review.json',denied)
                else:
                    assert final['status']=='succeeded' and final['result']['qc']['passed'],final.get('error')
                    for name in ['final.mp4','qc-report.json','render-manifest.json','timeline.json','timeline-render.json','audio-analysis.json','cost.json']:shutil.copyfile(source_folder/name,folder/name)
                shutil.copyfile(server.previews.video_path(project['id'],preview['timeline_version']),folder/'preview.mp4');write(folder/'project.json',server.store.get(project['id']));write(folder/'tracking-analysis.json',record)
                output_name='candidate-failed-qc.mp4' if lost else 'final.mp4'
                bundles.append({'case':label,'project_id':project['id'],'render_job_id':final['id'],'tracking_id':record['analysis']['tracking_id'],'source_sha256':original,'output_sha256':file_sha(folder/output_name),'output_name':output_name,'source_original_unchanged':True,'full_QC_passed':not lost,'negative_QC_gate_passed':lost,'render_status':final['status'],'real_ASR':False,'saved_ASR_fixture':True,'real_semantic_Vision':False,'fixture_approval':True,'owner_UAT':False})
            expected=[server.store.get(v['project_id']) for v in bundles];write(out/'expected-projects.json',expected);write(out/'backup.json',create_backup(config,out/'owned-tracking-backup.zip'))
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
        restored=owned/'restored';write(out/'restore.json',restore_backup(out/'owned-tracking-backup.zip',restored,expected_sha256=file_sha(out/'owned-tracking-backup.zip')))
        run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--evidence-dir',str(out),'--reopen',str(restored)],capture_output=True,timeout=60)
        if run.returncode:(out/'failed-cold-process.log').write_bytes(run.stderr);raise AssertionError('Cold process verification failed')
        write(out/'evidence.json',{'schema_version':'owned-native-subject-tracking-rehearsal-v1','bundles':bundles,'parent_requests':requests,'actual_shipped_controller':True,'actual_signed_HTTP':True,'actual_decoded_source_pixels_and_PTS':True,'actual_local_template_tracking':True,'actual_separate_process_restore':True,'owned_temp_cleaned_after_export':True,'fixture_DOM':True,'browser_rendered':False,'saved_ASR_fixture':True,'real_ASR_provider':False,'semantic_inference':False,'provider_calls':0,'paid_calls':0,'Owner_UAT':False,'production_deployed':False,'publishing_enabled':False})
    print(json.dumps({'status':'LOCAL_TRACKING_PREVIEW_RENDER_COLD_RECOVERY_PASS','bundles':len(bundles),'provider_calls':0}))


if __name__=='__main__':main()
