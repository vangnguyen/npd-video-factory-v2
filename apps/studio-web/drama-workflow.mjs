const ACTIVE=new Set(['queued','running','retrying']);
export const isDramaProject=project=>project?.document?.production_workflow?.kind==='drama';
export const dramaSteps=[['script','Kịch bản'],['voices','Nhân vật & giọng'],['scenes','Hình ảnh & cảnh'],['preview','Dựng & xem thử'],['export','Xuất video']];
export function dramaProgress(project){
  const d=project?.document??{},c=d.drama_casting?.configuration,active=(c?.lines??[]).filter(v=>v.enabled&&(c.characters.find(x=>x.character_id===v.character_id)?.role!=='narrator'||c.narrator_enabled));
  const uncast=[...new Set(active.filter(v=>!c.casting.some(x=>x.character_id===v.character_id)).map(v=>c.characters.find(x=>x.character_id===v.character_id)?.name??'Nhân vật'))];
  const shots=project?.shot_timeline?.shots??[];
  return {script:Boolean(d.drama_script?.raw_text?.trim()),confirmed:d.drama_script?.characters_confirmed===true,uncast,
    voiceCount:new Set(c?.casting.map(v=>v.voice_id)??[]).size,characterCount:c?.characters.filter(v=>v.role!=='narrator').length??0,
    scenes:shots.length>0&&shots.every(v=>v.asset_id),audio:Boolean(d.prepared_narration),active:(project?.jobs??[]).some(v=>ACTIVE.has(v.status))};
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
  node('p','Mỗi câu ghi Tên nhân vật: lời thoại. Đặt mô tả hành động trong ngoặc hoặc bắt đầu bằng “Hành động:”. Hành động chỉ dùng cho hình ảnh, không được đọc thành lời.',scriptPane,{class:'hint'});
  const text=node('textarea',null,node('label','Kịch bản của phim',scriptPane),{rows:'9',maxlength:'20000','data-workspace-control':'',placeholder:'CẢNH 1: Chiếc ô\n(An đặt chiếc ô lên bàn.)\nAn: Mình tìm thấy chiếc ô của bạn rồi.\nBình: Cảm ơn, mình đã tìm nó cả buổi.'});
  const tools=node('div',null,scriptPane,{class:'actions'}),save=button('Lưu nháp',tools,()=>saveScript(false)),example=button('Dùng kịch bản ví dụ nguyên bản',tools,()=>{text.value='CẢNH 1: Chiếc ô\n(An đặt chiếc ô lên bàn.)\nAn: Mình tìm thấy chiếc ô của bạn rồi.\nBình: Cảm ơn, mình đã tìm nó cả buổi.';changed();});
  node('p','Ví dụ chỉ là nội dung viết sẵn để thử thao tác, chưa có tư liệu hay phê duyệt. Bạn có thể thay bằng câu chuyện của mình.',scriptPane,{class:'hint'});
  const saved=node('p','Đã lưu',scriptPane,{role:'status','aria-live':'polite'});
  const voicePane=node('section',null,flow,{class:'drama-voices-pane'}),confirmCard=node('section',null,voicePane,{class:'card'});node('h2','Xác nhận người nói',confirmCard);
  const characterList=node('div',null,confirmCard),confirm=button('Xác nhận nhân vật & tạo phân cảnh nháp',confirmCard,()=>saveScript(true));
  node('p','Xác nhận danh sách không phải duyệt kịch bản hoặc chất lượng giọng. Người kể mặc định tắt; nhân vật không có thoại không bắt buộc có giọng.',confirmCard,{class:'hint'});
  const voiceSlot=node('div',null,voicePane),previewTools=node('section',null,null,{class:'card drama-preview-tools'});
  node('h2','Chuẩn bị lời thoại rồi xem thử',previewTools);node('p','Kiểm tra phân vai, duyệt nội dung tạo thoại, nghe audio và áp dụng thời lượng đã đo. Sau đó tạo xem thử và duyệt đúng phiên bản trước khi tạo video cuối.',previewTools,{class:'hint'});
  const openAudio=button('Mở bước chuẩn bị lời thoại',previewTools,()=>{const p=dom.getElementById('native-narration-panel');if(p){p.open=true;p.scrollIntoView({block:'start',behavior:'smooth'});}});
  const footer=node('div',null,flow,{class:'drama-next-actions'}),back=button('← Quay lại',footer,()=>go(dramaSteps[Math.max(0,dramaSteps.findIndex(v=>v[0]===step)-1)][0])),next=button('Tiếp tục →',footer,()=>go(dramaSteps[Math.min(4,dramaSteps.findIndex(v=>v[0]===step)+1)][0]));next.classList.add('primary');
  const settings=node('section',null,root,{class:'card studio-settings'});settings.hidden=true;node('h2','Cài đặt',settings);node('p','Các chức năng hoạt động trên máy và cấu hình dùng chung.',settings);
  const about=node('details',null,settings);node('summary','Thông tin ứng dụng',about);const aboutText=node('p','Đang đọc phiên bản…',about);
  const advanced=node('details',null,settings);node('summary','Kết nối & nâng cao',advanced);node('a','Cấu hình nhận diện lời nói',advanced,{href:'/settings/assemblyai'});
  let kind=null,step='script',binding=null,scriptDirty=false,working=false,pending=null,timer=null,assignments={};
  const current=()=>getState().project,blocked=()=>{const s=getState();return working||s.busy||dramaProgress(s.project).active||s.project?.archived||s.canEdit===false||(s.dirty&&s.dirtyPart!=='drama-script');};
  function changed(){scriptDirty=true;onDirty(true);saved.textContent='Chưa lưu';clearTimeout(timer);controls();}
  text.addEventListener('input',changed);
  async function createProject(){if(working)return;try{if(!filmName.value.trim())throw Error('Nhập tên phim trước khi bắt đầu.');working=true;onWorking(true);controls();
      const value=await api('/api/projects',{name:filmName.value.trim(),prompt:'',input_kind:kind==='source'?'media':'script',workflow_kind:kind,output_format:format.value});
      if(!/^[a-f0-9]{32}$/.test(value?.id??'')||value.document?.production_workflow?.kind!==kind)throw Error('Chưa xác nhận tạo dự án; kiểm tra Dự án của tôi trước khi thử lại.');
      await onCreated(value);kind=null;onMessage('Đã tạo bản nháp. Nhập kịch bản và xác nhận nhân vật để tiếp tục.');
    }catch(error){onMessage(error.message,true);}finally{working=false;onWorking(false);sync();}}
  async function saveScript(confirmCharacters){
    if(working||!current()||blocked())return;const project=current();
    try{const request=pending??{revision:project.revision,request_key:globalThis.crypto.randomUUID(),text:text.value,confirm_characters:confirmCharacters,
        narrator_enabled:project.document.drama_casting?.configuration.narrator_enabled??false,speaker_assignments:assignments};
      if(pending&&pending.confirm_characters!==confirmCharacters)throw Error('Đối chiếu lần lưu chưa nhận được kết quả bằng nút Lưu nháp trước.');
      pending=request;working=true;onWorking(true);saved.textContent='Đang lưu…';controls();
      const result=validateDramaScriptResponse(await api(`/api/projects/${project.id}/drama-script`,request),project,request);
      await onSaved();pending=null;
      if(current()?.revision!==result.revision||current()?.document?.drama_script?.raw_text!==request.text){scriptDirty=true;onDirty(true);throw Error('Dự án đã có bản mới. Nội dung đang sửa được giữ; kiểm tra lịch sử trước khi lưu lại.');}
      scriptDirty=false;onDirty(false);saved.textContent='Đã lưu';binding=null;sync();if(confirmCharacters)go('voices');
      onMessage(confirmCharacters?'Đã xác nhận nhân vật và tạo cảnh nháp. Chọn giọng riêng cho từng người; chưa tạo audio hoặc phê duyệt video.':'Đã lưu nháp kịch bản.');
    }catch(error){saved.textContent='Chưa lưu được · nội dung đang sửa được giữ';onMessage(error.message,true);}finally{working=false;onWorking(false);controls();}
  }
  function go(value){if(!dramaSteps.some(v=>v[0]===value))return;if(scriptDirty&&value!=='script'&&step==='script'){onMessage('Lưu nháp kịch bản trước khi chuyển bước.',true);return;}
    step=value;try{if(current())storage.setItem('vf-drama-step:'+current().id,step);}catch{}
    display();if(step==='voices'){const p=dom.getElementById('native-drama-panel');if(p)p.open=true;void drama?.load();}}
  function display(){const p=current(),enabled=isDramaProject(p);dom.body.classList.toggle('drama-project',enabled);dom.body.dataset.dramaStep=step;
    flow.hidden=!enabled;scriptPane.hidden=step!=='script';voicePane.hidden=step!=='voices';previewTools.hidden=step!=='preview';
    const originalNav=dom.querySelector('.stage-navigation');if(enabled){originalNav.hidden=true;showStage(({script:'script',voices:'script',scenes:'assets',preview:'video',export:'video'})[step]);
      dom.getElementById('stage-script').hidden=true;dom.getElementById('brief-card').hidden=true;dom.getElementById('proposal-card').hidden=true;}
    for(const[id,b]of stepButtons){if(id===step)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');}
    goal.textContent=({script:'Mục tiêu: lưu câu chuyện và tách đúng lời thoại khỏi hành động.',voices:'Mục tiêu: xác nhận nhân vật, nghe và chọn giọng cho từng vai.',scenes:'Mục tiêu: chọn ảnh/video có quyền sử dụng cho từng cảnh, kiểm tra thứ tự và crop.',preview:'Mục tiêu: tạo lời thoại, áp thời lượng đã đo và xem thử bản dựng.',export:'Mục tiêu: duyệt video cuối, kiểm QC rồi tải MP4 và gói đăng thủ công.'})[step];
    if(enabled){const ratio=p.document.canonical_timeline?.snapshot?.aspect_ratio??p.document.brand_template?.template?.aspect_ratio??'9:16';dom.body.style.setProperty('--drama-player-ratio',ratio.replace(':',' / '));}
    controls();}
  function drawCharacters(){characterList.replaceChildren();const record=current()?.document.drama_script;if(!record){node('p','Lưu kịch bản ở bước 1 để gợi ý người nói. Bạn vẫn có thể lưu phim khi chưa đủ nội dung.',characterList);return;}
    for(const c of record.parsed.characters)node('p',`${c.name}${c.role==='narrator'?' · người kể, đang tắt theo mặc định':''}`,characterList);
    for(const line of record.parsed.lines.filter(v=>v.needs_speaker)){const select=node('select',null,node('label',`Chọn người nói: ${line.text}`,characterList),{'data-workspace-control':''});node('option','Chưa rõ người nói',select,{value:''});for(const c of record.parsed.characters)node('option',c.name,select,{value:c.character_id});select.value=assignments[line.line_id]??'';select.addEventListener('change',()=>{assignments[line.line_id]=select.value;});}
    confirm.textContent=record.characters_confirmed?'Xác nhận lại nhân vật từ kịch bản':'Xác nhận nhân vật & tạo phân cảnh nháp';
  }
  function controls(){const p=current(),s=dramaProgress(p),stop=blocked();create.disabled=working||getState().busy||!kind;save.disabled=stop||!scriptDirty&&!pending;example.disabled=stop;confirm.disabled=stop||!p?.document.drama_script?.raw_text?.trim();text.disabled=working||getState().busy||s.active||p?.archived||getState().canEdit===false;
    back.disabled=step==='script'||working;next.disabled=working||step==='export';
    const missing=step==='script'&&!s.script?'Lưu kịch bản để tiếp tục.':step==='voices'&&!s.confirmed?'Xác nhận danh sách nhân vật trước khi chọn giọng.':step==='voices'&&s.uncast.length?`${s.uncast.join(', ')} chưa có giọng. Chọn giọng ngay trong bước này.`:step==='scenes'&&!s.scenes?'Thêm tư liệu và chọn nguồn cho từng cảnh.':step==='preview'&&!s.audio?'Chuẩn bị lời thoại và áp thời lượng audio đã đo trước khi duyệt xem thử.':'';
    state.textContent=missing||({script:'Bản nháp có thể lưu khi chưa đủ cảnh hoặc giọng.',voices:`${s.characterCount} nhân vật · ${s.voiceCount} giọng đã chọn.`,scenes:'Ảnh/video và dòng thời gian được lưu chung trong dự án.',preview:'Giữ các chốt duyệt nội dung và video; không tự tạo lại job chưa rõ kết quả.',export:'Video và nội dung đăng được tải về máy; bạn tự đăng thủ công.'})[step];
    if(step==='script'&&!s.script||step==='voices'&&(!s.confirmed||s.uncast.length)||step==='scenes'&&!s.scenes)next.disabled=true;
    next.title=missing;openAudio.disabled=stop||!p?.document.drama_casting;
    const voiceStatus=dom.getElementById('runtime-voice-summary');if(voiceStatus)voiceStatus.textContent=isDramaProject(p)?`${s.characterCount} nhân vật · ${s.voiceCount} giọng`:p?'Giọng theo cấu hình đã lưu của dự án':'Chọn giọng theo từng dự án';
  }
  function sync(){const p=current(),url=new URL(globalThis.location?.href??'http://studio.local/'),view=url.searchParams.get('view');chooser.hidden=Boolean(p);settings.hidden=view!=='settings';
    const k=`${p?.id}:${p?.revision}`;if(binding!==k){const changedProject=binding?.split(':')[0]!==p?.id;binding=k;if(!scriptDirty&&!pending){text.value=p?.document.drama_script?.raw_text??'';assignments={};drawCharacters();}if(changedProject){try{step=storage.getItem('vf-drama-step:'+p?.id)??'script';}catch{step='script';}if(!dramaSteps.some(v=>v[0]===step))step='script';}}
    const panel=dom.getElementById('native-drama-panel');if(panel&&isDramaProject(p)&&panel.parentNode!==voiceSlot)voiceSlot.append(panel);
    const audio=dom.getElementById('native-narration-panel');if(audio&&isDramaProject(p)&&audio.parentNode!==previewTools)previewTools.append(audio);
    if(isDramaProject(p)&&previewTools.parentNode!==dom.getElementById('video-stage-body'))dom.getElementById('video-stage-body').prepend(previewTools);
    if(view==='settings'){chooser.hidden=flow.hidden=true;dom.querySelectorAll('[data-stage-panel],.stage-navigation').forEach(v=>v.hidden=true);dom.getElementById('studio-title').textContent='Cài đặt';return;}
    if(!p&&kind===null){dom.querySelectorAll('[data-stage-panel],.stage-navigation').forEach(v=>v.hidden=true);dom.getElementById('studio-title').textContent='Tạo video mới';}
    if(isDramaProject(p))display();else{flow.hidden=true;dom.body.classList.remove('drama-project');controls();}}
  async function load(){try{const [catalog,info]=await Promise.all([api('/api/production-workflows'),api('/api/app-info')]);if(catalog?.schema_version!=='native-production-workflow.v1'||!Array.isArray(catalog.choices))throw Error('Chưa tải được lựa chọn tạo video.');
      for(const choice of catalog.choices){const card=node('article',null,cards,{class:'workflow-choice'});node('h3',choice.name,card);node('p',choice.description,card);node('p','Đầu vào: '+choice.input,card,{class:'hint'});node('p','Nhận được: '+choice.output,card,{class:'hint'});const b=button('Bắt đầu '+(choice.kind==='drama'?'Phim Drama':choice.kind==='source'?'dựng video':'video nội dung'),card,()=>{kind=choice.kind;
          if(kind==='standard'){chooser.hidden=true;dom.querySelector('.stage-navigation').hidden=false;showStage('script');dom.getElementById('brief-card').hidden=false;return;}
          creation.hidden=false;creationTitle.textContent=choice.name;create.textContent=kind==='drama'?'Tạo phim Drama':'Tạo dự án từ video';format.value='9:16';filmName.focus();controls();});b.classList.add('primary');}
      aboutText.textContent=`Bản dựng: ${info.build??'Chưa rõ'} · Nhánh: ${info.branch??'Chưa rõ'} · Phiên bản: ${info.commit??'Chưa rõ'} · Nguồn ứng dụng: ${info.application_source??'Chưa rõ'}`;
    }catch(error){onMessage(error.message,true);createHint.textContent='Chưa tải được các lựa chọn. Làm mới trang để thử đọc lại; không có TTS hoặc render được gọi.';}}
  sync();void load();return {sync,controls,showStep:go,isDirty:()=>scriptDirty,isWorking:()=>working};
}
