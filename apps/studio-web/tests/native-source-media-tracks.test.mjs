import test from 'node:test';import assert from 'node:assert/strict';import{readFileSync}from'node:fs';
import{initializeSourceMediaTracks,validateSourceMediaTracks}from'../native-source-media-tracks.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/native-source-media-tracks.json',import.meta.url),'utf8')),copy=v=>structuredClone(v);
const narratedFixture=JSON.parse(readFileSync(new URL('./fixtures/native-narrated-media-tracks.json',import.meta.url),'utf8'));
const mappedFixture=JSON.parse(readFileSync(new URL('./fixtures/native-source-caption-mapping.json',import.meta.url),'utf8'));
function harness(page=fixture.initial){
  class Node{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.value='';this.checked=false;}
    append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}}
  const card=new Node('details');card.id='native-source-media-tracks-card';const walk=(n,id)=>n.id===id?n:n.children.map(c=>walk(c,id)).find(Boolean),root={getElementById:id=>walk(card,id),createElement:t=>new Node(t)};
  const state={workspace_id:page.workspace_id,project:{id:page.project_id,revision:page.revision},canEdit:true,busy:false,dirty:false,dirtyPart:null,active:false};
  const calls=[],saved=[],messages=[],dirty=[];let respond=async(path,body)=>copy(body?fixture.audio:page);
  const controller=initializeSourceMediaTracks({root,getState:()=>state,api:async(path,body)=>{calls.push({path,body});return respond(path,body);},requestKey:()=> 'explicit-source-track-fixture-key',
    onWorking:v=>{state.busy=v;},onDirty:v=>{dirty.push(v);state.dirty=v;state.dirtyPart=v?'source_media_tracks':null;},onMessage:(...v)=>messages.push(v),onSaved:async v=>{saved.push(v);state.project.revision=v.revision;}});
  const node=n=>root.getElementById('native-source-media-tracks-'+n);
  return{card,state,controller,calls,saved,messages,dirty,node,respond:fn=>{respond=fn;}};
}
test('actual signed HTTP fixtures retain honest local/media/mock qualification and validate all stages',()=>{
  assert.equal(fixture.fixture_human,true);assert.equal(fixture.saved_ASR_fixture,true);assert.equal(fixture.actual_local_media_waveform,true);assert.equal(fixture.real_provider_calls,0);assert.equal(fixture.owner_UAT,false);assert.equal(fixture.browser_rendered,false);
  for(const name of['initial','audio','subtitles','edited','reopened']){const p=fixture[name];assert.equal(validateSourceMediaTracks(p,{workspace_id:p.workspace_id,project:{id:p.project_id,revision:p.revision}}),p);}
});
test('initialization is inert and audio placement uses the read source and canonical timeline binding',async()=>{
  const h=harness();assert.equal(h.calls.length,0);await h.controller.load();assert.equal(h.controller.fields.size,2);
  h.node('timeline-start').value='.5';await h.controller.applyAudio();assert.equal(h.saved.length,1,JSON.stringify(h.messages));const b=h.calls[1].body;
  assert.equal(b.asset_id,fixture.initial.assets[0].asset_id);assert.equal(b.asset_sha256,fixture.initial.assets[0].asset_sha256);assert.equal(b.timeline_sha256,fixture.initial.timeline_sha256);
  assert.equal(b.timeline_start,.5);assert.equal(b.source_start,0);assert.equal(b.source_end,2);assert.equal(b.role,'voice');assert.equal(b.captions,null);assert.equal(h.controller.currentBinding().timeline_version,fixture.audio.timeline_version);
});
test('SRT import explicitly selects the existing caption track and finite template with no word timing fiction',async()=>{
  const h=harness(fixture.audio);h.respond(async(path,body)=>copy(body?fixture.subtitles:fixture.audio));await h.controller.load();await h.controller.applySubtitles();
  assert.equal(h.saved.length,1,JSON.stringify(h.messages));const b=h.calls[1].body;assert.equal(b.replace_track_id,fixture.subtitles.mutation.track_id);assert.equal(b.timebase,'timeline');assert.equal(b.offset_seconds,0);assert.equal(b.trim_to_timeline,false);
  assert.equal(b.subtitle_template_ref,'sentence-clean@v1');assert.equal(h.controller.currentBinding().captions[0].has_word_timing,false);
});
test('caption editor retains UTF8 plain text and saves timing through the same canonical version',async()=>{
  const h=harness(fixture.subtitles);h.respond(async(path,body)=>copy(body?fixture.edited:fixture.subtitles));await h.controller.load();const f=[...h.controller.fields.values()][0];f.text.value=fixture.edited.captions[0].text;f.start.value='.2';f.duration.value='.7';f.text.listeners.input[0]();
  assert.equal(h.state.dirtyPart,'source_media_tracks');await h.controller.saveCaptionEdits();assert.equal(h.saved.length,1,JSON.stringify(h.messages));assert.equal(h.calls[1].body.expected_version,fixture.subtitles.timeline_version);
  assert.equal(h.calls[1].body.edits[0].text,fixture.edited.captions[0].text);assert.equal(h.state.dirty,false);assert.equal(h.node('caption-rows').innerHTML,undefined);
});
test('viewer, unrelated dirty form, active job and archive prevent writes through controller methods',async()=>{
  for(const flag of['viewer','dirty','active','archived']){const h=harness();if(flag==='viewer')h.state.canEdit=false;else if(flag==='dirty'){h.state.dirty=true;h.state.dirtyPart='prompt';}else if(flag==='active')h.state.active=true;else h.state.project.archived=true;
    await h.controller.load();await h.controller.applyAudio();await h.controller.applySubtitles();await h.controller.saveCaptionEdits();assert.equal(h.calls.length,1,flag);assert.equal(h.saved.length,0);}
});
test('foreign/stale/privacy/invalid source or pagination DTO never installs editable tracks',()=>{
  const page=fixture.initial,s={workspace_id:page.workspace_id,project:{id:page.project_id,revision:page.revision}};
  for(const change of[v=>v.workspace_id='foreign',v=>v.revision++,v=>v.timeline_sha256='bad',v=>v.provider_calls=1,v=>v.publishing_enabled=true,v=>v.assets[0].asset_sha256='bad',v=>v.assets[0].transcript_id='trn_missing',
    v=>v.tracks[0].locked='false',v=>v.captions[0].duration=600,v=>v.captions_total++,v=>v.access_token='NEVER']){const bad=copy(page);change(bad);assert.throws(()=>validateSourceMediaTracks(bad,s));}
});
test('late response after changing project is discarded and prior caption text is cleared',async()=>{
  const h=harness();await h.controller.load();let resolve;h.respond(()=>new Promise(r=>{resolve=r;}));const read=h.controller.load();await Promise.resolve();h.state.project={id:'a'.repeat(32),revision:1};h.controller.sync();
  assert.equal(h.controller.fields.size,0);assert.equal(h.node('caption-rows').children.length,0);resolve(copy(fixture.initial));await read;assert.equal(h.controller.currentBinding(),null);assert.equal(h.saved.length,0);
});
test('lost mutation response keeps exactly one frozen request key and retries the same intent',async()=>{
  const h=harness();await h.controller.load();h.node('timeline-start').value='.5';let sent=false;
  h.respond(async()=>{if(!sent){sent=true;throw Error('Explicit fixture observation lost');}return{...copy(fixture.audio),mutation:{...fixture.audio.mutation,replayed:true}};});
  await h.controller.applyAudio();await h.controller.applyAudio();assert.equal(h.calls.length,3);assert.deepEqual(h.calls[1].body,h.calls[2].body);assert.equal(h.saved.length,1,JSON.stringify(h.messages));
});
test('wrong source or receipt interval cannot reload the project as a successful write',async()=>{
  for(const change of[v=>v.mutation.asset_id=fixture.initial.assets[1].asset_id,v=>v.mutation.asset_sha256='a'.repeat(64),v=>v.mutation.timeline_window[1]=3,v=>v.mutation.clip_ids=['clip_wrong','clip_wrong']]){
    const h=harness();await h.controller.load();h.node('timeline-start').value='.5';const bad=copy(fixture.audio);change(bad);h.respond(async()=>bad);await h.controller.applyAudio();assert.equal(h.saved.length,0);assert.ok(h.messages.length);}
});
test('caption pagination is an explicit read and out-of-range input cannot dispatch',async()=>{
  const h=harness();await h.controller.load();const p={...copy(fixture.initial),caption_page:2,captions:[],captions_has_next:false};h.respond(async()=>p);await h.controller.load(2);
  assert.match(h.calls[1].path,/\?caption_page=2$/);assert.equal(h.controller.fields.size,0);await assert.rejects(h.controller.load(0));assert.equal(h.calls.length,2);
});
test('measured storyboard signed HTTP fixtures remain distinct from ASR, provider, browser and Owner acceptance',()=>{
  assert.equal(narratedFixture.synthetic_measured_narration_fixture,true);assert.equal(narratedFixture.saved_ASR_fixture,false);assert.equal(narratedFixture.owner_UAT,false);assert.equal(narratedFixture.real_provider_calls,0);
  for(const name of['initial','audio','subtitles','edited','reopened']){const p=narratedFixture[name];assert.equal(p.timeline_mode,'narrated');assert.equal(validateSourceMediaTracks(p,{workspace_id:p.workspace_id,project:{id:p.project_id,revision:p.revision}}),p);}
});
test('storyboard projection reads measured captions and audio placement seeds through the same canonical CAS',async()=>{
  const h=harness(narratedFixture.initial);h.respond(async(path,body)=>copy(body?narratedFixture.audio:narratedFixture.initial));await h.controller.load();
  assert.equal(h.controller.currentBinding().pending_generated_tracks,true);assert.equal(h.node('timebase').value,'timeline');assert.equal(h.node('timebase').disabled,true);
  assert.match(h.node('status').textContent,/PCM đã đo/);assert.equal(h.controller.fields.size,2);assert.equal(h.calls.length,1);
  h.node('timeline-start').value='.5';await h.controller.applyAudio();assert.equal(h.saved.length,1,JSON.stringify(h.messages));assert.equal(h.controller.currentBinding().pending_generated_tracks,false);
  assert.equal(h.calls[1].body.timeline_sha256,narratedFixture.initial.timeline_sha256);assert.equal(h.calls[1].body.expected_version,narratedFixture.initial.timeline_version);
});
test('storyboard imported caption edit keeps Vietnamese text and cannot manufacture word alignment',async()=>{
  const h=harness(narratedFixture.subtitles);h.respond(async(path,body)=>copy(body?narratedFixture.edited:narratedFixture.subtitles));await h.controller.load();
  const f=[...h.controller.fields.values()][0];f.text.value=narratedFixture.edited.captions[0].text;f.start.value='.2';f.duration.value='.7';f.text.listeners.input[0]();
  await h.controller.saveCaptionEdits();assert.equal(h.saved.length,1,JSON.stringify(h.messages));assert.equal(h.controller.currentBinding().captions[0].has_word_timing,false);assert.equal(h.state.dirty,false);
  for(const v of['external','mode-a-ready']){const bad=copy(narratedFixture.initial);bad.timeline_mode=v;assert.throws(()=>validateSourceMediaTracks(bad,h.state));}
});

