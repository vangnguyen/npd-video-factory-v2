import test from 'node:test';
import assert from 'node:assert/strict';
import {reframeProfiles,matchingVision,needsProductionReview} from '../reframe.mjs';

test('review and final profiles follow all four canonical aspect ratios',()=>{
  const expected={'9:16':['review-540x960','vertical-1080x1920'],'16:9':['review-960x540','landscape-1920x1080'],
    '1:1':['review-540x540','square-1080x1080'],'4:5':['review-432x540','portrait-1080x1350']};
  for(const [aspect,[review,final]] of Object.entries(expected)){
    const snapshot={metadata:{reframe:{aspect_ratio:aspect}}};
    assert.deepEqual(reframeProfiles(snapshot),{review,final});assert.equal(needsProductionReview(snapshot),true);
  }
  assert.equal(needsProductionReview({metadata:{}}),false);
});
test('only ready Vision evidence for the current source is offered',()=>{
  const source={analysis_id:'a',asset_id:'b'},ready={...source,status:'succeeded'};
  assert.deepEqual(matchingVision([ready,{...ready,asset_id:'c'},{...ready,status:'failed'}],source),[ready]);
});

test('saved canvas chooses its profile without requiring a later reframe action',()=>{
  const cases=[['16:9',1920,1080,'landscape-1920x1080'],['9:16',1080,1920,'vertical-1080x1920'],
    ['1:1',1080,1080,'square-1080x1080'],['4:5',1080,1350,'portrait-1080x1350']];
  for(const [aspect_ratio,width,height,final] of cases){
    assert.equal(reframeProfiles({aspect_ratio,width,height,metadata:{}}).final,final);
  }
});
test('canonical canvas controls review and final even when a historical reframe annotation is stale',()=>{
  assert.deepEqual(reframeProfiles({aspect_ratio:'16:9',width:1920,height:1080,metadata:{reframe:{aspect_ratio:'9:16'}}}),
    {review:'review-960x540',final:'landscape-1920x1080'});
});
test('metadata-only legacy callers retain their selected ratio and an empty caller retains the existing default',()=>{
  assert.equal(reframeProfiles({metadata:{reframe:{aspect_ratio:'4:5'}}}).review,'review-432x540');
  assert.equal(reframeProfiles({}).final,'vertical-1080x1920');
});
