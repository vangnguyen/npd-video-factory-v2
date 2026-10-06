"""Export local source-preview evidence from an isolated synthetic Native fixture."""
import argparse
import array
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.windows_native.contracts import file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.pipeline import Config
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.store import Store
from services.windows_native.auto_edit_timeline import view


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--project-id',required=True)
    parser.add_argument('--evidence-dir',type=Path,required=True)
    args=parser.parse_args();root=args.data_root.resolve();out=args.evidence_dir.resolve()
    if root.parent!=Path('C:/') or not root.name.startswith('vf-native-fixture-'):
        raise ValueError('Synthetic Native fixture root required')
    if out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:
        raise ValueError('Fresh external evidence directory required')
    absent=root.parent/(root.name+'-absent-secrets')
    config=Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
    store=Store(root);project=view(store,args.project_id);before=store.get(project['id'])
    manager=PreviewManager(config,store)
    try:
        manager.generate(project['id'],project['revision'])
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            value=manager.status(project['id'])
            if value['status'] not in {'QUEUED','RUNNING'}:break
            time.sleep(.1)
        if value['status']!='READY':raise RuntimeError(value.get('error') or value['status'])
        output=manager.video_path(project['id'],value['timeline_version'])
        probe=json.loads(subprocess.check_output([str(config.ffmpeg_bin/'ffprobe.exe'),'-v','error',
            '-show_streams','-show_format','-of','json',str(output)],text=True))
        pcm=subprocess.check_output([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-i',str(output),
            '-map','0:a:0','-ac','1','-ar','48000','-f','s16le','pipe:1'])
        samples=array.array('h');samples.frombytes(pcm)
        rms=math.sqrt(sum(float(sample)**2 for sample in samples)/len(samples))/32768
        if before!=store.get(project['id']):raise AssertionError('Preview mutated project')
        out.mkdir(parents=True)
        shutil.copyfile(output,out/'preview.mp4')
        durable_json(out/'preview.json',value)
        durable_json(out/'render-manifest.json',value['manifest'])
        durable_json(out/'timeline.json',project['document']['canonical_timeline'])
        durable_json(out/'ffprobe.json',probe)
        durable_json(out/'audio-analysis.json',{'source':'actual_decoded_preview_pcm','sample_rate':48000,
            'sample_count':len(samples),'rms':rms,'speech_recognition_accepted':False})
        receipt={'explicit_fixture':True,'fixture_asr':True,'project_id':project['id'],
            'project_unchanged':True,'source_sha256':project['document']['assets'][0]['sha256'],
            'timeline_sha256':value['timeline_sha256'],'timeline_version':value['timeline_version'],
            'local_real_preview':True,'external_provider_calls':0,'tts_calls':0,'audio_rms':rms,
            'canvas':[value['manifest']['width'],value['manifest']['height']],
            'duration_seconds':float(probe['format']['duration']),
            'exports':{path.name:file_sha(path) for path in out.iterdir() if path.is_file()},
            'captions_included':False,'smart_reframe_keyframes_included':False,'music_ducking':False,
            'final_render_ready':False,'ui_workflow_ready':False,'owner_uat':False,
            'real_provider_acceptance':False,'production_deployed':False}
        durable_json(out/'evidence.json',receipt)
        print(json.dumps(receipt,ensure_ascii=False))
    finally:manager.close()


if __name__=='__main__':main()