test('actual source-video mapping HTTP fixture remains distinct from ASR, browser and Owner acceptance',()=>{
  assert.equal(mappedFixture.source_video_mapping,true);assert.equal(mappedFixture.fake_DOM,true);assert.equal(mappedFixture.saved_ASR_fixture,false);assert.equal(mappedFixture.owner_UAT,false);assert.equal(mappedFixture.browser_rendered,false);assert.equal(mappedFixture.real_provider_calls,0);
  for(const name of['initial','audio','music','subtitles','edited','reopened']){const v=mappedFixture[name];assert.equal(validateSourceMediaTracks(v,{workspace_id:v.workspace_id,project:{id:v.project_id,revision:v.revision}}),v);}
  assert.equal(mappedFixture.subtitles.captions.length,4);assert.ok(mappedFixture.subtitles.captions.every(c=>c.source_video_mapping_mode==='follow_video'&&!c.has_word_timing));
});

test('source-clock storyboard import requires an explicit loaded video and binds both video and SRT hashes',async()=>{
  const h=harness(mappedFixture.music);h.respond(async(path,body)=>copy(body?mappedFixture.subtitles:mappedFixture.music));await h.controller.load();
  assert.equal(h.node('timebase').disabled,false);assert.equal(h.node('source-video').hidden,true);h.node('timebase').value='source';for(const f of h.node('timebase').listeners.change)f();
  assert.equal(h.node('source-video').hidden,false);assert.equal(h.node('save-subtitle').disabled,true);await h.controller.applySubtitles();assert.equal(h.calls.length,1);assert.match(h.messages[0][0],/Chọn video/);
  const video=mappedFixture.music.source_video_assets[0];h.node('source-video').value=video.asset_id;for(const f of h.node('source-video').listeners.change)f();await h.controller.applySubtitles();
  assert.equal(h.saved.length,1,JSON.stringify(h.messages));const b=h.calls[1].body;assert.equal(b.source_video_asset_id,video.asset_id);assert.equal(b.source_video_asset_sha256,video.asset_sha256);assert.equal(b.timebase,'source');
  assert.equal(b.timeline_sha256,mappedFixture.music.timeline_sha256);assert.equal(b.asset_id,mappedFixture.subtitles.mutation.asset_id);assert.equal(b.asset_sha256,mappedFixture.subtitles.mutation.asset_sha256);
  assert.equal(h.state.dirty,false);assert.match(h.node('caption-rows').children[0].children[0].textContent,/theo các đoạn video nguồn/);
});

