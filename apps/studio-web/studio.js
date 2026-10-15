import {
  analyticsMetricItems,
  canDropOnTrack,
  clipStyle,
  describeAnalytics,
  describeApproval,
  describePublication,
  describeProductionRender,
  describePreview,
  formatTime,
  getClip,
  pixelsPerSecond,
  publicationGateItems,
  qcItems,
  timelinePositionFromPointer,
} from "/studio-utils.mjs?v=0.12.0";
import { authenticatedFetch, ensureAuthenticatedSession, sessionToken } from "/auth.mjs";
import { initializeMultiInput } from "/multi-input.mjs";
import { transcriptEditPayload } from "/transcript-editor.mjs";
import { timelineHistory,timelineTranscriptId } from "/timeline-history.mjs";
import { silenceSelection,canonicalShotClips,compatibleSceneAssessments,sceneScore } from "/analysis-review.mjs";
import { waveformPath } from "/waveform.mjs";
import {reframeProfiles,matchingVision,needsProductionReview} from "/reframe.mjs";
import {subtitleCueEdit,compatibleSubtitleTemplates,subtitleSaveStyle,timedSubtitleModes} from '/subtitle-editor.mjs';
import {compatibleBrollPlans,selectedBrollAsset,brollApplyPayload} from '/broll-planner.mjs';
import {initializePublishingConsole} from '/publishing-console.mjs';
import {initializeAnalyticsConsole} from '/analytics-console.mjs';
import {initializeAnalyticsChannels} from '/analytics-channels.mjs';
import {initializeAnalyticsRefresh} from '/analytics-refresh.mjs';
import {initializeChannelLearning} from '/channel-learning.mjs';
import {initializeUploadedAudioReview,audioRole,audioByteHash} from '/uploaded-audio-review.mjs?v=sql-audio-1';
import {initializeStockPlanningReview} from '/stock-planning-review.mjs?v=sql-stock-1';
import {initializeVideoAnalysisJobs,videoReviewSelection,selectedVideoReviewAnalysis} from '/video-analysis-jobs.mjs?v=sql-video-jobs-1';
import {initializeSqlVariantFamilies} from '/sql-variant-families.mjs?v=sql-family-1';
import {initializeSqlVariantNarration} from '/sql-variant-narration.mjs?v=sql-narration-1';
import {initializeVideoTranscriptWordReview} from '/video-transcript-word-review.mjs?v=sql-video-words-1';
import {initializeSqlTimelineAudioProcessing,audioProcessingRead} from '/sql-timeline-audio-processing.mjs?v=sql-audio-processing-1';
import {initializeSqlSourceLinkedEdit,sourceLinkedRead} from '/sql-source-linked-edit.mjs?v=sql-source-linked-1';
import {initializeSqlManualReframe,manualReframeRead,manualReframeSettings} from '/sql-manual-reframe.mjs?v=sql-manual-reframe-1';
import {initializeBrollPlanReview,defaultBrollPlanSettings,brollPlanSettings,validateBrollPlanContext} from '/broll-plan-review.mjs?v=broll-plan-review-1';
import {videoWordSessionStorage} from '/video-transcript-word-review.mjs?v=sql-video-words-1';
import {initializeSqlBrollTimelineReview,brollTimelineRead,brollTimelineSelection} from '/sql-broll-timeline-review.mjs?v=sql-broll-timeline-1';
import {initializeSqlBrollInternalResolution,validateBrollInternalContext} from '/sql-broll-internal-resolution.mjs?v=sql-broll-internal-1';

const state = {
  workspaceId: null,
  workspaceSlug: null,
  principal: null,
  projects: [],
  projectId: null,
  assets: [],
  analyses: [],
  mediaPlans: [],
  selectedBrollPlanId: '',
  timeline: null,
  versions: [],
  preview: null,
  productionPackage: null,
  subtitleCatalog: null,
  publications: [],
  publishingPlatforms: [],
  activePublication: null,
  analyticsReport: null,
  analyticsProviders: [],
  activeAnalyticsSync: null,
  publishRequestSignature: null,
  publishIdempotencyKey: null,
  activeProductionRender: null,
  selectedClipId: null,
  panelTab: "media",
  query: "",
  zoom: 1,
  snapping: true,
  playhead: 0,
  redoStack: [],
  undoStack: [],
  transcriptDrafts: new Map(),
  highlightDrafts: [],
  highlightSupported: false,
  visionAnalyses: [],
  sceneAssessments: [],
  selectedSceneAssessmentId: '',
  videoReviewSelection: null,
  sceneIntelligenceSupported: false,
  draggingClipId: null,
  pollTimer: null,
  productionPollTimer: null,
  analyticsPollTimer: null,
  projectLoading: 0,
};

const $ = (selector) => document.querySelector(selector);
let videoWordReview = null;
let sqlAudioProcessing = null;
let sourceLinkedEditor = null;
let brollPlanController=null,brollPlanFormRead=null,brollPlanFormBaseline=null,brollPlanOperation=null;
let brollPlanBusy=false;
const brollPlanAdmission=Symbol('scoped-broll-preparation');
const brollPlanStore=videoWordSessionStorage();
function brollPlanDraft(){return JSON.stringify([...document.querySelectorAll('#broll-plan-form [data-broll-setting]')]
  .map(e=>[e.id,e.type==='checkbox'?e.checked:e.value]));}
