import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {supportsShotStudio,loadNativeShotStudio,nativeLegacyLayout} from '../native.mjs';
import {projectShots,shotMutationAllowed,changedShotValues,reorderedShotIds,safeSuggestion,previewLabel,previewTimingLabel,escapeText,scriptReviewAllowed,scriptStageReview,readableSuggestion,boundPreview,currentStudioRender,supportsVoiceQuality,loadVoiceQuality,voiceQualityApplyAllowed,voiceQualityLabel,narratedPreviewReady} from '../shot-studio.mjs';

const project={id:'project',revision:7,archived:false,jobs:[],shot_timeline:{version:3,sha256:'timeline-a',shots:[{shot_id:'s-a',scene:1,visual:'Biển',narration:'Nội dung A',subtitle:'Nội dung A',on_screen_text:'A',asset_id:'asset-a',duration:4,narration_enabled:true,crop_strategy:'contain',motion:'none',source_start:0,transition:'cut'},{shot_id:'s-b',scene:2,duration:5}]}};

test('narrated preview is bound to current canonical edits and audio, with distinct approval eligibility',()=>{
  const p={...project,document:{prepared_narration:{voice_audio_sha256:'voice-a'}}},preview={status:'READY',revision:7,timeline_sha256:'timeline-a',video_url:'/private-fixture-preview',
    audio_mode:'measured_scene_narration_full_effects_preview',preview_profile:'native-narrated-storyboard-preview-v1',final_approval_eligible:true,
    manifest:{schema_version:'native-narrated-storyboard-preview-v1',playable:true,timeline_sha256:'timeline-a',timeline_version:3,source_voice_sha256:'voice-a',new_inference_calls:0,final_render_authorized:false,qc:{passed:true}}};
  assert.equal(boundPreview(p,preview).status,'READY');assert.equal(narratedPreviewReady(p,preview),true);assert.match(previewLabel(preview),/có lời đọc/);assert.match(previewTimingLabel('proxy',preview,p),/đã đo/);
  for(const mutate of [v=>v.final_approval_eligible=false,v=>v.manifest.source_voice_sha256='foreign',v=>v.manifest.final_render_authorized=true,v=>v.manifest.qc.passed=false,v=>v.preview_profile='old']){
    const v=structuredClone(preview);mutate(v);assert.equal(boundPreview(p,v).status,'FAILED');assert.equal(narratedPreviewReady(p,v),false);
  }
  assert.equal(boundPreview(p,{...preview,revision:8}).status,'STALE');assert.equal(boundPreview(project,preview).status,'FAILED');
});
test('narration-only approval never presents a final production render',()=>{
  assert.equal(currentStudioRender({...project,approval:{revision:7,approval_scope:'narration_only'},jobs:[{kind:'render',status:'succeeded',revision:7}]}),null);
});

test('Shot view retains server identities and does not invent editable state for old projects',()=>{
  const before=JSON.stringify(project);
  assert.equal(projectShots(project)[0].shot_id,'s-a');
  assert.deepEqual(projectShots({id:'old',document:{proposal:{visual_brief:[{scene:1}]}}}),[]);
  assert.equal(JSON.stringify(project),before);
});

test('Shot mutation gates reject dirty, busy, archived and active-production projects',()=>{
  assert.equal(shotMutationAllowed(project),true);
  for(const guards of [{dirty:true},{busy:true}])assert.equal(shotMutationAllowed(project,guards),false);
  for(const p of [{...project,archived:true},{...project,shot_timeline:null},{...project,jobs:[{status:'retrying'}]},{...project,jobs:[{status:'running'}]},null])assert.equal(shotMutationAllowed(p),false);
});

test('A narration edit sends only narration and never broadens mutation scope',()=>{
  const shot=projectShots(project)[0];
  const edited={...shot,narration:'Lời đọc mới',unexpected:'ignored'};
  assert.deepEqual(changedShotValues(shot,edited),{narration:'Lời đọc mới'});
  assert.deepEqual(changedShotValues(shot,{...shot}),{});
  assert.throws(()=>changedShotValues(shot,{duration:NaN}),/Thời lượng/);
  assert.throws(()=>changedShotValues(shot,{duration:0}),/Thời lượng/);
  assert.throws(()=>changedShotValues(shot,{source_start:-1}),/bắt đầu/);
});

