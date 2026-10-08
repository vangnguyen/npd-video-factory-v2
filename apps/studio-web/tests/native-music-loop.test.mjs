import test from 'node:test';import assert from 'node:assert/strict';
import {musicLoopHeaders,supportsMusicLoopProject} from '../native.mjs';
const source={document:{canonical_timeline:{snapshot:{metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1'}}}}};
test('loop request is opt-in for an advertised source capability and zero preserves old request',()=>{
  assert.deepEqual(musicLoopHeaders(source,'.25',true),{'X-VF-Music-Loop-Crossfade':'0.25'});
  assert.deepEqual(musicLoopHeaders(source,'0',true),{});assert.deepEqual(musicLoopHeaders(source,'bad',false),{});
  assert.deepEqual(musicLoopHeaders({document:{}},'.25',true),{});assert.deepEqual(musicLoopHeaders(null,'.25',true),{});
});
test('invalid values cannot become header injection, nonfinite or out-of-range requests',()=>{
  for(const value of ['', ' ', '-.1','1.001','.1234','NaN','Infinity','0.5\r\nX-Fixture: bad',true,null])assert.throws(()=>musicLoopHeaders(source,value,true));
});
test('narrated overlap requires its own advertised capability and a saved shot timeline',()=>{
  const narrated={document:{canonical_timeline:{snapshot:{metadata:{native_shot_schema:'native-shot-timeline-v1'}}}}};
  assert.equal(supportsMusicLoopProject(narrated,true,false),false);assert.equal(supportsMusicLoopProject(narrated,false,true),true);
  assert.deepEqual(musicLoopHeaders(narrated,'.25',true),{});assert.deepEqual(musicLoopHeaders(narrated,'.25',false,true),{'X-VF-Music-Loop-Crossfade':'0.25'});
  assert.deepEqual(musicLoopHeaders(narrated,'0',false,true),{});assert.deepEqual(musicLoopHeaders({document:{}},'.25',false,true),{});
  assert.throws(()=>musicLoopHeaders(narrated,'Infinity',false,true));
});
