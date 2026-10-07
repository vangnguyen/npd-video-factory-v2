import test from 'node:test';
import assert from 'node:assert/strict';
import {sourceShortsPayload,shortsMarkup,analysisMarkup} from '../native-auto-edit.mjs';
const project={id:'a'.repeat(32),revision:7,document:{input_kind:'media',canonical_timeline:{version:2}}};
const item={filename:'Source',analysis:{analysis_id:'ana_saved',source_media:{duration_seconds:3},transcript:{transcript_id:'trn_saved',version:1,language:'vi',segments:[]},silence_decisions:[]},scenes:[],highlights:[],transcript_history:[]};
test('Native Auto Shorts request binds saved source/transcript/project/timeline and an explicit retry key',()=>{
  const body=sourceShortsPayload(project,item,{count:5,maximumDuration:45,aspectRatio:'4:5',requestKey:'b'.repeat(32)});
  assert.equal(body.revision,7);assert.equal(body.payload.expected_version,2);assert.equal(body.payload.count,5);
  assert.equal(body.payload.transcript_id,'trn_saved');assert.equal(body.payload.maximum_duration_seconds,45);
  assert.equal(body.payload.request_key,'b'.repeat(32));assert.equal(body.payload.aspect_ratio,'4:5');
  for(const options of [{count:4},{maximumDuration:NaN},{maximumDuration:2},{requestKey:'bad'}])assert.throws(()=>sourceShortsPayload(project,item,options));
});
test('Native Auto Shorts UI shows fewer candidates and independent unapproved drafts with escaped metadata',()=>{
  const html=shortsMarkup({batches:[{generated_count:1,requested_count:3,aspect_ratio:'9:16',drafts:[{project_id:'c'.repeat(32),name:'<script>x</script>',source_window:[.2,1.2]}]}]});
  assert.match(html,/1\/3/);assert.match(html,/chưa duyệt/);assert.ok(!html.includes('<script>'));
  assert.match(html,/data-open-short/);assert.match(analysisMarkup({analyses:[item]},{project,sourceEnabled:true}),/data-create-shorts/);
  assert.doesNotMatch(analysisMarkup({analyses:[item]},{project,sourceEnabled:false}),/data-create-shorts/);
});
