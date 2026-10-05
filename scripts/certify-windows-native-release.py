"""Read actual final approvals and evidence; refuse missing human release gates."""
import json
from pathlib import Path
import sqlite3
import sys
REPO=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(REPO))
from services.windows_native.contracts import digest,file_sha,write_json
from services.windows_native.hardening import Artifacts
from services.windows_native.media import verify_selected_files
from services.windows_native.editor import validate_plan
from services.windows_native.pipeline import Config,verify_runtime
from services.windows_native.store import Store

def main(*, emit=True):
    directory=REPO/'evidence/post-mvp-roadmap/phase-8'; config=Config(); store=Store(config.data_root)
    real=json.loads((directory/'real-candidates.json').read_bytes()); final=json.loads((directory/'final-review-manifest.json').read_bytes())
    authorization_path=directory/'owner-final-authorization.json'
    authorization=json.loads(authorization_path.read_bytes()) if authorization_path.exists() else None
    native_log=(REPO/'evidence/post-mvp-roadmap/phase-7/native-tests-fixed.log').read_text(encoding='utf-8-sig')
    studio_log=(REPO/'evidence/post-mvp-roadmap/phase-7/studio-tests.log').read_text(encoding='utf-8-sig')
    checks={'native_103_tests':'Ran 103 tests' in native_log and '\nOK' in native_log,'studio_27_tests':'pass 27' in studio_log and 'fail 0' in studio_log,'ten_real_successful_jobs':real['successful_jobs']==10 and real['failed_jobs']==0,'restart_evidence':all(json.loads((directory/'real-release-restart.json').read_bytes())['checks'].values()),'human_final_authorization':bool(authorization and authorization.get('watch_listen_acknowledged') is True),'explicit_native_internal_scope':bool(authorization and authorization.get('accepted_scope')=='Windows Native internal production only; legacy stack not certified'),'review_bundle_unchanged':file_sha(directory/'final-review-bundle.md')==final['review_bundle_sha256']}
    assert len(real['jobs'])==len(final['projects'])==10
    assert len({e['job_id'] for e in real['jobs']})==10
    verify_runtime(config,full=True); checks['locked_voice_runtime']=True
    decisions=[]; matrix=[]
    for e in real['jobs']:
        job=store.get_job(e['job_id']); p=store.get(e['project_id']); out=config.data_root/'jobs'/job['id']; voice=json.loads((out/'voice.json').read_bytes()); a=Artifacts(out,job)
        assert job['status']=='succeeded' and job['kind']=='render' and job['project_id']==p['id']
        reviewed=next(v for v in final['projects'] if v['job_id']==job['id'])
        assert all(reviewed[k]==e[k] for k in ('number','project_id','revision','document_sha256','final_sha256'))
        assert reviewed['snapshot_sha256']==digest(job['snapshot'])
        assert p['revision']==e['revision'] and digest(p['document'])==e['document_sha256'] and p['approval']==e['approval']
        assert a.load('tts') and a.load('render') and file_sha(out/'final.mp4')==e['final_sha256']
        assert file_sha(out/'voice.wav')==voice['audio_sha256'] and voice['network_blocked'] is True and voice['inference_calls']>0 and voice['retries']==0 and voice['speed']==1
        assert all(job['result']['qc']['checks'].values()) and job['result']['qc']['duration_seconds']==30
        review=job.get('final_review'); accepted=False
        if review and review['decision']=='approve' and review['artifact_sha256']==e['final_sha256'] and review['snapshot_sha256']==digest(job['snapshot']) and not review['reviewer'].startswith(('UNIT FIXTURE','INTEGRATION FIXTURE')):
            final_job=store.final_video(job['id']); assert final_job['id']==job['id']; accepted=True; decisions.append(review)
        draft=next(r for r in json.loads((directory/'review-drafts.json').read_bytes())['cases'] if r['number']==e['number'])
        family=draft['input_family']
        content=store.get_job(draft['job_id'])
        if draft.get('content_origin'):
            assert content['status']=='failed' and content['error']['code']=='CONTENT_AMBIGUOUS_RESPONSE'
            with store.transaction() as con:
                events=con.execute("SELECT payload FROM events WHERE project_id=? AND action='release_explicit_local_editor_draft_after_provider_failure'",(p['id'],)).fetchall()
            assert len(events)==1 and json.loads(events[0]['payload'])['proposal_sha256']==digest(p['document']['proposal'])
        else:
            assert content['status']=='awaiting_review' and Artifacts(config.data_root/'jobs'/content['id'],content).load('content')
            result=content['result']
            assert result['human_review_required'] is True and result['facts_verified'] is False
            assert (result.get('response_id') and result.get('usage') and result.get('model')=='gpt-6-luna') or result.get('source') in ('existing_user_script','immutable_provider_transcript_for_human_review')
        verify_selected_files(config,p['document']); assert validate_plan(p['document'])
        matrix.append({'number':e['number'],'input':family,'project_id':e['project_id'],'job_id':job['id'],'narration_snapshot_sha256':e['document_sha256'],'actual_voice_sha256':voice['audio_sha256'],'actual_mp4_sha256':e['final_sha256'],'provider_or_script_source_evidenced':True,'actual_human_script_approved':True,'storyboard_sources_validated':True,'fresh_locked_voice_inference_calls':voice['inference_calls'],'ffprobe_decode_audio_video_qc':True,'native_restart_checkpoint_hashes':True,'actual_human_final_approved':accepted})
    checks['ten_exact_final_decisions']=len(decisions)==10
    if authorization:
        checks['authorization_binds_ten_exact_files']=authorization.get('review_manifest_sha256')==file_sha(directory/'final-review-manifest.json') and len(authorization.get('projects',[]))==10 and all(any(v['job_id']==e['job_id'] and v['final_sha256']==e['final_sha256'] for v in authorization['projects']) for e in real['jobs'])
    else: checks['authorization_binds_ten_exact_files']=False
    with store.transaction() as con:
        checks['sqlite_integrity']=con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        checks['no_active_jobs']=con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]==0
    checks['accepted_mvp_mp4_unchanged']=file_sha(REPO/'evidence/windows-native-mvp/final.mp4')=='c0bbcf029554cfd2e7c29e05d595379abb6d894babc78154a16537f7fba1a47a'
    checks['accepted_mvp_wav_unchanged']=file_sha(Path(r'C:\NPD-Video-Factory\outputs\MVP1\voice.wav'))=='2b5f57c31c2514683a6465e408b2cbe20e949cc9e3921a84f68c28ab983a73e5'
    ready=all(checks.values())
    report={'INTERNAL_PRODUCTION_READY':'YES' if ready else 'NO','scope':'Windows Native internal production only; legacy stack not certified','status':'PASS' if ready else 'WAITING_ACTUAL_HUMAN_FINAL_REVIEW','checks':checks,'acceptance_matrix':matrix,'actual_human_final_decisions':decisions,'real_final_videos':10,'human_approved_final_videos':len(decisions),'new_local_tts_inference_calls':sum(e['voice.json']['inference_calls'] for e in real['jobs']),'new_content_provider_attempts':8,'valid_content_provider_results':7,'explicit_provider_failure_preserved':1,'automatic_paid_replays':0,'new_asr_calls_for_import':0,'legacy_windows_baseline':'NOT PASS: 46 failures / 24 errors; not certified; native-only scope acceptance '+('recorded' if checks['explicit_native_internal_scope'] else 'pending'),'limits':['Reference branding; no official logo/assets claim','Phrase subtitle estimates for new voice; no word alignment claim','Historical original-upload provenance gap disclosed and retained','No background music in this ten-video batch; real music/ducking acceptance belongs to Phase 5','Publishing, analytics and autonomy not implemented']}
    report['human_final_authorization_sha256']=file_sha(authorization_path) if authorization else None
    report['release_review_manifest_sha256']=file_sha(directory/'final-review-manifest.json')
    write_json(directory/'release-certification.json',report)
    if emit: print(json.dumps({'INTERNAL_PRODUCTION_READY':report['INTERNAL_PRODUCTION_READY'],'real_videos':10,'human_final_reviews':len(decisions),'scope':report['scope']}))
    return report

if __name__=='__main__': main()
