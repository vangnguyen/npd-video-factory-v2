"""Independent decoded-media oracle for the six-effect/two-clip local fixture.

No renderer implementation is imported. RGB matrices follow W3C Filter Effects
1 sections 9.6/13.1, with sRGB clamping after each saved effect. PIL Gaussian
blur is an approximation, so this proves sampled fixture parity, not pixel
identity, universal filter correctness, semantic quality or Owner acceptance.
"""
import argparse, copy, io, json, math, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from services.windows_native.pipeline import Config
from services.windows_native.contracts import file_sha
from services.windows_native.hardening import durable_json

SPEC='https://www.w3.org/TR/filter-effects-1/'

def effects(layer, decisions, width):
    alpha=np.asarray(layer.getchannel('A')).astype(float)/255
    rgb=np.asarray(layer.convert('RGB')).astype(float)/255
    for effect in decisions:
        kind, amount=effect['type'],effect['value']
        if kind=='brightness':rgb*=amount
        elif kind=='contrast':rgb=(rgb-.5)*amount+.5
        elif kind in {'saturation','grayscale'}:
            weights=np.array([.2126,.7152,.0722] if kind=='grayscale' else [.213,.715,.072])
            gain=1-amount if kind=='grayscale' else amount
            luma=np.sum(rgb*weights,axis=2,keepdims=True);rgb=luma+(rgb-luma)*gain
        elif kind=='hue_rotate':
            angle=math.radians(amount)
            base=np.tile([.213,.715,.072],(3,1))
            cosine=np.array([[.787,-.715,-.072],[-.213,.285,-.072],[-.213,-.715,.928]])
            sine=np.array([[-.213,-.715,.928],[.143,.140,-.283],[-.787,.715,.072]])
            rgb=rgb@(base+math.cos(angle)*cosine+math.sin(angle)*sine).T
        elif kind=='blur':
            # Blur premultiplied color/alpha, then restore unpremultiplied RGB.
            premul=np.dstack([np.clip(rgb,0,1)*alpha[:,:,None],alpha])
            image=Image.fromarray(np.round(premul*255).astype('uint8')).filter(ImageFilter.GaussianBlur(amount*width))
            data=np.asarray(image).astype(float)/255;alpha=data[:,:,3]
            rgb=np.divide(data[:,:,:3],alpha[:,:,None],out=np.zeros_like(rgb),where=alpha[:,:,None]>0)
        else:raise AssertionError('Unsupported independent oracle effect')
        rgb=np.clip(rgb,0,1)
    result=Image.fromarray(np.round(rgb*255).astype('uint8')).convert('RGBA')
    result.putalpha(Image.fromarray(np.round(alpha*255).astype('uint8')))
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--evidence-dir',type=Path,required=True);args=parser.parse_args()
    bundle=args.bundle.resolve();out=args.evidence_dir.resolve()
    if out.exists() or out==REPO or REPO in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);e=json.loads((bundle/'evidence.json').read_bytes());project=json.loads((bundle/'project.json').read_bytes())
    path=bundle/('narrated-video-render.json' if e.get('canonical_video_render') else 'timeline-render.json')
    m=json.loads(path.read_bytes());manifest=m.get('manifest',m);assert manifest['version']=='2.4'
    source_track=next(t for t in project['document']['canonical_timeline']['snapshot']['tracks'] if t['track_id']=='trk_native_video' or t['type']=='video' and t['kind']=='source')
    originals=sorted(source_track['clips'],key=lambda c:c['timeline_start'])[:2]
    clips=[next(c for c in manifest['visual_clips'] if c['clip_id']==o['clip_id']) for o in originals]
    first,second=clips;assert first['transition_out']['kind']=='crossfade'
    assert abs(second['timeline_start']-first['timeline_start']-first['duration'])<.001
    catalog={'brightness','contrast','saturation','hue_rotate','grayscale','blur'}
    assert all({e['type'] for e in c['effects']}==catalog for c in clips)
    ffmpeg=str(Config().ffmpeg_bin/'ffmpeg.exe');width=manifest['metadata']['width'];height=manifest['metadata']['height'];fps=manifest['metadata']['fps']
    vp=first.get('viewport',{'x':0,'y':0,'width':1,'height':1});vw=round(vp['width']*width);vh=round(vp['height']*height)
    assert all(c.get('viewport',vp)==vp for c in clips)
    roi=(round(vw*.08),round(vh*.24),round(vw*.65),round(vh*.36));sources={}
    for clip,original in zip(clips,originals):
        native=original['metadata']['native_asset_id'];asset=next(a for a in project['document']['assets'] if a['id']==native)
        p=bundle/'assets'/native;assert file_sha(p)==asset['sha256'];sources[clip['clip_id']]=p
    cache={}
    def decode(p,seconds):
        key=(str(p),round(seconds,6))
        if key not in cache:
            raw=subprocess.run([ffmpeg,'-v','error','-nostdin','-ss',str(seconds),'-i',str(p),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,check=True,timeout=30).stdout
            cache[key]=Image.open(io.BytesIO(raw)).convert('RGBA')
        return cache[key]
    def layer(clip,relative,props):
        end=max(1,round(clip['duration']*fps));source_frame=min(relative,end-1)
        seconds=clip['source_start']+source_frame/fps*(clip['source_end']-clip['source_start'])/clip['duration']
        pixels=decode(sources[clip['clip_id']],seconds);crop=props['crop'];transform=props['transform']
        w=vw/crop['width'];h=vh/crop['height'];left=-crop['x']/crop['width']*vw;top=-crop['y']/crop['height']*vh
        factor=(min if props['fit']=='contain' else max)(w/pixels.width,h/pixels.height)
        ox=(w-pixels.width*factor)/2;oy=(h-pixels.height*factor)/2
        angle=math.radians(transform['rotation_degrees']);scale=transform['scale'];a=math.cos(angle)/scale;b=math.sin(angle)/scale
        x=left+w/2+transform['x']*w;y=top+h/2+transform['y']*h
        affine=(a/factor,b/factor,(-x*a-y*b+w/2-ox)/factor,-b/factor,a/factor,(x*b-y*a+h/2-oy)/factor)
        image=pixels.transform((vw,vh),Image.Transform.AFFINE,affine,Image.Resampling.BICUBIC)
        xx,yy=np.meshgrid(np.arange(vw),np.arange(vh));u=(xx-x)*a+(yy-y)*b+w/2;v=-(xx-x)*b+(yy-y)*a+h/2
        alpha=np.asarray(image.getchannel('A')).copy();alpha[(u<0)|(u>w)|(v<0)|(v>h)]=0;image.putalpha(Image.fromarray(alpha))
        image=effects(image,props['effects'],vw)
        return image
    def expected(frame,omit=None,hardcut=False,no_slide=False,reverse=False):
        result=Image.new('RGBA',(vw,vh),(5,8,13,255));at=frame/fps
        ordered=list(reversed(clips)) if reverse else clips
        for clip in ordered:
            start=round(clip['timeline_start']*fps);end=max(1,round(clip['duration']*fps));relative=frame-start
            tail=first['transition_out']['duration_seconds'] if clip['clip_id']==first['clip_id'] and not hardcut else 0
            if relative<0 or relative>=end+round(tail*fps):continue
            props=copy.deepcopy(clip)
            if omit:props['effects']=[e for e in props['effects'] if e['type']!=omit]
            image=layer(clip,relative,props);gain=props['opacity']
            if clip['clip_id']==second['clip_id'] and not hardcut:gain*=min(1,relative/max(1,round(tail_seconds*fps)))
            outgoing=props.get('transition_out',{});count=max(1,round(outgoing.get('duration_seconds',0)*fps))
            progress=max(0,min(1,(relative-(end-count))/max(1,count-1)))
            if outgoing.get('kind')=='slide' and not no_slide:
                shifted=Image.new('RGBA',image.size);shifted.alpha_composite(image,(-round(progress*vw),0));image=shifted
            image.putalpha(Image.fromarray(np.round(np.asarray(image.getchannel('A')).astype(float)*gain).astype('uint8')))
            result.alpha_composite(image)
        return result.convert('RGB').crop((roi[0],roi[1],roi[0]+roi[2],roi[1]+roi[3]))
    tail_seconds=first['transition_out']['duration_seconds'];measurements=[];qualified=set()
    frames=[round((first['timeline_start']+min(.1,first['duration']/2))*fps),round((second['timeline_start']+tail_seconds/2)*fps),
            round((second['timeline_start']+tail_seconds)*fps),round((second['timeline_start']+second['duration']-.1)*fps)]
    for sample_index,frame in enumerate(frames):
        actual=decode(bundle/'final.mp4',frame/fps);x=round(vp['x']*width)+roi[0];y=round(vp['y']*height)+roi[1]
        actual=actual.crop((x,y,x+roi[2],y+roi[3])).convert('RGB');actual.save(out/f'frame-{frame}-actual.png')
        variants={'canonical':expected(frame),**{'omit_'+k:expected(frame,omit=k) for k in sorted(catalog)},
                  'hard_cut':expected(frame,hardcut=True),'no_outgoing_slide':expected(frame,no_slide=True),'wrong_reverse_draw_order':expected(frame,reverse=True)}
        arrays={k:np.asarray(v).astype(float) for k,v in variants.items()};errors={k:round(float(np.abs(np.asarray(actual).astype(float)-v).mean()),6) for k,v in arrays.items()}
        deltas={k:round(float(np.abs(arrays['canonical']-v).mean()),6) for k,v in arrays.items() if k!='canonical'}
        # Each frame has a declared purpose: color catalog, blend/draw order,
        # complete second-chain appearance, or outgoing slide. A color
        # omission during a mostly offscreen slide is not a color test.
        targets=({'omit_'+k for k in catalog if k!='blur'} if sample_index==0 else
                 {'hard_cut','wrong_reverse_draw_order'} if sample_index==1 else
                 {'no_outgoing_slide'} if sample_index==3 else set())
        relevant=[k for k in sorted(targets) if deltas[k]>2]
        # Blur is assessed at source-derived filter edges, not diluted by
        # flat areas. The mask never uses the actual output pixels.
        blur_mask=np.abs(arrays['canonical']-arrays['omit_blur']).mean(axis=2)>8
        edge={'selection':'canonical-versus-no-blur oracle delta >8/255; actual output excluded from mask',
              'pixels':int(blur_mask.sum()),'canonical_MAE':None,'omit_blur_MAE':None}
        if blur_mask.any():
            actual_array=np.asarray(actual).astype(float)
            edge.update(canonical_MAE=round(float(np.abs(actual_array-arrays['canonical'])[blur_mask].mean()),6),
                        omit_blur_MAE=round(float(np.abs(actual_array-arrays['omit_blur'])[blur_mask].mean()),6))
        for name,image in variants.items():image.save(out/f'frame-{frame}-{name}.png')
        row={'frame':frame,'timeline_seconds':frame/fps,'purpose':['first_clip_color_catalog','crossfade_and_draw_order','second_clip_chain_appearance','outgoing_slide'][sample_index],
             'ROI':{'x':x,'y':y,'width':roi[2],'height':roi[3]},'MAE_8bit':errors,'control_oracle_difference':deltas,'required_distinguishable_controls':relevant,'blur_edges':edge};measurements.append(row)
        durable_json(out/'measurements-draft.json',measurements)
        if set(relevant)!=targets:raise AssertionError('Required sample controls are not distinguishable: '+json.dumps(row))
        if errors['canonical']>=14 or any(errors['canonical']>=errors[k] for k in relevant):raise AssertionError('Independent parity mismatch: '+json.dumps(row))
        qualified.update(relevant)
        if sample_index==0:
            if edge['pixels']<64 or edge['canonical_MAE']>=14 or edge['canonical_MAE']>=edge['omit_blur_MAE']:
                raise AssertionError('First-clip edge sample does not favor saved blur')
            qualified.add('omit_blur')
    required={'omit_'+k for k in catalog}|{'hard_cut','no_outgoing_slide','wrong_reverse_draw_order'}
    if not required<=qualified:raise AssertionError('Fixture cannot distinguish all required controls: '+repr(required-qualified))
    durable_json(out/'evidence.json',{'schema_version':'owned-six-effect-crossfade-pixel-proof-v1','bundle':str(bundle),'specification':SPEC,
        'method':'independent sRGB matrices/PIL Gaussian blur/inverse affine/source-window freeze and alpha composition; sampled ROIs only',
        'manifest_sha256':file_sha(path),'final_sha256':file_sha(bundle/'final.mp4'),'source_sha256':{k:file_sha(v) for k,v in sources.items()},
        'measurements':measurements,'all_six_effect_omissions_distinguishable':True,'crossfade_and_outgoing_slide_distinguishable':True,
        'canonical_beats_every_required_sample_control':True,'blur_qualified_at_source_derived_edges':True,
        'other_control_comparisons_are_diagnostic_only':True,'whole_frame_or_semantic_quality_accepted':False,'owner_UAT':False,'browser_rendered':False,'provider_calls':0,
        'exports':{p.name:file_sha(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'samples':len(measurements),'qualified_controls':sorted(qualified),'canonical_MAE':[m['MAE_8bit']['canonical'] for m in measurements]}))

if __name__=='__main__':main()
