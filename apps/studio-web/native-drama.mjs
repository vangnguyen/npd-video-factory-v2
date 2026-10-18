import {initializeVoiceBrowser,usableVoice} from './voice-browser.mjs';
const ID=/^[a-f0-9]{32}$/,SHA=/^[a-f0-9]{64}$/,VOICE=/^nvoice_[a-f0-9]{32}$/;
const source=s=>s.project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1';
const active=s=>s.active||(s.project?.jobs??[]).some(j=>['queued','running','retrying'].includes(j.status));
const blocked=s=>!ID.test(s.project?.id??'')||s.busy||active(s)||s.project?.archived||source(s)||(s.dirty&&s.dirtyPart!=='drama');
const messages={DRAMA_DELIVERY_PLAN_NOT_READY:'Kiểm tra giọng, quyền sử dụng, người nói và shot của từng câu. Chọn mẫu theo lời đọc trước khi thử lại.',
  DRAMA_CHARACTER_CONFIRMATION_REQUIRED:'Kịch bản đang là bản nháp mới. Quay lại bước Nhân vật & giọng, kiểm tra người nói và bấm Xác nhận nhân vật trước.',
  DRAMA_VOICE_BINDING_CHANGED:'Giọng trong thư viện đã có phiên bản mới. Tải lại, chọn rõ giọng cho nhân vật và lưu phân vai.',
  DRAMA_FIT_NARRATION_TEMPLATE_REQUIRED:'Chọn thời lượng “Theo lời đọc” trong Thương hiệu & mẫu, rồi kiểm tra phân vai lại.',
  DRAMA_LEGACY_NARRATOR_POLICY_CONFLICT:'Dự án đang dùng cách đọc một giọng cũ. Cần bỏ lựa chọn đó trước khi chuyển sang thoại nhiều nhân vật.',
  DRAMA_CANONICAL_SCRIPT_BINDING_CHANGED:'Lời thoại và shot đã khác nhau. Xem lại từng câu rồi lưu thoại vào timeline.',
  DRAMA_DIALOGUE_SHOT_ORDER_INVALID:'Dùng nút lên/xuống để xếp các câu theo thứ tự shot, rồi lưu và kiểm tra phân vai lại.',
  DRAMA_PROVIDER_CONFIGURATION_CHANGED:'Cấu hình giọng local đã thay đổi hoặc chưa sẵn sàng. Tải lại thư viện và kiểm tra phân vai trước khi tạo audio.',
  VOICE_RIGHTS_CONFIRMATION_REQUIRED:'Owner cần khai báo quyền sử dụng giọng trong Thư viện giọng.',
  DRAMA_SERIES_CHARACTER_REVIEW_REQUIRED:'Các câu hiện tại dùng nhân vật khác. Giữ bản hiện tại và điều chỉnh phân vai trước khi áp dụng series.',
  DRAMA_CLIP_RECOVERY_REQUIRED:'Lần tạo câu trước chưa có kết quả chắc chắn. Kiểm tra kết quả; muốn tạo mới, chọn “Tạo lại riêng câu này” rồi duyệt lại.'};
