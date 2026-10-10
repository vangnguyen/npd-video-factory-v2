// Human layout decisions only. The schematic never claims decoded frame/AI evidence.
const fields=[['crop_x','Crop trái (%)',0,100],['crop_y','Crop trên (%)',0,100],['crop_width','Crop rộng (%)',.001,100],['crop_height','Crop cao (%)',.001,100],
  ['x','Dịch ngang (% kích thước hình sau crop)',-200,200],['y','Dịch dọc (% kích thước hình sau crop)',-200,200],
  ['scale','Scale (%)',.001,800],['rotation_degrees','Xoay (độ)',-360,360],['opacity','Độ hiện (%)',0,100]];
const finite=v=>typeof v==='number'&&Number.isFinite(v),percent=v=>Number((v*100).toFixed(8));
const defaults={crop:{x:0,y:0,width:1,height:1},transform:{x:0,y:0,scale:1,rotation_degrees:0},opacity:1};
export function visualDraft(clip){
  const c=clip.crop??defaults.crop,t=clip.transform??defaults.transform;
  return {crop_x:percent(c.x),crop_y:percent(c.y),crop_width:percent(c.width),crop_height:percent(c.height),x:percent(t.x),y:percent(t.y),scale:percent(t.scale),
    rotation_degrees:t.rotation_degrees,opacity:percent(clip.opacity??1)};
}
export function visualProperties(draft){
  if(!draft||Object.keys(draft).length!==fields.length||fields.some(([key,,min,max])=>!finite(draft[key])||draft[key]<min||draft[key]>max))throw Error('Crop, vị trí, scale, xoay và độ hiện phải là số trong giới hạn.');
  const crop={x:draft.crop_x/100,y:draft.crop_y/100,width:draft.crop_width/100,height:draft.crop_height/100};
  if(crop.x+crop.width>1.000001||crop.y+crop.height>1.000001)throw Error('Khung crop phải nằm trong hình nguồn.');
  return {crop,transform:{x:draft.x/100,y:draft.y/100,scale:draft.scale/100,rotation_degrees:draft.rotation_degrees},opacity:draft.opacity/100};
}
export function visualChanges(clip,draft){
  const value=visualProperties(draft),before=visualDraft(clip),changed={};
  for(const [group,keys] of [['crop',['x','y','width','height']],['transform',['x','y','scale','rotation_degrees']]]){
    for(const key of keys){const field=group==='crop'?'crop_'+key:key;if(draft[field]!==before[field]){changed[group]??={...(clip[group]??defaults[group])};changed[group][key]=value[group][key];}}
  }
  if(draft.opacity!==before.opacity)changed.opacity=value.opacity;return changed;
}
export function visualSchematic(draft,id='vf-visual-layout-bounds'){
  if(!/^[A-Za-z0-9_-]{4,100}$/.test(id))throw Error('Mã sơ đồ không hợp lệ.');
  const {crop,transform,opacity}=visualProperties(draft),box={x:12,y:18,w:180,h:112};
  const rectangle=`<rect x="${box.x+crop.x*box.w}" y="${box.y+crop.y*box.h}" width="${crop.width*box.w}" height="${crop.height*box.h}" fill="#17B9A640" stroke="#17B9A6"/>`;
  return `<svg viewBox="0 0 420 154" role="img" aria-label="Sơ đồ crop và bố trí, chưa phải khung hình render" style="max-width:620px;width:100%;height:auto"><defs><clipPath id="${id}"><rect x="222" y="18" width="180" height="112"/></clipPath></defs><rect x="12" y="18" width="180" height="112" fill="#142638" stroke="#6D879B"/>${rectangle}<g clip-path="url(#${id})"><rect x="222" y="18" width="180" height="112" fill="#142638"/><g transform="translate(${312+transform.x*180/crop.width} ${74+transform.y*112/crop.height}) scale(${transform.scale}) rotate(${transform.rotation_degrees})"><rect x="-90" y="-56" width="180" height="112" fill="#F5C451" opacity="${opacity}" stroke="#F5C451"/></g></g><rect x="222" y="18" width="180" height="112" fill="none" stroke="#6D879B"/><text x="12" y="149" fill="currentColor" font-size="11">Crop cố định dự kiến</text><text x="222" y="149" fill="currentColor" font-size="11">Sơ đồ bố trí trong vùng hình</text></svg>`;
}
const context=s=>JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.timeline?.version,s.timeline?.sha256,s.selected?.clip?.clip_id,
  s.selected?.track?.track_id,s.selected?.track?.locked,s.canEdit!==false,s.project?.archived===true,s.voice_input_current!==false]);
