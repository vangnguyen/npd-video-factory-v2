import {test} from 'node:test';
import assert from 'node:assert/strict';
import {newProjectQuality,narratedWorkflowGuide,usesNarratedWorkflow} from '../project-quality.mjs';
import {briefSendRequest} from '../intelligence.mjs';
test('New storyboard and approved idea creation share strict capability-gated preferences',()=>{
  const session={capabilities:{north_star_quality:true,native_narrated_workflow:true}};
  assert.deepEqual(newProjectQuality(session),{production_quality:true,narrated_workflow:true});assert.deepEqual(briefSendRequest({version:3},session),{version:3,...newProjectQuality(session)});
  for(const value of [undefined,{}, {capabilities:{native_narrated_workflow:true}},{capabilities:{north_star_quality:'true',native_narrated_workflow:true}}])assert.deepEqual(newProjectQuality(value),{});
  assert.deepEqual(briefSendRequest({version:3},{}),{version:3});assert.deepEqual(newProjectQuality({capabilities:{north_star_quality:true,native_narrated_workflow:'true'}}),{production_quality:true});
});
test('Guidance follows saved script, measured voice, audible review and production approval without opting in legacy or Source',()=>{
  const p={document:{narrated_workflow:{id:'native-narrated-storyboard-workflow-v1'}}};assert.equal(usesNarratedWorkflow(p),true);assert.match(narratedWorkflowGuide(p),/kịch bản/);
  p.document.proposal={};assert.match(narratedWorkflowGuide(p),/áp dụng thời lượng/);p.document.prepared_narration={};assert.match(narratedWorkflowGuide(p),/preview có tiếng/);
  p.approval={approval_scope:'narration_only'};assert.match(narratedWorkflowGuide(p),/preview có tiếng/);p.approval={};assert.match(narratedWorkflowGuide(p),/video cuối/);
  for(const value of [undefined,{document:{}},{...p,document:{...p.document,canonical_timeline:{snapshot:{metadata:{native_auto_edit_schema:'native-auto-edit-timeline-v1'}}}}}])assert.equal(narratedWorkflowGuide(value),'');
});
