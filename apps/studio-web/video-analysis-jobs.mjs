// SQL video queue UI: explicit writes, saved reads and independent human review.
import {audioRole} from './uploaded-audio-review.mjs';
import {isVerifiedVariantSource, verifiedVariantReceipt, loadVariantReceipt} from './verified-variant-source.mjs';
const sha=/^[a-f0-9]{64}$/, id={asset:/^ast_[A-Za-z0-9_-]{4,60}$/, analysis:/^ana_[a-f0-9]{24}$/, job:/^job_analysis_[a-f0-9]{24}$/};
const active=new Set(['queued','running']);
const labels={queued:'Đang chờ phân tích',running:'Đang phân tích video',awaiting_review:'Đã có kết quả · cần kiểm tra lời nói và cảnh',
  failed:'Phân tích bị chặn hoặc thất bại',cancelled:'Đã hủy',needs_attention:'Cần kiểm tra tác vụ · không tự chạy lại'};
const stable=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const demand=(ok,message)=>{if(!ok)throw Error(message);};
const scope=s=>stable([s.workspaceId,s.projectId,s.principal?.subject,s.principal?.token_id,s.principal?.expires_at,audioRole(s)]);
const configuration=(assetId,top)=>({asset_id:assetId,acceptance_operation_id:null,top_highlights:top,silence_threshold_db:-35,
  minimum_silence_duration:.5,padding_before:.08,padding_after:.08,word_timing_policy:'strict_provider_intervals'});
export function videoAnalysisAssets(s){return(s.assets??[]).filter(a=>a.project_id===s.projectId&&a.workspace_id===s.workspaceId
  &&id.asset.test(a.asset_id)&&a.asset_class==='source'&&a.kind==='video'&&a.content_type==='video/mp4'
  &&sha.test(a.checksum_sha256)&&Number.isSafeInteger(a.size_bytes)&&a.size_bytes>0&&a.size_bytes<=2*1024**3
  &&(a.provenance?.source_type==='user_upload'||isVerifiedVariantSource(a,s))&&a.provenance?.media_metadata?.media_kind==='video'
  &&Number.isFinite(a.provenance.media_metadata.duration_seconds)&&a.provenance.media_metadata.duration_seconds>0
  &&a.provenance.media_metadata.duration_seconds<=1800);}
function guard(s){demand(s.projectId&&s.workspaceId&&['editor','reviewer','owner'].includes(audioRole(s)),
  'Cần quyền biên tập để gửi hoặc hủy phân tích.');demand(!s.busy&&!s.dirty,'Lưu thay đổi đang sửa và chờ dự án tải xong trước khi thao tác.');}
export function videoAnalysisPayload(s,assetId,top,key){guard(s);
  const a=videoAnalysisAssets(s).find(a=>a.asset_id===assetId);
  demand(a&&[3,5].includes(top)&&typeof key==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$/.test(key),'Chọn video còn hợp lệ và số đoạn nổi bật.');
  if(a.provenance.source_type==='verified_variant_derivative')verifiedVariantReceipt(s,a);
  return{configuration:configuration(assetId,top),source_sha256:a.checksum_sha256,idempotency_key:key};}
export function validateVideoAnalysisJob(v,s){const j=v?.job,a=v?.analysis,asset=videoAnalysisAssets(s).find(x=>x.asset_id===a?.asset_id);
  demand(v?.schema_version==='auto-edit-analysis-job.v1'&&v.human_review_required===true&&v.source_media_mutated===false
    &&v.timeline_mutated===false&&v.publishing_enabled===false&&j&&a&&asset&&id.job.test(j.job_id)&&id.analysis.test(a.analysis_id)
    &&j.project_id===s.projectId&&j.workspace_id===s.workspaceId&&a.project_id===s.projectId&&a.workspace_id===s.workspaceId
    &&j.request?.kind==='auto_edit_analysis'&&j.request.analysis_id===a.analysis_id&&j.request.source_sha256===v.source_sha256
    &&sha.test(j.request.provider_binding_sha256)&&sha.test(v.custody_sha256)&&v.source_sha256===asset.checksum_sha256
    &&a.configuration?.asset_id===asset.asset_id&&Number.isInteger(j.progress)&&j.progress>=0&&j.progress<=100
    &&Object.hasOwn(labels,j.status)&&['pending','analyzing','succeeded','failed'].includes(a.status)
    &&(j.status!=='awaiting_review'||a.status==='succeeded'),'Kết quả phân tích không khớp nguồn hoặc dự án hiện tại.');
  if(asset.provenance.source_type==='verified_variant_derivative')verifiedVariantReceipt(s,asset);
  return v;}