function brollPlanDirty(){return brollPlanFormRead!==null&&brollPlanFormBaseline!==brollPlanDraft();}
function brollPlanStored(){
  if(!state.workspaceId||!state.projectId||!state.principal?.subject)return false;
  try{if(!brollPlanStore)return true;const value=brollPlanStore.getItem('vf-broll-plan-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]));
    return value!==null&&value!==undefined;}catch{return true;}
}
function brollPreparationHeld(){return brollPlanBusy||brollPlanDirty()||brollPlanStored()||brollPlanController?.state().pending!==null&&brollPlanController?.state().pending!==undefined;}
function brollPlanHeld(){return brollPreparationHeld()||brollTimelineHeld()||brollInternalHeld();}
let brollTimelineController=null,brollTimelineBusy=false,brollTimelineFormRead=null,brollTimelineBaseline=null,brollTimelineOperation=null;
const brollTimelineAdmission=Symbol('scoped-broll-timeline-controller');
const brollTimelineStore=videoWordSessionStorage();
function brollTimelineDraft(){return JSON.stringify([...document.querySelectorAll('#broll-timeline-form [data-broll-timeline-setting]')]
  .map(e=>[e.id,e.type==='checkbox'?e.checked:e.value]));}
function brollTimelineDirty(){return brollTimelineFormRead!==null&&brollTimelineBaseline!==brollTimelineDraft();}
function brollTimelineStored(){
  if(!state.workspaceId||!state.projectId||!state.principal?.subject)return false;
  const scope=()=>JSON.stringify([state.workspaceId,state.projectId,state.principal,sessionToken()]),before=scope();
  const key='vf-sql-broll-timeline-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]);
  try{if(!brollTimelineStore)return true;const raw=brollTimelineStore.getItem(key);return scope()!==before||raw!==null&&raw!==undefined;}catch{return true;}
}
function brollTimelineHeld(){return brollTimelineBusy||brollTimelineDirty()||brollTimelineStored()||brollTimelineController?.isPending()===true;}
let brollInternalController=null,brollInternalBusy=false,brollInternalOperation=null,brollInternalFormRead=null,brollInternalBaseline=null,brollInternalItemId='';
let brollInternalStatus='Chưa đọc. Chỉ dùng tư liệu đã lưu sau lựa chọn và xác nhận rõ ràng.';
const brollInternalAdmission=Symbol('scoped-internal-broll-resolution'),brollInternalStore=videoWordSessionStorage();
function brollInternalDraft(){return JSON.stringify([...document.querySelectorAll('#broll-internal-form [data-broll-internal-setting]')]
  .map(e=>[e.id,e.type==='checkbox'?e.checked:e.value]));}
function brollInternalDirty(){return brollInternalFormRead!==null&&brollInternalBaseline!==brollInternalDraft();}
function brollInternalBareScope(){return sqlAudioStable([state.workspaceId,state.projectId,state.principal,sessionToken()]);}
function brollInternalBucket(){return 'vf-sql-broll-internal-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal?.subject]);}
function brollInternalStored(){if(!state.workspaceId||!state.projectId||!state.principal?.subject)return false;
  const before=brollInternalBareScope();try{if(!brollInternalStore)return true;const raw=brollInternalStore.getItem(brollInternalBucket());
    return before!==brollInternalBareScope()||raw!==null&&raw!==undefined;}catch{return true;}}
function brollInternalHeld(){return brollInternalBusy||brollInternalDirty()||brollInternalStored()||brollInternalController?.isPending()===true;}

let manualReframeEditor = null;
let manualReframeFormRead = null;
let manualReframeFormBaseline = null;
let manualReframeApplying = null;
const manualReframeAdmission = Symbol('scoped-manual-reframe-controller');
function manualReframeDraft(){return JSON.stringify([$('#manual-reframe-aspect')?.value??'',
  [...document.querySelectorAll('#manual-reframe-points [data-manual-reframe-field]')].map(input=>[input.dataset.manualReframeField,input.value])]);}
function manualReframeDirty(){return manualReframeFormRead!==null&&manualReframeFormBaseline!==manualReframeDraft();}
function manualReframeHeld(){return manualReframeApplying!==null||manualReframeDirty()||manualReframeEditor?.isWorking()===true||manualReframeEditor?.isPending()===true;}
const initialProjectRead = Symbol('initial-canonical-project-read');
const sourceLinkedAdmission = Symbol('scoped-source-linked-controller');
function sourceLinkedHeld(){return sourceLinkedEditor?.isWorking()===true||sourceLinkedEditor?.isDirty()===true||sourceLinkedEditor?.isPending()===true;}
const audioProcessingAdmission = Symbol('scoped-audio-processing-controller');
function audioProcessingHeld(){return sqlAudioProcessing?.isWorking()===true || sqlAudioProcessing?.isDirty()===true || sqlAudioProcessing?.isPending()===true;}
const videoWordAdmission = Symbol('scoped-word-controller');
function videoWordsHeld(){return videoWordReview?.isWorking()===true || videoWordReview?.isDirty()===true || videoWordReview?.isPending()===true;}
const multiInput = initializeMultiInput({api, getState: () => state, refresh: () => loadProject(),
  refreshProjects: () => loadProjectList(), toast, uploadFetch: authenticatedFetch});
let multiInputBaseline = null;
let productionBaseline = null;
let variantNarration = null;
let productionPollGeneration = 0;
let productionPollInFlight = null;
function audioWorkbenchDraft() {
  return JSON.stringify([...document.querySelectorAll('#mvp-kind,#mvp-original,#mvp-script,#mvp-facts,#mvp-protected,#mvp-scenes input,#mvp-scenes textarea,#mvp-scenes select')]
    .map(input => [input.id, input.dataset.field, input.type === 'checkbox' ? input.checked : input.value]));
}
function productionWorkbenchDraft(){return JSON.stringify([...document.querySelectorAll(
  '#subtitle-list [data-cue-field],#subtitle-position,#subtitle-animation,#subtitle-template,#subtitle-keywords,#subtitle-font-size,#subtitle-safe-margin,#voice-enabled,#voice-speed,#voice-gain,#music-gain,#music-ducking,#music-asset')]
  .map(input=>[input.id,input.dataset.cueField,input.type==='checkbox'?input.checked:input.value]));}
const audioReview = initializeUploadedAudioReview({root: $('#uploaded-audio-review'), api,
  mediaFetch: authenticatedFetch, getState: () => ({...state, busy: state.projectLoading > 0 || videoWordReview?.isWorking()===true || sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true||brollPlanBusy,
    dirty: brollPlanHeld()||manualReframeHeld()||sourceLinkedHeld()||sqlAudioProcessing?.isDirty()===true || sqlAudioProcessing?.isPending()===true || videoWordReview?.isDirty()===true || videoWordReview?.isPending()===true || state.transcriptDrafts.size > 0 || multiInputBaseline !== null && audioWorkbenchDraft() !== multiInputBaseline}),
  onMessage: toast, onUploaded: () => loadProject(), onCanonicalSaved: () => loadProject()});
const stockReview = initializeStockPlanningReview({root: $('#stock-planning-review'), api,
  getState: () => ({...state, busy: state.projectLoading > 0 || videoWordReview?.isWorking()===true || sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true||brollPlanBusy,
    dirty: brollPlanHeld()||manualReframeHeld()||sourceLinkedHeld()||sqlAudioProcessing?.isDirty()===true || sqlAudioProcessing?.isPending()===true || videoWordReview?.isDirty()===true || videoWordReview?.isPending()===true || audioReview.isDirty() || state.transcriptDrafts.size > 0
      || multiInputBaseline !== null && audioWorkbenchDraft() !== multiInputBaseline}),
  onMessage: toast, onPlanUpdated: plan => {
    if (plan.project_id !== state.projectId || plan.workspace_id !== state.workspaceId) return;
    state.mediaPlans = [plan, ...state.mediaPlans.filter(item => item.media_plan_id !== plan.media_plan_id)];
    if (state.timeline) renderBrowser();
  }});
const videoReview = initializeVideoAnalysisJobs({root: $('#video-analysis-jobs'), api,
  getState: () => ({...state, busy: state.projectLoading > 0 || multiInput.isBusy() || videoWordReview?.isWorking()===true || sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true||brollPlanBusy,
    dirty: brollPlanHeld()||manualReframeHeld()||sourceLinkedHeld()||sqlAudioProcessing?.isDirty()===true || sqlAudioProcessing?.isPending()===true || videoWordReview?.isDirty()===true || videoWordReview?.isPending()===true || audioReview.isDirty() || stockReview.isPending() || state.transcriptDrafts.size > 0
      || multiInputBaseline !== null && audioWorkbenchDraft() !== multiInputBaseline}),
  onMessage: toast, onReview: async value => {
    const selection=videoReviewSelection(state,value);
    await loadProject();
    if(state.projectId!==selection.project_id||state.workspaceId!==selection.workspace_id)return;
    state.videoReviewSelection=selection;
    state.selectedSceneAssessmentId='';
    renderAnalysisReview();
    if(!state.timeline)render();
  }});
function sqlEditorState(){return{...state,busy: state.projectLoading > 0 || multiInput.isBusy()
      || ['queued','running'].includes(state.activeProductionRender?.status),
    dirty: audioReview.isDirty() || stockReview.isPending() || videoReview.isPending() || state.transcriptDrafts.size > 0
      || multiInputBaseline !== null && audioWorkbenchDraft() !== multiInputBaseline
      || productionBaseline !== null && productionWorkbenchDraft() !== productionBaseline};}
function sqlFamilyState(){const value=sqlEditorState();return{...value,
  busy:value.busy||variantNarration?.isWorking()===true||videoWordReview?.isWorking()===true||sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true||brollPlanBusy,
  dirty:value.dirty||brollPlanHeld()||manualReframeHeld()||sourceLinkedHeld()||variantNarration?.isPending()===true||videoWordReview?.isDirty()===true||videoWordReview?.isPending()===true||sqlAudioProcessing?.isDirty()===true||sqlAudioProcessing?.isPending()===true};}
function sqlNarrationState(){const value=sqlEditorState();return{...value,
  busy:value.busy||variantFamilies.isBusy()||videoWordReview?.isWorking()===true||sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true||brollPlanBusy,dirty:value.dirty||brollPlanHeld()||manualReframeHeld()||sourceLinkedHeld()||variantFamilies.isPending()||videoWordReview?.isDirty()===true||videoWordReview?.isPending()===true||sqlAudioProcessing?.isDirty()===true||sqlAudioProcessing?.isPending()===true};}
const variantFamilies = initializeSqlVariantFamilies({root: $('#sql-variant-families'),api,getState:sqlFamilyState,
  onMessage: toast,onChild: async selection => {
    const principal=state.principal,subject=principal?.subject,tokenId=principal?.token_id;
    const projects=await api(`/api/v1/workspaces/${selection.workspace_id}/projects`);
    if(state.workspaceId!==selection.workspace_id||state.projectId!==selection.master_project_id
      ||state.principal?.subject!==subject||state.principal?.token_id!==tokenId)return;
    const latest=sqlFamilyState();
    if(latest.busy||latest.dirty)throw Error('Lưu thay đổi đang sửa và chờ thao tác hiện tại xong trước khi mở bản nháp.');
    if(!projects.some(project=>project.project_id===selection.child_project_id&&project.workspace_id===selection.workspace_id))
      throw Error('Chưa tìm thấy bản nháp trong workspace hiện tại.');
    state.projects=projects;
    $('#project-select').innerHTML=projects.map(project=>`<option value="${escapeHtml(project.project_id)}">${escapeHtml(project.name)}</option>`).join('');
    state.projectId=selection.child_project_id;$('#project-select').value=state.projectId;
    window.localStorage.setItem('npd-studio-project',state.projectId);await loadProject();
  }});
const unsubscribeVideoBusy = multiInput.onBusyChanged(() => {videoReview.sync();variantFamilies.sync();variantNarration?.sync();videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();});
variantNarration = initializeSqlVariantNarration({root:$('#sql-variant-narration'),api,getState:sqlNarrationState,
  onMessage:toast,onImported:refreshNarrationAssets,onReviewQueued:refreshNarrationReview});

function videoWordEditorState(){const value=sqlEditorState();return {...value,analysis:reviewedAnalysis(),
  busy:value.busy||variantFamilies.isBusy()||variantNarration?.isWorking()===true||sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true||brollPlanBusy,
  dirty:value.dirty||brollPlanHeld()||manualReframeHeld()||sourceLinkedHeld()||variantFamilies.isPending()||variantNarration?.isPending()===true||sqlAudioProcessing?.isDirty()===true||sqlAudioProcessing?.isPending()===true};}
function syncVideoWordPeers(){audioReview.sync();stockReview.sync();videoReview.sync();variantFamilies.sync();variantNarration?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();}
videoWordReview=initializeVideoTranscriptWordReview({root:$('#video-transcript-word-review'),
  api:(path,options={})=>api(path,{...options,videoWordAdmission}),mediaFetch:authenticatedFetch,
  getState:videoWordEditorState,getSessionToken:sessionToken,onMessage:toast,
  onSaved:refreshVideoWordReceipt,onBusyChanged:syncVideoWordPeers});

function sqlAudioEditorState(){const value=sqlEditorState();return {...value,
  busy:value.busy||variantFamilies.isBusy()||variantNarration?.isWorking()===true||videoWordReview?.isWorking()===true,
  dirty:value.dirty||brollPlanHeld()||manualReframeHeld()||sourceLinkedHeld()||variantFamilies.isPending()||variantNarration?.isPending()===true||videoWordReview?.isDirty()===true||videoWordReview?.isPending()===true};}
function syncSqlAudioPeers(){syncVideoWordPeers();videoWordReview?.sync();}
sqlAudioProcessing=initializeSqlTimelineAudioProcessing({root:$('#sql-timeline-audio-processing'),
  api:(path,options={})=>api(path,{...options,audioProcessingAdmission}),getState:sqlAudioEditorState,
  getSessionToken:sessionToken,onMessage:toast,onSaved:refreshSqlAudioProcessing,onBusyChanged:syncSqlAudioPeers});
function sqlAudioStable(value){return JSON.stringify(value,(_key,item)=>item&&typeof item==='object'&&!Array.isArray(item)
  ?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);}
function sqlAudioSourceValue(timeline){const snapshot=structuredClone(timeline.snapshot);delete snapshot.metadata.source_audio_processing;
  return {timeline_id:timeline.timeline_id,project_id:timeline.project_id,workspace_id:timeline.workspace_id,
    source_analysis_id:timeline.source_analysis_id,source_content_version_id:timeline.source_content_version_id,
    source_kind:timeline.source_kind,source_media_plan_id:timeline.source_media_plan_id,snapshot};}
function sqlAudioEditorBoundary(){const value=sqlAudioEditorState();return JSON.stringify([
  value.workspaceId,value.projectId,value.principal,sessionToken(),value.timeline,value.assets,value.analyses,value.mediaPlans,
  value.productionPackage,productionWorkbenchDraft(),audioWorkbenchDraft()]);}
function assertSqlAudioBoundary(boundary){const value=sqlAudioEditorState();
  if(value.busy||value.dirty||sqlAudioEditorBoundary()!==boundary||value.principal?.human_write_enabled!==true
    ||!['editor','reviewer','owner'].includes(audioRole(value))
    ||!Number.isFinite(Date.parse(value.principal?.expires_at))||Date.parse(value.principal.expires_at)<=Date.now())
    throw Error('Nguồn, phiên hoặc bản sửa khác đã đổi; giữ cấu hình âm thanh để đối chiếu.');}
async function refreshSqlAudioProcessing(value,requestGuard){
  const guard=()=>{if(typeof requestGuard!=='function'||requestGuard()!==true)
    throw Error('Thiếu ràng buộc đồng bộ với đúng yêu cầu âm thanh đang giữ.');};guard();
  const boundary=sqlAudioEditorBoundary(),current=sqlAudioEditorState(),receipt=value.receipt,timeline=value.timeline;
  assertSqlAudioBoundary(boundary);
  if(!current.timeline||value.workspace_id!==current.workspaceId||value.project_id!==current.projectId
    ||value.actor_ref!==current.principal?.subject||receipt?.actor_ref!==value.actor_ref
    ||receipt.workspace_id!==value.workspace_id||receipt.project_id!==value.project_id
    ||receipt.timeline_id!==current.timeline.timeline_id||timeline?.timeline_id!==current.timeline.timeline_id
    ||timeline.workspace_id!==value.workspace_id||timeline.project_id!==value.project_id
    ||receipt.parent_version!==value.parent_version||receipt.result_version!==value.result_version
    ||value.result_version!==value.parent_version+1||timeline.current_version!==value.result_version
    ||![value.parent_version,value.result_version].includes(current.timeline.current_version)
    ||sqlAudioStable(sqlAudioSourceValue(current.timeline))!==sqlAudioStable(sqlAudioSourceValue(timeline))
    ||current.timeline.current_version===value.result_version&&sqlAudioStable(current.timeline)!==sqlAudioStable(timeline))
    throw Error('Biên nhận cấu hình chưa khớp đúng nguồn, người sửa và timeline; không đổi CAS.');
  const path=`/api/v1/projects/${value.project_id}/timeline/audio-processing`;
  const proof=await api(path);guard();assertSqlAudioBoundary(boundary);audioProcessingRead(proof,sqlAudioEditorState());
  if(sqlAudioStable(proof.timeline)!==sqlAudioStable(timeline)||sqlAudioStable(proof.receipt)!==sqlAudioStable(receipt))
    throw Error('Cấu hình hiện tại chưa chứng minh đúng lần lưu; giữ yêu cầu.');
  const versions=await api(`/api/v1/projects/${value.project_id}/timeline/versions`);guard();assertSqlAudioBoundary(boundary);
  if(!videoWordHistoryMatches(versions,proof.timeline))throw Error('Lịch sử timeline chưa khớp cấu hình đã đọc; giữ yêu cầu.');
  const head=versions.find(row=>row.version===proof.timeline.current_version
    &&row.timeline_version_id===proof.timeline.current_version_id);
  if(head?.actor_ref!==receipt.actor_ref||head.mutation?.type!=='source-audio-processing'
    ||head.mutation.source_media_mutated!==false||head.mutation.publish_requested!==false
    ||sqlAudioStable(head.mutation.receipt)!==sqlAudioStable(receipt))
    throw Error('Lịch sử timeline chưa khớp người sửa và biên nhận âm thanh; giữ yêu cầu.');
  const finalProof=await api(path);guard();assertSqlAudioBoundary(boundary);audioProcessingRead(finalProof,sqlAudioEditorState());
  if(sqlAudioStable(finalProof.timeline)!==sqlAudioStable(proof.timeline)||sqlAudioStable(finalProof.receipt)!==sqlAudioStable(receipt))
    throw Error('Timeline hoặc biên nhận đã đổi sau khi đọc lịch sử; giữ yêu cầu.');
  guard();state.timeline=structuredClone(finalProof.timeline);state.versions=structuredClone(versions);
  state.selectedClipId=null;state.undoStack=[];state.redoStack=[];
  if(state.preview)state.preview={...state.preview,status:'stale',valid_for_current_timeline:false};
  if(state.productionPackage)state.productionPackage={...state.productionPackage,current_for_timeline:false,
    approval:null,latest_review_render:null,latest_final_render:null};
  state.activeProductionRender=null;stopPreviewPolling();stopProductionPolling();render();
}

function videoWordEditorBoundary(){const value=videoWordEditorState();return JSON.stringify([
  value.workspaceId,value.projectId,value.principal,sessionToken(),value.analysis,value.assets,value.timeline,
  value.productionPackage,productionWorkbenchDraft(),audioWorkbenchDraft()]);}
function assertVideoWordEditorBoundary(boundary){const value=videoWordEditorState();
  if(value.busy||value.dirty||videoWordEditorBoundary()!==boundary)
    throw Error('Nguồn, phiên hoặc bản sửa khác đã đổi; giữ lần lưu từ để đối chiếu.');}
function videoWordHistoryMatches(versions,timeline){
  if(!Array.isArray(versions)||!versions.length)return false;
  const ids=new Set(),ordinals=new Set();let head=null;
  for(const row of versions){
    if(!row||row.project_id!==timeline.project_id||row.timeline_id!==timeline.timeline_id
      ||typeof row.timeline_version_id!=='string'||!row.timeline_version_id
      ||!Number.isInteger(row.version)||row.version<1||row.version>timeline.current_version
      ||ids.has(row.timeline_version_id)||ordinals.has(row.version)
      ||!row.snapshot||typeof row.snapshot!=='object'||Array.isArray(row.snapshot))return false;
    ids.add(row.timeline_version_id);ordinals.add(row.version);
    if(row.version===timeline.current_version)head=row;
  }
  const stable=value=>JSON.stringify(value,(_key,item)=>item&&typeof item==='object'&&!Array.isArray(item)
    ?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
  return !!head&&head.timeline_version_id===timeline.current_version_id&&stable(head.snapshot)===stable(timeline.snapshot);
}
async function refreshVideoWordReceipt(value,requestGuard){
  const guard=()=>{if(typeof requestGuard!=='function'||requestGuard()!==true)
    throw Error('Thiếu ràng buộc đồng bộ với đúng yêu cầu sửa từ đang giữ.');};guard();
  const boundary=videoWordEditorBoundary(),current=videoWordEditorState(),receipt=value.receipt;
  assertVideoWordEditorBoundary(boundary);
  const source=current.assets.find(asset=>asset.asset_id===value.asset_id);
  if(value.workspace_id!==current.workspaceId||value.project_id!==current.projectId
    ||current.analysis?.analysis_id!==value.analysis_id||current.analysis.asset_id!==value.asset_id
    ||!source||source.workspace_id!==value.workspace_id||source.project_id!==value.project_id||source.checksum_sha256!==value.source_sha256
    ||receipt.project_id!==value.project_id||receipt.workspace_id!==value.workspace_id||receipt.analysis_id!==value.analysis_id
    ||receipt.asset_id!==value.asset_id||receipt.transcript.transcript_id!==value.result_transcript_id
    ||receipt.transcript.provenance.derived_from_transcript_id!==value.base_transcript_id
    ||(current.timeline?.current_version??null)!==value.expected_timeline_version)
    throw Error('Biên nhận sửa từ không còn khớp nguồn và timeline đang xem.');
  const timeline=await api(`/api/v1/projects/${value.project_id}/timeline`).catch(error=>{
    if(error.status===404&&value.expected_timeline_version===null)return null;throw error;});
  guard();assertVideoWordEditorBoundary(boundary);
  if(value.expected_timeline_version===null?timeline!==null:
    !timeline||timeline.project_id!==value.project_id||timeline.workspace_id!==value.workspace_id
      ||timeline.source_analysis_id!==value.analysis_id||timeline.current_version!==value.expected_timeline_version+1
      ||timeline.snapshot?.metadata?.transcript_revision?.transcript_id!==value.result_transcript_id)
    throw Error('Timeline chưa chứng minh đúng lần lưu từ; không đổi CAS hoặc bỏ yêu cầu chờ.');
  const versions=timeline?await api(`/api/v1/projects/${value.project_id}/timeline/versions`):[];
  guard();assertVideoWordEditorBoundary(boundary);
  if(timeline?!videoWordHistoryMatches(versions,timeline):!Array.isArray(versions)||versions.length)
    throw Error('Lịch sử timeline không khớp phiên bản vừa đọc; giữ yêu cầu để đối chiếu.');
  guard();state.analyses=state.analyses.map(analysis=>analysis.analysis_id===value.analysis_id?structuredClone(receipt):analysis);
  state.timeline=timeline;state.versions=versions;state.videoReviewSelection=null;state.selectedSceneAssessmentId='';
  state.selectedClipId=null;state.undoStack=[];state.redoStack=[];
  if(state.preview)state.preview={...state.preview,status:'stale',valid_for_current_timeline:false};
  if(state.productionPackage)state.productionPackage={...state.productionPackage,current_for_timeline:false,
    approval:null,latest_review_render:null,latest_final_render:null};
  state.activeProductionRender=null;stopPreviewPolling();stopProductionPolling();render();
}


function narrationEditorBoundary(){const current=sqlNarrationState();return JSON.stringify([
  current.workspaceId,current.projectId,current.principal,sessionToken(),
  current.timeline?.current_version_id,current.timeline?.current_version,current.timeline?.source_content_version_id,
  current.productionPackage?.package_id,current.productionPackage?.timeline_version_id,
  current.productionPackage?.subtitle?.subtitle_version_id,current.productionPackage?.audio_mix?.audio_version_id,
  current.productionPackage?.audio_mix?.config?.voice]);}
function assertNarrationEditorBoundary(boundary){const current=sqlNarrationState();
  if(current.busy||current.dirty||narrationEditorBoundary()!==boundary)
    throw Error('Nguồn, phiên truy cập hoặc thay đổi đang sửa đã đổi. Đọc lại trạng thái trước khi tiếp tục.');}
async function refreshNarrationAssets(receipt){
  const boundary=narrationEditorBoundary(),projectId=state.projectId,workspaceId=state.workspaceId;
  const assets=await api(`/api/v1/projects/${projectId}/assets`);
  assertNarrationEditorBoundary(boundary);
  if(receipt.child_project_id!==projectId||receipt.workspace_id!==workspaceId
    ||!Array.isArray(assets)||assets.some(asset=>asset.project_id!==projectId||asset.workspace_id!==workspaceId))
    throw Error('Tư liệu đã nhập không thuộc dự án hiện tại.');
  state.assets=assets;if(state.timeline)renderBrowser();
}
async function refreshNarrationReview(render){
  const boundary=narrationEditorBoundary(),projectId=state.projectId,workspaceId=state.workspaceId;
  const packageState=await api(`/api/v1/projects/${projectId}/production-package`);
  assertNarrationEditorBoundary(boundary);
  if(render.project_id!==projectId||packageState.project_id!==projectId||packageState.workspace_id!==workspaceId
    ||packageState.latest_review_render?.render_id!==render.render_id
    ||packageState.package_id!==state.productionPackage?.package_id
    ||packageState.timeline_version_id!==state.productionPackage?.timeline_version_id
    ||packageState.subtitle.subtitle_version_id!==state.productionPackage?.subtitle.subtitle_version_id
    ||packageState.audio_mix.audio_version_id!==state.productionPackage?.audio_mix.audio_version_id)
    throw Error('Gói review đã đổi. Đọc lại trạng thái để xem đúng bản hiện tại.');
  state.productionPackage=packageState;state.activeProductionRender=packageState.latest_review_render;
  renderSummary();renderProduction();
  if(['queued','running'].includes(state.activeProductionRender.status))startProductionPolling();
}
document.addEventListener('input', event => {
  if (event.target.closest('#multi-input-workbench') || event.target.closest('[data-transcript-text]')) audioReview.sync();
  stockReview.sync();
  videoReview.sync();
  variantFamilies.sync();
  variantNarration?.sync();
  videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();
});
document.addEventListener('change', event => {
  if (event.target.closest('#multi-input-workbench')) audioReview.sync();
  stockReview.sync();
  videoReview.sync();
  variantFamilies.sync();
  variantNarration?.sync();
  videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();
});
const publishingConsole = initializePublishingConsole({api, getState: () => state, publicationPayload,
  setPublication: publication => {
    state.activePublication = publication;
    state.publications = [publication, ...state.publications.filter(row => row.publication_id !== publication.publication_id)];
    renderPublishing();
  }, toast});
const analyticsConsole = initializeAnalyticsConsole({api, getState: () => state, toast,
  onReport: report => {
    state.analyticsReport = report; state.activeAnalyticsSync = report?.latest_sync ?? null; renderAnalytics();
    if (['scheduled', 'queued', 'running', 'retry_scheduled'].includes(state.activeAnalyticsSync?.status)) startAnalyticsPolling();
    else stopAnalyticsPolling();
  },
  onQueued: sync => {state.activeAnalyticsSync = sync; renderAnalytics(); startAnalyticsPolling();}});
const analyticsChannels = initializeAnalyticsChannels({api, getState: () => state, toast});
const analyticsRefresh = initializeAnalyticsRefresh({api, getState: () => state, toast});
const channelLearning = initializeChannelLearning({api, getState: () => state, toast, onTemplateSelection: reference => {
  const template = state.subtitleCatalog?.templates.find(item => item.template_ref === reference);
  const option = [...$('#subtitle-template').options].find(item => item.value === reference);
  if (!template || !option || option.disabled) throw new Error('Template hoặc thời gian từng từ chưa sẵn sàng.');
  $('#subtitle-template').value = reference;
  $('#subtitle-animation').value = template.style.animation; $('#subtitle-position').value = template.style.position;
  $('#subtitle-font-size').value = template.style.font_size; $('#subtitle-safe-margin').value = template.style.safe_margin_percent;
  updateSubtitleAlignment();
}});
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function api(path, options = {}) {
  const {videoWordAdmission:admission,audioProcessingAdmission:processingAdmission,sourceLinkedAdmission:linkedAdmission,manualReframeAdmission:manualAdmission,brollPlanAdmission:brollAdmission,brollTimelineAdmission:placementAdmission,brollInternalAdmission:internalAdmission,...requestOptions}=options;
  if(!['GET','HEAD'].includes((requestOptions.method??'GET').toUpperCase())&&brollPlanHeld()&&brollAdmission!==brollPlanAdmission&&placementAdmission!==brollTimelineAdmission&&internalAdmission!==brollInternalAdmission)
    throw Error('Lưu/bỏ lựa chọn B-roll hoặc đối chiếu lần chuẩn bị đang giữ trước khi sửa phần khác.');
  if(!['GET','HEAD'].includes((requestOptions.method??'GET').toUpperCase())&&manualReframeHeld()&&manualAdmission!==manualReframeAdmission)
    throw Error('Lưu/bỏ đường crop hoặc đối chiếu yêu cầu đang giữ trước khi sửa phần khác.');
  if(!['GET','HEAD'].includes((requestOptions.method??'GET').toUpperCase())&&sourceLinkedHeld()&&linkedAdmission!==sourceLinkedAdmission)
    throw Error('Đối chiếu lần chỉnh shot đang giữ trước khi sửa phần khác.');
  if(!['GET','HEAD'].includes((requestOptions.method??'GET').toUpperCase())&&audioProcessingHeld()&&processingAdmission!==audioProcessingAdmission)
    throw Error('Lưu/bỏ cấu hình âm thanh hoặc đối chiếu yêu cầu đang giữ trước khi sửa phần khác.');
  if(!['GET','HEAD'].includes((requestOptions.method??'GET').toUpperCase())&&videoWordsHeld()&&admission!==videoWordAdmission)
    throw new ApiError('Lưu/bỏ bản sửa từ hoặc đối chiếu yêu cầu đang giữ trước khi thay đổi dự án.',409,{});
  const response = await authenticatedFetch(path, {
    ...requestOptions,
    headers: { "Content-Type": "application/json", ...(requestOptions.headers ?? {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail ?? {};
    const message = detail?.error?.message ?? detail?.message ?? body?.message ?? `API ${response.status}`;
    throw new ApiError(message, response.status, detail);
  }
  return response.status === 204 ? null : response.json();
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show${error ? " error" : ""}`;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => { element.className = "toast"; }, 3200);
}

function setSaveStatus(label, tone = "safe") {
  const element = $("#save-status");
  element.textContent = label;
  element.className = `pill ${tone}`;
}

function sourceLinkedEditorState(){const value=sqlEditorState();return {...value,analysis:reviewedAnalysis(),
  busy:value.busy||variantFamilies.isBusy()||variantNarration?.isWorking()===true||videoWordReview?.isWorking()===true||sqlAudioProcessing?.isWorking()===true||manualReframeEditor?.isWorking()===true||brollPlanBusy,
  dirty:value.dirty||brollPlanHeld()||manualReframeHeld()||variantFamilies.isPending()||variantNarration?.isPending()===true||videoWordReview?.isDirty()===true||videoWordReview?.isPending()===true||sqlAudioProcessing?.isDirty()===true||sqlAudioProcessing?.isPending()===true};}
function syncSourceLinkedPeers(){audioReview.sync();stockReview.sync();videoReview.sync();variantFamilies.sync();variantNarration?.sync();videoWordReview?.sync();sqlAudioProcessing?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();}
function sourceLinkedEditorBoundary(){const v=sourceLinkedEditorState();return JSON.stringify([
  v.workspaceId,v.projectId,v.principal,sessionToken(),v.timeline,v.analysis,v.assets,v.analyses,v.mediaPlans,
  v.productionPackage,productionWorkbenchDraft(),audioWorkbenchDraft()]);}
function assertSourceLinkedBoundary(boundary){const v=sourceLinkedEditorState();
  if(v.busy||v.dirty||sourceLinkedEditorBoundary()!==boundary||v.principal?.human_write_enabled!==true
    ||!['editor','reviewer','owner'].includes(audioRole(v))
    ||!Number.isFinite(Date.parse(v.principal?.expires_at))||Date.parse(v.principal.expires_at)<=Date.now())
    throw Error('Nguồn, phiên hoặc bản sửa khác đã đổi; giữ lần chỉnh shot để đối chiếu.');}
async function refreshSourceLinkedReceipt(value,requestGuard){
  const guard=()=>{if(typeof requestGuard!=='function'||requestGuard()!==true)
    throw Error('Thiếu ràng buộc đồng bộ với đúng yêu cầu chỉnh shot đang giữ.');};guard();
  const boundary=sourceLinkedEditorBoundary(),current=sourceLinkedEditorState(),receipt=value.receipt,timeline=value.timeline;
  assertSourceLinkedBoundary(boundary);
  const parent=current.timeline?.current_version===value.parent_version;
  const result=current.timeline?.current_version===value.result_version;
  if(!current.timeline||value.workspace_id!==current.workspaceId||value.project_id!==current.projectId
    ||value.actor_ref!==current.principal?.subject||receipt?.actor_ref!==value.actor_ref
    ||receipt.workspace_id!==value.workspace_id||receipt.project_id!==value.project_id
    ||receipt.timeline_id!==current.timeline.timeline_id||timeline?.timeline_id!==current.timeline.timeline_id
    ||timeline.workspace_id!==value.workspace_id||timeline.project_id!==value.project_id
    ||receipt.parent_version_id!==value.parent_version_id||receipt.parent_version!==value.parent_version
    ||receipt.result_version!==value.result_version||value.result_version!==value.parent_version+1
    ||timeline.current_version!==value.result_version||!(parent||result)
    ||parent&&(current.timeline.current_version_id!==value.parent_version_id
      ||sqlAudioStable(current.timeline)!==sqlAudioStable(value.parent_timeline))
    ||result&&sqlAudioStable(current.timeline)!==sqlAudioStable(timeline)
    ||sqlAudioStable(receipt.requested_operations)!==sqlAudioStable(value.requested_operations)
    ||sqlAudioStable(receipt.applied_operations)!==sqlAudioStable(value.applied_operations))
    throw Error('Biên nhận chỉnh shot chưa khớp nguồn, người sửa và phiên bản; không đổi CAS.');
  const path=`/api/v1/projects/${value.project_id}/timeline/source-linked-edit`;
  const proof=await api(path);guard();assertSourceLinkedBoundary(boundary);sourceLinkedRead(proof,sourceLinkedEditorState());
  if(sqlAudioStable(proof.timeline)!==sqlAudioStable(timeline)||sqlAudioStable(proof.receipt)!==sqlAudioStable(receipt))
    throw Error('Timeline hiện tại chưa chứng minh đúng lần chỉnh shot; giữ yêu cầu.');
  const versions=await api(`/api/v1/projects/${value.project_id}/timeline/versions`);guard();assertSourceLinkedBoundary(boundary);
  if(!videoWordHistoryMatches(versions,proof.timeline))throw Error('Lịch sử timeline chưa khớp lần chỉnh shot; giữ yêu cầu.');
  const previous=versions.find(row=>row.version===value.parent_version),head=versions.find(row=>row.version===value.result_version);
  if(previous?.timeline_version_id!==value.parent_version_id
    ||value.parent_timeline&&sqlAudioStable(previous.snapshot)!==sqlAudioStable(value.parent_timeline.snapshot)
    ||head?.actor_ref!==receipt.actor_ref||head.mutation?.type!=='source-linked-edit'
    ||head.mutation.source_media_mutated!==false||head.mutation.publish_requested!==false
    ||sqlAudioStable(head.mutation.receipt)!==sqlAudioStable(receipt))
    throw Error('Lịch sử timeline chưa khớp phiên bản gốc và biên nhận chỉnh shot; giữ yêu cầu.');
  const finalProof=await api(path);guard();assertSourceLinkedBoundary(boundary);sourceLinkedRead(finalProof,sourceLinkedEditorState());
  if(sqlAudioStable(finalProof.timeline)!==sqlAudioStable(proof.timeline)||sqlAudioStable(finalProof.receipt)!==sqlAudioStable(receipt))
    throw Error('Timeline hoặc biên nhận đã đổi sau khi đọc lịch sử; giữ yêu cầu.');
  guard();state.timeline=structuredClone(finalProof.timeline);state.versions=structuredClone(versions);
  state.selectedClipId=null;state.undoStack=[];state.redoStack=[];
  state.playhead=Math.min(state.playhead??0,state.timeline.snapshot.duration_seconds);
  if(state.preview)state.preview={...state.preview,status:'stale',valid_for_current_timeline:false};
  if(state.productionPackage)state.productionPackage={...state.productionPackage,current_for_timeline:false,
    approval:null,latest_review_render:null,latest_final_render:null};
  state.activeProductionRender=null;stopPreviewPolling();stopProductionPolling();render();
}
function sourceLinkedOperations(operations){
  if(state.timeline?.source_kind!=='video_analysis')return null;
  const selected=operations.map(operation=>getClip(state.timeline,operation.clip_id));
  const source=selection=>selection?.track.type==='video'&&selection.track.kind==='source';
  if(!selected.some(source))return null;
  if(!selected.every(source))throw Error('Chỉnh shot nguồn riêng với các lớp khác để giữ tiếng và phụ đề đồng bộ.');
  const result=[];
  for(let i=0;i<operations.length;i++){
    const operation=structuredClone(operations[i]),{track,clip}=selected[i];
    if(operation.target_track_id!==undefined){
      if(operation.type!=='move'||operation.target_track_id!==track.track_id)
        throw Error('Giữ shot nguồn trong lớp hình gốc khi di chuyển.');
      delete operation.target_track_id;
    }
    if(operation.type==='set_clip_properties'&&Object.hasOwn(operation,'volume')){
      if(operation.volume!==clip.volume)throw Error('Chọn lớp tiếng gốc để chỉnh âm lượng; thao tác này giữ phần tiếng đã sửa.');
      delete operation.volume;
    }
    if(operation.type==='trim'&&Object.hasOwn(operation,'timeline_start')){
      const position=operation.timeline_start;delete operation.timeline_start;result.push(operation);
      if(position!==clip.timeline_start)result.push({type:'move',clip_id:clip.clip_id,timeline_start:position});
    }else result.push(operation);
  }
  return result;
}
sourceLinkedEditor=initializeSqlSourceLinkedEdit({root:$('#sql-source-linked-edit'),
  api:(path,options={})=>api(path,{...options,sourceLinkedAdmission}),getState:sourceLinkedEditorState,
  getSessionToken:sessionToken,onMessage:toast,onSaved:refreshSourceLinkedReceipt,onBusyChanged:syncSourceLinkedPeers});

function activeAnalysis() {
  if (!state.timeline) return state.analyses.find((item) => item.status === "succeeded") ?? null;
  return state.analyses.find((item) => item.analysis_id === state.timeline.source_analysis_id) ?? null;
}
function reviewedAnalysis(){return selectedVideoReviewAnalysis(state,state.videoReviewSelection,activeAnalysis());}
async function syncTimelineTranscript(){
  const id=timelineTranscriptId(state.timeline),analysis=activeAnalysis();
  if(!id||!analysis||analysis.transcript?.transcript_id===id)return;
  const selected=await api(`/api/v1/projects/${state.projectId}/analyses/${analysis.analysis_id}?transcript_id=${encodeURIComponent(id)}`);
  state.analyses=state.analyses.map(item=>item.analysis_id===selected.analysis_id?selected:item);
}

function activeMediaPlan() {
  if (!state.timeline) return state.mediaPlans[0] ?? null;
  return state.mediaPlans.find((item) => item.media_plan_id === state.timeline.source_media_plan_id) ?? null;
}

function selectedClip() {
  return getClip(state.timeline, state.selectedClipId);
}

function manualReframeEditorState(){const value=sqlEditorState();return {...value,analysis:activeAnalysis(),
  busy:value.busy||variantFamilies.isBusy()||variantNarration?.isWorking()===true||videoWordReview?.isWorking()===true
    ||sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true,
  dirty:value.dirty||brollPlanHeld()||variantFamilies.isPending()||variantNarration?.isPending()===true||videoWordReview?.isDirty()===true
    ||videoWordReview?.isPending()===true||sqlAudioProcessing?.isDirty()===true||sqlAudioProcessing?.isPending()===true||sourceLinkedHeld()};}
function manualReframeContext(){const v=manualReframeEditorState();return sqlAudioStable([
  v.workspaceId,v.projectId,v.principal,sessionToken(),v.timeline,v.analysis,v.assets,v.analyses,v.mediaPlans,
  v.productionPackage,v.videoReviewSelection,productionWorkbenchDraft(),audioWorkbenchDraft()]);}
function manualReframeBoundary(){return sqlAudioStable([manualReframeContext(),manualReframeDraft()]);}
function assertManualReframeBoundary(boundary){const v=manualReframeEditorState();
  if(v.busy||v.dirty||manualReframeBoundary()!==boundary||v.principal?.human_write_enabled!==true
    ||!['editor','reviewer','owner'].includes(audioRole(v))||!Number.isFinite(Date.parse(v.principal?.expires_at))
    ||Date.parse(v.principal.expires_at)<=Date.now())throw Error('Nguồn, phiên hoặc bản sửa đã đổi; giữ đường crop để đối chiếu.');}
function manualReframeSettingsFromForm(){
  const number=(raw)=>{if(typeof raw!=='string'||!/^\d+(?:\.\d*)?(?:e[+-]?\d+)?$|^\.\d+(?:e[+-]?\d+)?$/i.test(raw.trim()))
    throw Error('Điền đủ mốc giây, X/Y và zoom bằng số hữu hạn.');return Number(raw);};
  const rows=[...document.querySelectorAll('#manual-reframe-points tr')];
  return manualReframeSettings({aspect_ratio:$('#manual-reframe-aspect').value,points:rows.map(row=>{
    const read=field=>number(row.querySelector(`[data-manual-reframe-field="${field}"]`)?.value);
    return{time:read('time'),x:read('x')/100,y:read('y')/100,zoom:read('zoom')};
  })},manualReframeFormRead?.data.source.duration_seconds??0);
}
function renderManualReframePoints(settings){
  $('#manual-reframe-aspect').value=settings.aspect_ratio;
  $('#manual-reframe-points').innerHTML=settings.points.map((p,index)=>`<tr>${[
    ['time',p.time,'0',manualReframeFormRead.data.source.duration_seconds,'Giây nguồn'],['x',p.x*100,'0','100','X phần trăm'],
    ['y',p.y*100,'0','100','Y phần trăm'],['zoom',p.zoom,'1','4','Zoom']].map(([field,value,min,max,label])=>
    `<td><input type="number" step="any" min="${min}" max="${max}" data-manual-reframe-field="${field}" aria-label="${label} điểm ${index+1}" value="${value}"></td>`).join('')}
    <td><button type="button" data-manual-reframe-remove="${index}" aria-label="Xóa điểm ${index+1}">Xóa</button></td></tr>`).join('');
}
function clearManualReframeForm(){manualReframeFormRead=null;manualReframeFormBaseline=null;
  $('#manual-reframe-points').innerHTML='';$('#manual-reframe-aspect').value='9:16';}
function syncManualReframeForm(){
  const dirty=manualReframeDirty();
  if(manualReframeFormRead&&manualReframeFormRead.context!==manualReframeContext()&&!dirty)clearManualReframeForm();
  const value=manualReframeEditorState(),valid=manualReframeFormRead?.context===manualReframeContext();
  const busy=manualReframeEditor?.isWorking()===true||manualReframeEditor?.isPending()===true||manualReframeApplying!==null;
  const write=value.principal?.human_write_enabled===true&&['editor','reviewer','owner'].includes(audioRole(value))
    &&Number.isFinite(Date.parse(value.principal?.expires_at))&&Date.parse(value.principal.expires_at)>Date.now();
  $('#manual-reframe-fields').disabled=!valid||busy||value.busy||value.dirty||!write;
  $('#manual-reframe-discard').disabled=!dirty||busy;
  $('#manual-reframe-add').disabled=!valid||busy||value.busy||value.dirty||!write
    ||document.querySelectorAll('#manual-reframe-points tr').length>=200;
  $('#manual-reframe-form-status').textContent=busy?'Đang giữ lần chỉnh crop; đối chiếu đúng yêu cầu trước khi thay đổi.':
    !valid?'Đọc trạng thái hiện tại trước khi chỉnh các điểm crop.':dirty?'Có bản sửa crop chưa gửi. Lưu hoặc bỏ bản sửa trước khi sửa phần khác.':
    `Timeline v${value.timeline.current_version} · ${manualReframeFormRead.data.source.duration_seconds} giây nguồn · ${manualReframeFormRead.data.source.width}×${manualReframeFormRead.data.source.height}. ${manualReframeFormRead.data.settings===null?'Chưa có đường crop thủ công được lưu; điểm giữa là gợi ý để bắt đầu.':'Đã đọc đường crop thủ công đã lưu.'} Cần kiểm tra preview trước khi duyệt.`;
}
function syncManualReframePeers(){audioReview.sync();stockReview.sync();videoReview.sync();variantFamilies.sync();
  variantNarration?.sync();videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();syncManualReframeForm();syncBrollPlanForm();}
function readManualReframeForm(data){
  if(manualReframeDirty())throw Error('Lưu hoặc bỏ bản sửa crop trước khi đọc và điền lại biểu mẫu.');
  const v=manualReframeEditorState();
  if(v.busy||v.dirty)throw Error('Hoàn tất bản sửa khác trước khi đọc crop.');
  manualReframeRead(data,v);
  if(sqlAudioStable(data.timeline)!==sqlAudioStable(v.timeline))throw Error('Đọc đúng timeline hiện tại trước khi chỉnh crop.');
  manualReframeFormRead={data:structuredClone(data),context:manualReframeContext()};
  renderManualReframePoints(data.settings??{aspect_ratio:data.timeline.snapshot.aspect_ratio??'9:16',points:[{time:0,x:.5,y:.5,zoom:1}]});
  manualReframeFormBaseline=manualReframeDraft();syncManualReframePeers();
}
async function manualReframeApi(path,options={}){
  const expectedPath=`/api/v1/projects/${state.projectId}/timeline/manual-reframe`,method=(options.method??'GET').toUpperCase();
  if(path!==expectedPath||!['GET','PUT'].includes(method))throw Error('Lệnh crop chỉ được đọc hoặc lưu trên dự án hiện tại.');
  const applying=manualReframeApplying;
  const current=()=>applying===null||manualReframeApplying===applying&&manualReframeContext()===applying.context&&manualReframeDraft()===applying.draft;
  if(!current())throw Error('Biểu mẫu hoặc nguồn crop đã đổi trước khi gửi.');
  const data=await api(path,{...options,manualReframeAdmission});
  if(!current()||applying&&data.source_binding_sha256!==applying.source_binding_sha256)
    throw Error('Ràng buộc nguồn đã đổi sau lần đọc; đọc lại trước khi chỉnh, không đổi CAS tự động.');
  return data;
}
function manualReframePreservedValue(timeline){const snapshot=structuredClone(timeline.snapshot);
  delete snapshot.width;delete snapshot.height;delete snapshot.aspect_ratio;delete snapshot.metadata.reframe;delete snapshot.metadata.manual_reframe;
  for(const track of snapshot.tracks)if(track.type==='video'&&track.kind==='source')for(const clip of track.clips){delete clip.crop;delete clip.metadata.reframe;}
  return{timeline_id:timeline.timeline_id,workspace_id:timeline.workspace_id,project_id:timeline.project_id,
    project_version_id:timeline.project_version_id,source_analysis_id:timeline.source_analysis_id,
    source_content_version_id:timeline.source_content_version_id,source_kind:timeline.source_kind,
    source_media_plan_id:timeline.source_media_plan_id,created_at:timeline.created_at,snapshot};
}
async function refreshManualReframe(value,requestGuard){
  const guard=()=>{if(typeof requestGuard!=='function'||requestGuard()!==true)
    throw Error('Thiếu ràng buộc đồng bộ với đúng yêu cầu crop đang giữ.');};guard();
  const boundary=manualReframeBoundary(),current=manualReframeEditorState(),receipt=value.receipt,timeline=value.timeline;
  assertManualReframeBoundary(boundary);
  const parent=current.timeline?.current_version===value.parent_version,result=current.timeline?.current_version===value.result_version;
  const read={timeline,source:value.source,source_binding_sha256:value.source_binding_sha256,settings:value.settings,receipt,replayed:false};
  manualReframeRead(read,current);
  if(!current.timeline||value.workspace_id!==current.workspaceId||value.project_id!==current.projectId
    ||value.actor_ref!==current.principal?.subject||receipt.actor_ref!==value.actor_ref
    ||receipt.parent_version_id!==value.parent_version_id||receipt.parent_version!==value.parent_version
    ||receipt.result_version!==value.result_version||value.result_version!==value.parent_version+1||!(parent||result)
    ||parent&&(current.timeline.current_version_id!==value.parent_version_id||sqlAudioStable(current.timeline)!==sqlAudioStable(value.parent_timeline))
    ||result&&sqlAudioStable(current.timeline)!==sqlAudioStable(timeline)
    ||sqlAudioStable(manualReframePreservedValue(current.timeline))!==sqlAudioStable(manualReframePreservedValue(timeline))
    ||sqlAudioStable(receipt.settings)!==sqlAudioStable(value.settings)||sqlAudioStable(receipt.applied_keyframes)!==sqlAudioStable(value.applied_keyframes)
    ||manualReframeApplying&&(manualReframeApplying.context!==manualReframeContext()||manualReframeApplying.draft!==manualReframeDraft()
      ||manualReframeApplying.source_binding_sha256!==value.source_binding_sha256))
    throw Error('Biên nhận crop chưa giữ đúng nguồn, âm thanh, phụ đề, người sửa hoặc phiên bản.');
  const path=`/api/v1/projects/${value.project_id}/timeline/manual-reframe`;
  const proof=await api(path);guard();assertManualReframeBoundary(boundary);manualReframeRead(proof,manualReframeEditorState());
  if(sqlAudioStable(proof)!==sqlAudioStable(read)){
    const withoutReplay=object=>({...object,replayed:false});
    if(sqlAudioStable(withoutReplay(proof))!==sqlAudioStable(read))throw Error('Bản đọc crop hiện tại chưa khớp biên nhận.');
  }
  const versions=await api(`/api/v1/projects/${value.project_id}/timeline/versions`);guard();assertManualReframeBoundary(boundary);
  if(!videoWordHistoryMatches(versions,proof.timeline))throw Error('Lịch sử crop chưa khớp timeline hiện tại.');
  const previous=versions.find(v=>v.version===value.parent_version),head=versions.find(v=>v.version===value.result_version);
  if(previous?.timeline_version_id!==value.parent_version_id||value.parent_timeline&&sqlAudioStable(previous.snapshot)!==sqlAudioStable(value.parent_timeline.snapshot)
    ||head?.actor_ref!==receipt.actor_ref||head.mutation?.type!=='manual-reframe'||head.mutation.source_media_mutated!==false
    ||head.mutation.publish_requested!==false||sqlAudioStable(head.mutation.receipt)!==sqlAudioStable(receipt))
    throw Error('Lịch sử crop chưa chứng minh đúng bản cha, người sửa và biên nhận.');
  const finalProof=await api(path);guard();assertManualReframeBoundary(boundary);manualReframeRead(finalProof,manualReframeEditorState());
  if(sqlAudioStable({...finalProof,replayed:false})!==sqlAudioStable({...proof,replayed:false}))throw Error('Crop đã đổi sau khi đọc lịch sử; giữ yêu cầu.');
  guard();state.timeline=structuredClone(finalProof.timeline);state.versions=structuredClone(versions);state.selectedClipId=null;state.undoStack=[];state.redoStack=[];
  state.playhead=Math.min(state.playhead??0,state.timeline.snapshot.duration_seconds);
  if(state.preview)state.preview={...state.preview,status:'stale',valid_for_current_timeline:false};
  if(state.productionPackage)state.productionPackage={...state.productionPackage,current_for_timeline:false,approval:null,latest_review_render:null,latest_final_render:null};
  state.activeProductionRender=null;stopPreviewPolling();stopProductionPolling();
  manualReframeFormRead={data:structuredClone(finalProof),context:manualReframeContext()};renderManualReframePoints(finalProof.settings);
  manualReframeFormBaseline=manualReframeDraft();render();
}
manualReframeEditor=initializeSqlManualReframe({root:$('#sql-manual-reframe'),api:manualReframeApi,getState:manualReframeEditorState,
  getSessionToken:sessionToken,onRead:readManualReframeForm,onSaved:refreshManualReframe,onBusyChanged:syncManualReframePeers,onMessage:toast});
$('#manual-reframe-form').addEventListener('submit',async event=>{
  event.preventDefault();if(manualReframeApplying)return;
  try{
    const boundary=manualReframeBoundary();assertManualReframeBoundary(boundary);
    if(manualReframeEditor.isWorking()||manualReframeEditor.isPending()||manualReframeFormRead?.context!==manualReframeContext())
      throw Error('Đọc đúng trạng thái crop hiện tại và hoàn tất yêu cầu đang giữ trước khi lưu.');
    const settings=manualReframeSettingsFromForm();
    manualReframeApplying=Object.freeze({context:manualReframeContext(),draft:manualReframeDraft(),source_binding_sha256:manualReframeFormRead.data.source_binding_sha256});
    syncManualReframePeers();const saved=await manualReframeEditor.runSettings(settings,{acknowledged:true});
    setSaveStatus(saved?'Đã lưu':manualReframeEditor.isPending()?'Cần đối chiếu':'Chưa lưu',saved?'safe':'warning');
  }catch(error){toast(error.message,true);}finally{manualReframeApplying=null;syncManualReframePeers();}
});
$('#manual-reframe-form').addEventListener('input',syncManualReframePeers);
$('#manual-reframe-aspect').addEventListener('change',syncManualReframePeers);
$('#manual-reframe-add').addEventListener('click',()=>{
  try{
    if($('#manual-reframe-fields').disabled)throw Error('Đọc trạng thái crop trước khi thêm điểm.');
    const settings=manualReframeSettingsFromForm(),last=settings.points.at(-1),duration=manualReframeFormRead.data.source.duration_seconds;
    if(settings.points.length>=200||last.time>=duration)throw Error('Đã tới giới hạn điểm hoặc hết thời lượng nguồn.');
    settings.points.push({...last,time:Math.min(duration,last.time+1)});renderManualReframePoints(settings);syncManualReframePeers();
  }catch(error){toast(error.message,true);}
});
$('#manual-reframe-points').addEventListener('click',event=>{
  const button=event.target.closest('[data-manual-reframe-remove]');if(!button)return;
  try{
    if($('#manual-reframe-fields').disabled)throw Error('Chờ thao tác crop hoàn tất trước khi xóa điểm.');
    const settings=manualReframeSettingsFromForm(),index=Number(button.dataset.manualReframeRemove);
    if(!Number.isSafeInteger(index)||index<0||index>=settings.points.length||settings.points.length<=1)throw Error('Giữ ít nhất một điểm crop.');
    settings.points.splice(index,1);renderManualReframePoints(settings);syncManualReframePeers();
  }catch(error){toast(error.message,true);}
});
$('#manual-reframe-discard').addEventListener('click',()=>{
  if(manualReframeEditor.isWorking()||manualReframeEditor.isPending()||manualReframeApplying)return toast('Giữ yêu cầu chưa rõ kết quả; đối chiếu trước khi bỏ bản sửa.',true);
  const read=manualReframeFormRead?.context===manualReframeContext()?structuredClone(manualReframeFormRead.data):null;
  clearManualReframeForm();if(read)readManualReframeForm(read);syncManualReframePeers();
});

function brollPlanEditorState(){const v=sqlEditorState();return {...v,analysis:activeAnalysis(),
  learning_snapshot_id:channelLearning.advice().learning_snapshot_id??null,
  busy:v.busy||variantFamilies.isBusy()||variantNarration?.isWorking()===true||videoWordReview?.isWorking()===true
    ||sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true,
  dirty:v.dirty||variantFamilies.isPending()||variantNarration?.isPending()===true||videoWordReview?.isDirty()===true
    ||videoWordReview?.isPending()===true||sqlAudioProcessing?.isDirty()===true||sqlAudioProcessing?.isPending()===true||sourceLinkedHeld()||manualReframeHeld()||brollTimelineHeld()||brollInternalHeld()};}
function brollPlanContext(){const v=brollPlanEditorState();return sqlAudioStable([v.workspaceId,v.workspaceSlug,v.projectId,v.principal,sessionToken(),
  v.timeline,v.analysis,v.assets,v.analyses,v.versions,v.preview,v.productionPackage,v.videoReviewSelection,v.learning_snapshot_id,
  productionWorkbenchDraft(),audioWorkbenchDraft()]);}
function assertBrollPlanOperation(op){const v=brollPlanEditorState();
  if(brollPlanOperation!==op||brollPlanContext()!==op.context||brollPlanDraft()!==op.draft||v.busy||v.dirty
    ||['recover-inspect','abandon'].includes(op.kind)&&sqlAudioStable([state.mediaPlans,state.selectedBrollPlanId])!==op.plans
    ||!Number.isFinite(Date.parse(v.principal?.expires_at))||Date.parse(v.principal.expires_at)<=Date.now()
    ||!['viewer','editor','reviewer','owner'].includes(audioRole(v))
    ||op.write&&(v.principal.human_write_enabled!==true||!['editor','reviewer','owner'].includes(audioRole(v))))
    throw Error('Nguồn, phiên hoặc lựa chọn B-roll đã đổi; giữ đúng yêu cầu để đối chiếu.');
}
function brollPlanSettingsFromForm(){
  const choices=[['user_asset','user'],['internal_library','library'],['licensed_stock','stock']]
    .filter(([,name])=>$('#broll-plan-'+name).checked).map(([tier,name])=>({tier,order:$('#broll-plan-'+name+'-order').value}));
  if(choices.some(v=>!['1','2','3'].includes(v.order))||new Set(choices.map(v=>v.order)).size!==choices.length)
    throw Error('Mỗi nguồn đã chọn cần thứ tự khác nhau từ 1 đến 3.');
  return brollPlanSettings({allow_stock:choices.some(v=>v.tier==='licensed_stock'),allow_ai_image:false,allow_ai_video:false,max_ai_cost_vnd:'0',
    resolver_priority:choices.sort((a,b)=>Number(a.order)-Number(b.order)).map(v=>v.tier)});
}
function renderBrollPlanSettings(value){
  const settings=brollPlanSettings(value);
  for(const [tier,name,index] of [['user_asset','user',1],['internal_library','library',2],['licensed_stock','stock',3]]){
    $('#broll-plan-'+name).checked=settings.resolver_priority.includes(tier);
    $('#broll-plan-'+name+'-order').value=String(settings.resolver_priority.includes(tier)?settings.resolver_priority.indexOf(tier)+1:index);
  }
  $('#broll-plan-acknowledge').checked=false;$('#broll-plan-abandon-acknowledge').checked=false;
}
function clearBrollPlanForm(){brollPlanFormRead=null;brollPlanFormBaseline=null;renderBrollPlanSettings(defaultBrollPlanSettings());}
function syncBrollPlanForm(){
  if(brollPlanFormRead&&brollPlanFormRead.binding!==brollPlanContext()&&!brollPlanDirty()&&!brollPlanBusy)clearBrollPlanForm();
  const v=brollPlanEditorState(),c=brollPlanController?.state(),held=brollPlanStored()||c?.pending!==null&&c?.pending!==undefined;
  const valid=brollPlanFormRead?.binding===brollPlanContext(),readable=!v.busy&&!v.dirty&&Number.isFinite(Date.parse(v.principal?.expires_at))
    &&Date.parse(v.principal.expires_at)>Date.now()&&['viewer','editor','reviewer','owner'].includes(audioRole(v));
  const writable=readable&&v.principal?.human_write_enabled===true&&['editor','reviewer','owner'].includes(audioRole(v));
  $('#broll-plan-fields').disabled=!valid||brollPlanBusy||held||!writable;
  $('#broll-plan-read').disabled=brollPlanBusy||held||brollPlanDirty()||!readable;
  $('#broll-plan-prepare').disabled=brollPlanBusy||held||!valid||!writable||!brollPlanFormRead?.context.can_prepare;
  $('#broll-plan-reconcile').disabled=brollPlanBusy||!held||!readable;
  $('#broll-plan-resend').disabled=brollPlanBusy||!held||c?.mayResend!==true||!writable;
  $('#broll-plan-discard').disabled=brollPlanBusy||held||!brollPlanDirty();
  $('#broll-plan-recovery-read').disabled=brollPlanBusy||!held||!writable;
  $('#broll-plan-abandon').disabled=brollPlanBusy||!held||!writable||!c?.recovery;
  $('#broll-plan-abandon-acknowledge').disabled=brollPlanBusy||!held||!writable;
  $('#broll-plan-recovery').textContent=c?.recovery?`Server: ${c.recovery.state==='settled'?'đã ghi nhận dừng':'đã đối chiếu'}. ${c.recovery.preserved_plan?'Kế hoạch gốc được giữ; đây là ảnh chụp lịch sử, không thay thế tiến trình hiện tại.':'Chưa có kế hoạch trong biên nhận gốc.'} Chưa gỡ bản ghi đang giữ cho tới khi xác minh dừng thành công.`:'';
  $('#broll-plan-acknowledge').disabled=brollPlanBusy||!writable;
  $('#broll-plan-stock').disabled=!valid||held||brollPlanBusy||!writable||brollPlanFormRead.context.licensed_stock_enabled!==true;
  $('#broll-plan-availability').textContent=!valid?'Đọc nguồn để xem khả năng stock hiện tại. AI tắt · ngân sách AI 0 VND.':
    `Tư liệu tải lên / thư viện: có thể chọn. Stock chính thức miễn phí: ${brollPlanFormRead.context.licensed_stock_enabled?'đã cấu hình; cần chọn rõ':'chưa khả dụng'}. AI tắt · ngân sách AI 0 VND. Gợi ý học: ${v.learning_snapshot_id??'không dùng'}.`;
  $('#broll-plan-pending').textContent=c?.pending?JSON.stringify({request_key:c.pending.body?.request_key,settings:c.pending.body?.settings,
    learning_snapshot_id:c.pending.body?.learning_snapshot_id},null,2):held?'Có bản ghi đang giữ trong phiên; chỉ đối chiếu, không tạo lần mới.':'';
}
function syncBrollPlanPeers(){audioReview.sync();stockReview.sync();videoReview.sync();variantFamilies.sync();variantNarration?.sync();
  videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();
  if(brollTimelineController){brollTimelineController.sync();syncBrollTimelineForm();}
  if(brollInternalController){brollInternalController.sync();syncBrollInternalForm();}}
async function brollPlanApi(path,options={}){
  const op=brollPlanOperation;if(!op)throw Error('B-roll chỉ đọc/gửi sau thao tác rõ ràng.');assertBrollPlanOperation(op);
  const route=`/api/v1/projects/${state.projectId}/broll-plan-review`,method=(options.method??'GET').toUpperCase();
  const requestRead=path.startsWith(route+'/requests/')&&/^[A-Za-z0-9_-]{8,128}$/.test(path.slice((route+'/requests/').length));
  const settlementRead=path.startsWith(route+'/recovery/settlements/')&&/^sop_[a-f0-9]{32}$/.test(path.slice((route+'/recovery/settlements/').length));
  const recoveryPost=method==='POST'&&(op.kind==='recover-inspect'&&path===route+'/recovery/inspect'||op.kind==='abandon'&&path===route+'/recovery/abandon');
  if(!(method==='GET'&&(path==='/api/v1/auth/session'||path===route||requestRead||settlementRead)||method==='POST'&&path===route&&['prepare','resend'].includes(op.kind)||recoveryPost))
    throw Error('Lệnh B-roll chỉ chuẩn bị hoặc đối chiếu đúng yêu cầu; không áp dụng hay gọi provider.');
  if(method==='POST'){
    const body=JSON.parse(options.body),pending=brollPlanController.state().pending;
    if(!op.write||!pending)throw Error('Thiếu yêu cầu đang giữ cho thao tác B-roll.');
    const key='vf-broll-plan-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]);
    const raw=brollPlanStore.getItem(key);assertBrollPlanOperation(op);
    if(raw!==sqlAudioStable(pending))throw Error('Bản ghi đang giữ đã đổi; không gửi lại hoặc ghi đè yêu cầu khác.');
    if(recoveryPost){
      const keys=op.kind==='abandon'?['acknowledged','intent_json','intent_sha256','observation_sha256']:['intent_json','intent_sha256'];
      if(sqlAudioStable(Object.keys(body).sort())!==sqlAudioStable(keys.sort())||body.intent_json!==raw
        ||typeof body.intent_sha256!=='string'||!/^[a-f0-9]{64}$/.test(body.intent_sha256)
        ||op.kind==='abandon'&&(body.acknowledged!==true||$('#broll-plan-abandon-acknowledge').checked!==true
          ||body.observation_sha256!==brollPlanController.state().recovery?.observation_sha256))
        throw Error('Chỉ đối chiếu hoặc dừng đúng bản ghi cũ sau xác nhận riêng.');
    }else if(sqlAudioStable(body)!==sqlAudioStable(pending.body)
      ||op.kind==='prepare'&&(body.context_sha256!==brollPlanFormRead?.context.context_sha256
        ||sqlAudioStable(body.settings)!==sqlAudioStable(brollPlanSettingsFromForm())))
      throw Error('Yêu cầu B-roll phải giữ nguyên lựa chọn và mã lần chuẩn bị.');
    assertBrollPlanOperation(op);
  }
  const value=await api(path,{...options,brollPlanAdmission});assertBrollPlanOperation(op);return value;
}
const brollPlanObservedStorage=new Map();
const brollPlanStorage={
  getItem(key){const op=brollPlanOperation;if(!op||!brollPlanStore)throw Error('Chưa có nơi giữ yêu cầu B-roll an toàn.');assertBrollPlanOperation(op);
    const value=brollPlanStore.getItem(key);assertBrollPlanOperation(op);brollPlanObservedStorage.set(key,value);return value;},
  setItem(key,value){const op=brollPlanOperation;assertBrollPlanOperation(op);brollPlanStore.setItem(key,value);assertBrollPlanOperation(op);},
  compareAndRemoveItem(key,raw){const op=brollPlanOperation;assertBrollPlanOperation(op);
    const expected='vf-broll-plan-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]);
    if(op.kind!=='abandon'||key!==expected||typeof raw!=='string'||typeof brollPlanStore?.compareAndRemoveItem!=='function')return false;
    const result=brollPlanStore.compareAndRemoveItem(key,raw);assertBrollPlanOperation(op);return result===true;},
  removeItem(key){const op=brollPlanOperation;assertBrollPlanOperation(op);const raw=brollPlanObservedStorage.get(key);
    if(typeof raw!=='string'||typeof brollPlanStore?.compareAndRemoveItem!=='function'||!brollPlanStore.compareAndRemoveItem(key,raw))
      throw Error('Bản ghi B-roll đã đổi; giữ nguyên để kiểm tra.');
    assertBrollPlanOperation(op);brollPlanObservedStorage.delete(key);}
};
async function adoptPreparedBrollPlan(plan,receipt,requestGuard){
  const op=brollPlanOperation;assertBrollPlanOperation(op);const pending=brollPlanController.state().pending;
  if(!pending||receipt.request_key!==pending.body.request_key||receipt.context_sha256!==pending.context.context_sha256
    ||receipt.actor_ref!==state.principal.subject||receipt.workspace_id!==state.workspaceId||receipt.project_id!==state.projectId
    ||receipt.authority_sha256!==pending.context.authority_sha256||receipt.timeline_id!==state.timeline.timeline_id
    ||receipt.timeline_version!==state.timeline.current_version||receipt.timeline_version_id!==state.timeline.current_version_id
    ||sqlAudioStable(receipt.settings)!==sqlAudioStable(pending.body.settings)||sqlAudioStable(receipt.source)!==sqlAudioStable(pending.context.source)
    ||receipt.learning_snapshot_id!==pending.body.learning_snapshot_id||plan.workspace_id!==state.workspaceId||plan.project_id!==state.projectId
    ||plan.analysis_id!==activeAnalysis()?.analysis_id||plan.configuration?.purpose!=='supporting_broll')
    throw Error('Biên nhận chuẩn bị B-roll chưa khớp dự án, lựa chọn hoặc nguồn đang xem.');
  const plans=sqlAudioStable([state.mediaPlans,state.selectedBrollPlanId]);
  const pendingKey='vf-broll-plan-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]);
  const expectedRaw=sqlAudioStable(pending);
  const guard=()=>{assertBrollPlanOperation(op);if(typeof requestGuard!=='function'||requestGuard()!==true)throw Error('Quyền giữ yêu cầu B-roll đã kết thúc.');
    assertBrollPlanOperation(op);if(sqlAudioStable([state.mediaPlans,state.selectedBrollPlanId])!==plans)
    throw Error('Danh sách đề xuất đã đổi trong lúc đối chiếu.');
    const raw=brollPlanStore.getItem(pendingKey);assertBrollPlanOperation(op);
    if(sqlAudioStable([state.mediaPlans,state.selectedBrollPlanId])!==plans)throw Error('Danh sách đề xuất đã đổi khi đọc bản ghi đang giữ.');
    if(raw!==expectedRaw)throw Error('Bản ghi B-roll đang giữ đã đổi; chưa nhận đề xuất vào dự án.');
    if(requestGuard()!==true)throw Error('Quyền giữ yêu cầu B-roll đã kết thúc.');assertBrollPlanOperation(op);
    if(sqlAudioStable([state.mediaPlans,state.selectedBrollPlanId])!==plans)throw Error('Danh sách đề xuất đã đổi sau đối chiếu cuối.');};
  guard();
  const base=`/api/v1/projects/${state.projectId}`;
  const proof=await api(`${base}/broll-plan-review/requests/${receipt.request_key}`,{cache:'no-store'});guard();
  if(proof?.schema_version!=='broll-plan-review-result.v1'||proof.state!=='prepared'||proof.preparation_provider_calls!==0
    ||proof.publishing_enabled!==false||proof.owner_approval_inferred!==false||proof.error_code!==null
    ||sqlAudioStable(proof.receipt)!==sqlAudioStable(receipt)||sqlAudioStable(proof.plan)!==sqlAudioStable(plan))
    throw Error('Bản đọc biên nhận B-roll chưa xác nhận đúng kết quả đã chuẩn bị.');
  const saved=await api(`${base}/media-plans/${plan.media_plan_id}`,{cache:'no-store'});guard();
  if(sqlAudioStable(saved)!==sqlAudioStable(plan))throw Error('Media Plan hiện tại chưa khớp biên nhận B-roll.');
  const context=await api(`${base}/broll-plan-review`,{cache:'no-store'});guard();validateBrollPlanContext(context,brollPlanEditorState());
  if(sqlAudioStable(context)!==sqlAudioStable(pending.context))throw Error('Nguồn hoặc cấu hình B-roll đã đổi; giữ yêu cầu để đối chiếu.');
  guard();
  state.mediaPlans=[structuredClone(saved),...state.mediaPlans.filter(v=>v.media_plan_id!==saved.media_plan_id)];state.selectedBrollPlanId=saved.media_plan_id;
  renderBrowser();stockReview.sync();
}
function brollRecoveryGuard(requestGuard){
  const op=brollPlanOperation;assertBrollPlanOperation(op);
  const plans=sqlAudioStable([state.mediaPlans,state.selectedBrollPlanId]);
  return()=>{assertBrollPlanOperation(op);
    if(typeof requestGuard!=='function'||requestGuard()!==true)throw Error('Quyền giữ yêu cầu khôi phục đã kết thúc.');
    assertBrollPlanOperation(op);
    if(sqlAudioStable([state.mediaPlans,state.selectedBrollPlanId])!==plans)throw Error('Danh sách hoặc lựa chọn đã đổi trong lúc khôi phục.');
    return true;};
}
async function readBrollRecovery(value,requestGuard){
  const guard=brollRecoveryGuard(requestGuard);guard();
  const context=await api(`/api/v1/projects/${state.projectId}/broll-plan-review`,{cache:'no-store'});guard();
  validateBrollPlanContext(context,brollPlanEditorState());
  if(context.context_sha256!==value.current_context_sha256||context.authority_sha256!==value.current_authority_sha256
    ||sqlAudioStable(context.source)!==sqlAudioStable(value.source))throw Error('Nguồn hoặc quyền trên server đã đổi trong lúc đối chiếu.');
  guard();return true;
}
async function settleBrollRecovery(value,requestGuard){
  const guard=brollRecoveryGuard(requestGuard);guard();
  const route=`/api/v1/projects/${state.projectId}/broll-plan-review/recovery/settlements/${value.settlement.settlement_id}`;
  const first=await api(route,{cache:'no-store'});guard();
  if(sqlAudioStable(first)!==sqlAudioStable(value))throw Error('Bản ghi dừng trên server chưa khớp.');
  await readBrollRecovery(value,guard);guard();
  const last=await api(route,{cache:'no-store'});guard();
  if(sqlAudioStable(last)!==sqlAudioStable(value))throw Error('Bản ghi dừng đã đổi khi đọc lại.');
  guard();return true;
}
brollPlanController=initializeBrollPlanReview({api:brollPlanApi,getState:brollPlanEditorState,getSessionToken:sessionToken,storage:brollPlanStorage,
  onPrepared:adoptPreparedBrollPlan,onRecoveryRead:readBrollRecovery,onRecovered:settleBrollRecovery,onStatus:text=>{$('#broll-plan-status').textContent=text;}});
async function runBrollPlanAction(kind){
  if(brollPlanBusy)return;
  try{
    syncBrollPlanForm();if(kind==='read'&&brollPlanDirty())throw Error('Bỏ lựa chọn chưa gửi trước khi đọc lại.');
    if(kind==='prepare'&&(brollPlanFormRead?.binding!==brollPlanContext()||brollPlanStored()))throw Error('Đọc đúng nguồn hiện tại và đối chiếu lần đang giữ trước khi chuẩn bị.');
    const op=Object.freeze({kind,write:['prepare','resend','recover-inspect','abandon'].includes(kind),context:brollPlanContext(),draft:brollPlanDraft(),
      plans:sqlAudioStable([state.mediaPlans,state.selectedBrollPlanId])});
    brollPlanOperation=op;assertBrollPlanOperation(op);
    const settings=kind==='prepare'?brollPlanSettingsFromForm():null;
    if(['prepare','resend'].includes(kind)&&$('#broll-plan-acknowledge').checked!==true)throw Error('Xác nhận rõ lựa chọn hoặc đúng yêu cầu đang giữ trước khi gửi.');
    if(kind==='abandon'&&$('#broll-plan-abandon-acknowledge').checked!==true)throw Error('Xác nhận dừng đúng yêu cầu cũ; kế hoạch và lịch sử vẫn được giữ.');
    brollPlanBusy=true;syncBrollPlanPeers();
    if(kind==='read'){
      const context=await brollPlanController.reload();assertBrollPlanOperation(op);
      brollPlanFormRead={context:structuredClone(context),binding:brollPlanContext()};renderBrollPlanSettings(defaultBrollPlanSettings());brollPlanFormBaseline=brollPlanDraft();
    }else{
      const result=await (kind==='prepare'?brollPlanController.prepare(settings,true):kind==='resend'?brollPlanController.resend(true):kind==='recover-inspect'?brollPlanController.inspectRecovery():kind==='abandon'?brollPlanController.abandonRecovery(true):brollPlanController.reconcile());
      assertBrollPlanOperation(op);if(result&&(['prepared','rejected'].includes(result.state)||kind==='abandon'&&result.state==='settled'))clearBrollPlanForm();
    }
  }catch(error){toast(error.detail?.error?.code==='BROLL_RECOVERY_IDENTITY_UNVERIFIABLE'
    ?'Chưa chứng minh được đúng phiên gốc. Yêu cầu chưa tới server hiện cần phiên gốc còn hiệu lực; giữ nguyên bản ghi để kiểm tra.'
    :error.message,true);}finally{brollPlanBusy=false;brollPlanOperation=null;syncBrollPlanPeers();}
}
for(const [id,kind] of [['broll-plan-read','read'],['broll-plan-prepare','prepare'],['broll-plan-reconcile','reconcile'],['broll-plan-resend','resend'],['broll-plan-recovery-read','recover-inspect'],['broll-plan-abandon','abandon']])
  $('#'+id).addEventListener('click',()=>runBrollPlanAction(kind));
$('#broll-plan-form').addEventListener('submit',event=>{event.preventDefault();});
$('#broll-plan-form').addEventListener('change',syncBrollPlanPeers);
$('#broll-plan-discard').addEventListener('click',()=>{
  if(brollPlanBusy||brollPlanStored()||brollPlanController.state().pending)return toast('Giữ lần chuẩn bị chưa rõ kết quả; đối chiếu trước khi bỏ lựa chọn.',true);
  const read=brollPlanFormRead?.binding===brollPlanContext()?brollPlanFormRead:null;
  clearBrollPlanForm();if(read){brollPlanFormRead=read;brollPlanFormBaseline=brollPlanDraft();}syncBrollPlanPeers();
});


async function loadProjectList() {
  multiInput.setBusy(true);
  try {
  const workspaces = await api("/api/v1/workspaces");
  state.workspaceId = workspaces[0]?.workspace_id ?? null;
  state.workspaceSlug = workspaces[0]?.slug ?? null;
  if (!state.workspaceId) {
    renderNoProject("Workspace chưa được khởi tạo.", "Tạo workspace và project trước khi mở Studio.");
    return;
  }
  state.projects = await api(`/api/v1/workspaces/${state.workspaceId}/projects`);
  const select = $("#project-select");
  select.innerHTML = state.projects.length
    ? state.projects.map((item) => `<option value="${escapeHtml(item.project_id)}">${escapeHtml(item.name)}</option>`).join("")
    : `<option value="">Chưa có dự án</option>`;
  const stored = window.localStorage.getItem("npd-studio-project");
  state.projectId = state.projects.some((item) => item.project_id === stored)
    ? stored
    : state.projects[0]?.project_id ?? null;
  select.value = state.projectId ?? "";
  if (!state.projectId) {
    renderNoProject("Chưa có project để dựng.", "Tạo draft project từ Trend Radar hoặc API trước khi mở Studio.");
    return;
  }
  await loadProject({initialRead:initialProjectRead});
  } finally {multiInput.setBusy(false);}
}

async function loadProject({ quiet = false, initialRead = null } = {}) {
  if (!state.projectId) return;
  const initialCanonicalRead=initialRead===initialProjectRead&&state.timeline===null&&state.projectLoading===0
    &&state.assets.length===0&&state.analyses.length===0&&state.versions.length===0&&state.transcriptDrafts.size===0
    &&!brollPlanBusy&&!brollPlanDirty()&&brollPlanOperation===null
    &&manualReframeEditor?.isWorking()!==true&&!manualReframeDirty()&&manualReframeApplying===null
    &&sourceLinkedEditor?.isWorking()!==true&&!brollInternalBusy&&!brollInternalDirty()&&brollInternalOperation===null&&!brollTimelineBusy&&!brollTimelineDirty()&&brollTimelineOperation===null&&sqlAudioProcessing?.isWorking()!==true
    &&videoWordReview?.isWorking()!==true&&variantNarration?.isWorking()!==true;
  if(!initialCanonicalRead&&brollPlanHeld()){toast('Lưu/bỏ lựa chọn B-roll hoặc đối chiếu lần chuẩn bị đang giữ trước khi tải lại.',true);return;}
  if(!initialCanonicalRead&&manualReframeHeld()){toast('Lưu/bỏ crop hoặc đối chiếu lần lưu đang giữ trước khi tải lại.',true);return;}
  if(!initialCanonicalRead&&sourceLinkedHeld()){toast('Đối chiếu lần chỉnh shot đang giữ trước khi tải lại.',true);return;}
  if(!initialCanonicalRead&&audioProcessingHeld()){toast('Lưu/bỏ cấu hình âm thanh hoặc đối chiếu yêu cầu đang giữ trước khi tải lại.',true);return;}
  if(!initialCanonicalRead&&videoWordsHeld()){toast('Lưu/bỏ bản sửa từ hoặc đối chiếu lần lưu chưa rõ kết quả trước khi tải lại.',true);return;}
  if (!initialCanonicalRead&&(variantNarration?.isWorking() || variantNarration?.isPending())) {
    toast('Chờ nhập/review giọng đọc hoàn tất hoặc đối chiếu yêu cầu cũ trước khi tải lại dự án.', true);return;
  }
  if (!initialCanonicalRead&&audioReview.isDirty()) {toast('Lưu/bỏ sửa hoặc đối chiếu yêu cầu audio trước khi tải lại dự án.', true); return;}
  if (!initialCanonicalRead&&stockReview.isPending()) {toast('Đối chiếu yêu cầu tìm tư liệu trong panel trước khi tải lại dự án.', true); return;}
  // A clean form from the previous project is invalidated before capturing the
  // read boundary. Dirty forms and UNKNOWN requests have already been fenced.
  syncManualReframeForm();syncBrollPlanForm();if(brollTimelineController)syncBrollTimelineForm();if(brollInternalController)syncBrollInternalForm();
  const loadedProjectId = state.projectId;
  const readBoundary=()=>JSON.stringify([state.workspaceId,state.projectId,state.principal,sessionToken(),
    [...state.transcriptDrafts],productionWorkbenchDraft(),audioWorkbenchDraft(),manualReframeDraft(),brollPlanDraft(),brollTimelineDraft(),brollInternalDraft()]);
  const expectedReadBoundary=readBoundary();
  const readCurrent=()=>readBoundary()===expectedReadBoundary
    &&(!state.principal?.expires_at||Date.parse(state.principal.expires_at)>Date.now());
  const canonicalBoundary=()=>JSON.stringify([state.timeline,state.assets,state.analyses,state.mediaPlans,state.versions,
    state.preview,state.productionPackage,state.selectedClipId,state.playhead,state.redoStack,state.undoStack]);
  const expectedCanonicalBoundary=canonicalBoundary();
  let installedBoundary=null;
  let installing=false;
  state.projectLoading++;
  $('#project-select').disabled = true;
  audioReview.sync();
  stockReview.sync();
  videoReview.sync();
  multiInput.setBusy(true);
  variantFamilies.sync();
  variantNarration?.sync();
  videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();
  stopPreviewPolling();
  stopProductionPolling();
  stopAnalyticsPolling();
  if (!quiet) setSaveStatus("Đang tải…", "muted");
  try {
    const read=async(path,{notFound,optional=false}={})=>{
      const value=await api(path).catch(error=>{
        if(optional||error.status===404&&notFound!==undefined)return optional?null:notFound;
        throw error;
      });
      if(!readCurrent()||canonicalBoundary()!==expectedCanonicalBoundary)throw Error('Ngữ cảnh tải dự án đã đổi.');
      return value;
    };
    const projectPath=`/api/v1/projects/${loadedProjectId}`;
    const [assets, analyses, mediaPlans, timeline, publications, publishingPlatforms, analyticsReport, analyticsProviders] = await Promise.all([
      read(`${projectPath}/assets`),read(`${projectPath}/analyses`),read(`${projectPath}/media-plans`),
      read(`${projectPath}/timeline`,{notFound:null}),read(`${projectPath}/publications`),
      read('/api/v1/publishing-platforms'),read(`${projectPath}/analytics`),read('/api/v1/analytics-providers'),
    ]);
    const versions=timeline?await read(`${projectPath}/timeline/versions`):[];
    const visionAnalyses=await read(`${projectPath}/vision-analyses`,{notFound:[]});
    const subtitleCatalog=await read(`${projectPath}/subtitle-templates`,{notFound:null});
    const sceneResponse=await read(`${projectPath}/scene-intelligence`,{notFound:null});
    let selectedAnalyses=analyses;
    const transcriptId=timelineTranscriptId(timeline);
    const analysis=timeline?analyses.find(item=>item.analysis_id===timeline.source_analysis_id):null;
    if(transcriptId&&analysis&&analysis.transcript?.transcript_id!==transcriptId){
      const selected=await read(`${projectPath}/analyses/${analysis.analysis_id}?transcript_id=${encodeURIComponent(transcriptId)}`);
      if(selected.analysis_id!==analysis.analysis_id||selected.transcript?.transcript_id!==transcriptId)
        throw Error('Bản transcript trả về chưa khớp timeline đã lưu.');
      selectedAnalyses=analyses.map(item=>item.analysis_id===selected.analysis_id?selected:item);
    }
    const highlightResponse=await read(`${projectPath}/highlight-drafts`,{notFound:null});
    const preview=timeline?.latest_preview_id?await read(`${projectPath}/previews/${timeline.latest_preview_id}`,{optional:true}):null;
    const productionPackage=timeline?await read(`${projectPath}/production-package`,{notFound:null}):null;
    const applyMultiInput=await multiInput.prepareReload({isCurrent:readCurrent});
    if(!readCurrent()||canonicalBoundary()!==expectedCanonicalBoundary)return;
    // All asynchronous reads finish before any canonical or workbench state is installed.
    // The workbench closure only hydrates staged data; it performs no further reads.
    installing=true;
    Object.assign(state, {
      assets,
      analyses:selectedAnalyses,
      mediaPlans,
      timeline,
      versions,visionAnalyses,subtitleCatalog,
      sceneIntelligenceSupported:sceneResponse!==null,sceneAssessments:sceneResponse??[],
      highlightSupported:highlightResponse!==null,highlightDrafts:highlightResponse??[],
      preview,productionPackage,
      activeProductionRender:productionPackage?.latest_final_render??productionPackage?.latest_review_render??null,
      publications,
      publishingPlatforms,
      activePublication: publications[0] ?? null,
      analyticsReport,
      analyticsProviders,
      activeAnalyticsSync: analyticsReport.latest_sync,
      selectedClipId: null,
      redoStack: [],
      publishRequestSignature: null,
      publishIdempotencyKey: null,
    });
    applyMultiInput();
    state.playhead = Math.min(state.playhead, timeline?.snapshot?.duration_seconds ?? 0);
    multiInputBaseline = audioWorkbenchDraft();
    render();
    installedBoundary=readBoundary();
    if (["queued", "running"].includes(state.preview?.status)) startPreviewPolling();
    if (["queued", "running"].includes(state.activeProductionRender?.status)) startProductionPolling();
    if (["scheduled", "queued", "running", "retry_scheduled"].includes(state.activeAnalyticsSync?.status)) startAnalyticsPolling();
    setSaveStatus("Đã lưu", "safe");
  } catch (error) {
    if(!installing&&(!readCurrent()||canonicalBoundary()!==expectedCanonicalBoundary))return;
    setSaveStatus("Lỗi tải", "danger");
    toast(error.message, true);
  } finally {
    multiInput.setBusy(false);
    state.projectLoading--;
    $('#project-select').disabled = state.projectLoading > 0;
    audioReview.sync();
    stockReview.sync();
    videoReview.sync();
    variantFamilies.sync();
    variantNarration?.sync();
  videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();
  }
  if (installedBoundary!==null&&readBoundary()===installedBoundary) {
    await audioReview.reload();
    if(readBoundary()===installedBoundary)await videoReview.reload();
  }
}

function renderNoProject(title, description) {
  audioReview.sync();
  stockReview.sync();
  videoReview.sync();
  variantFamilies.sync();
  variantNarration?.sync();
  videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();
  if (!state.projectId) $("#analysis-review").hidden = true;
  $("#multi-input-workbench").open = !state.projectId || !state.assets.length;
  $("#studio-workspace").hidden = true;
  $("#empty-state").hidden = false;
  $("#empty-title").textContent = title;
  $("#empty-description").textContent = description;
  $("#create-timeline-button").hidden = true;
}

function render() {
  audioReview.sync();
  stockReview.sync();
  variantFamilies.sync();
  variantNarration?.sync();
  videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();
  renderAnalysisReview();
  renderReframe();
  if (!state.timeline) {
    const analysis = reviewedAnalysis();
    renderNoProject(
      analysis ? "Kết quả phân tích đã sẵn sàng." : "Tạo storyboard từ ảnh/text ở workbench đa đầu vào.",
      analysis
        ? "Khởi tạo timeline từ scene, transcript, khoảng lặng và B-roll đã lưu."
        : "Chọn media, sửa và duyệt script/storyboard; video có lời nói cần analysis/ASR hợp lệ.",
    );
    $("#create-timeline-button").hidden = !analysis;
    return;
  }
  $("#empty-state").hidden = true;
  $("#studio-workspace").hidden = false;
  renderSummary();
  renderBrowser();
  renderTimeline();
  renderInspector();
  renderPreview();
  renderProduction();
  renderPublishing();
  renderAnalytics();
  const sourceShots=canonicalShotClips(state.timeline.snapshot);
  $("#canonical-shot-list").innerHTML=sourceShots.map((clip,index)=>`<button type="button" data-canonical-shot="${escapeHtml(clip.clip_id)}" aria-pressed="${state.selectedClipId===clip.clip_id}"><strong>Shot ${index+1}</strong><span>${escapeHtml(clip.label)}</span><small>${formatTime(clip.timeline_start)} · ${clip.duration.toFixed(1)} giây${clip.disabled?' · Đã tắt':''}</small></button>`).join('');
}

function renderReframe(){
  if(state.timeline?.snapshot){
    const snapshot=state.timeline.snapshot,selector=$('#final-profile');
    const canvasBinding=JSON.stringify([state.workspaceId,state.projectId,state.timeline.workspace_id,state.timeline.project_id,
      snapshot.width,snapshot.height,snapshot.fps,snapshot.aspect_ratio??snapshot.metadata?.reframe?.aspect_ratio]);
    if(selector.dataset.canvasBinding!==canvasBinding){
      selector.value=reframeProfiles(snapshot).final;
      selector.dataset.canvasBinding=canvasBinding;
    }
  }
  const source=activeAnalysis();
  $('#reframe-review').hidden=!state.timeline?.source_analysis_id||!source;
  if($('#reframe-review').hidden)return;
  const binding=state.timeline.snapshot.metadata.reframe;
  $('#reframe-aspect').value=binding?.aspect_ratio??'9:16';
  $('#reframe-vision').innerHTML='<option value="">Cắt giữa · cần kiểm tra</option>'+matchingVision(state.visionAnalyses,source).map(item=>
    `<option value="${escapeHtml(item.vision_analysis_id)}">${escapeHtml(item.provider_key)} · ${escapeHtml(item.model)} · ${item.frames.length} khung hình</option>`).join('');
  $('#reframe-vision').value=binding?.vision_analysis_id??'';
  $('#reframe-status').textContent=binding?`${binding.aspect_ratio} · ${binding.fallback==='center_crop'?'Cắt giữa':binding.strategy} · ${binding.needs_attention?'Cần kiểm tra chủ thể trong A/V review':'Xem A/V review trước khi duyệt'} · timeline v${state.timeline.current_version}`:'Chọn tỷ lệ và kết quả phân tích chủ thể đã lưu. Nếu chưa có, dùng cắt giữa và kiểm tra trong A/V review.';
}

function renderAnalysisReview(){
  const analysis=reviewedAnalysis();$("#analysis-review").hidden=!analysis;
  if(!analysis)return;
  const sourceName=state.assets.find(asset=>asset.asset_id===analysis.asset_id)?.filename??'Video nguồn';
  $("#analysis-review-summary").textContent=`${sourceName} · ${analysis.scenes.length} cảnh · ${analysis.transcript?.language??'Chưa có lời nhận diện'} · ${analysis.highlights.length} đoạn nổi bật${state.timeline&&state.timeline.source_analysis_id!==analysis.analysis_id?' · Đang xem video khác với timeline; áp dụng cắt sẽ tạo phiên bản timeline mới. Cần timeline của video này trước khi sửa lời nhận diện.':''}${analysis.provenance?.semantic_analysis_refresh_required?' · Nhãn ngữ nghĩa cần cập nhật sau khi sửa lời nhận diện':''}`;
  const previous=[...$("#silence-review-list").querySelectorAll('[data-silence-id]')];
  const selected=new Set(state.timeline?.snapshot.metadata.silence_review?.selected_ids??analysis.silence_decisions.filter(d=>d.enabled&&!d.conflicts_with_speech).map(d=>d.decision_id));
  const binding=`${state.projectId}:${analysis.analysis_id}:${state.timeline?.current_version??0}`;
  const preserved=new Map($("#silence-review-list").dataset.binding===binding?previous.map(input=>[input.dataset.silenceId,input.checked]):[]);
  $("#silence-review-list").dataset.binding=binding;
  $("#analysis-transcript-list").innerHTML=(analysis.transcript?.segments??[]).map(item=>transcriptReviewForm(item,analysis)).join('')||'<p>Chưa có lời nhận diện.</p>';
  const compatible=compatibleSceneAssessments(state.sceneAssessments,analysis);
  const assessment=compatible.find(item=>item.assessment_id===state.selectedSceneAssessmentId)??null;
  if(!assessment)state.selectedSceneAssessmentId='';
  $('#scene-assessment').innerHTML='<option value="">Phân tích nguồn ban đầu</option>'+compatible.map(item=>`<option value="${escapeHtml(item.assessment_id)}">${item.vision_analysis_id?'Có hiểu hình ảnh':'Transcript và đo tại máy'} · ${escapeHtml(new Date(item.created_at).toLocaleString('vi-VN'))}</option>`).join('');
  $('#scene-assessment').value=state.selectedSceneAssessmentId;
  const selectedVision=$('#scene-vision').value;
  $('#scene-vision').innerHTML='<option value="">Chỉ dùng transcript và đo tại máy</option>'+matchingVision(state.visionAnalyses,analysis).map(item=>`<option value="${escapeHtml(item.vision_analysis_id)}">${escapeHtml(item.provider_key)} · ${escapeHtml(item.model)} · ${item.frames.length} khung hình</option>`).join('');
  if(matchingVision(state.visionAnalyses,analysis).some(item=>item.vision_analysis_id===selectedVision))$('#scene-vision').value=selectedVision;
  $('#assess-scenes').disabled=!state.sceneIntelligenceSupported;
  $('#scene-assessment-status').textContent=assessment?`${assessment.scenes.length} cảnh · ${assessment.provenance.fixture_asr?'Transcript mô phỏng · ':''}${assessment.vision_analysis_id?'Hiểu hình ảnh đã lưu':'Chưa có hiểu hình ảnh'} · Highlight dùng bản đánh giá đang chọn. Tư liệu gốc được giữ nguyên.`:'Chọn bản đánh giá để dùng các chỉ số có bằng chứng cho highlight. Chưa có dữ liệu sẽ hiển thị rõ.';
  $("#analysis-scene-list").innerHTML=(assessment?.scenes??analysis.scenes).map(scene=>`<article><strong>Cảnh ${scene.ordinal+1} · ${formatTime(scene.start_seconds)} → ${formatTime(scene.end_seconds)}</strong><p>${escapeHtml(scene.semantic_label)} · ${escapeHtml(scene.description)}</p><small>${assessment?`${scene.evidence.vision_used?'Chất lượng từ hiểu hình ảnh':'Phơi sáng tại máy (heuristic)'}: ${sceneScore(scene.quality_score)} · Chuyển động pixel: ${sceneScore(scene.motion_score)} · Lời nói: ${sceneScore(scene.speech_score)} · ${scene.needs_attention?'Cần kiểm tra':''}`:`Độ tin cậy theo heuristic: ${sceneScore(scene.confidence)}`}</small>${assessment?`<p>${scene.subjects.length} phát hiện chủ thể từ hình ảnh · ${scene.evidence.frame_evidence.length} khung hình Vision · ${scene.evidence.local_metrics.sample_count} mẫu hình ảnh đo tại máy</p>`:''}</article>`).join('');
  $("#silence-review-list").innerHTML=analysis.silence_decisions.map(d=>`<label><input type="checkbox" data-silence-id="${escapeHtml(d.decision_id)}" ${(preserved.get(d.decision_id)??selected.has(d.decision_id))?'checked':''} ${d.enabled&&!d.conflicts_with_speech?'':'disabled'}>${formatTime(d.start_seconds)} → ${formatTime(d.end_seconds)} · ${d.conflicts_with_speech?'Giữ lại để bảo vệ lời nói':d.enabled?'Có thể đề xuất cắt':'Giữ lại'}</label>`).join('')||'<p>Không có khoảng lặng đủ điều kiện cắt.</p>';
  $("#highlight-review-list").innerHTML=analysis.highlights.map(h=>`<article><strong>Đề xuất ${h.rank} · ${(h.highlight_score*100).toFixed(0)}/100</strong><p>${formatTime(h.recommended_start)} → ${formatTime(h.recommended_end)}</p><p>${escapeHtml(h.reason)}</p></article>`).join('')||'<p>Chưa có đoạn nổi bật.</p>';
  $("#highlight-draft-list").innerHTML=state.highlightDrafts.filter(d=>d.analysis_id===analysis.analysis_id).map(d=>`<article><strong>Draft · ${d.snapshot.duration_seconds.toFixed(1)} giây · ${(d.evidence.score*100).toFixed(0)}/100</strong><p>${escapeHtml(d.evidence.reason)}</p><small>${d.evidence.fixture_asr?'Transcript mô phỏng · chưa nghiệm thu ASR':'Dựa trên transcript đã lưu'} · Giữ nguyên nguồn</small><button type="button" data-apply-highlight="${escapeHtml(d.draft_id)}">Chọn draft này cho timeline</button></article>`).join('')||'<p>Chưa tạo draft nổi bật.</p>';
  $("#analysis-review").querySelectorAll('[data-highlight-count],[data-highlight-mode]').forEach(button=>{button.disabled=!state.highlightSupported;});
}

function transcriptReviewForm(item,analysis){
  return `<article class="transcript-item"><button type="button" data-seek="${item.start_seconds}">${formatTime(item.start_seconds)} → ${formatTime(item.end_seconds)}</button>
    <form data-transcript-edit="${escapeHtml(item.segment_id)}" data-transcript-version="${analysis.transcript.version}" data-transcript-id="${escapeHtml(analysis.transcript.transcript_id)}" data-analysis-id="${escapeHtml(analysis.analysis_id)}">
    <label>Lời nhận diện · bản ${analysis.transcript.version}<textarea data-transcript-text="${escapeHtml(item.segment_id)}" required maxlength="4000">${escapeHtml(state.transcriptDrafts.get(item.segment_id)??item.text)}</textarea></label>
    <button type="submit">Lưu phiên bản mới</button><small>Sửa lời nhận diện giữ tệp gốc, yêu cầu duyệt lại và bỏ dấu thời gian từng từ của đoạn đã sửa.</small></form></article>`;
}

function renderSummary() {
  const clips = state.timeline.snapshot.tracks.flatMap((track) => track.clips);
  const analysis = activeAnalysis();
  const previewState = describePreview(state.preview, state.timeline.current_version);
  $("#metric-version").textContent = `v${state.timeline.current_version}`;
  $("#metric-version-note").textContent = `${state.versions.length} phiên bản đã lưu`;
  $("#metric-duration").textContent = formatTime(state.timeline.snapshot.duration_seconds);
  $("#metric-clips").textContent = clips.length;
  $("#metric-scenes").textContent = `${analysis?.scenes?.length ?? 0} cảnh có dữ liệu`;
  $("#metric-preview").textContent = previewState.label.split(" · ")[0];
  $("#metric-approval").textContent = describeApproval(currentProductionApproval(state.productionPackage)).label;
}

function renderBrowser() {
  document.querySelectorAll("[data-panel-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.panelTab === state.panelTab);
  });
  const query = state.query.trim().toLocaleLowerCase("vi");
  const matches = (value) => !query || String(value ?? "").toLocaleLowerCase("vi").includes(query);
  const panel = $("#browser-content");
  const analysis = activeAnalysis();
  if (state.panelTab === "media") {
    const assets = state.assets.filter((item) => matches(`${item.filename} ${item.kind} ${item.asset_class}`));
    panel.innerHTML = assets.length ? `<div class="browser-list">${assets.map((item) => `
      <button class="browser-item" data-asset-id="${escapeHtml(item.asset_id)}">
        <span class="browser-thumb">${item.content_type.startsWith("video/") ? "▶" : item.content_type.startsWith("image/") ? "▧" : "♪"}</span>
        <span><strong>${escapeHtml(item.filename)}</strong><small>${escapeHtml(item.kind)} · ${formatBytes(item.size_bytes)}</small></span>
      </button>`).join("")}</div>` : browserEmpty("Chưa có media phù hợp.");
  } else if (state.panelTab === "transcript") {
    const segments = (analysis?.transcript?.segments ?? []).filter((item) => matches(item.text));
    panel.innerHTML = segments.length ? segments.map(item=>transcriptReviewForm(item,analysis)).join("") : browserEmpty("Project chưa có transcript hoặc không khớp tìm kiếm.");
  } else if (state.panelTab === "scenes") {
    const scenes = (analysis?.scenes ?? []).filter((item) => matches(`${item.semantic_label} ${item.description}`));
    panel.innerHTML = scenes.length ? scenes.map((item) => `
      <article class="scene-item" data-seek="${item.start_seconds}"><time>Cảnh ${item.ordinal + 1} · ${formatTime(item.start_seconds)}</time><p><strong>${escapeHtml(item.semantic_label)}</strong><br>${escapeHtml(item.description)}</p></article>
    `).join("") : browserEmpty("Chưa có dữ liệu cảnh phù hợp.");
  } else {
    renderBrollBrowser(panel,analysis,matches);
  }
}

function selectedBrollPlan(){
  const plans=compatibleBrollPlans(state.mediaPlans,activeAnalysis());
  return plans.find(item=>item.media_plan_id===state.selectedBrollPlanId)??plans[0]??null;
}

function renderBrollBrowser(panel,analysis,matches){
  const plans=compatibleBrollPlans(state.mediaPlans,analysis),plan=selectedBrollPlan();
  if(!brollTimelineHeld()&&!brollInternalHeld())state.selectedBrollPlanId=plan?.media_plan_id??'';
  else if(plan?.media_plan_id!==state.selectedBrollPlanId){panel.innerHTML='<p>Đối chiếu lựa chọn B-roll đang giữ trước khi đổi đề xuất.</p>';return;}
  panel.innerHTML=`<div class="broll-tools"><button type="button" data-broll-create ${analysis?'':'disabled'}>Tạo đề xuất B-roll</button>
    <p>Chọn tư liệu bổ trợ cho cảnh. Giữ lời nói và tệp gốc; xem preview và duyệt lại sau khi áp dụng.</p>
    ${plans.length?`<label>Bản đề xuất<select data-broll-plan>${plans.map(item=>`<option value="${escapeHtml(item.media_plan_id)}" ${item===plan?'selected':''}>${escapeHtml(new Date(item.created_at).toLocaleString('vi-VN'))} · ${item.items.length} cảnh</option>`).join('')}</select></label>`:''}</div>`;
  if(!plan){panel.innerHTML+=browserEmpty('Chưa có đề xuất phù hợp với transcript đang chọn.');return;}
  const items=plan.items.filter(item=>matches(`${item.broll.search_query} ${item.strategy}`));
  panel.innerHTML+=items.map(item=>{
    const candidates=item.provenance?.supporting_candidates??[],stock=item.candidates??[];
    const ready=item.status==='resolved';
    const resolvedAsset=plan.media_assets.find(asset=>asset.media_asset_id===item.selected_media_asset_id);
    const selectedAssetId=resolvedAsset?.asset_id??item.source_asset_id;
    return `<article class="scene-item broll-card"><button type="button" data-seek="${item.broll.placement_start_seconds}">Cảnh ${item.ordinal+1} · ${formatTime(item.broll.placement_start_seconds)}</button>
      <p><strong>${escapeHtml(item.broll.broll_intent)}</strong><br>${escapeHtml(item.broll.search_query)}</p>
      <p>${item.broll.duration_seconds.toFixed(1)} giây · ${escapeHtml(item.status)}${item.needs_attention?' · Cần kiểm tra':''}</p>
      ${resolvedAsset?`<p>Đã chọn: ${escapeHtml(state.assets.find(asset=>asset.asset_id===resolvedAsset.asset_id)?.filename??resolvedAsset.asset_id)} · ${escapeHtml(resolvedAsset.rights_status)}</p>`:''}
      <small>${item.broll.provenance?.vision_analysis_id?'Có bằng chứng hình ảnh đã lưu':'Chưa có hiểu hình ảnh; điểm liên quan dựa trên tên, mô tả và nhãn đã lưu.'}</small>
      ${candidates.length?`<form data-broll-select="${escapeHtml(item.media_plan_item_id)}"><label>Tư liệu bổ trợ<select data-broll-asset>${candidates.map(candidate=>`<option value="${escapeHtml(candidate.asset_id)}" ${candidate.asset_id===selectedAssetId?'selected':''}>${escapeHtml(candidate.filename)} · ${escapeHtml(candidate.rights_status)} · ${(candidate.relevance_score*100).toFixed(0)}% khớp từ khóa</option>`).join('')}</select></label><button type="submit">Chọn tư liệu</button></form>`:'<p>Chưa có tư liệu tải lên phù hợp. Thêm ảnh/video tại mục Media.</p>'}
      ${stock.length?`<form data-broll-stock="${escapeHtml(item.media_plan_item_id)}"><label>Stock đã tìm được<select data-broll-candidate>${stock.map(candidate=>`<option value="${escapeHtml(candidate.candidate_id)}">${escapeHtml(candidate.provider)} · ${escapeHtml(candidate.creator)} · ${escapeHtml(candidate.rights_status)}</option>`).join('')}</select></label><button type="submit">Đưa stock vào hàng đợi</button></form>`:''}
    </article>`;
  }).join('');
  panel.innerHTML+='<div class="broll-tools"><button type="button" data-broll-apply '+(state.timeline?'':'disabled')+'>Kiểm tra và áp dụng B-roll</button><p>Đọc đề xuất và chọn cảnh tại form áp dụng. Tư liệu chưa rõ quyền vẫn bị chặn đăng bài.</p></div>';
}

function browserEmpty(message) {
  return `<div class="browser-empty">${escapeHtml(message)}</div>`;
}

function renderTimeline() {
  const linkedSource=state.timeline?.source_kind==='video_analysis';
  for(const id of ['#source-linked-explanation','#sql-source-linked-edit']){
    const panel=$(id);if(panel)panel.hidden=!linkedSource;
  }
  const history=timelineHistory(state.versions,state.timeline.current_version);state.undoStack=history.undo;state.redoStack=history.redo;
  const snapshot = state.timeline.snapshot;
  const pps = pixelsPerSecond(state.zoom);
  const laneWidth = Math.max(650, snapshot.duration_seconds * pps + 120);
  const canvas = $("#timeline-canvas");
  canvas.style.width = `${145 + laneWidth}px`;
  $("#timeline-ruler").style.width = `${laneWidth}px`;
  const ticks = [];
  const interval = snapshot.duration_seconds > 180 ? 10 : snapshot.duration_seconds > 60 ? 5 : 1;
  for (let second = 0; second <= Math.ceil(snapshot.duration_seconds + 2); second += interval) {
    const major = second % (interval * 5) === 0;
    ticks.push(`<span class="ruler-tick ${major ? "major" : ""}" style="left:${second * pps}px"><span>${major ? formatTime(second) : ""}</span></span>`);
  }
  $("#timeline-ruler").innerHTML = ticks.join("");
  $("#timeline-tracks").innerHTML = snapshot.tracks.map((track) => `
    <div class="track-row" data-track-row="${escapeHtml(track.track_id)}">
      <div class="track-head"><div><strong>${escapeHtml(track.label)}</strong><small>${escapeHtml(track.type)} · ${track.clips.length} clip${track.type === "audio" ? (track.clips.some(c=>waveformPath(c))?' · waveform đã đo':' · chưa có waveform đo') : ""}</small></div>
        <div class="track-controls">
          <button data-track-action="lock" data-track-id="${escapeHtml(track.track_id)}" class="${track.locked ? "active" : ""}" title="Khóa track">${track.locked ? "🔒" : "◇"}</button>
          <button data-track-action="mute" data-track-id="${escapeHtml(track.track_id)}" class="${track.muted ? "active" : ""}" title="Tắt tiếng">M</button>
        </div>
      </div>
      <div class="track-lane" data-track-id="${escapeHtml(track.track_id)}" data-track-type="${escapeHtml(track.type)}" data-track-locked="${track.locked}" style="width:${laneWidth}px">
        ${track.clips.map((clip) => {
          const style = clipStyle(clip, track.kind, state.zoom);
          const waveform=track.type==='audio'?waveformPath(clip):null;
          return `<button draggable="${!track.locked}" class="timeline-clip ${clip.disabled ? "disabled" : ""} ${clip.clip_id === state.selectedClipId ? "selected" : ""}" data-clip-id="${escapeHtml(clip.clip_id)}" data-track-type="${escapeHtml(track.type)}" style="left:${style.left};width:${style.width};background-color:${style.color};opacity:${style.opacity}">${waveform?`<svg class="measured-waveform" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path d="${waveform}"/></svg>`:''}<strong>${escapeHtml(clip.label)}</strong><small>${formatTime(clip.timeline_start)} · ${clip.duration.toFixed(1)}s</small></button>`;
        }).join("")}
      </div>
    </div>`).join("");
  $("#timeline-playhead").style.left = `${145 + state.playhead * pps}px`;
  $("#playhead-range").max = snapshot.duration_seconds;
  $("#playhead-range").value = state.playhead;
  $("#playhead-label").textContent = formatTime(state.playhead);
  $("#duration-label").textContent = formatTime(snapshot.duration_seconds);
  $("#undo-button").disabled = !state.undoStack.length;
  $("#redo-button").disabled = !state.redoStack.length;
}

function renderInspector() {
  const selection = selectedClip();
  const controls = [
    "#split-button",
    "#duplicate-button",
    "#reorder-up-button",
    "#reorder-down-button",
    "#toggle-clip-button",
    "#delete-button",
  ];
  controls.forEach((selector) => { $(selector).disabled = !selection || selection.track.locked; });
  $("#inspector-empty").hidden = Boolean(selection);
  $("#clip-inspector").hidden = !selection;
  if (!selection) return;
  const { clip, track } = selection;
  $("#clip-label").value = clip.label;
  $("#clip-source-start").value = clip.source_start;
  $("#clip-source-end").value = clip.source_end;
  $("#clip-timeline-start").value = clip.timeline_start;
  $('#clip-display-duration-label').hidden=clip.kind!=='image';
  $('#clip-display-duration').value=clip.duration;
  $('#clip-display-duration').disabled=track.locked||clip.kind!=='image';
  $("#clip-speed").value = clip.speed;
  $("#clip-opacity").value = clip.opacity;
  $("#clip-volume").value = clip.volume;
  $("#clip-crop-x").value = clip.crop.x;
  $("#clip-crop-y").value = clip.crop.y;
  $("#clip-crop-width").value = clip.crop.width;
  $("#clip-crop-height").value = clip.crop.height;
  $("#clip-transform-x").value = clip.transform.x;
  $("#clip-transform-y").value = clip.transform.y;
  $("#clip-transform-scale").value = clip.transform.scale;
  $("#clip-transform-rotation").value = clip.transform.rotation_degrees;
  [
    "#clip-source-start", "#clip-source-end", "#clip-timeline-start", "#clip-speed", "#clip-opacity", "#clip-volume",
    "#clip-crop-x", "#clip-crop-y", "#clip-crop-width", "#clip-crop-height",
    "#clip-transform-x", "#clip-transform-y", "#clip-transform-scale", "#clip-transform-rotation",
  ].forEach((selector) => {
    $(selector).disabled = track.locked || (clip.kind === "image" && ["#clip-source-start", "#clip-source-end", "#clip-speed"].includes(selector));
  });
  if(state.timeline.source_kind==='video_analysis'&&track.type==='video'&&track.kind==='source')$("#clip-volume").disabled=true;
  $("#clip-inspector button[type=submit]").disabled = track.locked;
  const clipIndex = track.clips.findIndex((item) => item.clip_id === clip.clip_id);
  $("#reorder-up-button").disabled = track.locked || clipIndex <= 0;
  $("#reorder-down-button").disabled = track.locked || clipIndex < 0 || clipIndex >= track.clips.length - 1;
  $("#toggle-clip-button").textContent = clip.disabled ? "Hiện clip" : "Ẩn clip";
}

function clearAuthenticatedMedia(video) {
  video.dataset.playbackPath = "";
  if (video.dataset.blobUrl) URL.revokeObjectURL(video.dataset.blobUrl);
  video.dataset.blobUrl = "";
}

async function attachAuthenticatedMedia(video, path) {
  if (video.dataset.playbackPath === path) return;
  clearAuthenticatedMedia(video);
  video.dataset.playbackPath = path;
  try {
    const response = await authenticatedFetch(path);
    if (!response.ok) throw new Error(`Không tải được review A/V (${response.status}).`);
    const blob = await response.blob();
    if (video.dataset.playbackPath !== path) return;
    video.dataset.blobUrl = URL.createObjectURL(blob);
    video.src = video.dataset.blobUrl;
  } catch(error) {
    if (video.dataset.playbackPath === path) clearAuthenticatedMedia(video);
    toast(error.message, true);
  }
}

function renderPreview() {
  const currentVersion = state.timeline?.current_version ?? null;
  const description = describePreview(state.preview, currentVersion);
  const pill = $("#preview-status");
  pill.textContent = description.label;
  pill.className = `pill ${description.tone}`;
  const video = $("#preview-video");
  const placeholder = $("#preview-placeholder");
  const playable = state.preview?.playback_url && ["ready", "stale"].includes(state.preview.status) && state.preview.manifest?.playable !== false;
  if (playable) {
    const nextSource = `${state.preview.playback_url}?version=${state.preview.timeline_version}`;
    attachAuthenticatedMedia(video, nextSource);
    video.hidden = false;
    placeholder.hidden = true;
  } else {
    video.hidden = true;
    placeholder.hidden = false;
  }
  const busy = ["queued", "running"].includes(state.preview?.status);
  $("#preview-button").disabled = busy;
  $("#preview-button").textContent = busy ? `Đang tạo ${state.preview.progress}%` : needsProductionReview(state.timeline?.snapshot) ? 'Tạo A/V review cho khung hình' : state.preview?.status === "stale" ? "Tạo lại preview" : "Tạo preview 540p";
  $("#cancel-preview-button").disabled = !busy;
  $("#preview-title").textContent = currentVersion ? `Timeline v${currentVersion}` : "Timeline hiện tại";
  $('#preview-audio-summary').textContent = state.preview?.manifest?.playable === false
    ? 'Bản kiểm thử không phát được; chưa có âm thanh để kiểm tra.'
    : state.preview?.manifest?.audio_included === true
      ? 'Có âm thanh theo timeline · trim, tốc độ, âm lượng và fade đã áp dụng. Kiểm tra phụ đề và mix hoàn chỉnh ở review.'
      : state.preview?.manifest?.audio_included === false
        ? 'Preview này không có âm thanh. Bản cũ hoặc timeline không có track âm thanh hoạt động.'
        : 'Âm thanh theo timeline sẽ được ghi rõ sau khi tạo preview.';
}

function currentProductionApproval(packageState) {
  const approval=packageState?.approval,review=packageState?.latest_review_render;
  if(!packageState?.current_for_timeline||!approval||!review
    ||approval.project_id!==packageState.project_id||approval.package_id!==packageState.package_id
    ||approval.preview_render_id!==review.render_id||approval.preview_version!==review.version
    ||approval.timeline_version_id!==packageState.timeline_version_id||approval.timeline_version!==packageState.timeline_version
    ||approval.subtitle_version_id!==packageState.subtitle.subtitle_version_id||approval.subtitle_version!==packageState.subtitle.version
    ||approval.audio_version_id!==packageState.audio_mix.audio_version_id||approval.audio_version!==packageState.audio_mix.version)return null;
  return approval;
}

function renderProduction({preserveDraft=false}={}) {
  const packageState = state.productionPackage;
  const empty = $("#production-empty");
  const content = $("#production-content");
  const packagePill = $("#production-package-status");
  const packageButton = $("#production-package-button");
  if (!packageState) {
    productionBaseline=null;
    empty.hidden = false;
    content.hidden = true;
    packagePill.textContent = "Chưa khởi tạo";
    packagePill.className = "pill muted";
    packageButton.textContent = "Khởi tạo gói dựng";
    return;
  }
  empty.hidden = true;
  content.hidden = false;
  packagePill.textContent = packageState.current_for_timeline
    ? `Timeline v${packageState.timeline_version}`
    : `Cần làm mới từ timeline v${state.timeline.current_version}`;
  packagePill.className = `pill ${packageState.current_for_timeline ? "safe" : "warning"}`;
  packageButton.textContent = packageState.current_for_timeline ? "Làm mới gói dựng" : "Đồng bộ timeline mới";

  if(!preserveDraft){
  $("#subtitle-version").textContent = `v${packageState.subtitle.version}`;
  $("#subtitle-list").innerHTML = packageState.subtitle.cues.map((cue) => `
    <div class="subtitle-row" data-cue-id="${escapeHtml(cue.cue_id)}">
      <label>Bắt đầu<input data-cue-field="start" type="number" min="0" step="0.000001" value="${cue.start_seconds}" /></label>
      <label>Kết thúc<input data-cue-field="end" type="number" min="0.05" step="0.000001" value="${cue.end_seconds}" /></label>
      <label>Nội dung<textarea data-cue-field="text" maxlength="180">${escapeHtml(cue.text)}</textarea></label>
    </div>
  `).join("");
  $("#subtitle-position").value = packageState.subtitle.style.position;
  $("#subtitle-animation").value = packageState.subtitle.style.animation;
  $('#subtitle-template').innerHTML='<option value="">Tùy chỉnh</option>'+compatibleSubtitleTemplates(state.subtitleCatalog,packageState.subtitle.cues)
    .map(template=>`<option value="${escapeHtml(template.template_ref)}" ${template.disabled?'disabled':''}>${escapeHtml(template.name)}${template.disabled?' · cần thời gian từng từ':''}</option>`).join('');
  $('#subtitle-template').value=packageState.subtitle.style.template_ref??'';
  $('#subtitle-keywords').value=(packageState.subtitle.style.keywords??[]).join(', ');
  $('#subtitle-keywords').disabled=!state.subtitleCatalog;
  updateSubtitleAlignment();
  $("#subtitle-font-size").value = packageState.subtitle.style.font_size;
  $("#subtitle-safe-margin").value = packageState.subtitle.style.safe_margin_percent;

  const mix = packageState.audio_mix.config;
  $("#audio-version").textContent = `v${packageState.audio_mix.version}`;
  const audioStatus = {configured:"đã cấu hình", model_voice_selection_required:"cần chọn model/giọng",
    tts_authority_required:"cần authority TTS riêng", disabled:"đã tắt", not_configured:"chưa cấu hình"};
  $("#audio-provider-status").textContent = `TTS: ${audioStatus[packageState.audio_mix.provider_status] ?? "chưa xác minh"} · 48 kHz · limiter ${mix.limiter_peak_db} dB`;
  $("#voice-enabled").checked = mix.voice.enabled;
  $("#voice-speed").value = mix.voice.speed;
  $("#voice-speed-output").textContent = `${Number(mix.voice.speed).toFixed(2)}×`;
  $("#voice-gain").value = mix.voice.gain_db;
  $("#music-gain").value = mix.music.gain_db;
  $("#music-ducking").value = mix.music.ducking_db;
  const licensedAudio = state.assets.filter((asset) => {
    const rights = String(asset.provenance?.rights_status ?? "").toLowerCase();
    return asset.content_type.startsWith("audio/") && ["owned", "licensed", "public_domain", "royalty_free"].includes(rights);
  });
  $("#music-asset").innerHTML = `<option value="">Không dùng nhạc</option>${licensedAudio.map((asset) => `
    <option value="${escapeHtml(asset.asset_id)}">${escapeHtml(asset.filename)} · ${escapeHtml(asset.provenance.rights_status)}</option>
  `).join("")}`;
  $("#music-asset").value = mix.music.asset_id ?? "";
  }

  const approval = currentProductionApproval(packageState);
  const approvalState = describeApproval(approval);
  $("#approval-status").textContent = approvalState.label;
  $("#approval-status").className = `pill ${approvalState.tone}`;
  const render = state.activeProductionRender
    ?? packageState.latest_final_render
    ?? packageState.latest_review_render;
  const renderState = describeProductionRender(render);
  $("#render-summary").textContent = render
    ? `${renderState.label} · ${render.render_kind === "final" ? "Final" : "Review"} v${render.version} · timeline v${render.timeline_version} / subtitle v${render.subtitle_version} / audio v${render.audio_version}`
    : renderState.label;
  const productionVideo = $("#production-video");
  if (render?.playback_url && ["awaiting_review", "ready"].includes(render.status)) {
    attachAuthenticatedMedia(productionVideo, `${render.playback_url}?render=${encodeURIComponent(render.render_id)}`);
    productionVideo.hidden = false;
  } else {
    productionVideo.hidden = true;
    clearAuthenticatedMedia(productionVideo);
    productionVideo.removeAttribute("src");
  }
  $("#qc-summary").innerHTML = qcItems(render?.qc_report).map(([label, value]) => `
    <div class="qc-item">${escapeHtml(label)}<strong>${escapeHtml(value)}</strong></div>
  `).join("");
  const busy = ["queued", "running"].includes(render?.status);
  const reviewReady = packageState.latest_review_render?.status === "awaiting_review"
    && packageState.latest_review_render?.qc_status === "passed";
  const awaitingDecision = approval?.status === "awaiting_review";
  const approved = approval?.status === "approved";
  $("#review-render-button").disabled = busy || !packageState.current_for_timeline;
  $("#review-render-button").textContent = busy && render?.render_kind === "review"
    ? `Đang render ${render.progress}%`
    : "Tạo review A/V 540p";
  $("#request-approval-button").disabled = busy || !reviewReady || awaitingDecision || approved;
  $("#approve-button").disabled = !awaitingDecision;
  $("#changes-button").disabled = !awaitingDecision;
  $("#final-render-button").disabled = busy || !approved;
  $("#download-final-button").disabled = !approved || packageState.latest_final_render?.status !== "ready" || !packageState.current_for_timeline;
  $("#final-render-button").textContent = busy && render?.render_kind === "final"
    ? `Đang render ${render.progress}%`
    : "Render final đã duyệt";
  renderPublishing();
  if(!preserveDraft)productionBaseline=productionWorkbenchDraft();
  variantNarration?.sync();
  videoWordReview?.sync();sqlAudioProcessing?.sync();sourceLinkedEditor?.sync();manualReframeEditor?.sync();syncManualReframeForm();syncBrollPlanForm();
}

function selectedPublishingPlatform() {
  const key = $("#publishing-platform")?.value ?? "youtube";
  return state.publishingPlatforms.find((item) => item.platform === key) ?? null;
}

function renderPublishing() {
  const packageState = state.productionPackage;
  const finalRender = packageState?.latest_final_render ?? null;
  const approved = currentProductionApproval(packageState)?.status === "approved";
  const eligible = Boolean(
    packageState?.current_for_timeline
    && approved
    && finalRender?.status === "ready"
    && finalRender?.qc_status === "passed",
  );
  const platformState = selectedPublishingPlatform();
  const liveEnabled = Boolean(platformState?.live_execution_enabled);
  $("#publishing-live-status").textContent = liveEnabled ? "Owner gate đang bật" : "Live bị khóa";
  $("#publishing-live-status").className = `pill ${liveEnabled ? "warning" : "muted"}`;
  $("#publishing-dry-run-button").disabled = !eligible;
  if (!$("#publishing-title").value && state.projectId) {
    const project = state.projects.find((item) => item.project_id === state.projectId);
    $("#publishing-title").value = project?.name ?? "NPD Video";
  }

  const publication = state.activePublication ?? state.publications[0] ?? null;
  const status = describePublication(publication);
  $("#publishing-status").textContent = status.label;
  $("#publishing-status").className = `pill ${status.tone}`;
  const gates = publicationGateItems(publication);
  if (gates.length) {
    $("#publishing-gates").innerHTML = gates.map((item) => `
      <div class="publishing-gate ${item.passed ? "passed" : "failed"}">
        <span>${item.passed ? "✓" : "!"}</span>
        <div><small>${escapeHtml(item.group)} · ${escapeHtml(item.code)}</small><strong>${escapeHtml(item.message)}</strong></div>
      </div>
    `).join("");
  } else {
    const capability = platformState?.capability;
    $("#publishing-gates").innerHTML = `
      <div class="publishing-gate ${eligible ? "passed" : "pending"}">
        <span>${eligible ? "✓" : "…"}</span>
        <div><small>Điều kiện đầu vào</small><strong>${eligible ? "Final render đã duyệt và QC PASS." : "Cần final render đã duyệt và QC PASS."}</strong></div>
      </div>
      <div class="publishing-gate pending">
        <span>i</span>
        <div><small>Capability ${escapeHtml(capability?.version ?? "—")}</small><strong>Internal safe profile · phải xác minh lại trước live.</strong></div>
      </div>
    `;
  }
  $("#publication-history").innerHTML = state.publications.length
    ? `<strong>Receipt gần đây</strong>${state.publications.slice(0, 5).map((item) => {
      const itemStatus = describePublication(item);
      return `<button type="button" data-publication-id="${escapeHtml(item.publication_id)}"><span>${escapeHtml(item.platform)}</span><small class="${escapeHtml(itemStatus.tone)}">${escapeHtml(itemStatus.label)} · ${escapeHtml(item.publication_id)}</small></button>`;
    }).join("")}`
    : `<p class="browser-empty">Chưa có dry-run receipt.</p>`;
  publishingConsole.sync();
}

function analyticsFactorLabel(name) {
  return ({
    view_velocity: "Tốc độ view",
    retention: "Giữ chân",
    completion: "Xem hết",
    engagement: "Tương tác",
    shares: "Chia sẻ",
    saves: "Lưu",
    ctr: "CTR",
    follower_conversion: "Tăng follower",
    revenue_efficiency: "Hiệu quả doanh thu",
    production_cost_efficiency: "Hiệu quả chi phí",
  })[name] ?? name;
}

function renderAnalytics() {
  const report = state.analyticsReport;
  const status = describeAnalytics(report);
  const sync = state.activeAnalyticsSync ?? report?.latest_sync ?? null;
  const collecting = ["scheduled", "queued", "running", "retry_scheduled"].includes(sync?.status);
  const snapshot = report?.latest_snapshot ?? null;
  const assessment = report?.latest_assessment ?? null;
  const providers = state.analyticsProviders ?? [];
  const officialProviders = providers.filter((item) => item.mode === "official");
  const unavailableCount = officialProviders.filter((item) => !item.supports_sync).length;

  $("#analytics-status").textContent = collecting ? "Đang thu thập" : status.label;
  $("#analytics-status").className = `pill ${collecting ? "warning" : status.tone}`;
  $("#analytics-source-status").textContent = !snapshot ? 'Chưa có snapshot' : snapshot.mock === false ? "Nguồn provider" : "Dữ liệu mô phỏng";
  $("#analytics-source-status").className = `pill ${snapshot?.mock === false ? "safe" : "muted"}`;
  $("#analytics-provider-summary").textContent = officialProviders.length
    ? `Adapter: ${unavailableCount}/${officialProviders.length} chưa cấu hình; ${officialProviders.some(value => value.external_calls_enabled) ? 'có transport ngoài được bật' : 'transport ngoài tắt; mock nếu cấu hình'}.`
    : "Provider thật: chưa đăng ký; external calls=false.";

  $("#analytics-metrics").innerHTML = snapshot
    ? analyticsMetricItems(report).map((item) => `
      <div class="analytics-metric${item.value === "Không có dữ liệu" ? " missing" : ""}">
        <small>${escapeHtml(item.label)}</small><strong>${escapeHtml(item.value)}</strong>
      </div>
    `).join("")
    : `<p class="browser-empty">${collecting ? "Worker đang tạo snapshot…" : "Chưa có snapshot."}</p>`;
  $("#analytics-history-count").textContent = `${report?.history_count ?? 0} snapshot`;
  $("#analytics-winner-score").textContent = assessment?.score === null || assessment?.score === undefined
    ? "—"
    : String(Math.round(assessment.score));
  $("#analytics-winner-state").textContent = status.winnerLabel;
  $("#analytics-factor-list").innerHTML = assessment?.factors?.length
    ? assessment.factors.map((factor) => `
      <div class="analytics-factor">
        <span>${escapeHtml(analyticsFactorLabel(factor.factor))}</span>
        <progress max="100" value="${factor.score ?? 0}"></progress>
        <strong>${factor.score === null || factor.score === undefined ? "—" : Math.round(factor.score)}</strong>
      </div>
    `).join("")
    : `<p class="browser-empty">Chưa có yếu tố đánh giá.</p>`;

  $("#analytics-learning-list").innerHTML = report?.learning_insights?.length
    ? report.learning_insights.map((insight) => `
      <div class="analytics-insight">
        <strong>${escapeHtml(insight.statement)}</strong>
        <span>${escapeHtml(insight.recommendation)}</span>
        <small>${escapeHtml(insight.insight_type)} · confidence ${Math.round(insight.confidence * 100)}% · applied=false</small>
      </div>
    `).join("")
    : `<p class="browser-empty">Chưa có khuyến nghị.</p>`;

  const features = report?.video_features;
  const featureItems = features ? [
    ["Trend", features.trend_cluster_id],
    ["Idea", features.idea_id],
    ["Hook", features.hook_type],
    ["Thời lượng", features.duration_seconds === null ? null : `${features.duration_seconds}s`],
    ["Scene", features.scene_count],
    ["Subtitle", features.subtitle_template],
    ["Voice", features.voice_profile],
    ["Music", features.music_profile],
    ["Visual", features.visual_strategy],
    ["Lĩnh vực", features.niche],
    ["Nội dung", features.topic],
    ["CTA", features.cta],
    ["Nguồn nhãn", features.evidence?.project_metadata_source === 'published_render_request_context'
      ? 'Đã lưu cùng bản render' : 'Chưa có dữ liệu lịch sử'],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "") : [];
  $("#analytics-feature-list").innerHTML = featureItems.map(([label, value]) => (
    `<span><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</span>`
  )).join("");
  analyticsConsole.sync();
  analyticsChannels.sync();
  analyticsRefresh.sync();
  channelLearning.sync();
}

function startAnalyticsPolling() {
  stopAnalyticsPolling();
  const projectId = state.projectId, syncId = state.activeAnalyticsSync?.sync_id, scope = analyticsConsole.key();
  state.analyticsPollTimer = window.setInterval(async () => {
    try {
      if (!state.activeAnalyticsSync || state.projectId !== projectId || analyticsConsole.key() !== scope || state.activeAnalyticsSync.sync_id !== syncId) return stopAnalyticsPolling();
      const next = await api(
        `/api/v1/projects/${projectId}/analytics/syncs/${syncId}`,
      );
      if (state.projectId !== projectId || analyticsConsole.key() !== scope || state.activeAnalyticsSync?.sync_id !== syncId) return;
      state.activeAnalyticsSync = next;
      const terminal = ["succeeded", "not_configured", "failed", "cancelled"].includes(state.activeAnalyticsSync.status);
      if (terminal) {
        stopAnalyticsPolling();
        await analyticsConsole.refresh();
        if (state.projectId !== projectId || analyticsConsole.key() !== scope || state.activeAnalyticsSync?.sync_id !== syncId) return;
        toast(next.status === "succeeded"
          ? "Analytics đã chuẩn hóa; nguồn/transport được ghi rõ. Khuyến nghị vẫn cần review."
          : `Analytics kết thúc ở trạng thái ${next.status}.`,
          next.status === "failed");
      }
      renderAnalytics();
    } catch (error) {
      if (state.projectId !== projectId || analyticsConsole.key() !== scope || state.activeAnalyticsSync?.sync_id !== syncId) return;
      stopAnalyticsPolling();
      toast(error.message, true);
    }
  }, 1000);
}

function stopAnalyticsPolling() {
  if (state.analyticsPollTimer) window.clearInterval(state.analyticsPollTimer);
  state.analyticsPollTimer = null;
}

function publicationPayload() {
  const finalRender = state.productionPackage?.latest_final_render;
  if (!finalRender) return null;
  return {
    platform: $("#publishing-platform").value,
    final_render_id: finalRender.render_id,
    mode: "dry_run",
    metadata: {
      title: $("#publishing-title").value.trim(),
      description: $("#publishing-description").value.trim(),
      caption: $("#publishing-caption").value.trim(),
      hashtags: $("#publishing-hashtags").value.split(",").map((item) => item.trim().replace(/^#/, "")).filter(Boolean),
      privacy: $("#publishing-privacy").value,
      scheduled_at: $("#publishing-scheduled").value ? new Date($("#publishing-scheduled").value).toISOString() : null,
    },
    actor_ref: "studio-user",
  };
}

async function createPublishingDryRun(event) {
  event.preventDefault();
  const payload = publicationPayload();
  if (!payload) return toast("Cần final render đã duyệt trước khi kiểm tra publishing.", true);
  const signature = JSON.stringify(payload);
  if (signature !== state.publishRequestSignature) {
    state.publishRequestSignature = signature;
    state.publishIdempotencyKey = `v2-09-${crypto.randomUUID()}`;
  }
  $("#publishing-dry-run-button").disabled = true;
  $("#publishing-dry-run-button").textContent = "Đang kiểm tra…";
  try {
    const publication = await api(`/api/v1/projects/${state.projectId}/publish`, {
      method: "POST",
      headers: { "Idempotency-Key": state.publishIdempotencyKey },
      body: JSON.stringify(payload),
    });
    state.activePublication = publication;
    state.publications = [publication, ...state.publications.filter((item) => item.publication_id !== publication.publication_id)];
    toast("Dry-run PASS: đã tạo receipt, không có bài đăng hoặc external action.");
  } catch (error) {
    const publicationId = error.detail?.error?.publication_id;
    if (publicationId) {
      state.activePublication = await api(`/api/v1/projects/${state.projectId}/publications/${publicationId}`).catch(() => null);
      if (state.activePublication) {
        state.publications = [state.activePublication, ...state.publications.filter((item) => item.publication_id !== publicationId)];
      }
    }
    toast(error.message, true);
  } finally {
    $("#publishing-dry-run-button").textContent = "Kiểm tra và tạo dry-run receipt";
    renderPublishing();
  }
}

async function createOrRefreshProductionPackage() {
  if (!state.timeline) return;
  try {
    state.productionPackage = await api(`/api/v1/projects/${state.projectId}/production-package`, {
      method: "POST",
      body: JSON.stringify({
        expected_timeline_version: state.timeline.current_version,
        actor_ref: "studio-user",
      }),
    });
    state.activeProductionRender = null;
    renderSummary();
    renderProduction();
    toast("Gói dựng V2-08 đã đồng bộ với timeline hiện tại.");
  } catch (error) {
    toast(error.message, true);
  }
}

function editedSubtitleCues() {
  return [...document.querySelectorAll('.subtitle-row')].map(row=>subtitleCueEdit(
    state.productionPackage?.subtitle.cues.find(cue=>cue.cue_id===row.dataset.cueId),{
      cue_id:row.dataset.cueId,start_seconds:Number(row.querySelector('[data-cue-field="start"]').value),
      end_seconds:Number(row.querySelector('[data-cue-field="end"]').value),text:row.querySelector('[data-cue-field="text"]').value,
    }));
}

function updateSubtitleAlignment() {
  const cues=editedSubtitleCues();
  const aligned=cues.length>0&&cues.every(cue=>cue.words.length);
  for(const option of $('#subtitle-animation').options){
    option.disabled=(timedSubtitleModes.includes(option.value)&&!aligned)||
      (!state.subtitleCatalog&&['word_by_word','karaoke','keyword_highlight'].includes(option.value));
  }
  for(const template of compatibleSubtitleTemplates(state.subtitleCatalog,cues)){
    const option=[...$('#subtitle-template').options].find(item=>item.value===template.template_ref);
    if(option)option.disabled=template.disabled;
  }
  $('#subtitle-alignment-note').textContent=aligned?'Có thời gian từng từ từ bản phân tích. Đổi nội dung hoặc thời gian sẽ bỏ căn chỉnh cũ.':
    'Chưa có thời gian từng từ phù hợp. Có thể chọn mẫu theo câu, từ khóa hoặc chữ chuyển động.';
}

async function saveSubtitles() {
  const packageState = state.productionPackage;
  if (!packageState) return;
  const cues = editedSubtitleCues();
  try {
    const template=state.subtitleCatalog?.templates.find(item=>item.template_ref===$('#subtitle-template').value);
    const style=subtitleSaveStyle(packageState.subtitle.style,template,{
      position:$('#subtitle-position').value,animation:$('#subtitle-animation').value,
      font_size:Number($('#subtitle-font-size').value),safe_margin_percent:Number($('#subtitle-safe-margin').value),
      ...(state.subtitleCatalog?{template_ref:template?.template_ref??null,
        keywords:$('#subtitle-keywords').value.split(',').map(value=>value.trim()).filter(Boolean)}:{}),
    });
    if(timedSubtitleModes.includes(style.animation)&&cues.some(cue=>!cue.words.length))
      throw new Error('Nội dung hoặc thời gian đã đổi. Chọn phụ đề theo câu hoặc tạo lại thời gian từng từ.');
    state.productionPackage = await api(`/api/v1/projects/${state.projectId}/subtitles`, {
      method: "PUT",
      body: JSON.stringify({
        expected_timeline_version: packageState.timeline_version,
        expected_subtitle_version: packageState.subtitle.version,
        cues,
        style,
        actor_ref: "studio-user",
        reason: "subtitle-editor",
      }),
    });
    state.activeProductionRender = null;
    renderSummary();
    renderProduction();
    toast("Đã lưu phiên bản phụ đề mới; approval/render cũ đã được vô hiệu hóa nếu có.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function saveAudioMix() {
  const packageState = state.productionPackage;
  if (!packageState) return;
  const config = structuredClone(packageState.audio_mix.config);
  config.voice.enabled = $("#voice-enabled").checked;
  config.voice.speed = Number($("#voice-speed").value);
  config.voice.gain_db = Number($("#voice-gain").value);
  config.music.asset_id = $("#music-asset").value || null;
  config.music.gain_db = Number($("#music-gain").value);
  config.music.ducking_db = Number($("#music-ducking").value);
  try {
    state.productionPackage = await api(`/api/v1/projects/${state.projectId}/audio-mix`, {
      method: "PUT",
      body: JSON.stringify({
        expected_timeline_version: packageState.timeline_version,
        expected_audio_version: packageState.audio_mix.version,
        config,
        actor_ref: "studio-user",
        reason: "audio-mixer",
      }),
    });
    state.activeProductionRender = null;
    renderSummary();
    renderProduction();
    toast("Đã lưu phiên bản audio mix mới; chỉ nhạc có metadata quyền sử dụng mới được chấp nhận.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function createProductionRender(kind) {
  const packageState = state.productionPackage;
  if (!packageState) return;
  const isFinal = kind === "final";
  if(isFinal&&!currentProductionApproval(packageState))return toast('Cần duyệt đúng review hiện tại trước khi render final.',true);
  const path = isFinal ? "final-render" : "review-render";
  try {
    state.activeProductionRender = await api(`/api/v1/projects/${state.projectId}/${path}`, {
      method: "POST",
      body: JSON.stringify({
        expected_timeline_version: packageState.timeline_version,
        expected_subtitle_version: packageState.subtitle.version,
        expected_audio_version: packageState.audio_mix.version,
        profile: isFinal ? $("#final-profile").value : reframeProfiles(state.timeline.snapshot).review,
        actor_ref: "studio-user",
        ...(isFinal ? {approval_id: packageState.approval?.approval_id} : {}),
      }),
    });
    renderProduction();
    startProductionPolling();
    toast(isFinal ? "Final render đã vào hàng đợi nội bộ." : "Review A/V đã vào hàng đợi nội bộ.");
  } catch (error) {
    toast(error.message, true);
  }
}

function startProductionPolling() {
  stopProductionPolling();
  if (!state.activeProductionRender) return;
  state.productionPollTimer = window.setInterval(pollProductionRender,1200);
}

function productionPollingBoundary(){return JSON.stringify([state.workspaceId,state.projectId,
  state.principal,sessionToken(),state.activeProductionRender?.render_id,
  state.timeline?.current_version_id,state.timeline?.current_version,state.timeline?.source_content_version_id,
  state.productionPackage?.package_id,state.productionPackage?.timeline_version_id,
  state.productionPackage?.subtitle?.subtitle_version_id,state.productionPackage?.audio_mix?.audio_version_id,
  state.productionPackage?.audio_mix?.config?.voice]);}
function productionEditableBinding(packageState){return JSON.stringify([
  packageState?.package_id,packageState?.timeline_version_id,packageState?.timeline_version,
  packageState?.subtitle?.subtitle_version_id,packageState?.subtitle?.version,
  packageState?.subtitle?.cues,packageState?.subtitle?.style,
  packageState?.audio_mix?.audio_version_id,packageState?.audio_mix?.version,packageState?.audio_mix?.config]);}
async function pollProductionRender(){
  if(!state.activeProductionRender)return;
  const generation=productionPollGeneration;
  if(productionPollInFlight?.generation===generation)return;
  const ticket={generation};productionPollInFlight=ticket;
  const boundary=productionPollingBoundary(),projectId=state.projectId,renderId=state.activeProductionRender.render_id;
  try{
    const render=await api(`/api/v1/projects/${projectId}/renders/${renderId}`);
    if(productionPollGeneration!==generation||productionPollingBoundary()!==boundary)return;
    const packageState=await api(`/api/v1/projects/${projectId}/production-package`);
    if(productionPollGeneration!==generation||productionPollingBoundary()!==boundary)return;
    if(render.project_id!==projectId||render.render_id!==renderId||packageState.project_id!==projectId
      ||packageState.workspace_id!==state.workspaceId)throw Error('Kết quả review không thuộc dự án hiện tại.');
    const preserveDraft=productionBaseline!==null&&productionWorkbenchDraft()!==productionBaseline;
    if(preserveDraft&&productionEditableBinding(packageState)!==productionEditableBinding(state.productionPackage))
      throw Error('Gói dựng đã được cập nhật ở nơi khác. Nội dung đang sửa và phiên bản cũ vẫn được giữ; cần đối chiếu trước khi lưu.');
    state.activeProductionRender=render;state.productionPackage=packageState;
    renderSummary();renderProduction({preserveDraft});
    const description=describeProductionRender(render);
    if(description.terminal){stopProductionPolling();toast(description.label,!['awaiting_review','ready'].includes(render.status));}
  }catch(error){
    if(productionPollGeneration!==generation||productionPollingBoundary()!==boundary)return;
    stopProductionPolling();toast(error.message,true);
  }finally{
    if(productionPollInFlight===ticket)productionPollInFlight=null;
  }
}

function stopProductionPolling() {
  productionPollGeneration++;
  if (state.productionPollTimer) window.clearInterval(state.productionPollTimer);
  state.productionPollTimer = null;
}

async function requestProductionApproval() {
  const review = state.productionPackage?.latest_review_render;
  if (!review) return;
  try {
    const approval = await api(`/api/v1/projects/${state.projectId}/approvals`, {
      method: "POST",
      body: JSON.stringify({
        review_render_id: review.render_id,
        requester_ref: "studio-user",
        note: "Vui lòng duyệt đúng review A/V và các phiên bản đang hiển thị.",
      }),
    });
    state.productionPackage = {...state.productionPackage, approval};
    renderSummary();
    renderProduction();
    toast("Đã gửi gói review gắn phiên bản cho owner.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function decideProductionApproval(decision) {
  const approval = currentProductionApproval(state.productionPackage);
  if (!approval) return;
  try {
    const updated = await api(`/api/v1/projects/${state.projectId}/approvals/${approval.approval_id}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        reviewer_ref: "studio-owner",
        comment: decision === "approved"
          ? "Owner xác nhận đã xem hình, nghe audio và kiểm tra phụ đề/QC."
          : "Owner yêu cầu chỉnh lại gói dựng trước khi render final.",
      }),
    });
    state.productionPackage = {...state.productionPackage, approval: updated};
    renderSummary();
    renderProduction();
    toast(decision === "approved" ? "Gói review đã được owner phê duyệt." : "Đã trả gói dựng về trạng thái cần chỉnh sửa.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function createTimeline() {
  const analysis = reviewedAnalysis();
  if (!analysis) return;
  const plan = state.mediaPlans.find((item) => item.analysis_id === analysis.analysis_id) ?? null;
  const button = $("#create-timeline-button");
  button.disabled = true;
  button.textContent = "Đang tạo timeline…";
  try {
    state.timeline = await api(`/api/v1/projects/${state.projectId}/timeline`, {
      method: "POST",
      body: JSON.stringify({
        analysis_id: analysis.analysis_id,
        media_plan_id: plan?.media_plan_id ?? null,
        expected_timeline_version: state.timeline?.current_version ?? null,
        actor_ref: "studio-user",
      }),
    });
    state.versions = await api(`/api/v1/projects/${state.projectId}/timeline/versions`);
    render();
    toast("Timeline AI đã được tạo từ evidence đã lưu. Media gốc không bị thay đổi.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Khởi tạo timeline AI";
  }
}

async function mutate(operations, reason, { preserveRedo = false } = {}) {
  if (!state.timeline || !operations.length) return;
  try {
    const linked=sourceLinkedOperations(operations);
    if(linked){
      if(!sourceLinkedEditor)return toast('Chưa mở được trình chỉnh shot. Đọc lại trạng thái trước khi sửa.',true);
      setSaveStatus('Đang lưu shot…','warning');
      const saved=await sourceLinkedEditor.runOperations(linked,{acknowledged:true});
      setSaveStatus(saved?'Đã lưu':sourceLinkedEditor.isPending()?'Cần đối chiếu':'Chưa lưu',saved?'safe':'warning');
      return;
    }
  }catch(error){setSaveStatus('Chưa lưu','danger');toast(error.message,true);return;}
  setSaveStatus("Đang lưu…", "warning");
  const priorPreview = state.preview;
  try {
    state.timeline = await api(`/api/v1/projects/${state.projectId}/timeline`, {
      method: "PUT",
      body: JSON.stringify({
        expected_version: state.timeline.current_version,
        operations,
        actor_ref: "studio-user",
        reason,
      }),
    });
    if (!preserveRedo) state.redoStack = [];
    state.versions = await api(`/api/v1/projects/${state.projectId}/timeline/versions`);
    if (priorPreview) state.preview = { ...priorPreview, status: "stale", valid_for_current_timeline: false };
    if (state.productionPackage) {
      state.productionPackage = {
        ...state.productionPackage,
        current_for_timeline: false,
        approval: null,
        latest_review_render: null,
        latest_final_render: null,
      };
      state.activeProductionRender = null;
    }
    if (state.selectedClipId && !selectedClip()) state.selectedClipId = null;
    state.playhead = Math.min(state.playhead, state.timeline.snapshot.duration_seconds);
    render();
    setSaveStatus("Đã lưu", "safe");
  } catch (error) {
    if (error.status === 409) {
      $("#timeline-conflict").textContent = "Có phiên bản mới — Studio đã nạp lại";
      toast("Timeline đã thay đổi ở phiên khác. Đã nạp bản mới nhất.", true);
      await loadProject({ quiet: true });
    } else {
      setSaveStatus("Chưa lưu", "danger");
      toast(error.message, true);
    }
  }
}

async function restoreVersion(targetVersion, { isUndo = false } = {}) {
  if (!state.timeline) return;
  const previousVersion = state.timeline.current_version;
  setSaveStatus("Đang khôi phục…", "warning");
  try {
    state.timeline = await api(`/api/v1/projects/${state.projectId}/timeline/restore`, {
      method: "POST",
      body: JSON.stringify({
        expected_version: previousVersion,
        restore_version: targetVersion,
        actor_ref: "studio-user",
      }),
    });
    state.preview = state.preview ? { ...state.preview, status: "stale", valid_for_current_timeline: false } : null;
    if (state.productionPackage) {
      state.productionPackage = {
        ...state.productionPackage,
        current_for_timeline: false,
        approval: null,
        latest_review_render: null,
        latest_final_render: null,
      };
      state.activeProductionRender = null;
    }
    state.versions = await api(`/api/v1/projects/${state.projectId}/timeline/versions`);
    state.selectedClipId = null;
    await syncTimelineTranscript();
    render();
    setSaveStatus("Đã lưu", "safe");
  } catch (error) {
    setSaveStatus("Chưa lưu", "danger");
    toast(error.message, true);
  }
}

async function createPreview() {
  if (!state.timeline) return;
  if(needsProductionReview(state.timeline.snapshot)){
    if(!state.productionPackage)return toast('Hãy chuẩn bị audio/phụ đề ở phần A/V review để xem khung hình mới.',true);
    return createProductionRender('review');
  }
  try {
    state.preview = await api(`/api/v1/projects/${state.projectId}/preview`, {
      method: "POST",
      body: JSON.stringify({ timeline_version: state.timeline.current_version, actor_ref: "studio-user" }),
    });
    renderPreview();
    startPreviewPolling();
    toast("Preview đã vào hàng đợi nội bộ. Không có publish hoặc API trả phí.");
  } catch (error) {
    toast(error.message, true);
  }
}

function startPreviewPolling() {
  stopPreviewPolling();
  if (!state.preview) return;
  state.pollTimer = window.setInterval(async () => {
    try {
      state.preview = await api(`/api/v1/projects/${state.projectId}/previews/${state.preview.preview_id}`);
      renderSummary();
      renderPreview();
      if (!["queued", "running"].includes(state.preview.status)) {
        stopPreviewPolling();
        toast(state.preview.status === "ready" ? "Preview timeline đã sẵn sàng." : `Preview kết thúc: ${state.preview.status}`, state.preview.status !== "ready");
      }
    } catch (error) {
      stopPreviewPolling();
      toast(error.message, true);
    }
  }, 1000);
}

function stopPreviewPolling() {
  if (state.pollTimer) window.clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function cancelPreview() {
  if (!state.preview) return;
  try {
    state.preview = await api(`/api/v1/projects/${state.projectId}/previews/${state.preview.preview_id}/cancel`, { method: "POST" });
    stopPreviewPolling();
    renderPreview();
    renderSummary();
    toast("Đã gửi yêu cầu hủy preview.");
  } catch (error) { toast(error.message, true); }
}

function setPlayhead(value, syncVideo = true) {
  state.playhead = Math.max(0, Math.min(Number(value) || 0, state.timeline?.snapshot?.duration_seconds ?? 0));
  $("#playhead-range").value = state.playhead;
  $("#playhead-label").textContent = formatTime(state.playhead);
  if (state.timeline) $("#timeline-playhead").style.left = `${145 + state.playhead * pixelsPerSecond(state.zoom)}px`;
  const video = $("#preview-video");
  if (syncVideo && !video.hidden && Number.isFinite(video.duration)) video.currentTime = Math.min(state.playhead, video.duration);
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

$("#project-select").addEventListener("change", async (event) => {
  if(brollPlanHeld()){event.target.value=state.projectId??'';return toast('Lưu/bỏ lựa chọn B-roll hoặc đối chiếu lần chuẩn bị đang giữ trước khi đổi dự án.',true);}
  if(manualReframeHeld()){event.target.value=state.projectId??'';return toast('Lưu/bỏ crop hoặc đối chiếu yêu cầu đang giữ trước khi đổi dự án.',true);}
  if(sourceLinkedHeld()){event.target.value=state.projectId??'';return toast('Đối chiếu lần chỉnh shot đang giữ trước khi đổi dự án.',true);}
  if(audioProcessingHeld()){event.target.value=state.projectId??'';return toast('Lưu/bỏ cấu hình âm thanh hoặc đối chiếu yêu cầu đang giữ trước khi đổi dự án.',true);}
  if(videoWordsHeld()){event.target.value=state.projectId??'';return toast('Lưu/bỏ bản sửa từ hoặc đối chiếu yêu cầu đang giữ trước khi đổi dự án.',true);}
  if(variantNarration?.isWorking()||variantNarration?.isPending()){
    event.target.value=state.projectId??'';
    return toast('Chờ nhập/review giọng đọc hoàn tất hoặc đối chiếu yêu cầu cũ trước khi đổi dự án.',true);
  }
  if(variantFamilies.isBusy()||variantFamilies.isPending()){
    event.target.value=state.projectId??'';
    return toast('Chờ thao tác phiên bản hoàn tất hoặc đối chiếu yêu cầu cũ trước khi đổi dự án.',true);
  }
  if (stockReview.isPending()) {
    event.target.value = state.projectId ?? '';
    return toast('Đối chiếu yêu cầu tìm tư liệu trong panel trước khi đổi dự án.', true);
  }
  if (audioReview.isDirty()) {
    event.target.value = state.projectId ?? '';
    return toast('Lưu/bỏ sửa hoặc đối chiếu yêu cầu audio trước khi đổi dự án.', true);
  }
  state.projectId = event.target.value || null;
  audioReview.sync();
  stockReview.sync();
  window.localStorage.setItem("npd-studio-project", state.projectId ?? "");
  await loadProject();
});
$("#reload-button").addEventListener("click", () => loadProject());
$("#create-timeline-button").addEventListener("click", createTimeline);
$("#preview-button").addEventListener("click", createPreview);
$('#apply-reframe').addEventListener('click',async()=>{
  if(!state.timeline)return;
  const button=$('#apply-reframe');button.disabled=true;
  try{
    await api(`/api/v1/projects/${state.projectId}/timeline/reframe`,{method:'POST',body:JSON.stringify({
      expected_version:state.timeline.current_version,aspect_ratio:$('#reframe-aspect').value,
      vision_analysis_id:$('#reframe-vision').value||null})});
    await loadProject();toast('Đã lưu khung hình vào timeline. Xem A/V review và duyệt lại.');
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
$("#cancel-preview-button").addEventListener("click", cancelPreview);
$("#production-package-button").addEventListener("click", createOrRefreshProductionPackage);
$("#save-subtitles-button").addEventListener("click", saveSubtitles);
$('#subtitle-list').addEventListener('input',updateSubtitleAlignment);
$('#subtitle-template').addEventListener('change',()=>{
  const template=state.subtitleCatalog?.templates.find(item=>item.template_ref===$('#subtitle-template').value);
  if(!template)return;
  $('#subtitle-animation').value=template.style.animation;
  $('#subtitle-position').value=template.style.position;
  $('#subtitle-font-size').value=template.style.font_size;
  $('#subtitle-safe-margin').value=template.style.safe_margin_percent;
  updateSubtitleAlignment();
});
$("#save-audio-button").addEventListener("click", saveAudioMix);
$("#review-render-button").addEventListener("click", () => createProductionRender("review"));
$("#request-approval-button").addEventListener("click", requestProductionApproval);
$("#approve-button").addEventListener("click", () => decideProductionApproval("approved"));
$("#changes-button").addEventListener("click", () => decideProductionApproval("changes_requested"));
$("#final-render-button").addEventListener("click", () => createProductionRender("final"));
$("#download-final-button").addEventListener("click", async () => {
  const render = state.productionPackage?.latest_final_render;
  if (render?.status !== "ready" || currentProductionApproval(state.productionPackage)?.status !== "approved") return;
  try {
    const response = await authenticatedFetch(render.playback_url);
    if (!response.ok) throw new Error("Export không còn hợp lệ.");
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${state.projectId}-final.mp4`;
    anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch(error) { toast(error.message, true); }
});
$("#publishing-form").addEventListener("submit", createPublishingDryRun);
$("#publishing-platform").addEventListener("change", () => {
  state.activePublication = state.publications.find((item) => item.platform === $("#publishing-platform").value) ?? null;
  state.publishRequestSignature = null;
  state.publishIdempotencyKey = null;
  renderPublishing();
});
$("#publication-history").addEventListener("click", (event) => {
  const button = event.target.closest("[data-publication-id]");
  if (!button) return;
  state.activePublication = state.publications.find((item) => item.publication_id === button.dataset.publicationId) ?? null;
  renderPublishing();
});
$("#voice-speed").addEventListener("input", (event) => {
  $("#voice-speed-output").textContent = `${Number(event.target.value).toFixed(2)}×`;
});
$("#menu-button").addEventListener("click", () => $(".sidebar").classList.toggle("open"));

document.querySelector(".panel-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-panel-tab]");
  if (!button) return;
  state.panelTab = button.dataset.panelTab;
  renderBrowser();
});
$("#browser-search").addEventListener("input", (event) => {
  if(brollTimelineHeld()||brollInternalHeld()){event.target.value=state.query;return toast('Giữ lựa chọn hoặc đối chiếu lần áp dụng B-roll trước khi tìm lại.',true);}
  state.query = event.target.value; renderBrowser(); });
$("#browser-content").addEventListener("click", (event) => {
  const seek = event.target.closest("[data-seek]");
  if (seek) setPlayhead(Number(seek.dataset.seek));
});
$('#browser-content').addEventListener('change',event=>{
  if(event.target.matches('[data-broll-plan]')){
    if(brollTimelineHeld()||brollInternalHeld()){event.target.value=state.selectedBrollPlanId;return toast('Lưu/bỏ lựa chọn hoặc đối chiếu B-roll trước khi đổi đề xuất.',true);}
    state.selectedBrollPlanId=event.target.value;clearBrollTimelineForm();clearBrollInternalForm();brollInternalItemId='';renderBrowser();syncBrollPlanPeers();}
});
$('#browser-content').addEventListener('click',async event=>{
  const button=event.target.closest('[data-broll-create],[data-broll-apply]');if(!button)return;
  button.disabled=true;
  try{
    if(button.hasAttribute('data-broll-create')){
      $('#broll-plan-workbench').open=true;$('#broll-plan-read').focus();
      toast('Đọc nguồn và review lựa chọn trước khi chuẩn bị B-roll.');
    }else{
      $('#broll-timeline-workbench').open=true;$('#broll-timeline-read').focus();
      toast('Đọc đúng đề xuất, chọn cảnh và xác nhận trước khi áp dụng vào timeline.');
    }
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
$('#browser-content').addEventListener('submit',async event=>{
  const form=event.target.closest('[data-broll-select],[data-broll-stock]');if(!form)return;event.preventDefault();
  if(form.dataset.brollSelect){
    try{const v=brollInternalEditorState();if(brollInternalHeld()||brollTimelineHeld()||brollPreparationHeld()||v.busy||v.dirty)throw Error('Đối chiếu yêu cầu hoặc lưu/bỏ lựa chọn trước khi đổi cảnh.');
      const plan=selectedBrollPlan(),item=plan?.items.find(i=>i.media_plan_item_id===form.dataset.brollSelect);
      if(!item)throw Error('Cảnh B-roll không còn trong đề xuất.');clearBrollInternalForm();brollInternalItemId=item.media_plan_item_id;
      brollInternalSelectors();$('#broll-internal-workbench').open=true;syncBrollPlanPeers();$('#broll-internal-read').focus();
      toast('Đọc nguồn và chọn tư liệu nội bộ trước khi gửi phân giải.');
    }catch(error){toast(error.message,true);}return;
  }
  const button=form.querySelector('button[type="submit"]');button.disabled=true;
  const projectId=state.projectId;
  try{
    const plan=selectedBrollPlan(),id=form.dataset.brollSelect??form.dataset.brollStock;
    const item=plan.items.find(item=>item.media_plan_item_id===id);
    const body=form.dataset.brollSelect?selectedBrollAsset(item,form.querySelector('[data-broll-asset]').value):
      {candidate_id:form.querySelector('[data-broll-candidate]').value};
    let job=await api(`/api/v1/projects/${projectId}/media-plans/${plan.media_plan_id}/items/${id}/resolve`,{method:'POST',body:JSON.stringify(body)});
    toast('Tư liệu đã vào hàng đợi. Timeline sẽ đổi khi bạn chọn áp dụng.');
    for(let count=0;['queued','running'].includes(job.status)&&count<60;count++){
      await new Promise(resolve=>setTimeout(resolve,1000));
      if(state.projectId!==projectId)return;
      job=await api(`/api/v1/projects/${projectId}/media-resolution-jobs/${job.resolution_job_id}`);
    }
    if(state.projectId!==projectId)return;
    state.mediaPlans=await api(`/api/v1/projects/${projectId}/media-plans`);renderBrowser();
    toast(job.status==='succeeded'?'Tư liệu đã sẵn sàng. Chọn cảnh và áp dụng vào timeline.':job.status==='needs_approval'?'Tư liệu cần phê duyệt chi phí.':job.failure_reason??'Hàng đợi đang xử lý; làm mới để xem trạng thái.',job.status==='failed');
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
$("#canonical-shot-list").addEventListener('click',event=>{const card=event.target.closest('[data-canonical-shot]');if(!card)return;state.selectedClipId=card.dataset.canonicalShot;render();});
$("#apply-silence-review").addEventListener('click',async event=>{
  const button=event.currentTarget;button.disabled=true;
  try{
    const analysis=reviewedAnalysis(),ids=[...$("#silence-review-list").querySelectorAll('[data-silence-id]:checked:not(:disabled)')].map(input=>input.dataset.silenceId);
    if(!analysis)throw new Error('Kết quả đang xem đã thay đổi. Chọn lại tác vụ để kiểm tra.');
    const selection=silenceSelection(analysis,ids);
    await api(`/api/v1/projects/${state.projectId}/timeline`,{method:'POST',body:JSON.stringify({analysis_id:analysis.analysis_id,
      media_plan_id:activeMediaPlan()?.analysis_id===analysis.analysis_id?activeMediaPlan().media_plan_id:null,silence_decision_ids:selection,expected_timeline_version:state.timeline?.current_version??null,actor_ref:'studio-user'})});
    await loadProject();toast('Đã lưu timeline với các khoảng cắt đã chọn. Cần xem preview và duyệt lại.');
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
$("#analysis-review").addEventListener('click',async event=>{
  const button=event.target.closest('[data-highlight-count],[data-highlight-mode],[data-apply-highlight]');if(!button)return;
  button.disabled=true;
  try{
    if(button.dataset.applyHighlight){
      await api(`/api/v1/projects/${state.projectId}/highlight-drafts/${encodeURIComponent(button.dataset.applyHighlight)}/apply`,{
        method:'POST',body:JSON.stringify({expected_timeline_version:state.timeline?.current_version??null})});
      await loadProject();toast('Draft đã đưa vào timeline. Xem preview và duyệt trước khi render.');
    }else{
      const analysis=reviewedAnalysis();
      if(!analysis)throw new Error('Chờ phân tích hoàn tất.');
      const drafts=await api(`/api/v1/projects/${state.projectId}/highlight-drafts`,{method:'POST',body:JSON.stringify({
        analysis_id:analysis.analysis_id,transcript_id:analysis.transcript?.transcript_id??null,
        ...(state.selectedSceneAssessmentId?{scene_intelligence_id:state.selectedSceneAssessmentId}:{}),
        count:Number(button.dataset.highlightCount??3),mode:button.dataset.highlightMode??'top_highlights',maximum_duration_seconds:60})});
      state.highlightDrafts=await api(`/api/v1/projects/${state.projectId}/highlight-drafts`);renderAnalysisReview();
      toast(`Đã lưu ${drafts.length} draft phù hợp. Timeline hiện tại được giữ nguyên.`);
    }
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
function captureTranscriptInput(event){const input=event.target.closest('[data-transcript-text]');if(input)state.transcriptDrafts.set(input.dataset.transcriptText,input.value);}
$('#scene-assessment').addEventListener('change',event=>{state.selectedSceneAssessmentId=event.target.value;renderAnalysisReview();});
$('#assess-scenes').addEventListener('click',async()=>{
  const analysis=reviewedAnalysis();if(!analysis)return;
  const button=$('#assess-scenes');button.disabled=true;
  try{
    const assessment=await api(`/api/v1/projects/${state.projectId}/scene-intelligence`,{method:'POST',body:JSON.stringify({
      analysis_id:analysis.analysis_id,transcript_id:analysis.transcript?.transcript_id??null,
      vision_analysis_id:$('#scene-vision').value||null})});
    state.selectedSceneAssessmentId=assessment.assessment_id;
    state.sceneAssessments=await api(`/api/v1/projects/${state.projectId}/scene-intelligence`);
    renderAnalysisReview();toast('Đã lưu bản đánh giá cảnh. Highlight sẽ dùng bản đang chọn.');
  }catch(error){toast(error.message,true);}finally{button.disabled=!state.sceneIntelligenceSupported;}
});
async function saveTranscriptReview(event){
  const form=event.target.closest('[data-transcript-edit]');if(!form)return;event.preventDefault();
  const analysis=state.analyses.find(a=>a.analysis_id===form.dataset.analysisId&&a.project_id===state.projectId&&a.workspace_id===state.workspaceId),button=form.querySelector('button[type="submit"]');button.disabled=true;
  try{
    if(analysis?.transcript?.transcript_id!==form.dataset.transcriptId)throw new Error('Transcript đã thay đổi. Làm mới trước khi lưu.');
    const body=transcriptEditPayload(analysis,state.timeline,form.dataset.transcriptEdit,form.querySelector('textarea').value);
    await api(`/api/v1/projects/${state.projectId}/analyses/${analysis.analysis_id}/transcript`,{method:'POST',body:JSON.stringify(body)});
    state.transcriptDrafts.delete(form.dataset.transcriptEdit);await loadProject();
    toast('Đã lưu transcript mới. Preview và phê duyệt cần cập nhật.');
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
}
for(const panel of [$("#browser-content"),$("#analysis-transcript-list")]){
  panel.addEventListener('input',captureTranscriptInput);
  panel.addEventListener('submit',saveTranscriptReview);
}

$("#timeline-tracks").addEventListener("click", async (event) => {
  const trackAction = event.target.closest("[data-track-action]");
  if (trackAction) {
    const track = state.timeline.snapshot.tracks.find((item) => item.track_id === trackAction.dataset.trackId);
    if (!track) return;
    const property = trackAction.dataset.trackAction;
    await mutate([{
      type: "set_track_state",
      track_id: track.track_id,
      ...(property === "lock" ? { locked: !track.locked } : { muted: !track.muted }),
    }], `track-${property}`);
    return;
  }
  const clip = event.target.closest("[data-clip-id]");
  if (!clip) return;
  state.selectedClipId = clip.dataset.clipId;
  renderTimeline();
  renderInspector();
});
$("#timeline-tracks").addEventListener("dragstart", (event) => {
  const clip = event.target.closest("[data-clip-id]");
  if (!clip || clip.getAttribute("draggable") !== "true") return;
  event.dataTransfer.effectAllowed = "move";
  state.draggingClipId = clip.dataset.clipId;
  event.dataTransfer.setData("text/plain", clip.dataset.clipId);
  event.dataTransfer.setData("application/x-npd-track-type", clip.dataset.trackType);
});
$("#timeline-tracks").addEventListener("dragover", (event) => {
  const lane = event.target.closest("[data-track-id]");
  if (!lane) return;
  const sourceType = getClip(state.timeline, state.draggingClipId)?.track?.type;
  if (canDropOnTrack(sourceType || lane.dataset.trackType, lane.dataset.trackType, lane.dataset.trackLocked === "true")) {
    event.preventDefault();
    lane.classList.add("drag-target");
  }
});
$("#timeline-tracks").addEventListener("dragend", () => {
  state.draggingClipId = null;
  document.querySelectorAll(".drag-target").forEach((item) => item.classList.remove("drag-target"));
});
$("#timeline-tracks").addEventListener("dragleave", (event) => event.target.closest("[data-track-id]")?.classList.remove("drag-target"));
$("#timeline-tracks").addEventListener("drop", async (event) => {
  const lane = event.target.closest("[data-track-id]");
  document.querySelectorAll(".drag-target").forEach((item) => item.classList.remove("drag-target"));
  if (!lane) return;
  event.preventDefault();
  const clipId = event.dataTransfer.getData("text/plain");
  state.draggingClipId = null;
  const selection = getClip(state.timeline, clipId);
  if (!selection || !canDropOnTrack(selection.track.type, lane.dataset.trackType, lane.dataset.trackLocked === "true")) return;
  const start = timelinePositionFromPointer(event.clientX, lane.getBoundingClientRect().left, 0, state.zoom, state.snapping);
  state.selectedClipId = clipId;
  await mutate([{ type: "move", clip_id: clipId, target_track_id: lane.dataset.trackId, timeline_start: start }], "drag-drop");
});

$("#timeline-ruler").addEventListener("click", (event) => {
  const rect = event.currentTarget.getBoundingClientRect();
  setPlayhead(timelinePositionFromPointer(event.clientX, rect.left, 0, state.zoom, state.snapping));
});
$("#playhead-range").addEventListener("input", (event) => setPlayhead(event.target.value));
$("#zoom-range").addEventListener("input", (event) => { state.zoom = Number(event.target.value); renderTimeline(); });
$("#snap-button").addEventListener("click", (event) => {
  state.snapping = !state.snapping;
  event.currentTarget.classList.toggle("active", state.snapping);
  event.currentTarget.setAttribute("aria-pressed", String(state.snapping));
  event.currentTarget.textContent = state.snapping ? "⌁ Snap 0.25s" : "⌁ Snap off";
});

$("#clip-inspector").addEventListener("submit", async (event) => {
  event.preventDefault();
  const selection = selectedClip();
  if (!selection) return;
  await mutate([
    {
      type: "trim",
      clip_id: selection.clip.clip_id,
      ...(selection.clip.kind === "image" ? {duration:Number($('#clip-display-duration').value)} : {source_start: Number($("#clip-source-start").value), source_end: Number($("#clip-source-end").value)}),
      timeline_start: Number($("#clip-timeline-start").value),
    },
    {
      type: "set_clip_properties",
      clip_id: selection.clip.clip_id,
      ...(selection.clip.kind === "image" ? {} : {speed: Number($("#clip-speed").value)}),
      opacity: Number($("#clip-opacity").value),
      volume: Number($("#clip-volume").value),
      crop: {
        x: Number($("#clip-crop-x").value),
        y: Number($("#clip-crop-y").value),
        width: Number($("#clip-crop-width").value),
        height: Number($("#clip-crop-height").value),
      },
      transform: {
        x: Number($("#clip-transform-x").value),
        y: Number($("#clip-transform-y").value),
        scale: Number($("#clip-transform-scale").value),
        rotation_degrees: Number($("#clip-transform-rotation").value),
      },
    },
  ], "inspector-edit");
});
$("#split-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  await mutate([{ type: "split", clip_id: selection.clip.clip_id, at_seconds: state.playhead }], "split-at-playhead");
});
$("#duplicate-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  await mutate([{ type: "duplicate", clip_id: selection.clip.clip_id, timeline_start: selection.clip.timeline_start + selection.clip.duration }], "duplicate-clip");
});
$("#reorder-up-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  const currentIndex = selection.track.clips.findIndex((item) => item.clip_id === selection.clip.clip_id);
  if (currentIndex > 0) {
    await mutate([{ type: "reorder", clip_id: selection.clip.clip_id, target_index: currentIndex - 1 }], "reorder-clip");
  }
});
$("#reorder-down-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  const currentIndex = selection.track.clips.findIndex((item) => item.clip_id === selection.clip.clip_id);
  if (currentIndex >= 0 && currentIndex < selection.track.clips.length - 1) {
    await mutate([{ type: "reorder", clip_id: selection.clip.clip_id, target_index: currentIndex + 1 }], "reorder-clip");
  }
});
$("#toggle-clip-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  await mutate([{ type: "disable", clip_id: selection.clip.clip_id, disabled: !selection.clip.disabled }], "toggle-clip");
});
$("#delete-button").addEventListener("click", async () => {
  const selection = selectedClip();
  if (!selection) return;
  await mutate([{ type: "delete", clip_id: selection.clip.clip_id }], "delete-from-timeline");
});
$("#undo-button").addEventListener("click", async () => {
  const target=state.undoStack.at(-1);if(target)await restoreVersion(target,{isUndo:true});
});
$("#redo-button").addEventListener("click", async () => {
  const target = state.redoStack.at(-1);
  if (target) await restoreVersion(target);
});

$("#play-button").addEventListener("click", () => {
  const video = $("#preview-video");
  if (video.hidden) return toast("Hãy tạo preview trước khi phát.");
  if (video.paused) video.play(); else video.pause();
});
$("#back-button").addEventListener("click", () => setPlayhead(state.playhead - 1));
$("#preview-video").addEventListener("timeupdate", (event) => setPlayhead(event.target.currentTime, false));

window.addEventListener("beforeunload", () => {
  audioReview.dispose();
  stockReview.dispose();
  videoReview.dispose();
  variantFamilies.dispose();
  variantNarration?.dispose();
  videoWordReview?.dispose();sqlAudioProcessing?.dispose();sourceLinkedEditor?.dispose();manualReframeEditor?.dispose();brollPlanController?.dispose();brollTimelineController?.dispose();brollInternalController?.dispose();
  unsubscribeVideoBusy();
  stopPreviewPolling();
  stopProductionPolling();
  stopAnalyticsPolling();
});
// Reviewed B-roll placement Root integration.
function brollTimelineEditorState(){const v=sqlEditorState();return {...v,analysis:activeAnalysis(),mediaPlanId:state.selectedBrollPlanId,
  brollDraft:brollTimelineDraft(),busy:v.busy||variantFamilies.isBusy()||variantNarration?.isWorking()===true||videoWordReview?.isWorking()===true
    ||sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true,
  dirty:v.dirty||brollInternalHeld()||brollPreparationHeld()||manualReframeHeld()||sourceLinkedHeld()||variantFamilies.isPending()
    ||variantNarration?.isPending()===true||videoWordReview?.isDirty()===true||videoWordReview?.isPending()===true
    ||sqlAudioProcessing?.isDirty()===true||sqlAudioProcessing?.isPending()===true};}
function brollTimelineSourceContext(){const v=brollTimelineEditorState();return sqlAudioStable([v.workspaceId,v.workspaceSlug,v.projectId,v.principal,
  sessionToken(),v.assets,v.analyses,v.analysis,v.mediaPlans,v.mediaPlanId,v.videoReviewSelection,productionWorkbenchDraft(),audioWorkbenchDraft()]);}
function brollTimelineCanonicalContext(){return sqlAudioStable([state.timeline,state.versions,state.preview,state.productionPackage,
  state.activeProductionRender,state.selectedClipId,state.playhead,state.undoStack,state.redoStack]);}
let brollTimelineInstalled=null;
function assertBrollTimelineOperation(op,allowInstalled=true){const v=brollTimelineEditorState(),canonical=brollTimelineCanonicalContext();
  if(!op||brollTimelineOperation!==op||brollTimelineSourceContext()!==op.source||brollTimelineDraft()!==op.draft||v.busy||v.dirty
    ||canonical!==op.canonical&&!(allowInstalled&&brollTimelineInstalled?.op===op&&canonical===brollTimelineInstalled.canonical)
    ||!Number.isFinite(Date.parse(v.principal?.expires_at))||Date.parse(v.principal.expires_at)<=Date.now()
    ||!['viewer','editor','reviewer','owner'].includes(audioRole(v))
    ||op.write&&(v.principal.human_write_enabled!==true||!['editor','reviewer','owner'].includes(audioRole(v))))
    throw Error('Nguồn, phiên, timeline hoặc lựa chọn B-roll đã đổi; giữ đúng yêu cầu để đối chiếu.');}
function brollTimelineChoice(){return brollTimelineSelection({
  item_ids:[...document.querySelectorAll('#broll-timeline-items [data-broll-timeline-item]')].filter(e=>e.checked).map(e=>e.dataset.brollTimelineItem),
  replace_plan_clips:$('#broll-timeline-replace').checked});}
function clearBrollTimelineForm(){brollTimelineFormRead=null;brollTimelineBaseline=null;$('#broll-timeline-items').replaceChildren();
  $('#broll-timeline-replace').checked=false;$('#broll-timeline-acknowledge').checked=false;}
function readBrollTimelineForm(data){brollTimelineRead(data,brollTimelineEditorState());const target=$('#broll-timeline-items');target.replaceChildren();
  const pending=brollTimelineController.state().pending;
  for(const [index,item] of data.items.entries()){const label=document.createElement('label'),input=document.createElement('input'),text=document.createElement('span');
    input.type='checkbox';input.id='broll-timeline-item-'+index;input.setAttribute('data-broll-timeline-setting','');
    input.setAttribute('data-broll-timeline-item',item.media_plan_item_id);input.checked=pending?.body.item_ids.includes(item.media_plan_item_id)===true;
    input.disabled=!data.ready_item_ids.includes(item.media_plan_item_id);text.textContent=(item.broll?.broll_intent??item.media_plan_item_id)
      +' · '+(data.ready_item_ids.includes(item.media_plan_item_id)?'Đã có tư liệu':'Chưa có tư liệu đã phân giải');
    label.append(input,text);target.append(label);}
  $('#broll-timeline-replace').checked=pending?.body.replace_plan_clips===true;$('#broll-timeline-acknowledge').checked=false;
  brollTimelineFormRead={data:structuredClone(data),source:brollTimelineSourceContext(),timeline:sqlAudioStable(state.timeline)};
  brollTimelineBaseline=brollTimelineDraft();}
function syncBrollTimelineForm(){if(!brollTimelineController)return;
  if(brollTimelineFormRead&&(brollTimelineFormRead.source!==brollTimelineSourceContext()||brollTimelineFormRead.timeline!==sqlAudioStable(state.timeline))&&!brollTimelineDirty()&&!brollTimelineBusy)
    clearBrollTimelineForm();
  const v=brollTimelineEditorState(),c=brollTimelineController.state(),held=brollTimelineStored()||c.held||c.pending!==null;
  const valid=brollTimelineFormRead?.source===brollTimelineSourceContext()&&brollTimelineFormRead?.timeline===sqlAudioStable(state.timeline),readable=!v.busy&&!v.dirty
    &&Number.isFinite(Date.parse(v.principal?.expires_at))&&Date.parse(v.principal.expires_at)>Date.now()
    &&['viewer','editor','reviewer','owner'].includes(audioRole(v)),writable=readable&&v.principal?.human_write_enabled===true
    &&['editor','reviewer','owner'].includes(audioRole(v));
  $('#broll-timeline-read').disabled=brollTimelineBusy||brollTimelineDirty()&&!held||!readable||!v.mediaPlanId;
  $('#broll-timeline-open-held').disabled=brollTimelineBusy||brollTimelineDirty()||!held||!readable;
  $('#broll-timeline-fields').disabled=brollTimelineBusy||held||!valid||!writable;
  $('#broll-timeline-acknowledge').disabled=brollTimelineBusy||!writable;
  $('#broll-timeline-apply').disabled=brollTimelineBusy||held||!valid||!writable||!brollTimelineFormRead?.data.ready_item_ids.length;
  $('#broll-timeline-reconcile').disabled=brollTimelineBusy||!c.pending||!writable;
  $('#broll-timeline-retry').disabled=brollTimelineBusy||!c.canRetry||!writable;
  $('#broll-timeline-discard').disabled=brollTimelineBusy||held||!brollTimelineDirty();
  $('#broll-timeline-context').textContent=valid?'Đề xuất '+v.mediaPlanId+' · Timeline v'+brollTimelineFormRead.data.timeline_version
    +' · '+brollTimelineFormRead.data.ready_item_ids.length+' cảnh có tư liệu. Chưa cấp quyền đăng bài.':'Chọn đề xuất trong mục B-roll rồi đọc đúng bản trước khi sửa.';
  $('#broll-timeline-status').textContent=brollTimelineController.getStatus();
  $('#broll-timeline-pending').textContent=c.pending?JSON.stringify({request_key:c.pending.body.request_key,media_plan_id:c.pending.media_plan_id,
    parent_version:c.pending.body.expected_version,item_ids:c.pending.body.item_ids,replace_plan_clips:c.pending.body.replace_plan_clips},null,2)
    :held?'Có bản ghi đang giữ; chỉ đọc và đối chiếu đúng yêu cầu. Không tạo lần áp dụng mới.':'';
}
async function brollTimelineApi(path,options={}){const op=brollTimelineOperation;assertBrollTimelineOperation(op);
  const route='/api/v1/projects/'+state.projectId+'/timeline/broll-review/'+state.selectedBrollPlanId,method=(options.method??'GET').toUpperCase();
  if(path!==route||!['GET','PUT'].includes(method)||method==='PUT'&&!['apply','retry'].includes(op.kind))
    throw Error('Chỉ đọc hoặc áp dụng đúng B-roll đã review; không gọi provider.');
  if(method==='PUT'){const p=brollTimelineController.state().pending,body=JSON.parse(options.body);
    if(!op.write||!p||sqlAudioStable(body)!==sqlAudioStable(p.body)||$('#broll-timeline-acknowledge').checked!==true)
      throw Error('Chỉ gửi đúng lựa chọn đang giữ sau xác nhận rõ ràng.');
    const key='vf-sql-broll-timeline-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]);
    const raw=brollTimelineStore.getItem(key);assertBrollTimelineOperation(op);
    if(raw!==JSON.stringify(p))throw Error('Bản ghi B-roll đã đổi trước khi gửi; giữ nguyên.');
  }
  const value=await api(path,{...options,brollTimelineAdmission});assertBrollTimelineOperation(op);return value;}
const brollTimelineStorage={
  getItem(key){const op=brollTimelineOperation;
    if(!op){const scope=()=>JSON.stringify([state.workspaceId,state.projectId,state.principal,sessionToken()]),before=scope();
      const expected='vf-sql-broll-timeline-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal?.subject]);
      if(key!==expected)throw Error('Chỉ đọc ô chờ B-roll của dự án hiện tại.');
      const raw=brollTimelineStore?.getItem(key);if(scope()!==before)throw Error('Phiên đã đổi khi đọc ô chờ B-roll.');return raw;}
    assertBrollTimelineOperation(op);
    const raw=brollTimelineStore?.getItem(key);assertBrollTimelineOperation(op);return raw;},
  setItem(key,raw){const op=brollTimelineOperation;assertBrollTimelineOperation(op);
    brollTimelineStore.setItem(key,raw);assertBrollTimelineOperation(op);},
  compareAndRemoveItem(key,raw){const op=brollTimelineOperation;assertBrollTimelineOperation(op);
    const expected='vf-sql-broll-timeline-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]);
    if(key!==expected||typeof raw!=='string'||typeof brollTimelineStore?.compareAndRemoveItem!=='function')return false;
    const result=brollTimelineStore.compareAndRemoveItem(key,raw);assertBrollTimelineOperation(op);return result===true;}
};
function brollTimelinePreserved(before,after,request,planId){
  const outer=({schema_version,tracks,metadata,...v})=>v,meta=({broll_review,...v})=>v,others=tracks=>tracks.filter(t=>t.kind!=='broll').map(({order,...v})=>v);
  if(sqlAudioStable(outer(before))!==sqlAudioStable(outer(after))||sqlAudioStable(meta(before.metadata))!==sqlAudioStable(meta(after.metadata))
    ||sqlAudioStable(others(before.tracks))!==sqlAudioStable(others(after.tracks)))throw Error('B-roll đã đổi nguồn, âm thanh, phụ đề hoặc metadata ngoài lựa chọn.');
  for(const t of before.tracks.filter(t=>t.kind==='broll')){const saved=after.tracks.find(v=>v.track_id===t.track_id),info=({order,clips,...v})=>v;
    const replaced=c=>request.replace_plan_clips&&c.metadata?.media_plan_id===planId&&request.item_ids.includes(c.metadata?.media_plan_item_id);
    if(!saved||sqlAudioStable(info(t))!==sqlAudioStable(info(saved))||t.clips.filter(c=>!replaced(c)).some(c=>!saved.clips.some(v=>sqlAudioStable(v)===sqlAudioStable(c))))
      throw Error('B-roll đã đổi clip ngoài những cảnh được xác nhận thay thế.');}
}
async function refreshBrollTimeline(value,requestGuard){
  const op=brollTimelineOperation,guard=()=>{assertBrollTimelineOperation(op,false);
    if(typeof requestGuard!=='function'||requestGuard()!==true)throw Error('Thiếu ràng buộc đồng bộ với đúng yêu cầu B-roll.');
    assertBrollTimelineOperation(op,false);};guard();
  const current=brollTimelineEditorState(),r=value.receipt,t=value.timeline,request=value.request,path='/api/v1/projects/'+value.project_id+'/timeline/broll-review/'+value.media_plan_id;
  brollTimelineRead(value.read,current);
  if(value.workspace_id!==current.workspaceId||value.project_id!==current.projectId||value.actor_ref!==current.principal.subject
    ||value.media_plan_id!==current.mediaPlanId||r.actor_ref!==value.actor_ref||r.media_plan_id!==value.media_plan_id
    ||r.timeline_id!==current.timeline.timeline_id||r.parent_version_id!==value.parent_version_id||r.parent_version!==value.parent_version
    ||r.result_version!==value.result_version||value.result_version!==value.parent_version+1||r.context_sha256!==request.expected_context_sha256
    ||request.expected_version!==value.parent_version||request.expected_timeline_id!==r.timeline_id||request.request_key!==r.request_key
    ||sqlAudioStable(request.item_ids)!==sqlAudioStable(r.item_ids)||request.replace_plan_clips!==r.replace_plan_clips||request.acknowledged!==true
    ||sqlAudioStable(value.read.timeline)!==sqlAudioStable(t)||sqlAudioStable(value.read.receipt)!==sqlAudioStable(r)
    ||![value.parent_version,value.result_version].includes(current.timeline.current_version)
    ||current.timeline.current_version===value.parent_version&&current.timeline.current_version_id!==value.parent_version_id
    ||current.timeline.current_version===value.result_version&&sqlAudioStable(current.timeline)!==sqlAudioStable(t))
    throw Error('Biên nhận B-roll chưa khớp nguồn, người sửa, lựa chọn hoặc bản cha.');
  const proof=await api(path,{cache:'no-store'});guard();brollTimelineRead(proof,brollTimelineEditorState());
  const equalRead=(a,b)=>sqlAudioStable({...a,replayed:false})===sqlAudioStable({...b,replayed:false});
  if(!equalRead(proof,value.read))throw Error('B-roll hiện tại chưa khớp đúng biên nhận đang giữ.');
  const versions=await api('/api/v1/projects/'+value.project_id+'/timeline/versions',{cache:'no-store'});guard();
  if(!videoWordHistoryMatches(versions,proof.timeline))throw Error('Lịch sử B-roll chưa khớp timeline hiện tại.');
  const parent=versions.find(v=>v.version===value.parent_version),head=versions.find(v=>v.version===value.result_version);
  if(parent?.timeline_version_id!==value.parent_version_id||head?.timeline_version_id!==t.current_version_id||head.actor_ref!==r.actor_ref
    ||head.mutation?.type!=='broll-timeline-review'||head.mutation.source_media_mutated!==false||head.mutation.publish_requested!==false
    ||sqlAudioStable(head.mutation.receipt)!==sqlAudioStable(r)||sqlAudioStable(head.snapshot)!==sqlAudioStable(t.snapshot)
    ||value.parent_timeline&&sqlAudioStable(parent.snapshot)!==sqlAudioStable(value.parent_timeline.snapshot)
    ||current.timeline.current_version===value.parent_version&&sqlAudioStable(parent.snapshot)!==sqlAudioStable(current.timeline.snapshot))
    throw Error('Lịch sử chưa chứng minh đúng bản cha, nguồn và lựa chọn B-roll.');
  brollTimelinePreserved(parent.snapshot,proof.timeline.snapshot,request,value.media_plan_id);
  const last=await api(path,{cache:'no-store'});guard();brollTimelineRead(last,brollTimelineEditorState());
  if(!equalRead(last,proof))throw Error('B-roll đã đổi sau khi đọc lịch sử; giữ yêu cầu.');
  guard();
  state.timeline=structuredClone(last.timeline);state.versions=structuredClone(versions);state.selectedClipId=null;state.undoStack=[];state.redoStack=[];
  state.playhead=Math.min(state.playhead??0,state.timeline.snapshot.duration_seconds);
  if(state.preview)state.preview={...state.preview,status:'stale',valid_for_current_timeline:false};
  if(state.productionPackage)state.productionPackage={...state.productionPackage,current_for_timeline:false,approval:null,latest_review_render:null,latest_final_render:null};
  state.activeProductionRender=null;stopPreviewPolling();stopProductionPolling();render();
  brollTimelineInstalled={op,canonical:brollTimelineCanonicalContext()};
}
brollTimelineController=initializeSqlBrollTimelineReview({api:brollTimelineApi,getState:brollTimelineEditorState,getSessionToken:sessionToken,
  storage:brollTimelineStorage,onSaved:refreshBrollTimeline,onRead:value=>{assertBrollTimelineOperation(brollTimelineOperation);brollTimelineRead(value,brollTimelineEditorState());},
  onMessage:(text,error)=>toast(text,error),onBusyChanged:()=>{if(brollTimelineController)syncBrollTimelineForm();if(brollInternalController)syncBrollInternalForm();}});
async function runBrollTimelineAction(kind){
  if(brollTimelineBusy)return;
  try{syncBrollTimelineForm();
    if(kind==='read'&&brollTimelineDirty()&&!brollTimelineStored()&&!brollTimelineController.isPending())
      throw Error('Bỏ lựa chọn chưa gửi trước khi đọc lại B-roll.');
    if(['apply','retry'].includes(kind)&&$('#broll-timeline-acknowledge').checked!==true)throw Error('Xác nhận rõ lựa chọn hoặc đúng yêu cầu đang giữ trước khi gửi.');
    const selection=kind==='apply'?structuredClone(brollTimelineChoice()):null;
    const op=Object.freeze({kind,write:kind!=='read',source:brollTimelineSourceContext(),draft:brollTimelineDraft(),canonical:brollTimelineCanonicalContext()});
    brollTimelineOperation=op;brollTimelineInstalled=null;assertBrollTimelineOperation(op);brollTimelineBusy=true;syncBrollPlanPeers();
    if(kind==='read'){const data=await brollTimelineController.reload();assertBrollTimelineOperation(op);readBrollTimelineForm(data);}
    else{const result=await(kind==='apply'?brollTimelineController.applySelection(selection,{acknowledged:true})
      :kind==='reconcile'?brollTimelineController.reconcile():brollTimelineController.retry());
      if(result&&!brollTimelineController.isPending())clearBrollTimelineForm();}
  }catch(error){toast(error.message,true);}
  finally{brollTimelineBusy=false;brollTimelineOperation=null;brollTimelineInstalled=null;syncBrollPlanPeers();}
}
for(const [id,kind]of [['broll-timeline-read','read'],['broll-timeline-apply','apply'],['broll-timeline-reconcile','reconcile'],['broll-timeline-retry','retry']])
  $('#'+id).addEventListener('click',()=>runBrollTimelineAction(kind));
$('#broll-timeline-form').addEventListener('submit',event=>event.preventDefault());
$('#broll-timeline-form').addEventListener('change',syncBrollPlanPeers);
$('#broll-timeline-discard').addEventListener('click',()=>{
  if(brollTimelineBusy||brollTimelineStored()||brollTimelineController.isPending())return toast('Giữ yêu cầu chưa rõ kết quả; đối chiếu trước khi bỏ lựa chọn.',true);
  const data=brollTimelineFormRead?.source===brollTimelineSourceContext()&&brollTimelineFormRead?.timeline===sqlAudioStable(state.timeline)?structuredClone(brollTimelineFormRead.data):null;
  clearBrollTimelineForm();if(data)readBrollTimelineForm(data);syncBrollPlanPeers();
});
$('#broll-timeline-open-held').addEventListener('click',()=>{
  try{
    const v=brollTimelineEditorState();
    if(brollTimelineBusy||brollTimelineController.isWorking()||brollTimelineDirty()||v.busy||v.dirty
      ||!['viewer','editor','reviewer','owner'].includes(audioRole(v))||!Number.isFinite(Date.parse(v.principal?.expires_at))
      ||Date.parse(v.principal.expires_at)<=Date.now())throw Error('Chờ hoặc bỏ bản sửa chưa gửi trước khi mở đúng yêu cầu đang giữ.');
    const source=brollTimelineSourceContext(),canonical=brollTimelineCanonicalContext(),draft=brollTimelineDraft();
    const key='vf-sql-broll-timeline-pending-v1:'+JSON.stringify([state.workspaceId,state.projectId,state.principal.subject]);
    const raw=brollTimelineStore.getItem(key);
    const unchanged=()=>{if(source!==brollTimelineSourceContext()||canonical!==brollTimelineCanonicalContext()||draft!==brollTimelineDraft()
      ||brollTimelineEditorState().busy||brollTimelineEditorState().dirty
      ||!Number.isFinite(Date.parse(state.principal?.expires_at))||Date.parse(state.principal.expires_at)<=Date.now())
      throw Error('Nguồn hoặc phiên đã đổi khi đọc yêu cầu đang giữ.');};
    unchanged();if(typeof raw!=='string'||new TextEncoder().encode(raw).length>5*1024*1024)throw Error('Chưa có đúng bản ghi B-roll có thể đọc.');
    const p=JSON.parse(raw),plan=state.mediaPlans.find(item=>item.media_plan_id===p.media_plan_id);
    if(p.schema_version!=='sql-broll-timeline-pending.v1'||p.workspace_id!==state.workspaceId||p.project_id!==state.projectId||p.actor_ref!==state.principal.subject
      ||!/^mpl_[A-Za-z0-9_-]{4,60}$/.test(p.media_plan_id)||!plan||plan.workspace_id!==state.workspaceId||plan.project_id!==state.projectId
      ||plan.analysis_id!==state.timeline.source_analysis_id||plan.configuration?.purpose!=='supporting_broll'
      ||p.body?.expected_timeline_id!==state.timeline.timeline_id||!Number.isSafeInteger(p.body.expected_version)
      ||![p.body.expected_version,p.body.expected_version+1].includes(state.timeline.current_version)
      ||!/^[A-Za-z0-9_-]{8,128}$/.test(p.body.request_key))throw Error('Bản ghi chưa xác định đúng đề xuất và nguồn của dự án.');
    const finalRaw=brollTimelineStore.getItem(key);unchanged();if(finalRaw!==raw)throw Error('Bản ghi đang giữ đã đổi; giữ nguyên.');
    clearBrollTimelineForm();state.selectedBrollPlanId=p.media_plan_id;state.query='';state.panelTab='broll';
    const search=$('#browser-search');if(search)search.value='';renderBrowser();syncBrollPlanPeers();
    $('#broll-timeline-context').textContent='Đã mở đề xuất của bản ghi đang giữ. Đọc và đối chiếu đầy đủ trước khi nhận kết quả hoặc gửi lại.';
    $('#broll-timeline-read').focus();
  }catch(error){toast(error.message,true);}
});
syncBrollTimelineForm();

// Reviewed internal B-roll resolution Root integration. No timer or timeline write.
function brollInternalEditorState(){const v=sqlEditorState();return {...v,analysis:activeAnalysis(),mediaPlanId:state.selectedBrollPlanId,
  mediaPlanItemId:brollInternalItemId,internalResolutionDraft:brollInternalDraft(),
  busy:v.busy||variantFamilies.isBusy()||variantNarration?.isWorking()===true||videoWordReview?.isWorking()===true
    ||sqlAudioProcessing?.isWorking()===true||sourceLinkedEditor?.isWorking()===true||manualReframeEditor?.isWorking()===true,
  dirty:v.dirty||brollPreparationHeld()||brollTimelineHeld()||manualReframeHeld()||sourceLinkedHeld()||variantFamilies.isPending()
    ||variantNarration?.isPending()===true||videoWordReview?.isDirty()===true||videoWordReview?.isPending()===true
    ||sqlAudioProcessing?.isDirty()===true||sqlAudioProcessing?.isPending()===true};}
function brollInternalSourceContext(){const v=brollInternalEditorState();return sqlAudioStable([v.workspaceId,v.workspaceSlug,v.projectId,v.principal,
  sessionToken(),v.timeline,v.assets,v.analyses,v.analysis,v.mediaPlanId,v.mediaPlanItemId,v.videoReviewSelection,
  state.versions,state.preview,state.productionPackage,state.activeProductionRender,state.selectedClipId,state.playhead,state.undoStack,state.redoStack,
  productionWorkbenchDraft(),audioWorkbenchDraft()]);}
let brollInternalInstalled=null;
function assertBrollInternalOperation(op,allowInstalled=true){const v=brollInternalEditorState(),plans=sqlAudioStable(state.mediaPlans);
  if(!op||brollInternalOperation!==op||brollInternalSourceContext()!==op.source||brollInternalDraft()!==op.draft||v.busy||v.dirty
    ||plans!==op.plans&&!(allowInstalled&&brollInternalInstalled?.op===op&&plans===brollInternalInstalled.plans)
    ||!Number.isFinite(Date.parse(v.principal?.expires_at))||Date.parse(v.principal.expires_at)<=Date.now()
    ||!['viewer','editor','reviewer','owner'].includes(audioRole(v))
    ||op.write&&(v.principal.human_write_enabled!==true||!['editor','reviewer','owner'].includes(audioRole(v))))
    throw Error('Nguồn, phiên, đề xuất hoặc lựa chọn đã đổi; giữ đúng yêu cầu phân giải để đối chiếu.');}
function brollInternalRoute(){return '/api/v1/projects/'+state.projectId+'/media-plans/'+state.selectedBrollPlanId+'/items/'+brollInternalItemId+'/internal-resolution-review';}
function clearBrollInternalForm(){brollInternalFormRead=null;brollInternalBaseline=null;$('#broll-internal-asset').replaceChildren();
  $('#broll-internal-acknowledge').checked=false;}
function brollInternalSelectors(){const planSelect=$('#broll-internal-plan'),itemSelect=$('#broll-internal-item');
  planSelect.replaceChildren();for(const p of compatibleBrollPlans(state.mediaPlans,activeAnalysis())){const e=document.createElement('option');
    e.value=p.media_plan_id;e.textContent=p.media_plan_id;planSelect.append(e);}planSelect.value=state.selectedBrollPlanId;
  const plan=state.mediaPlans.find(p=>p.media_plan_id===state.selectedBrollPlanId);itemSelect.replaceChildren();
  if(!plan?.items.some(i=>i.media_plan_item_id===brollInternalItemId))brollInternalItemId=plan?.items[0]?.media_plan_item_id??'';
  for(const i of plan?.items??[]){const e=document.createElement('option');e.value=i.media_plan_item_id;
    e.textContent='Cảnh '+(i.ordinal+1)+' · '+(i.broll?.broll_intent??i.media_plan_item_id);itemSelect.append(e);}itemSelect.value=brollInternalItemId;}
function readBrollInternalForm(data){validateBrollInternalContext(data,brollInternalEditorState());const select=$('#broll-internal-asset');select.replaceChildren();
  const empty=document.createElement('option');empty.value='';empty.textContent='Chọn tư liệu đã lưu';select.append(empty);
  for(const c of data.candidates){const e=document.createElement('option');e.value=c.asset_id;e.disabled=!c.available;
    e.textContent=(c.candidate.filename??c.asset_id)+' · '+(c.candidate.rights_status??'unknown')+' · '+(c.available?'Sẵn sàng':'Không dùng được: '+c.unavailable_code);select.append(e);}
  select.value=brollInternalController.state().pending?.body.asset_id??'';$('#broll-internal-acknowledge').checked=false;
  brollInternalFormRead={data:structuredClone(data),source:brollInternalSourceContext(),plans:sqlAudioStable(state.mediaPlans)};brollInternalBaseline=brollInternalDraft();}
function syncBrollInternalForm(){if(!brollInternalController)return;
  if(!brollInternalBusy&&!brollInternalDirty()&&!brollInternalStored()&&!brollInternalController.isPending()){
    if(brollInternalFormRead&&(brollInternalFormRead.source!==brollInternalSourceContext()||brollInternalFormRead.plans!==sqlAudioStable(state.mediaPlans)))clearBrollInternalForm();
    brollInternalSelectors();}
  const v=brollInternalEditorState(),c=brollInternalController.state(),held=brollInternalStored()||c.pending!==null;
  const readable=!v.busy&&!v.dirty&&Number.isFinite(Date.parse(v.principal?.expires_at))&&Date.parse(v.principal.expires_at)>Date.now()
    &&['viewer','editor','reviewer','owner'].includes(audioRole(v)),writable=readable&&v.principal?.human_write_enabled===true
    &&['editor','reviewer','owner'].includes(audioRole(v)),valid=brollInternalFormRead?.source===brollInternalSourceContext()
      &&brollInternalFormRead?.plans===sqlAudioStable(state.mediaPlans);
  for(const id of ['plan','item'])$('#broll-internal-'+id).disabled=brollInternalBusy||held||brollInternalDirty()||!readable;
  $('#broll-internal-read').disabled=brollInternalBusy||brollInternalDirty()&&!held||!readable||!v.mediaPlanId||!v.mediaPlanItemId;
  $('#broll-internal-open-held').disabled=brollInternalBusy||brollInternalDirty()||!held||!readable;
  $('#broll-internal-fields').disabled=brollInternalBusy||held||!valid||!writable;
  $('#broll-internal-acknowledge').disabled=brollInternalBusy||!writable;
  $('#broll-internal-admit').disabled=brollInternalBusy||held||!valid||!writable;
  $('#broll-internal-observe').disabled=brollInternalBusy||!c.pending?.receipt||!readable;
  $('#broll-internal-retry').disabled=brollInternalBusy||!c.pending||!writable;
  $('#broll-internal-discard').disabled=brollInternalBusy||held||!brollInternalDirty();
  $('#broll-internal-context').textContent=valid?'Đề xuất '+v.mediaPlanId+' · Cảnh '+v.mediaPlanItemId+' · chỉ tái sử dụng tư liệu nội bộ.':'Chọn đề xuất và cảnh rồi đọc nguồn đã lưu.';
  const o=c.observation;$('#broll-internal-status').textContent=brollInternalStatus+(o?' · '+o.state+(o.job?' · Job '+o.job.resolution_job_id:''):'');
  $('#broll-internal-pending').textContent=c.pending?JSON.stringify({request_key:c.pending.body.request_key,asset_id:c.pending.body.asset_id,
    media_plan_id:c.pending.context.plan.media_plan_id,media_plan_item_id:c.pending.context.item.media_plan_item_id,
    resolution_job_id:c.pending.receipt?.resolution_job_id??null},null,2):held?'Có bản ghi đang giữ. Không tạo yêu cầu mới hoặc tự xóa bản ghi.':'';
  $('#broll-internal-result').textContent=o?.can_adopt?'Tư liệu '+o.output.asset_id+' · '+o.output.rights_status+' · '+(o.output.publishing_allowed?'quyền đã ghi nhận':'chưa được phép đăng')+'; chưa áp dụng vào timeline.':'';
}
async function brollInternalApi(path,options={}){const op=brollInternalOperation;assertBrollInternalOperation(op);
  const method=(options.method??'GET').toUpperCase(),base=brollInternalRoute(),p=brollInternalController.state().pending;
  const exactJob=p?.receipt?base+'/requests/'+p.body.request_key+'/jobs/'+p.receipt.resolution_job_id:null;
  if(method==='GET'&&![base,'/api/v1/auth/session',exactJob].includes(path)||method==='POST'&&(path!==base||!['admit','retry'].includes(op.kind))
    ||!['GET','POST'].includes(method))throw Error('Chỉ đọc hoặc gửi đúng phân giải nội bộ đã kiểm tra.');
  if(method==='POST'){if(!op.write||!p||sqlAudioStable(JSON.parse(options.body))!==sqlAudioStable(p.body)||$('#broll-internal-acknowledge').checked!==true)
      throw Error('Cần xác nhận đúng yêu cầu nội bộ đang giữ.');
    const raw=brollInternalStore.getItem(brollInternalBucket());assertBrollInternalOperation(op);
    if(raw!==sqlAudioStable(p))throw Error('Yêu cầu đang giữ đã đổi trước khi gửi.');}
  const result=await api(path,{...options,brollInternalAdmission});assertBrollInternalOperation(op);return result;}
const brollInternalStorage={getItem(key){const op=brollInternalOperation;
    if(!op){const before=brollInternalBareScope();if(key!==brollInternalBucket())throw Error('Chỉ đọc ô chờ nội bộ hiện tại.');
      const raw=brollInternalStore?.getItem(key);if(before!==brollInternalBareScope())throw Error('Phiên đã đổi trong ô chờ.');return raw;}
    assertBrollInternalOperation(op);const raw=brollInternalStore?.getItem(key);assertBrollInternalOperation(op);return raw;},
  setItem(key,raw){const op=brollInternalOperation;assertBrollInternalOperation(op);if(key!==brollInternalBucket())throw Error('Sai ô chờ phân giải.');
    brollInternalStore.setItem(key,raw);assertBrollInternalOperation(op);},
  compareAndRemoveItem(key,raw){const op=brollInternalOperation;assertBrollInternalOperation(op);if(key!==brollInternalBucket()||typeof raw!=='string'
      ||typeof brollInternalStore?.compareAndRemoveItem!=='function')return false;
    const result=brollInternalStore.compareAndRemoveItem(key,raw);assertBrollInternalOperation(op);return result===true;}};
async function refreshBrollInternal(value,requestGuard){const op=brollInternalOperation,guard=()=>{assertBrollInternalOperation(op,false);
    if(typeof requestGuard!=='function'||requestGuard()!==true)throw Error('Thiếu ràng buộc đồng bộ với yêu cầu nội bộ đang giữ.');assertBrollInternalOperation(op,false);
    const v=brollInternalEditorState();if(v.principal.human_write_enabled!==true||!['editor','reviewer','owner'].includes(audioRole(v)))
      throw Error('Phiên này chưa được phép nhận tư liệu phân giải.');};guard();
  const r=value.receipt,original=value.context,base=brollInternalRoute(),path=base+'/requests/'+r.request_key+'/jobs/'+r.resolution_job_id;
  if(r.workspace_id!==state.workspaceId||r.project_id!==state.projectId||r.actor_ref!==state.principal.subject||r.media_plan_id!==state.selectedBrollPlanId
    ||r.media_plan_item_id!==brollInternalItemId||r.context_sha256!==original.context_sha256||value.request.context_sha256!==original.context_sha256
    ||value.request.request_key!==r.request_key||value.request.asset_id!==r.asset_id||value.request.acknowledged!==true
    ||value.observation.can_adopt!==true||value.observation.source_current!==true||value.observation.state!=='resolved'
    ||sqlAudioStable(value.observation.receipt)!==sqlAudioStable(r)||sqlAudioStable(value.observation.job)!==sqlAudioStable(value.job)
    ||sqlAudioStable(value.observation.output)!==sqlAudioStable(value.output))throw Error('Kết quả chưa đúng nguồn, cảnh, tư liệu hoặc job ban đầu.');
  const proof=await api(path,{cache:'no-store'});guard();if(sqlAudioStable(proof)!==sqlAudioStable(value.observation))throw Error('Job hiện tại chưa khớp đúng kết quả đã giữ.');
  const fresh=await api(base,{cache:'no-store'});guard();validateBrollInternalContext(fresh,brollInternalEditorState());
  const hash=await audioByteHash(new TextEncoder().encode(fresh.context_json));guard();const {context_json,context_sha256,...projected}=fresh;
  if(hash!==context_sha256||sqlAudioStable(JSON.parse(context_json))!==sqlAudioStable(projected))throw Error('JSON ngữ cảnh nội bộ chưa khớp đúng hash đã lưu.');
  const old=structuredClone(original),normalized=structuredClone(fresh),fields=['status','updated_at','selected_media_asset_id','needs_attention'];
  for(const k of fields)normalized.item[k]=old.item[k];delete old.context_json;delete old.context_sha256;delete normalized.context_json;delete normalized.context_sha256;
  if(sqlAudioStable(old)!==sqlAudioStable(normalized)||fresh.item.status!=='resolved'||fresh.item.selected_media_asset_id!==value.output.media_asset_id
    ||fresh.item.selected_media_asset_id!==value.job.output_media_asset_id||typeof fresh.item.needs_attention!=='boolean'||typeof fresh.item.updated_at!=='string')
    throw Error('Đề xuất, nguồn hoặc cảnh hiện tại chưa chứng minh đúng tư liệu đã phân giải.');
  const last=await api(path,{cache:'no-store'});guard();if(sqlAudioStable(last)!==sqlAudioStable(proof))throw Error('Job đã đổi sau khi đọc cảnh hiện tại.');
  const next=structuredClone(state.mediaPlans),plan=next.find(p=>p.media_plan_id===r.media_plan_id),item=plan?.items.find(i=>i.media_plan_item_id===r.media_plan_item_id);
  if(!item)throw Error('Cảnh đang giữ không còn trong đề xuất hiện tại.');for(const k of fields)item[k]=fresh.item[k];
  guard();state.mediaPlans=next;brollInternalInstalled={op,plans:sqlAudioStable(next)};renderBrowser();return true;
}
brollInternalController=initializeSqlBrollInternalResolution({api:brollInternalApi,getState:brollInternalEditorState,getSessionToken:sessionToken,storage:brollInternalStorage,
  onRead:(value,requestGuard)=>{const op=brollInternalOperation;assertBrollInternalOperation(op);if(typeof requestGuard!=='function'||requestGuard()!==true)
      throw Error('Thiếu ràng buộc bản đọc nội bộ.');assertBrollInternalOperation(op);validateBrollInternalContext(value,brollInternalEditorState());},
  onResolved:refreshBrollInternal,onStatus:text=>{brollInternalStatus=text;},onBusyChanged:()=>{if(brollInternalController)syncBrollInternalForm();}});
async function runBrollInternalAction(kind){if(brollInternalBusy)return;
  try{syncBrollInternalForm();if(kind==='read'&&brollInternalDirty()&&!brollInternalStored()&&!brollInternalController.isPending())throw Error('Bỏ lựa chọn chưa gửi trước khi đọc lại.');
    if(['admit','retry'].includes(kind)&&$('#broll-internal-acknowledge').checked!==true)throw Error('Xác nhận rõ đúng tư liệu hoặc yêu cầu đang giữ.');
    const asset=$('#broll-internal-asset').value,op=Object.freeze({kind,write:['admit','retry'].includes(kind),source:brollInternalSourceContext(),
      draft:brollInternalDraft(),plans:sqlAudioStable(state.mediaPlans)});brollInternalOperation=op;brollInternalInstalled=null;assertBrollInternalOperation(op);brollInternalBusy=true;syncBrollPlanPeers();
    if(kind==='read'){const data=await brollInternalController.reload();assertBrollInternalOperation(op);readBrollInternalForm(data);}
    else{const result=await(kind==='admit'?brollInternalController.admit(asset,true):kind==='retry'?brollInternalController.retry(true):brollInternalController.observe());
      if(result?.can_adopt&&!brollInternalController.isPending())clearBrollInternalForm();}
  }catch(error){brollInternalStatus=error.message;toast(error.message,true);}
  finally{brollInternalBusy=false;brollInternalOperation=null;brollInternalInstalled=null;syncBrollPlanPeers();}}
for(const [id,kind]of [['read','read'],['admit','admit'],['observe','observe'],['retry','retry']])$('#broll-internal-'+id).addEventListener('click',()=>runBrollInternalAction(kind));
$('#broll-internal-form').addEventListener('submit',e=>e.preventDefault());$('#broll-internal-form').addEventListener('change',syncBrollPlanPeers);
for(const id of ['plan','item'])$('#broll-internal-'+id).addEventListener('change',event=>{
  const old=id==='plan'?state.selectedBrollPlanId:brollInternalItemId;
  try{const v=brollInternalEditorState();if(brollInternalHeld()||v.busy||v.dirty)throw Error('Lưu/bỏ lựa chọn hoặc đối chiếu yêu cầu đang giữ trước khi đổi cảnh.');
    const next=event.target.value,plan=state.mediaPlans.find(p=>p.media_plan_id===(id==='plan'?next:state.selectedBrollPlanId));
    if(!plan||!compatibleBrollPlans(state.mediaPlans,activeAnalysis()).includes(plan)||id==='item'&&!plan.items.some(i=>i.media_plan_item_id===next))throw Error('Cảnh hoặc đề xuất không thuộc nguồn hiện tại.');
    clearBrollInternalForm();if(id==='plan'){state.selectedBrollPlanId=next;brollInternalItemId='';clearBrollTimelineForm();}else brollInternalItemId=next;
    brollInternalSelectors();renderBrowser();syncBrollPlanPeers();
  }catch(error){event.target.value=old;toast(error.message,true);}});
$('#broll-internal-discard').addEventListener('click',()=>{if(brollInternalBusy||brollInternalStored()||brollInternalController.isPending())return toast('Giữ nguyên yêu cầu chưa rõ kết quả.',true);
  const data=brollInternalFormRead?.source===brollInternalSourceContext()&&brollInternalFormRead?.plans===sqlAudioStable(state.mediaPlans)?structuredClone(brollInternalFormRead.data):null;
  clearBrollInternalForm();if(data)readBrollInternalForm(data);syncBrollPlanPeers();});
$('#broll-internal-open-held').addEventListener('click',()=>{try{const v=brollInternalEditorState();if(brollInternalBusy||brollInternalDirty()||v.busy||v.dirty)throw Error('Chờ hoặc bỏ lựa chọn chưa gửi trước khi mở bản đang giữ.');
    const before=brollInternalSourceContext(),plans=sqlAudioStable(state.mediaPlans),draft=brollInternalDraft(),key=brollInternalBucket(),raw=brollInternalStore.getItem(key);
    const unchanged=()=>{const s=brollInternalEditorState();if(before!==brollInternalSourceContext()||plans!==sqlAudioStable(state.mediaPlans)||draft!==brollInternalDraft()
        ||s.busy||s.dirty||!Number.isFinite(Date.parse(s.principal?.expires_at))||Date.parse(s.principal.expires_at)<=Date.now())throw Error('Nguồn hoặc phiên đã đổi khi mở bản đang giữ.');};
    unchanged();if(typeof raw!=='string'||new TextEncoder().encode(raw).length>5*1024*1024)throw Error('Không có đúng bản ghi có thể đọc.');
    const p=JSON.parse(raw),c=p.context,plan=compatibleBrollPlans(state.mediaPlans,activeAnalysis()).find(p=>p.media_plan_id===c?.plan?.media_plan_id);
    if(p.schema_version!=='sql-broll-internal-pending.v1'||c.workspace_id!==state.workspaceId||c.project_id!==state.projectId||c.actor_ref!==state.principal.subject
      ||!plan||!plan.items.some(i=>i.media_plan_item_id===c.item?.media_plan_item_id)||c.timeline_id!==state.timeline.timeline_id
      ||c.timeline_version_id!==state.timeline.current_version_id||c.timeline_version!==state.timeline.current_version)throw Error('Bản ghi không thuộc nguồn và cảnh của dự án.');
    const last=brollInternalStore.getItem(key);unchanged();if(last!==raw)throw Error('Bản ghi đã đổi; giữ nguyên.');
    clearBrollInternalForm();state.selectedBrollPlanId=plan.media_plan_id;brollInternalItemId=c.item.media_plan_item_id;state.query='';state.panelTab='broll';
    if($('#browser-search'))$('#browser-search').value='';brollInternalSelectors();renderBrowser();syncBrollPlanPeers();$('#broll-internal-read').focus();
  }catch(error){toast(error.message,true);}});
syncBrollInternalForm();

ensureAuthenticatedSession()
  .then(principal => { state.principal = principal; return loadProjectList(); })
  .catch((error) => { renderNoProject("Không tải được Studio.", error.message); toast(error.message, true); })
  .finally(() => multiInput.setBusy(false));