test('legacy Source mode and timeline-clock storyboard requests retain historical payloads without a video binding',async()=>{
  for(const page of[fixture.audio,mappedFixture.music]){const h=harness(page);h.respond(async()=>copy(page));await h.controller.load();h.node('source-video').value='a'.repeat(32)+'.mp4';await h.controller.applySubtitles();
    const body=h.calls[1].body;assert.equal(body.timebase,'timeline');assert.equal('source_video_asset_id'in body,false);assert.equal('source_video_asset_sha256'in body,false);}
});

test('foreign video hashes or mapping receipt schema never install a claimed successful source mapping',async()=>{
  for(const change of[v=>v.mutation.source_video_asset_id='a'.repeat(32)+'.mp4',v=>v.mutation.source_video_asset_sha256='a'.repeat(64),v=>v.mutation.mapping_schema='unapproved']){
    const h=harness(mappedFixture.music);await h.controller.load();h.node('timebase').value='source';h.node('source-video').value=mappedFixture.source_video_asset_id;const bad=copy(mappedFixture.subtitles);change(bad);h.respond(async()=>bad);
    await h.controller.applySubtitles();assert.equal(h.saved.length,0);assert.match(h.messages[0][0],/Video ánh xạ/);}
});

test('bounded source-video DTO and honest caption mapping mode reject malformed, incomplete or private metadata',()=>{
  const page=mappedFixture.subtitles,s={workspace_id:page.workspace_id,project:{id:page.project_id,revision:page.revision}};
  for(const change of[v=>delete v.source_video_assets,v=>v.source_video_assets_total++,v=>v.source_video_mapping_available=false,v=>v.source_video_assets[0].asset_sha256='bad',
    v=>v.source_video_assets.push(copy(v.source_video_assets[0])),v=>v.source_video_assets[0].duration_seconds=Infinity,v=>v.source_video_assets[0].access_token='NEVER',
    v=>v.captions[0].source_video_mapping_mode='disabled',v=>v.captions[0].source_video_mapping_mode='AI-aligned',v=>v.captions[0].source_video_asset_id=null]){const bad=copy(page);change(bad);assert.throws(()=>validateSourceMediaTracks(bad,s));}
});

