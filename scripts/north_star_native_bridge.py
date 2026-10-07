"""Owned playable Native-to-fixture bridge acceptance, restart and offline restore.

Synthetic pixels/tone; saved ASR and research/idea/publication/analytics fixtures.
Actual local CPU media/render/QC. No Agent Hub, external API, paid call or Owner UAT.
"""
import argparse,http.client,json,re,shutil,subprocess,sys,threading,time,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.bridge import NativeBridge
from services.windows_native.bridge_transport import FixtureWebhookTransport,BridgeResponse
from services.windows_native.contracts import digest,file_sha
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.intelligence_store import IntelligenceStore
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.tests.test_human_identity import fixture
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native.tests.test_intelligence_engines import receipt
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
from services.windows_native import auto_edit_analysis as analysis
from app.bridge_auth import ServiceIdentity,SigningKeyring,sign_service_request,canonical_json_bytes
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier

WORKSPACE='wsp_native_bridge_fixture'
KEY=b'explicit-fixture-only-native-bridge-key-0001'

def config(root):
    absent=root.parent/(root.name+'-absent-secrets')
    return Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')

def read_state(root):
    store=Store(root);bridge=NativeBridge(store,workspace_id=WORKSPACE);intelligence=IntelligenceStore(root);bridge.attach_intelligence(intelligence)
    page=bridge.page(limit=100);assert page['next_cursor'] is None
    with intelligence.transaction() as con:source=[dict(r) for r in con.execute('SELECT * FROM native_bridge_source_events ORDER BY sequence')]
    return {'projects':[store.get(p['id']) for p in store.list()],
        'versions':{p['id']:store.versions(p['id']) for p in store.list()},'events':page,
        'audit':{r['envelope']['event_id']:bridge.audit(r['envelope']['event_id']) for r in page['items']},'source_events':source}

