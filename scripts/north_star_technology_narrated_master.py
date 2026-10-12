"""Real local spoken technology master using configured Native channel/engine.

One existing locked offline TTS invocation, no remote provider or secret. All
HTTP approvals are explicit fixture decisions; Owner/listening/legal/full Mode
A acceptance remain separate. Only a freshly owned temporary root is removed,
after successful export/backup or a retained failure backup.
"""
import argparse, http.client, io, json, shutil, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,access,write,WORKSPACE
from services.windows_native.server import LocalServer
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup
from services.windows_native.costs import CostLedger

TEXTS=['Hiệu ứng video có thể thay đổi màu sắc.','Hãy xem lại hình ảnh trước khi đăng.']
CORE=['pipeline.py','store.py','editor.py','branding.py','contracts.py','channel_profiles.py','narration.py','narration_preview.py','narrated_variants.py']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence-dir',type=Path,required=True);a=parser.parse_args();out=a.evidence_dir.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);before={p:file_sha(ROOT/'services/windows_native'/p) for p in CORE}
    requests=[];server=None;success=False
    with tempfile.TemporaryDirectory(prefix='vf-tech-',dir='C:/') as temporary:
        owned=Path(temporary);root=owned/'state';config=settings(root);auth,cookie,session=access()
        server=LocalServer(0,config,start_worker=False,access=auth);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def send(method,path,body=None,expected=200,headers=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=60)
            binary=isinstance(body,bytes);wire=body if binary else json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None
            connection.request(method,path,body=wire,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf,**(headers or {})})
            response=connection.getresponse();raw=response.read();connection.close();value=json.loads(raw)
            requests.append({'method':method,'path':path,'status':response.status});assert response.status==expected,(response.status,value)
            return value
        try:
            p=send('POST','/api/projects',{'name':'AI dễ hiểu · kiểm tra hiệu ứng video','prompt':' '.join(TEXTS),'input_kind':'script',
                'channel_profile_ref':'ai-education-reference@1','production_quality':True,'narrated_workflow':True},201)
            base='/api/projects/'+p['id'];proposal={'narration':' '.join(TEXTS),'visual_brief':[
                {'scene':1,'visual':'Owned manual diagram: the same color bars with different filter levels.','on_screen_text':'Hiệu ứng làm đổi màu','narration_excerpt':TEXTS[0]},
                {'scene':2,'visual':'Owned manual illustration of a before/after review checklist.','on_screen_text':'Xem lại trước khi đăng','narration_excerpt':TEXTS[1]}],
                'facts_needing_source':[]}
            p=send('POST',base+'/draft',{'revision':p['revision'],'proposal':proposal})
            selections=[]
            for index in range(2):
                image=Image.new('RGB',(640,360),'#10233b');draw=ImageDraw.Draw(image)
                colors=['#ffcc4d','#27c6ab','#4277ee','#d35ace']
                for ordinal,color in enumerate(colors):draw.rounded_rectangle((45+ordinal*145,75,160+ordinal*145,275),radius=15,fill=color)
                if index:draw.line((50,300,220,315,430,300,590,320),fill='white',width=6)
                buf=io.BytesIO();image.save(buf,format='PNG');data=buf.getvalue()
                p=send('POST',base+'/media',data,201,{'Content-Type':'image/png','X-VF-Revision':str(p['revision']),
                    'X-VF-Rights':'confirmed','X-VF-Illustration':'true','X-VF-Filename':f'owned-manual-technology-{index+1}.png'})
                asset=p['document']['assets'][-1];selections.append({'scene':index+1,'asset_id':asset['id']})
                (out/f'owned-manual-technology-{index+1}.png').write_bytes(data)
            p=send('POST',base+'/draft',{'revision':p['revision'],'scene_media':selections})
            p=send('POST',base+'/auto-plan',{'revision':p['revision']})
            assert p['document']['niche']=='technology' and p['document']['brand_template']['brand']['id']=='vf-ai-education'
            assert p['document']['channel_profile']['profile']['profile_ref']=='ai-education-reference@1'
            send('POST',base+'/approve',{'revision':p['revision'],'reviewer':'EXPLICIT FIXTURE BEFORE MEASUREMENT','acknowledged':True},400)
            p=send('POST',base+'/approve',{'revision':p['revision'],'reviewer':'EXPLICIT SIGNED LOCAL TTS FIXTURE; NOT OWNER UAT','acknowledged':True,'purpose':'narration'})
            job=send('POST',base+'/jobs',{'revision':p['revision'],'kind':'narration','request_key':uuid.uuid4().hex})
            print(json.dumps({'stage':'existing_locked_offline_local_TTS','project_id':p['id'],'job_id':job['id'],'paid_calls':0}),flush=True)
            assert server.runner.run_one();source=server.store.get_job(job['id']);write(out/'narration-job.json',source)
            assert source['status']=='succeeded',source.get('error')
            voice_dir=root/'jobs'/source['id'];voice_sha=file_sha(voice_dir/'voice.wav');voice_metadata=json.loads((voice_dir/'voice.json').read_bytes())
            for name in ['voice.wav','voice.json','tts-plan.json','narration-plan.json']:
                if (voice_dir/name).exists():shutil.copyfile(voice_dir/name,out/name)
            p=send('GET',base);p=send('POST',base+'/narration/'+source['id']+'/apply',{'revision':p['revision'],
                'expected_plan_sha256':source['result']['plan_sha256'],'acknowledged':True})
            send('POST',base+'/approve',{'revision':p['revision'],'reviewer':'EXPLICIT FIXTURE BEFORE AUDIBLE PREVIEW','acknowledged':True},400)
            send('POST',base+'/preview',{'revision':p['revision'],'action':'generate'})
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                preview=send('GET',base+'/preview')
                if preview['status'] not in {'QUEUED','RUNNING'}:break
                time.sleep(.2)
            write(out/'preview.json',preview);assert preview['status']=='READY' and preview['final_approval_eligible'],preview
            shutil.copyfile(server.previews.video_path(p['id'],preview['timeline_version']),out/'preview.mp4')
            p=send('POST',base+'/approve',{'revision':p['revision'],'reviewer':'EXPLICIT SIGNED PRODUCTION FIXTURE; NOT OWNER UAT','acknowledged':True})
            queued=send('POST',base+'/jobs',{'revision':p['revision'],'kind':'render','request_key':uuid.uuid4().hex});assert server.runner.run_one()
            job=server.store.get_job(queued['id']);write(out/'render-job.json',job);assert job['status']=='succeeded',job.get('error')
            directory=root/'jobs'/job['id'];qc=job['result']['qc'];assert qc['passed'] and qc['full_quality']['status']=='passed'
            assert file_sha(directory/'voice.wav')==voice_sha
            reuse=json.loads((directory/'voice-reuse.json').read_bytes());assert reuse['new_inference_calls']==0
            for name in ['final.mp4','timeline.json','subtitles.ass','render-manifest.json','qc-report.json','full-qc-report.json','voice-reuse.json','render-voice.wav','render-voice.json']:
                if (directory/name).exists():shutil.copyfile(directory/name,out/name)
            write(out/'qc.json',qc)
            send('POST','/api/jobs/'+job['id']+'/review',{'revision':job['revision'],'reviewer':'EXPLICIT SIGNED FINAL FIXTURE; NOT OWNER UAT',
                'acknowledged':True,'decision':'approve','note':'Technical fixture only; speech/legal/Owner/provider acceptance remains separate.'})
            final=send('GET',base);write(out/'project.json',final);write(out/'canonical-timeline.json',final['document']['canonical_timeline'])
            write(out/'script.json',proposal);write(out/'storyboard.json',final['document']['edit_plan']);write(out/'asset-provenance.json',final['document']['assets'])
            write(out/'research-evidence.json',{'source_reference':'https://www.w3.org/TR/filter-effects-1/','source_type':'official_documentation',
                'published_at':'2018-12-18','facts':['Filter operations can modify image color.'],'editorial_advice':'Review rendered output before publishing.',
                'basis':'Previously read official W3C source; manually authored paraphrase, not an automated research-provider run or a trend observation.'})
            write(out/'cost.json',CostLedger(server.store).summary(p['id']))
            with server.store.transaction() as con:write(out/'job-events.json',[dict(row) for row in con.execute('SELECT * FROM events WHERE project_id=? ORDER BY id',(p['id'],))])
            write(out/'http-requests.json',requests);write(out/'backup.json',create_backup(config,out/'owned-master-backup.zip'))
            assert before=={name:file_sha(ROOT/'services/windows_native'/name) for name in CORE}
            write(out/'evidence.json',{'schema_version':'native-technology-spoken-master-v1','project_id':p['id'],'render_job_id':job['id'],
                'channel_profile_ref':'ai-education-reference@1','niche':'technology','brand':'vf-ai-education','actual_offline_local_TTS_jobs':1,
                'local_model_inference_calls':voice_metadata['inference_calls'],'voice_duration_seconds':voice_metadata['duration_seconds'],
                'source_voice_sha256':voice_sha,'local_preview_render_full_QC':True,'same_production_core_unchanged':before,'human_HTTP_requests':len(requests),
                'manual_editorial_script_and_owned_graphics':True,'remote_provider_calls':0,'paid_calls':0,'browser_rendered':False,'Owner_UAT':False,
                'genuine_speech_quality_accepted':False,'rights_independently_verified':False,'full_Mode_A_accepted':False,'real_published':False,'production_deployed':False,
                'owned_temporary_data_cleaned_after_export':True,'exports':{f.name:{'sha256':file_sha(f),'bytes':f.stat().st_size} for f in out.iterdir() if f.is_file()}})
            success=True;print(json.dumps({'status':'LOCAL_TECHNOLOGY_SPOKEN_MASTER_PASS','project_id':p['id'],'voice_sha256':voice_sha,'backup_sha256':file_sha(out/'owned-master-backup.zip')}),flush=True)
        finally:
            server.shutdown();server.server_close();thread.join()
            if not success:
                write(out/'failed-http-requests.json',requests)
                write(out/'failure-backup.json',create_backup(config,out/'failed-owned-master-backup.zip'))

if __name__=='__main__':main()
