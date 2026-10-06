import test from 'node:test';
import assert from 'node:assert/strict';
import {transcriptEditPayload} from '../transcript-editor.mjs';
const analysis={analysis_id:'analysis-fixture',transcript:{version:2,segments:[{segment_id:'segment-fixture'}]}};
test('Transcript edits bind both saved versions and preserve Vietnamese text',()=>{
  const body=transcriptEditPayload(analysis,{source_analysis_id:analysis.analysis_id,current_version:4},'segment-fixture','Vang Nguyễn.');
  assert.equal(body.expected_version,2);assert.equal(body.expected_timeline_version,4);assert.equal(body.segments[0].text,'Vang Nguyễn.');
  assert.equal(transcriptEditPayload(analysis,null,'segment-fixture','Chào bạn.').expected_timeline_version,null);
});
test('Missing or stale transcript, foreign timeline and invalid text do not make requests',()=>{
  for(const args of [[null,null,'segment-fixture','hello'],[analysis,null,'foreign','hello'],[analysis,{source_analysis_id:'other'},'segment-fixture','hello'],[analysis,null,'segment-fixture',' '],[analysis,null,'segment-fixture','x'.repeat(4001)]])assert.throws(()=>transcriptEditPayload(...args));
});
