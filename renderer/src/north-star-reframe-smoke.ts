/** Local synthetic media acceptance. No Vision/provider claim or production server. */
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
execFileSync('ffmpeg',['-v','error','-nostdin','-f','lavfi','-i','color=green:s=320x240:r=30:d=2',
  '-vf','drawbox=x=0:y=0:w=106:h=240:color=red:t=fill,drawbox=x=214:y=0:w=106:h=240:color=blue:t=fill',
  '-c:v','libx264','-pix_fmt','yuv420p',source]);
execFileSync('ffmpeg',['-v','error','-nostdin','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-ac','2',audio]);
const port=18040,app=createRendererApp({engine:new RemotionRenderEngine(),port,storageRoot:root});
const server=app.listen(port,'127.0.0.1');
try{
  const evidence=[];
  for(const [label,width,height] of [['portrait',540,960],['landscape',960,540],['square',540,540],['four-five',432,540]] as const){
    const manifest=makeTimelineManifest(source,audio);
    manifest.version='2.2';Object.assign(manifest.metadata,{width,height,duration_seconds:2,niche:'technology'});
    manifest.subtitles=[{cue_id:'sub_fixture',start_seconds:0,end_seconds:2,text:'Khung hình thử nghiệm',words:[]}];
    const relative=(320/240)/(width/height),cropWidth=Math.min(1,1/relative),cropHeight=Math.min(1,relative);
    Object.assign(manifest.visual_clips[0],{type:'video',duration:2,source_end:2,
      crop:{x:0,y:0,width:cropWidth,height:cropHeight},crop_keyframes:[
        {time:0,x:0,y:0,width:cropWidth,height:cropHeight},
        {time:2,x:1-cropWidth,y:1-cropHeight,width:cropWidth,height:cropHeight}]});
    const path=resolve(root,`${label}-manifest.json`),output=resolve(root,`${label}.mp4`);
    await writeFile(path,JSON.stringify(manifest,null,2));
    const response=await fetch(`http://127.0.0.1:${port}/render`,{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({job_id:`rnd_fixture_${label.replace('-','_')}`,manifest_path:path,output_path:output})});
    const receipt=await response.json();
    if(!response.ok||receipt.status==='failed')throw new Error(JSON.stringify(receipt));
    const measured=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',output],{encoding:'utf8'}));
    const video=measured.streams.find((s:{codec_type:string})=>s.codec_type==='video');
    if(video.width!==width||video.height!==height||Math.abs(Number(measured.format.duration)-2)>.1)throw new Error('measured geometry/duration mismatch');
    const pixel=(time:string)=>execFileSync('ffmpeg',['-v','error','-ss',time,'-i',output,'-vf',`crop=2:2:${Math.floor(width/2)}:${Math.floor(height*.35)}`,
      '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1']);
    const first=[...pixel('0.1').subarray(0,3)],last=[...pixel('1.8').subarray(0,3)];
    if(label==='portrait'&&(!(first[0]>first[2]+80)||!(last[2]>last[0]+80)))throw new Error('encoded crop path did not traverse red to blue');
    evidence.push({label,width,height,receipt,measured,first_rgb:first,last_rgb:last,fixture:true,real_provider:false});
  }
  await writeFile(resolve(root,'evidence.json'),JSON.stringify({test:'local-real renderer / synthetic tracking evidence',evidence},null,2));
  console.log(JSON.stringify({output:root,profiles:evidence.length,status:'passed'}));
}finally{await new Promise<void>(done=>server.close(()=>done()));}
