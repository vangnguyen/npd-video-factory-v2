// Inert until an explicit user action. Chunk hashing keeps memory bounded to 1 MiB.
const limits={video:250,image:15,logo:15,audio:25,music:25,subtitle:1},chunkBytes=1048576;
const mimes={video:['video/mp4','video/quicktime'],image:['image/jpeg','image/png'],logo:['image/png'],
  audio:['audio/wav','audio/x-wav','audio/mpeg'],music:['audio/wav','audio/x-wav','audio/mpeg'],subtitle:['application/x-subrip','text/vtt']};
const labels={video:'Video',audio:'Âm thanh nguồn',image:'Ảnh',logo:'Logo PNG giữ alpha',music:'Nhạc',subtitle:'Phụ đề SRT/VTT'};
const stable=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),id=v=>typeof v==='string'&&/^nup_[a-f0-9]{32}$/.test(v);
const exact=(v,keys,optional=[])=>v&&typeof v==='object'&&!Array.isArray(v)&&keys.every(k=>Object.hasOwn(v,k))&&Object.keys(v).every(k=>keys.includes(k)||optional.includes(k));
export async function uploadDigest(data){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(v=>v.toString(16).padStart(2,'0')).join('');}
export async function validateNativeUpload(v,s,hash=uploadDigest){
  const r=v?.request;if(v?.schema_version!=='native-multipart-upload-v1'||!id(v.upload_id)||v.workspace_id!==s.workspace_id||v.project_id!==s.project?.id||v.publishing_enabled!==false
    ||!exact(v,['schema_version','upload_id','workspace_id','project_id','request','request_sha256','status','received_bytes','chunk_bytes','parts','parts_sha256','deadline','created_at','updated_at','failure_code','result','publishing_enabled'],['idempotent_replay'])
    ||Object.hasOwn(v,'idempotent_replay')&&typeof v.idempotent_replay!=='boolean'||!['deadline','created_at','updated_at'].every(k=>typeof v[k]==='string'&&Number.isFinite(Date.parse(v[k])))
    ||v.failure_code!==null&&(typeof v.failure_code!=='string'||!/^[A-Z0-9_]{1,160}$/.test(v.failure_code))
    ||!['receiving','validating','needs_attention','completed','cancelled'].includes(v.status)||v.chunk_bytes!==chunkBytes||!r||r.schema_version!=='native-multipart-upload-request-v1'
    ||!exact(r,['schema_version','revision','kind','content_type','filename','total_bytes','expected_sha256','rights_confirmed','illustration'])
    ||!Object.hasOwn(limits,r.kind)||!mimes[r.kind].includes(r.content_type)||typeof r.filename!=='string'||!r.filename||r.filename.length>200||/[\\/]/.test(r.filename)
    ||!Number.isSafeInteger(r.total_bytes)||r.total_bytes<1||r.total_bytes>limits[r.kind]*chunkBytes||!Number.isSafeInteger(r.revision)||r.revision<1||r.rights_confirmed!==true||typeof r.illustration!=='boolean'
    ||r.expected_sha256!==null&&!sha(r.expected_sha256)||!sha(v.request_sha256)||!sha(v.parts_sha256)||!Array.isArray(v.parts)||v.parts.length>250)
    throw Error('Bằng chứng upload không đúng dự án hoặc hợp đồng.');
  if(await hash(new TextEncoder().encode(stable(r)))!==v.request_sha256)throw Error('Nội dung yêu cầu upload đã thay đổi.');
  let offset=0;for(const[i,p]of v.parts.entries()){if(p.ordinal!==i||p.offset!==offset||p.bytes!==Math.min(chunkBytes,r.total_bytes-offset)||!sha(p.sha256)||Object.keys(p).length!==4)throw Error('Danh sách chunk không hợp lệ.');offset+=p.bytes;}
  if(offset!==v.received_bytes||offset>r.total_bytes||await hash(new TextEncoder().encode(stable(v.parts)))!==v.parts_sha256)throw Error('Checksum danh sách chunk không hợp lệ.');
  if(v.status==='completed'){
    const x=v.result,a=x?.asset;if(offset!==r.total_bytes||!a||!sha(a.sha256)||!sha(x.source_sha256)||x.source_sha256!==a.source_sha256||x.source_bytes!==r.total_bytes||a.source_bytes!==r.total_bytes
      ||!exact(x,['asset','source_sha256','source_bytes','duplicate','attached_revision','rights_status','publishing_enabled'])||typeof a.id!=='string'||!/^[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}$/.test(a.id)
      ||a.source_mime!==r.content_type||a.canonical_role!==r.kind||a.rights_confirmed!==true||typeof x.duplicate!=='boolean'||!Number.isSafeInteger(x.attached_revision)||x.attached_revision<1
      ||a.illustration!==r.illustration||typeof a.rights_status!=='string'||a.rights_status.length>64
      ||x.publishing_enabled!==false||x.rights_status!==a.rights_status||r.expected_sha256!==null&&r.expected_sha256!==x.source_sha256)throw Error('Biên nhận asset không đúng upload.');
  }else if(v.result!==null)throw Error('Upload chưa hoàn tất không được có biên nhận asset.');
  function privateFields(x,depth=0){if(depth>30)throw Error('Bằng chứng upload quá sâu.');if(x&&typeof x==='object')for(const[k,c]of Object.entries(x)){if(/^(?:token|access_token|refresh_token|token_path|credential_path|private_path|authorization|upload_url)$/i.test(k))throw Error('Bằng chứng upload chứa trường riêng tư.');privateFields(c,depth+1);}}
  privateFields(v);return v;
}
export function initializeNativeMultipartUpload({api,binary,getState,root=document,onWorking=()=>{},onMessage=()=>{},onSaved=async()=>{},hash=uploadDigest,uuid=()=>crypto.randomUUID()}){
  const card=root.getElementById('native-multipart-upload-card');card.hidden=false;card.replaceChildren();
  const node=(tag,text,name)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(name)n.id='native-multipart-upload-'+name;return n;};
  const label=(text,n)=>{const p=node('label',text);p.append(n);return p;};
  const button=(text,name)=>{const b=node('button',text,name);b.type='button';b.className='secondary';b.dataset.vfPermission='edit';return b;};
  const kind=node('select',null,'kind'),mime=node('select',null,'mime'),file=node('input',null,'file');file.type='file';
  for(const[k,text]of Object.entries(labels)){const option=node('option',text);option.value=k;kind.append(option);}kind.value='video';
  const rights=node('input',null,'rights'),illustration=node('input',null,'illustration');rights.type=illustration.type='checkbox';
  const list=button('Đọc upload đã lưu','history-read'),upload=button('Tải và lưu asset','upload'),resume=button('Tiếp tục upload đã chọn','resume'),
    pause=button('Tạm dừng sau chunk hiện tại','pause'),cancel=button('Hủy upload đang dở','cancel'),selection=node('select',null,'selection'),status=node('p','Chọn loại và file. MIME sẽ được kiểm tra với nội dung thực.','status'),detail=node('pre',null,'detail');
  detail.className='native-publication-evidence';list.dataset.vfPermission='read';
  card.append(node('summary','Upload có thể tiếp tục'),label('Loại asset',kind),label('MIME khai báo',mime),label('File gốc',file),
    label('Tôi có quyền sử dụng file đã chọn.',rights),label('Đây là hình minh họa.',illustration),upload,pause,list,label('Upload đã lưu',selection),resume,cancel,status,detail);
  let working=false,scope='',generation=0,selected=null,rows=[],pauseRequested=false;const keys=new Map();
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.canEdit,s.dirty,s.active]);};
  const endpoint=s=>'/api/projects/'+s.project.id+'/uploads';
  function modes(){mime.replaceChildren();for(const value of mimes[kind.value]??[]){const n=node('option',value);n.value=value;mime.append(n);}mime.value=mimes[kind.value]?.[0]??'';file.accept=(mimes[kind.value]??[]).join(',');}
  modes();
  function controls(){const s=getState(),blocked=working||s.busy,edit=s.canEdit&&!s.dirty&&!s.active&&!s.project?.archived;
    for(const n of[kind,mime,file,rights,illustration])n.disabled=blocked||!s.project||!edit;
    list.disabled=blocked||!s.project;selection.disabled=blocked||!rows.length;upload.disabled=blocked||!edit||!file.files?.[0]||!rights.checked;
    resume.disabled=blocked||!edit||!selected||!['receiving','needs_attention'].includes(selected.status)||!file.files?.[0]||!rights.checked;
    cancel.disabled=blocked||!edit||!selected||!['receiving','needs_attention','cancelled'].includes(selected.status);pause.disabled=!working;}
  function sync(){const next=context();if(next!==scope){scope=next;generation++;selected=null;rows=[];selection.replaceChildren();detail.textContent='';rights.checked=false;}controls();}
  const render=()=>{selection.replaceChildren();for(const r of rows){const n=node('option',r.request.filename+' · '+r.request.kind+' · '+r.status);n.value=r.upload_id;selection.append(n);}selection.value=selected?.upload_id??'';detail.textContent=selected?JSON.stringify(selected,null,2):'';controls();};
  async function run(fn){sync();const s=getState();if(working||s.busy||!s.project)return;const expected=context(),ticket=++generation;working=true;pauseRequested=false;onWorking(true);controls();const accept=()=>expected===context()&&ticket===generation;
    try{await fn(s,accept);}catch(e){if(accept())onMessage(e.message,true);}finally{working=false;onWorking(false);sync();}}
  function chosen(s){const f=file.files?.[0];if(!s.canEdit||s.dirty||s.active||s.project?.archived||!f||!rights.checked||!Number.isSafeInteger(f.size)||f.size<1||f.size>limits[kind.value]*chunkBytes||!mimes[kind.value]?.includes(mime.value))throw Error('Lưu dự án, chọn đúng loại/file và xác nhận quyền sử dụng trước.');return f;}
  async function readHistory(){await run(async(s,accept)=>{const v=await api(endpoint(s));if(!accept())return;
    if(v?.schema_version!=='native-multipart-upload-page-v1'||v.workspace_id!==s.workspace_id||v.project_id!==s.project.id||!Array.isArray(v.items)||v.items.length>50||typeof v.truncated!=='boolean'||v.publishing_enabled!==false)throw Error('Lịch sử upload không đúng phạm vi.');
    const validated=[];for(const item of v.items)validated.push(await validateNativeUpload(item,s,hash));if(!accept())return;rows=validated;selected=rows.find(r=>r.upload_id===selected?.upload_id)??rows[0]??null;render();});}
  async function transfer(s,accept,f,current){
    selected=await validateNativeUpload(current,s,hash);if(!accept())return;
    if(selected.request.kind!==kind.value||selected.request.content_type!==mime.value||selected.request.filename!==f.name||selected.request.total_bytes!==f.size||selected.request.illustration!==illustration.checked)throw Error('File và loại đang chọn khác upload đã lưu.');
    if(selected.status==='completed'){status.textContent='Upload đã hoàn tất; không gửi lại bytes.';render();return;}
    if(!['receiving','needs_attention'].includes(selected.status))throw Error('Upload không ở trạng thái có thể tiếp tục.');
    for(const p of selected.parts){const data=await f.slice(p.offset,p.offset+p.bytes).arrayBuffer();if(await hash(data)!==p.sha256)throw Error('File đang chọn khác chunk đã lưu. Chọn lại đúng file gốc.');if(!accept())return;}
    for(let offset=selected.received_bytes;offset<f.size;offset+=chunkBytes){if(pauseRequested||!accept())break;
      const data=await f.slice(offset,Math.min(offset+chunkBytes,f.size)).arrayBuffer(),checksum=await hash(data);if(!accept())return;
      const v=await binary(endpoint(s)+'/'+selected.upload_id+'/chunks',data,{'X-VF-Offset':String(offset),'X-VF-SHA256':checksum});if(!accept())return;
      const accepted=await validateNativeUpload(v,s,hash);if(!accept())return;
      if(accepted.upload_id!==selected.upload_id||accepted.request_sha256!==selected.request_sha256||accepted.received_bytes!==offset+data.byteLength)throw Error('Phản hồi chunk không đúng upload đã chọn.');
      selected=accepted;status.textContent='Đã nhận '+selected.received_bytes+'/'+f.size+' bytes.';render();}
    rows=[selected,...rows.filter(r=>r.upload_id!==selected.upload_id)];render();
    if(!accept())return;if(pauseRequested){status.textContent='Đã tạm dừng; bytes đã nhận được giữ để tiếp tục.';return;}
    if(selected.received_bytes!==f.size)throw Error('Upload chưa nhận đủ bytes.');
    const value=await api(endpoint(s)+'/'+selected.upload_id+'/complete',{revision:s.project.revision,expected_parts_sha256:selected.parts_sha256});if(!accept())return;
    const done=await validateNativeUpload(value,s,hash);if(!accept())return;if(done.upload_id!==selected.upload_id||done.request_sha256!==selected.request_sha256||done.status!=='completed')throw Error('Biên nhận hoàn tất không đúng upload.');
    selected=done;rows=[done,...rows.filter(r=>r.upload_id!==done.upload_id)];status.textContent=done.result.duplicate?'Đã nhận diện asset trùng trong dự án.':'Đã lưu asset và file gốc. Phiên bản mới cần được duyệt lại.';render();rights.checked=false;await onSaved(done);
  }
  async function createUpload(){await run(async(s,accept)=>{const f=chosen(s),body={schema_version:'native-multipart-upload-request-v1',revision:s.project.revision,kind:kind.value,content_type:mime.value,filename:f.name,total_bytes:f.size,expected_sha256:null,rights_confirmed:true,illustration:illustration.checked};
    const keyScope=stable([s.workspace_id,s.project.id,body]);if(!keys.has(keyScope))keys.set(keyScope,'native-multipart-'+uuid());
    const result=await api(endpoint(s),{...body,request_key:keys.get(keyScope)});if(!accept())return;const current=await validateNativeUpload(result,s,hash);if(stable(current.request)!==stable(body))throw Error('Upload trả về không đúng yêu cầu đã chọn.');await transfer(s,accept,f,current);});}
  async function resumeUpload(){await run(async(s,accept)=>{const f=chosen(s);if(!selected)throw Error('Đọc và chọn upload đã lưu trước.');const current=await api(endpoint(s)+'/'+selected.upload_id);if(!accept())return;await transfer(s,accept,f,current);});}
  async function cancelUpload(){await run(async(s,accept)=>{if(!s.canEdit||s.dirty||s.active||s.project?.archived||!selected)throw Error('Chọn upload đang dở khi dự án có thể chỉnh sửa.');const prior=selected,value=await api(endpoint(s)+'/'+prior.upload_id+'/cancel',{});if(!accept())return;
    const v=await validateNativeUpload(value,s,hash);if(v.upload_id!==prior.upload_id||v.request_sha256!==prior.request_sha256||v.status!=='cancelled')throw Error('Phản hồi hủy không đúng upload.');selected=v;rows=rows.map(r=>r.upload_id===v.upload_id?v:r);render();});}
  kind.addEventListener('change',()=>{modes();rights.checked=false;controls();});for(const n of[mime,file,rights,illustration])n.addEventListener('change',controls);
  selection.addEventListener('change',()=>{selected=rows.find(r=>r.upload_id===selection.value)??null;render();});
  for(const[b,fn]of[[upload,createUpload],[resume,resumeUpload],[list,readHistory],[cancel,cancelUpload]])b.addEventListener('click',fn);pause.addEventListener('click',()=>{pauseRequested=true;});
  sync();return{createUpload,resumeUpload,readHistory,cancelUpload,controls,sync,currentBinding:()=>({upload:selected}),isWorking:()=>working};
}