test('caption cards disclose manual positions and keep source evidence without claiming word alignment',async()=>{
  const h=harness(mappedFixture.edited);await h.controller.load();assert.match(h.node('caption-rows').children[0].children[0].textContent,/vị trí thủ công/);
  assert.ok(h.controller.currentBinding().captions.every(c=>c.source_video_mapping_mode==='human_layout'&&!c.has_word_timing));
});

test('project changes discard selected video and late mapping response without carrying old source text into a new project',async()=>{
  const h=harness(mappedFixture.music);await h.controller.load();h.node('timebase').value='source';h.node('source-video').value=mappedFixture.source_video_asset_id;
  let resolve;h.respond(()=>new Promise(r=>{resolve=r;}));const save=h.controller.applySubtitles();await Promise.resolve();h.state.project={id:'a'.repeat(32),revision:1};h.controller.sync();
  assert.equal(h.node('source-video').children.length,0);assert.equal(h.controller.fields.size,0);resolve(copy(mappedFixture.subtitles));await save;assert.equal(h.controller.currentBinding(),null);assert.equal(h.saved.length,0);
});

test('lost source mapping response retains the exact frozen source-video, SRT and timeline request binding on retry',async()=>{
  const h=harness(mappedFixture.music);await h.controller.load();h.node('timebase').value='source';h.node('source-video').value=mappedFixture.source_video_asset_id;let lost=false;
  h.respond(async()=>{if(!lost){lost=true;throw Error('Owned fixture observation lost');}const v=copy(mappedFixture.subtitles);v.mutation.replayed=true;return v;});
  await h.controller.applySubtitles();await h.controller.applySubtitles();assert.deepEqual(h.calls[1].body,h.calls[2].body);assert.equal(h.saved.length,1,JSON.stringify(h.messages));
});
