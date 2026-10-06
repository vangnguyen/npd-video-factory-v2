import test from 'node:test';
import assert from 'node:assert/strict';
import {silenceSelection,canonicalShotClips} from '../analysis-review.mjs';
test('Silence review permits keeping all footage and rejects unsafe or foreign cuts',()=>{
  const analysis={status:'succeeded',silence_decisions:[{decision_id:'safe',enabled:true,conflicts_with_speech:false},
    {decision_id:'speech',enabled:true,conflicts_with_speech:true},{decision_id:'short',enabled:false}]};
  assert.deepEqual(silenceSelection(analysis,[]),[]);
  assert.deepEqual(silenceSelection(analysis,['safe']),['safe']);
  for(const ids of [['speech'],['short'],['foreign'],['safe','safe']])assert.throws(()=>silenceSelection(analysis,ids));
  assert.throws(()=>silenceSelection({...analysis,status:'running'},['safe']));
});
test('Shot view uses canonical clip identities, ordering and locks',()=>{
  const snapshot={tracks:[{track_id:'source',type:'video',kind:'source',locked:true,clips:[{clip_id:'second',timeline_start:2},{clip_id:'first',timeline_start:0}]},
    {type:'audio',kind:'original_audio',clips:[{clip_id:'audio',timeline_start:0}]},{type:'video',kind:'source',disabled:true,clips:[{clip_id:'disabled-track'}]}]};
  assert.deepEqual(canonicalShotClips(snapshot).map(c=>c.clip_id),['first','second']);
  assert.equal(canonicalShotClips(snapshot)[0].track_id,'source');assert.equal(canonicalShotClips(snapshot)[0].track_locked,true);
  assert.deepEqual(canonicalShotClips(null),[]);
});
