import {describe,expect,it} from 'vitest';
import {sourceCropAt} from './reframe';
import {makeTimelineManifest} from './test-fixtures';
import {timelineRenderManifestSchema} from './contract';

describe('source-relative reframe paths',()=>{
  const clip=()=>({...makeTimelineManifest('file:///fixture.mp4').visual_clips[0],type:'video' as const,
    source_start:2,source_end:6,duration:2,crop_keyframes:[
      {time:0,x:0,y:0,width:.5,height:1},{time:8,x:.5,y:0,width:.5,height:1}]});
  it('preserves source time through trim, speed, split and timeline moves',()=>{
    expect(sourceCropAt(clip(),0).x).toBe(.125);
    expect(sourceCropAt(clip(),1).x).toBe(.25);
    expect(sourceCropAt({...clip(),timeline_start:20},1).x).toBe(.25);
    expect(sourceCropAt({...clip(),source_start:4,duration:1},0).x).toBe(.25);
  });
  it('clamps endpoints and retains manual crops without a tracking path',()=>{
    expect(sourceCropAt(clip(),-1).x).toBe(.125);
    expect(sourceCropAt(clip(),20).x).toBe(.5);
    const manual=makeTimelineManifest('x').visual_clips[0];
    expect(sourceCropAt(manual,20)).toEqual(manual.crop);
  });
  it('requires v2.2 for paths, validates order, bounds and new profiles',()=>{
    const manifest=makeTimelineManifest('file:///fixture.mp4');
    manifest.version='2.2';manifest.metadata.width=432;manifest.metadata.height=540;
    manifest.visual_clips[0]={...clip(),source_start:0,source_end:1,duration:1};
    expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(true);
    manifest.version='2.1';expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(false);
    manifest.version='2.2';manifest.visual_clips[0].crop_keyframes![1].time=0;
    expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(false);
    manifest.visual_clips[0].crop_keyframes![1].time=8;manifest.visual_clips[0].crop_keyframes![1].x=.6;
    expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(false);
  });
});