def run(args):
    root=args.data_root.resolve();restored=args.restore_root.resolve();out=args.output.resolve()
    for path in [root,restored]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-bridge-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned bridge fixture roots required')
    if root==restored:raise ValueError('Distinct roots required')
    root.mkdir();out.mkdir(parents=True,exist_ok=False);settings=config(root);pipeline=Pipeline(settings)
    source=root/'explicit-synthetic-bridge-source.mp4'
    subprocess.run([str(settings.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=3',
        '-f','lavfi','-i','sine=frequency=880:duration=3','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-t','3',str(source)],check=True,timeout=30)
    source_sha=file_sha(source);raw,registry=fixture('owner',workspace=WORKSPACE)
    access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,settings,pipeline=pipeline,start_worker=False,access=access);cookie,session=access.login(raw)
    clock=[time.time()];server.bridge.clock=lambda:clock[0]
    server.bridge.configure_auth({'hub-fixture':ServiceIdentity('hub-fixture',('service',),{'fixture-v1':KEY})})
    signing=SigningKeyring('fixture-v1',{'fixture-v1':KEY});wire=[];accepted=set();receiver_events={};first_retry=[True]
    def receiver(body,headers):
        value=json.loads(body);identity=value['event_id']
        assert headers['Idempotency-Key']==identity and headers['X-NPD-Contract-Version']=='agent-hub-bridge.v1'
        assert signing.verify(body,key_id=headers['X-NPD-Key-Id'],timestamp=int(headers['X-NPD-Timestamp']),event_id=identity,signature=headers['X-NPD-Signature'])
        assert value['payload']['workspace_id']==WORKSPACE
        wire.append({'event_id':identity,'body_sha256':digest(value),'signed_at':headers['X-NPD-Timestamp'],'fixture_receiver':True,'actual_hub_request':False})
        if first_retry[0]:first_retry[0]=False;return BridgeResponse(429,5)
        if identity in receiver_events:assert receiver_events[identity]==value
        receiver_events[identity]=value;accepted.add(identity);return BridgeResponse(204)
    # Explicit in-process fixture enablement. Nothing opens a webhook socket.
    server.bridge.configure_delivery(transport=FixtureWebhookTransport(receiver),signing=signing,enabled=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[]
    def request(method,path,body=None,*,status=200,service=False,binary=None,headers=None):
        encoded=canonical_json_bytes(body) if body is not None else binary
        options={'Content-Type':'application/json',**(headers or {})}
        if service:
            base,_,query=path.partition('?')
            options.update(sign_service_request(key=KEY,service_id='hub-fixture',key_id='fixture-v1',method=method,path=base,query=query,
                body=encoded or b'',timestamp=int(clock[0]),nonce=uuid.uuid4().hex))
        else:options.update({'Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        connection.request(method,path,body=encoded,headers=options);response=connection.getresponse();value=json.loads(response.read());metadata=dict(response.getheaders());connection.close()
        requests.append({'method':method,'path':path,'status':response.status,'signed_service':service})
        assert response.status==status,(response.status,value);assert metadata['Cache-Control']=='no-store';return value
    try:
        contract=request('GET','/v1/contract',service=True);assert contract['webhook_mode']=='fixture' and not contract['shared_database']
        draft={'workspace_id':WORKSPACE,'name':'EXPLICIT SYNTHETIC BRIDGE SOURCE FIXTURE','input_kind':'media','prompt':'',
            'niche':'technology','channel_profile_ref':'ai-education-reference@1'}
        created=request('POST','/v1/projects',draft,status=201,service=True,headers={'Idempotency-Key':'native-playable-bridge-draft-key'})
        repeated=request('POST','/v1/projects',draft,service=True,headers={'Idempotency-Key':'native-playable-bridge-draft-key'})
        assert repeated['idempotent_replay'] and repeated['project_id']==created['project_id'] and not created['execution_started']
        project=server.store.get(created['project_id']);assert project['approval'] is None and not project['jobs']
        project=request('POST',f'/api/projects/{project["id"]}/media',status=201,binary=source.read_bytes(),headers={'Content-Type':'video/mp4',
            'X-VF-Revision':str(project['revision']),'X-VF-Rights':'confirmed','X-VF-Illustration':'false','X-VF-Filename':'explicit-bridge-source.mp4'})
        # The HTTP upload correctly keeps rights unknown. This specific source
        # was actually generated above from testsrc2 + tone. Register explicit
        # fixture provenance in this fresh owned root, never an Owner override
        # for external assets or an acceptance claim for the rights editor UI.
        with server.store.transaction() as con:
            document=project['document'];asset=document['assets'][0]
            asset.update(rights_status='owned',license='locally_generated_synthetic_fixture',source_type='synthetic_fixture',
                provider='local-ffmpeg-fixture',source_reference=source.name,
                generation_provenance={'explicit_fixture':True,'workflow':'FFmpeg lavfi testsrc2 and sine',
                    'synthetic_tone_not_speech':True,'no_external_media_download':True})
            con.execute('UPDATE projects SET revision=revision+1,document=?,approval=NULL WHERE id=?',(json.dumps(document,ensure_ascii=False),project['id']))
            server.store.version(con,project['id']);server.store.event(con,project['id'],'explicit_fixture_owned_source_registered',{'source_sha256':source_sha})
        project=server.store.get(project['id'])
        asset=project['document']['assets'][0];job=server.store.enqueue(project['id'],project['revision'],'asr',uuid.uuid4().hex)
        claimed=server.store.claim();assert claimed['id']==job['id'];server.store.finish(claimed,result={'media_analysis':[saved_asr(asset)]})
        for kind in ['auto_edit_analysis','media_frames']:
            current=server.store.get(project['id']);job=request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':current['revision'],'kind':kind,'request_key':uuid.uuid4().hex})
            assert server.runner.run_one();assert server.store.get_job(job['id'])['status']=='succeeded'
        bundle=analysis.view(server.store,project['id']);measured=bundle['analyses'][0]['analysis']
        project=request('POST',f'/api/projects/{project["id"]}/auto-edit/timeline',{'revision':bundle['revision'],'action':'create','payload':{
            'analysis_id':measured['analysis_id'],'transcript_id':measured['transcript']['transcript_id']}})
        denied=request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':project['revision'],'kind':'render','request_key':uuid.uuid4().hex},status=409)
        assert denied['code']=='AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER'
        request('POST',f'/api/projects/{project["id"]}/preview',{'revision':project['revision'],'action':'generate'});deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            preview=server.previews.status(project['id'])
            if preview['status']=='READY':break
            if preview['status'] in ('FAILED','CANCELLED'):raise AssertionError(preview)
            time.sleep(.25)
        from services.windows_native.source_preview import FULL_PROFILE
        assert preview['status']=='READY';assert preview['preview_profile']==FULL_PROFILE
        project=request('POST',f'/api/projects/{project["id"]}/approve',{'revision':project['revision'],'reviewer':'EXPLICIT BRIDGE FIXTURE — NOT OWNER UAT','acknowledged':True})
        job=request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':project['revision'],'kind':'render','request_key':uuid.uuid4().hex})
        with patch('services.windows_native.pipeline.verify_runtime',side_effect=AssertionError('No locked TTS or provider calls')):assert server.runner.run_one()
        final=server.store.get_job(job['id']);assert final['status']=='succeeded' and final['result']['qc']['passed']
        folder=root/'jobs'/job['id'];qc=json.loads((folder/'qc-report.json').read_bytes());assert qc['passed'] and qc['width']==1080 and qc['height']==1920
        request('POST',f'/api/jobs/{job["id"]}/review',{'revision':project['revision'],'reviewer':'EXPLICIT MOCK FINAL REVIEW — NOT OWNER UAT',
            'acknowledged':True,'decision':'approve','note':'Synthetic CPU media, saved ASR. Fixture review only.'})
        before=server.store.get(project['id']);base=f'/api/projects/{project["id"]}/publications'
        pub=request('POST',base,{'revision':project['revision'],'final_job_id':job['id'],'platform':'youtube','mode':'dry_run',
            'metadata':{'title':'EXPLICIT BRIDGE DRY RUN FIXTURE','privacy':'private'},'request_key':'native-bridge-dry-run-publication-key'})
        route=base+'/'+pub['publication_id']
        request('POST',route+'/approve',{'expected_fingerprint':pub['request_fingerprint'],'expected_artifact_sha256':pub['snapshot']['final_sha256'],'acknowledged':True})
        pub=request('POST',route+'/dry-run',{'expected_fingerprint':pub['request_fingerprint']});assert pub['receipt']['remote_post_id'] is None and not pub['receipt']['external_action']
        base=f'/api/projects/{project["id"]}/analytics'
        sync=request('POST',base,{'publication_id':pub['publication_id'],'provider_mode':'fixture','fixture_acknowledged':True,
            'fixture_profile':'winner_candidate','request_key':'native-bridge-winner-fixture-key'})
        analytics=request('POST',base+'/'+sync['sync_id']+'/process',{'expected_fingerprint':sync['request_fingerprint']})
        assert analytics['snapshot']['mock'] and analytics['snapshot']['assessment']['state']=='winner_candidate'
        assert server.store.get(project['id'])==before and file_sha(source)==source_sha
        intelligence=IntelligenceService(settings,server.store,research_provider=PublicWebResearchProvider(root/'research-sources',fetch=lambda url:receipt()),idea_provider=FixtureIdeas())
        server.bridge.attach_intelligence(intelligence.store)
        research=intelligence.create('Explicit technology fixture research','ai-education',['https://example.com/test'])
        for action in ('research','ideas'):
            intelligence.enqueue(research['run']['id'],research['run']['version'],action,uuid.uuid4().hex)
            assert intelligence.run_one();research=intelligence.bundle(research['run']['id']);assert research['operations'][0]['status']=='SUCCEEDED'
        assert server.bridge.harvest()>0 and server.bridge.harvest()==0
        while server.bridge.process() is not None:pass
        clock[0]+=5
        while server.bridge.process() is not None:pass
        page=request('GET','/v1/events?limit=100',service=True);assert page['next_cursor'] is None
        types={row['envelope']['event_type'] for row in page['items']}
        expected={'trend.opportunity.detected','idea.shortlist.ready','video.project.created','video.analysis.completed','video.preview.ready',
            'video.approval.required','video.approved','video.render.completed','video.publish.completed','video.analytics.updated','video.winner.detected'}
        assert expected<=types,(expected-types);assert all(row['delivery']['status']=='succeeded' for row in page['items'])
        assert len(accepted)==len(page['items']) and len(wire)==len(accepted)+1
        assert 'EXPLICIT SYNTHETIC BRIDGE SOURCE FIXTURE' not in json.dumps(page)
        for row in page['items']:
            audit=request('GET','/v1/events/'+row['envelope']['event_id']+'/delivery',service=True)
            assert audit['fixture'] and not audit['real_hub_receipt_verified'] and all(a['external_call']==0 for a in audit['attempts'])
        for name in ['final.mp4','qc-report.json','ffprobe.json','render-manifest.json','timeline.json','timeline-render.json','subtitles.json','audio-analysis.json','cost.json']:
            shutil.copyfile(folder/name,out/name)
        shutil.copyfile(server.previews.video_path(project['id'],preview['timeline_version']),out/'preview.mp4')
        evidence={'schema_version':'native-bridge-playable-contract-v1','project_id':project['id'],'job_id':job['id'],
            'final_sha256':file_sha(out/'final.mp4'),'preview_sha256':file_sha(out/'preview.mp4'),'event_types':sorted(types),
            'events':len(accepted),'attempts':len(wire),'authenticated_http_requests':len(requests),'local_real_full_qc':True,
            'fixture_service_auth':True,'fixture_signed_delivery':True,'saved_asr_fixture':True,'research_ideas_fixture':True,
            'publication_analytics_fixture':True,'explicit_synthetic_owned_provenance_seed':True,'runtime_rights_editor_tested':False,
            'actual_hub_calls':0,'actual_provider_calls':0,'owner_uat':False,'production_deployed':False}
        for name,value in [('evidence.json',evidence),('events.json',page),('wire-audit.json',wire),('http-requests.json',requests),
            ('research.json',research),('publication.json',pub),('analytics.json',analytics),('project.json',before)]:
            (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'media':'PASS','events':len(accepted),'fixture_signed_attempts':len(wire),'actual_hub_calls':0}),flush=True)
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    before=read_state(root)
    restart=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root)],timeout=60));assert restart==before
    backup=create_backup(settings,out/'native-bridge-backup.zip');receipt_restore=restore_backup(out/'native-bridge-backup.zip',restored,expected_sha256=backup['sha256'])
    after=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(restored)],timeout=60));assert after==before
    assert file_sha(restored/'jobs'/job['id']/'final.mp4')==evidence['final_sha256']
    (out/'recovery.json').write_text(json.dumps({'backup':backup,'restore':receipt_restore,'new_process_exact':True,'offline_restore_exact':True,
        'original_artifacts_unchanged':True,'secrets_in_backup':False,'actual_hub_calls':0},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'new_process':'PASS','offline_restore':'PASS','events':len(before['events']['items'])}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--read-root',type=Path);args=parser.parse_args()
    if args.read_root:print(json.dumps(read_state(args.read_root),ensure_ascii=True))
    else:run(args)
