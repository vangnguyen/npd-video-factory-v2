// Original saved pixels and reviewed suggestions. Choosing an image is explicit.
import {reviewedVisionRequest,validateReviewedVisionContext} from './native-media-planner.mjs';
const HASH=/^[a-f0-9]{64}$/,REC=/^nstr_[a-f0-9]{32}$/,FRAME=/^mfr_[a-f0-9]{24}$/;
const same=(a,b)=>JSON.stringify(a,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v)===JSON.stringify(b,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v);
const source=s=>s.project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
const analysis=s=>s.project?.document?.auto_edit_analyses?.find(v=>v.analysis.analysis_id===s.project.document.canonical_timeline?.snapshot.metadata.source_analysis_id);
export function validateThumbnailReview(record,state){
  const v=record?.recommendation;
  if(!HASH.test(record?.sha256??'')||v?.schema_version!=='native-reviewed-source-thumbnail-v1'||!REC.test(v.recommendation_id??'')
    ||v.project_id!==state.project?.id||v.workspace_id!==state.workspace_id||!Number.isInteger(v.source_revision)||v.source_revision<1
    ||!HASH.test(v.source_document_sha256??'')||!HASH.test(v.fingerprint??'')||!Number.isFinite(Date.parse(v.created_at))
    ||!Array.isArray(v.candidates)||v.candidates.length>3||v.external_dispatches!==0||v.paid_operations!==0
    ||['canonical_timeline_mutated','full_media_qc_replaced','publishing_authorized','owner_uat_accepted'].some(k=>v[k]!==false))throw new Error('Gợi ý thumbnail không đúng nguồn gốc của dự án.');
  const context=validateReviewedVisionContext(v.reviewed_vision,state),item=context.items[0];
  if(context.items.length!==1||item.asset_id!==v.source?.asset?.id||item.source_sha256!==v.source?.asset?.sha256)throw new Error('Thumbnail cần bằng chứng của video nguồn chính.');
  const ids=new Set();for(const [i,c]of v.candidates.entries()){
    const frame=item.source_frame_evidence.find(f=>f.frame_id===c.frame_id),predicted=item.frames.find(f=>f.frame_id===c.original_vision_frame_id);
    if(!FRAME.test(c.frame_id??'')||ids.has(c.frame_id)||c.rank!==i+1||!frame||!same(c.source_frame,frame)
      ||!predicted||predicted.evidence_frame_reference!==frame.reference||predicted.timestamp_seconds!==frame.timestamp_seconds
      ||c.confidence!==null||c.needs_attention!==true||c.publishing_authorized!==false||c.full_media_qc_replaced!==false
      ||c.pixel_quality_heuristic!==frame.pixel_facts.heuristic_quality_score
      ||item.mock&&['provider_thumbnail_suggestion','predicted_sample_quality','uncalibrated_prediction_confidence','provider_caption','predicted_watermark_or_logo'].some(k=>c[k]!==null)
      ||!item.mock&&(c.provider_thumbnail_suggestion!==item.thumbnail_candidate_ids.includes(predicted.frame_id)
        ||c.predicted_sample_quality!==predicted.quality.quality_score||c.uncalibrated_prediction_confidence!==predicted.confidence
        ||c.provider_caption!==predicted.caption||c.predicted_watermark_or_logo!==predicted.quality.watermark_or_logo_detected))throw new Error('Khung thumbnail đã thay đổi hoặc mô phỏng được nâng thành thật.');
    ids.add(c.frame_id);
  }
  return record;
}
export function thumbnailInputCurrent(record,state){
  validateThumbnailReview(record,state);const a=analysis(state),v=record.recommendation;
  const transcript=[...(state.project.document.auto_edit_transcripts??[]).filter(t=>t.analysis_id===a?.analysis.analysis_id),a?.analysis.transcript].filter(Boolean).sort((a,b)=>a.version-b.version).at(-1)??null;
  return Boolean(a&&a.analysis.analysis_id===v.source.analysis.analysis_id&&same(state.project.document.assets.find(x=>x.id===a.native_asset_id),v.source.asset)
    &&same(transcript,v.source.analysis.transcript)&&same(a.analysis.scenes,v.source.analysis.scenes));
}
export function thumbnailSelectionRequest(record,state,{frameId,acknowledged=false,acknowledgedMock=false}={}){
  if(!source(state)||state.canEdit!==true||state.dirty||state.busy||state.active||state.project.archived||!thumbnailInputCurrent(record,state)
    ||acknowledged!==true||acknowledgedMock!==record.recommendation.reviewed_vision.items[0].mock
    ||!record.recommendation.candidates.some(c=>c.frame_id===frameId))throw new Error('Xem đúng khung nguồn, chọn ảnh và xác nhận riêng mô phỏng trước khi lưu.');
  return {revision:state.project.revision,recommendation_id:record.recommendation.recommendation_id,expected_sha256:record.sha256,
    frame_id:frameId,acknowledged_thumbnail:true,acknowledged_protocol_mock:acknowledgedMock};
}
export function initializeSourceThumbnailReview({root,api,getState,getReviewedVision=()=>null,onProject,onMessage=()=>{},onWorking=()=>{},dom=globalThis.document}){
  let selected=null,binding=null,working=false,historyKey=null,choiceBinding=null,invalid=null;
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.document?.canonical_timeline?.sha256,s.canEdit,s.dirty,s.busy,s.active,s.project?.archived??false]);};
  const stable=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.document?.canonical_timeline?.sha256,s.canEdit,s.dirty,s.project?.archived??false]);};
  const blocked=()=>{const s=getState();return Boolean(invalid)||working||!source(s)||s.canEdit!==true||s.dirty||s.busy||s.active||s.project.archived;};
  function element(tag,text='',attributes={},parent=root){const n=dom.createElement(tag);n.textContent=text;for(const [k,v]of Object.entries(attributes))n.setAttribute(k,String(v));parent.append(n);return n;}
  element('h3','Thumbnail từ khung nguồn');
  element('p','Chọn Vision của video nguồn đã xem trong Assets để lưu tối đa ba gợi ý. Xem ảnh rồi chọn riêng. Mô phỏng chỉ dùng điểm ảnh nguồn đã đo; chưa có nhận diện thật. Ảnh này dùng xem dự án, còn đăng thumbnail cần tích hợp và duyệt riêng.',{class:'hint'});
  const pick=element('button','Chọn Vision của nguồn cho thumbnail',{type:'button','data-thumbnail-review-pick':''});
  const clear=element('button','Bỏ Vision khỏi thumbnail',{type:'button','data-thumbnail-review-clear':''});
  const status=element('p','Chưa chọn Vision.',{class:'hint',role:'status'});
  const ackLabel=element('label','Tôi đã xem kết quả Vision của nguồn.',{class:'check'}),ack=element('input','',{type:'checkbox','data-thumbnail-review-ack':''},ackLabel);
  const mockLabel=element('label','Tôi hiểu mô phỏng không thêm nhận diện hay chất lượng Vision thật.',{class:'check'}),mockAck=element('input','',{type:'checkbox','data-thumbnail-review-mock':''},mockLabel);
  const save=element('button','Lưu gợi ý thumbnail',{type:'button','data-thumbnail-review-save':''});
  const history=element('details'),summary=element('summary','Gợi ý thumbnail đã lưu',{},history),body=element('section','',{},history);
  const choiceLabel=element('label','Gợi ý thumbnail hiện tại'),choice=element('select','',{'data-thumbnail-choice':''},choiceLabel);
  const frameLabel=element('label','Khung thumbnail'),frame=element('select','',{'data-thumbnail-frame':''},frameLabel);
  const images=element('section','',{'data-thumbnail-images':''});
  const selectionLabel=element('label','Tôi đã xem ảnh nguồn và chọn khung này làm ảnh xem dự án.',{class:'check'}),selectionAck=element('input','',{type:'checkbox','data-thumbnail-selection-ack':''},selectionLabel);
  const selectionMockLabel=element('label','Tôi hiểu gợi ý có Vision mô phỏng; ảnh nguồn thật không chứng minh nhận diện thật.',{class:'check'}),selectionMock=element('input','',{type:'checkbox','data-thumbnail-selection-mock':''},selectionMockLabel);
  const apply=element('button','Lưu khung thumbnail đã chọn',{type:'button','data-thumbnail-selection-apply':''});
  const savedStatus=element('p','Chưa chọn thumbnail từ gợi ý.',{class:'hint'});
  const records=()=>getState().project?.document?.source_thumbnail_reviews??[];
  const chosen=()=>records().find(r=>r.recommendation.recommendation_id===choice.value);
  function clearVision(){selected=null;binding=null;ack.checked=mockAck.checked=false;}
  function resetReview(){selectionAck.checked=selectionMock.checked=false;choiceBinding=context();}
  function renderChoice(){
    frame.replaceChildren();images.replaceChildren();const s=getState(),record=chosen();
    if(record)for(const c of record.recommendation.candidates){
      const option=element('option',`Khung ${c.rank} · ${c.source_frame.timestamp_seconds.toFixed(2)}s`,{},frame);option.value=c.frame_id;
      const figure=element('figure','',{},images);element('img','',{src:`/api/projects/${s.project.id}/media-frames/${c.frame_id}/image`,
        alt:`Ảnh nguồn khung ${c.rank} tại ${c.source_frame.timestamp_seconds.toFixed(2)}s`,loading:'lazy',width:c.source_frame.width,height:c.source_frame.height},figure);
      element('figcaption',`Khung ${c.rank} · ${c.source_frame.timestamp_seconds.toFixed(2)}s · điểm ảnh ${c.pixel_quality_heuristic.toFixed(3)} · ${c.provider_caption??'nhận diện chưa có'} · độ tin cậy chưa hiệu chuẩn`,{},figure);
    }
    frame.value=record?.recommendation.candidates[0]?.frame_id??'';resetReview();
  }
  function renderHistory(){
    const s=getState(),key=JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision]);if(historyKey===key)return;
    body.replaceChildren();choice.replaceChildren();element('option','Chọn gợi ý đã xem',{value:''},choice);choice.value='';
    for(const record of records()){
      validateThumbnailReview(record,s);const v=record.recommendation,item=v.reviewed_vision.items[0],current=thumbnailInputCurrent(record,s);
      element('p',`${v.created_at} · ${item.mock?'mô phỏng':'dự đoán chưa hiệu chuẩn'} · ${current?'nguồn hiện tại':'nguồn đã thay đổi'} · ${v.candidates.length} khung · phản hồi ${item.response_id} · chi phí ${item.cost_operation_id}. Hóa đơn thực tế chưa có.`,{},body);
      if(current){const option=element('option',`${v.created_at} · ${item.mock?'mô phỏng':'Vision đã xem'}`,{},choice);option.value=v.recommendation_id;}
    }
    summary.textContent=`Gợi ý thumbnail đã lưu · ${records().length}`;renderChoice();historyKey=key;
  }
  function sync(){
    if(selected&&(binding!==context()||!same(selected,getReviewedVision())))clearVision();
    if(choiceBinding!==context())resetReview();root.hidden=!source(getState());
    try{renderHistory();invalid=null;}catch(error){invalid=error;body.replaceChildren();choice.replaceChildren();frame.replaceChildren();images.replaceChildren();clearVision();resetReview();}
    const disabled=blocked(),record=chosen();for(const n of[pick,choice,frame])n.disabled=disabled;
    clear.disabled=disabled||!selected;ack.disabled=disabled||!selected;mockLabel.hidden=!selected?.result?.mock;mockAck.disabled=disabled||mockLabel.hidden;
    save.disabled=disabled||!selected;selectionMockLabel.hidden=!record?.recommendation.reviewed_vision.items[0].mock;
    selectionAck.disabled=disabled||!record;selectionMock.disabled=disabled||selectionMockLabel.hidden;apply.disabled=disabled||!record||!frame.value;
    status.textContent=invalid?invalid.message:selected?`${selected.snapshot.source.asset.filename} · ${selected.result.mock?'mô phỏng, chỉ dùng điểm ảnh đã đo':'gợi ý chưa hiệu chuẩn'}. Không gửi lại ảnh hoặc đổi timeline.`:'Chưa chọn Vision.';
    const saved=getState().project?.document?.source_thumbnail_selection;
    savedStatus.textContent=saved?`Ảnh đã chọn: ${saved.frame_id} · ${saved.mock_original_result?'gợi ý có mô phỏng':'dự đoán chưa hiệu chuẩn'} · phản hồi ${saved.original_response_id}. Chưa cấp quyền đăng thumbnail hoặc thay QC.`:'Chưa chọn thumbnail từ gợi ý.';
  }
  function choose(){sync();if(blocked())return;try{
    const s=getState(),row=getReviewedVision();reviewedVisionRequest(row,s,{acknowledgedReviewed:true,acknowledgedMock:row?.result?.mock??false});
    if(row.snapshot.source.asset.id!==analysis(s)?.native_asset_id)throw new Error('Chọn Vision của chính video nguồn trong Assets.');
    selected=structuredClone(row);binding=context();ack.checked=mockAck.checked=false;sync();
  }catch(error){clearVision();sync();onMessage(error.message,true);}}
  async function perform(action){
    sync();if(blocked())return;const s=getState(),base=stable(),project=s.project;let request;
    try{if(action==='save')request={revision:project.revision,analysis_id:analysis(s).analysis.analysis_id,
      reviewed_vision:reviewedVisionRequest(selected,s,{acknowledgedReviewed:ack.checked,acknowledgedMock:mockAck.checked})};
      else if(action==='select')request=thumbnailSelectionRequest(chosen(),s,{frameId:frame.value,acknowledged:selectionAck.checked,acknowledgedMock:selectionMock.checked});
      else throw new Error('Chọn thao tác thumbnail hợp lệ.');
    }catch(error){onMessage(error.message,true);return;}
    working=true;onWorking();sync();
    try{
      const value=await api(`/api/projects/${project.id}/auto-edit/thumbnail-reviews${action==='select'?'/select':''}`,request);
      if(base!==stable())return;
      if(value?.schema_version!=='native-reviewed-source-thumbnail-page-v1'||value.project_id!==project.id||![project.revision,project.revision+1].includes(value.revision))throw new Error('Dự án đã thay đổi. Đọc lại thumbnail đã lưu.');
      const next=await api(`/api/projects/${project.id}/auto-edit/timeline`);if(base!==stable())return;
      if(next?.id!==project.id||next.revision!==value.revision||next.document.canonical_timeline.sha256!==project.document.canonical_timeline.sha256
        ||!same(next.document.source_thumbnail_reviews??[],value.items)||!same(next.document.source_thumbnail_selection??null,value.selection??null))throw new Error('Nguồn hoặc thumbnail đã thay đổi. Mở lại dự án để xem.');
      clearVision();resetReview();onProject(next,true);onMessage(action==='save'?'Đã lưu gợi ý thumbnail. Xem ảnh rồi chọn riêng; timeline được giữ nguyên.':'Đã chọn ảnh xem dự án. Timeline giữ nguyên; phê duyệt cũ cần cập nhật.');
    }catch(error){onMessage(error.message,true);}finally{working=false;onWorking();sync();}
  }
  pick.addEventListener('click',choose);clear.addEventListener('click',()=>{clearVision();sync();});choice.addEventListener('change',()=>{renderChoice();sync();});
  frame.addEventListener('change',()=>{resetReview();sync();});save.addEventListener('click',()=>{void perform('save');});apply.addEventListener('click',()=>{void perform('select');});
  sync();return {choose,sync,perform,isWorking:()=>working};
}
