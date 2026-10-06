"""Local-real private renderer transport proof, using explicit synthetic Native evidence.

This bypasses no user workflow: the fixture calls the low-level renderer, never
approves a project or certifies its final QC/Owner acceptance.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.auto_edit_timeline import view
from services.windows_native.source_preview import resolve_assets
from services.windows_native.hardening import durable_json
from services.windows_native.contracts import file_sha
from app.production_logic import build_timeline_render_manifest, derive_subtitle_cues
from app.production_models import SubtitleVersionRead, SubtitleStyle, MixConfig
from app.timeline_audio import build_timeline_audio_graph


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--project-id',required=True)
    parser.add_argument('--evidence-dir',type=Path,required=True)
    args=parser.parse_args();root=args.data_root.resolve();out=args.evidence_dir.resolve()
    if root.parent!=Path('C:/') or not root.name.startswith('vf-native-fixture-'):
        raise ValueError('Synthetic Native fixture required')
    if out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:
        raise ValueError('Fresh external output required')
    config=Config(data_root=root);store=Store(root);project=view(store,args.project_id);before=store.get(project['id'])
    snapshot,assets=resolve_assets(config,project)
    out.mkdir(parents=True);media=out/'media';media.mkdir()
    staged={}
    for identifier,(asset,path) in assets.items():
        destination=media/(identifier+path.suffix.lower())
        shutil.copyfile(path,destination)
        if file_sha(destination)!=asset.checksum_sha256:raise AssertionError('Staged source changed')
        staged[identifier]=(asset,destination)
    graph=build_timeline_audio_graph(snapshot,staged,first_input_index=0)
    if not graph.clips:raise ValueError('This transport proof requires actual source audio')
    filter_path=out/'audio-filter.txt';filter_path.write_text(';'.join(graph.filters),encoding='utf-8')
    mixed=media/'mix.wav'
    subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n',*graph.inputs,
        '-/filter_complex',str(filter_path),'-map','[outa]','-c:a','pcm_s16le','-ar','48000','-ac','2',str(mixed)],
        check=True,capture_output=True,timeout=60)
    state=project['document']['canonical_timeline']
    subtitles=SubtitleVersionRead(subtitle_version_id='sub_fixture',package_id='pkg_fixture',project_id='prj_'+project['id'],
        timeline_version_id='tlv_fixture',timeline_version=state['version'],version=1,
        cues=derive_subtitle_cues(snapshot),style=SubtitleStyle(animation='none'),actor_ref='explicit-fixture',created_at=datetime.now(timezone.utc))
    profile={(1080,1920):'vertical-1080x1920',(1920,1080):'landscape-1920x1080',
        (1080,1080):'square-1080x1080',(1080,1350):'portrait-1080x1350'}[(snapshot.width,snapshot.height)]
    manifest=build_timeline_render_manifest(snapshot=snapshot,subtitles=subtitles,mix_config=MixConfig(),
        mixed_audio_path=mixed,asset_paths=staged,profile=profile,project_name=project['document']['name'],
        project_slug=project['id'],niche='technology',brand_name='Explicit local fixture',language='vi')
    # The private renderer validates the same versioned contract before exposing
    # any media or encoding. Native's locked environment needs no API validator.
    durable_json(out/'timeline-render.json',manifest)
    node=Path(r'C:\Program Files\nodejs\node.exe')
    command=[str(node),str(ROOT/'renderer/node_modules/tsx/dist/cli.mjs'),str(ROOT/'renderer/src/native-job-cli.ts'),str(out)]
    with (out/'renderer-process.log').open('wb') as log:
        subprocess.run(command,cwd=ROOT/'renderer',stdout=log,stderr=log,check=True,timeout=180)
    output=out/'final.mp4'
    probe=json.loads(subprocess.check_output([str(config.ffmpeg_bin/'ffprobe.exe'),'-v','error',
        '-show_streams','-show_format','-of','json',str(output)],text=True))
    durable_json(out/'ffprobe.json',probe)
    video=next(stream for stream in probe['streams'] if stream['codec_type']=='video')
    audio=next(stream for stream in probe['streams'] if stream['codec_type']=='audio')
    if ((video['width'],video['height'])!=(snapshot.width,snapshot.height)
            or video['pix_fmt']!='yuv420p' or video['codec_name']!='h264'
            or audio['codec_name']!='aac' or int(audio['sample_rate'])!=48000
            or abs(float(probe['format']['duration'])-snapshot.duration_seconds)>.12):
        raise AssertionError('Measured native renderer geometry/codec/profile mismatch')
    subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-ss','0.35',
        '-i',str(output),'-frames:v','1',str(out/'caption-frame.png')],check=True,capture_output=True,timeout=30)
    if before!=store.get(project['id']):raise AssertionError('Low-level renderer changed Native project')
    receipt={'explicit_fixture':True,'fixture_asr':True,'local_real_renderer_transport':True,
        'project_id':project['id'],'project_unchanged':True,'timeline_sha256':state['sha256'],
        'source_sha256':project['document']['assets'][0]['sha256'],'renderer':json.loads((out/'renderer-receipt.json').read_bytes()),
        'video_sha256':file_sha(output),'duration_seconds':float(probe['format']['duration']),
        'exports':{path.name:file_sha(path) for path in out.iterdir() if path.is_file()},
        'new_provider_calls':0,'new_tts_calls':0,'source_final_workflow_wired':False,'final_qc_accepted':False,
        'ui_workflow_ready':False,'owner_uat':False,'real_provider_acceptance':False,'production_deployed':False}
    durable_json(out/'evidence.json',receipt);print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
