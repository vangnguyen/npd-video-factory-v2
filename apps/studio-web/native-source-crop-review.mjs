// Explicit local choice of original sampled Vision. No analysis or auto-apply.
import {reviewedVisionRequest} from './native-media-planner.mjs';
const same=(a,b)=>JSON.stringify(a,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v)===JSON.stringify(b,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v);
export function initializeSourceCropReview({root,getState,getReviewedVision=()=>null,onMessage=()=>{},dom=globalThis.document}){
  let selected=null,binding=null;
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,
    s.project?.document?.canonical_timeline?.sha256,s.canEdit,s.dirty,s.busy,s.active,s.project?.archived??false]);};
  const source=()=>getState().project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
  const blocked=()=>{const s=getState();return !source()||s.canEdit!==true||s.dirty||s.busy||s.active||s.project?.archived;};
  function element(tag,text,attributes={}){const n=dom.createElement(tag);n.textContent=text;for(const[k,v]of Object.entries(attributes))n.setAttribute(k,String(v));root.append(n);return n;}
  element('h3','Crop từ Vision đã xem');
  element('p','Chọn kết quả Vision của video nguồn đang xem trong Assets. Khung mẫu chỉ gợi ý vị trí chủ thể; chưa có tracking liên tục hoặc độ tin cậy đã hiệu chuẩn. Mô phỏng giữ crop giữa. Lưu tạo phiên bản timeline mới; xem preview đầy đủ và duyệt lại.',{class:'hint'});
  const pick=element('button','Chọn Vision của nguồn cho crop',{type:'button','data-crop-review-pick':''});
  const clearButton=element('button','Bỏ Vision khỏi crop',{type:'button','data-crop-review-clear':''});
  const status=element('p','Chưa chọn Vision.',{class:'hint',role:'status'});
  const savedStatus=element('p','Chưa lưu crop từ Vision đã xem.',{class:'hint'});
  const history=element('details','');const summary=dom.createElement('summary');summary.textContent='Bằng chứng crop đã lưu';history.append(summary);
  const evidence=dom.createElement('pre');evidence.setAttribute('class','native-json');history.append(evidence);
  const label=element('label','Tôi đã xem kết quả và chọn dùng vị trí chủ thể khi lưu crop.',{class:'check'});
  const ack=dom.createElement('input');ack.type='checkbox';ack.setAttribute('data-crop-review-ack','');label.append(ack);
  const mockLabel=element('label','Tôi hiểu mô phỏng giữ crop giữa, chưa đo vị trí hoặc tracking thật.',{class:'check'});
  const mockAck=dom.createElement('input');mockAck.type='checkbox';mockAck.setAttribute('data-crop-review-mock','');mockLabel.append(mockAck);
  const ratioLabel=element('label','Định dạng crop đã xem');const ratio=dom.createElement('select');ratio.setAttribute('data-crop-review-ratio','');
  for(const value of ['9:16','16:9','1:1','4:5']){const option=dom.createElement('option');option.textContent=option.value=value;ratio.append(option);}ratio.value='9:16';ratioLabel.append(ratio);
  const save=element('button','Lưu crop từ Vision đã xem',{type:'button','data-reframe-reviewed-apply':''});
  function clear(){selected=null;binding=null;ack.checked=mockAck.checked=false;controls();}
  function controls(){
    root.hidden=!source();pick.disabled=blocked();clearButton.disabled=!selected||blocked();ack.disabled=!selected||blocked();
    mockLabel.hidden=!selected?.result?.mock;mockAck.disabled=mockLabel.hidden||blocked();ratio.disabled=blocked();
    save.disabled=blocked()||!selected||ack.checked!==true||mockAck.checked!==(selected?.result?.mock??false);
    status.textContent=selected?`${selected.result.mock?'Mô phỏng · crop giữa cần kiểm tra':'Vị trí theo khung mẫu · chưa phải tracking liên tục'} · ${selected.snapshot.source.asset.filename} · phản hồi ${selected.response_id} · chi phí ${selected.cost_operation_id}. Hóa đơn thực tế chưa có. Preview, quyền và duyệt video cần kiểm tra riêng.`:'Chưa chọn Vision.';
    const p=getState().project,proof=p?.document?.canonical_timeline?.snapshot?.metadata?.reviewed_reframe_selection;
    const saved=(p?.document?.source_reframe_reviews??[]).find(v=>v.review.review_id===proof?.review_id);
    if(saved){const v=saved.review;
      savedStatus.textContent=`Crop đã lưu: ${v.plan.strategy==='subject_samples'?'vị trí theo khung mẫu':'crop giữa'} · ${v.aspect_ratio} · cần kiểm tra · ${proof.mock_original_result?'mô phỏng':'dự đoán chưa hiệu chuẩn'} · phản hồi ${proof.original_response_id} · chi phí ${proof.original_cost_operation_id}. Độ tin cậy tracking: chưa có.`;
    }else savedStatus.textContent='Chưa lưu crop từ Vision đã xem. Crop thủ công và lịch sử timeline vẫn dùng riêng.';
    evidence.textContent=JSON.stringify((p?.document?.source_reframe_reviews??[]).map(v=>({review_id:v.review.review_id,sha256:v.sha256,
      aspect_ratio:v.review.aspect_ratio,plan:v.review.plan,sample_evidence:v.review.sample_evidence,confidence_basis:v.review.confidence_basis,
      original_vision_id:v.review.reviewed_vision.items[0].request.vision_id,original_response_id:v.review.reviewed_vision.items[0].response_id,
      original_response_sha256:v.review.reviewed_vision.items[0].response_sha256,original_cost_operation_id:v.review.reviewed_vision.items[0].cost_operation_id,
      mock:v.review.reviewed_vision.items[0].mock,tracking_confidence:null,continuous_tracking_performed:false,decoded_pts_verified:false})),null,2);
  }
  function sync(){if(selected&&(binding!==context()||!same(selected,getReviewedVision())))clear();else controls();}
  function choose(){sync();if(blocked()){onMessage('Lưu chỉnh sửa và mở video nguồn có quyền chỉnh sửa trước khi chọn crop.',true);return;}
    try{const row=getReviewedVision(),s=getState();reviewedVisionRequest(row,s,{acknowledgedReviewed:true,acknowledgedMock:row?.result?.mock??false});
      const id=s.project.document.canonical_timeline.snapshot.metadata.source_analysis_id;
      const analysis=s.project.document.auto_edit_analyses.find(v=>v.analysis.analysis_id===id);
      if(!analysis||row.snapshot.source.asset.id!==analysis.native_asset_id)throw new Error('main source required');
      selected=structuredClone(row);binding=context();ack.checked=mockAck.checked=false;ratio.value=s.project.document.canonical_timeline.snapshot.aspect_ratio;controls();
    }catch{clear();onMessage('Chọn kết quả Vision thành công của chính video nguồn trong Assets trước.',true);}
  }
  function request(){sync();if(blocked()||!selected||!['9:16','16:9','1:1','4:5'].includes(ratio.value))throw new Error('Chọn lại Vision của nguồn và xác nhận trước khi lưu crop.');
    const s=getState(),ref=reviewedVisionRequest(selected,s,{acknowledgedReviewed:ack.checked,acknowledgedMock:mockAck.checked});
    return {revision:s.project.revision,action:'reframe',payload:{expected_version:s.project.document.canonical_timeline.version,
      aspect_ratio:ratio.value,mode:'reviewed_vision',points:[],reviewed_vision:ref}};
  }
  pick.addEventListener('click',choose);clearButton.addEventListener('click',clear);
  ack.addEventListener('change',sync);mockAck.addEventListener('change',sync);controls();
  return {choose,clear,sync,controls,request};
}
