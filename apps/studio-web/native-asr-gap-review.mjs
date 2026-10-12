// Read-only initialization; edits and known-job resume require explicit clicks.
const id=v=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v),sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const asset=v=>typeof v==='string'&&/^[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}$/.test(v);
export function validateGapReviews(v,s){
  function privacy(x,depth=0){if(depth>30)throw Error('Bản kiểm tra quá sâu.');if(x&&typeof x==='object')for(const[k,c]of Object.entries(x)){if(/^(token|access_token|refresh_token|authorization|private_path|credential_path)$/i.test(k))throw Error('Bản kiểm tra chứa dữ liệu riêng tư.');privacy(c,depth+1);}}
  privacy(v);
  if(v?.schema_version!=='native-asr-gap-review-v1'||v.workspace_id!==s.workspace_id||v.project_id!==s.project?.id||v.revision!==s.project?.revision||v.provider_calls!==0||v.source_media_mutated!==false||v.publishing_enabled!==false||v.human_review_required!==true||!Array.isArray(v.items)||v.items.length>800)throw Error('Bản kiểm tra không đúng dự án hoặc phiên bản.');
  const seen=new Set();
  for(const r of v.items){
    const key=r.job_id+'/'+r.asset_id;
    if(!id(r.job_id)||!asset(r.asset_id)||seen.has(key)||!sha(r.source_sha256)||!sha(r.candidate_sha256)||typeof r.filename!=='string'||!['video','audio'].includes(r.source_kind)||!['failed','succeeded','queued','running','retrying','interrupted'].includes(r.status)||typeof r.editable!=='boolean'||typeof r.can_resume!=='boolean'||!Number.isSafeInteger(r.version)||r.version<0||r.version>50||!Array.isArray(r.history)||r.history.length!==r.version||r.source_url!==`/api/projects/${v.project_id}/asr-gap-reviews/${r.job_id}/${r.asset_id}/source`)throw Error('Nguồn bản kiểm tra không hợp lệ.');
    seen.add(key);
    if(!Array.isArray(r.original_words)||!r.original_words.length||r.original_words.length>2000||!Array.isArray(r.current_words)||r.current_words.length!==r.original_words.length||!Array.isArray(r.gaps)||!r.gaps.length)throw Error('Thiếu từ hoặc khoảng thiếu audio.');
    for(const [i,w]of r.original_words.entries())if(w.ordinal!==i||typeof w.text!=='string'||!w.text.trim()||!Number.isFinite(w.start_seconds)||!Number.isFinite(w.end_seconds)||w.start_seconds<0||w.end_seconds<=w.start_seconds||w.end_seconds>600||typeof w.crosses_missing_audio!=='boolean')throw Error('Thời gian từ gốc không hợp lệ.');
    for(const [i,w]of r.current_words.entries())if(w.ordinal!==i||typeof w.text!=='string'||!w.text.trim()||w.text.length>500||!Number.isFinite(w.start_seconds)||!Number.isFinite(w.end_seconds)||w.start_seconds<0||w.end_seconds<=0||w.end_seconds>600||typeof w.removed!=='boolean')throw Error('Bản sửa từ không hợp lệ.');
    for(const g of r.gaps)if(!Number.isFinite(g.start_seconds)||!Number.isFinite(g.end_seconds)||g.start_seconds<0||g.end_seconds<=g.start_seconds||g.end_seconds>600)throw Error('Khoảng thiếu audio không hợp lệ.');
    for(const [i,h]of r.history.entries())if(h.version!==i+1||h.candidate_sha256!==r.candidate_sha256||h.job_id!==r.job_id||h.asset_id!==r.asset_id||!sha(h.sha256)||h.acknowledged!==true||h.source_media_mutated!==false||h.provider_calls!==0)throw Error('Lịch sử kiểm tra không khớp.');
  }
  return v;
}

