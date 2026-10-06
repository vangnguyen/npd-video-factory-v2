/** Fresh local encode with synthetic word timing. No ASR/provider/Owner UAT claim. */
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {createRendererApp} from './app';
import {RemotionRenderEngine} from './engine';
import {makeTimelineManifest} from './test-fixtures';

const root=resolve(process.argv[2]??'');
if(!process.argv[2])throw new Error('fresh output directory required');
await mkdir(root,{recursive:false});
const source=resolve(root,'source-fixture.mp4'),audio=resolve(root,'tone-not-speech.wav');
execFileSync('ffmpeg',['-v','error','-nostdin','-f','lavfi','-i','color=0x223344:s=320x240:r=30:d=2',
  '-c:v','libx264','-pix_fmt','yuv420p',source]);
execFileSync('ffmpeg',['-v','error','-nostdin','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-ac','2',audio]);
const app=createRendererApp({engine:new RemotionRenderEngine(),port:18041,storageRoot:root});
const server=app.listen(18041,'127.0.0.1');
try{
  const evidence=[];
  for(const animation of ['none','word_by_word','karaoke','keyword_highlight','pop','fade'] as const){
    const manifest=makeTimelineManifest(source,audio);manifest.version='2.3';
    Object.assign(manifest.metadata,{width:540,height:960,duration_seconds:2,niche:'technology'});
    Object.assign(manifest.visual_clips[0],{type:'video',duration:2,source_end:2});
    manifest.subtitles=[{cue_id:'sub_unicode',start_seconds:0,end_seconds:2,text:'Cần Giờ, Việt Nam!',words:[
      {text:'Cần',start_seconds:0,end_seconds:.3},{text:'Giờ',start_seconds:.4,end_seconds:.8},
      {text:'Việt',start_seconds:1,end_seconds:1.3},{text:'Nam',start_seconds:1.4,end_seconds:1.8}]}];
    Object.assign(manifest.subtitle_style,{animation,font_size:64,keywords:['Cần Giờ']});
    const path=resolve(root,`${animation}-manifest.json`),output=resolve(root,`${animation}.mp4`);
    await writeFile(path,JSON.stringify(manifest,null,2));
    const response=await fetch('http://127.0.0.1:18041/render',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({job_id:`rnd_fixture_${animation}`,manifest_path:path,output_path:output})});
    const receipt=await response.json();if(!response.ok||receipt.status==='failed')throw new Error(JSON.stringify(receipt));
    const measured=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',output],{encoding:'utf8'}));
    const video=measured.streams.find((s:{codec_type:string})=>s.codec_type==='video');
    if(video.width!==540||video.height!==960||Math.abs(Number(measured.format.duration)-2)>.1)throw new Error('measured geometry/duration mismatch');
    // Decode a caption frame and a timestamp gap for later visual review.
    for(const [label,time] of [['caption','0.6'],['gap','0.35']])execFileSync('ffmpeg',['-v','error','-ss',time,'-i',output,'-frames:v','1',resolve(root,`${animation}-${label}.png`)]);
    evidence.push({animation,receipt,measured,fixture_word_timestamps:true,audio:'synthetic tone, not speech',real_provider:false});
  }
  await writeFile(resolve(root,'evidence.json'),JSON.stringify({test:'local-real renderer / synthetic aligned caption evidence',evidence},null,2));
  console.log(JSON.stringify({output:root,modes:evidence.length,status:'passed'}));
}finally{await new Promise<void>(done=>server.close(()=>done()));}