test('Keyboard reorder retains every stable shot identity exactly once',()=>{
  const shots=projectShots(project);
  assert.deepEqual(reorderedShotIds(shots,'s-a',1),['s-b','s-a']);
  assert.deepEqual(reorderedShotIds(shots,'s-a',-1),['s-a','s-b']);
  assert.deepEqual(reorderedShotIds(shots,'foreign',1),['s-a','s-b']);
  assert.equal(shots[0].shot_id,'s-a');
});

test('AI application requires current binding and a single selected-shot operation with known dependencies',()=>{
  const suggestion={project_id:'project',revision:7,timeline_sha256:'timeline-a',requires_human_apply:true,operation:{type:'update',shot_id:'s-a',values:{duration:4}},affected_shot_ids:['s-a']};
  assert.equal(safeSuggestion(project,'s-a',suggestion,7),true);
  assert.equal(safeSuggestion(project,'s-a',{...suggestion,affected_shot_ids:['s-a','s-b']},7),true);
  assert.equal(safeSuggestion(project,'s-a',suggestion,6),false);
  for(const value of [{...suggestion,project_id:'other-project'},{...suggestion,timeline_sha256:'timeline-b'},{...suggestion,revision:6},{...suggestion,requires_human_apply:false},{...suggestion,affected_shot_ids:['s-a','foreign']},{...suggestion,affected_shot_ids:['s-b']},{...suggestion,affected_shot_ids:['s-a','s-a']},{...suggestion,operation:{type:'delete',shot_id:'s-a'}},{...suggestion,operation:{type:'update',shot_id:'s-b'}}])assert.equal(safeSuggestion(project,'s-a',value,7),false);
});

test('Silent visual proxy labels never imply voice or final acceptance',()=>{
  assert.match(previewLabel({status:'READY',final_approval_eligible:false}),/chưa có giọng đọc/);
  assert.match(previewLabel({status:'STALE'}),/cần tạo lại/);
  assert.match(previewLabel({status:'RUNNING',completed_shots:2,total_shots:5}),/2\/5/);
  assert.match(previewTimingLabel('proxy'),/ước tính/);
  assert.match(previewTimingLabel('proxy'),/chưa tạo hay đo audio/);
  assert.match(previewTimingLabel('final'),/các shot có lời đọc dùng thời lượng audio đo được/);
  assert.equal(escapeText('<img onerror="run()">'),'&lt;img onerror=&quot;run()&quot;&gt;');
});

test('Script-only review requires a saved script, reviewer and an explicit human acknowledgment',()=>{
  const p={...project,document:{proposal:{narration:'Lời đọc đã lưu'}}};
  assert.equal(scriptReviewAllowed(p,{},true,'Owner'),true);
  assert.equal(scriptReviewAllowed(p,{},false,'Owner'),false);
  assert.equal(scriptReviewAllowed(p,{},true,' '),false);
  assert.equal(scriptReviewAllowed(p,{dirty:true},true,'Owner'),false);
  assert.equal(scriptReviewAllowed({...p,jobs:[{status:'running'}]},{},true,'Owner'),false);
  assert.equal(scriptReviewAllowed({...p,document:{}},{},true,'Owner'),false);
  assert.equal(readableSuggestion({duration:4,narration:'Ngắn hơn'},p),'Thời lượng: 4 giây · Lời đọc: Ngắn hơn');
});

test('Legacy current combined approval retains script authority without inventing a script-only review',()=>{
  const p={...project,document:{proposal:{narration:'Lời đọc đã lưu'}},script_review:null,approval:{revision:7,reviewer:'Owner'}};
  assert.equal(scriptStageReview(p).label,'Đã duyệt cùng nội dung');
  assert.match(scriptStageReview(p).detail,/duyệt cùng nội dung và cách dựng/);
  assert.equal(p.script_review,null);
  assert.equal(scriptReviewAllowed(p,{},true,'Owner'),true,'Separate script review remains optional and available');
  for(const invalid of [{...p,archived:true},{...p,approval:{revision:6}},{...p,approval:null,script_review:{current:false}}])assert.equal(scriptStageReview(invalid).label,'Cần duyệt');
  assert.equal(scriptStageReview({...p,approval:null,script_review:{current:true,reviewer:'Editor'}}).label,'Đã duyệt');
  assert.equal(scriptStageReview(null).label,'Bắt đầu');
});

