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
