import {test} from 'node:test';
import assert from 'node:assert/strict';
import {activeOperation,currentIdeas,canSendBrief,canApproveBrief,safeLink,escapeHtml} from '../intelligence.mjs';
test('Brief send needs explicit approval, saved edits, idle state and queue approval',()=>{
  const b={brief:{status:'APPROVED',approval:{reviewer:'Fixture'}},operations:[],opportunity:{status:'APPROVED'}};
  assert.equal(canSendBrief(b,false,false),true);
  for(const value of [{...b,brief:{status:'DRAFT'}},{...b,operations:[{status:'RUNNING'}]},{...b,opportunity:{status:'REJECTED'}}])assert.equal(canSendBrief(value,false,false),false);
  assert.equal(canSendBrief(b,true,false),false);assert.equal(canSendBrief(b,false,true),false);
});
test('Brief review needs human acknowledgment and reviewer, and never uses a stale draft',()=>{
  const b={brief:{status:'DRAFT'},operations:[]};assert.equal(canApproveBrief(b,false,false,true,'Fixture'),true);
  for(const [dirty,busy,ack,name] of [[true,false,true,'Fixture'],[false,true,true,'Fixture'],[false,false,false,'Fixture'],[false,false,true,'']])assert.equal(canApproveBrief(b,dirty,busy,ack,name),false);
});
test('Regenerated candidates keep only the current generation in active selection',()=>{
  const b={run:{generation:2},ideas:[{generation:1,status:'SUPERSEDED'},{generation:2,status:'CANDIDATE'},{generation:2,status:'REJECTED'}]};
  assert.equal(currentIdeas(b).length,2);assert.equal(currentIdeas(null).length,0);assert.equal(activeOperation({operations:[{status:'FAILED'}]}),false);
});
test('Untrusted research renders as escaped text and links allow only public HTTPS syntax',()=>{
  assert.equal(safeLink('javascript:alert(1)'),'#');assert.equal(safeLink('https://user:secret@example.com'),'#');assert.equal(safeLink('https://example.com/path'),'https://example.com/path');assert.equal(escapeHtml('<script>'),'&lt;script&gt;');
});
