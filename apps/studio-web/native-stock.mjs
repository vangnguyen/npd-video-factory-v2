const HASH=/^[a-f0-9]{64}$/,ID=/^nstk_[a-f0-9]{32}$/,CANDIDATE=/^smc_[a-f0-9]{24}$/;
const STATES=new Set(['queued','running','retry_scheduled','succeeded','failed','not_configured','cancelled']);
export const supportsNativeStock=session=>session?.capabilities?.native_stock_media===true;
export function stockSourceLink(value,provider){const url=new URL(value),host=provider==='pexels'?'pexels.com':provider==='pixabay'?'pixabay.com':null;
  if(!host||url.protocol!=='https:'||![host,`www.${host}`].includes(url.hostname)||url.port||url.username||url.password||url.search||url.hash)throw new Error('Tham chiếu stock không hợp lệ.');return url.href;}

export function initializeNativeStock({api,getState,dom=document,onMessage=()=>{},onSaved=async()=>{},onWorking=()=>{},uuid=()=>crypto.randomUUID(),
  setTimer=(fn,time)=>setTimeout(fn,time),clearTimer=id=>clearTimeout(id)}){
  const root=dom.getElementById('native-stock-panel'),node=(tag,text)=>{const value=dom.createElement(tag);value.textContent=text??'';return value;};
  const status=node('p','Chưa đọc cấu hình và lịch sử stock.'),read=node('button','Đọc nguồn stock & lịch sử'),provider=node('select'),query=node('input'),type=node('select'),orientation=node('select');
  query.type='text';query.maxLength=200;query.placeholder='Ví dụ: công nghệ AI, làm việc với máy tính';
  function options(control,rows){for(const [value,text]of rows){const option=node('option',text);option.value=value;control.append(option);}}
  options(type,[['video','Video'],['image','Ảnh']]);options(orientation,[['portrait','Dọc'],['landscape','Ngang'],['square','Vuông'],['any','Bất kỳ']]);
  const ack=node('input');ack.type='checkbox';const acknowledgment=node('label');acknowledgment.className='check';
  const ackText=node('span','Tôi chọn tìm/tải từ API đã cấu hình và sẽ kiểm tra nguồn, tác giả, giấy phép trước khi sử dụng.');acknowledgment.append(ack,ackText);
  const search=node('button','Tìm 5 tư liệu'),jobs=node('select'),candidates=node('select'),detail=node('pre'),download=node('button','Tải tư liệu đã chọn'),cancel=node('button','Hủy yêu cầu đang chờ');
  const importAck=node('input');importAck.type='checkbox';const importLabel=node('label');importLabel.className='check';
  importLabel.append(importAck,node('span','Tôi chọn thêm tư liệu đã kiểm tra vào dự án. Thao tác này cần duyệt lại và không cấp quyền xuất bản.'));
  const attach=node('button','Thêm tư liệu vào dự án'),more=node('button','Lịch sử tiếp'),sources=node('p'),preview=node('div');preview.className='native-stock-preview';
  const pexels=node('a','Tư liệu từ Pexels');pexels.href='https://www.pexels.com/';const pixabay=node('a','Tư liệu từ Pixabay');pixabay.href='https://pixabay.com/';sources.append(pexels,node('span',' · '),pixabay);
  for(const control of [read,provider,query,type,orientation,ack,search,jobs,candidates,download,cancel,importAck,attach,more]){
    control.dataset.workspaceControl='';if(control.tagName==='BUTTON')control.type='button';}
  for(const control of [provider,query,type,orientation,ack,search,download,cancel])control.dataset.vfPermission='manage';attach.dataset.vfPermission='edit';
  function label(text,control){const wrapper=node('label',text);wrapper.append(control);return wrapper;}
  detail.className='native-publication-evidence';status.className='hint';root.append(status,sources,read,label('Nguồn API',provider),label('Từ khóa',query),
    label('Loại tư liệu',type),label('Hướng khung',orientation),acknowledgment,search,label('Yêu cầu đã lưu',jobs),label('Tư liệu tìm được',candidates),detail,download,cancel,importLabel,attach,more,preview);
  let scope='',serial=0,working=false,configuration=null,rows=[],cursor=null,selected=null,candidate=null,timer=null,polls=0;const keys=new Map();
  const context=()=>JSON.stringify([getState().workspace_id,getState().project?.id,getState().project?.revision]);
  const blocked=()=>working||getState().busy;
  const selectedProvider=()=>configuration?.items.find(row=>row.provider===provider.value);
  const editable=()=>!blocked()&&getState().project&&!getState().dirty&&!getState().active&&!getState().project.archived;
  function controls(){const state=getState(),edit=editable(),owner=edit&&state.canManage;read.disabled=blocked()||!state.project;more.disabled=blocked()||!cursor;
    for(const control of [provider,query,type,orientation,ack])control.disabled=!owner;jobs.disabled=blocked()||!rows.length;candidates.disabled=blocked()||!candidate;
    search.disabled=!owner||!selectedProvider()||!ack.checked||!query.value.trim();
    download.disabled=!owner||selected?.kind!=='search'||selected.status!=='succeeded'||!candidate||!ack.checked
      ||configuration?.items.find(row=>row.provider===selected.snapshot.provider)?.configuration_sha256!==selected.snapshot.provider_configuration_sha256;
    cancel.disabled=!owner||!selected||!['queued','retry_scheduled'].includes(selected.status);
    importAck.disabled=!edit||!state.canEdit||selected?.kind!=='download'||selected.status!=='succeeded'||Boolean(selected.attachment);
    attach.disabled=importAck.disabled||!importAck.checked;
  }
  function render(){const spec=selectedProvider();status.textContent=!configuration?'Chưa đọc cấu hình và lịch sử stock.':spec?.mode==='fixture'?
    'MÔ PHỎNG API stock: không phải media hoặc giấy phép nhận từ nhà cung cấp thật.':`${spec?.provider??''} · ${spec?.status??'NOT_CONFIGURED'} · tư liệu vẫn cần kiểm tra quyền sử dụng.`;
    ackText.textContent=spec?.mode==='fixture'?'Tôi hiểu đây là dữ liệu và media kiểm thử mô phỏng, không phải kết quả stock thật.':'Tôi chọn tìm/tải từ API đã cấu hình và sẽ kiểm tra nguồn, tác giả, giấy phép trước khi sử dụng.';
    jobs.replaceChildren();for(const row of rows){const option=node('option',`${row.kind==='search'?'Tìm':'Tải'} · ${row.snapshot.provider} · ${row.status}${row.attachment?' · đã thêm':''}`);option.value=row.stock_id;jobs.append(option);}jobs.value=selected?.stock_id??'';
    candidates.replaceChildren();for(const item of selected?.result?.candidates??[]){const option=node('option',`${item.creator} · ${item.width??'?'} × ${item.height??'?'} · ${item.license}`);option.value=item.candidate_id;candidates.append(option);}candidates.value=candidate?.candidate_id??'';
    detail.textContent=selected?JSON.stringify({status:selected.status,failure_code:selected.failure_code,provider:selected.snapshot.provider,
      mock:selected.result?.mock??selected.snapshot.provider_mode==='fixture',candidate,asset:selected.result?.asset??null,attachment:selected.attachment,
      actual_provider_calls:selected.result?.actual_provider_calls??null,independent_rights_verification:false},null,2):'Chọn yêu cầu hoặc tư liệu để kiểm tra.';
    preview.replaceChildren();if(selected?.kind==='download'&&selected.status==='succeeded'){const image=selected.result.asset.kind==='image',media=node(image?'img':'video');
      media.src=`/api/projects/${getState().project.id}/stock/${selected.stock_id}/file`;if(image)media.alt='Tư liệu stock đã tải · cần kiểm tra quyền';else{media.controls=true;media.preload='metadata';}
      preview.append(node('p',selected.result.mock?'Media kiểm thử mô phỏng; không phải tư liệu stock thật.':'Xem tư liệu đã tải; giấy phép và quyền bên thứ ba cần kiểm tra.'),media);}
    controls();}
  function sync(){if(context()!==scope){scope=context();serial++;configuration=null;rows=[];cursor=null;selected=null;candidate=null;ack.checked=false;importAck.checked=false;
      provider.replaceChildren();polls=0;clearTimer(timer);timer=null;}render();}
  function validateRow(row,state){if(row?.schema_version!=='native-stock-job-v1'||!ID.test(row.stock_id??'')||row.workspace_id!==state.workspace_id||row.project_id!==state.project.id
    ||!STATES.has(row.status)||!['search','download'].includes(row.kind)||!HASH.test(row.request_fingerprint)||row.publish_enabled!==false||row.automatic_attachment!==false
    ||row.snapshot?.workspace_id!==state.workspace_id||row.snapshot?.project_id!==state.project.id||!['pexels','pixabay'].includes(row.snapshot.provider)
    ||!['fixture','official'].includes(row.snapshot.provider_mode))throw new Error('Yêu cầu stock ngoài không gian hiện tại.');
    if(row.result){const result=row.result;if(row.status!=='succeeded'||result.stock_id!==row.stock_id||result.project_id!==state.project.id||result.workspace_id!==state.workspace_id
      ||result.mock!==(row.snapshot.provider_mode==='fixture')||result.canonical_timeline_mutated!==false||result.automatic_attachment!==false||result.paid_operations!==0
      ||result.real_provider_acceptance_complete!==false||(result.mock&&result.actual_provider_calls!==0)||!HASH.test(row.result_sha256))throw new Error('Kết quả stock không hợp lệ.');
      if(row.kind==='search'){if(!Array.isArray(result.candidates)||result.candidates.length>20)throw new Error('Danh sách stock không hợp lệ.');
        for(const item of result.candidates){if(!CANDIDATE.test(item.candidate_id)||item.provider!==row.snapshot.provider||item.production_eligible!==false
          ||item.semantic_score!==null||item.provenance?.fixture!==result.mock||!HASH.test(result.candidate_sha256?.[item.candidate_id]))throw new Error('Tư liệu stock không hợp lệ.');stockSourceLink(item.source_reference,item.provider);}}
      else if(result.asset?.production_eligible!==false||result.asset.needs_attention!==true||result.asset.rights_status!==(result.mock?'unknown':'licensed')||!HASH.test(result.asset.sha256))throw new Error('Media tải về cần giữ trạng thái kiểm tra.');}
    if(row.attachment&&(row.attachment.project_id!==state.project.id||row.attachment.workspace_id!==state.workspace_id||row.attachment.stock_id!==row.stock_id||row.attachment.rights_independently_verified!==false))throw new Error('Biên nhận thêm tư liệu không hợp lệ.');return row;}
  function choose(row){selected=row;candidate=row?.result?.candidates?.[0]??null;ack.checked=false;importAck.checked=false;polls=0;render();}
  function polling(){clearTimer(timer);timer=null;if(!selected||!['queued','running','retry_scheduled'].includes(selected.status)||polls>=40)return;
    const expected=context(),identity=selected.stock_id;timer=setTimer(async()=>{if(expected!==context())return;polls++;
      await perform(async()=>{const state=getState(),row=validateRow(await api(`/api/projects/${state.project.id}/stock/${identity}`),state);return()=>{rows=rows.map(old=>old.stock_id===identity?row:old);selected=row;candidate=row.result?.candidates?.[0]??null;};});},3000);}
  async function perform(fn){sync();if(blocked())return;const token=++serial,expected=context();working=true;onWorking();controls();
    try{const apply=await fn();if(token===serial&&expected===context())await apply?.();}catch(error){if(token===serial&&expected===context())onMessage(error.message,true);}
    finally{working=false;if(expected!==context())sync();else render();onWorking();polling();}}
  async function load(moreRows=false){const state=getState();if(!state.project)return;return perform(async()=>{
    const [config,page]=await Promise.all([api('/api/stock/providers'),api(`/api/projects/${state.project.id}/stock?limit=25${moreRows&&cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`)]);
    if(config?.schema_version!=='native-stock-providers-v1'||config.workspace_id!==state.workspace_id||config.ui_enablement_supported!==false||config.automatic_attachment!==false
      ||!Array.isArray(config.items)||config.items.length!==2||new Set(config.items.map(item=>item.provider)).size!==2
      ||config.items.some(item=>!['pexels','pixabay'].includes(item.provider)||!['official','fixture'].includes(item.mode)||!['CONFIGURED','NOT_CONFIGURED'].includes(item.status)||(item.status==='CONFIGURED'&&!HASH.test(item.configuration_sha256)))
      ||page?.schema_version!=='native-stock-page-v1'||page.workspace_id!==state.workspace_id||page.project_id!==state.project.id||page.automatic_attachment!==false
      ||!Array.isArray(page.items)||page.items.length>25||(page.next_cursor!==null&&typeof page.next_cursor!=='string'))throw new Error('Cấu hình hoặc lịch sử stock không hợp lệ.');
    const incoming=page.items.map(row=>validateRow(row,state));return()=>{configuration=config;const previous=provider.value;provider.replaceChildren();
      for(const item of config.items){const option=node('option',`${item.provider} · ${item.status}${item.mode==='fixture'?' · MÔ PHỎNG':''}`);option.value=item.provider;provider.append(option);}provider.value=previous||config.items[0].provider;
      rows=moreRows?[...rows,...incoming.filter(row=>!rows.some(old=>old.stock_id===row.stock_id))]:incoming;cursor=page.next_cursor;choose(rows.find(row=>row.stock_id===selected?.stock_id)??rows[0]??null);};});}
  async function execute(action){const state=getState();if(!editable()||!state.project)return;if(action==='import'?!state.canEdit:!state.canManage)return;
    if(action==='search'&&(!ack.checked||!selectedProvider()||!query.value.trim()))return;
    if(action==='download'&&(!ack.checked||!candidate||selected?.status!=='succeeded'))return;
    if(action==='import'&&(!importAck.checked||selected?.kind!=='download'||selected.status!=='succeeded'||selected.attachment))return;
    if(action==='cancel'&&(!selected||!['queued','retry_scheduled'].includes(selected.status)))return;
    const own=selected,chosen=candidate;return perform(async()=>{let path=`/api/projects/${state.project.id}/stock`,request;
      if(action==='search'){const spec=selectedProvider();request={revision:state.project.revision,provider:spec.provider,query:query.value.trim(),media_type:type.value,orientation:orientation.value,limit:5,
        external_acknowledged:spec.mode==='official',fixture_acknowledged:spec.mode==='fixture'};path+='/search';}
      else if(action==='download'){const fixture=own.snapshot.provider_mode==='fixture';request={revision:state.project.revision,search_id:own.stock_id,candidate_id:chosen.candidate_id,
        expected_result_sha256:own.result_sha256,expected_candidate_sha256:own.result.candidate_sha256[chosen.candidate_id],external_acknowledged:!fixture,fixture_acknowledged:fixture};path+='/download';}
      else{path+=`/${own.stock_id}/${action}`;request={expected_fingerprint:own.request_fingerprint};if(action==='import')Object.assign(request,{revision:state.project.revision,expected_asset_sha256:own.result.asset.sha256,acknowledged:true});}
      if(action!=='cancel'){const signature=scope+action+JSON.stringify(request),key=keys.get(signature)??`native-stock-${uuid()}`;keys.set(signature,key);request.request_key=key;}
      const value=await api(path,request);
      if(action==='import'){if(value?.schema_version!=='native-stock-import-v1'||value.project_id!==state.project.id||value.workspace_id!==state.workspace_id||value.stock_id!==own.stock_id
        ||value.asset_sha256!==own.result.asset.sha256||value.revision!==state.project.revision+1||value.approval_invalidated!==true||value.rights_independently_verified!==false||value.external_calls!==0)throw new Error('Biên nhận thêm stock không hợp lệ.');
        return async()=>{await onSaved(value);onMessage('Đã thêm tư liệu; kiểm tra vị trí, quyền sử dụng và duyệt lại dự án.');};}
      const row=validateRow(value,state);return()=>{rows=[row,...rows.filter(old=>old.stock_id!==row.stock_id)];choose(row);onMessage(row.status==='not_configured'?'API stock chưa cấu hình; không tạo tư liệu mẫu thay thế.':'Đã lưu yêu cầu. Theo dõi trạng thái rồi kiểm tra tư liệu trước khi thêm.');};});}
  read.addEventListener('click',()=>load());more.addEventListener('click',()=>load(true));search.addEventListener('click',()=>execute('search'));download.addEventListener('click',()=>execute('download'));
  cancel.addEventListener('click',()=>execute('cancel'));attach.addEventListener('click',()=>execute('import'));
  jobs.addEventListener('change',()=>{choose(rows.find(row=>row.stock_id===jobs.value)??null);polling();});candidates.addEventListener('change',()=>{candidate=selected?.result?.candidates.find(row=>row.candidate_id===candidates.value)??null;render();});
  provider.addEventListener('change',()=>{ack.checked=false;render();});for(const control of [ack,importAck,query])control.addEventListener(control===query?'input':'change',controls);
  sync();return {sync,controls,load,execute,isWorking:()=>working,close:()=>{clearTimer(timer);serial++;}};
}