test('A preview from another revision or timeline cannot enter playback',()=>{
  const p={...project,shot_timeline:{...project.shot_timeline,sha256:'timeline-a'}};
  const preview={status:'READY',revision:7,timeline_sha256:'timeline-a',video_url:'/preview',audio_mode:'silent_visual_proxy',final_approval_eligible:false};
  assert.equal(boundPreview(p,preview).video_url,'/preview');
  assert.equal(boundPreview(p,{...preview,revision:6}).status,'STALE');
  assert.equal(boundPreview(p,{...preview,timeline_sha256:'timeline-b'}).video_url,null);
  assert.equal(boundPreview(p,{...preview,final_approval_eligible:true}).status,'FAILED');
});

test('Source proxy playback requires its canonical manifest and labels missing final effects',()=>{
  const p={...project,shot_timeline:{...project.shot_timeline,editing_mode:'source_footage'}};
  const preview={status:'READY',revision:7,timeline_sha256:'timeline-a',video_url:'/source-preview',audio_mode:'canonical_timeline_proxy',preview_profile:'native-source-timeline-proxy-v1',final_approval_eligible:false,manifest:{playable:true,timeline_sha256:'timeline-a',timeline_version:3,final_approval_eligible:false}};
  assert.equal(boundPreview(p,preview).video_url,'/source-preview');
  assert.match(previewLabel(preview),/âm thanh theo timeline/);
  assert.match(previewTimingLabel('proxy',preview),/Chưa dựng phụ đề/);
  for(const changed of [{...preview,manifest:null},{...preview,preview_profile:'old-profile'},{...preview,manifest:{...preview.manifest,timeline_version:2}},{...preview,final_approval_eligible:true}])assert.equal(boundPreview(p,changed).status,'FAILED');
  assert.equal(boundPreview(project,preview).status,'FAILED');
  assert.equal(boundPreview(p,{...preview,audio_mode:'silent_visual_proxy'}).status,'FAILED');
});

test('Studio final review is available only for a current approved active project render',()=>{
  const render={id:'render-a',kind:'render',status:'succeeded',revision:7},p={...project,approval:{revision:7},jobs:[render]};
  assert.equal(currentStudioRender(p),render);
  for(const invalid of [null,{...p,archived:true},{...p,approval:null},{...p,approval:{revision:6}},{...p,jobs:[{...render,revision:6}]},{...p,jobs:[{...render,status:'running'}]}])assert.equal(currentStudioRender(invalid),null);
});

test('The staged shell preserves every legacy native control target without duplicate identities',()=>{
  const html=readFileSync(new URL('../native.html',import.meta.url),'utf8'),native=readFileSync(new URL('../native.mjs',import.meta.url),'utf8');
  const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]),known=new Set(ids);
  assert.equal(known.size,ids.length,'A duplicate identity can connect a legacy handler to the wrong control');
  for(const match of native.matchAll(/\$\("([^"]+)"\)/g))assert.ok(known.has(match[1]),`Missing native target: ${match[1]}`);
  for(const id of ['approve','review-check','render','video','final-watch','approve-final','reject-final','download','shot-editor-form','approve-script-only','script-only-ack'])assert.ok(known.has(id));
  for(const stage of ['script','assets','storyboard','video'])assert.match(html,new RegExp(`data-stage-panel="${stage}"`));
});

