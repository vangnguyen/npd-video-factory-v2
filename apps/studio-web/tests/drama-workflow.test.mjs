import test from 'node:test';
import assert from 'node:assert/strict';
import {dramaProgress,isDramaProject,dramaSteps,validateDramaScriptResponse} from '../drama-workflow.mjs';
test('Drama has five explicit stages and does not migrate a legacy casting project',()=>{
  assert.deepEqual(dramaSteps.map(v=>v[0]),['script','voices','scenes','preview','export']);
  assert.equal(isDramaProject({document:{drama_casting:{}}}),false);
  assert.equal(isDramaProject({document:{production_workflow:{kind:'drama'}}}),true);
});
test('Progress requires voices only for enabled speaking characters and an enabled narrator',()=>{
  const project={document:{drama_script:{raw_text:'An: Xin chào.',characters_confirmed:true},drama_casting:{configuration:{narrator_enabled:false,characters:[{character_id:'a',name:'An',role:'character'},{character_id:'b',name:'Bình',role:'character'},{character_id:'n',name:'Người kể',role:'narrator'}],casting:[],lines:[{enabled:true,character_id:'a'},{enabled:true,character_id:'n'}]}}},shot_timeline:{shots:[]},jobs:[]};
  assert.deepEqual(dramaProgress(project).uncast,['An']);
  project.document.drama_casting.configuration.casting=[{character_id:'a',voice_id:'v'}];
  assert.deepEqual(dramaProgress(project).uncast,[]);
  project.document.drama_casting.configuration.narrator_enabled=true;
  assert.deepEqual(dramaProgress(project).uncast,['Người kể']);
  assert.equal(dramaProgress(project).audio,false);
});
test('Script save receipts cannot fabricate approval or accept another project/revision',()=>{
  const result={project_id:'p',revision:3,provider_calls:0,human_approval_granted:false};
  assert.equal(validateDramaScriptResponse(result,{id:'p'},{revision:2}),result);
  for(const delta of [{project_id:'q'},{revision:4},{provider_calls:1},{human_approval_granted:true}])assert.throws(()=>validateDramaScriptResponse({...result,...delta},{id:'p'},{revision:2}));
});
