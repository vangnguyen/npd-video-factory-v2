import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {initializeNarratedTimeline,validateNarratedTimeline,narratedTimelineMarkup} from '../native-narrated-timeline.mjs';
import {pixelsPerSecond} from '../studio-utils.mjs';
import {visualWindowLabel} from '../shot-studio.mjs';
const video=JSON.parse(readFileSync(new URL('./fixtures/native-narrated-video-timeline.json',import.meta.url),'utf8'));
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-narrated-timeline.json',import.meta.url),'utf8')),copy=v=>structuredClone(v);
function harness(page=fixture.preSettings){
  class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,f){(this.listeners[k]??=[]).push(f);}}
  const card=new Node('details');card.id='native-narrated-timeline-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean),root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)};
  const state={workspace_id:page.workspace_id,project:{id:page.project_id,revision:page.revision,document:{prepared_narration:{fixture:true},canonical_timeline:{snapshot:{metadata:{}}}}},canEdit:true,busy:false,active:false,dirty:false,dirtyPart:null},calls=[],saved=[],messages=[];let respond=async(path,body)=>copy(body?fixture.settings:page),refresh=async()=>{};
  const controller=initializeNarratedTimeline({root,getState:()=>state,api:async(path,body)=>{calls.push({path,body});return respond(path,body);},onWorking:v=>{state.busy=v;},onDirty:v=>{state.dirty=v;state.dirtyPart=v?'narrated_timeline':null;},onSaved:async v=>{saved.push(v);state.project.revision=v.revision;},onRefresh:()=>refresh(),onMessage:(...v)=>messages.push(v)});
  return {card,state,controller,calls,saved,messages,field:id=>root.getElementById('native-narrated-timeline-'+id),respond:fn=>{respond=fn;},refresh:fn=>{refresh=fn;}};
}
function graphEvent(id,track='trk_native_video',seconds=.23){
  const target={dataset:{clip:id},closest:()=>target,getBoundingClientRect:()=>({left:10})},lane={dataset:{track},closest:()=>lane,getBoundingClientRect:()=>({left:10})};
  return {start:{target,clientX:10,preventDefault(){},dataTransfer:{setData(){}}},drop:{target:lane,clientX:10+seconds*pixelsPerSecond(1),preventDefault(){}}};
}
test('captured video controller uses canonical split, drag, speed and undo through signed HTTP',()=>{
  assert.equal(video.actual_signed_HTTP,true);assert.equal(video.fake_DOM,true);assert.equal(video.browser_rendered,false);assert.equal(video.owner_UAT,false);
  assert.equal(video.provider_calls,0);assert.equal(video.actual_graph_drag_controller,true);assert.equal(video.requests.length,11);
  for(const p of [video.initial,video.split,video.dragged,video.speed,video.final])assert.equal(validateNarratedTimeline(p,{workspace_id:p.workspace_id,project:{id:p.project_id,revision:p.revision}}),p);
});
test('video selection sends speed without an audio volume property',async()=>{
  const h=harness(video.dragged);h.respond(async(path,body)=>copy(body?video.speed:video.dragged));await h.controller.load();
  const clip=video.dragged.snapshot.tracks[0].clips[0];h.field('clip').value=clip.clip_id;h.field('operation').value='set_clip_properties';h.field('operation').listeners.change[0]();
  assert.equal(h.field('volume').disabled,true);assert.equal(h.field('speed').disabled,false);h.field('speed').value='2';await h.controller.editClip();
  assert.deepEqual(h.calls[1].body.operations,[{type:'set_clip_properties',clip_id:clip.clip_id,speed:2}]);assert.equal(h.saved.length,1);
});
test('image controls use display duration while source time and playback rate are disabled',async()=>{
  const p=copy(video.split),clip=p.snapshot.tracks[0].clips[0];clip.kind='image';clip.source_start=0;clip.source_end=null;clip.speed=1;
  const h=harness(p);h.respond(async(path,body)=>copy(body?video.dragged:p));await h.controller.load();h.field('clip').value=clip.clip_id;h.field('clip').listeners.change[0]();
  h.field('operation').value='trim';h.field('operation').listeners.change[0]();assert.equal(h.field('source-start').disabled,true);assert.equal(h.field('source-end').disabled,true);
  assert.equal(h.field('image-duration').disabled,false);assert.equal(h.field('speed').disabled,true);h.field('image-duration').value='.6';h.field('start').value='0';await h.controller.editClip();
  assert.deepEqual(h.calls[1].body.operations,[{type:'trim',clip_id:clip.clip_id,duration:.6,timeline_start:0}]);
});
test('graph drag snaps a canonical move with the current version and SHA',async()=>{
  const h=harness(video.split);h.respond(async(path,body)=>copy(body?video.dragged:video.split));await h.controller.load();
  const id=video.split.snapshot.tracks[0].clips[0].clip_id,events=graphEvent(id);await h.field('graph').listeners.dragstart[0](events.start);await h.field('graph').listeners.drop[0](events.drop);
  assert.equal(h.calls[1].body.timeline_sha256,video.split.timeline_sha256);assert.equal(h.calls[1].body.expected_version,video.split.timeline_version);
  assert.deepEqual(h.calls[1].body.operations,[{type:'move',clip_id:id,timeline_start:.25}]);assert.equal(h.saved.length,1);
});
test('graph drag refuses foreign lane, excessive duration and stale, locked, viewer or dirty context',async()=>{
  for(const mode of ['foreign','outside','stale','locked','viewer','dirty','voice-stale','generated']){
    const p=copy(video.split);if(mode==='locked')p.snapshot.tracks[0].locked=true;if(mode==='voice-stale')p.voice_input_current=false;if(mode==='generated')p.snapshot.tracks[0].clips[0].metadata.narrated_generated_voice=true;
    const h=harness(p);await h.controller.load();const id=p.snapshot.tracks[0].clips[0].clip_id,e=graphEvent(id,mode==='foreign'?'trk_narrated_measured_voice':'trk_native_video',mode==='outside'?100:.2);
    await h.field('graph').listeners.dragstart[0](e.start);
    if(mode==='stale')h.state.project.revision++;if(mode==='viewer')h.state.canEdit=false;if(mode==='dirty'){h.state.dirty=true;h.state.dirtyPart='prompt';}
    await h.field('graph').listeners.drop[0](e.drop);assert.equal(h.calls.length,1,mode);assert.equal(h.saved.length,0,mode);
  }
});
test('default shot label describes actual advanced windows and does not infer them for legacy projects',()=>{
  assert.equal(visualWindowLabel({duration:3.3}),'');assert.match(visualWindowLabel({advanced_visual_windows:[]}),/Chưa có clip tư liệu/);
  const windows=video.final.snapshot.tracks[0].clips;assert.match(visualWindowLabel({advanced_visual_windows:windows}),new RegExp(windows.length+' clip tư liệu'));
  assert.match(narratedTimelineMarkup(video.final),/data-track="trk_native_video"/);
});
test('captured real signed HTTP controller pages preserve qualification and closed finite timeline scope',()=>{
  assert.equal(fixture.actual_signed_HTTP,true);assert.equal(fixture.fake_DOM,true);assert.equal(fixture.synthetic_tones_not_speech,true);assert.equal(fixture.owner_UAT,false);assert.equal(fixture.browser_rendered,false);assert.equal(fixture.provider_calls,0);
  assert.equal(fixture.requests.length,9);for(const name of['initial','preSettings','settings','undo','redo','split']){const v=fixture[name];assert.equal(validateNarratedTimeline(v,{workspace_id:v.workspace_id,project:{id:v.project_id,revision:v.revision}}),v);}
});
test('controller initialization is inert and settings save the same canonical binding with Vietnamese keywords',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();h.field('duck').checked=false;h.field('keywords').value='Vang Nguyễn, Cần Giờ';h.field('keywords').listeners.input[0]();assert.equal(h.state.dirtyPart,'narrated_timeline');
  await h.controller.configure();assert.equal(h.saved.length,1,JSON.stringify(h.messages));assert.equal(h.calls[1].body.timeline_sha256,fixture.preSettings.timeline_sha256);assert.equal(h.calls[1].body.expected_version,fixture.preSettings.timeline_version);
  assert.deepEqual(h.calls[1].body.keywords,['Vang Nguyễn','Cần Giờ']);assert.equal(h.calls[1].body.audio_processing.duck_music,false);assert.equal(h.state.dirty,false);assert.equal(h.controller.currentBinding().timeline_version,fixture.settings.timeline_version);
});
test('undo and redo use immutable actual target revisions and source digests with new current versions',async()=>{
  const h=harness(fixture.settings);let undone=false;h.respond(async(path,body)=>{if(!body)return copy(fixture.settings);const v=undone?fixture.redo:fixture.undo;undone=true;return copy(v);});await h.controller.load();await h.controller.restore('undo');await h.controller.restore('redo');
  assert.equal(h.saved.length,2,JSON.stringify(h.messages));assert.equal(h.calls[1].body.restore_revision,fixture.preSettings.revision);assert.equal(h.calls[1].body.restore_timeline_sha256,fixture.preSettings.timeline_sha256);
  assert.equal(h.calls[2].body.restore_revision,fixture.settings.revision);assert.equal(h.calls[2].body.expected_version,fixture.undo.timeline_version);assert.equal(h.controller.currentBinding().timeline_sha256,fixture.redo.timeline_sha256);
});
test('track lock mute and imported split operations use closed canonical requests and source roles',async()=>{
  const h=harness();await h.controller.load();h.field('track').value='trk_narrated_measured_voice';await h.controller.trackState('muted');assert.deepEqual(h.calls[1].body.operations,[{type:'set_track_state',track_id:'trk_narrated_measured_voice',muted:true}]);
  const split=harness(fixture.redo);split.respond(async(path,body)=>copy(body?fixture.split:fixture.redo));await split.controller.load();const clip=fixture.redo.snapshot.tracks.find(t=>t.kind==='voice'&&t.track_id!=='trk_narrated_measured_voice').clips[0];split.field('clip').value=clip.clip_id;split.field('operation').value='split';split.field('snap').checked=false;split.field('playhead').value='1.5';await split.controller.editClip();assert.deepEqual(split.calls[1].body.operations,[{type:'split',clip_id:clip.clip_id,at_seconds:1.5}]);assert.equal(split.saved.length,1);
});
test('viewer unrelated dirty form active jobs archive and parent busy fence all write methods',async()=>{
  for(const flag of['viewer','dirty','active','archived','busy']){const h=harness();if(flag==='viewer')h.state.canEdit=false;else if(flag==='dirty'){h.state.dirty=true;h.state.dirtyPart='prompt';}else if(flag==='archived')h.state.project.archived=true;else h.state[flag]=true;
    await h.controller.load();const count=h.calls.length;await h.controller.configure();await h.controller.editClip();await h.controller.trackState('muted');await h.controller.restore('undo');assert.equal(h.calls.length,count,flag);assert.equal(h.saved.length,0);}
});
test('late project workspace revision and role changes never install private timeline content',async()=>{
  for(const flag of['project','workspace','revision','role']){const h=harness();let release;h.respond(()=>new Promise(r=>{release=r;}));const pending=h.controller.load();if(flag==='project')h.state.project.id='a'.repeat(32);else if(flag==='workspace')h.state.workspace_id='foreign';else if(flag==='revision')h.state.project.revision++;else h.state.canEdit=false;h.controller.sync();release(copy(fixture.preSettings));await pending;assert.equal(h.controller.currentBinding(),null);assert.equal(h.field('graph').innerHTML,'');assert.equal(h.field('keywords').value,'');}
});
test('malformed stale foreign secret or non-finite DTOs fail before enabling editing',()=>{
  const p=fixture.preSettings,s={workspace_id:p.workspace_id,project:{id:p.project_id,revision:p.revision}};
  for(const change of[v=>v.project_id='foreign',v=>v.revision++,v=>v.provider_calls=1,v=>v.publishing_enabled=true,v=>v.snapshot.tracks[0].locked='false',v=>v.snapshot.tracks[0].clips[0].duration=Infinity,v=>v.history[0].sha256='bad',v=>v.access_token='NEVER',v=>v.snapshot.metadata.native_project_id='foreign']){const bad=copy(p);change(bad);assert.throws(()=>validateNarratedTimeline(bad,s));}
});
test('uncertain mutation is not repeated and requires reading current durable history',async()=>{
  const h=harness();await h.controller.load();h.respond(async()=>{throw Error('Owned response-loss fixture');});await h.controller.configure();await h.controller.configure();assert.equal(h.calls.length,2);assert.equal(h.saved.length,0);assert.equal(h.controller.currentBinding(),null);assert.equal(h.field('graph').innerHTML,'');
});
test('explicit reread after an uncertain write refreshes the parent revision without sending another mutation',async()=>{
  const h=harness();await h.controller.load();h.respond(async()=>{throw Error('Owned lost response');});await h.controller.configure();assert.equal(h.controller.currentBinding(),null);
  let refreshed=0;h.refresh(async()=>{refreshed++;h.state.project.revision=fixture.settings.revision;});h.respond(async()=>copy(fixture.settings));await h.controller.load();assert.equal(refreshed,1);assert.equal(h.controller.currentBinding().timeline_version,fixture.settings.timeline_version);assert.equal(h.calls.filter(c=>c.body).length,1);assert.equal(h.saved.length,0);
});
test('dirty clip and mix forms cannot discard each other through another save action',async()=>{
  for(const kind of['clip','settings']){const h=harness();await h.controller.load();if(kind==='clip'){h.field('start').listeners.input[0]();await h.controller.configure();assert.equal(h.field('save-settings').disabled,true);}else{h.field('keywords').listeners.input[0]();await h.controller.editClip();assert.equal(h.field('save-clip').disabled,true);}assert.equal(h.calls.length,1);assert.equal(h.state.dirty,true);}
});
test('word caption templates are visibly unavailable without measured word evidence',async()=>{
  const h=harness();await h.controller.load();const refs=fixture.preSettings.subtitle_templates.templates.filter(t=>t.requires_word_timestamps).map(t=>t.template_ref);assert.ok(refs.length);
  for(const ref of refs){const option=h.field('template').children.find(o=>o.value===ref);assert.equal(option.disabled,true);assert.ok(option.textContent.includes('cần thời gian từng từ'));}
});
test('changed measured speech input disables new audio edits while keeping exact history restoration available',async()=>{
  const page=copy(fixture.settings);page.voice_input_current=false;const h=harness(page);h.respond(async(path,body)=>copy(body?fixture.undo:page));await h.controller.load();assert.equal(h.field('save-settings').disabled,true);
  await h.controller.configure();await h.controller.trackState('muted');assert.equal(h.calls.length,1);await h.controller.restore('undo');assert.equal(h.saved.length,1,JSON.stringify(h.messages));assert.ok(h.calls[1].path.endsWith('/restore'));
});
test('timeline graph shares measured uploaded waveform zoom and playhead with escaped labels',()=>{
  const page=copy(fixture.preSettings),t=page.snapshot.tracks.find(t=>t.kind==='voice'&&t.track_id!=='trk_narrated_measured_voice');t.clips[0].label='<svg onload="NEVER">';const html=narratedTimelineMarkup(page,2,1);
  assert.ok(html.includes('&lt;svg onload=&quot;NEVER&quot;&gt;'));assert.ok(!html.includes('<svg onload='));assert.ok(html.includes('Biên độ âm thanh đo từ nguồn'));assert.ok(html.includes('left:68px'));assert.ok(html.includes('narrated-playhead'));
});
