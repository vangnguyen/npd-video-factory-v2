import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {videoFormat,applyVideoFormat,nextProjectStage} from '../video-preview.mjs';
import {filterAssets,assetCard,projectAssets,assetFacts} from '../asset-picker.mjs';

test('Preview dimensions follow saved portrait/landscape templates and measured MP4 metadata',()=>{
  const portrait={document:{brand_template:{template:{width:1080,height:1920}}}};
  const landscape={document:{brand_template:{template:{width:1920,height:1080}}}};
  assert.equal(videoFormat(portrait).aspect,'9:16');assert.equal(videoFormat(landscape).aspect,'16:9');
  assert.equal(videoFormat(portrait,{width:1920,height:1080}).aspect,'16:9','Measured loaded media governs its own canvas');
  assert.equal(videoFormat(null).label,'9:16 · 1080×1920');
  assert.equal(videoFormat(portrait,{width:NaN,height:0}).aspect,'9:16');
  const style=new Map(),attributes=new Map(),canvas={style:{setProperty:(key,value)=>style.set(key,value)},dataset:{},setAttribute:(key,value)=>attributes.set(key,value)};
  applyVideoFormat(canvas,portrait);assert.equal(canvas.dataset.aspectRatio,'9:16');assert.equal(style.get('--preview-aspect'),'1080 / 1920');
  applyVideoFormat(canvas,landscape);assert.equal(canvas.dataset.aspectRatio,'16:9');assert.equal(Number(style.get('--preview-ratio')),16/9);assert.match(attributes.get('aria-label'),/1920×1080/);
});

test('New media-first project exposes Assets before any proposal or render exists',()=>{
  assert.equal(nextProjectStage({document:{input_kind:'media',assets:[],proposal:null}}),'assets');
  assert.equal(nextProjectStage({document:{input_kind:'prompt',assets:[],proposal:null}}),'script');
  assert.equal(nextProjectStage({document:{proposal:{},assets:[]},script_review:{current:true}}),'assets');
  assert.equal(nextProjectStage({document:{proposal:{},assets:[{id:'asset'}]},script_review:{current:true}}),'storyboard');
});

test('One picker filters original names/types/tags and preserves source objects',()=>{
  const assets=[{id:'a',filename:'Biển Cần Giờ.png',kind:'image',tags:['phối cảnh']},{id:'b',filename:'Dự án.mp4',kind:'video',width:1080,height:1920,duration_seconds:12}];
  const before=JSON.stringify(assets);
  assert.deepEqual(filterAssets(assets,{query:'CẦN GIỜ',kind:'image'}).map(a=>a.id),['a']);
  assert.deepEqual(filterAssets(assets,{query:'phối cảnh',kind:'all'}).map(a=>a.id),['a']);
  assert.deepEqual(filterAssets(assets,{kind:'video'}).map(a=>a.id),['b']);
  assert.equal(JSON.stringify(assets),before);assert.match(assetFacts(assets[1]),/1080×1920.*12.0 giây/);
  assert.deepEqual(projectAssets({document:{asset:assets[0]}}),[assets[0]]);
});

test('Asset cards expose selection, provenance and guarded association removal without HTML injection',()=>{
  const asset={id:'a',filename:'<img onerror="bad()">.png',kind:'image',width:1080,height:1920,rights_confirmed:true,provenance:{source_type:'user_upload'}};
  const card=assetCard(asset,{thumbnail:'/thumbnail',used:true,attached:true});
  assert.doesNotMatch(card,/<img onerror=/);assert.match(card,/&lt;img onerror/);
  assert.match(card,/data-asset-action="remove"[^>]*disabled/);assert.match(card,/Gỡ khỏi dự án giữ nguyên tư liệu thư viện/);
  const selected=assetCard(asset,{thumbnail:'/thumbnail',picker:true,selected:true});assert.match(selected,/data-asset-select="a" checked/);assert.match(selected,/Đã chọn/);
});

test('Legacy Native server never needs new optional UX assets during startup',()=>{
  const source=readFileSync(new URL('../native.mjs',import.meta.url),'utf8'),shots=readFileSync(new URL('../shot-studio.mjs',import.meta.url),'utf8');
  assert.match(source,/session\.capabilities\?\.native_studio_ux===true/);
  assert.doesNotMatch(source,/import\s+[^\n]+from\s+['"]\.\/(asset-picker|video-preview|studio-shell)/);
  assert.doesNotMatch(shots,/import\s+[^\n]+from\s+['"]\.\/(asset-picker|video-preview|studio-shell)/);
});
