import test from 'node:test';
import assert from 'node:assert/strict';
import {compatibleBrollPlans,selectedBrollAsset,brollApplyPayload} from '../broll-planner.mjs';

test('B-roll selection stays bound to source and transcript, and applies only resolved unique items',()=>{
  const analysis={analysis_id:'ana_source',transcript:{transcript_id:'trn_current'}};
  const plan={media_plan_id:'mpl_plan',analysis_id:'ana_source',status:'draft',configuration:{purpose:'supporting_broll'},
    provenance:{transcript_id:'trn_current'},items:[{media_plan_item_id:'mpi_one',status:'resolved',provenance:{supporting_candidates:[{asset_id:'ast_image'}]}}]};
  assert.equal(compatibleBrollPlans([plan,{...plan,provenance:{transcript_id:'trn_old'}}],analysis).length,1);
  assert.deepEqual(selectedBrollAsset(plan.items[0],'ast_image'),{asset_id:'ast_image'});
  assert.throws(()=>selectedBrollAsset(plan.items[0],'ast_foreign'));
  const timeline={source_analysis_id:'ana_source',current_version:7,snapshot:{metadata:{transcript_revision:{transcript_id:'trn_current'}}}};
  assert.deepEqual(brollApplyPayload(timeline,plan,['mpi_one']),{expected_version:7,item_ids:['mpi_one'],replace_plan_clips:false});
  assert.throws(()=>brollApplyPayload(timeline,plan,['mpi_one','mpi_one']));
  assert.throws(()=>brollApplyPayload(timeline,plan,['mpi_foreign']));
  assert.throws(()=>brollApplyPayload(timeline,{...plan,provenance:{transcript_id:'trn_old'}},['mpi_one']));
});
