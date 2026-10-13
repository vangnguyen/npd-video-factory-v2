"""Local component rehearsal over a checksum-anchored browser state backup.

Speech may be a licensed benchmark; visual, identity and approvals are CI
fixtures. This does not certify Owner UAT, genuine user footage or Mode B.
"""
import argparse,copy,json,shutil,subprocess,sys,tempfile,time,uuid
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO),str(REPO/'apps/api')]
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native.server import Runner
from services.windows_native.contracts import digest,file_sha
from services.windows_native.shot_preview import PreviewManager
from services.windows_native import source_settings,transcript_word_routes,transcript_word_review

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def request(item,timeline):
    segment=item['current']['segments'][0]
    return {'expected_version':item['current']['version'],'expected_transcript_id':item['current']['transcript_id'],
        'expected_timeline_version':timeline,'acknowledged':True,'note':'Explicit CI word interval review, not Owner UAT',
        'segments':[{'segment_id':segment['segment_id'],'start_seconds':segment['start_seconds'],
            'end_seconds':segment['end_seconds'],'words':[{k:w[k] for k in ('word_id','text','start_seconds','end_seconds')}
                for w in segment['words']]}]}

def audio_case(config,store,source,out):
    from services.windows_native.multipart_ingestion import NativeMultipartIngestion
    project=store.create('Licensed speech audio; actual local ASR, CI word review','','media')
    service=NativeMultipartIngestion(store,config,workspace_id='wsp_word_audio_fixture');raw=source.read_bytes()
    row=service.create(project['id'],{'revision':project['revision'],'kind':'audio','content_type':'audio/wav',
        'filename':'licensed-speech.bin','total_bytes':len(raw),'rights_confirmed':True,'request_key':'word-audio-'+uuid.uuid4().hex},
        actor='explicit-ci-editor')[0]
    row=service.chunk(project['id'],row['upload_id'],0,__import__('hashlib').sha256(raw).hexdigest(),raw)[0]
    result=service.complete(project['id'],row['upload_id'],{'revision':project['revision'],
        'expected_parts_sha256':row['parts_sha256']})[0]
    project=store.get(project['id']);job=store.enqueue(project['id'],project['revision'],'asr',uuid.uuid4().hex,
        asr_request={'language':'vi','provider':'local-whisper','model_key':'small'})
    Runner(store,Pipeline(config)).run_one();finished=store.get_job(job['id'])
    write(out/'audio-asr-job.json',finished);assert finished['status']=='succeeded',finished.get('error')
    before=copy.deepcopy(store.get(project['id'])['document']['media_analysis'])
    value=transcript_word_routes.view(store,project['id'],'wsp_word_audio_fixture');item=value['items'][0]
    body=request(item,value['timeline_version']);body['segments'][0]['words'][0]['text']+=' [CI]'
    transcript_word_review.save(store,project['id'],value['revision'],item['identity'],body,actor_ref='explicit-ci-editor',
        asset_sha256=item['asset_sha256'],analysis_sha256=item['analysis_sha256'],audio=True,workspace_id='wsp_word_audio_fixture')
    saved=transcript_word_routes.view(store,project['id'],'wsp_word_audio_fixture')
    assert saved['items'][0]['current']['version']==2
    assert store.get(project['id'])['document']['media_analysis']==before
    assert store.get(project['id'])['approval'] is None
    write(out/'audio-word-review.json',saved)
    return project['id']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--backup',required=True);parser.add_argument('--backup-sha',required=True)
    parser.add_argument('--project-id',required=True);parser.add_argument('--expected-project',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--audio-wav');parser.add_argument('--local-asr-manifest')
    parser.add_argument('--rereview-preserved-intervals',action='store_true',help='Explicit CI revision to remap the preserved browser word intervals')
    parser.add_argument('--source-end',type=float,help='Explicit non-destructive CI source trim; spoken words remain protected')
    args=parser.parse_args();out=Path(args.output).resolve();assert not out.exists();out.mkdir()
    expected=json.loads(Path(args.expected_project).read_bytes());assert expected['id']==args.project_id
    with tempfile.TemporaryDirectory(prefix='vf-transcript-word-media-') as temporary:
        root=Path(temporary)/'state';restore=restore_backup(args.backup,root,expected_sha256=args.backup_sha)
        write(out/'initial-restore.json',restore);store=Store(root);project=store.get(args.project_id)
        assert project==expected,'Browser project must survive exact backup restore'
        config=Config(data_root=root,**({'local_asr_manifest':Path(args.local_asr_manifest)} if args.local_asr_manifest else {}))
        original=copy.deepcopy(project['document']['media_analysis']);original_analysis=copy.deepcopy(project['document']['auto_edit_analyses'])
        sources={str(p.relative_to(root)):file_sha(p) for folder in ('assets','originals') for p in (root/folder).rglob('*') if p.is_file()}
        review=transcript_word_routes.view(store,project['id'],'wsp_word_browser_fixture');current=review['items'][0]['current']
        assert current['version']==2 and current['provenance']['timing_independently_measured'] is False
        assert current['segments'][0]['words'][0]['end_seconds']==1.8
        assert current['segments'][0]['words'][19]['text']=='lông,'
        browser_transcript_id=current['transcript_id']
        if args.rereview_preserved_intervals:
            item=review['items'][0]
            transcript_word_review.save(store,project['id'],review['revision'],item['identity'],request(item,review['timeline_version']),
                actor_ref='explicit-ci-boundary-review',asset_sha256=item['asset_sha256'],analysis_sha256=item['analysis_sha256'])
            project=store.get(project['id']);review=transcript_word_routes.view(store,project['id'],'wsp_word_browser_fixture')
            current=review['items'][0]['current'];assert current['version']==3
        write(out/'transcript.json',current);write(out/'original-transcript.json',original_analysis[0]['analysis']['transcript'])
        write(out/'asr-evidence.json',original);write(out/'scene-analysis.json',original_analysis)
        write(out/'asset-provenance.json',project['document']['assets'])
        if args.source_end is not None:
            from services.windows_native.source_linked_edit import edit
            state=project['document']['canonical_timeline'];track=next(t for t in state['snapshot']['tracks'] if t['kind']=='source')
            assert len(track['clips'])==1,'This rehearsal trim is for one explicit source clip'
            clip=track['clips'][0]
            write(out/'explicit-source-cut.json',{'source_duration':clip['source_end'],'retained_source_end':args.source_end,
                'reason':'Explicit CI review after measured trailing-silence QC failure; no spoken words cut',
                'actor_is_fixture':True,'destructive':False,'Owner_UAT':False})
            project=edit(store,project['id'],project['revision'],{'expected_version':state['version'],
                'operation':{'type':'trim','clip_id':clip['clip_id'],'source_end':args.source_end}})
            review=transcript_word_routes.view(store,project['id'],'wsp_word_browser_fixture')
        project=source_settings.configure(store,project['id'],project['revision'],{
            'expected_version':review['timeline_version'],'preview_mode':'final_effects','subtitle_template_ref':'karaoke-gold@v1'})
        manager=PreviewManager(config,store)
        try:
            manager.generate(project['id'],project['revision']);deadline=time.monotonic()+300
            while True:
                preview=manager.status(project['id'])
                if preview['status'] not in {'QUEUED','RUNNING'}:break
                if time.monotonic()>deadline:raise RuntimeError('Owned preview process observation deadline exceeded')
                time.sleep(.2)
            write(out/'preview-receipt.json',preview);assert preview['status']=='READY',preview.get('error')
            assert preview['manifest']['captions_included'] is True
            shutil.copyfile(manager.video_path(project['id'],preview['timeline_version']),out/'preview.mp4')
        finally:manager.close()
        project=store.approve(project['id'],project['revision'],'EXPLICIT CI REVIEW FIXTURE — NOT OWNER UAT',True)
        job=store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex)
        Runner(store,Pipeline(config)).run_one();finished=store.get_job(job['id'])
        write(out/'render-job.json',finished)
        folder=root/'jobs'/job['id']
        if finished['status']!='succeeded':
            reports=out/'failed-render';reports.mkdir()
            for path in folder.rglob('*'):
                if path.is_file() and (path.suffix=='.json' or path.suffix=='.log'):
                    target=reports/path.relative_to(folder);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
            write(out/'failed-render-evidence.json',{'status':finished['status'],'error':finished.get('error'),
                'Owner_UAT':False,'accepted':False,'QC_bypassed':False})
            raise AssertionError(finished.get('error'))
        assert finished['result']['qc']['passed'] is True
        assert finished['result']['qc']['human_final_video_accepted'] is False
        for name in ('final.mp4','timeline.json','subtitles.json','subtitles.ass','render-manifest.json','audio-analysis.json',
            'audio-balance.json','source-audio-clocks.json','cost.json'):
            if (folder/name).is_file():shutil.copyfile(folder/name,out/name)
        subtitles=json.loads((folder/'subtitles.json').read_bytes())
        assert subtitles['transcript_evidence']==current
        assert subtitles['word_alignment']=='human_supplied_source_intervals_not_independently_measured'
        assert any('lông,' in cue['text'] for cue in subtitles['cues'])
        assert any(w['end_seconds']==1.8 for cue in subtitles['cues'] for w in cue.get('words',[]))
        write(out/'qc.json',finished['result']['qc'])
        after=store.get(project['id'])
        with store.transaction() as con:
            events=[{**dict(row),'payload':json.loads(row['payload'])} for row in con.execute(
                'SELECT id,action,payload,created_at FROM events WHERE project_id=? ORDER BY id',(project['id'],)).fetchall()]
        write(out/'job-events.json',events)
        assert after['document']['media_analysis']==original and after['document']['auto_edit_analyses']==original_analysis
        assert all(file_sha(root/name)==sha for name,sha in sources.items())
        audio_id=None
        if args.audio_wav:
            assert args.local_asr_manifest
            audio_id=audio_case(config,store,Path(args.audio_wav),out)
        backup=create_backup(config,out/'word-reviewed-media-state.zip');write(out/'backup.json',backup)
        expected_hashes={pid:digest(store.get(pid)) for pid in (project['id'],audio_id) if pid}
        write(out/'expected-projects.json',expected_hashes)
        child_code='''import json,sys,tempfile
from pathlib import Path
from services.windows_native.backup import restore_backup
from services.windows_native.store import Store
from services.windows_native.contracts import digest
with tempfile.TemporaryDirectory(prefix="vf-word-cold-") as temporary:
 root=Path(temporary)/"restore";restore_backup(sys.argv[1],root,expected_sha256=sys.argv[2]);store=Store(root)
 expected=json.loads(Path(sys.argv[3]).read_bytes());assert {pid:digest(store.get(pid)) for pid in expected}==expected
 print(json.dumps({"projects":len(expected),"exact_fresh_process_restore":True,"provider_calls":0}))
'''
        child=subprocess.run([sys.executable,'-X','utf8','-c',child_code,backup['backup_path'],backup['sha256'],str(out/'expected-projects.json')],
            capture_output=True,text=True,timeout=60)
        if child.returncode:raise RuntimeError(child.stderr[-2000:])
        cold=json.loads(child.stdout.strip().splitlines()[-1]);write(out/'fresh-process-restore.json',cold)
    report={'schema_version':'north-star-native-transcript-word-media.v1','project_id':args.project_id,'render_job_id':job['id'],
        'browser_state_exact_restore':True,'source_and_original_transcripts_unchanged':True,'versioned_manual_words_used_in_subtitles':True,
        'full_effects_preview_actual':True,'final_render_actual':True,'measured_QC_passed':True,'fresh_process_restore':cold,
        'actual_additional_local_ASR_calls':int(audio_id is not None),'external_calls':0,'paid_calls':0,'human_timing_is_fixture':True,
        'browser_transcript_id':browser_transcript_id,'rendered_transcript_version':current['version'],
        'explicit_CI_boundary_rereview':args.rereview_preserved_intervals,
        'explicit_non_destructive_source_end':args.source_end,
        'timing_independently_measured':False,'human_identity_and_approval_are_fixtures':True,'Owner_UAT':False,
        'full_Mode_A_B_accepted':False,'genuine_user_footage_accepted':False,'production_deployed':False,
        'owned_new_temporary_roots_cleaned':True,'original_browser_root_cleanup_claimed':False,'model_weights_in_backup':False}
    write(out/'evidence.json',report);print(json.dumps(report))

if __name__=='__main__':main()
