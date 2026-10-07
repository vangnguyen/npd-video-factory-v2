/** Private local job renderer; no general render API or whole-workspace static root. */
import express from 'express';
import {randomBytes} from 'node:crypto';
import {access, lstat, readFile, realpath, writeFile} from 'node:fs/promises';
import {extname, isAbsolute, join, relative, resolve} from 'node:path';
import type {Server} from 'node:http';
import {timelineRenderManifestSchema} from './contract';
import type {RenderEngine} from './app';
import {RemotionRenderEngine} from './engine';

const inside = (root:string,path:string) => {
  const rel=relative(root,path);
  return rel!==''&&!rel.startsWith('..')&&!isAbsolute(rel);
};

export async function renderNativeJob(directory:string, engine?:RenderEngine, options:{preview?:boolean}={}) {
  if(options.preview!==undefined&&typeof options.preview!=='boolean')throw new Error('NATIVE_RENDER_OPTIONS_INVALID');
  const scale=options.preview === true ? 0.4 : 1;
  engine ??= new RemotionRenderEngine({sourceProfile:true,scale});
  if(!isAbsolute(directory))throw new Error('NATIVE_RENDER_JOB_PATH_INVALID');
  const root=await realpath(directory),media=join(root,'media');
  const output=join(root,'final.mp4');
  try {await access(output);throw new Error('NATIVE_RENDER_OUTPUT_EXISTS');}
  catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
  const manifest=timelineRenderManifestSchema.parse(JSON.parse(await readFile(join(root,'timeline-render.json'),'utf8')));
  const paths=[manifest.audio.mix_uri,...manifest.visual_clips.map(clip=>clip.uri)];
  const files=new Map<string,string>();
  for(const candidate of paths){
    if(!isAbsolute(candidate))throw new Error('NATIVE_RENDER_LOCAL_ASSET_REQUIRED');
    if(!['.png','.jpg','.jpeg','.webp','.mp4','.mov','.webm','.wav'].includes(extname(candidate).toLowerCase()))throw new Error('NATIVE_RENDER_MEDIA_TYPE_INVALID');
    const path=await realpath(candidate),stat=await lstat(candidate);
    if(!stat.isFile()||stat.isSymbolicLink()||!inside(media,resolve(candidate))||!inside(media,path))throw new Error('NATIVE_RENDER_MEDIA_SCOPE_INVALID');
    if(!files.has(candidate))files.set(candidate,path);
  }
  const app=express(),token=randomBytes(32).toString('hex');
  const addresses=new Map<string,string>();
  let index=0;
  for(const [original,path] of files){
    const route=`/${token}/${index++}`;
    addresses.set(original,route);
    app.get(route,(_req,res)=>{
      res.setHeader('Cache-Control','no-store');
      res.setHeader('Access-Control-Allow-Origin','*');
      res.sendFile(path,{dotfiles:'deny'});
    });
  }
  app.use((_req,res)=>res.sendStatus(404));
  const server:Server=await new Promise((done,reject)=>{
    const candidate=app.listen(0,'127.0.0.1',()=>done(candidate));
    candidate.once('error',reject);
  });
  try{
    const address=server.address();
    if(!address||typeof address==='string')throw new Error('NATIVE_RENDER_MEDIA_SERVER_FAILED');
    const url=(path:string)=>`http://127.0.0.1:${address.port}${addresses.get(path)}`;
    const browserManifest={...manifest,audio:{...manifest.audio,mix_uri:url(manifest.audio.mix_uri)},
      visual_clips:manifest.visual_clips.map(clip=>({...clip,uri:url(clip.uri)}))};
    await engine.render({manifest:browserManifest,outputPath:output,
      onProgress:progress=>process.stdout.write(JSON.stringify({event:'native_render_progress',progress:Math.max(0,Math.min(1,progress))})+'\n')});
    await access(output);
    const receipt={status:'success',renderer:'remotion-local-native-job-v1',
      fixture:!(engine instanceof RemotionRenderEngine),final_qc_verified:false,
      duration_seconds:manifest.metadata.duration_seconds,width:Math.round(manifest.metadata.width*scale),
      height:Math.round(manifest.metadata.height*scale),fps:manifest.metadata.fps,private_job_media_only:true,
      ...(options.preview?{preview:true,scale,composition_width:manifest.metadata.width,
        composition_height:manifest.metadata.height,rendering_effects_parity:true}:{}),
      external_publish_requested:false,human_final_video_accepted:false};
    await writeFile(join(root,'renderer-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
    return receipt;
  }finally{
    server.closeAllConnections();
    await new Promise<void>(done=>server.close(()=>done()));
  }
}
