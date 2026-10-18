import {initializeVoiceBrowser,usableVoice} from './voice-browser.mjs';
import {verifyDramaSaveReceipt,stableDramaJSON} from './drama-script-save.mjs';
const ACTIVE=new Set(['queued','running','retrying']);
export const isDramaProject=project=>project?.document?.production_workflow?.kind==='drama';
export const dramaSteps=[['script','Kịch bản'],['voices','Nhân vật & giọng'],['scenes','Hình ảnh & cảnh'],['preview','Dựng & xem thử'],['export','Xuất video']];
export function dramaProgress(project){
  const d=project?.document??{},c=d.drama_casting?.configuration,active=(c?.lines??[]).filter(v=>v.enabled&&(c.characters.find(x=>x.character_id===v.character_id)?.role!=='narrator'||c.narrator_enabled));
  const uncast=[...new Set(active.filter(v=>!c.casting.some(x=>x.character_id===v.character_id)).map(v=>c.characters.find(x=>x.character_id===v.character_id)?.name??'Nhân vật'))];
  const shots=project?.shot_timeline?.shots??[];
  return {script:Boolean(d.drama_script?.raw_text?.trim())&&d.drama_script?.input_mode!=='idea',confirmed:d.drama_script?.characters_confirmed===true,uncast,
    voiceCount:new Set(c?.casting.map(v=>v.voice_id)??[]).size,characterCount:c?.characters.filter(v=>v.role!=='narrator').length??0,
    scenes:shots.length>0&&shots.every(v=>v.asset_id),audio:Boolean(d.prepared_narration)&&project?.drama_voice_binding?.current!==false,active:(project?.jobs??[]).some(v=>ACTIVE.has(v.status))};
}
export function validateDramaScriptResponse(value,project,request){
  if(value?.project_id!==project.id||value.revision!==request.revision+1||value.provider_calls!==0||value.human_approval_granted!==false)throw Error('Chưa xác nhận lưu kịch bản. Giữ nội dung và thử lại đúng yêu cầu.');
  return value;
}
export function initializeDramaWorkflow({api,getState,onCreated,onSaved,onDirty,onWorking,onMessage,showStage,drama,narration,dom=globalThis.document,storage=globalThis.localStorage}){
  const node=(tag,text,parent,attrs={})=>{const n=dom.createElement(tag);if(text!==null)n.textContent=text;for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);parent?.append(n);return n;};
  const button=(text,parent,fn)=>{const n=node('button',text,parent,{type:'button',class:'secondary','data-workspace-control':''});n.addEventListener('click',()=>void fn());return n;};
  const root=node('section',null,null,{id:'drama-workflow',class:'drama-workflow'});dom.querySelector('.stage-navigation').before(root);
  const chooser=node('section',null,root,{class:'card workflow-entry','aria-label':'Chọn loại video'});node('h2','Bạn muốn tạo video nào?',chooser);node('p','Chọn quy trình sản xuất. Hồ sơ nội dung, thương hiệu và định dạng xuất là các lựa chọn riêng.',chooser,{class:'hint'});
  const cards=node('div',null,chooser,{class:'workflow-cards'}),creation=node('section',null,chooser,{class:'workflow-create-form'});creation.hidden=true;
  const creationTitle=node('h3','',creation),filmName=node('input',null,node('label','Tên phim / video',creation),{maxlength:'150',placeholder:'Nhập tên của bạn','data-workspace-control':''});
  const format=node('select',null,node('label','Định dạng xuất ban đầu',creation),{'data-workspace-control':''});
  for(const [value,label] of [['9:16','Dọc · 1080×1920'],['16:9','Ngang · 1920×1080'],['1:1','Vuông · 1080×1080'],['4:5','Feed · 1080×1350']])node('option',label,format,{value});
  const create=button('Tạo phim',creation,createProject),createHint=node('p','Bạn có thể tạo bản nháp trước khi có kịch bản hoặc tư liệu.',creation,{class:'hint'});
  const flow=node('section',null,root,{class:'drama-flow'});flow.hidden=true;
  const nav=node('nav',null,flow,{'aria-label':'Năm bước làm phim Drama',class:'drama-steps'}),stepButtons=new Map();
  for(const [i,[id,label]]of dramaSteps.entries()){const b=button(`${i+1}. ${label}`,nav,()=>go(id));b.dataset.dramaStep=id;stepButtons.set(id,b);}
  const goal=node('p','',flow,{class:'drama-goal'}),state=node('p','',flow,{role:'status','aria-live':'polite',class:'hint'});
  const scriptPane=node('section',null,flow,{class:'card drama-script-pane'});node('h2','Viết câu chuyện và lời thoại',scriptPane);
  const inputMode=node('select',null,node('label','Bạn đang nhập',scriptPane),{'data-workspace-control':''});node('option','Kịch bản có lời thoại',inputMode,{value:'script'});node('option','Ý tưởng nháp',inputMode,{value:'idea'});inputMode.value='script';
  const ideaHint=node('p','Bạn có thể lưu ý tưởng rồi chọn “Kịch bản có lời thoại” để phát triển thành câu chuyện. Tạo kịch bản Drama bằng AI chưa khả dụng trong runtime này.',scriptPane,{class:'hint'});ideaHint.hidden=true;
  node('p','Mỗi câu ghi Tên nhân vật: lời thoại. Đặt mô tả hành động trong ngoặc hoặc bắt đầu bằng “Hành động:”. Hành động chỉ dùng cho hình ảnh, không được đọc thành lời.',scriptPane,{class:'hint'});
  const text=node('textarea',null,node('label','Kịch bản của phim',scriptPane),{rows:'9',maxlength:'20000','data-workspace-control':'',placeholder:'CẢNH 1: Chiếc ô\n(An đặt chiếc ô lên bàn.)\nAn: Mình tìm thấy chiếc ô của bạn rồi.\nBình: Cảm ơn, mình đã tìm nó cả buổi.'});
  const seriesInput=node('input',null,node('label','Series (tùy chọn)',scriptPane),{maxlength:'100','data-workspace-control':''}),episodeInput=node('input',null,node('label','Tập (tùy chọn)',scriptPane),{maxlength:'100','data-workspace-control':''});
  const tools=node('div',null,scriptPane,{class:'actions'}),save=button('Lưu nháp',tools,()=>saveScript(false)),example=button('Dùng kịch bản ví dụ nguyên bản',tools,()=>{text.value='CẢNH 1: Chiếc ô\n(An đặt chiếc ô lên bàn.)\nAn: Mình tìm thấy chiếc ô của bạn rồi.\nBình: Cảm ơn, mình đã tìm nó cả buổi.';changed();});
  node('p','Ví dụ chỉ là nội dung viết sẵn để thử thao tác, chưa có tư liệu hay phê duyệt. Bạn có thể thay bằng câu chuyện của mình.',scriptPane,{class:'hint'});
  const saved=node('p','Đã lưu',scriptPane,{role:'status','aria-live':'polite'});
  const recoveryTools=node('div',null,scriptPane,{class:'actions'});
  button('Sao chép bản đang nhập',recoveryTools,async()=>{try{if(!globalThis.navigator?.clipboard?.writeText)throw Error();await globalThis.navigator.clipboard.writeText(text.value);onMessage('Đã sao chép bản đang nhập.');}catch{text.focus();text.select?.();onMessage('Bản đang nhập đã được chọn. Nhấn Ctrl+C để sao chép; nội dung chưa bị thay thế.');}});
  const viewSaved=button('Xem bản đã lưu',recoveryTools,()=>readServerSnapshot());
  const comparison=node('section',null,scriptPane,{class:'card','aria-label':'Đối chiếu kịch bản'});comparison.hidden=true;
  const comparisonStatus=node('p','',comparison,{role:'status'});
  node('p','Đối chiếu bản đã lưu bên dưới với ô đang nhập phía trên. Bạn có thể sửa hoặc sao chép phần muốn giữ trước khi chọn mốc lưu; hệ thống không tự ghi đè.',comparison,{class:'hint'});
  const serverText=node('textarea',null,node('label','Kịch bản đã lưu trên máy',comparison),{rows:'7',readonly:'', 'aria-readonly':'true'});
  const rebase=button('Giữ bản đang nhập · dùng phiên bản này làm mốc lưu',comparison,()=>adoptReviewedSnapshot());
  const voicePane=node('section',null,flow,{class:'drama-voices-pane'}),confirmCard=node('section',null,voicePane,{class:'card'});node('h2','Xác nhận người nói',confirmCard);
  const characterList=node('div',null,confirmCard),confirm=button('Xác nhận nhân vật & tạo phân cảnh nháp',confirmCard,()=>saveScript(true));
  node('p','Xác nhận danh sách không phải duyệt kịch bản hoặc chất lượng giọng. Người kể mặc định tắt; nhân vật không có thoại không bắt buộc có giọng.',confirmCard,{class:'hint'});
  const voiceSlot=node('div',null,voicePane),previewTools=node('section',null,null,{class:'card drama-preview-tools'});
  node('h2','Chuẩn bị lời thoại rồi xem thử',previewTools);node('p','Kiểm tra phân vai, duyệt nội dung tạo thoại, nghe audio và áp dụng thời lượng đã đo. Sau đó tạo xem thử và duyệt đúng phiên bản trước khi tạo video cuối.',previewTools,{class:'hint'});
  const openAudio=button('Kiểm tra phân vai đã lưu',previewTools,async()=>{if(!dramaProgress(current()).audio&&await drama?.check()===false)return;const p=dom.getElementById('native-narration-panel');if(p){p.open=true;await narration?.load();p.scrollIntoView({block:'start',behavior:'smooth'});}});
  const approvalCard=node('section',null,null,{class:'card drama-final-approval'});node('h2','Duyệt bản xem thử có tiếng',approvalCard);node('p','Xem và nghe video đúng phiên bản trước khi xác nhận. Thay đổi lời thoại, giọng, hình ảnh hoặc cách dựng sẽ cần duyệt lại.',approvalCard,{class:'hint'});
  const footer=node('div',null,flow,{class:'drama-next-actions'}),back=button('← Quay lại',footer,()=>go(dramaSteps[Math.max(0,dramaSteps.findIndex(v=>v[0]===step)-1)][0])),next=button('Tiếp tục →',footer,continueStep);next.classList.add('primary');
  const confirmHere=button('Xác nhận người nói',footer,()=>saveScript(true)),fixVoice=button('Chọn giọng còn thiếu',footer,()=>drama?.focusMissing?.());confirmHere.hidden=fixVoice.hidden=true;
  const settings=node('section',null,root,{class:'card studio-settings'});settings.hidden=true;node('h2','Cài đặt',settings);node('p','Các chức năng hoạt động trên máy và cấu hình dùng chung.',settings);
  const about=node('details',null,settings);node('summary','Thông tin ứng dụng',about);const aboutText=node('p','Đang đọc phiên bản…',about);
  const advanced=node('details',null,settings);node('summary','Kết nối & nâng cao',advanced);node('a','Cấu hình nhận diện lời nói',advanced,{href:'/settings/assemblyai'});
  const voicesPage=node('section',null,root,{class:'card studio-voices-page'});voicesPage.hidden=true;node('h2','Thư viện giọng',voicesPage);node('p','Nghe các preset local đã cài. Chọn giọng cho vai trong bước Nhân vật & giọng của từng phim. Mở trang này không tạo audio.',voicesPage,{class:'hint'});
  const voicePageCards=node('div',null,voicesPage);let globalVoiceBrowser=null;
  const importVoices=button('Nạp các giọng local đã cài',voicesPage,async()=>{try{await api('/api/voice-library/import-installed',{method:'POST',body:JSON.stringify({acknowledged:true})});await loadGlobalVoices();}catch(error){onMessage(error.message,true);}});importVoices.hidden=true;
  async function loadGlobalVoices(){const [library,presets]=await Promise.all([api('/api/voice-library'),api('/api/voice-library/presets')]);if(!Array.isArray(library?.items)||!Array.isArray(presets?.voices))throw Error('Chưa đọc được thư viện giọng.');globalVoiceBrowser?.dispose();globalVoiceBrowser=initializeVoiceBrowser({root:voicePageCards,api,voices:library.items.filter(usableVoice),catalog:presets,dom,canEdit:()=>getState().canEdit!==false&&!getState().busy,onMessage});importVoices.hidden=presets.voices.every(v=>library.items.some(x=>x.definition.provider_voice_id===v.provider_voice_id&&x.definition.rights_status==='source_licensed'));}
  let kind=null,step='script',binding=null,scriptDirty=false,working=false,pending=null,pendingResult=null,timer=null,assignments={},characterNotes={},audioProject=null,lastPrepared=null;
  let scopeKey=null,boundProject=null,conflict=null;const localDrafts=new Map();
  const homes=new Map();
  function moveHere(element,parent){if(element&&element.parentNode!==parent){if(!homes.has(element))homes.set(element,{parent:element.parentNode,next:element.nextSibling});parent.append(element);}}
  function restoreHomes(){for(const[element,home]of homes){if(element.parentNode!==home.parent&&home.parent){if(home.parent.insertBefore)home.parent.insertBefore(element,home.next?.parentNode===home.parent?home.next:null);else home.parent.append(element);}}}
  const buffer=()=>({text:text.value,input_mode:inputMode.value,narrator_enabled:boundProject?.document.drama_casting?.configuration.narrator_enabled??false,speaker_assignments:assignments,character_notes:characterNotes,series:seriesInput.value.trim()||null,episode:episodeInput.value.trim()||null});
  const sameBuffer=request=>stableDramaJSON(buffer())===stableDramaJSON(Object.fromEntries(Object.keys(buffer()).map(key=>[key,request[key]])));
  const current=()=>getState().project,blocked=(allowCasting=false)=>{const s=getState();return working||s.busy||dramaProgress(s.project).active||s.project?.archived||s.canEdit===false||(s.dirty&&!['drama-script','drama-both',...(allowCasting?['drama']:[])].includes(s.dirtyPart));};
  const scope=()=>({project_id:current()?.id,workspace_id:getState().workspace_id??'wsp_native_local'});
  const keyFor=value=>value.project_id?'vf-drama-script-draft:v1:'+encodeURIComponent(value.workspace_id)+':'+value.project_id:null;
  const sameScope=value=>keyFor(scope())===keyFor(value);
  function persist(){if(!scopeKey)return;const value={schema:'drama-local-draft.v1',buffer:structuredClone(buffer()),dirty:scriptDirty,pending,pendingResult};if(scriptDirty||pending)localDrafts.set(scopeKey,value);else localDrafts.delete(scopeKey);try{if(!scriptDirty&&!pending){storage.removeItem?.(scopeKey);return;}storage.setItem(scopeKey,JSON.stringify(value));}catch{}}
  function rememberLate(value,result){const key=keyFor(value);try{const draft=localDrafts.get(key)??JSON.parse(storage.getItem(key));if(draft?.pending?.request_key===value.request.request_key){const updated={...draft,pendingResult:result};localDrafts.set(key,updated);storage.setItem(key,JSON.stringify(updated));}}catch{}}
  function fill(value){text.value=value.text??'';inputMode.value=value.input_mode??'script';seriesInput.value=value.series??'';episodeInput.value=value.episode??'';assignments=structuredClone(value.speaker_assignments??{});characterNotes=structuredClone(value.character_notes??{});ideaHint.hidden=inputMode.value!=='idea';}
  function showConflict(project,message='Dự án có phiên bản mới hơn. Nội dung đang nhập chưa bị thay thế.'){
    conflict=project;comparison.hidden=false;serverText.value=project?.document.drama_script?.raw_text??'';comparisonStatus.textContent=message+' · Bản đã lưu: phiên bản '+project.revision;
    scriptDirty=true;onDirty(true);saved.textContent='Cần đối chiếu · bản đang nhập được giữ';persist();controls();
  }
  async function readServerSnapshot(){const selected=scope();if(!selected.project_id||working)return;try{const latest=await api(`/api/projects/${selected.project_id}`);if(!sameScope(selected))return;conflict=latest;comparison.hidden=false;serverText.value=latest.document.drama_script?.raw_text??'';comparisonStatus.textContent=`Bản đã lưu: phiên bản ${latest.revision}. Nội dung đang nhập chưa bị thay thế.`;controls();}catch(error){if(sameScope(selected))onMessage(error.message,true);}}
  async function adoptReviewedSnapshot(){if(!conflict||pending||blocked())return;const selected=scope(),snapshot=conflict;try{working=true;onWorking(true);controls();const value=await onSaved({...selected,kind:'reviewed-server',snapshot});if(!sameScope(selected))return;if(value?.status!=='rebased'){if(value?.project)showConflict(value.project);return;}conflict=null;comparison.hidden=true;scriptDirty=true;onDirty(true);saved.textContent='Đã đối chiếu · bản đang nhập chưa lưu';persist();onMessage('Đã chọn mốc lưu sau đối chiếu. Bấm Lưu nháp để lưu nội dung đang nhập; chưa có phê duyệt video.');}catch(error){if(sameScope(selected))onMessage(error.message,true);}finally{working=false;onWorking(false);controls();}}
  function changed(){scriptDirty=true;onDirty(true);saved.textContent='Chưa lưu';persist();clearTimeout(timer);timer=setTimeout(()=>{if(scriptDirty&&!pending&&!conflict&&!blocked())void saveScript(false);},1800);controls();}
  text.addEventListener('input',changed);
  inputMode.addEventListener('change',()=>{ideaHint.hidden=inputMode.value!=='idea';changed();});
  seriesInput.addEventListener('input',changed);episodeInput.addEventListener('input',changed);
  async function createProject(){if(working)return;try{if(!filmName.value.trim())throw Error('Nhập tên phim trước khi bắt đầu.');working=true;onWorking(true);controls();
      const value=await api('/api/projects',{name:filmName.value.trim(),prompt:'',input_kind:kind==='source'?'media':'script',workflow_kind:kind,output_format:format.value});
      if(!/^[a-f0-9]{32}$/.test(value?.id??'')||value.document?.production_workflow?.kind!==kind)throw Error('Chưa xác nhận tạo dự án; kiểm tra Dự án của tôi trước khi thử lại.');
      await onCreated(value);kind=null;onMessage('Đã tạo bản nháp. Nhập kịch bản và xác nhận nhân vật để tiếp tục.');
    }catch(error){onMessage(error.message,true);}finally{working=false;onWorking(false);sync();}}
  async function saveScript(confirmCharacters){
    if(working||!current()||blocked(confirmCharacters)||(conflict&&!pending)||(!scriptDirty&&!pending&&!confirmCharacters))return;const project=current(),selected=scope();
    clearTimeout(timer);
    try{
      const request=pending??structuredClone({revision:project.revision,request_key:globalThis.crypto.randomUUID(),...buffer(),confirm_characters:confirmCharacters});
      pending=request;working=true;onWorking(true);saved.textContent='Đang lưu…';persist();controls();
      const result=validateDramaScriptResponse(pendingResult??await api(`/api/projects/${project.id}/drama-script`,request),project,request);
      await verifyDramaSaveReceipt(result,{...selected,request});
      if(!sameScope(selected)){rememberLate({...selected,request},result);return;}
      pendingResult=result;persist();
      const loaded=await onSaved({...selected,kind:'saved',request,result});
      if(!sameScope(selected))return;
      if(loaded?.status==='newer'){pending=null;pendingResult=null;showConflict(loaded.project,'Lần lưu của bạn đã thành công; sau đó dự án có phiên bản mới hơn. Nội dung đang nhập chưa bị thay thế.');return;}
      if(loaded?.status!=='saved')throw Error('Chưa đối chiếu được trạng thái lưu. Giữ bản đang nhập và kiểm tra lại yêu cầu cũ.');
      const newerBuffer=!sameBuffer(request);pending=null;pendingResult=null;conflict=null;comparison.hidden=true;
      if(newerBuffer){scriptDirty=true;onDirty(true);saved.textContent='Đã đối chiếu lần lưu trước · nội dung mới đang sửa chưa lưu';onMessage('Đã giữ nội dung mới đang sửa. Bấm Lưu nháp để lưu bản này.');return;}
      scriptDirty=false;onDirty(false);saved.textContent='Đã lưu';persist();binding=null;sync();if(request.confirm_characters)go('voices');
      onMessage(request.confirm_characters?'Đã xác nhận nhân vật và tạo cảnh nháp. Chọn giọng riêng cho từng người; chưa tạo audio hoặc phê duyệt video.':'Đã lưu nháp kịch bản.');
    }catch(error){if(!sameScope(selected))return;
      const rejected=!pendingResult&&[400,401,403,404,409,422].includes(error.status)&&typeof error.code==='string';
      if(rejected){pending=null;pendingResult=null;}
      scriptDirty=true;onDirty(true);saved.textContent=pendingResult?'Đã nhận biên nhận lưu · cần đối chiếu trạng thái':pending?'Chưa rõ kết quả lưu · đối chiếu yêu cầu cũ':'Chưa lưu được · nội dung đang sửa được giữ';
      persist();onMessage(error.message,true);
      if(rejected&&error.status===409){try{const latest=await api(`/api/projects/${selected.project_id}`);if(sameScope(selected))showConflict(latest);}catch{}}
    }finally{working=false;onWorking(false);if(sameScope(selected))persist();controls();}
  }
  async function continueStep(){
    if(step!=='voices'){go(dramaSteps[Math.min(4,dramaSteps.findIndex(v=>v[0]===step)+1)][0]);return;}
    if(scriptDirty){await saveScript(false);if(scriptDirty)return;}
    if(drama?.saveForScenes){if(await drama.saveForScenes())go('scenes');return;}
    if(!getState().dirty&&dramaProgress(current()).confirmed&&!dramaProgress(current()).uncast.length)go('scenes');
  }
  function go(value){if(!dramaSteps.some(v=>v[0]===value))return;if(scriptDirty&&value!=='script'&&step==='script'){onMessage('Lưu nháp kịch bản trước khi chuyển bước.',true);return;}
    step=value;try{if(current())storage.setItem('vf-drama-step:'+current().id,step);}catch{}
    if(step==='preview'&&!dramaProgress(current()).audio){const p=dom.getElementById('native-narration-panel');if(p)p.open=true;}
    display();if(step==='voices'){const p=dom.getElementById('native-drama-panel');if(p)p.open=true;void drama?.load();}}
  function display(){const p=current(),enabled=isDramaProject(p);dom.body.classList.toggle('drama-project',enabled);dom.body.dataset.dramaStep=step;
    drama?.setWorkflowStep?.(enabled?step:null);
    flow.hidden=!enabled;scriptPane.hidden=step!=='script';voicePane.hidden=step!=='voices';previewTools.hidden=step!=='preview';
    const originalNav=dom.querySelector('.stage-navigation');if(enabled){originalNav.hidden=true;showStage(({script:'script',voices:'script',scenes:'assets',preview:'video',export:'video'})[step]);
      dom.getElementById('stage-script').hidden=true;dom.getElementById('brief-card').hidden=true;dom.getElementById('proposal-card').hidden=true;
      if(step==='scenes')dom.getElementById('stage-video').hidden=false;
      const cast=dom.getElementById('native-drama-panel');if(step==='voices'&&cast)cast.open=true;
      approvalCard.hidden=!['preview','export'].includes(step);}
    for(const[id,b]of stepButtons){if(id===step)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');}
    goal.textContent=({script:'Mục tiêu: lưu câu chuyện và tách đúng lời thoại khỏi hành động.',voices:'Mục tiêu: xác nhận nhân vật, nghe và chọn giọng cho từng vai.',scenes:'Mục tiêu: chọn ảnh/video có quyền sử dụng cho từng cảnh, kiểm tra thứ tự và crop.',preview:'Mục tiêu: tạo lời thoại, áp thời lượng đã đo và xem thử bản dựng.',export:'Mục tiêu: duyệt video cuối, kiểm QC rồi tải MP4 và gói đăng thủ công.'})[step];
    if(enabled){const ratio=p.document.canonical_timeline?.snapshot?.aspect_ratio??p.document.brand_template?.template?.aspect_ratio??'9:16';dom.body.style.setProperty('--drama-player-ratio',ratio.replace(':',' / '));const [w,h]=ratio.split(':').map(Number);dom.body.style.setProperty('--drama-width-multiplier',String(w/h));}
    controls();}
  function drawCharacters(){characterList.replaceChildren();const record=current()?.document.drama_script;if(!record){node('p','Lưu kịch bản ở bước 1 để gợi ý người nói. Bạn vẫn có thể lưu phim khi chưa đủ nội dung.',characterList);return;}
    for(const c of record.parsed.characters){node('p',`${c.name}${c.role==='narrator'?' · người kể, tùy chọn':''}`,characterList);const note=node('input',null,node('label','Vai trò / tính cách của '+c.name+' (tùy chọn)',characterList),{maxlength:'500','data-workspace-control':''});note.value=characterNotes[c.character_id]??'';note.addEventListener('input',()=>{characterNotes[c.character_id]=note.value;changed();});}
    for(const line of record.parsed.lines.filter(v=>v.needs_speaker)){const select=node('select',null,node('label',`Chọn người nói: ${line.text}`,characterList),{'data-workspace-control':''});node('option','Chưa rõ người nói',select,{value:''});for(const c of record.parsed.characters)node('option',c.name,select,{value:c.character_id});select.value=assignments[line.line_id]??'';select.addEventListener('change',()=>{assignments[line.line_id]=select.value;changed();});}
    confirm.textContent=record.characters_confirmed?'Xác nhận lại nhân vật từ kịch bản':'Xác nhận nhân vật & tạo phân cảnh nháp';
  }
  function controls(){const p=current(),s=dramaProgress(p),stop=blocked();create.disabled=working||getState().busy||!kind;save.disabled=stop||Boolean(conflict&&!pending)||!scriptDirty&&!pending;example.disabled=stop;confirm.disabled=stop||Boolean(conflict)||!p?.document.drama_script?.raw_text?.trim();text.disabled=(getState().busy&&!working)||s.active||p?.archived||getState().canEdit===false;
    save.title=conflict?'Đối chiếu bản đã lưu và chọn mốc lưu trước khi lưu lại.':'';viewSaved.disabled=working||!p;rebase.disabled=stop||Boolean(pending)||!conflict;
    save.textContent=pending?'Đối chiếu lần lưu trước':'Lưu nháp';confirm.disabled||=Boolean(pending);
    inputMode.disabled=seriesInput.disabled=episodeInput.disabled=text.disabled;for(const element of characterList.querySelectorAll('input,select'))element.disabled=stop;confirm.disabled||=inputMode.value==='idea';
    globalVoiceBrowser?.refresh();if(isDramaProject(p)&&step==='voices')drama?.ensureLoaded?.();if(isDramaProject(p)&&step==='preview')narration?.ensureLoaded?.();
    importVoices.disabled=getState().canManage===false||getState().busy;const scriptReview=dom.getElementById('script-only-review');if(isDramaProject(p)&&scriptReview)scriptReview.hidden=!s.confirmed||scriptDirty;
    back.disabled=step==='script'||working;next.disabled=working||step==='export';
    const missing=step==='script'&&!s.script?'Lưu kịch bản để tiếp tục.':step==='voices'&&!s.confirmed?'Xác nhận danh sách nhân vật trước khi chọn giọng.':step==='voices'&&s.uncast.length?`${s.uncast.join(', ')} chưa có giọng. Chọn giọng ngay trong bước này.`:step==='scenes'&&!s.scenes?'Thêm tư liệu và chọn nguồn cho từng cảnh.':step==='preview'&&!s.audio?'Chuẩn bị lời thoại và áp thời lượng audio đã đo trước khi duyệt xem thử.':'';
    state.textContent=missing||({script:'Bản nháp có thể lưu khi chưa đủ cảnh hoặc giọng.',voices:`${s.characterCount} nhân vật · ${s.voiceCount} giọng đã chọn.`,scenes:'Ảnh/video và dòng thời gian được lưu chung trong dự án.',preview:'Giữ các chốt duyệt nội dung và video; không tự tạo lại job chưa rõ kết quả.',export:'Video và nội dung đăng được tải về máy; bạn tự đăng thủ công.'})[step];
    const audioJob=(p?.jobs??[]).find(v=>v.kind==='narration'&&ACTIVE.has(v.status));if(step==='preview'&&audioJob){const m=/^dialogue_line_(\d+)_of_(\d+)$/.exec(audioJob.stage??''),c=p.document.drama_casting?.configuration,lines=(c?.lines??[]).filter(v=>v.enabled&&(c.characters.find(x=>x.character_id===v.character_id)?.role!=='narrator'||c.narrator_enabled)),name=m?c?.characters.find(v=>v.character_id===lines[Number(m[1])-1]?.character_id)?.name:null;state.textContent=m?`Đang tạo câu ${m[1]}/${m[2]}${name?' · '+name:''}`:audioJob.status==='queued'?'Lời thoại đang chờ được tạo trên máy.':'Đang chuẩn bị audio và đo thời lượng lời thoại.';}
    if(step==='script'&&!s.script||step==='voices'&&(!s.confirmed||s.uncast.length)||step==='scenes'&&!s.scenes)next.disabled=true;
    if(getState().dirty)next.disabled=true;
    next.title=getState().dirty?'Lưu bản nháp đang sửa trước khi tiếp tục.':missing;openAudio.disabled=stop||!p?.document.drama_casting;
    confirmHere.hidden=step!=='voices'||s.confirmed;confirmHere.disabled=blocked(true)||Boolean(pending)||!p?.document.drama_script?.raw_text?.trim();fixVoice.hidden=true;
    if(step==='voices'&&drama?.continuationState){const readiness=drama.continuationState();next.textContent=readiness.pending?'Đối chiếu phân vai & tiếp tục':'Lưu phân vai & tiếp tục';next.disabled=working||!readiness.can_continue_to_scenes;next.title=readiness.reason;state.textContent=readiness.reason||(readiness.has_changes?'Chưa lưu lựa chọn giọng. Bấm Lưu phân vai & tiếp tục.':`Đã lưu phân vai: ${readiness.assigned}/${readiness.needed} nhân vật có thoại đã có giọng. Chưa tạo lời thoại.`);fixVoice.hidden=!readiness.missing.length;fixVoice.disabled=readiness.working;}else next.textContent='Tiếp tục →';
    openAudio.textContent=s.audio?'Nghe hoặc kiểm tra lại lời thoại':'Kiểm tra phân vai đã lưu';
    const voiceStatus=dom.getElementById('runtime-voice-summary');if(voiceStatus)voiceStatus.textContent=isDramaProject(p)?`${s.characterCount} nhân vật · ${s.voiceCount} giọng`:p?'Giọng theo cấu hình đã lưu của dự án':'Chọn giọng theo từng dự án';
  }
  function sync(){const p=current(),url=new URL(globalThis.location?.href??'http://studio.local/'),view=url.searchParams.get('view');chooser.hidden=Boolean(p)||kind==='standard';settings.hidden=view!=='settings';voicesPage.hidden=view!=='voices';
    const selectedKey=keyFor(scope());if(selectedKey!==scopeKey){persist();scopeKey=selectedKey;boundProject=p;scriptDirty=false;pending=null;pendingResult=null;conflict=null;comparison.hidden=true;binding=null;if(getState().dirtyPart==='drama-script')onDirty(false);
      let draft=localDrafts.get(scopeKey);try{draft??=JSON.parse(storage.getItem(scopeKey));}catch{}
      if(isDramaProject(p)&&draft?.schema==='drama-local-draft.v1'&&typeof draft.buffer?.text==='string'&&draft.buffer.text.length<=20000&&(draft.dirty||draft.pending)){fill(draft.buffer);scriptDirty=true;pending=draft.pending??null;pendingResult=draft.pendingResult??null;saved.textContent=pending?'Đã khôi phục bản nháp · đối chiếu lần lưu trước':'Đã khôi phục bản nháp chưa lưu';onDirty(true);}else{saved.textContent='Đã lưu';}
    }boundProject=p;
    const k=`${p?.id}:${p?.revision}`;if(binding!==k){const changedProject=binding?.split(':')[0]!==p?.id;binding=k;if(!scriptDirty&&!pending){text.value=p?.document.drama_script?.raw_text??'';inputMode.value=p?.document.drama_script?.input_mode??'script';ideaHint.hidden=inputMode.value!=='idea';seriesInput.value=p?.document.production_workflow?.series??'';episodeInput.value=p?.document.production_workflow?.episode??'';characterNotes=structuredClone(p?.document.drama_script?.character_notes??{});assignments={};drawCharacters();}if(changedProject){try{step=storage.getItem('vf-drama-step:'+p?.id)??'script';}catch{step='script';}if(!dramaSteps.some(v=>v[0]===step))step='script';}}
    const panel=dom.getElementById('native-drama-panel');if(panel&&isDramaProject(p))moveHere(panel,voiceSlot);
    const audio=dom.getElementById('native-narration-panel');if(audio&&isDramaProject(p)){moveHere(audio,previewTools);const prepared=p.document.prepared_narration?.plan_sha256??null;if(audioProject!==p.id){audioProject=p.id;lastPrepared=prepared;audio.open=step==='preview'&&!dramaProgress(p).audio;}else if(lastPrepared!==prepared){lastPrepared=prepared;if(dramaProgress(p).audio)audio.open=false;}}
    if(isDramaProject(p)&&previewTools.parentNode!==dom.getElementById('video-stage-body'))dom.getElementById('video-stage-body').prepend(previewTools);
    if(isDramaProject(p)){const review=dom.getElementById('approve')?.closest('.review');if(review)moveHere(review,approvalCard);if(approvalCard.parentNode!==dom.getElementById('video-review-body'))dom.getElementById('video-review-body').prepend(approvalCard);const scriptReview=dom.getElementById('script-only-review');if(scriptReview)moveHere(scriptReview,scriptPane);}else{restoreHomes();previewTools.hidden=approvalCard.hidden=true;dom.getElementById('brief-card').hidden=false;if(p&&!['assets','brands','voices','settings'].includes(view))dom.querySelector('.stage-navigation').hidden=false;}
    if(['settings','voices'].includes(view)){chooser.hidden=flow.hidden=true;dom.querySelectorAll('[data-stage-panel],.stage-navigation').forEach(v=>v.hidden=true);dom.getElementById('studio-title').textContent=view==='voices'?'Thư viện giọng':'Cài đặt';controls();return;}
    if(!p&&kind===null){dom.querySelectorAll('[data-stage-panel],.stage-navigation').forEach(v=>v.hidden=true);dom.getElementById('studio-title').textContent='Tạo video mới';}
    if(isDramaProject(p))display();else{flow.hidden=true;dom.body.classList.remove('drama-project');controls();}}
  async function load(){try{const [catalog,info]=await Promise.all([api('/api/production-workflows'),api('/api/app-info')]);if(catalog?.schema_version!=='native-production-workflow.v1'||!Array.isArray(catalog.choices))throw Error('Chưa tải được lựa chọn tạo video.');
      for(const choice of catalog.choices){const card=node('article',null,cards,{class:'workflow-choice'});node('h3',choice.name,card);node('p',choice.description,card);node('p','Đầu vào: '+choice.input,card,{class:'hint'});node('p','Nhận được: '+choice.output,card,{class:'hint'});const b=button('Bắt đầu '+(choice.kind==='drama'?'Phim Drama':choice.kind==='source'?'dựng video':'video nội dung'),card,()=>{kind=choice.kind;
          if(kind==='standard'){chooser.hidden=true;dom.querySelector('.stage-navigation').hidden=false;showStage('script');dom.getElementById('brief-card').hidden=false;return;}
          creation.hidden=false;creationTitle.textContent=choice.name;create.textContent=kind==='drama'?'Tạo phim Drama':'Tạo dự án từ video';format.value='9:16';filmName.focus();controls();});b.classList.add('primary');}
      aboutText.textContent=`Bản dựng: ${info.build??'Chưa rõ'} · Nhánh: ${info.branch??'Chưa rõ'} · Phiên bản: ${info.commit??'Chưa rõ'} · Nguồn ứng dụng: ${info.application_source??'Chưa rõ'}`;
      if(new URL(globalThis.location?.href??'http://studio.local/').searchParams.get('view')==='voices'){
        await loadGlobalVoices();
      }
    }catch(error){onMessage(error.message,true);createHint.textContent='Chưa tải được các lựa chọn. Làm mới trang để thử đọc lại; không có TTS hoặc render được gọi.';}}
  dom.addEventListener('click',event=>{if(!isDramaProject(current()))return;const target=event.target.closest?.('[data-stage]');if(!target)return;const mapped={script:'script',assets:'scenes',storyboard:'scenes',video:'preview'}[target.dataset.stage];if(mapped){event.preventDefault();event.stopImmediatePropagation();go(mapped);}},true);
  const beforeLeave=event=>{if(scriptDirty||pending){event.preventDefault();event.returnValue='';}};globalThis.addEventListener?.('beforeunload',beforeLeave);
  sync();void load();return {sync,controls,showStep:go,isDirty:()=>scriptDirty,isWorking:()=>working,dispose(){clearTimeout(timer);globalVoiceBrowser?.dispose();globalThis.removeEventListener?.('beforeunload',beforeLeave);}};
}