test('Old native sessions never request the optional shot module or stylesheet',async()=>{
  let requested=0;const unavailable=async()=>{requested++;throw new Error('404 from old server');};
  for(const session of [{csrf:'old'},{capabilities:{}},{capabilities:{native_shot_studio:false}},{capabilities:{native_shot_studio:'true'}}]){
    assert.equal(supportsShotStudio(session),false);
    assert.equal(await loadNativeShotStudio(session,unavailable),null);
  }
  assert.equal(requested,0);
  const module={initializeShotStudio(){}};
  assert.equal(await loadNativeShotStudio({capabilities:{native_shot_studio:true}},async()=>{requested++;return module;}),module);
  assert.equal(requested,1);
  const source=readFileSync(new URL('../native.mjs',import.meta.url),'utf8'),html=readFileSync(new URL('../native.html',import.meta.url),'utf8');
  assert.doesNotMatch(source,/import\s+[^\n]+from\s+['"]\.\/shot-studio\.mjs['"]/);
  assert.doesNotMatch(html,/<link[^>]+href="\/shot-studio\.css"/);
});

test('Legacy fallback restores the original workspace without moving its render or review controls',()=>{
  const render={id:'render'},review={id:'final-review-panel'},workspace={hidden:true,children:[render,review]},timing={textContent:''},phaseOnly=[{hidden:false},{hidden:false}];
  let removedClass=null,removedStyle=false;
  const dom={body:{classList:{remove:value=>removedClass=value}},querySelector:selector=>selector==='.workspace'?workspace:{remove:()=>removedStyle=true},querySelectorAll:()=>phaseOnly,getElementById:()=>timing};
  nativeLegacyLayout(dom);
  assert.equal(removedClass,'shot-studio');assert.equal(removedStyle,true);
  assert.equal(workspace.hidden,false);assert.deepEqual(workspace.children,[render,review]);
  assert.ok(phaseOnly.every(el=>el.hidden));assert.match(timing.textContent,/Thùy Dung đã khóa/);
});

test('Voice-quality catalog is strictly capability gated and never selects a policy on load',async()=>{
  const catalog={choices:[{id:'warm-scene-context-v1',version:1,sha256:'warm-sha',label:'Thùy Dung · Giọng B (ngữ cảnh)'}],default:{id:null,label:'Thùy Dung · MVP đã nghiệm thu (theo câu)'}};
  const calls=[],api=async(...args)=>{calls.push(args);return catalog;},before=JSON.stringify(project);
  for(const capabilities of [{},{voice_quality_selection:false},{voice_quality_selection:'true'}]){assert.equal(supportsVoiceQuality(capabilities),false);assert.equal(await loadVoiceQuality(api,capabilities),null);}
  assert.deepEqual(calls,[]);
  assert.equal(await loadVoiceQuality(api,{voice_quality_selection:true}),catalog);
  assert.deepEqual(calls,[['/api/voice-quality']],'Catalog read sends no POST body or production request');
  assert.equal(voiceQualityLabel({...project,document:{}},catalog),catalog.default.label);
  assert.equal(JSON.stringify(project),before,'Reading choices leaves the existing preset and default document untouched');
});

test('Applying a known voice-quality policy requires saved idle active project state',()=>{
  const warm={id:'warm-scene-context-v1',version:1,sha256:'warm-sha',label:'Thùy Dung · Giọng B (ngữ cảnh)'},catalog={choices:[warm]},capabilities={voice_quality_selection:true},p={...project,document:{}};
  assert.equal(voiceQualityApplyAllowed(p,capabilities,catalog,warm.id),true);
  for(const guards of [{dirty:true},{busy:true}])assert.equal(voiceQualityApplyAllowed(p,capabilities,catalog,warm.id,guards),false);
  for(const invalid of [null,{...p,archived:true},{...p,jobs:[{status:'running'}]},{...p,jobs:[{status:'retrying'}]}])assert.equal(voiceQualityApplyAllowed(invalid,capabilities,catalog,warm.id),false);
  assert.equal(voiceQualityApplyAllowed(p,{},catalog,warm.id),false);
  assert.equal(voiceQualityApplyAllowed(p,capabilities,catalog,''),false,'Sentence default is display-only and cannot be auto-applied');
  assert.equal(voiceQualityApplyAllowed(p,capabilities,catalog,'unknown'),false);
  const selected={...p,document:{voice_quality:{id:warm.id,version:warm.version,sha256:warm.sha256}}};
  assert.equal(voiceQualityApplyAllowed(selected,capabilities,catalog,warm.id),false,'Existing exact policy is a no-op');
  assert.equal(voiceQualityLabel(selected,catalog),warm.label);
  assert.equal(voiceQualityApplyAllowed({...selected,document:{voice_quality:{...selected.document.voice_quality,sha256:'stale'}}},capabilities,catalog,warm.id),true);
});
