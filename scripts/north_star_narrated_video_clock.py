"""Independent decoded-frame check of an owned moving-video fixture clock.

FFmpeg source decoding does not reuse Remotion's playback implementation.
Evidence is local transport verification, never speech/provider/Owner acceptance.
"""
import argparse,json,subprocess,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from services.windows_native.pipeline import Config
from services.windows_native.contracts import file_sha
from services.windows_native.hardening import durable_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--evidence-dir',type=Path,required=True);args=parser.parse_args()
    bundle=args.bundle.resolve();out=args.evidence_dir.resolve()
    if out.exists() or REPO==out or REPO in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);record=json.loads((bundle/'narrated-video-render.json').read_bytes());manifest=record['manifest']
    project=json.loads((bundle/'project.json').read_bytes());registered={a['id']:a for a in project['document']['assets']}
    timeline=project['document']['canonical_timeline']['snapshot'];primary=next(t for t in timeline['tracks'] if t['track_id']=='trk_native_video')
    ffmpeg=str(Config().ffmpeg_bin/'ffmpeg.exe');measurements=[]
    for frame in (6,18,33):
        t=frame/30;clip=next(c for c in manifest['visual_clips'] if c['type']=='video' and c['timeline_start']<=t<c['timeline_start']+c['duration'])
        original=next(c for c in primary['clips'] if c['clip_id']==clip['clip_id']);source=bundle/'assets'/original['metadata']['native_asset_id']
        if file_sha(source)!=registered[original['metadata']['native_asset_id']]['sha256']:raise AssertionError('Fixture source changed')
        viewport=clip['viewport'];width=manifest['metadata']['width'];height=manifest['metadata']['height'];top=round(viewport['y']*height);plane=round(viewport['height']*height)
        expected=clip['source_start']+(t-clip['timeline_start'])*(clip['source_end']-clip['source_start'])/clip['duration']
        def raw(path,at,source_frame=False):
            fit=f'scale={width}:{plane}:force_original_aspect_ratio='+('decrease' if clip['fit']=='contain' else 'increase')
            fit+=f',pad={width}:{plane}:(ow-iw)/2:(oh-ih)/2:color=black' if clip['fit']=='contain' else f',crop={width}:{plane}'
            filt=(fit+',' if source_frame else '')+f'crop=720:400:180:{80 if source_frame else top+80},format=rgb24'
            return subprocess.run([ffmpeg,'-v','error','-nostdin','-ss',str(at),'-i',str(path),'-vf',filt,'-frames:v','1','-f','rawvideo','pipe:1'],capture_output=True,check=True,timeout=30).stdout
        actual=raw(bundle/'final.mp4',t);times={'canonical_source_clock':expected,'unretimed_timeline_clock':t,'source_start_without_speed':clip['source_start']+t-clip['timeline_start']}
        errors={}
        for name,at in times.items():
            other=raw(source,at,True)
            if len(actual)!=720*400*3 or len(other)!=len(actual):raise AssertionError('Decoded ROI shape differs')
            errors[name]=round(sum(abs(a-b) for a,b in zip(actual,other))/len(actual),6)
        if errors['canonical_source_clock']>=errors['unretimed_timeline_clock']:raise AssertionError('Actual video does not follow its canonical source clock')
        if original['speed']!=1 and errors['canonical_source_clock']>=errors['source_start_without_speed']:raise AssertionError('Actual video speed differs from canonical')
        measurements.append({'frame':frame,'timeline_seconds':t,'source_seconds':expected,'clip_id':clip['clip_id'],'speed':original['speed'],'roi_MAE_8bit':errors})
    for name in ('preview','final'):
        subprocess.run([ffmpeg,'-v','error','-nostdin','-n','-ss','0.2','-i',str(bundle/(name+'.mp4')),'-frames:v','1',str(out/(name+'-canonical-frame.png'))],capture_output=True,check=True,timeout=30)
    evidence={'schema_version':'owned-narrated-video-clock-proof-v1','bundle':str(bundle),'method':'independent FFmpeg source frame decode, fit to brand media viewport and compare a moving ROI excluding subtitles',
        'manifest_sha256':file_sha(bundle/'narrated-video-render.json'),'final_sha256':file_sha(bundle/'final.mp4'),'measurements':measurements,
        'provider_calls':0,'owner_UAT':False,'browser_rendered':False,'exports':{p.name:file_sha(p) for p in out.iterdir() if p.is_file()}}
    durable_json(out/'evidence.json',evidence);print(json.dumps(measurements))

if __name__=='__main__':main()
