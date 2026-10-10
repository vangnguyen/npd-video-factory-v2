// Explicit upload-to-track decisions. Reads/initialization never dispatch providers.
const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),integer=v=>Number.isSafeInteger(v)&&v>=0;
const asset=v=>typeof v==='string'&&/^[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}$/.test(v);
const track=v=>typeof v==='string'&&/^trk_[A-Za-z0-9_-]{4,60}$/.test(v),clip=v=>typeof v==='string'&&/^clip_[A-Za-z0-9_-]{4,60}$/.test(v);
const finite=v=>typeof v==='number'&&Number.isFinite(v),bool=v=>typeof v==='boolean';
const PART='source_media_tracks';
export function validateSourceMediaTracks(v,s,{revision=s.project?.revision,version=null,page=1}={}){
  if(v?.timeline_mode!==undefined&&!['source','narrated',null].includes(v.timeline_mode)||v?.pending_generated_tracks!==undefined&&!bool(v.pending_generated_tracks))throw Error('Chế độ track không hợp lệ.');
  if(v?.schema_version!=='native-source-media-tracks-v1'||v.workspace_id!==s.workspace_id||v.project_id!==s.project?.id||v.revision!==revision
    ||!bool(v.timeline_available)||v.provider_calls!==0||v.publishing_enabled!==false||v.human_review_required!==true||v.source_media_mutated!==false)throw Error('Track không đúng dự án hoặc phiên bản.');
  if(v.timeline_available){if(!integer(v.timeline_version)||v.timeline_version<1||!sha(v.timeline_sha256)||!finite(v.duration_seconds)||v.duration_seconds<=0||v.duration_seconds>600||version!==null&&v.timeline_version!==version)throw Error('Timeline chưa khớp dữ liệu đã đọc.');}
  else if(v.timeline_version!==null||v.timeline_sha256!==null||v.duration_seconds!==null)throw Error('Timeline không hợp lệ.');
  if(!Array.isArray(v.assets)||v.assets.length>200||!integer(v.assets_total)||v.assets_total<v.assets.length||v.assets_truncated!==(v.assets_total>200))throw Error('Danh sách tư liệu không hợp lệ.');
  const ids=new Set();for(const a of v.assets){if(!asset(a.asset_id)||ids.has(a.asset_id)||!sha(a.asset_sha256)||!['audio','subtitle'].includes(a.kind)||typeof a.filename!=='string'||!a.filename||a.filename.length>200
      ||!finite(a.duration_seconds)||a.duration_seconds<=0||a.duration_seconds>600||typeof a.rights_status!=='string'||!bool(a.word_timing_available))throw Error('Nguồn track không hợp lệ.');ids.add(a.asset_id);
    if(a.transcript_id!==null&&(!/^trn_[a-f0-9]{24}$/.test(a.transcript_id)||!integer(a.transcript_version)||a.transcript_version<1||!sha(a.analysis_sha256)))throw Error('Bản lời nói không hợp lệ.');
    if(a.transcript_id===null&&(a.transcript_version!==null||a.analysis_sha256!==null||a.word_timing_available))throw Error('Chưa có bằng chứng lời nói.');
    if(a.kind==='subtitle'&&(!integer(a.cue_count)||a.cue_count<1||a.transcript_id!==null))throw Error('Cue nguồn không hợp lệ.');
  }
  if(['source_video_assets','source_video_assets_total','source_video_assets_truncated','source_video_mapping_available'].some(k=>v[k]!==undefined)){
    if(!Array.isArray(v.source_video_assets)||v.source_video_assets.length>200||!integer(v.source_video_assets_total)||v.source_video_assets.length!==Math.min(200,v.source_video_assets_total)||v.source_video_assets_truncated!==(v.source_video_assets_total>200)||v.source_video_mapping_available!==(v.source_video_assets_total>0))throw Error('Danh sách video nguồn không hợp lệ.');
    const videos=new Set();for(const a of v.source_video_assets){if(!asset(a.asset_id)||videos.has(a.asset_id)||!sha(a.asset_sha256)||typeof a.filename!=='string'||!a.filename||a.filename.length>200||!finite(a.duration_seconds)||a.duration_seconds<=0||a.duration_seconds>600)throw Error('Video nguồn chưa được xác minh.');videos.add(a.asset_id);}
  }
  if(!Array.isArray(v.tracks)||v.tracks.length>32)throw Error('Các track không hợp lệ.');const tracks=new Map();
  for(const t of v.tracks){if(!track(t.track_id)||tracks.has(t.track_id)||!['audio','video','text','metadata'].includes(t.type)||typeof t.label!=='string'||!t.label||t.label.length>160||![t.locked,t.muted,t.disabled].every(bool))throw Error('Track đã thay đổi.');tracks.set(t.track_id,t);}
  if(v.caption_page!==page||v.caption_page_size!==50||!integer(v.captions_total)||!Array.isArray(v.captions)||v.captions.length>50||v.captions.length!==Math.min(50,Math.max(0,v.captions_total-(page-1)*50))||v.captions_has_next!==((page-1)*50+50<v.captions_total))throw Error('Trang phụ đề không hợp lệ.');
  const captions=new Set();for(const c of v.captions){const t=tracks.get(c.track_id);if(!t||t.type!=='text'||t.kind!=='subtitles'||!clip(c.clip_id)||captions.has(c.clip_id)||typeof c.text!=='string'||!c.text.trim()||c.text.length>4000
      ||!finite(c.timeline_start)||c.timeline_start<0||!finite(c.duration)||c.duration<=0||c.timeline_start+c.duration>v.duration_seconds+.05||c.track_locked!==t.locked||c.track_disabled!==t.disabled||!bool(c.disabled)||!bool(c.has_word_timing))throw Error('Caption không hợp lệ.');captions.add(c.clip_id);
    if(c.source_video_asset_id!==undefined||c.source_video_mapping_mode!==undefined){if(c.source_video_asset_id===null){if(c.source_video_mapping_mode!==null)throw Error('Ánh xạ caption không hợp lệ.');}
      else if(!asset(c.source_video_asset_id)||!['follow_video','human_layout','disabled'].includes(c.source_video_mapping_mode)||(c.source_video_mapping_mode==='disabled')!==Boolean(c.track_disabled||c.disabled))throw Error('Ánh xạ caption không hợp lệ.');}}
  if(!Array.isArray(v.imports)||v.imports.length>50||!integer(v.imports_total)||v.imports_total<v.imports.length||v.imports_truncated!==(v.imports_total>50))throw Error('Lịch sử nhập không hợp lệ.');
  for(const r of v.imports)if(!/^smi_[a-f0-9]{24}$/.test(r.import_id??'')||!['audio','subtitles'].includes(r.operation)||!asset(r.asset_id)||!sha(r.asset_sha256)||!bool(r.inherited)||!Number.isFinite(Date.parse(r.created_at)))throw Error('Bản nhập không hợp lệ.');
  if(v.subtitle_templates?.version!=='1.0'||!Array.isArray(v.subtitle_templates.templates)||!v.subtitle_templates.templates.length)throw Error('Mẫu phụ đề chưa được xác minh.');
  const templates=new Set();for(const t of v.subtitle_templates.templates){if(typeof t.template_ref!=='string'||!t.template_ref||templates.has(t.template_ref)||!bool(t.requires_word_timestamps)||!t.style||typeof t.style.animation!=='string')throw Error('Mẫu phụ đề không hợp lệ.');templates.add(t.template_ref);}
  if(v.selected_subtitle_template_ref!==null&&!templates.has(v.selected_subtitle_template_ref))throw Error('Mẫu timeline đã thay đổi.');
  const privacy=(x,depth=0)=>{if(depth>30)throw Error('Dữ liệu track quá sâu.');if(x&&typeof x==='object')for(const[k,c]of Object.entries(x)){if(/^(token|access_token|refresh_token|token_path|credential_path|private_path|authorization)$/i.test(k))throw Error('Dữ liệu track chứa thông tin riêng tư.');privacy(c,depth+1);}};privacy(v);
  return v;
}
export function initializeSourceMediaTracks({api,getState,root=document,onWorking=()=>{},onSaved=async()=>{},onMessage=()=>{},onDirty=()=>{},requestKey=()=>crypto.randomUUID()}){
  const card=root.getElementById('native-source-media-tracks-card');card.hidden=false;card.replaceChildren();
  const node=(tag,text,id)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(id)n.id='native-source-media-tracks-'+id;return n;};
  const button=(text,id)=>{const n=node('button',text,id);n.type='button';n.className='secondary';return n;};
  const controlsList=[],choice=(parent,text,id)=>{const n=node('select',null,id),l=node('label',text);l.append(n);parent.append(l);controlsList.push(n);return n;};
  const number=(parent,text,id,value,min=0,max=600)=>{const n=node('input',null,id);Object.assign(n,{type:'number',value:String(value),min:String(min),max:String(max),step:'any'});const l=node('label',text);l.append(n);parent.append(l);controlsList.push(n);return n;};
  const check=(parent,text,id)=>{const n=node('input',null,id);n.type='checkbox';n.checked=false;const l=node('label',text);l.className='check';l.append(n);parent.append(l);controlsList.push(n);return n;};
  const read=button('Đọc track và tư liệu đã lưu','read'),status=node('p','Tạo bản dựng video nguồn, hoặc áp dụng lời đọc đã đo cho storyboard, rồi đọc tư liệu.','status');
  const audioBox=node('fieldset'),subtitleBox=node('fieldset'),captionBox=node('fieldset');audioBox.className=subtitleBox.className='scene-grid';
  audioBox.append(node('legend','Đặt audio vào bản dựng'));
  const audio=choice(audioBox,'Audio đã tải lên','audio'),role=choice(audioBox,'Vai trò','role'),audioTrack=choice(audioBox,'Track đích','audio-track'),replace=check(audioBox,'Thay toàn bộ clip của track đã chọn · giữ lịch sử','replace-audio');
  const sourceStart=number(audioBox,'Bắt đầu trong audio nguồn (s)','source-start',0),sourceEnd=number(audioBox,'Kết thúc trong audio nguồn (s)','source-end',1),timelineStart=number(audioBox,'Vị trí trên timeline (s)','timeline-start',0),volume=number(audioBox,'Âm lượng (0–2)','volume',1,0,2),
    fadeIn=number(audioBox,'Fade vào (s)','fade-in',0,0,5),fadeOut=number(audioBox,'Fade ra (s)','fade-out',0,0,5),loop=check(audioBox,'Lặp nhạc tới mốc timeline đã chọn','loop'),until=number(audioBox,'Lặp tới (s)','repeat-until',1),crossfade=number(audioBox,'Crossfade vòng lặp (s)','crossfade',0,0,1);
  const withCaptions=check(audioBox,'Tạo phụ đề từ lời nhận diện đã lưu','audio-captions'),audioCaptionTrack=choice(audioBox,'Track phụ đề · thay nội dung của track đã chọn','audio-caption-track'),audioTemplate=choice(audioBox,'Mẫu phụ đề cho audio','audio-template'),saveAudio=button('Lưu audio vào timeline','save-audio');audioBox.append(saveAudio);
  subtitleBox.append(node('legend','Nhập phụ đề SRT / VTT'));
  const subtitle=choice(subtitleBox,'File phụ đề đã tải lên','subtitle'),timebase=choice(subtitleBox,'Mốc thời gian trong file','timebase'),sourceVideo=choice(subtitleBox,'Video nguồn dùng mốc thời gian trong file','source-video'),offset=number(subtitleBox,'Dịch phụ đề trên timeline (s)','offset',0,-600,600),trim=check(subtitleBox,'Cho phép cắt/bỏ phần cue ngoài timeline · cần review','trim'),subtitleTrack=choice(subtitleBox,'Track phụ đề · thay nội dung của track đã chọn','subtitle-track'),subtitleTemplate=choice(subtitleBox,'Mẫu phụ đề','subtitle-template'),saveSubtitle=button('Lưu cue vào timeline','save-subtitle');subtitleBox.append(saveSubtitle);
  const sourceVideoLabel=Array.from(subtitleBox.children).find(n=>Array.from(n.children).includes(sourceVideo));
  captionBox.append(node('legend','Sửa caption trên timeline'));
  const captionTemplate=choice(captionBox,'Mẫu sau khi sửa caption','caption-template'),captionRows=node('div',null,'caption-rows'),previous=button('Trang trước','previous'),next=button('Trang sau','next'),saveCaptions=button('Lưu chữ và thời điểm caption','save-captions');captionBox.append(captionRows,previous,next,saveCaptions);
  card.append(node('summary','Audio & phụ đề trong bản dựng'),node('p','Mọi thay đổi lưu vào cùng timeline và yêu cầu preview/duyệt lại. Byte nguồn và bản dựng cũ được giữ. Chữ mới không kế thừa timestamp từng từ cũ.'),read,status,audioBox,subtitleBox,captionBox);
  const staticControls=controlsList.length;
  let value=null,working=false,scope='',generation=0,ownDirty=false;const fields=new Map(),pending=new Map();
  const externalDirty=s=>s.dirty&&s.dirtyPart!==PART;
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.canEdit,s.active,s.project?.archived,Boolean(externalDirty(s))]);};
  const audioAsset=()=>value?.assets.find(a=>a.asset_id===audio.value),subtitleAsset=()=>value?.assets.find(a=>a.asset_id===subtitle.value),videoAsset=()=>value?.source_video_assets?.find(a=>a.asset_id===sourceVideo.value);
  function options(select,items,chosen){select.replaceChildren();for(const[key,label]of items){const o=node('option',label);o.value=key;select.append(o);}select.value=items.some(([k])=>k===chosen)?chosen:items[0]?.[0]??'';}
  function trackOptions(select,kind,preferExisting=false){const available=(value?.tracks??[]).filter(t=>t.kind===kind&&!t.locked&&!t.disabled);options(select,[['','Tạo track mới'],...available.map(t=>[t.track_id,t.label])],preferExisting?available[0]?.track_id:null);}
  function controls(){const s=getState(),busy=working||s.busy,editable=!busy&&s.canEdit&&!externalDirty(s)&&!s.active&&!s.project?.archived&&value?.timeline_available;
    read.disabled=busy||!s.project;for(const c of controlsList)c.disabled=!editable;
    const mapping=timebase.value==='source'&&value?.source_video_mapping_available===true;sourceVideoLabel.hidden=sourceVideo.hidden=!mapping;sourceVideo.disabled=!editable||!mapping;
    saveAudio.disabled=!editable||!audioAsset();saveSubtitle.disabled=!editable||!subtitleAsset()||mapping&&!videoAsset();saveCaptions.disabled=!editable||![...fields.values()].some(f=>!f.source.track_locked);
    previous.disabled=busy||!value||value.caption_page<=1;next.disabled=busy||!value?.captions_has_next;
    replace.disabled=!editable||!audioTrack.value;loop.disabled=!editable||role.value!=='music';until.disabled=crossfade.disabled=!editable||role.value!=='music'||!loop.checked;
    withCaptions.disabled=!editable||role.value!=='voice'||!audioAsset()?.transcript_id;
    audioCaptionTrack.disabled=audioTemplate.disabled=!editable||!withCaptions.checked||withCaptions.disabled;
    timebase.disabled=!editable||value?.timeline_mode==='narrated'&&!value.source_video_mapping_available;
    for(const f of fields.values())for(const input of[f.text,f.start,f.duration])input.disabled=!editable||f.source.track_locked;
  }
  function clear(){value=null;fields.clear();pending.clear();controlsList.splice(staticControls);captionRows.replaceChildren();for(const s of[audio,subtitle,sourceVideo,audioTrack,audioCaptionTrack,subtitleTrack])s.replaceChildren();audioBox.hidden=subtitleBox.hidden=captionBox.hidden=true;if(ownDirty){ownDirty=false;onDirty(false);}}
  function sync(){const now=context();if(now!==scope){scope=now;generation++;clear();}controls();}
  function changed(){ownDirty=true;onDirty(true);controls();}
  function render(){audioBox.hidden=subtitleBox.hidden=!value?.timeline_available;captionBox.hidden=!value?.timeline_available;
    options(audio,value.assets.filter(a=>a.kind==='audio').map(a=>[a.asset_id,a.filename]));options(role,[['voice','Giọng nói'],['music','Nhạc nền']],audioAsset()?.role==='music'?'music':'voice');
    options(subtitle,value.assets.filter(a=>a.kind==='subtitle').map(a=>[a.asset_id,a.filename]));options(timebase,[['timeline','Timeline hiện tại'],['source','Video nguồn · ánh xạ qua các đoạn đã cắt']]);
    options(sourceVideo,[['','Chọn video đang dùng trong shot'],...(value.source_video_assets??[]).map(a=>[a.asset_id,a.filename])]);
    for(const s of[audioCaptionTrack,subtitleTrack])trackOptions(s,'subtitles',true);trackOptions(audioTrack,role.value);
    const templates=value.subtitle_templates.templates,defaultTemplate=value.selected_subtitle_template_ref??templates.find(t=>!t.requires_word_timestamps)?.template_ref;
    for(const s of[audioTemplate,subtitleTemplate,captionTemplate])options(s,templates.map(t=>[t.template_ref,(t.name??t.label??t.template_ref)+(t.requires_word_timestamps?' · cần timestamp từng từ':'')]),s===subtitleTemplate?templates.find(t=>!t.requires_word_timestamps)?.template_ref:defaultTemplate);
    sourceStart.value=timelineStart.value=offset.value='0';sourceEnd.value=String(audioAsset()?.duration_seconds??1);volume.value=role.value==='music'?'0.12':'1';fadeIn.value=fadeOut.value=crossfade.value='0';until.value=String(value.duration_seconds);replace.checked=loop.checked=withCaptions.checked=trim.checked=false;
    fields.clear();controlsList.splice(staticControls);captionRows.replaceChildren();for(const c of value.captions){const box=node('section'),text=node('textarea');text.value=c.text;text.maxLength=4000;text.rows=2;const label=node('label','Caption'+(c.track_locked?' · track đã khóa':'')+(c.source_video_mapping_mode==='follow_video'?' · theo các đoạn video nguồn':c.source_video_mapping_mode==='human_layout'?' · vị trí thủ công':c.source_video_mapping_mode==='disabled'?' · ánh xạ đã tắt':''));label.append(text);box.append(label);
      const start=number(box,'Vị trí timeline (s)',null,c.timeline_start),duration=number(box,'Thời lượng hiển thị (s)',null,c.duration,.05,600);captionRows.append(box);fields.set(c.clip_id,{source:c,text,start,duration});
      for(const n of[text,start,duration])n.addEventListener('input',changed);}
    if(value.timeline_mode==='narrated')timebase.value='timeline';
    for(const option of timebase.children)if(option.value==='source')option.disabled=value.timeline_mode==='narrated'&&!value.source_video_mapping_available;
    status.textContent=value.timeline_available?`Timeline bản ${value.timeline_version} · ${value.assets_total} tư liệu audio/phụ đề · ${value.captions_total} caption, trang ${value.caption_page}. ${value.pending_generated_tracks?'Track lời đọc/caption là projection từ PCM đã đo; chọn Lưu sẽ gắn vào timeline. ':''}Lưu một thao tác rồi kiểm tra preview.`:'Chưa có timeline phù hợp; phân tích video nguồn và tạo bản dựng, hoặc áp dụng lời đọc đã đo cho storyboard.';controls();}
  async function run(fn){sync();const s=getState();if(working||s.busy||!s.project)return;const expected=context(),ticket=++generation;working=true;onWorking(true);controls();const accept=()=>expected===context()&&ticket===generation;
    try{await fn(s,accept);}catch(e){if(accept())onMessage(e.message,true);}finally{working=false;onWorking(false);sync();}}
  const path=s=>'/api/projects/'+s.project.id+'/auto-edit/media-tracks';
  async function load(page=1){if(!integer(page)||page<1||page>1000)throw Error('Trang phụ đề không hợp lệ.');await run(async(s,accept)=>{const response=await api(path(s)+(page===1?'':'?caption_page='+page));if(!accept())return;
    const verified=validateSourceMediaTracks(response,s,{page});if(ownDirty){ownDirty=false;onDirty(false);}value=verified;pending.clear();render();});}
  function requireWrite(s){if(!value?.timeline_available||!s.canEdit||externalDirty(s)||s.active||s.project.archived)throw Error('Đọc bản dựng đang chỉnh sửa được trước khi lưu track.');}
  function n(field){if(!String(field.value).trim())throw Error('Điền đầy đủ các mốc và giá trị.');const v=Number(field.value);if(!finite(v))throw Error('Mốc thời gian/âm lượng phải là số hữu hạn.');return v;}
  function binding(s,a){return{revision:s.project.revision,expected_version:value.timeline_version,timeline_sha256:value.timeline_sha256,asset_id:a.asset_id,asset_sha256:a.asset_sha256};}
  function keyed(type,body){const signature=JSON.stringify(body),old=pending.get(type);if(old?.signature===signature)return old.body;const key=requestKey();if(typeof key!=='string'||key.length<16||key.length>128)throw Error('Khóa yêu cầu không hợp lệ.');const request={...body,request_key:key};pending.set(type,{signature,body:request});return request;}
  async function save(type,build){await run(async(s,accept)=>{requireWrite(s);const request=build(s),response=await api(path(s)+'/'+type,request);if(!accept())return;const m=response.mutation;
    if(!m||type==='captions'&&!bool(m.changed))throw Error('Biên nhận thay đổi không hợp lệ.');
    const changed=type==='captions'?m.changed:true,verified=validateSourceMediaTracks(response,s,{revision:s.project.revision+(changed?1:0),version:value.timeline_version+(changed?1:0)});
    if(type!=='captions'){
      if(m.operation!==type||!/^smi_[a-f0-9]{24}$/.test(m.import_id??'')||!bool(m.replayed)||m.asset_id!==request.asset_id||m.asset_sha256!==request.asset_sha256||!sha(m.request_sha256)||!track(m.track_id)||!Array.isArray(m.clip_ids)||!m.clip_ids.length||m.clip_ids.some(id=>!clip(id))||new Set(m.clip_ids).size!==m.clip_ids.length)throw Error('Nguồn nhập hoặc clip trả về khác yêu cầu.');
      if(type==='audio'&&(JSON.stringify(m.source_window)!==JSON.stringify([request.source_start,request.source_end])||!Array.isArray(m.timeline_window)||Math.abs(m.timeline_window[0]-request.timeline_start)>1e-6||Math.abs(m.timeline_window[1]-(request.repeat_until??request.timeline_start+request.source_end-request.source_start))>1e-6))throw Error('Khoảng audio trả về khác lựa chọn.');
      if(type==='subtitles'&&(m.timebase!==request.timebase||!integer(m.caption_count)||m.caption_count!==m.clip_ids.length||!integer(m.clipped_intervals)||!integer(m.dropped_intervals)))throw Error('Khoảng cue trả về chưa khớp.');
      if(type==='subtitles'&&request.source_video_asset_id&&(m.source_video_asset_id!==request.source_video_asset_id||m.source_video_asset_sha256!==request.source_video_asset_sha256||m.mapping_schema!=='native-source-video-caption-mapping-v1'))throw Error('Video ánh xạ trả về khác lựa chọn.');
    }
    if(type==='captions'){const ids=new Set(request.edits.map(e=>e.clip_id));if(!Array.isArray(m.clip_ids)||m.clip_ids.some(id=>!ids.has(id)))throw Error('Biên nhận caption khác lựa chọn.');}
    ownDirty=false;onDirty(false);pending.delete(type);await onSaved(response);
    const current=getState();if(current.workspace_id===s.workspace_id&&current.project?.id===response.project_id&&current.project.revision===response.revision&&current.canEdit===s.canEdit&&!externalDirty(current)){
      scope=context();generation++;value=verified;render();status.textContent=type==='subtitles'?`Đã nhập ${m.caption_count} caption; ${m.clipped_intervals} khoảng cắt ngắn, ${m.dropped_intervals} khoảng bỏ. Kiểm tra preview rồi duyệt lại.`:'Đã lưu vào timeline. Kiểm tra preview và duyệt lại.';}
  });}
  async function applyAudio(){await save('audio',s=>{const a=audioAsset();if(!a)throw Error('Chọn audio đã tải lên.');const captions=withCaptions.checked;
    if(captions&&(role.value!=='voice'||!a.transcript_id))throw Error('Nhận diện lời nói trước khi tạo caption cho audio.');
    return keyed('audio',{...binding(s,a),role:role.value,track_id:audioTrack.value||null,replace_existing:replace.checked,source_start:n(sourceStart),source_end:n(sourceEnd),timeline_start:n(timelineStart),volume:n(volume),fade_in_seconds:n(fadeIn),fade_out_seconds:n(fadeOut),
      repeat_until:loop.checked?n(until):null,crossfade_seconds:loop.checked?n(crossfade):0,captions:captions?{transcript_id:a.transcript_id,analysis_sha256:a.analysis_sha256,replace_track_id:audioCaptionTrack.value||null,subtitle_template_ref:audioTemplate.value}:null});});}
  async function applySubtitles(){await save('subtitles',s=>{const a=subtitleAsset();if(!a)throw Error('Chọn SRT/VTT đã tải lên.');const mapping={};
    if(timebase.value==='source'&&(value.source_video_mapping_available||value.timeline_mode==='narrated')){const video=videoAsset();if(!value.source_video_mapping_available||!video)throw Error('Chọn video đang dùng trong shot để ánh xạ phụ đề.');mapping.source_video_asset_id=video.asset_id;mapping.source_video_asset_sha256=video.asset_sha256;}
    return keyed('subtitles',{...binding(s,a),timebase:timebase.value,offset_seconds:n(offset),trim_to_timeline:trim.checked,replace_track_id:subtitleTrack.value||null,subtitle_template_ref:subtitleTemplate.value,...mapping});});}
  async function saveCaptionEdits(){await save('captions',s=>{const edits=[...fields.entries()].filter(([,f])=>!f.source.track_locked).map(([clip_id,f])=>({clip_id,text:f.text.value,timeline_start:n(f.start),duration:n(f.duration)}));if(!edits.length||edits.some(e=>!e.text?.trim()))throw Error('Caption cần chữ và track có thể chỉnh sửa.');
    return{revision:s.project.revision,expected_version:value.timeline_version,timeline_sha256:value.timeline_sha256,edits,subtitle_template_ref:captionTemplate.value};});}
  for(const c of controlsList)c.addEventListener(c.type==='checkbox'||c.tagName==='SELECT'?'change':'input',changed);
  audio.addEventListener('change',()=>{sourceStart.value='0';sourceEnd.value=String(audioAsset()?.duration_seconds??1);withCaptions.checked=false;controls();});
  role.addEventListener('change',()=>{trackOptions(audioTrack,role.value);replace.checked=loop.checked=withCaptions.checked=false;volume.value=role.value==='music'?'0.12':'1';controls();});
  timebase.addEventListener('change',controls);sourceVideo.addEventListener('change',controls);
  read.addEventListener('click',()=>load(1));previous.addEventListener('click',()=>load(Math.max(1,(value?.caption_page??1)-1)));next.addEventListener('click',()=>load((value?.caption_page??0)+1));
  saveAudio.addEventListener('click',applyAudio);saveSubtitle.addEventListener('click',applySubtitles);saveCaptions.addEventListener('click',saveCaptionEdits);
  sync();return{load,applyAudio,applySubtitles,saveCaptionEdits,sync,isWorking:()=>working,currentBinding:()=>value,fields};
}
