"""Retained four-canvas local render/QC with explicitly synthetic PCM and images.

This is renderer geometry evidence, not a cross-project narration reuse, provider
inference, family UI, real footage/voice, legal acceptance or Owner UAT claim.
"""
import argparse,copy,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.contracts import digest,file_sha,write_json
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.north_star_quality import policy_reference
from services.windows_native.pipeline import render
from services.windows_native.tests.test_shot_production import prepared,voice

def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as handle:json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n')

def run(args):
    root,out=args.data_root.resolve(),args.output.resolve()
    if root.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-narrated-canvas-[a-z0-9-]+',root.name) or root.exists():raise ValueError('Fresh owned canvas root required')
    if out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:raise ValueError('Fresh distinct evidence required')
    root.mkdir();out.mkdir(parents=True);config,store,project=prepared(root)
    config.secret_file=root/'absent-secrets'/'absent-openai.env';config.assemblyai_secret_file=root/'absent-secrets'/'absent-asr.dpapi'
    assert not config.secret_file.exists() and not config.assemblyai_secret_file.exists()
    project=store.set_brand(project['id'],project['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
    for shot in list(store.shot_view(project['id'])['shot_timeline']['shots']):
        project=store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'requested_duration':None}})
    voice(root/'synthetic-source-pcm');original_sha=file_sha(root/'synthetic-source-pcm'/'voice.wav');receipts=[]
    for suffix,ratio,w,h,profile in [('', '9:16',1080,1920,'vertical-short'),('-landscape','16:9',1920,1080,'landscape'),('-square','1:1',1080,1080,'square'),('-feed','4:5',1080,1350,'portrait-feed')]:
        current=store.set_brand(project['id'],store.get(project['id'])['revision'],'vang-nguyen','personal-30'+suffix,duration_mode=FIT_NARRATION_POLICY)
        doc=copy.deepcopy(current['document']);doc['production_quality']=policy_reference()
        snapshot={'document':doc,'approval':{'snapshot_sha256':digest(doc),'revision':current['revision'],'reviewer':'EXPLICIT SYNTHETIC CANVAS FIXTURE, NOT OWNER UAT'}}
        directory=out/profile;directory.mkdir();write(directory/'input.json',snapshot)
        for name in ['voice.wav','voice.json']:
            with (directory/name).open('xb') as handle:handle.write((root/'synthetic-source-pcm'/name).read_bytes())
        report=render(config,snapshot,directory);manifest=json.loads((directory/'render-manifest.json').read_bytes())
        assert report['passed'] and report['full_quality']['status']=='passed' and file_sha(directory/'voice.wav')==original_sha
        assert manifest['render_profile']=={'id':profile,'width':w,'height':h,'aspect_ratio':ratio}
        assert len(report['full_quality']['subtitle_bounds']['samples'])==2 and all(s['inside_safe_area'] for s in report['full_quality']['subtitle_bounds']['samples'])
        cue=manifest['captions'][0];stamp=(cue['start']+cue['end'])/2
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-n','-ss',str(stamp),'-i',str(directory/'final.mp4'),
            '-frames:v','1',str(directory/'review-frame.png')],check=True,capture_output=True,timeout=30)
        receipts.append({'profile':profile,'width':w,'height':h,'aspect_ratio':ratio,'final_sha256':report['final_sha256'],
            'duration_seconds':report['duration_seconds'],'source_pcm_unchanged':True,'voice_sha256':original_sha,
            'actual_libass_masks':2,'full_qc':'passed','human_final_video_accepted':False})
    names=['services/windows_native/branding.py','services/windows_native/narrated_layout.py','services/windows_native/pipeline.py',
        'services/windows_native/tests/test_narrated_canvas.py','scripts/north_star_native_narrated_canvas.py']
    write(out/'evidence.json',{'schema':'native-narrated-canvas-rehearsal-v1','explicit_synthetic_pcm_images_and_approval':True,'renders':receipts,
        'provider_inferences':0,'external_provider_calls':0,'paid_operations':0,'owner_uat_accepted':False,'cross_project_voice_reuse_tested':False,
        'multi_platform_family_ui_tested':False,'publishing_enabled':False,'production_deployed':False,
        'source_sha256':{n:file_sha(ROOT/n) for n in names},'exports':{p.relative_to(out).as_posix():{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.rglob('*') if p.is_file()}})
    print(json.dumps({'status':'NARRATED_FOUR_CANVAS_RENDER_QC_PASS','profiles':4,'actual_masks':8,'external_calls':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