const bindingKey=s=>JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.timeline?.version,s.timeline?.sha256]);
const selectable=s=>Boolean(s.project?.id&&s.timeline?.sha256&&s.selected?.track?.type==='video'&&s.selected?.clip?.asset_id&&!s.selected.clip.metadata?.narrated_generated_voice);
export function initializeVisualProperties({root,dom=document,getState,onSave,onDirty=()=>{},onMessage=()=>{}}){
  root.replaceChildren();const controls={},create=(tag,text)=>{const n=dom.createElement(tag);if(text)n.textContent=text;return n;};
  const details=create('details'),summary=create('summary','Crop & bố trí hình'),status=create('p'),preview=create('div'),grid=create('div'),actions=create('div');
  grid.className='scene-grid';status.className='hint';actions.className='actions';details.append(summary,status,preview,grid,actions);root.append(details);
  for(const[key,label,min,max]of fields){const wrap=create('label',label),input=create('input');input.type='number';input.min=String(min);input.max=String(max);input.step='any';input.id=(root.id||'vf-visual')+'-'+key;wrap.append(input);grid.append(wrap);controls[key]=input;}
  const apply=create('button','Lưu crop & bố trí'),reset=create('button','Đặt về bố trí mặc định'),discard=create('button','Bỏ chỉnh sửa');
  for(const b of[apply,reset,discard]){b.type='button';b.className='secondary';actions.append(b);}
  let loaded=null,working=false,dirty=false,uncertain=null;
  const blocked=()=>{const s=getState();return !selectable(s)||loaded!==context(s)||uncertain===bindingKey(s)||working||s.canEdit===false||s.busy||s.active||s.project.archived||s.selected.track.locked||s.voice_input_current===false||(s.dirty&&s.dirtyPart!=='visual');};
  const draft=()=>Object.fromEntries(fields.map(([key])=>[key,controls[key].value.trim()===''?NaN:Number(controls[key].value)]));
  function paint(){try{preview.innerHTML=visualSchematic(draft(),(root.id||'vf-visual')+'-layout-bounds');status.textContent=(getState().selected?.clip.metadata?.reframe?'Đang dùng đường crop theo nguồn; khi render, đường đó ưu tiên hơn crop cố định bên dưới. Lưu crop khác sẽ thay đường này riêng cho clip. ':'')+'Sơ đồ chưa phải khung hình render. Sau khi lưu, tạo preview để kiểm tra hình, vùng brand, phụ đề và duyệt lại.';}
    catch(error){preview.innerHTML='';status.textContent=error.message;}}
  function buttons(){const stop=blocked();for(const input of Object.values(controls))input.disabled=stop;apply.disabled=stop||!dirty;reset.disabled=stop;discard.disabled=working||!dirty;}
  function fill(clip){for(const[key,value]of Object.entries(visualDraft(clip)))controls[key].value=String(value);paint();buttons();}
  function sync(){const s=getState();root.hidden=!selectable(s);if(loaded!==context(s)){loaded=context(s);dirty=false;onDirty(false);if(selectable(s))fill(s.selected.clip);else preview.innerHTML='';}buttons();}
  function change(){if(blocked())return;dirty=true;onDirty(true);paint();buttons();}
  async function save(){
    if(blocked()||!dirty)return;const s=getState(),key=loaded;let values;
    try{values=visualChanges(s.selected.clip,draft());if(!Object.keys(values).length){dirty=false;onDirty(false);buttons();return;}}
    catch(error){onMessage(error.message,true);return;}
    working=true;buttons();
    try{const result=await onSave(values,{project_id:s.project.id,revision:s.project.revision,timeline_version:s.timeline.version,timeline_sha256:s.timeline.sha256,
        clip_id:s.selected.clip.clip_id,workspace_id:s.workspace_id});
      if(result!==true)throw Error('Chưa xác nhận bản đã lưu. Đọc lại timeline trước khi thử tiếp.');
      if(key===context(getState()))throw Error('Bản lưu chưa đổi phiên bản. Đọc lại timeline trước khi thử tiếp.');
      dirty=false;onDirty(false);sync();
    }catch(error){uncertain=bindingKey(s);onMessage(error.message,true);if(key!==context(getState()))sync();}
    finally{working=false;buttons();}
  }
  for(const input of Object.values(controls))input.addEventListener('input',change);
  apply.addEventListener('click',save);reset.addEventListener('click',()=>{if(blocked())return;fill(defaults);change();});
  function discardDraft(){if(working)return;dirty=false;onDirty(false);sync();if(selectable(getState()))fill(getState().selected.clip);buttons();}
  discard.addEventListener('click',discardDraft);
  sync();return {sync,save,discardDraft,isDirty:()=>dirty,isWorking:()=>working,controls,apply,reset,discard,preview};
}
