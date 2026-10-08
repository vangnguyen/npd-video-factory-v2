"""Signed actual narrated overlap mix/recovery on a copied owned media bundle.

Previously generated genuine voice PCM is reused. Music is an explicit local
tone fixture with unknown rights; signed approvals are fixtures, not Owner UAT.
"""
import argparse,http.client,json,re,subprocess,sys,threading,time,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,access,write
from scripts.north_star_native_narrated_variants import copy
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.server import LocalServer
from services.windows_native.narrated_music import verify_bundle

def owned(root):
    if root.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-narrated-music-[a-z0-9-]+',root.name):raise ValueError('Owned narrated music root required')

def run(args):
    root,out,restored=args.data_root.resolve(),args.output.resolve(),args.restore_root.resolve()
    for path in (root,restored):
        owned(path)
        if path.exists():raise ValueError('Fresh owned roots required')
    if out.exists() or out==ROOT or ROOT in out.parents or out in (root,restored) or root in out.parents or restored in out.parents:raise ValueError('Fresh separate evidence required')
    if not re.fullmatch(r'[a-f0-9]{32}',args.project_id):raise ValueError('Exact copied master required')
    out.mkdir(parents=True);write(out/'initial-restore.json',restore_backup(args.backup,root,expected_sha256=args.expected_sha256))
    auth,cookie,session=access();server=LocalServer(0,settings(root),start_worker=False,access=auth)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[]
    def send(method,path,body=None,expected=200,raw=False,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=60)
        conn.request(method,path,body=body if raw else json.dumps(body) if body is not None else None,
            headers={'Content-Type':'audio/wav' if raw else 'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf,**(headers or {})})
        response=conn.getresponse();meta=dict(response.getheaders());data=response.read();conn.close()
        value=json.loads(data) if meta.get('Content-Type','').startswith('application/json') else data
        requests.append({'method':method,'path':path,'status':response.status});assert response.status==expected,(response.status,value);return value
    try:
        base='/api/projects/'+args.project_id;copied=send('GET',base);write(out/'copied-master.json',copied)
        physical={p.relative_to(root).as_posix():file_sha(p) for d in ('assets','originals','jobs','shot-previews') for p in (root/d).rglob('*') if p.is_file()}
        source=out/'explicit-tone-music.wav'
        subprocess.run([str(server.config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-n','-f','lavfi','-i','sine=frequency=220:duration=3',
            '-ar','48000','-ac','2','-c:a','pcm_s16le',str(source)],check=True,capture_output=True,timeout=20)
        master=send('POST',base+'/music',source.read_bytes(),expected=201,raw=True,headers={'X-VF-Revision':str(copied['revision']),'X-VF-Rights':'confirmed','X-VF-Music-Loop-Crossfade':'0.31'})
        assert master['approval'] is None and master['document']['music']['rights_status']=='unknown'
        doc=master['document'];ref=doc['prepared_narration'];track=doc['canonical_timeline']['snapshot']['tracks'][-1]
        assert track['track_id']=='trk_native_music' and len(track['clips'])>1 and doc['music']['narrated_loop']['crossfade_frames']==14880
        write(out/'master-music.json',doc['music']);write(out/'original-master.json',master)
        profiles=send('GET','/api/narrated/variant-profiles');write(out/'catalog.json',profiles)
        body={'schema_version':'native-narrated-variant-request-v1','revision':master['revision'],'expected_version':doc['canonical_timeline']['version'],
            'expected_prepared_reference_sha256':digest(ref),'profile_refs':[p['profile_ref'] for p in profiles['profiles']],'request_key':'owned-six-narrated-music-overlap-family'}
        batch=send('POST',base+'/narrated-variants',body);write(out/'created-family.json',batch)
        assert send('POST',base+'/narrated-variants',body)['idempotent_replay'];receipts=[];bed_hashes=set()
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new inference permitted')):
            for descriptor in batch['result']['variants']:
                identifier=descriptor['project_id'];child_base='/api/projects/'+identifier;directory=out/descriptor['profile']['profile_ref'].replace('@','-');directory.mkdir()
                child=send('GET',child_base);assert child['approval'] is None and not child['jobs'];write(directory/'initial-project.json',child)
                assert child['document']['canonical_timeline']['snapshot']['tracks'][-1]==track
                send('POST',child_base+'/preview',{'revision':child['revision'],'action':'generate'});deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    preview=send('GET',child_base+'/preview')
                    if preview['status'] not in {'QUEUED','RUNNING'}:break
                    time.sleep(.5)
                assert preview['status']=='READY' and preview['final_approval_eligible'],preview;write(directory/'preview.json',preview)
                copy(server.previews.video_path(identifier,preview['timeline_version']),directory/'preview.mp4')
                approved=send('POST',child_base+'/approve',{'revision':child['revision'],'reviewer':'EXPLICIT SIGNED MUSIC FIXTURE; NOT OWNER UAT','acknowledged':True});write(directory/'render-approval-fixture.json',approved['approval'])
                queued=send('POST',child_base+'/jobs',{'revision':child['revision'],'kind':'render','request_key':uuid.uuid4().hex});assert server.runner.run_one()
                job=server.store.get_job(queued['id']);assert job['status']=='succeeded',job;write(directory/'job.json',job)
                folder=root/'jobs'/job['id'];qc=job['result']['qc'];assert qc['passed'] and qc['full_quality']['status']=='passed'
                loop=verify_bundle(server.config,child['document'],folder);bed_hashes.add(loop['output_sha256'])
                assert file_sha(folder/'voice.wav')==ref['voice_audio_sha256'] and loop['pre_pcm_clipped_samples']==0
                preview_folder=root/'shot-previews'/preview['id'];assert file_sha(preview_folder/'music-loop.wav')==loop['output_sha256']
                assert not loop['speech_quality_accepted'] and not loop['rights_independently_verified']
                for name in ['final.mp4','timeline.json','subtitles.ass','voice-reuse.json','render-manifest.json','qc-report.json','full-qc-report.json','transport-qc-report.json','voice.wav','voice.json','tts-plan.json','music-loop.json','music-loop.wav','ffprobe.json']:
                    if (folder/name).is_file():copy(folder/name,directory/name)
                (directory/'subtitle-qc').mkdir()
                for mask in (folder/'subtitle-qc').glob('*.png'):copy(mask,directory/'subtitle-qc'/mask.name)
                write(directory/'canonical-timeline.json',child['document']['canonical_timeline']);write(directory/'qc.json',qc)
                from services.windows_native.costs import CostLedger
                from services.windows_native.media import project_assets
                write(directory/'cost.json',CostLedger(server.store).summary(identifier));write(directory/'asset-provenance.json',project_assets(child['document']))
                with server.store.transaction() as con:write(directory/'job-events.json',[dict(row) for row in con.execute('SELECT * FROM events WHERE project_id=? ORDER BY id',(identifier,))])
                send('POST','/api/jobs/'+job['id']+'/review',{'revision':job['revision'],'reviewer':'EXPLICIT SIGNED FINAL MUSIC FIXTURE; NOT OWNER UAT','acknowledged':True,
                    'decision':'approve','note':'Audio transport and measured PCM fixture only; speech, balance, legal and Owner acceptance remain pending.'})
                cue=json.loads((folder/'render-manifest.json').read_bytes())['captions'][0]
                subprocess.run([str(server.config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-n','-ss',str((cue['start']+cue['end'])/2),'-i',str(folder/'final.mp4'),'-frames:v','1',str(directory/'review-frame.png')],check=True,capture_output=True,timeout=30)
                receipts.append({'project_id':identifier,'render_job_id':job['id'],'profile':descriptor['profile'],'source_voice_sha256':ref['voice_audio_sha256'],
                    'final_sha256':qc['final_sha256'],'preview_sha256':preview['sha256'],'duration_seconds':qc['duration_seconds'],'full_qc':'passed',
                    'music_loop':loop,'identical_preview_final_music_pcm':True,'new_inference_calls':0,'owner_uat_accepted':False})
        assert len(receipts)==6 and len(bed_hashes)==1 and send('GET',base)==master and physical=={name:file_sha(root/name) for name in physical}
        write(out/'physical-source-hashes.json',physical);write(out/'receipts.json',receipts);write(out/'expected-family-page.json',send('GET',base+'/narrated-variants?limit=100'));write(out/'http-requests.json',requests)
    finally:server.shutdown();server.server_close();thread.join()
    write(out/'backup.json',create_backup(settings(root),out/'owned-narrated-music.zip'));archive=out/'owned-narrated-music.zip'
    write(out/'recovery-restore.json',restore_backup(archive,restored,expected_sha256=file_sha(archive)));args.data_root=restored;reopen(args)
    names=['services/windows_native/narrated_music.py','services/windows_native/narrated_variants.py','services/windows_native/shot_adapter.py','services/windows_native/store.py',
        'services/windows_native/pipeline.py','services/windows_native/narration_preview.py','services/windows_native/storyboard_qc.py','services/windows_native/server.py',
        'services/windows_native/tests/test_narrated_music.py','services/windows_native/tests/test_narrated_music_http.py','services/windows_native/tests/test_phase10_http.py',
        'apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/tests/native-music-loop.test.mjs','scripts/north_star_native_narrated_music.py']
    write(out/'evidence.json',{'schema_version':'native-narrated-music-rehearsal-v1','signed_http_requests':len(requests),'child_projects':6,'audible_previews':6,'final_renders':6,'actual_canvases':4,
        'all_full_qc_passed':True,'identical_preview_final_music_pcm':True,'one_music_bed_for_six_formats':True,'previously_generated_genuine_local_voice_pcm_reused':True,
        'original_media_unchanged':True,'music_is_explicit_synthetic_fixture':True,'approval_decisions_explicit_signed_fixtures':True,
        'new_inference_calls':0,'external_provider_calls':0,'paid_operations':0,'speech_quality_accepted':False,'voice_music_balance_accepted':False,
        'rights_independently_verified':False,'owner_uat_accepted':False,'publishing_enabled':False,'production_deployed':False,
        'source_sha256':{name:file_sha(ROOT/name) for name in names},'exports':{p.relative_to(out).as_posix():{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.rglob('*') if p.is_file()}})
    print(json.dumps({'status':'NARRATED_MUSIC_SIX_FORMAT_RECOVERY_PASS','previews':6,'renders':6,'music_beds':1,'new_inference_calls':0}))

def reopen(args):
    root,out=args.data_root.resolve(),args.output.resolve();owned(root);auth,_,_=access();server=LocalServer(0,settings(root),start_worker=False,access=auth)
    try:
        assert server.narrated_variants.page(args.project_id,limit=100)==json.loads((out/'expected-family-page.json').read_bytes())
        assert server.store.get(args.project_id)==json.loads((out/'original-master.json').read_bytes())
        physical=json.loads((out/'physical-source-hashes.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
        from services.windows_native.narration import load_reference
        for item in json.loads((out/'receipts.json').read_bytes()):
            child=server.store.get(item['project_id']);job=server.store.get_job(item['render_job_id'])
            assert verify_bundle(server.config,child['document'],root/'jobs'/job['id'])==item['music_loop']
            with server.store.transaction() as con:_,_,result=load_reference(server.store,con,child['id'],child['document'])
            assert result['plan']['voice_audio_sha256']==item['source_voice_sha256']
            assert server.store.final_video(job['id'])['final_review']['artifact_sha256']==item['final_sha256']
        assert not server.runner.run_one()
        write(out/('new-process-replay.json' if args.reopen else 'restored-in-process.json'),{'exact_family_master_and_media':True,'verified_music_beds':6,'verified_source_pcm_children':6,
            'verified_final_fixture_reviews':6,'new_jobs':0,'new_inference_calls':0,'publishing_enabled':False})
    finally:server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id',required=True)
    p.add_argument('--backup',type=Path);p.add_argument('--expected-sha256');p.add_argument('--restore-root',type=Path);p.add_argument('--reopen',action='store_true');args=p.parse_args();reopen(args) if args.reopen else run(args)
