"""Signed six-format family/recovery on a copied genuine local narration bundle.

No new inference, paid operation, real publishing, legal or Owner UAT acceptance.
The six preview/render approvals are explicitly signed test-fixture decisions.
"""
import argparse,http.client,json,re,subprocess,sys,threading,time,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_analytics_refresh import settings,access,write
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.server import LocalServer

def copy(source,target):
    with source.open('rb') as incoming,target.open('xb') as output:
        while chunk:=incoming.read(1024**2):output.write(chunk)

def run(args):
    root,out,restored=args.data_root.resolve(),args.output.resolve(),args.restore_root.resolve()
    for path in [root,restored]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-narrated-variants-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned family roots required')
    if out.exists() or ROOT==out or ROOT in out.parents or out in (root,restored) or root in out.parents or restored in out.parents:raise ValueError('Fresh separate evidence required')
    if not re.fullmatch(r'[a-f0-9]{32}',args.project_id):raise ValueError('Exact copied master required')
    out.mkdir(parents=True);write(out/'initial-restore.json',restore_backup(args.backup,root,expected_sha256=args.expected_sha256))
    auth,cookie,session=access();server=LocalServer(0,settings(root),start_worker=False,access=auth)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[]
    def send(method,path,body=None,expected=200,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=60)
        conn.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf,**(headers or {})})
        response=conn.getresponse();meta=dict(response.getheaders());raw=response.read();conn.close()
        value=json.loads(raw) if meta.get('Content-Type','').startswith('application/json') else raw
        requests.append({'method':method,'path':path,'status':response.status});assert response.status==expected,(response.status,value);return value
    try:
        base='/api/projects/'+args.project_id;copied=send('GET',base)
        # Earlier recovery bundles deliberately retain a frozen-video QC failure
        # draft. Restore only previously verified visual selections through edits.
        from services.windows_native.shot_adapter import shots
        from services.windows_native.narration import identity
        accepted=next(j for j in copied['jobs'] if j['kind']=='render' and j['status']=='succeeded' and (j.get('final_review') or {}).get('decision')=='approve')
        from services.windows_native.hardening import Artifacts
        historical=server.store.get_job(accepted['id']);historical_out=root/'jobs'/accepted['id'];checkpoint=Artifacts(historical_out,historical).load('render')
        assert checkpoint and checkpoint['result']==historical['result'] and historical['result']['qc']['passed']
        assert file_sha(historical_out/'final.mp4')==historical['result']['qc']['final_sha256']==historical['final_review']['artifact_sha256']
        assert digest(historical['snapshot'])==historical['final_review']['snapshot_sha256']
        passed=historical['snapshot']['document'];assert identity(copied['document'])==identity(passed)
        current=copied
        for source,target in zip(shots(copied['document']),shots(passed)):
            assert source['shot_id']==target['shot_id']
            if source['asset_id']!=target['asset_id']:
                current=send('POST',base+'/shots',{'revision':current['revision'],'operation':{'type':'update','shot_id':source['shot_id'],'values':{'asset_id':target['asset_id']}}})
        write(out/'copied-master-visual-restoration.json',{'schema_version':'native-owned-master-visual-restoration-v1','explicit_fixture':True,
            'copied_revision':copied['revision'],'restored_revision':current['revision'],'verified_render_job_id':accepted['id'],
            'copied_document_sha256':digest(copied['document']),'restored_document_sha256':digest(current['document']),
            'same_narration_identity':True,'source_pcm_mutated':False,'owner_uat_accepted':False})
        original=send('GET',base);doc=original['document'];ref=doc['prepared_narration']
        physical={p.relative_to(root).as_posix():file_sha(p) for d in ('assets','originals','jobs','shot-previews') for p in (root/d).rglob('*') if p.is_file()}
        profiles=send('GET','/api/narrated/variant-profiles');write(out/'catalog.json',profiles)
        body={'schema_version':'native-narrated-variant-request-v1','revision':original['revision'],'expected_version':doc['canonical_timeline']['version'],
            'expected_prepared_reference_sha256':digest(ref),'profile_refs':[p['profile_ref'] for p in profiles['profiles']],'request_key':'native-owned-six-narrated-variants-fixture'}
        batch=send('POST',base+'/narrated-variants',body);write(out/'created-family.json',batch);assert len(batch['result']['variants'])==6
        replay=send('POST',base+'/narrated-variants',body);assert replay['idempotent_replay'] and {k:v for k,v in replay.items() if k!='idempotent_replay'}=={k:v for k,v in batch.items() if k!='idempotent_replay'}
        receipts=[]
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new inference is permitted')):
            for descriptor in batch['result']['variants']:
                identifier=descriptor['project_id'];child_base='/api/projects/'+identifier;directory=out/descriptor['profile']['profile_ref'].replace('@','-');directory.mkdir()
                child=send('GET',child_base);write(directory/'initial-project.json',child);assert child['approval'] is None and child['jobs']==[]
                review=send('GET',child_base+'/narration');write(directory/'narration-review.json',review)
                audio=send('GET',review['derived_narration']['voice_url']);assert audio==(root/'jobs'/ref['job_id']/'voice.wav').read_bytes()
                send('GET',review['derived_narration']['voice_url'],expected=401,headers={'Cookie':''})
                send('POST',child_base+'/approve',{'revision':child['revision'],'reviewer':'EXPLICIT SIGNED CHILD FIXTURE','acknowledged':True},expected=400)
                send('POST',child_base+'/preview',{'revision':child['revision'],'action':'generate'})
                deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    preview=send('GET',child_base+'/preview')
                    if preview['status'] not in {'QUEUED','RUNNING'}:break
                    time.sleep(.2)
                assert preview['status']=='READY' and preview['final_approval_eligible'],preview;write(directory/'preview.json',preview)
                copy(server.previews.video_path(identifier,preview['timeline_version']),directory/'preview.mp4')
                approved=send('POST',child_base+'/approve',{'revision':child['revision'],'reviewer':'EXPLICIT SIGNED CHILD FIXTURE; NOT OWNER UAT','acknowledged':True});write(directory/'render-approval-fixture.json',approved['approval'])
                queued=send('POST',child_base+'/jobs',{'revision':child['revision'],'kind':'render','request_key':uuid.uuid4().hex});assert server.runner.run_one()
                job=server.store.get_job(queued['id']);assert job['status']=='succeeded',job;write(directory/'job.json',job)
                source=root/'jobs'/job['id'];manifest=json.loads((source/'render-manifest.json').read_bytes());qc=job['result']['qc']
                assert qc['passed'] and qc['full_quality']['status']=='passed'
                assert manifest['render_profile']['width']==descriptor['profile']['width'] and manifest['render_profile']['height']==descriptor['profile']['height']
                assert file_sha(source/'voice.wav')==ref['voice_audio_sha256']
                reuse=json.loads((source/'voice-reuse.json').read_bytes());assert reuse['new_inference_calls']==0 and reuse['source_project_id']==args.project_id and not reuse['approval_inherited'] and not reuse['rights_authority_inherited']
                for name in ['final.mp4','timeline.json','subtitles.ass','voice-reuse.json','render-manifest.json','qc-report.json','full-qc-report.json','transport-qc-report.json','voice.wav','voice.json','tts-plan.json']:
                    if (source/name).is_file():copy(source/name,directory/name)
                if (source/'subtitle-qc').is_dir():
                    (directory/'subtitle-qc').mkdir()
                    for mask in (source/'subtitle-qc').glob('*.png'):copy(mask,directory/'subtitle-qc'/mask.name)
                write(directory/'qc.json',qc)
                from services.windows_native.costs import CostLedger
                write(directory/'cost.json',CostLedger(server.store).summary(identifier))
                with server.store.transaction() as con:write(directory/'job-events.json',[dict(row) for row in con.execute('SELECT * FROM events WHERE project_id=? ORDER BY id',(identifier,))])
                from services.windows_native.media import project_assets
                write(directory/'canonical-timeline.json',job['snapshot']['document']['canonical_timeline']);write(directory/'asset-provenance.json',project_assets(job['snapshot']['document']))
                write(directory/'rights-review.json',send('GET',child_base+'/narration-rights'));assert not send('GET',child_base+'/narration-rights')['active_exception']
                send('POST','/api/jobs/'+job['id']+'/review',{'revision':job['revision'],'reviewer':'EXPLICIT SIGNED FINAL FIXTURE; NOT OWNER UAT','acknowledged':True,'decision':'approve','note':'Fixture approval only. Speech, legal, real publication and Owner acceptance remain pending.'})
                cue=manifest['captions'][0];stamp=(cue['start']+cue['end'])/2
                subprocess.run([str(server.config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-n','-ss',str(stamp),'-i',str(source/'final.mp4'),'-frames:v','1',str(directory/'review-frame.png')],check=True,capture_output=True,timeout=30)
                receipts.append({'project_id':identifier,'profile':descriptor['profile'],'source_voice_sha256':ref['voice_audio_sha256'],'final_sha256':qc['final_sha256'],
                    'duration_seconds':qc['duration_seconds'],'full_qc':'passed','preview_sha256':preview['sha256'],'new_inference_calls':0,'independent_fixture_approval':True,'owner_uat_accepted':False})
        assert send('GET',base)==original and physical=={name:file_sha(root/name) for name in physical}
        write(out/'original-master.json',original);write(out/'physical-source-hashes.json',physical);write(out/'receipts.json',receipts)
        write(out/'expected-family-page.json',send('GET',base+'/narrated-variants?limit=100'));write(out/'http-requests.json',requests)
    finally:server.shutdown();server.server_close();thread.join()
    write(out/'backup.json',create_backup(settings(root),out/'owned-narrated-variants.zip'))
    archive=out/'owned-narrated-variants.zip';write(out/'recovery-restore.json',restore_backup(archive,restored,expected_sha256=file_sha(archive)))
    args.data_root=restored;reopen(args)
    names=['services/windows_native/narrated_variants.py','services/windows_native/narrated_variants_models.py','services/windows_native/narrated_variant_routes.py',
        'services/windows_native/narration.py','services/windows_native/narration_preview.py','services/windows_native/narration_rights.py','services/windows_native/server.py',
        'services/windows_native/access.py','services/windows_native/backup.py','services/windows_native/tests/test_narrated_variants.py','services/windows_native/tests/test_narrated_variants_http.py',
        'apps/studio-web/native-narrated-variants.mjs','apps/studio-web/native-narration.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/tests/native-narrated-variants.test.mjs','scripts/north_star_native_narrated_variants.py']
    write(out/'evidence.json',{'schema_version':'native-narrated-variants-rehearsal-v1','genuine_previously_generated_local_pcm_reused':True,'approval_decisions_explicit_signed_fixtures':True,
        'human_http_requests':len(requests),'child_projects':6,'audible_previews':6,'final_renders':6,'actual_canvases':4,'all_full_qc_passed':True,'original_master_and_media_unchanged':True,
        'new_inference_calls':0,'paid_operations':0,'external_provider_calls':0,'publishing_enabled':False,'speech_quality_accepted':False,'rights_independently_verified':False,'owner_uat_accepted':False,'production_deployed':False,
        'source_sha256':{name:file_sha(ROOT/name) for name in names},'exports':{p.relative_to(out).as_posix():{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.rglob('*') if p.is_file()}})
    print(json.dumps({'status':'NARRATED_SIX_FORMAT_FAMILY_RECOVERY_PASS','children':6,'previews':6,'renders':6,'new_inference_calls':0}))

def reopen(args):
    root,out=args.data_root.resolve(),args.output.resolve()
    if root.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-narrated-variants-[a-z0-9-]+',root.name):raise ValueError('Owned family recovery root required')
    auth,_,_=access();server=LocalServer(0,settings(root),start_worker=False,access=auth)
    try:
        assert server.narrated_variants.page(args.project_id,limit=100)==json.loads((out/'expected-family-page.json').read_text(encoding='utf-8'))
        assert server.store.get(args.project_id)==json.loads((out/'original-master.json').read_text(encoding='utf-8'))
        physical=json.loads((out/'physical-source-hashes.json').read_text(encoding='utf-8'));assert physical=={name:file_sha(root/name) for name in physical}
        from services.windows_native.narration import load_reference
        for item in json.loads((out/'receipts.json').read_text(encoding='utf-8')):
            child=server.store.get(item['project_id'])
            with server.store.transaction() as con:source,_,result=load_reference(server.store,con,child['id'],child['document'])
            assert result['plan']['voice_audio_sha256']==item['source_voice_sha256'];assert server.store.final_video(child['jobs'][0]['id'])['final_review']['artifact_sha256']==item['final_sha256']
        assert not server.runner.run_one()
        write(out/('new-process-replay.json' if args.reopen else 'restored-in-process.json'),{'exact_family_master_and_media':True,'verified_source_pcm_children':6,'verified_final_fixture_reviews':6,'new_inference_calls':0,'new_jobs':0,'publishing_enabled':False})
    finally:server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id',required=True)
    p.add_argument('--backup',type=Path);p.add_argument('--expected-sha256');p.add_argument('--restore-root',type=Path);p.add_argument('--reopen',action='store_true');args=p.parse_args();reopen(args) if args.reopen else run(args)
