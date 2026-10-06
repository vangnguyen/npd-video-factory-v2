import {describe,it,expect} from 'vitest';
import {captionParts,keywordParts} from './subtitles';
import {timelineRenderManifestSchema} from './contract';
import {makeTimelineManifest} from './test-fixtures';

const cue={cue_id:'sub_unicode',start_seconds:0,end_seconds:2,text:'Cần Giờ, Việt Nam!',words:[
  {text:'Cần',start_seconds:0,end_seconds:.3},{text:'Giờ',start_seconds:.4,end_seconds:.8},
  {text:'Việt',start_seconds:1,end_seconds:1.3},{text:'Nam',start_seconds:1.4,end_seconds:1.8}]};
const style=makeTimelineManifest('fixture').subtitle_style;
describe('measured dynamic captions',()=>{
  it('displays only the current measured word, without filling timestamp gaps',()=>{
    const selected={...style,animation:'word_by_word' as const};
    expect(captionParts(cue,selected,.2).map(p=>p.text)).toEqual(['Cần']);
    expect(captionParts(cue,selected,.35)).toEqual([]);
    expect(captionParts(cue,selected,.6).map(p=>p.text)).toEqual(['Giờ']);
  });
  it('preserves full Vietnamese punctuation and uses measured karaoke progress',()=>{
    const parts=captionParts(cue,{...style,animation:'karaoke'},.6);
    expect(parts.map(p=>p.text).join('')).toBe(cue.text);
    expect(parts.find(p=>p.wordIndex===0)?.progress).toBe(1);
    expect(parts.find(p=>p.wordIndex===1)?.progress).toBeCloseTo(.5);
    expect(parts.find(p=>p.wordIndex===2)?.progress).toBe(0);
  });
  it('matches accented words and phrases without substring false matches or timing',()=>{
    const text='Cần Giờ, gần Cần Giờ! cần thiết; giờ.';
    const parts=keywordParts(text.normalize('NFD'),['Cần Giờ']);
    expect(parts.map(p=>p.text).join('')).toBe(text);
    expect(parts.filter(p=>p.highlighted).map(p=>p.text)).toEqual(['Cần','Giờ','Cần','Giờ']);
    expect(parts.every(p=>p.wordIndex===null)).toBe(true);
  });
  it('gates v2.3, rejects missing or mismatched words, and allows static keyword captions',()=>{
    const manifest=makeTimelineManifest('fixture');manifest.version='2.3';
    manifest.metadata.duration_seconds=2;manifest.subtitles=[structuredClone(cue)];
    manifest.subtitle_style={...style,animation:'karaoke',template_ref:'karaoke-gold@v1',keywords:[]};
    manifest.visual_clips[0].type='video';manifest.visual_clips[0].source_end=2;
    expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(true);
    manifest.version='2.2';expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(false);
    manifest.version='2.3';manifest.subtitles[0].words=[];
    expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(false);
    manifest.subtitle_style.animation='keyword_highlight';expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(true);
    manifest.subtitle_style.animation='word_by_word';manifest.subtitles[0].words=structuredClone(cue.words).slice(0,2);
    expect(timelineRenderManifestSchema.safeParse(manifest).success).toBe(false);
  });
});
