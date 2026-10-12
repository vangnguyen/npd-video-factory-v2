"""Independent fixture color/transition geometry against decoded owned-source and final video pixels.

No renderer function is reused. Only a foreground ROI away from captions/header
is evaluated; this proves fixture geometry, not semantic media quality or UAT.
"""
import argparse,io,json,math,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from services.windows_native.pipeline import Config
from services.windows_native.contracts import file_sha
from services.windows_native.hardening import durable_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--evidence-dir',type=Path,required=True);a=p.parse_args()
    bundle=a.bundle.resolve();out=a.evidence_dir.resolve()
    if out.exists() or out==REPO or REPO in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);e=json.loads((bundle/'evidence.json').read_bytes());project=json.loads((bundle/'project.json').read_bytes())
    path=bundle/('narrated-video-render.json' if e.get('canonical_video_render') else 'timeline-render.json')
    m=json.loads(path.read_bytes());manifest=m.get('manifest',m);canonical=project['document']['canonical_timeline']['snapshot']
    primary=next(t for t in canonical['tracks'] if t['track_id']=='trk_native_video' or t['type']=='video' and t['kind']=='source')
    original=primary['clips'][0];clip=next(c for c in manifest['visual_clips'] if c['clip_id']==original['clip_id'])
    native=original['metadata']['native_asset_id'];asset=next(a for a in project['document']['assets'] if a['id']==native);source=bundle/'assets'/native
    if file_sha(source)!=asset['sha256']:raise AssertionError('Retained source changed')
    width=manifest['metadata']['width'];height=manifest['metadata']['height'];fps=manifest['metadata']['fps']
    vp=clip.get('viewport',{'x':0,'y':0,'width':1,'height':1});vw=vp['width']*width;vh=vp['height']*height
    roi=(round(vw*.23),round(vh*.25),round(vw*.55),round(vh*.4));ffmpeg=str(Config().ffmpeg_bin/'ffmpeg.exe')
    def decode(path,at):
        raw=subprocess.run([ffmpeg,'-v','error','-nostdin','-ss',str(at),'-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,check=True,timeout=30).stdout
        return Image.open(io.BytesIO(raw)).convert('RGBA')
    def expected(pixels,props,relative_frame):
        c=props['crop'];t=props['transform'];w=vw/c['width'];h=vh/c['height']
        incoming=props.get('transition_in',{});outgoing=props.get('transition_out',{})
        entry=min(1,max(0,relative_frame/max(1,round(incoming.get('duration_seconds',0)*fps)))) if incoming.get('duration_seconds') else 1
        out_frames=max(1,round(outgoing.get('duration_seconds',0)*fps));end=max(1,round(props['duration']*fps))
        exit=min(1,max(0,(relative_frame-(end-out_frames))/max(1,out_frames-1))) if outgoing.get('duration_seconds') else 0
        opacity=props['opacity']*(entry if incoming.get('kind') in ('fade','crossfade','dissolve') else 1)*(1-exit if outgoing.get('kind') in ('fade','dissolve') else 1)
        slide=((1-entry) if incoming.get('kind')=='slide' else 0)-(exit if outgoing.get('kind')=='slide' else 0)
        shift=slide*vw;left=-c['x']/c['width']*vw+shift;top=-c['y']/c['height']*vh
        factor=(min if props['fit']=='contain' else max)(w/pixels.width,h/pixels.height);offset_x=(w-pixels.width*factor)/2;offset_y=(h-pixels.height*factor)/2
        angle=math.radians(t['rotation_degrees']);cos=math.cos(angle);sin=math.sin(angle);scale=t['scale']
        origin_x=left+w/2+t['x']*w;origin_y=top+h/2+t['y']*h
        # Inverse CSS translate * scale * rotate around the element centre.
        ax=cos/scale;bx=sin/scale;ay=-sin/scale;by=cos/scale
        dx=(roi[0]-origin_x)*ax+(roi[1]-origin_y)*bx+w/2;dy=(roi[0]-origin_x)*ay+(roi[1]-origin_y)*by+h/2
        layer=pixels.transform((roi[2],roi[3]),Image.Transform.AFFINE,(ax/factor,bx/factor,(dx-offset_x)/factor,ay/factor,by/factor,(dy-offset_y)/factor),Image.Resampling.BICUBIC)
        xx,yy=np.meshgrid(np.arange(roi[2]),np.arange(roi[3]));u=xx*ax+yy*bx+dx;v=xx*ay+yy*by+dy
        alpha=np.asarray(layer.getchannel('A')).copy();alpha[(u<0)|(u>w)|(v<0)|(v>h)|(xx+roi[0]<shift)|(xx+roi[0]>=shift+vw)]=0
        rgb=np.asarray(layer.convert('RGB')).astype(float)/255
        for effect in props.get('effects',[]):
            if effect['type']=='brightness':rgb=np.clip(rgb*effect['value'],0,1)
            elif effect['type']=='saturation':
                luma=np.sum(rgb*np.array([.213,.715,.072]),axis=2,keepdims=True);rgb=np.clip(luma+(rgb-luma)*effect['value'],0,1)
            else:raise ValueError('Independent pixel oracle only qualifies brightness/saturation fixtures')
        layer=Image.fromarray(np.round(rgb*255).astype('uint8')).convert('RGBA')
        alpha=(alpha.astype(float)*opacity).round().astype('uint8');layer.putalpha(Image.fromarray(alpha))
        result=Image.new('RGBA',layer.size,(5,8,13,255));result.alpha_composite(layer);return result.convert('RGB')
    measurements=[]
    frames=[round((clip['timeline_start']+.2)*fps),round((clip['timeline_start']+clip['duration']-.1)*fps),round((clip['timeline_start']+.1)*fps)]
    for frame in frames:
        at=frame/fps
        if not clip['timeline_start']<=at<clip['timeline_start']+clip['duration']:raise AssertionError('Sample outside the changed clip')
        source_at=clip['source_start']+(at-clip['timeline_start'])*(clip['source_end']-clip['source_start'])/clip['duration']
        source_frame=decode(source,source_at);actual=decode(bundle/'final.mp4',at)
        x=round(vp['x']*width)+roi[0];y=round(vp['y']*height)+roi[1];actual=actual.crop((x,y,x+roi[2],y+roi[3])).convert('RGB')
        variants={'canonical':clip,'wrong_no_effects':{**clip,'effects':[]},'wrong_no_transition':{**clip,'transition_in':{'kind':'cut','duration_seconds':0},'transition_out':{'kind':'cut','duration_seconds':0}}}
        errors={};expected_images={};actual.save(out/f'frame-{frame}-actual-ROI.png')
        for name,props in variants.items():
            image=expected(source_frame,props,frame-round(clip['timeline_start']*fps));image.save(out/f'frame-{frame}-{name}-ROI.png');expected_images[name]=np.asarray(image).astype(float)
            errors[name]=round(float(np.abs(np.asarray(actual).astype(float)-expected_images[name]).mean()),6)
        relevant=[name for name in variants if name!='canonical' and np.abs(expected_images['canonical']-expected_images[name]).mean()>2]
        if errors['canonical']>=14 or any(errors['canonical']>=errors[name] for name in relevant):
            raise AssertionError('Decoded pixels do not favor canonical style: '+json.dumps(errors))
        measurements.append({'frame':frame,'timeline_seconds':at,'source_seconds':source_at,'ROI':{'x':x,'y':y,'width':roi[2],'height':roi[3]},'MAE_8bit':errors,'distinguishable_controls':relevant})
    durable_json(out/'evidence.json',{'schema_version':'owned-clip-style-pixel-proof-v1','bundle':str(bundle),
        'method':'independent FFmpeg decode/PIL inverse affine; brightness/saturation matrix, viewport-relative slide and frame-bounded fade; foreground ROI excluding captions/header; other effect types not qualified by this fixture',
        'manifest_sha256':file_sha(path),'final_sha256':file_sha(bundle/'final.mp4'),'source_sha256':file_sha(source),'measurements':measurements,
        'canonical_style_beats_distinguishable_controls':True,'whole_frame_or_semantic_quality_accepted':False,'provider_calls':0,'owner_UAT':False,'browser_rendered':False,
        'exports':{f.name:file_sha(f) for f in out.iterdir() if f.is_file()}})
    print(json.dumps(measurements))

if __name__=='__main__':main()
