import {test} from 'node:test';
import assert from 'node:assert/strict';
import {jobActive,currentVideo,canRender} from '../native.mjs';

test('Render UI requires current approval, saved edits and idle job',()=>{
  const p={revision:3,approval:{revision:3},jobs:[]};
  assert.equal(canRender(p,false,false),true);
  for(const value of [null,{...p,approval:null},{...p,approval:{revision:2}},{...p,jobs:[{status:'running'}]},{...p,jobs:[{status:'queued'}]}])assert.equal(canRender(value,false,false),false);
  assert.equal(canRender(p,true,false),false);assert.equal(canRender(p,false,true),false);
});
test('Only successful video bound to current approved version is visible',()=>{
  const p={revision:3,approval:{revision:3},jobs:[{kind:'render',status:'succeeded',revision:2},{kind:'render',status:'succeeded',revision:3}]};
  assert.equal(currentVideo(p).revision,3);
  assert.equal(currentVideo({...p,approval:null}),null);
  assert.equal(jobActive({...p,jobs:[{status:'failed'}]}),false);
});
