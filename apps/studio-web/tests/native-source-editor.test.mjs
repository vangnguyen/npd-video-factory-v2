import test from 'node:test';
import assert from 'node:assert/strict';
import {isSourceProject,sourceRequest,sourceVersions,sourceClipAction,sourceAdvancedMarkup} from '../native-source-editor.mjs';
import {sourceCreatePayload} from '../native-auto-edit.mjs';
import {timelineHistory} from '../timeline-history.mjs';
import {videoFormat,nextProjectStage} from '../video-preview.mjs';
import {previewTimingLabel} from '../shot-studio.mjs';
import {musicSummary} from '../native.mjs';

const snapshot={width:1080,height:1350,duration_seconds:3,metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1'},tracks:[
  {track_id:'trk_source',kind:'source',type:'video',label:'Source',clips:[{clip_id:'clip_video',label:'<img onerror=x>',timeline_start:0,duration:3}]},
  {track_id:'trk_audio',kind:'original_audio',type:'audio',label:'Audio',muted:false,clips:[{clip_id:'clip_sound',duration:3,timeline_start:0}]}]};
const p={id:'a'.repeat(32),revision:7,document:{input_kind:'media',proposal:null,canonical_timeline:{version:2,sha256:'saved',snapshot}}};
test('Source requests bind both versions and route linked shots vs independent tracks',()=>{
  assert.equal(isSourceProject(p),true);assert.equal(isSourceProject({document:{}}),false);
  const body=sourceClipAction(p,'clip_video','trim',{source_end:2});assert.equal(body.action,'linked_edit');assert.equal(body.payload.operation.clip_id,'clip_video');assert.equal(body.payload.expected_version,2);
  const audio=sourceClipAction(p,'clip_sound','move',{timeline_start:1});assert.equal(audio.action,'edit');assert.equal(audio.payload.operations[0].clip_id,'clip_sound');
  assert.equal(sourceRequest(p,'configure',{expected_version:999,aspect_ratio:'4:5'}).payload.expected_version,2);
  assert.throws(()=>sourceClipAction(p,'foreign','delete'),/đã thay đổi/);
  assert.throws(()=>sourceRequest({...p,archived:true},'edit'),/đang hoạt động/);
});
test('Native history deduplicates approval revisions and undo/redo survive restore-as-new',()=>{
  const record=(revision,version,mutation)=>({revision,document:{canonical_timeline:{version,snapshot},source_timeline_mutations:[{version,mutation}]}});
  const versions=sourceVersions([record(1,1,{type:'edit'}),record(2,2,{type:'edit'}),record(3,2,{type:'edit'}),record(4,3,{type:'restore',restored_from_version:1})]);
  assert.deepEqual(versions.map(v=>v.version),[1,2,3]);assert.deepEqual(timelineHistory(versions,3),{undo:[],redo:[2]});
});
test('Source selection defaults to no silence cuts and binds only known highlights',()=>{
  const item={analysis:{analysis_id:'ana_saved',transcript:{transcript_id:'trn_saved'},silence_decisions:[{decision_id:'sil_safe',enabled:true,conflicts_with_speech:false},{decision_id:'sil_word',enabled:false,conflicts_with_speech:true}]},highlights:[{highlight_id:'hig_saved',recommended_start:.3,recommended_end:1.1}]};
  const defaultRequest=sourceCreatePayload(p,item);assert.deepEqual(defaultRequest.payload.silence_decision_ids,[]);assert.equal(defaultRequest.payload.expected_version,2);
  assert.deepEqual(sourceCreatePayload(p,item,{highlightId:'hig_saved',silenceIds:['sil_safe']}).payload.source_window,[.3,1.1]);
  assert.throws(()=>sourceCreatePayload(p,item,{silenceIds:['sil_word']}),/trùng lời nói/);
  assert.throws(()=>sourceCreatePayload(p,item,{highlightId:'foreign'}),/đã thay đổi/);
});
test('Source canvas, final explanation and advanced view follow the canonical source',()=>{
  assert.equal(videoFormat(p).aspect,'4:5');assert.equal(nextProjectStage(p),'video');
  assert.match(previewTimingLabel('final',null,p),/âm thanh gốc/);assert.doesNotMatch(previewTimingLabel('final',null,p),/Thùy Dung/);
  const markup=sourceAdvancedMarkup(p);assert.match(markup,/data-source-clip="clip_video"/);assert.match(markup,/data-track-state="muted"/);
  assert.ok(!markup.includes('<img onerror'));assert.ok(!markup.includes('aria-label="Biên độ'),'No fabricated waveform without measurements');
});

test('Source music describes editable routing without claiming automatic ducking',()=>{
  const project=structuredClone(p);project.document.music={filename:'User music.wav',duration_seconds:30};
  assert.match(musicSummary(project),/Advanced Timeline/);assert.doesNotMatch(musicSummary(project),/tự hạ/);
  assert.match(musicSummary({document:{music:project.document.music}}),/tự hạ/);
});