const humanError=error=>Object.entries(messages).find(([code])=>String(error.message).includes(code))?.[1]??error.message;
export function validateDramaPage(value,state){
  if(value?.schema_version!=='native-drama-studio.v1'||value.project_id!==state.project?.id||value.revision!==state.project?.revision||value.workspace_id!==state.workspace_id
    ||typeof value.compiled_current!=='boolean'||value.provider_calls!==0||value.human_voice_uat_complete!==false||!Array.isArray(value.shots)||value.shots.length>20
    ||value.shots.some(s=>!/^shot_[a-f0-9]{32}$/.test(s.shot_id??'')||typeof s.narration!=='string'||typeof s.narration_enabled!=='boolean')
    ||value.casting&&(!SHA.test(value.casting.sha256??'')||!Number.isInteger(value.casting.version)||!Array.isArray(value.casting.configuration?.characters)||!Array.isArray(value.casting.configuration?.lines)))throw Error('Phân vai không khớp dự án đã lưu.');
  return value;
}
export function dramaRequest(state,page,action,{configuration,requestKey,lineId,series,name,clearLegacyVoicePolicy=false}={}){
  if(blocked(state)||state.canEdit===false)throw Error('Lưu thay đổi khác và chờ tác vụ hoàn tất trước khi sửa thoại.');
  validateDramaPage(page,state);if(typeof requestKey!=='string'||!/^[A-Za-z0-9_.:-]{12,128}$/.test(requestKey))throw Error('Yêu cầu chưa hợp lệ.');
  const p=state.project,base=`/api/projects/${p.id}/drama-casting`,body={revision:p.revision,request_key:requestKey};
  if(action==='save'){
    if(!configuration?.characters?.length||!Array.isArray(configuration.lines)||configuration.lines.some(v=>!configuration.characters.some(c=>c.character_id===v.character_id)||!v.text?.trim()||v.shot_id!==null&&!page.shots.some(s=>s.shot_id===v.shot_id)))throw Error('Chọn người nói và nội dung hợp lệ cho từng câu.');
    if(typeof clearLegacyVoicePolicy!=='boolean')throw Error('Cần chọn rõ cách chuyển cấu hình giọng.');
    const bound=configuration.lines.length>0&&configuration.lines.every(v=>v.shot_id!==null);
    return {path:base,body:{...body,expected_version:page.casting?.version??0,configuration,sync_canonical_script:bound,clear_legacy_voice_policy:clearLegacyVoicePolicy}};
  }
  if(state.dirty)throw Error('Lưu phân vai và lời thoại trước khi tiếp tục.');
  if(action==='compile')return {path:base+'/compile',body:{...body,expected_version:p.document.compiled_dialogue?.version??0}};
  if(action==='take'){
    if(!page.casting?.configuration.lines.some(v=>v.line_id===lineId&&v.enabled&&((page.casting.configuration.characters.find(c=>c.character_id===v.character_id)?.role??'character')!=='narrator'||page.casting.configuration.narrator_enabled)))throw Error('Chọn một câu thoại đang bật.');
    return {path:base+'/takes',body:{...body,expected_casting_sha256:page.casting.sha256,line_ids:[lineId]}};
  }
  if(action==='series-save'){
    if(!name?.trim()||!page.casting)throw Error('Lưu phân vai và nhập tên series.');
    return {path:base+'/series-save',body:{...body,expected_version:0,name:name.trim()}};
  }
  if(action==='series-apply'){
    if(!/^nseries_[a-f0-9]{32}$/.test(series?.series_id??'')||!SHA.test(series.sha256??'')||!Number.isInteger(series.version))throw Error('Chọn bộ phân vai đã lưu.');
    return {path:base+'/series-apply',body:{...body,series_id:series.series_id,version:series.version,expected_sha256:series.sha256}};
  }
  throw Error('Thao tác chưa hỗ trợ.');
}
export function splitDialogueLine(configuration,index,position,newLineId){
  const result=structuredClone(configuration),line=result.lines[index];
  if(!line||!/^line_[a-f0-9]{32}$/.test(newLineId)||!Number.isInteger(position)||position<=0||position>=line.text.length||!(/\s/.test(line.text[position-1])||/\s/.test(line.text[position])))throw Error('Đặt con trỏ ở khoảng trắng giữa hai câu để chia.');
  const a=line.text.slice(0,position).trim(),b=line.text.slice(position).trim();if(!a||!b)throw Error('Mỗi câu cần nội dung.');
  result.lines.splice(index,1,{...line,text:a,pause_after_seconds:.15},{...line,line_id:newLineId,text:b});return result;
}
export function validateDramaWrite(result,request,action,projectId){
  if(!result||typeof result!=='object'||result.human_voice_uat_complete===true||result.human_approval_granted===true)throw Error('Biên nhận không hợp lệ; chưa xác nhận lưu. Thử lại đúng yêu cầu.');
  if(action==='voice-save'){
    if(!VOICE.test(result.voice_id??'')||!Number.isInteger(result.version)||result.version<1||!SHA.test(result.definition_sha256??''))throw Error('Biên nhận giọng không hợp lệ; thử lại đúng yêu cầu.');
  }else{
    if(result.project_id!==projectId)throw Error('Biên nhận không thuộc dự án hiện tại; thử lại đúng yêu cầu.');
    if(['save','compile','take','series-apply'].includes(action)&&(!Number.isInteger(result.project_revision_at_write)||result.project_revision_at_write!==request.body.revision+1))throw Error('Biên nhận không khớp phiên bản đã gửi; thử lại đúng yêu cầu.');
  }
  return result;
}
export function initializeNativeDrama({api,getState,onMessage,onWorking=()=>{},onSaved=async()=>{},onDirty=()=>{},dom=globalThis.document,newKey=()=>globalThis.crypto.randomUUID()}){
  const root=dom.getElementById('native-drama-panel');let page=null,voices=[],catalog=null,series=[],draft=null,dialogueDirty=false,voiceDirty=false,clearLegacyChoice=false,working=false,serial=0,binding=null,pending=null,editVoice=null,voiceBrowser=null,targetCharacter=null,autoLoadContext=null;
  const context=()=>{const s=getState();return `${s.workspace_id}:${s.project?.id}:${s.project?.revision}`;},uid=prefix=>prefix+newKey().replaceAll('-','');
  const node=(tag,text,parent,attrs={})=>{const n=dom.createElement(tag);if(text!==null)n.textContent=text;for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));parent.append(n);return n;};
  const button=(text,parent,action,permission='edit',saved=true)=>{const b=node('button',text,parent,{type:'button','data-drama-action':action});b._permission=permission;b._saved=saved;return b;};
  const changed=()=>{if(pending||working){controls();return;}dialogueDirty=true;onDirty(true);controls();};
  node('summary','Nhân vật & giọng thoại',root);node('p','Chọn giọng riêng cho từng nhân vật. Người kể mặc định tắt. Lưu thoại vào timeline, kiểm tra rồi duyệt để tạo audio; nghe và áp thời lượng đã đo ở phần Lời đọc bên dưới.',root,{class:'hint'});
  const tools=node('div',null,root,{class:'planner-tools'}),loadButton=button('Làm mới',tools,'load','read',false),start=button('Bắt đầu phân vai',tools,'start'),discard=button('Bỏ chỉnh sửa và tải lại',tools,'discard','read',false),status=node('p','',root,{role:'status'});
  const castArea=node('div',null,root),characterArea=node('div',null,castArea),addCharacter=button('Thêm nhân vật',castArea,'character','edit',false),narratorLabel=node('label',null,castArea,{class:'check'}),narrator=node('input',null,narratorLabel,{type:'checkbox'});node('span','Có người kể',narratorLabel);
  const lineArea=node('div',null,castArea),addLine=button('Thêm câu thoại',castArea,'line','edit',false),save=button('Lưu thoại & phụ đề vào timeline',castArea,'save','edit',false),compile=button('Kiểm tra phân vai để tạo audio',castArea,'compile');
  tools.append(save);save.setAttribute('class','primary');const sortLines=button('Xếp thoại theo thứ tự cảnh hiện tại',castArea,'sort-lines','edit',false);
  sortLines.addEventListener('click',()=>{if(sortLines.disabled||!draft)return;const order=new Map((page?.shots??[]).map((v,i)=>[v.shot_id,i]));draft.lines.sort((a,b)=>(order.get(a.shot_id)??999)-(order.get(b.shot_id)??999));changed();draw();controls();onMessage('Đã xếp bản nháp lời thoại theo cảnh. Kiểm tra rồi lưu phân vai trước khi tạo audio.');});
  const legacyLabel=node('label',null,castArea,{class:'check'}),legacy=node('input',null,legacyLabel,{type:'checkbox'});node('span','Chuyển từ cách đọc một giọng cũ sang giọng theo phân vai. Bản cũ giữ trong lịch sử.',legacyLabel);
  node('p','Sửa một giọng hoặc tạo lại một câu sẽ cần duyệt lại audio, preview và video cuối. Tư liệu hình ảnh được giữ lại.',castArea,{class:'hint'});
  const seriesArea=node('details',null,root);node('summary','Phân vai dùng lại cho series',seriesArea);const seriesName=node('input',null,node('label','Tên bộ phân vai mới',seriesArea),{maxlength:'100'}),seriesSave=button('Lưu bộ phân vai',seriesArea,'series-save'),seriesChoice=node('select',null,node('label','Bộ phân vai đã lưu',seriesArea)),seriesApply=button('Áp dụng phân vai từ series',seriesArea,'series-apply');
  node('p','Mỗi phim giữ bản phân vai riêng. Áp dụng series không mang theo câu thoại hoặc duyệt của phim cũ.',seriesArea,{class:'hint'});
  const library=node('details',null,root);library.open=true;node('summary','Nghe và chọn giọng local',library);
  const target=node('select',null,node('label','Chọn giọng cho nhân vật',library));target.addEventListener('change',()=>{targetCharacter=target.value;voiceBrowser?.refresh();});
  const voiceCards=node('div',null,library),registration=button('Đăng ký các preset đã cài có căn cứ quyền',library,'import-installed','manage',false);
  const manual=node('details',null,library);node('summary','Quản lý giọng nâng cao',manual);
  const voiceList=node('div',null,manual),voiceChoice=node('select',null,node('label','Thêm hoặc sửa giọng trong thư viện',manual)),voiceName=node('input',null,node('label','Tên hiển thị',manual),{maxlength:'100'}),preset=node('select',null,node('label','Giọng preset local',manual));
  const license=node('input',null,node('label','Giấy phép / điều kiện sử dụng',manual),{maxlength:'1000'}),reference=node('input',null,node('label','Nguồn tham chiếu quyền',manual),{maxlength:'2000'}),permission=node('input',null,node('label','Căn cứ được phép sử dụng',manual),{maxlength:'2000'}),rightsLabel=node('label',null,manual,{class:'check'}),rights=node('input',null,rightsLabel,{type:'checkbox'});
  node('span','Tôi xác nhận có quyền dùng giọng này theo thông tin đã nhập.',rightsLabel);const voiceSave=button('Lưu giọng vào thư viện',manual,'voice-save','manage',false);
  node('p','Preset có căn cứ được đăng ký từ manifest đã khóa. Giọng thêm tay cần căn cứ riêng. Chọn giọng cho vai không thay cho duyệt audio hoặc video.',library,{class:'hint'});
  const option=(select,text,value)=>node('option',text,select,{value});
  function markVoice(){if(pending||working){controls();return;}voiceDirty=true;onDirty(true);controls();}
  function fillVoice(){editVoice=voices.find(v=>v.voice_id===voiceChoice.value)??null;const d=editVoice?.definition;voiceName.value=d?.display_name??'';preset.value=d?.provider_voice_id??'';license.value=d?.license??'';reference.value=d?.source_reference??'';permission.value=d?.permission_reference??'';rights.checked=d?.rights_status==='owner_declared';voiceDirty=false;onDirty(dialogueDirty);controls();}
  function draw(){
    voiceBrowser?.dispose();voiceBrowser=null;
    characterArea.replaceChildren();lineArea.replaceChildren();voiceList.replaceChildren();seriesChoice.replaceChildren();voiceChoice.replaceChildren();preset.replaceChildren();
    option(seriesChoice,'Chọn bộ phân vai…','');for(const s of series)option(seriesChoice,`${s.name} · phiên bản ${s.version}`,s.series_id);
    option(voiceChoice,'Thêm giọng mới…','');for(const v of voices){option(voiceChoice,`${v.definition.display_name} · phiên bản ${v.version}`,v.voice_id);node('p',`${v.definition.display_name} · ${v.definition.provider_voice_id} · ${v.definition.rights_status==='owner_declared'?'Owner đã khai báo quyền':v.definition.rights_status==='blocked'?'Bị chặn':'Chưa khai báo quyền'}`,voiceList);}
    option(preset,'Chọn giọng…','');for(const v of catalog?.voices??[])option(preset,v.display_name,v.provider_voice_id);fillVoice();
    castArea.hidden=!draft;narrator.checked=draft?.narrator_enabled??false;legacyLabel.hidden=!getState().project?.document?.voice_quality;legacy.checked=clearLegacyChoice;
    status.textContent=!page?'Tải dữ liệu để bắt đầu.':page.compiled_current?'Phân vai đã kiểm tra. Duyệt nội dung và tạo lời đọc bên dưới; chưa duyệt video cuối.':page.casting?'Cần lưu / kiểm tra phân vai trước khi tạo audio.':'Chưa phân vai. Tạo nhân vật rồi chọn người nói cho từng câu.';
    if(page&&catalog?.status==='NOT_CONFIGURED')status.textContent+=' Chưa cấu hình bộ giọng local; vẫn có thể lưu bản phân vai nháp.';
    if(!draft)return;
    target.replaceChildren();for(const c of draft.characters.filter(v=>v.role!=='narrator'||draft.narrator_enabled))option(target,c.name,c.character_id);targetCharacter=draft.characters.some(v=>v.character_id===targetCharacter)?targetCharacter:target.value;target.value=targetCharacter??'';
    voiceBrowser=initializeVoiceBrowser({root:voiceCards,api,voices:voices.filter(v=>usableVoice(v)),catalog,dom,getCharacter:()=>{const c=draft?.characters.find(v=>v.character_id===targetCharacter);return c?{...c,selected_voice_id:draft.casting.find(v=>v.character_id===c.character_id)?.voice_id}:null;},getTrialText:()=>draft?.lines.find(v=>v.character_id===targetCharacter&&v.enabled)?.text??'',
      canEdit:()=>!working&&!blocked(getState())&&!voiceDirty&&!pending&&getState().canEdit!==false,
      onSelect:(voice,c)=>{draft.casting=draft.casting.filter(v=>v.character_id!==c.character_id);draft.casting.push({character_id:c.character_id,voice_id:voice.voice_id,voice_version:voice.version,voice_sha256:voice.definition_sha256});changed();onMessage(draft.casting.filter(v=>v.voice_id===voice.voice_id).length>1?'Hai nhân vật đang dùng cùng giọng. Bạn vẫn có thể giữ lựa chọn này.':`Đã chọn ${voice.definition.display_name} cho ${c.name}. Bấm Lưu thoại & phụ đề vào timeline để lưu phân vai.`);draw();controls();target.focus?.();},onMessage});
    registration.hidden=(catalog?.voices??[]).every(v=>voices.some(x=>x.definition.provider_voice_id===v.provider_voice_id&&x.definition.rights_status==='source_licensed'));
    for(const character of draft.characters){const card=node('article',null,characterArea,{class:'planner-scene'}),name=node('input',null,node('label',character.role==='narrator'?'Tên người kể':'Tên nhân vật',card),{maxlength:'100'});name.value=character.name;
      const select=node('select',null,node('label','Giọng của nhân vật trong phim này',card));option(select,'Chọn giọng…','');for(const voice of voices)option(select,`${voice.definition.display_name}${usableVoice(voice)?'':' · cần kiểm tra quyền'}`,voice.voice_id);
      const casting=draft.casting.find(v=>v.character_id===character.character_id),current=voices.find(v=>v.voice_id===casting?.voice_id&&v.version===casting.voice_version&&v.definition_sha256===casting.voice_sha256);select.value=current?.voice_id??'';
      const hear=button('Nghe và chọn giọng cho '+character.name,card,'browse-voices','edit',false);hear.addEventListener('click',()=>{targetCharacter=character.character_id;target.value=targetCharacter;library.open=true;voiceBrowser?.refresh();library.scrollIntoView?.({block:'start',behavior:'smooth'});});
      const note=getState().project?.document?.drama_script?.character_notes?.[character.character_id];if(note)node('p','Vai trò / tính cách: '+note,card,{class:'hint'});
      name.addEventListener('input',()=>{character.name=name.value;changed();});select.addEventListener('change',()=>{draft.casting=draft.casting.filter(v=>v.character_id!==character.character_id);const voice=voices.find(v=>v.voice_id===select.value);if(voice)draft.casting.push({character_id:character.character_id,voice_id:voice.voice_id,voice_version:voice.version,voice_sha256:voice.definition_sha256});changed();});
      const remove=button('Xóa nhân vật chưa dùng',card,'remove-character','edit',false);remove.addEventListener('click',()=>{if(remove.disabled)return;if(draft.characters.length<=1||draft.lines.some(v=>v.character_id===character.character_id)){onMessage('Giữ ít nhất một nhân vật và đổi người nói của các câu liên quan trước khi xóa.',true);return;}draft.characters=draft.characters.filter(v=>v.character_id!==character.character_id);draft.casting=draft.casting.filter(v=>v.character_id!==character.character_id);if(character.role==='narrator')draft.narrator_enabled=false;changed();draw();controls();});
    }
    for(const [index,line] of draft.lines.entries()){const card=node('article',null,lineArea,{class:'planner-scene','data-drama-line':line.line_id}),speaker=node('select',null,node('label',`Người nói · câu ${index+1}`,card));option(speaker,'Chọn người nói…','');for(const c of draft.characters)option(speaker,c.name+(c.role==='narrator'?' · người kể':''),c.character_id);speaker.value=line.character_id??'';
      const shot=node('select',null,node('label','Cảnh quay',card));option(shot,'Chọn cảnh…','');for(const s of page.shots)option(shot,`Cảnh ${s.scene}`,s.shot_id);shot.value=line.shot_id??'';
      const text=node('textarea',null,node('label','Nội dung câu thoại',card),{rows:'3',maxlength:'4000'});text.value=line.text;
      const enabled=node('input',null,node('label','Dùng câu này',card),{type:'checkbox'});enabled.checked=line.enabled;
      for(const [element,event,callback]of [[speaker,'change',()=>line.character_id=speaker.value],[shot,'change',()=>line.shot_id=shot.value],[text,'input',()=>line.text=text.value],[enabled,'change',()=>line.enabled=enabled.checked]])element.addEventListener(event,()=>{callback();changed();});
      const split=button('Chia câu tại con trỏ',card,'split','edit',false),take=button('Tạo lại riêng câu này',card,'take');take._lineId=line.line_id;
      const remove=button('Xóa câu khỏi bản đang sửa',card,'remove-line','edit',false);remove.addEventListener('click',()=>{if(remove.disabled)return;draft.lines.splice(index,1);changed();draw();controls();});
      for(const [direction,label]of [[-1,'Lên một câu'],[1,'Xuống một câu']]){const move=button(label,card,'move-line','edit',false);move._boundary=index+direction<0||index+direction>=draft.lines.length;
        move.addEventListener('click',()=>{if(move.disabled)return;[draft.lines[index],draft.lines[index+direction]]=[draft.lines[index+direction],draft.lines[index]];changed();draw();controls();});}
      split.addEventListener('click',()=>{if(split.disabled)return;try{draft=splitDialogueLine(draft,index,text.selectionStart,uid('line_'));changed();draw();controls();}catch(error){onMessage(error.message,true);}});
      take.addEventListener('click',()=>submit('take',{lineId:line.line_id}));
    }
  }
  async function load({discard=false}={}){
    const state=getState();if(working||blocked(state)||dialogueDirty&&!discard||voiceDirty&&!discard)return;const key=context(),ticket=++serial;working=true;onWorking(true);controls();
    try{const values=await Promise.all([api(`/api/projects/${state.project.id}/drama-casting`),api('/api/voice-library'),api('/api/voice-library/presets'),api('/api/drama-series')]);
      if(ticket!==serial||key!==context())return;const p=validateDramaPage(values[0],getState());
      if(!Array.isArray(values[1]?.items)||values[1].items.some(v=>!VOICE.test(v.voice_id??'')||!Number.isInteger(v.version)||!SHA.test(v.definition_sha256??'')||typeof v.definition?.display_name!=='string')||!Array.isArray(values[2]?.voices)||!Array.isArray(values[3]?.items))throw Error('Thư viện giọng chưa hợp lệ.');
      page=p;voices=values[1].items;catalog=values[2];series=values[3].items;draft=p.casting?structuredClone(p.casting.configuration):null;dialogueDirty=voiceDirty=clearLegacyChoice=false;pending=null;onDirty(false);draw();
    }catch(error){if(ticket===serial)onMessage(humanError(error),true);}finally{working=false;onWorking(false);controls();}
  }
  async function execute(request,action){
    if(working)return;const s=getState();if(blocked(s)||(action==='voice-save'?s.canManage===false:s.canEdit===false))throw Error('Bạn chưa có quyền sửa hoặc dự án đang bận.');
    const key=context(),ticket=++serial;working=true;pending={request,action};onWorking(true);controls();let saved=false;
    try{const result=await api(request.path,{method:'POST',body:JSON.stringify(request.body)});if(ticket!==serial||key!==context())return;
      validateDramaWrite(result,request,action,s.project.id);pending=null;dialogueDirty=voiceDirty=false;onDirty(false);await onSaved();saved=true;
      onMessage(result.current_for_project===false||result.current===false?'Yêu cầu đã hoàn tất ở phiên bản trước. Đã tải dữ liệu mới nhất; kiểm tra lại trước khi tiếp tục.':action==='take'?'Đã chọn tạo lại câu này. Kiểm tra phân vai, duyệt để tạo audio và áp lại thời lượng.':'Đã lưu. Kiểm tra phân vai, duyệt để tạo lời đọc; preview và video cuối cần nghe và duyệt riêng.');
    }catch(error){if(ticket===serial)onMessage(humanError(error),true);}finally{working=false;onWorking(false);controls();}if(saved)await load();
  }
  async function submit(action,extra={}){try{if(pending){if(pending.action!==action)throw Error('Thử lại thao tác chưa nhận được kết quả trước.');return await execute(pending.request,action);}
      if(voiceDirty)throw Error('Lưu giọng đang sửa hoặc bỏ chỉnh sửa trước.');const request=dramaRequest(getState(),page,action,{configuration:structuredClone(draft),requestKey:newKey(),clearLegacyVoicePolicy:legacy.checked,...extra});await execute(request,action);
    }catch(error){onMessage(humanError(error),true);}}
  function controls(){const s=getState(),stop=working||blocked(s),edit=stop||s.canEdit===false,manage=stop||s.canManage===false;root.hidden=!s.project||source(s);
    const unsupported=Boolean(editVoice&&(editVoice.definition.source_type!=='provider_preset'||editVoice.definition.provider!==catalog?.provider||editVoice.definition.model!==catalog?.model));
    for(const input of root.querySelectorAll('input,textarea,select'))input.disabled=edit||Boolean(pending);
    for(const input of castArea.querySelectorAll('input,textarea,select'))input.disabled=edit||voiceDirty||Boolean(pending);
    for(const input of manual.querySelectorAll('input,textarea,select'))input.disabled=manage||dialogueDirty||Boolean(pending)||unsupported&&input!==voiceChoice;
    target.disabled=edit||voiceDirty||Boolean(pending)||!draft;
    for(const b of root.querySelectorAll('button[data-drama-action]'))b.disabled=stop||Boolean(b._boundary)||(b._permission==='manage'?s.canManage===false:b._permission==='edit'?s.canEdit===false||voiceDirty:false)||b._saved&&(dialogueDirty||voiceDirty)||Boolean(pending&&b.getAttribute('data-drama-action')!==pending.action);
    loadButton.disabled=stop||dialogueDirty||voiceDirty||Boolean(pending);discard.disabled=stop||!dialogueDirty&&!voiceDirty||Boolean(pending);
    start.disabled=edit||!page||Boolean(draft)||Boolean(pending);save.disabled=edit||!draft||!dialogueDirty||voiceDirty||Boolean(pending&&pending.action!=='save');
    sortLines.disabled=edit||!draft||voiceDirty||!page?.shots?.length||Boolean(pending);
    compile.disabled=edit||!page?.casting||dialogueDirty||voiceDirty||Boolean(pending&&pending.action!=='compile');addLine.disabled=addCharacter.disabled=narrator.disabled=edit||!draft||voiceDirty||Boolean(pending);
    compile.disabled||=page?.compiled_current===true&&!pending;compile.title=page?.compiled_current?'Phân vai hiện tại đã kiểm tra. Chỉ kiểm tra lại sau khi thay đổi.':'';
    voiceSave.disabled=manage||unsupported||dialogueDirty||!catalog?.model||!preset.value||!voiceName.value?.trim()||Boolean(pending&&pending.action!=='voice-save');
    seriesSave.disabled=edit||!page?.casting||dialogueDirty||voiceDirty||!seriesName.value?.trim()||Boolean(pending&&pending.action!=='series-save');seriesApply.disabled=edit||!seriesChoice.value||dialogueDirty||voiceDirty||Boolean(pending&&pending.action!=='series-apply');
    voiceBrowser?.refresh();
  }
  function sync(){const key=context();if(binding!==key){binding=key;serial++;page=null;voices=[];catalog=null;series=[];draft=null;dialogueDirty=voiceDirty=clearLegacyChoice=false;pending=null;onDirty(false);draw();}controls();}
  loadButton.addEventListener('click',()=>load());discard.addEventListener('click',()=>load({discard:true}));
  root.addEventListener('toggle',()=>{if(root.open&&autoLoadContext!==context()&&!working&&!blocked(getState())){autoLoadContext=context();void load();}});
  registration.addEventListener('click',async()=>{if(registration.disabled)return;try{await api('/api/voice-library/import-installed',{method:'POST',body:JSON.stringify({acknowledged:true})});await load();}catch(error){onMessage(humanError(error),true);}});
  start.addEventListener('click',()=>{if(start.disabled)return;draft={narrator_enabled:false,characters:[{character_id:uid('chr_'),name:'Nhân vật 1',role:'character'}],casting:[],lines:page.shots.filter(s=>s.narration_enabled&&s.narration.trim()).map(s=>({line_id:uid('line_'),character_id:'',shot_id:s.shot_id,text:s.narration,enabled:true,speed:1,style:'neutral',pause_after_seconds:.15}))};changed();draw();controls();});
  addCharacter.addEventListener('click',()=>{if(addCharacter.disabled)return;draft.characters.push({character_id:uid('chr_'),name:`Nhân vật ${draft.characters.length+1}`,role:'character'});changed();draw();controls();});
  addLine.addEventListener('click',()=>{if(addLine.disabled)return;draft.lines.push({line_id:uid('line_'),character_id:'',shot_id:null,text:'',enabled:true,speed:1,style:'neutral',pause_after_seconds:.15});changed();draw();controls();});
  narrator.addEventListener('change',()=>{draft.narrator_enabled=narrator.checked;if(narrator.checked&&!draft.characters.some(c=>c.role==='narrator'))draft.characters.push({character_id:uid('chr_'),name:'Người kể',role:'narrator'});changed();draw();controls();});
  legacy.addEventListener('change',()=>{clearLegacyChoice=legacy.checked;changed();});
  save.addEventListener('click',()=>submit('save'));compile.addEventListener('click',()=>submit('compile'));seriesName.addEventListener('input',controls);seriesChoice.addEventListener('change',controls);
  seriesSave.addEventListener('click',()=>submit('series-save',{name:seriesName.value}));seriesApply.addEventListener('click',()=>submit('series-apply',{series:series.find(v=>v.series_id===seriesChoice.value)}));voiceChoice.addEventListener('change',fillVoice);
  for(const input of [voiceName,preset,license,reference,permission,rights])input.addEventListener(input===rights||input===preset?'change':'input',markVoice);
  voiceSave.addEventListener('click',async()=>{try{if(pending){if(pending.action!=='voice-save')throw Error('Thử lại thao tác trước.');return await execute(pending.request,'voice-save');}const s=getState();if(blocked(s)||s.canManage===false||dialogueDirty)throw Error('Owner mới được thay đổi thư viện giọng.');
      if(editVoice&&(editVoice.definition.source_type!=='provider_preset'||editVoice.definition.provider!==catalog?.provider||editVoice.definition.model!==catalog?.model))throw Error('Giao diện này chỉ sửa giọng preset local đang cấu hình. Chọn thêm giọng mới; bản cũ được giữ nguyên.');
      if(rights.checked&&![license.value,reference.value,permission.value].every(v=>v?.trim()))throw Error('Nhập giấy phép, nguồn và căn cứ được phép sử dụng.');
      const definition={display_name:voiceName.value.trim(),provider:catalog.provider,model:catalog.model,provider_voice_id:preset.value,locale:'vi-VN',source_type:'provider_preset',rights_status:rights.checked?'owner_declared':editVoice?.definition.rights_status==='blocked'?'blocked':'unknown',license:license.value?.trim()||null,source_reference:reference.value?.trim()||null,permission_reference:permission.value?.trim()||null,reference_asset_id:null,reference_sha256:null,cloning_consent:false};
      await execute({path:'/api/voice-library'+(editVoice?'/'+editVoice.voice_id:''),body:{request_key:newKey(),...(editVoice?{expected_version:editVoice.version}:{}),definition}},'voice-save');
    }catch(error){onMessage(error.message,true);}});
  function ensureLoaded(){if(root.open&&autoLoadContext!==context()&&!working&&!blocked(getState())){autoLoadContext=context();queueMicrotask(()=>void load());}}
  async function check(){if(!page||page.revision!==getState().project?.revision)await load();if(!page)return false;if(page.compiled_current)return true;await submit('compile');return page?.compiled_current===true;}
  sync();return {sync,controls,load,ensureLoaded,check,focusLine:id=>{if(/^line_[a-f0-9]{32}$/.test(id)){const row=root.querySelector(`[data-drama-line="${id}"]`);row?.scrollIntoView?.({block:'center',behavior:'smooth'});row?.querySelector('textarea')?.focus();}},isWorking:()=>working,isDirty:()=>dialogueDirty||voiceDirty};
}
