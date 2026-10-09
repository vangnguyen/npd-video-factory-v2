// Existing main-source evidence, explicitly reviewed recommendations and edits.
import {reviewedVisionRequest,validateReviewedVisionContext} from './native-media-planner.mjs';
const HASH=/^[a-f0-9]{64}$/,ANALYSIS=/^ana_[a-f0-9]{24}$/,REC=/^nscr_[a-f0-9]{32}$/,HIGHLIGHT=/^hig_[a-f0-9]{24}$/;
const same=(a,b)=>JSON.stringify(a,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v)===JSON.stringify(b,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v);
const score=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1;
const time=value=>Number(value).toFixed(2);
const source=state=>state.project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
function analysis(state){const document=state.project?.document;return document?.auto_edit_analyses?.find(v=>v.analysis.analysis_id===document.canonical_timeline?.snapshot.metadata.source_analysis_id);}
function transcript(state,record){return [...(state.project.document.auto_edit_transcripts??[]).filter(v=>v.analysis_id===record.analysis.analysis_id),record.analysis.transcript].filter(Boolean).sort((a,b)=>a.version-b.version).at(-1)??null;}
export function validateSceneRecommendation(record,state){
  const value=record?.recommendation,result=value?.result;
  if(!HASH.test(record?.sha256??'')||value?.schema_version!=='native-reviewed-scene-recommendations-v1'||!REC.test(value.recommendation_id??'')
    ||value.project_id!==state.project?.id||value.workspace_id!==state.workspace_id||!Number.isInteger(value.source_revision)||value.source_revision<1
    ||!HASH.test(value.source_document_sha256??'')||!HASH.test(value.fingerprint??'')||!Number.isFinite(Date.parse(value.created_at))
    ||!ANALYSIS.test(value.source?.analysis?.analysis_id??'')||!Array.isArray(result?.scenes)||result.scenes.length>200
    ||!Array.isArray(result.scene_ranking)||result.scene_ranking.length!==result.scenes.length||!Array.isArray(result.highlights)||result.highlights.length>5
    ||!same(result.highlights,result.scene_ranking.slice(0,5))||result.recommendation_only!==true||result.external_dispatches!==0||result.paid_operations!==0
    ||['prediction_confidence_calibrated','continuous_tracking_performed','decoded_source_pts_verified','canonical_timeline_mutated','silence_decisions_mutated','publishing_authorized','owner_uat_accepted','real_provider_tested','full_media_qc_replaced'].some(k=>result[k]!==false))throw new Error('Gợi ý cảnh không có nguồn gốc đúng dự án.');
  const context=validateReviewedVisionContext(value.reviewed_vision,state),original=context.items[0];
  if(context.items.length!==1||original.asset_id!==value.source.asset.id||original.source_sha256!==value.source.asset.sha256
    ||result.semantic_vision_used!==!original.mock)throw new Error('Dùng kết quả của video nguồn chính; mô phỏng không thêm nhận diện thật.');
  const ids=new Set();for(const [i,scene]of result.scenes.entries()){
    if(scene.scene_id!==value.source.analysis.scenes[i]?.scene_id||!Number.isFinite(scene.start_seconds)||!Number.isFinite(scene.end_seconds)
      ||scene.start_seconds<0||scene.end_seconds<=scene.start_seconds||scene.end_seconds>value.source.analysis.source_media.duration_seconds
      ||scene.evidence?.prediction_confidence_calibrated!==false||scene.evidence.reviewed_vision_recommendation_only!==true
      ||original.mock&&scene.evidence.vision_used!==false)throw new Error('Cảnh đã thay đổi hoặc nhận diện mô phỏng được nâng thành thật.');
    ids.add(scene.scene_id);
  }
  const highlights=new Set();for(const item of result.scene_ranking){
    if(!HIGHLIGHT.test(item.highlight_id??'')||highlights.has(item.highlight_id)||!ids.has(item.scene_id)||!score(item.highlight_score)
      ||!Number.isFinite(item.recommended_start)||!Number.isFinite(item.recommended_end)||item.recommended_start<0||item.recommended_end<=item.recommended_start
      ||item.recommended_end>value.source.analysis.source_media.duration_seconds||item.evidence?.original_vision_id!==original.request.vision_id
      ||item.evidence.original_response_sha256!==original.response_sha256||item.evidence.mock_original_result!==original.mock
      ||item.evidence.recommendation_only!==true||item.evidence.prediction_confidence_calibrated!==false||item.evidence.automatic_application!==false)throw new Error('Điểm nổi bật không khớp gợi ý đã lưu.');highlights.add(item.highlight_id);
  }
  return record;
}
export function sceneInputCurrent(record,state){
  validateSceneRecommendation(record,state);const selected=analysis(state),value=record.recommendation;
  const asset=state.project.document.assets?.find(v=>v.id===selected?.native_asset_id);
  return Boolean(selected&&selected.analysis.analysis_id===value.source.analysis.analysis_id&&same(asset,value.source.asset)
    &&same(transcript(state,selected),value.source.analysis.transcript)&&same(selected.analysis.scenes,value.source.analysis.scenes));
}
export function sceneSelectionRequest(record,state,{acknowledged=false,acknowledgedMock=false}={}){
  validateSceneRecommendation(record,state);
  if(!source(state)||state.canEdit!==true||state.dirty||state.busy||state.active||state.project.archived||!sceneInputCurrent(record,state)
    ||acknowledged!==true||acknowledgedMock!==record.recommendation.reviewed_vision.items[0].mock)throw new Error('Xem gợi ý của nguồn hiện tại và xác nhận riêng mô phỏng trước khi dựng.');
  return {recommendation_id:record.recommendation.recommendation_id,expected_recommendation_sha256:record.sha256,
    acknowledged_reviewed_recommendation:true,acknowledged_protocol_mock:acknowledgedMock};
}
export function sceneEditRequest(record,state,{highlightId,aspectRatio='9:16',count=3,maximumDuration=60,requestKey,shorts=false,...ack}={}){
  const reviewed=sceneSelectionRequest(record,state,ack),a=record.recommendation.source.analysis,p=state.project;
  if(!['9:16','16:9','1:1','4:5'].includes(aspectRatio))throw new Error('Chọn định dạng hỗ trợ.');
  const payload={analysis_id:a.analysis_id,transcript_id:a.transcript?.transcript_id??null,expected_version:p.document.canonical_timeline.version,
    aspect_ratio:aspectRatio,reviewed_scene:reviewed};
  if(shorts){
    if(![3,5].includes(count)||!Number.isFinite(maximumDuration)||maximumDuration<3||maximumDuration>180)throw new Error('Chọn Top 3/5 và thời lượng 3–180s.');
    const key=requestKey??globalThis.crypto.randomUUID().replaceAll('-','');if(!/^[a-f0-9]{32}$/.test(key))throw new Error('Mã yêu cầu Shorts không hợp lệ.');
    return {revision:p.revision,payload:{...payload,count,maximum_duration_seconds:maximumDuration,request_key:key}};
  }
  if(!record.recommendation.result.scene_ranking.some(v=>v.highlight_id===highlightId))throw new Error('Chọn điểm nổi bật từ gợi ý hiện tại.');
  return {revision:p.revision,action:'create',payload:{...payload,reviewed_highlight_id:highlightId}};
}
export function initializeSceneReview({root,api,getState,getReviewedVision=()=>null,onProject,onMessage=()=>{},onWorking=()=>{},onDraftsCreated=()=>{},dom=globalThis.document}){
  let selected=null,binding=null,working=false,historyKey=null,choiceBinding=null,pendingShorts=null,invalid=null,draftsIdentity=null;
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.document?.canonical_timeline?.sha256,s.canEdit,s.dirty,s.busy,s.active,s.project?.archived??false]);};
  const stable=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.document?.canonical_timeline?.sha256,s.canEdit,s.dirty,s.project?.archived??false]);};
  const blocked=()=>{const s=getState();return Boolean(invalid)||working||!source(s)||s.canEdit!==true||s.dirty||s.busy||s.active||s.project.archived;};
  function element(tag,text='',attributes={},parent=root){const node=dom.createElement(tag);node.textContent=text;for(const [k,v]of Object.entries(attributes))node.setAttribute(k,String(v));parent.append(node);return node;}
  element('h3','Cảnh & điểm nổi bật đã xem');
  element('p','Chọn kết quả Vision của video nguồn đang xem trong Assets. Lưu gợi ý giữ nguyên timeline và điểm cắt im lặng; xem gợi ý rồi chọn riêng khi dựng.',{class:'hint'});
  const pick=element('button','Chọn Vision của nguồn đang xem',{type:'button','data-scene-review-pick':''}),clear=element('button','Bỏ Vision đã chọn',{type:'button','data-scene-review-clear':''});
  const status=element('p','Chưa chọn Vision.',{class:'hint',role:'status'});
  const ackLabel=element('label','Tôi đã xem kết quả Vision.',{class:'check'}),ack=element('input','',{type:'checkbox','data-scene-review-ack':''},ackLabel);
  const mockLabel=element('label','Tôi hiểu mô phỏng không thêm nhận diện/chất lượng thật.',{class:'check'}),mockAck=element('input','',{type:'checkbox','data-scene-review-mock':''},mockLabel);
  const save=element('button','Lưu gợi ý cảnh & điểm nổi bật',{type:'button','data-scene-review-save':''});
  const history=element('details',''),summary=element('summary','Gợi ý đã lưu',{},history),historyBody=element('section','',{},history);
  const choiceLabel=element('label','Gợi ý dùng để dựng'),choice=element('select','',{'data-scene-choice':''},choiceLabel);
  const recommendationLabel=element('label','Tôi đã xem cảnh và điểm nổi bật này; tôi chọn dùng khi dựng.',{class:'check'}),recommendationAck=element('input','',{type:'checkbox','data-scene-selection-ack':''},recommendationLabel);
  const selectionMockLabel=element('label','Tôi hiểu gợi ý dùng kết quả Vision mô phỏng, chưa là nhận diện thật.',{class:'check'}),selectionMock=element('input','',{type:'checkbox','data-scene-selection-mock':''},selectionMockLabel);
  const highlightLabel=element('label','Điểm nổi bật'),highlight=element('select','',{'data-scene-highlight':''},highlightLabel);
  const ratioLabel=element('label','Định dạng'),ratio=element('select','',{'data-scene-ratio':''},ratioLabel);
  for(const value of['9:16','16:9','1:1','4:5']){const option=element('option',value,{},ratio);option.value=value;}ratio.value='9:16';
  const apply=element('button','Tạo lại bản dựng từ điểm nổi bật',{type:'button','data-scene-selection-apply':''});
  element('p','Tạo lại lưu phiên bản timeline mới; chỉnh sửa cũ còn trong lịch sử. Bản này giữ lời nói trọn vẹn và không tự áp dụng cắt im lặng. Xem preview và duyệt lại.',{class:'hint'});
  const countLabel=element('label','Số bản Shorts tối đa'),count=element('select','',{'data-scene-shorts-count':''},countLabel);
  for(const value of[3,5]){const option=element('option','Top '+value,{},count);option.value=String(value);}count.value='3';
  const durationLabel=element('label','Thời lượng Shorts tối đa (s)'),duration=element('input','',{type:'number',min:3,max:180,'data-scene-shorts-duration':''},durationLabel);duration.value='60';
  const shorts=element('button','Tạo Shorts độc lập từ gợi ý',{type:'button','data-scene-selection-shorts':''});
  const drafts=element('section','',{'data-scene-drafts':''});
  const records=()=>getState().project?.document?.source_scene_recommendations??[];
  const chosen=()=>records().find(v=>v.recommendation.recommendation_id===choice.value);
  function clearVision(){selected=null;binding=null;ack.checked=mockAck.checked=false;}
  function resetReview(){recommendationAck.checked=selectionMock.checked=false;choiceBinding=context();}
  function renderChoice(){highlight.replaceChildren();const record=chosen();if(record)for(const item of record.recommendation.result.highlights){const option=element('option',`${time(item.recommended_start)}–${time(item.recommended_end)}s · điểm ${time(item.highlight_score)}`,{},highlight);option.value=item.highlight_id;}highlight.value=record?.recommendation.result.highlights[0]?.highlight_id??'';resetReview();}
  function renderHistory(){
    const s=getState(),key=JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision]);if(historyKey===key)return;
    const nextDraftsIdentity=JSON.stringify([s.workspace_id,s.project?.id]);if(draftsIdentity!==nextDraftsIdentity){drafts.replaceChildren();pendingShorts=null;draftsIdentity=nextDraftsIdentity;}
    historyBody.replaceChildren();choice.replaceChildren();element('option','Chọn gợi ý đã xem',{value:''},choice);choice.value='';
    for(const record of records()){
      validateSceneRecommendation(record,s);const v=record.recommendation,original=v.reviewed_vision.items[0],current=sceneInputCurrent(record,s);
      const detail=element('details','',{},historyBody);element('summary',`${v.created_at} · ${original.mock?'mô phỏng':'dự đoán chưa hiệu chuẩn'} · ${current?'nguồn hiện tại':'lịch sử nguồn đã thay đổi'}`,{},detail);
      for(const scene of v.result.scenes){element('strong',`${time(scene.start_seconds)}–${time(scene.end_seconds)}s · ${scene.semantic_label}`,{},detail);element('p',scene.description,{},detail);}
      for(const item of v.result.highlights)element('p',`Điểm nổi bật ${time(item.recommended_start)}–${time(item.recommended_end)}s · điểm ${time(item.highlight_score)}`,{},detail);
      element('p',`Phản hồi ${original.response_id} · chi phí ${original.cost_operation_id} · hóa đơn thực tế chưa có. Crop, QC và duyệt video vẫn cần kiểm tra.`,{class:'hint'},detail);
      if(current){const option=element('option',`${v.created_at} · ${original.mock?'mô phỏng':'Vision đã xem'}`,{},choice);option.value=v.recommendation_id;}
    }
    summary.textContent=`Gợi ý đã lưu · ${records().length}`;renderChoice();historyKey=key;
  }
  function sync(){
    if(selected&&(binding!==context()||!same(selected,getReviewedVision())))clearVision();
    if(choiceBinding!==context())resetReview();root.hidden=!source(getState());
    try{renderHistory();invalid=null;}catch(error){invalid=error;historyBody.replaceChildren();choice.replaceChildren();highlight.replaceChildren();clearVision();resetReview();}
    const unavailable=blocked(),record=chosen();
    for(const node of[pick,save,choice,ratio,count,duration])node.disabled=unavailable;
    clear.disabled=unavailable||!selected;ack.disabled=unavailable||!selected;mockLabel.hidden=!selected?.result?.mock;mockAck.disabled=unavailable||mockLabel.hidden;
    save.disabled=unavailable||!selected;selectionMockLabel.hidden=!record?.recommendation.reviewed_vision.items[0].mock;
    for(const node of[recommendationAck,highlight,apply,shorts])node.disabled=unavailable||!record;selectionMock.disabled=unavailable||selectionMockLabel.hidden;
    status.textContent=invalid?invalid.message:selected?`${selected.snapshot.source.asset.filename} · ${selected.result.mock?'mô phỏng, không thêm điểm nhận diện/chất lượng':'dự đoán chưa hiệu chuẩn'}. Chưa gửi lại ảnh hoặc thay timeline.`:'Chưa chọn Vision.';
  }
  function choose(){sync();if(blocked())return;try{
    const row=getReviewedVision(),s=getState();reviewedVisionRequest(row,s,{acknowledgedReviewed:true,acknowledgedMock:row?.result?.mock??false});
    if(row.snapshot.source.asset.id!==analysis(s)?.native_asset_id)throw new Error('Chọn kết quả của video nguồn chính.');
    selected=structuredClone(row);binding=context();ack.checked=mockAck.checked=false;sync();
  }catch(error){clearVision();sync();onMessage(error.message,true);}}
  async function perform(action){
    sync();if(blocked())return;const s=getState(),base=stable(),project=s.project;let body,path;
    try{
      if(action==='save'){
        body={revision:project.revision,analysis_id:analysis(s).analysis.analysis_id,
          reviewed_vision:reviewedVisionRequest(selected,s,{acknowledgedReviewed:ack.checked,acknowledgedMock:mockAck.checked})};path='/auto-edit/scene-reviews';
      }else{
        const options={highlightId:highlight.value,aspectRatio:ratio.value,count:Number(count.value),maximumDuration:Number(duration.value),
          shorts:action==='shorts',acknowledged:recommendationAck.checked,acknowledgedMock:selectionMock.checked};
        const retry=JSON.stringify([project.id,project.revision,choice.value,options]);
        body=action==='shorts'&&pendingShorts?.key===retry?pendingShorts.body:sceneEditRequest(chosen(),s,options);
        if(action==='shorts')pendingShorts={key:retry,body};path=action==='shorts'?'/auto-edit/shorts':'/auto-edit/timeline';
      }
    }catch(error){onMessage(error.message,true);return;}
    working=true;onWorking();sync();
    try{
      const value=await api(`/api/projects/${project.id}${path}`,body);
      if(base!==stable())return;
      if(action==='shorts'){
        pendingShorts=null;resetReview();drafts.replaceChildren();for(const draft of value.batch.drafts)element('p',`${draft.name} · nguồn ${time(draft.source_window[0])}–${time(draft.source_window[1])}s · chưa duyệt`,{},drafts);
        await onDraftsCreated();onMessage(`Đã tạo ${value.batch.generated_count}/${value.batch.requested_count} bản Shorts độc lập chưa duyệt. Mở từ danh sách dự án để sửa, preview và duyệt.`);
      }else{
        const next=action==='save'?await api(`/api/projects/${project.id}/auto-edit/timeline`):value;if(base!==stable())return;
        if(next.id!==project.id||![project.revision,project.revision+1].includes(next.revision))throw new Error('Dự án đã thay đổi. Tải lại để xem bản đã lưu.');
        clearVision();resetReview();onProject(next,true);onMessage(action==='save'?'Đã lưu gợi ý; timeline và cắt im lặng được giữ nguyên. Xem và chọn riêng trước khi dựng.':'Đã lưu phiên bản bản dựng mới từ điểm nổi bật. Tạo preview và duyệt lại.');
      }
    }catch(error){onMessage(error.message,true);}finally{working=false;onWorking();sync();}
  }
  pick.addEventListener('click',choose);clear.addEventListener('click',()=>{clearVision();sync();});choice.addEventListener('change',()=>{renderChoice();sync();});
  for(const [node,action]of[[save,'save'],[apply,'apply'],[shorts,'shorts']])node.addEventListener('click',()=>{void perform(action);});
  sync();return {choose,sync,perform,isWorking:()=>working};
}
