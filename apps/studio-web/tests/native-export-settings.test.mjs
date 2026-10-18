import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {applyNativeExportSettings,canConfigureExport} from '../native-export-settings.mjs';
const choice={profile:'vertical-short',fps:24,quality_preset:'high',audio_included:true,burn_subtitles:false};
const project=()=>({id:'a'.repeat(32),revision:8,document:{prepared_narration:{job_id:'saved-voice'},canonical_timeline:{version:3,sha256:'b'.repeat(64),snapshot:{aspect_ratio:'9:16',fps:30,metadata:{}}},brand_template:{brand:{id:'npd'},template:{id:'personal-30',aspect_ratio:'9:16'}}}});
test('narrated settings reuse measured voice and strict current canonical binding',async()=>{
 const p=project(),calls=[];assert.equal(canConfigureExport(p),true);
 await applyNativeExportSettings({project:p,choice,api:async(...args)=>calls.push(args)});
 assert.deepEqual(calls,[[`/api/projects/${p.id}/narrated-timeline/configure`,{revision:8,expected_version:3,timeline_sha256:'b'.repeat(64),fps:24,quality_preset:'high',audio_included:true,burn_subtitles:false}]]);
});
test('source settings use same canonical configure endpoint',async()=>{
 const p=project(),calls=[];delete p.document.prepared_narration;p.document.canonical_timeline.snapshot.metadata.native_auto_edit_schema='source';
 await applyNativeExportSettings({project:p,choice,api:async(...args)=>calls.push(args)});
 assert.equal(calls[0][0],`/api/projects/${p.id}/auto-edit/timeline`);assert.equal(calls[0][1].payload.expected_version,3);assert.equal(calls[0][1].payload.fps,24);
});
test('format change waits for saved project revision before applying output options',async()=>{
 const p=project(),calls=[],next=structuredClone(p);next.revision=9;next.document.canonical_timeline.version=4;next.document.canonical_timeline.sha256='c'.repeat(64);
 await applyNativeExportSettings({project:p,choice:{...choice,profile:'landscape'},api:async(...args)=>{calls.push(args);return next;}});
 assert.equal(calls[0][1].template_id,'personal-30-landscape');assert.equal(calls[1][1].revision,9);assert.equal(calls[1][1].timeline_sha256,'c'.repeat(64));
});
test('failed format save never submits second mutation',async()=>{
 const calls=[];await assert.rejects(applyNativeExportSettings({project:project(),choice:{...choice,profile:'square'},api:async(...args)=>{calls.push(args);throw Error('VERSION_CHANGED');}}),/VERSION_CHANGED/);
 assert.equal(calls.length,1);
});
test('unprepared project cannot dispatch narrated settings or invent a voice',async()=>{
 const p=project(),calls=[];delete p.document.prepared_narration;assert.equal(canConfigureExport(p),false);
 await assert.rejects(applyNativeExportSettings({project:p,choice,api:async(...args)=>calls.push(args)}),/Chuẩn bị giọng/);assert.equal(calls.length,0);
});
test('focused Native runtime defers platform consoles while preserving modules',()=>{
 const text=readFileSync(new URL('../native.mjs',import.meta.url),'utf8');
 for(const name of ['native_analytics_review','native_official_account_review','native_publication_review','native_official_publication_review'])assert.ok(text.includes(`native_manual_delivery_focus!==true&&session.capabilities?.${name}`));
});