export function initializeGapReview({api,getState,root=document,onWorking=()=>{},onSaved=async()=>{},onMessage=()=>{},onDirty=()=>{}}){
  const card=root.getElementById('native-asr-gap-review-card');card.hidden=false;card.replaceChildren();
  const node=(tag,text,name)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(name)n.id='native-asr-gap-review-'+name;return n;};
  const button=(text,name,permission)=>{const n=node('button',text,name);n.type='button';n.className='secondary';n.dataset.vfPermission=permission;return n;};
  const read=button('Đọc các từ cần kiểm tra','read','read'),save=button('Lưu bản sửa từ','save','edit'),resume=button('Tiếp tục job đã biết','resume','edit'),discard=button('Bỏ thay đổi chưa lưu','discard','edit'),
    select=node('select',null,'selection'),playerBox=node('div'),original=node('p'),gaps=node('p'),rows=node('div',null,'rows'),prev=button('Trang trước','prev','read'),next=button('Trang sau','next','read'),pageText=node('span'),
    acknowledge=node('input',null,'acknowledged'),note=node('textarea',null,'note'),status=node('p','Bấm đọc khi job báo từ đi qua khoảng thiếu audio.','status');
  acknowledge.type='checkbox';note.maxLength=1000;note.rows=2;note.placeholder='Ghi chú kiểm tra';
  const ackLabel=node('label','Tôi đã nghe nguồn và kiểm tra các từ, thời điểm hoặc từ cần bỏ.');ackLabel.append(acknowledge);
  card.append(node('summary','Từ nhận diện cần kiểm tra'),node('p','Bằng chứng provider gốc được giữ riêng. Bản sửa do người dùng nhập; lưu không gọi ASR và không duyệt video.'),read,select,playerBox,original,gaps,rows,prev,pageText,next,ackLabel,note,save,resume,discard,status);
  let value=null,selected=null,draft=[],page=0,dirty=false,working=false,scope='',generation=0,pending=null;const fields=new Map();
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.canEdit,s.active,s.project?.archived]);};
  function markDirty(v){dirty=v;onDirty(v);controls();}
  function controls(){const s=getState(),blocked=working||s.busy,ownDirty=!s.dirty||s.dirtyPart==='asr_gap_review';
    read.disabled=blocked||!s.project||dirty;select.disabled=blocked||!value?.items.length||dirty;
    const editable=!blocked&&ownDirty&&s.canEdit&&!s.active&&!s.project?.archived&&selected?.editable;
    save.disabled=!editable||!acknowledge.checked;resume.disabled=blocked||!ownDirty||dirty||!s.canEdit||s.active||s.project?.archived||!selected?.can_resume;
    discard.disabled=blocked||!dirty;acknowledge.disabled=!editable;note.disabled=!editable;
    prev.disabled=blocked||page===0;next.disabled=blocked||page*25+25>=draft.length;
    for(const f of fields.values())for(const input of Object.values(f))input.disabled=!editable;
  }
  function sync(){const nextScope=context();if(nextScope!==scope){scope=nextScope;generation++;value=null;selected=null;draft=[];page=0;dirty=false;pending=null;select.replaceChildren();rows.replaceChildren();playerBox.replaceChildren();fields.clear();acknowledge.checked=false;}controls();}
  function renderRows(){rows.replaceChildren();fields.clear();pageText.textContent=` ${page+1} / ${Math.max(1,Math.ceil(draft.length/25))} `;
    for(const w of draft.slice(page*25,page*25+25)){
      const baseline=selected.original_words[w.ordinal],group=node('fieldset'),legend=node('legend',`Từ ${w.ordinal+1}: ${baseline.text} · gốc ${baseline.start_seconds} → ${baseline.end_seconds} giây${baseline.crosses_missing_audio?' · đi qua khoảng thiếu':''}`);
      group.append(legend);
      const text=node('input'),start=node('input'),end=node('input'),removed=node('input');text.type='text';text.maxLength=500;text.value=w.text;start.type=end.type='number';start.min=end.min='0';start.max=end.max='600';start.step=end.step='0.001';start.value=String(w.start_seconds);end.value=String(w.end_seconds);removed.type='checkbox';removed.checked=w.removed;
      for(const [label,input]of [['Chữ',text],['Bắt đầu (giây nguồn)',start],['Kết thúc (giây nguồn)',end],['Bỏ từ này khỏi bản sửa',removed]]){const l=node('label',label);l.append(input);group.append(l);}
      rows.append(group);fields.set(w.ordinal,{text,start,end,removed});
      text.addEventListener('input',()=>{w.text=text.value;markDirty(true);});start.addEventListener('input',()=>{w.start_seconds=start.value.trim()?Number(start.value):NaN;markDirty(true);});end.addEventListener('input',()=>{w.end_seconds=end.value.trim()?Number(end.value):NaN;markDirty(true);});removed.addEventListener('change',()=>{w.removed=removed.checked;markDirty(true);});
    }controls();
  }
  function render(){select.replaceChildren();for(const r of value?.items??[]){const option=node('option',`${r.filename} · bản sửa ${r.version} · ${r.status}`);option.value=r.job_id+'/'+r.asset_id;select.append(option);}select.value=selected?selected.job_id+'/'+selected.asset_id:'';
    playerBox.replaceChildren();if(selected){const player=node(selected.source_kind==='video'?'video':'audio',null,'source');player.controls=true;player.preload='metadata';player.src=selected.source_url;player.style.width='100%';player.style.maxHeight='240px';playerBox.append(player);}
    original.textContent=selected?'Bản provider gốc: '+selected.original_words.map(w=>w.text).join(' '):'';gaps.textContent=selected?'Khoảng thiếu audio: '+selected.gaps.map(g=>`${g.start_seconds} → ${g.end_seconds} giây`).join('; '):'';renderRows();
  }
  async function run(fn){sync();const s=getState();if(working||s.busy||!s.project)return;const expected=context(),ticket=++generation;working=true;onWorking(true);controls();const accept=()=>context()===expected&&generation===ticket;
    try{await fn(s,accept);}catch(e){if(accept()){status.textContent=e.message;onMessage(e.message,true);}}finally{working=false;onWorking(false);sync();}}
  const path=s=>'/api/projects/'+s.project.id+'/asr-gap-reviews';
  async function load(){await run(async(s,accept)=>{if(dirty)throw Error('Lưu hoặc bỏ thay đổi chưa lưu trước khi đọc lại.');const response=await api(path(s));if(!accept())return;value=validateGapReviews(response,s);selected=value.items[0]??null;draft=structuredClone(selected?.current_words??[]);page=0;acknowledge.checked=false;render();status.textContent=!selected?'Chưa có từ đi qua khoảng thiếu audio cần kiểm tra.':selected.editable?'Nghe nguồn, sửa thời điểm hoặc bỏ từ sai, rồi lưu bản sửa.':'Lịch sử chỉ đọc. Bản sửa được giữ riêng với bằng chứng provider gốc.';});}
  async function saveReview(){await run(async(s,accept)=>{if(!s.canEdit||s.active||s.project.archived||s.dirty&&s.dirtyPart!=='asr_gap_review'||!selected?.editable||!acknowledge.checked)throw Error('Kiểm tra và xác nhận bản sửa khi dự án có thể chỉnh sửa.');
    let end=0;for(const w of draft){if(!w.text.trim()||w.text.length>500||!Number.isFinite(w.start_seconds)||!Number.isFinite(w.end_seconds))throw Error('Nhập chữ và thời điểm hợp lệ cho từng từ.');if(!w.removed){if(w.start_seconds<end||w.end_seconds<=w.start_seconds||selected.gaps.some(g=>w.start_seconds<g.end_seconds&&w.end_seconds>g.start_seconds))throw Error('Từ còn chồng nhau hoặc đi qua khoảng thiếu audio.');end=w.end_seconds;}}
    if(draft.every(w=>w.removed))throw Error('Bản sửa cần ít nhất một từ; không thay bằng transcript rỗng.');const old=selected,requested=structuredClone(draft);
    const identity=JSON.stringify([old.candidate_sha256,old.version,requested,note.value]);if(pending?.identity!==identity)pending={identity,key:crypto.randomUUID()};
    const response=await api(path(s)+'/'+old.job_id+'/'+old.asset_id,{revision:s.project.revision,candidate_sha256:old.candidate_sha256,expected_version:old.version,request_key:pending.key,note:note.value,acknowledged:true,words:requested});
    if(!accept())return;value=validateGapReviews(response,s);selected=value.items.find(r=>r.job_id===old.job_id&&r.asset_id===old.asset_id);
    if(typeof response.changed!=='boolean'||!selected||selected.candidate_sha256!==old.candidate_sha256||selected.version!==old.version+1||JSON.stringify(selected.original_words)!==JSON.stringify(old.original_words)||selected.current_words.some((w,i)=>JSON.stringify(w)!==JSON.stringify({...requested[i],text:requested[i].text.normalize('NFC')})))throw Error('Biên nhận bản sửa không khớp yêu cầu.');
    pending=null;draft=structuredClone(selected.current_words);markDirty(false);acknowledge.checked=false;render();status.textContent='Đã lưu bản sửa riêng. Bấm tiếp tục job đã biết để áp dụng; video vẫn cần duyệt.';await onSaved(response);});}
  async function resumeKnown(){await run(async(s,accept)=>{if(dirty||!s.canEdit||s.dirty||s.active||s.project.archived||!selected?.can_resume)throw Error('Lưu bản sửa và chờ dự án sẵn sàng trước khi tiếp tục.');
    const old=selected,response=await api('/api/jobs/'+old.job_id+'/resume',{});if(!accept())return;if(response.id!==old.job_id||response.project_id!==s.project.id||response.kind!=='asr'||response.status!=='queued')throw Error('Biên nhận tiếp tục job không hợp lệ.');status.textContent='Job cũ đã được tiếp tục từ bằng chứng đã lưu.';await onSaved(response);});}
  select.addEventListener('change',()=>{selected=value.items.find(r=>r.job_id+'/'+r.asset_id===select.value);draft=structuredClone(selected?.current_words??[]);page=0;acknowledge.checked=false;render();});
  acknowledge.addEventListener('change',controls);read.addEventListener('click',load);save.addEventListener('click',saveReview);resume.addEventListener('click',resumeKnown);
  prev.addEventListener('click',()=>{page=Math.max(0,page-1);renderRows();});next.addEventListener('click',()=>{page=Math.min(Math.ceil(draft.length/25)-1,page+1);renderRows();});
  discard.addEventListener('click',()=>{draft=structuredClone(selected?.current_words??[]);acknowledge.checked=false;note.value='';markDirty(false);renderRows();});
  sync();return{load,save:saveReview,resume:resumeKnown,sync,controls,fields,binding:()=>({value,selected,draft,dirty}),isWorking:()=>working};
}