export function videoReviewSelection(s,v){validateVideoAnalysisJob(v,s);demand(v.job.status==='awaiting_review','Chưa có kết quả để kiểm tra.');
  return{workspace_id:s.workspaceId,project_id:s.projectId,analysis_id:v.analysis.analysis_id,asset_id:v.analysis.asset_id,source_sha256:v.source_sha256};}
export function selectedVideoReviewAnalysis(s,selection,fallback=null){
  if(!selection||selection.workspace_id!==s.workspaceId||selection.project_id!==s.projectId)return fallback;
  const asset=videoAnalysisAssets(s).find(a=>a.asset_id===selection.asset_id&&a.checksum_sha256===selection.source_sha256);
  if(!asset)return null;
  return(s.analyses??[]).find(a=>a.analysis_id===selection.analysis_id&&a.asset_id===selection.asset_id
    &&a.workspace_id===s.workspaceId&&a.project_id===s.projectId&&a.status==='succeeded')??null;
}
export function initializeVideoAnalysisJobs({root,api,getState,onMessage=()=>{},onReview=async()=>{},dom=globalThis.document,
  storage=globalThis.sessionStorage,newKey=()=>globalThis.crypto.randomUUID(),setTimer=globalThis.setTimeout,clearTimer=globalThis.clearTimeout,
  cryptoImpl=globalThis.crypto}){
  const liveState=getState;let variantReceipts=[];
  getState=()=>({...liveState(),verifiedVariantReceipts:variantReceipts});
  let context=scope(getState()),records=[],selected='',working=false,pending=null,timer=null,disposed=false,epoch=0;
  const make=(tag,name,text)=>{const e=dom.createElement(tag);e.setAttribute('data-video-job-'+name,'');if(text)e.textContent=text;return e;};
  const title=make('h3','title','Phân tích video'),source=make('select','source'),top=make('select','top'),saved=make('select','saved');
  const text=make('p','status','Chọn video để gửi phân tích. Kết quả cần kiểm tra trước khi đưa vào timeline.');text.setAttribute('role','status');
  const buttons={};for(const[name,label]of[['start','Gửi phân tích'],['read','Xem tác vụ đã lưu'],['cancel','Hủy tác vụ'],
    ['retry','Gửi lại yêu cầu cũ'],['review','Xem kết quả để kiểm tra']]){buttons[name]=make('button',name,label);buttons[name].type='button';}
  const wrap=(label,element)=>{const e=dom.createElement('label');e.textContent=label;e.append(element);return e;};
  for(const value of[3,5]){const e=dom.createElement('option');e.value=String(value);e.textContent=`${value} đoạn nổi bật`;top.append(e);}top.value='3';
  root.append(title,wrap('Video nguồn',source),wrap('Đoạn nổi bật',top),buttons.start,buttons.read,wrap('Tác vụ đã gửi',saved),
    text,buttons.cancel,buttons.retry,buttons.review);
  const endpoint=s=>`/api/v1/projects/${encodeURIComponent(s.projectId)}/analysis-jobs`;
  const key=s=>'npd-sql-video-pending:'+scope(s);
  const blockedSource=assetId=>records.some(v=>v.analysis.asset_id===assetId
    &&(active.has(v.job.status)||v.job.status==='needs_attention'));
  function stop(){if(timer!==null)clearTimer(timer);timer=null;}
  function sync(){const s=getState(),next=scope(s);if(next!==context){stop();epoch++;context=next;records=[];selected='';pending=null;
      variantReceipts=[];
      text.textContent='Dự án hoặc phiên truy cập đã đổi. Xem lại tác vụ đã lưu.';}
    const assets=videoAnalysisAssets(s),previous=source.value;
    source.replaceChildren(...assets.map(a=>{const e=dom.createElement('option');e.value=a.asset_id;e.textContent=a.filename;return e;}));
    source.value=assets.some(a=>a.asset_id===previous)?previous:assets[0]?.asset_id??'';
    saved.replaceChildren(...records.map(v=>{const e=dom.createElement('option');e.value=v.job.job_id;
      const name=assets.find(a=>a.asset_id===v.analysis.asset_id)?.filename??'Video nguồn';
      e.textContent=`${name} · ${labels[v.job.status]} · ${v.job.progress}%`;return e;}));saved.value=selected;
    const value=records.find(v=>v.job.job_id===selected);let writable=true;try{guard(s);}catch{writable=false;}
    source.disabled=top.disabled=working||!writable||!!pending; saved.disabled=working||!!pending;
    buttons.start.disabled=working||!writable||!!pending||!assets.length||blockedSource(source.value);
    buttons.start.textContent=assets.find(a=>a.asset_id===source.value)?.provenance.source_type==='verified_variant_derivative'
      ?'Gửi phân tích mới cho bản sao đã chọn':'Gửi phân tích';
    buttons.read.disabled=working||!s.projectId||!s.workspaceId||s.busy;
    buttons.cancel.disabled=working||!writable||!!pending||!active.has(value?.job.status);
    buttons.retry.disabled=working||!writable||!pending;
    buttons.review.disabled=working||!writable||!!pending||value?.job.status!=='awaiting_review';
    // A timer may have fired while another Studio operation held the busy
    // guard. Resume the saved read when that guard clears; never resubmit.
    if(!disposed&&!working&&!s.busy&&!pending&&timer===null&&active.has(value?.job.status))schedule();
  }
  function restore(s){const raw=storage?.getItem(key(s));if(!raw)return;let p;
    try{p=JSON.parse(raw);demand(p.schema_version==='sql-video-pending.v1'&&p.scope===scope(s)&&['create','cancel'].includes(p.kind),'');
      if(p.kind==='create')demand(stable(videoAnalysisPayload(s,p.body.configuration.asset_id,p.body.configuration.top_highlights,p.body.idempotency_key))===stable(p.body),'');
      else demand(id.job.test(p.job_id)&&stable(p.body)==='{}','');
    }catch{throw Error('Yêu cầu cũ chưa đối chiếu được. Giữ dữ liệu phiên và xem tác vụ đã lưu.');}pending=p;
  }
  function persist(p){demand(storage,'Trình duyệt cần lưu khóa yêu cầu trước khi gửi.');
    try{storage.setItem(key(getState()),JSON.stringify(p));demand(storage.getItem(key(getState()))===JSON.stringify(p),'');}
    catch{throw Error('Chưa lưu được khóa yêu cầu. Chưa gửi phân tích.');}pending=p;}
  function forget(s){storage?.removeItem(key(s));pending=null;}
  function adopt(v,s,expectedId=null){validateVideoAnalysisJob(v,s);demand(!expectedId||v.job.job_id===expectedId,'Tác vụ trả về không đúng yêu cầu.');
    records=[v,...records.filter(x=>x.job.job_id!==v.job.job_id)];selected=v.job.job_id;
    text.textContent=`${labels[v.job.status]} · ${v.job.progress}%${v.analysis.provenance?.fixture?' · Dữ liệu mô phỏng':''}`;
  }
  function schedule(){stop();const value=records.find(v=>v.job.job_id===selected);if(!disposed&&!working&&!getState().busy&&!pending&&active.has(value?.job.status))
    timer=setTimer(()=>readSelected().catch(e=>onMessage(e.message,true)),1200);}
  async function readSelected(){stop();const s=getState(),bound=scope(s),jobId=selected;if(!jobId||working||disposed||s.busy)return;
    const ticket=++epoch,v=await api(`${endpoint(s)}/${encodeURIComponent(jobId)}`);if(disposed||ticket!==epoch||scope(getState())!==bound)return;
    adopt(v,getState(),jobId);sync();}
  async function read(){stop();const s=getState(),bound=scope(s),ticket=++epoch;demand(s.projectId&&s.workspaceId&&!s.busy,'Chọn dự án và chờ tải xong.');
    const values=await api(endpoint(s));if(disposed||ticket!==epoch||scope(getState())!==bound)return;
    await loadSourceReceipts(s);if(disposed||ticket!==epoch||scope(getState())!==bound)return;
    demand(Array.isArray(values)&&values.length<=1000,'Danh sách tác vụ chưa có giới hạn hợp lệ.');
    values.forEach(v=>validateVideoAnalysisJob(v,getState()));demand(new Set(values.map(v=>v.job.job_id)).size===values.length,'Danh sách tác vụ trùng định danh.');
    records=values;selected=values.some(v=>v.job.job_id===selected)?selected:values.at(-1)?.job.job_id??'';
    if(!pending)restore(s);
    // A lost create response has no public request-key receipt. A read cannot
    // prove that an older same-source job is that exact write: retain its key.
    if(pending?.kind==='cancel'){const v=records.find(v=>v.job.job_id===pending.job_id);if(v&&!active.has(v.job.status))forget(s);}
    const v=records.find(v=>v.job.job_id===selected);
    text.textContent=pending?'Chưa rõ phản hồi yêu cầu cũ. Xem tác vụ hoặc gửi lại đúng yêu cầu cũ; không tạo yêu cầu mới.':
      v?`${labels[v.job.status]} · ${v.job.progress}%`:videoAnalysisAssets(getState()).some(a=>a.provenance.source_type==='verified_variant_derivative')
        ?'Cảnh và lời đã nhập vẫn thuộc timeline hiện tại. Chỉ gửi phân tích mới khi bạn chọn rõ thao tác này.'
        :'Chưa có tác vụ phân tích đã lưu.';
  }
  async function loadSourceReceipts(s,assetId=null){const next=[];
    for(const asset of videoAnalysisAssets(s)){
      if(asset.provenance.source_type!=='verified_variant_derivative'||assetId&&asset.asset_id!==assetId)continue;
      next.push(await loadVariantReceipt(s,asset,api,getState,cryptoImpl));
    }
    variantReceipts=assetId?[...variantReceipts.filter(v=>!next.some(n=>n.fingerprint===v.fingerprint)),...next]:next;
  }
  async function send(p){const s=getState(),bound=scope(s),ticket=++epoch;guard(s);
    if(p.kind==='create')demand(stable(videoAnalysisPayload(s,p.body.configuration.asset_id,p.body.configuration.top_highlights,p.body.idempotency_key))===stable(p.body),
      'Video hoặc cấu hình đã đổi; giữ yêu cầu cũ để đối chiếu.');
    const v=await api(p.kind==='create'?endpoint(s):`${endpoint(s)}/${encodeURIComponent(p.job_id)}/cancel`,{method:'POST',body:JSON.stringify(p.body)});
    if(disposed||ticket!==epoch||scope(getState())!==bound)return;
    validateVideoAnalysisJob(v,getState());
    if(p.kind==='create')demand(v.source_sha256===p.body.source_sha256&&stable(v.analysis.configuration)===stable(p.body.configuration),
      'Kết quả chưa khớp yêu cầu phân tích đang giữ.');
    else demand(v.job.job_id===p.job_id,'Kết quả hủy chưa khớp tác vụ.');
    adopt(v,s);forget(s);
  }
  async function run(fn){if(working||disposed)return;working=true;stop();sync();
    try{await fn();}catch(e){text.textContent=pending?'Chưa rõ kết quả yêu cầu. Khóa yêu cầu vẫn được giữ; xem lại trước khi tiếp tục.':'Chưa thực hiện được thao tác.';
      onMessage(e.message,true);}finally{working=false;sync();}}
  buttons.start.addEventListener('click',()=>run(async()=>{const s=getState(),bound=scope(s),startEpoch=epoch;guard(s);restore(s);demand(!pending,'Đối chiếu yêu cầu đang giữ trước khi gửi mới.');
    demand(!blockedSource(source.value),'Video đang phân tích hoặc có tác vụ cần đối chiếu. Kiểm tra tác vụ đã lưu trước khi gửi mới.');
    const assetId=source.value,topCount=Number(top.value),assetBinding=stable(videoAnalysisAssets(s).find(a=>a.asset_id===assetId));
    await loadSourceReceipts(s,assetId);demand(!disposed&&epoch===startEpoch&&scope(getState())===bound,'Ngữ cảnh đã đổi trước khi gửi phân tích.');
    demand(source.value===assetId&&Number(top.value)===topCount
      &&stable(videoAnalysisAssets(getState()).find(a=>a.asset_id===assetId))===assetBinding,'Video hoặc lựa chọn đã đổi trong lúc đọc biên nhận.');
    const body=videoAnalysisPayload(getState(),assetId,topCount,newKey());persist({schema_version:'sql-video-pending.v1',scope:bound,kind:'create',body});await send(pending);}));
  buttons.retry.addEventListener('click',()=>run(async()=>{const s=getState();guard(s);if(!pending)restore(s);demand(pending,'Chưa có yêu cầu cũ để gửi lại.');await send(pending);}));
  buttons.cancel.addEventListener('click',()=>run(async()=>{const s=getState();guard(s);restore(s);demand(!pending,'Đối chiếu yêu cầu cũ trước khi hủy.');
    const v=records.find(v=>v.job.job_id===selected);validateVideoAnalysisJob(v,s);demand(active.has(v.job.status),'Tác vụ đã kết thúc.');
    persist({schema_version:'sql-video-pending.v1',scope:scope(s),kind:'cancel',job_id:v.job.job_id,body:{}});await send(pending);}));
  buttons.read.addEventListener('click',()=>run(read));
  buttons.review.addEventListener('click',()=>run(async()=>{const s=getState();guard(s);const v=records.find(v=>v.job.job_id===selected);
    validateVideoAnalysisJob(v,s);demand(!pending&&v.job.status==='awaiting_review','Chưa có kết quả để kiểm tra.');await onReview(structuredClone(v));}));
  source.addEventListener('change',sync);top.addEventListener('change',sync);
  saved.addEventListener('change',()=>{if(working||pending)return;epoch++;selected=saved.value;const v=records.find(x=>x.job.job_id===selected);
    if(v)text.textContent=`${labels[v.job.status]} · ${v.job.progress}%`;sync();schedule();});
  sync();return{sync,reload:()=>run(read),isPending:()=>!!pending,isWorking:()=>working,dispose:()=>{disposed=true;epoch++;stop();variantReceipts=[];}};
}
