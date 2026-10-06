import type {TimelineRenderManifest} from './types';
type VisualClip=TimelineRenderManifest['visual_clips'][number];

export const sourceCropAt=(clip:VisualClip,localSeconds:number):VisualClip['crop']=>{
  const points=clip.crop_keyframes;
  if(!points?.length)return clip.crop;
  const speed=clip.source_end===null?1:(clip.source_end-clip.source_start)/clip.duration;
  const time=clip.source_start+Math.max(0,localSeconds)*speed;
  if(time<=points[0].time)return points[0];
  const last=points[points.length-1];
  if(time>=last.time)return last;
  const next=points.findIndex(point=>point.time>=time),a=points[next-1],b=points[next];
  const fraction=(time-a.time)/(b.time-a.time);
  return {x:a.x+(b.x-a.x)*fraction,y:a.y+(b.y-a.y)*fraction,
    width:a.width+(b.width-a.width)*fraction,height:a.height+(b.height-a.height)*fraction};
};
