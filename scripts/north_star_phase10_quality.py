"""Read-only candidate audit and optional isolated, network-blocked local TTS diagnostic.

Creates new evidence only. Never approves Owner UAT, rewrites candidate media,
reads API credentials, or calls remote transcription/content providers.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.windows_native.contracts import digest,file_sha,write_json
from services.windows_native.north_star_quality import POLICY,policy_reference,validate_render_profile,evaluate_speech_placement,audio_activity
from services.windows_native.pipeline import Config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--local-name-audio',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if output.exists():raise SystemExit('Evidence output already exists; use a fresh directory.')
    output.mkdir(parents=True)
    config=Config(data_root=output/'isolated-data',secret_file=output.parent/'absent-provider-config'/'openai.env',
                  assemblyai_secret_file=output.parent/'absent-provider-config'/'assemblyai.dpapi')
    summary=next((ROOT/'evidence/post-mvp-roadmap/phase-10/studio-ux-02/video-repair').rglob('five-repaired-video-summary.json'))
    old=json.loads(summary.read_bytes());rows=[]
    import numpy as np
    for candidate in old['actual_candidates']:
        video=Path(candidate['final_path']);before=file_sha(video)
        if before!=candidate['final_sha256']:raise SystemExit('Historical candidate hash mismatch')
        manifest=json.loads((video.parent/'render-manifest.json').read_bytes())
        measured=json.loads(subprocess.check_output([str(config.ffmpeg_bin/'ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(video)],timeout=30))
        stream=next(s for s in measured['streams'] if s['codec_type']=='video')
        from services.windows_native.branding import resolve
        snapshot=json.loads((video.parent/'input.json').read_bytes())
        _,template=resolve(snapshot['document'])
        expected_profile='landscape' if template and template.aspect_ratio=='16:9' else 'vertical-short'
        profile=validate_render_profile(expected_profile,stream['width'],stream['height'],template.aspect_ratio if template else '9:16')
        placement=evaluate_speech_placement(candidate['voice_placement'],float(measured['format']['duration']),POLICY)
        pcm=subprocess.check_output([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-i',str(video),'-vn','-f','f32le','-ac','1','-ar','48000','-'],timeout=60)
        activity=audio_activity(np.frombuffer(pcm,dtype='<f4'),48000)
        after=file_sha(video)
        row={'case':candidate['case'],'path':str(video),'sha256':before,'source_unchanged':before==after,
             'render_profile':profile,'speech_placement':placement,'final_audio_activity':activity,
             'canonical_input_name':candidate.get('required_full_name'),'lexicon_spelling_update_needed':candidate.get('required_full_name')=='Vinhomes Sài Gòn Park',
             'original_qc':json.loads((video.parent/'qc-report.json').read_bytes())['passed'],
             'duration_seconds':float(measured['format']['duration']),'owner_uat':'PENDING',
             'pronunciation_verified':False,'historical_artifact_replaced':False}
        row['measured_quality_passed']=row['source_unchanged'] and row['original_qc'] and all(placement[k] for k in ('no_narration_dead_air','no_excessive_speech_gaps')) and activity['trailing_silence_seconds']<=2.02
        rows.append(row)
    name_evidence={'status':'NOT_RUN','remote_calls':0}
    if args.local_name_audio:
        folder=output/'proper-name-diagnostic';folder.mkdir()
        names=POLICY['proper_names']
        sentences=[f'Tên cần kiểm tra là {name}.' for name in names]
        doc={'production_quality':policy_reference(),'proposal':{'narration':' '.join(sentences),
            'visual_brief':[{'scene':i+1,'visual':'Technical name diagnostic','on_screen_text':name,'narration_excerpt':sentence}
                            for i,(name,sentence) in enumerate(zip(names,sentences))],
            'facts_needing_source':['Local pronunciation diagnostic; Owner listening remains required.']}}
        snapshot={'document':doc,'approval':{'snapshot_sha256':digest(doc),'reviewer':'TECHNICAL PREPARATION AUTHORIZED BY PROGRAM TASK; NOT OWNER UAT'}}
        write_json(folder/'input.json',snapshot);write_json(folder/'runtime-config.json',config.dump())
        with (folder/'local-tts.log').open('w',encoding='utf-8') as log:
            child=subprocess.run([sys.executable,'-m','services.windows_native.tts_child',str(folder)],cwd=ROOT,stdout=log,stderr=log,timeout=600)
        status=json.loads((folder/'tts-status.json').read_bytes())
        name_evidence={'status':status,'child_returncode':child.returncode,'output':str(folder),'remote_calls':0,
                       'owner_listening_required':True,'pronunciation_verified':False,'names':names}
        if child.returncode==0:
            voice=json.loads((folder/'voice.json').read_bytes())
            name_evidence.update({'audio_sha256':file_sha(folder/'voice.wav'),'duration_seconds':voice['duration_seconds'],
                                  'units':voice['units'],'network_blocked':voice['network_blocked'],'real_local_inference_calls':voice['inference_calls']})
    result={'captured_at':datetime.now(timezone.utc).isoformat(),'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'policy':policy_reference(),'policy_configuration':POLICY,'candidates':rows,'local_name_evidence':name_evidence,
            'all_candidate_measured_quality_passed':all(x['measured_quality_passed'] for x in rows),
            'OWNER_UAT_REQUIRED':True,'PHASE10_READY':False,'production_deployed':False,'remote_provider_calls':0,'source_mutations':0}
    write_json(output/'phase10-quality-evidence.json',result)
    print(json.dumps({'candidates':len(rows),'measured_quality_pass':result['all_candidate_measured_quality_passed'],'local_tts_status':name_evidence['status'],'owner_uat':'PENDING'},ensure_ascii=False))


if __name__=='__main__':main()
