const ID=/^[a-f0-9]{32}$/,SHA=/^[a-f0-9]{64}$/,BATCH=/^nnvb_[a-f0-9]{32}$/;
const dimensions={'16:9':[1920,1080],'9:16':[1080,1920],'1:1':[1080,1080],'4:5':[1080,1350]};
const source=p=>p?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
const context=s=>JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision]);
function profile(p){const pair=dimensions[p?.aspect_ratio];
  if(!/^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$/.test(p?.profile_ref??'')||!pair||p.width!==pair[0]||p.height!==pair[1]
    ||typeof p.label!=='string'||!p.label.length||p.label.length>100||![null,'youtube','tiktok','instagram','facebook'].includes(p.platform))throw new Error('Định dạng bản lồng tiếng không hợp lệ.');return p;
}
export function validateNarratedVariantBatch(v,s){
  if(v?.schema_version!=='native-narrated-variant-batch-v1'||v.workspace_id!==s.workspace_id||v.master_project_id!==s.project?.id||!BATCH.test(v.batch_id??'')
    ||v.external_provider_calls!==0||v.result?.schema_version!=='native-narrated-variants-v1'||v.result.master_project_mutated!==false||v.result.publishing_enabled!==false
    ||v.result.new_inference_calls!==0||v.result.external_provider_calls!==0||v.result.rights_authority_inherited!==false||v.result.human_approval_required_per_variant!==true
    ||!Array.isArray(v.result.variants)||!v.result.variants.length||v.result.variants.length>6||!Number.isInteger(v.snapshot?.master_revision)||v.snapshot.master_revision<1)throw new Error('Nhóm bản lồng tiếng không khớp phạm vi.');
  for(const child of v.result.variants){profile(child.profile);const d=child.derivation;
    if(!ID.test(child.project_id??'')||child.approval_inherited!==false||child.render_dispatched!==false||!SHA.test(child.initial_document_sha256??'')||!SHA.test(child.initial_timeline_sha256??'')
      ||d?.schema_version!=='native-narrated-narration-derivation-v1'||d.batch_id!==v.batch_id||d.workspace_id!==s.workspace_id||d.master_project_id!==s.project.id||d.child_project_id!==child.project_id
      ||!ID.test(d.source_project_id??'')||!ID.test(d.source_narration_job_id??'')||!SHA.test(d.source_plan_sha256??'')||!SHA.test(d.source_voice_sha256??'')
      ||d.approval_inherited!==false||d.rights_authority_inherited!==false||d.new_inference_calls!==0||d.human_review_required!==true)throw new Error('Bản lồng tiếng phải giữ nguồn và duyệt riêng.');
  }
  if(new Set(v.result.variants.map(c=>c.project_id)).size!==v.result.variants.length)throw new Error('Bản dựng bị trùng.');return v;
}
export function initializeNarratedVariants({api,getState,onMessage=()=>{},onOpen=async()=>{},onCreated=()=>{},dom=globalThis.document,newKey=()=>globalThis.crypto.randomUUID()}){
  const root=dom.getElementById('native-narrated-variants-card');let scope='',serial=0,working=false,rows=[],profiles=[],cursor=null,binding=null;const selected=new Map(),keys=new Map();
  const node=(tag,text,parent,attrs={})=>{const n=dom.createElement(tag);if(text!==null)n.textContent=text;for(const [k,v]of Object.entries(attrs))n.setAttribute(k,String(v));parent.append(n);return n;};
  node('summary','Các định dạng từ master lồng tiếng',root);node('p','Tạo bản chưa duyệt từ timeline đã lưu và audio đã đo. Giữ nguyên lời đọc, không tạo giọng mới. Mỗi bản cần xem crop, tạo preview có tiếng, kiểm tra quyền và duyệt riêng.',root,{class:'hint'});
  const tools=node('div',null,root,{class:'planner-tools'}),load=node('button','Đọc định dạng và bản đã tạo',tools,{type:'button'}),choices=node('div',null,root),create=node('button','Tạo các bản lồng tiếng đã chọn',root,{type:'button'}),status=node('p',null,root,{class:'hint'}),history=node('div',null,root),more=node('button','Trang tiếp',root,{type:'button'});
  const eligible=s=>!!s.project?.document?.prepared_narration&&!source(s.project);
  function controls(){const s=getState(),blocked=working||s.busy||s.active||(s.project?.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status));
    root.hidden=!s.project||source(s.project);load.disabled=blocked||!s.project;more.disabled=blocked||!cursor;
    create.disabled=blocked||s.dirty||s.canEdit===false||s.project?.archived||!eligible(s)||binding?.revision!==s.project?.revision||!SHA.test(binding?.prepared_reference_sha256??'')||![...selected.values()].some(n=>n.checked);
    for(const n of selected.values())n.disabled=blocked||s.canEdit===false;
    for(const n of history.querySelectorAll('button'))n.disabled=blocked||s.dirty;
  }
  function draw(){history.replaceChildren();for(const row of rows){const card=node('article',null,history,{class:'planner-scene'});node('h3',`Master phiên bản ${row.snapshot.master_revision}`,card);
      for(const child of row.result.variants){const line=node('p',`${child.name} · ${child.profile.width}×${child.profile.height} · crop cần xem lại`,card),open=node('button','Mở bản lồng tiếng',line,{type:'button'});
        open.addEventListener('click',async()=>{const s=getState();if(working||s.busy||s.dirty)return;try{await onOpen(child.project_id);}catch(e){onMessage(e.message,true);}});}
    }status.textContent=eligible(getState())?'Đọc định dạng rồi chọn các bản. Duyệt và ngoại lệ quyền của master không chuyển sang bản mới.':'Tạo và áp dụng lời đọc đã đo vào master trước khi tạo định dạng.';controls();
  }
  function sync(){const next=context(getState());if(next!==scope){scope=next;serial++;working=false;rows=[];profiles=[];cursor=null;binding=null;keys.clear();selected.clear();choices.replaceChildren();}draw();}
  async function perform(fn){sync();if(working||getState().busy)return;const expected=scope,ticket=serial;working=true;controls();
    try{const apply=await fn();if(expected===context(getState())&&ticket===serial)apply();}catch(e){if(expected===context(getState())&&ticket===serial)onMessage(e.message,true);}
    finally{if(expected===context(getState())&&ticket===serial){working=false;draw();}}
  }
  function page(v,s){if(v?.schema_version!=='native-narrated-variant-page-v1'||v.workspace_id!==s.workspace_id||v.master_project_id!==s.project?.id||v.external_provider_calls!==0
      ||v.current_master?.revision!==s.project.revision||!Array.isArray(v.items)||v.items.length>25||(v.next_cursor!==null&&typeof v.next_cursor!=='string'))throw new Error('Lịch sử bản lồng tiếng đã thay đổi.');
    if(v.current_master.prepared_reference_sha256!==null&&!SHA.test(v.current_master.prepared_reference_sha256??''))throw new Error('Nguồn lời đọc chưa hợp lệ.');
    v.items.forEach(row=>validateNarratedVariantBatch(row,s));return v;
  }
  async function read(next=false){if(!getState().project)return;return perform(async()=>{const s=getState(),path=`/api/projects/${s.project.id}/narrated-variants?limit=25${next&&cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`;
    const [p,c]=await Promise.all([api(path),profiles.length?Promise.resolve(null):api('/api/narrated/variant-profiles')]);page(p,s);let fresh=null;
    if(c){if(c.schema_version!=='native-narrated-variant-catalog-v1'||c.publishing_enabled!==false||c.provider_dispatches!==0||!Array.isArray(c.profiles)||!c.profiles.length||c.profiles.length>32)throw new Error('Danh mục bản lồng tiếng chưa hợp lệ.');fresh=c.profiles.map(profile);if(new Set(fresh.map(p=>p.profile_ref)).size!==fresh.length)throw new Error('Định dạng bị trùng.');}
    return()=>{binding=p.current_master;rows=next?[...rows,...p.items.filter(row=>!rows.some(old=>old.batch_id===row.batch_id))]:p.items;cursor=p.next_cursor;
      if(fresh){profiles=fresh;choices.replaceChildren();selected.clear();for(const p of profiles){const label=node('label',p.label+' ',choices,{class:'check'}),input=node('input',null,label,{type:'checkbox'});input.checked=true;input.addEventListener('change',controls);selected.set(p.profile_ref,input);}}};
  });}
  async function make(){const s=getState();if(s.canEdit===false||s.dirty||s.busy||s.active||(s.project?.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status))||s.project?.archived||!eligible(s)||binding?.revision!==s.project?.revision)return onMessage('Cần master đã lưu, lời đọc đã đo và quyền biên tập.',true);
    return perform(async()=>{const refs=profiles.filter(p=>selected.get(p.profile_ref)?.checked).map(p=>p.profile_ref);if(!refs.length||refs.length>6||binding.timeline_version!==s.project.document.canonical_timeline.version||!SHA.test(binding.prepared_reference_sha256??''))throw new Error('Đọc lại master và chọn từ một đến sáu định dạng.');
      const body={schema_version:'native-narrated-variant-request-v1',revision:s.project.revision,expected_version:binding.timeline_version,expected_prepared_reference_sha256:binding.prepared_reference_sha256,profile_refs:refs};
      const signature=scope+JSON.stringify(body),key=keys.get(signature)??`native-narrated-${newKey()}`;keys.set(signature,key);const row=validateNarratedVariantBatch(await api(`/api/projects/${s.project.id}/narrated-variants`,{...body,request_key:key}),s);
      return()=>{rows=[row,...rows.filter(old=>old.batch_id!==row.batch_id)];cursor=null;onMessage('Đã tạo các bản chưa duyệt với lời đọc gốc. Mở từng bản, kiểm tra crop, preview và duyệt riêng.');onCreated();};
    });
  }
  load.addEventListener('click',()=>read());more.addEventListener('click',()=>read(true));create.addEventListener('click',make);sync();return {sync,controls,read,create:make,isWorking:()=>working};
}
