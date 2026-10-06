import test from 'node:test';
import assert from 'node:assert/strict';
import {sourceBrollPlans,sourceBrollRequest,sourceBrollMarkup} from '../native-source-broll.mjs';
const item={media_plan_item_id:'item',status:'resolved',source_asset_id:'ast_saved',selected_media_asset_id:'mas_saved',
  broll:{broll_intent:'<img onerror=x>',search_query:'Xin chào',placement_start_seconds:1,placement_end_seconds:2,confidence:.4},
  provenance:{supporting_candidates:[{asset_id:'ast_saved',filename:'<script>x</script>',rights_status:'verified',license:'owner_upload_rights_attestation',relevance_score:.5},
    {asset_id:'ast_unknown',filename:'Unknown',rights_status:'unknown',license:'unknown'}]}};
const plan={media_plan_id:'mpl_saved',version:2,items:[item],media_assets:[],provider_status:{semantic_vision:'NOT_CONFIGURED'},unresolved_items:0};
const p={id:'a'.repeat(32),revision:8,document:{canonical_timeline:{version:3},source_broll_plans:[{plan:{...plan,version:1}},{plan}]}};
test('Native B-roll uses newest saved plan and binds project, plan and canonical versions',()=>{
  assert.equal(sourceBrollPlans(p).length,1);assert.equal(sourceBrollPlans(p)[0].version,2);
  assert.deepEqual(sourceBrollRequest(p,'create'),{revision:8,action:'create',payload:{expected_version:3}});
  const selection=sourceBrollRequest(p,'select',{planId:'mpl_saved',itemId:'item',assetId:'ast_saved'});
  assert.equal(selection.payload.expected_plan_version,2);assert.equal(selection.payload.expected_version,3);
  assert.equal(sourceBrollRequest(p,'apply',{planId:'mpl_saved',itemId:'item',replace:true}).payload.replace_plan_clips,true);
  assert.throws(()=>sourceBrollRequest(p,'select',{planId:'mpl_saved',itemId:'item',assetId:'ast_unknown'}),/quyền/);
  assert.throws(()=>sourceBrollRequest(p,'apply',{planId:'foreign',itemId:'item'}),/đã thay đổi/);
  assert.throws(()=>sourceBrollRequest({...p,archived:true},'create'),/đang hoạt động/);
});
test('Native B-roll markup escapes saved metadata and attributes heuristic/provider limits',()=>{
  const html=sourceBrollMarkup(p);assert.ok(!html.includes('<img onerror'));assert.ok(!html.includes('<script>'));
  assert.match(html,/NOT_CONFIGURED/);assert.match(html,/heuristic/);assert.match(html,/chưa có Vision/);
  assert.match(html,/ast_unknown"\s+disabled/);assert.match(html,/data-broll-replace/);
});
