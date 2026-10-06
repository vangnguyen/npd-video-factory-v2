import {mkdtemp,mkdir,readFile,writeFile,rm,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {afterEach,expect,it,vi} from 'vitest';
import {renderNativeJob} from './native-job-render';
import {makeTimelineManifest} from './test-fixtures';

const roots:string[]=[];
afterEach(async()=>{vi.restoreAllMocks();await Promise.all(roots.splice(0).map(root=>rm(root,{recursive:true,force:true})));});
async function fixture(){
  const root=await mkdtemp(join(tmpdir(),'vf-native-render-job-'));roots.push(root);
  const media=join(root,'media');await mkdir(media);
  const visual=join(media,'visual.png'),audio=join(media,'mix.wav');
  await writeFile(visual,'explicit non-media contract fixture');await writeFile(audio,'explicit non-media contract fixture');
  const manifest=makeTimelineManifest(visual,audio);
  await writeFile(join(root,'timeline-render.json'),JSON.stringify(manifest));
  await writeFile(join(root,'private-database.sqlite3'),'PRIVATE_NATIVE_DATA_SENTINEL');
  return {root,visual,audio,manifest};
}

it('serves only selected media behind an ephemeral job token, supports ranges, closes and keeps raw manifests local',async()=>{
  const {root}=await fixture();let address='';
  const result=await renderNativeJob(root,{render:vi.fn(async({manifest,outputPath})=>{
    if(manifest.version==='1.0')throw new Error('timeline required');
    address=manifest.visual_clips[0].uri;
    expect(address).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/[a-f0-9]{64}\/\d+$/);
    const media=await fetch(address,{headers:{Range:'bytes=0-7'}});
    expect(media.status).toBe(206);expect(await media.text()).toBe('explicit');
    const base=new URL(address).origin,token=new URL(address).pathname.split('/')[1];
    for(const path of ['/media/private-database.sqlite3','/render','/timeline-render.json',`/${token}/private-database.sqlite3`,`/${token}/999`])expect((await fetch(base+path)).status).toBe(404);
    await writeFile(outputPath,'explicit nonplayable renderer fixture');
  })});
  expect(result.private_job_media_only).toBe(true);expect(result.human_final_video_accepted).toBe(false);
  expect(await readFile(join(root,'timeline-render.json'),'utf8')).not.toContain('http://127.0.0.1');
  await expect(fetch(address)).rejects.toThrow();
});

it('refuses external, cross-job and metadata files before renderer dispatch',async()=>{
  const {root,manifest}=await fixture();
  const engine={render:vi.fn(async()=>undefined)};
  for(const path of ['https://example.invalid/private.mp4',join(root,'private-database.sqlite3'),join(root,'..','another-job.mp4')]){
    manifest.visual_clips[0].uri=path;
    await writeFile(join(root,'timeline-render.json'),JSON.stringify(manifest));
    await expect(renderNativeJob(root,engine)).rejects.toThrow();
  }
  expect(engine.render).not.toHaveBeenCalled();
});

it('does not replace an existing output and closes media server after renderer failure',async()=>{
  const {root}=await fixture();let address='';
  await expect(renderNativeJob(root,{render:vi.fn(async({manifest})=>{
    if(manifest.version==='1.0')throw new Error('timeline required');
    address=manifest.audio.mix_uri;throw new Error('Explicit renderer failure fixture');
  })})).rejects.toThrow('Explicit renderer failure fixture');
  await expect(fetch(address)).rejects.toThrow();
  await writeFile(join(root,'final.mp4'),'KEEP_EXISTING_RENDER');
  const engine={render:vi.fn(async()=>undefined)};
  await expect(renderNativeJob(root,engine)).rejects.toThrow('NATIVE_RENDER_OUTPUT_EXISTS');
  expect(await readFile(join(root,'final.mp4'),'utf8')).toBe('KEEP_EXISTING_RENDER');
  expect(engine.render).not.toHaveBeenCalled();
});

it('rejects a media directory junction that points at private job files',async()=>{
  const {root,manifest}=await fixture();
  const hidden=join(root,'private');await mkdir(hidden);
  const secret=join(hidden,'pretend-video.mp4');await writeFile(secret,'PRIVATE_SCOPE_SENTINEL');
  const link=join(root,'media','junction');await symlink(hidden,link,'junction');
  manifest.visual_clips[0].uri=join(link,'pretend-video.mp4');
  await writeFile(join(root,'timeline-render.json'),JSON.stringify(manifest));
  const engine={render:vi.fn(async()=>undefined)};
  await expect(renderNativeJob(root,engine)).rejects.toThrow('NATIVE_RENDER_MEDIA_SCOPE_INVALID');
  expect(engine.render).not.toHaveBeenCalled();
});
