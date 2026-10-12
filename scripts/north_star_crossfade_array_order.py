"""Owned renderer probe: reversing storage order must preserve crossfade pixels.

This is a direct local renderer experiment, not a project mutation, approval,
full QC certification or accepted North Star video. Retained inputs are copied
into a fresh private job and exported before ordinary owned-fixture teardown.
"""
import argparse, copy, hashlib, io, json, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
import numpy as np
from PIL import Image

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from services.windows_native.pipeline import Config
from services.windows_native.contracts import file_sha
from services.windows_native.hardening import durable_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',required=True,type=Path);parser.add_argument('--evidence-dir',required=True,type=Path);a=parser.parse_args()
    bundle=a.bundle.resolve();out=a.evidence_dir.resolve()
    if out.exists() or out==REPO or REPO in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);e=json.loads((bundle/'evidence.json').read_bytes());project=json.loads((bundle/'project.json').read_bytes())
    for name,sha in e['exports'].items():assert file_sha(bundle/name)==sha,name
    original=json.loads((bundle/'timeline-render.json').read_bytes());assert original['version']=='2.4' and len(original['visual_clips'])==2
    clips=sorted(original['visual_clips'],key=lambda c:c['timeline_start']);assert clips[0]['transition_out']['kind']=='crossfade'
    assert clips[0]['track_order']==clips[1]['track_order'] and abs(clips[0]['timeline_start']+clips[0]['duration']-clips[1]['timeline_start'])<.001
    canonical={c['clip_id']:c for t in project['document']['canonical_timeline']['snapshot']['tracks'] for c in t['clips']}
    ffmpeg=str(Config().ffmpeg_bin/'ffmpeg.exe');samples=[]
    with tempfile.TemporaryDirectory(prefix='vf-xf-',dir='C:/') as temporary:
        root=Path(temporary);media=root/'media';media.mkdir();manifest=copy.deepcopy(original)
        for clip in manifest['visual_clips']:
            native=canonical[clip['clip_id']]['metadata']['native_asset_id'];asset=next(v for v in project['document']['assets'] if v['id']==native)
            source=bundle/'assets'/native;assert file_sha(source)==asset['sha256'];target=media/native
            if not target.exists():shutil.copyfile(source,target)
            clip['uri']=str(target)
        with zipfile.ZipFile(bundle/'backup.zip') as z:
            names=[n for n in z.namelist() if n.startswith('state/jobs/'+e['job_id']+'/') and n.endswith('/media/mix.wav')]
            assert len(names)==1;data=z.read(names[0])
            assert hashlib.sha256(data).hexdigest()==e['matching_preview_final_PCM_sha256']
        (media/'mix.wav').write_bytes(data);manifest['audio']['mix_uri']=str(media/'mix.wav')
        manifest['visual_clips']=list(reversed(manifest['visual_clips']))
        assert manifest['visual_clips'][0]['timeline_start']>manifest['visual_clips'][1]['timeline_start']
        durable_json(root/'timeline-render.json',manifest)
        with (out/'renderer.log').open('xb') as log:
            run=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(REPO/'renderer/node_modules/tsx/dist/cli.mjs'),str(REPO/'renderer/src/native-job-cli.ts'),str(root)],cwd=REPO,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        if run.returncode:raise AssertionError('Owned renderer reorder probe failed; retained renderer.log')
        shutil.copyfile(root/'final.mp4',out/'final.mp4');shutil.copyfile(root/'renderer-receipt.json',out/'renderer-receipt.json')
        shutil.copyfile(root/'timeline-render.json',out/'input-manifest.json');(out/'media').mkdir()
        for p in media.iterdir():shutil.copyfile(p,out/'media'/p.name)
        def decode(path,at):
            raw=subprocess.run([ffmpeg,'-v','error','-nostdin','-ss',str(at),'-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,check=True,timeout=30).stdout
            return Image.open(io.BytesIO(raw)).convert('RGB')
        midpoint=clips[1]['timeline_start']+clips[0]['transition_out']['duration_seconds']/2
        for at in [clips[1]['timeline_start']-.1,midpoint,clips[1]['timeline_start']+.3]:
            expected=decode(bundle/'final.mp4',at);actual=decode(out/'final.mp4',at)
            assert actual.size==expected.size;mae=float(np.abs(np.asarray(actual).astype(float)-np.asarray(expected).astype(float)).mean())
            expected.save(out/f'{at:.3f}-canonical.png');actual.save(out/f'{at:.3f}-reversed-input.png')
            samples.append({'timeline_seconds':at,'whole_frame_MAE_8bit':mae})
            durable_json(out/'measurements-draft.json',samples)
            if mae>=1:raise AssertionError('Storage order changed decoded renderer output')
    durable_json(out/'evidence.json',{'schema_version':'owned-crossfade-array-order-proof-v1','bundle':str(bundle),
        'input_clip_array_reversed':True,'native_project_or_history_mutated':False,'actual_remotion_renderer':True,
        'canonical_manifest_sha256':file_sha(bundle/'timeline-render.json'),'canonical_final_sha256':file_sha(bundle/'final.mp4'),
        'samples':samples,'decoded_pixels_preserved':True,'full_QC_performed_on_this_probe':False,'owner_UAT':False,'browser_rendered':False,
        'provider_calls':0,'paid_calls':0,'published':False,'production_deployed':False,'owned_fixture_cleaned_after_export':True,
        'exports':{str(p.relative_to(out)).replace('\\','/'):file_sha(p) for p in out.rglob('*') if p.is_file()}})
    print(json.dumps({'input_reversed':True,'samples':samples,'provider_calls':0}))

if __name__=='__main__':main()
