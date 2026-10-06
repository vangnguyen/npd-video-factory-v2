import test from 'node:test';
import assert from 'node:assert/strict';
import {timelineHistory,timelineTranscriptId} from '../timeline-history.mjs';
const edit=version=>({version,mutation:{type:'clip-edit'}}),restore=(version,target)=>({version,mutation:{type:'restore',restored_from_version:target}});
test('Repeated undo and redo follow saved content states across new restore versions',()=>{
  const versions=[edit(1),edit(2),edit(3)];
  assert.deepEqual(timelineHistory(versions,3),{undo:[1,2],redo:[]});
  versions.push(restore(4,2),restore(5,1));
  assert.deepEqual(timelineHistory(versions.toReversed(),5),{undo:[],redo:[3,4]});
  versions.push(restore(6,4),restore(7,3));
  assert.deepEqual(timelineHistory(versions,7),{undo:[5,6],redo:[]});
  versions.push(restore(8,6),edit(9));
  assert.deepEqual(timelineHistory(versions,9),{undo:[5,8],redo:[]});
});
test('Manual restore is a reversible new edit and future versions are omitted',()=>{
  assert.deepEqual(timelineHistory([edit(1),edit(2),edit(3),restore(4,1),edit(5)],4),{undo:[1,2,3],redo:[]});
  assert.deepEqual(timelineHistory([],1),{undo:[],redo:[]});
});
test('Canonical transcript selection uses version binding and supports older clip-only metadata',()=>{
  assert.equal(timelineTranscriptId({snapshot:{metadata:{transcript_revision:{transcript_id:'saved-v1'}},tracks:[{clips:[{metadata:{transcript_id:'other'}}]}]}}),'saved-v1');
  assert.equal(timelineTranscriptId({snapshot:{tracks:[{clips:[{metadata:{transcript_id:'legacy'}}]}]}}),'legacy');
  assert.equal(timelineTranscriptId(null),null);
});
