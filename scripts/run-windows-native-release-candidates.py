"""Dispatch exact user-approved release snapshots to the real native worker.

No fixture audio, provider substitutes, automatic approvals or failed-job replay.
"""
import json
from pathlib import Path
import sys
import time
REPO=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(REPO))
from services.windows_native.contracts import digest,file_sha,write_json
from services.windows_native.pipeline import Config
from services.windows_native.store import Store

def main():
    directory=REPO/'evidence/post-mvp-roadmap/phase-8'; config=Config(); store=Store(config.data_root)
    authorization=json.loads((directory/'owner-script-authorization.json').read_bytes())
    assert file_sha(directory/'review-bundle.md')==authorization['review_bundle_sha256']
    target=directory/'real-candidates.json'
    if target.exists(): report=json.loads(target.read_bytes())
    else: report={'status':'RUNNING_REAL_TTS_AND_RENDER','authorization_sha256':file_sha(directory/'owner-script-authorization.json'),'fixture_audio':False,'failed_job_automatic_replay':False,'human_final_approval_granted':False,'jobs':[]}
    for e in authorization['projects']:
        p=store.get(e['project_id']); assert p['revision']==e['revision'] and digest(p['document'])==e['document_sha256']
        assert p['approval'] and p['approval']['snapshot_sha256']==e['document_sha256'] and p['approval']['reviewer']==authorization['reviewer_label']
        entry=next((r for r in report['jobs'] if r['number']==e['number']),None)
        if entry is None:
            job=store.enqueue(p['id'],p['revision'],'render',f"phase8-real-render-{p['id']}-{p['revision']}")
            entry={**e,'job_id':job['id'],'approval':p['approval']}; report['jobs'].append(entry); write_json(target,report)
    previous=None
    while True:
        terminal=0; progress=[]
        for entry in report['jobs']:
            job=store.get_job(entry['job_id']); entry.update(status=job['status'],stage=job['stage'],error_code=(job.get('error') or {}).get('code'),result=job.get('result'),final_review=job.get('final_review'))
            if job['status'] in ('succeeded','failed','interrupted'): terminal+=1
            progress.append({'number':entry['number'],'status':job['status'],'stage':job['stage'],'error_code':entry['error_code']})
            out=config.data_root/'jobs'/entry['job_id']
            for name in ('voice.json','qc-report.json','render-manifest.json'):
                if (out/name).exists(): entry[name]=json.loads((out/name).read_bytes())
            if job['status']=='succeeded':
                entry['final_mp4']=str(out/'final.mp4'); entry['final_sha256']=file_sha(out/'final.mp4')
                assert entry['final_sha256']==job['result']['qc']['final_sha256']
                assert entry['voice.json']['profile_sha256']=='f2d848766784e7bd892680f933a799ec812c1c8acff62b019ac777aa1292c4d3'
                assert entry['voice.json']['network_blocked'] is True and entry['voice.json']['inference_calls']>0
                assert not (out/'fixture-voice-scene-projection.json').exists()
        summary=json.dumps(progress)
        if summary!=previous: print(summary,flush=True); previous=summary
        report['terminal_jobs']=terminal; report['successful_jobs']=sum(e['status']=='succeeded' for e in report['jobs']); report['failed_jobs']=sum(e['status'] in ('failed','interrupted') for e in report['jobs'])
        report['new_real_tts_inference_calls']=sum(e.get('voice.json',{}).get('inference_calls',0) for e in report['jobs'])
        if terminal==len(report['jobs']): report['status']='WAITING_ACTUAL_HUMAN_WATCH_LISTEN_REVIEW' if report['failed_jobs']==0 else 'REAL_RENDER_FAILURES_REQUIRE_REVIEW'
        write_json(target,report)
        if terminal==len(report['jobs']): break
        time.sleep(2)

if __name__=='__main__': main()
