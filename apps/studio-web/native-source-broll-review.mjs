// Local explicit review only. Planning does not renew consent or send images.
import {reviewedVisionRequest} from './native-media-planner.mjs';
const same=(a,b)=>JSON.stringify(a,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v)===JSON.stringify(b,(k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(key=>[key,v[key]])):v);
export function initializeSourceBrollReview({root,getState,getReviewedVision=()=>null,onMessage=()=>{},dom=globalThis.document}){
  let selected=null,binding=null;
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,
    s.project?.document?.canonical_timeline?.sha256,s.canEdit,s.dirty,s.busy,s.active,s.project?.archived??false]);};
  const source=()=>getState().project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
  const blocked=()=>{const s=getState();return !source()||s.canEdit!==true||s.dirty||s.busy||s.active||s.project?.archived;};
  function element(tag,text,attributes={}){const n=dom.createElement(tag);n.textContent=text;for(const [key,v]of Object.entries(attributes))n.setAttribute(key,String(v));root.append(n);return n;}
  element('p','Chọn kết quả thành công đang xem tại Vision trong Assets, rồi xác nhận riêng để dùng cho kế hoạch B-roll mới. Chọn tại đây không phân tích lại ảnh hoặc thay timeline.',{class:'hint'});
  const pick=element('button','Chọn kết quả Vision đang xem cho B-roll',{type:'button','data-broll-review-pick':''});
  const clearButton=element('button','Bỏ kết quả Vision khỏi B-roll',{type:'button','data-broll-review-clear':''});
  const status=element('p','Chưa chọn Vision. Kế hoạch dùng phân tích nguồn và thông tin tư liệu đã lưu.',{class:'hint',role:'status'});
  const label=element('label','Tôi đã xem kết quả Vision và muốn dùng cho kế hoạch B-roll mới.',{class:'check'});
  const ack=dom.createElement('input');ack.type='checkbox';ack.setAttribute('data-broll-review-ack','');label.append(ack);
  const mockLabel=element('label','Tôi hiểu mô phỏng không bổ sung điểm nhận diện hoặc chất lượng thật.',{class:'check'});
  const mockAck=dom.createElement('input');mockAck.type='checkbox';mockAck.setAttribute('data-broll-review-mock','');mockLabel.append(mockAck);
  function clear(){selected=null;binding=null;ack.checked=mockAck.checked=false;controls();}
  function controls(){
    root.hidden=!source();pick.disabled=blocked();clearButton.disabled=!selected||blocked();ack.disabled=!selected||blocked();
    mockLabel.hidden=!selected?.result?.mock;mockAck.disabled=mockLabel.hidden||blocked();
    status.textContent=selected?`${selected.result.mock?'Mô phỏng giao thức · không bổ sung điểm nhận diện/chất lượng':'Vision đã xem · dự đoán chưa hiệu chuẩn'} · nguồn ${selected.snapshot.source.asset.filename} · phản hồi ${selected.response_id} · chi phí ${selected.cost_operation_id}. Tiền đã tính hóa đơn: chưa có. Quyền, crop, QC và duyệt video vẫn cần kiểm tra riêng.`:
      'Chưa chọn Vision. Kế hoạch dùng phân tích nguồn và thông tin tư liệu đã lưu.';
  }
  function sync(){if(selected&&(binding!==context()||!same(selected,getReviewedVision())))clear();else controls();}
  function choose(){sync();if(blocked()){onMessage('Lưu chỉnh sửa và mở dự án nguồn có quyền chỉnh sửa trước khi chọn Vision.',true);return;}
    try{const row=getReviewedVision();reviewedVisionRequest(row,getState(),{acknowledgedReviewed:true,acknowledgedMock:row?.result?.mock??false});
      selected=structuredClone(row);binding=context();ack.checked=mockAck.checked=false;controls();
    }catch{clear();onMessage('Chọn kết quả Vision thành công của dự án này tại Assets trước.',true);}
  }
  function references(){const had=Boolean(selected);sync();if(blocked()||had&&!selected)throw new Error('Kết quả hoặc dự án đã thay đổi. Chọn lại Vision trước khi tạo kế hoạch.');
    return selected?[reviewedVisionRequest(selected,getState(),{acknowledgedReviewed:ack.checked,acknowledgedMock:mockAck.checked})]:[];
  }
  pick.addEventListener('click',choose);clearButton.addEventListener('click',clear);controls();
  return {choose,clear,sync,controls,references};
}
