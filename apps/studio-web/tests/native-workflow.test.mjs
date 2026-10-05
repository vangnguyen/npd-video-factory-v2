import {test} from 'node:test';
import assert from 'node:assert/strict';
import {jobActive,currentVideo,canRender,mediaLibrary,mediaBindings,mediaReady,mediaType,documentType,mediaAnalysisPending,defaultSceneOptions,musicType} from '../native.mjs';

test('Render UI requires current approval, saved edits and idle job',()=>{
  const p={revision:3,approval:{revision:3},jobs:[]};
  assert.equal(canRender(p,false,false),true);
  for(const value of [null,{...p,approval:null},{...p,approval:{revision:2}},{...p,jobs:[{status:'running'}]},{...p,jobs:[{status:'queued'}]}])assert.equal(canRender(value,false,false),false);
  assert.equal(canRender(p,true,false),false);assert.equal(canRender(p,false,true),false);
});
test('Each scene requires one source from its project library',()=>{
  const doc={assets:[{id:'photo',kind:'image'},{id:'clip',kind:'video'}],proposal:{visual_brief:[{scene:1},{scene:2},{scene:3}]},scene_media:[{scene:1,asset_id:'photo'},{scene:2,asset_id:'clip'},{scene:3,asset_id:'photo'}]};
  assert.equal(mediaReady(doc),true);
  assert.equal(mediaReady({...doc,scene_media:doc.scene_media.slice(0,2)}),false);
  assert.equal(mediaReady({...doc,scene_media:[doc.scene_media[0],doc.scene_media[0],doc.scene_media[2]]}),false);
  assert.equal(mediaReady({...doc,scene_media:doc.scene_media.map(b=>({...b,asset_id:'foreign'}))}),false);
  assert.equal(mediaReady(null),false);
});
test('Legacy image projects retain all scene choices without rewriting snapshot',()=>{
  const doc={asset:{id:'legacy'},proposal:{visual_brief:[{scene:1},{scene:2},{scene:3}]}};
  const before=JSON.stringify(doc);
  assert.equal(mediaLibrary(doc)[0].kind,'image');assert.equal(mediaBindings(doc).length,3);assert.equal(mediaReady(doc),true);
  assert.equal(JSON.stringify(doc),before);
});
test('Local multi-file selection accepts only supported image and video extensions',()=>{
  for(const [name,type] of [['Ảnh.JPG','image/jpeg'],['a.png','image/png'],['clip.MP4','video/mp4'],['phone.MOV','video/quicktime']])assert.equal(mediaType({name}),type);
  assert.equal(mediaType({name:'playlist.m3u8'}),'');
});
test('Only successful video bound to current approved version is visible',()=>{
  const p={revision:3,approval:{revision:3},jobs:[{kind:'render',status:'succeeded',revision:2},{kind:'render',status:'succeeded',revision:3}]};
  assert.equal(currentVideo(p).revision,3);
  assert.equal(currentVideo({...p,approval:null}),null);
  assert.equal(jobActive({...p,jobs:[{status:'failed'}]}),false);
});
test('Retrying job blocks editing and another render until its receipt completes',()=>{
  const p={revision:3,approval:{revision:3},jobs:[{status:'retrying'}]};
  assert.equal(jobActive(p),true);
  assert.equal(canRender(p,false,false),false);
});
test('Document chooser passes declared MIME while server must validate actual content',()=>{
  for(const name of ['brief.TXT','notes.md','source.docx'])assert.ok(documentType({name}));
  assert.equal(documentType({name:'binary.exe'}),'');
  assert.equal(documentType({name:'source.pdf'}),'');
});
test('Changed source needs new analysis while existing source keeps its result',()=>{
  const doc={assets:[{id:'clip',kind:'video',sha256:'source-a'}],media_analysis:[{asset_id:'clip',source_sha256:'source-a'}]};
  assert.equal(mediaAnalysisPending(doc),false);
  assert.equal(mediaAnalysisPending({...doc,assets:[{id:'clip',kind:'video',sha256:'source-b'}]}),true);
  assert.equal(mediaAnalysisPending({...doc,media_analysis:[]}),true);
  assert.equal(mediaAnalysisPending(null),false);
});
test('Video/image changes reset incompatible motion and source time',()=>{
  const old={motion:'pan_left',source_start:1.5,crop_strategy:'cover',transition:'fade'};
  assert.deepEqual(defaultSceneOptions(2,{kind:'video'},old),{scene:2,motion:'none',source_start:1.5,crop_strategy:'cover',transition:'fade'});
  assert.equal(defaultSceneOptions(1,{kind:'image'},old).source_start,0);
  assert.equal(defaultSceneOptions(1,{kind:'image'},null).motion,'none');
  assert.equal(musicType({name:'MUSIC.WAV'}),'audio/wav');assert.equal(musicType({name:'music.MP3'}),'audio/mpeg');assert.equal(musicType({name:'bad.mp4'}),'');
});
