// Typed human clip decisions. Preview remains the rendered review surface.
const definitions=[['brightness','Độ sáng (%)',0,200,100],['contrast','Tương phản (%)',0,300,100],['saturation','Bão hòa màu (%)',0,300,100],
  ['hue_rotate','Xoay hue (độ)',-180,180,1],['grayscale','Đen trắng (%)',0,100,100],['blur','Blur (% chiều rộng vùng hình)',0,2.5,100]];
const neutral={brightness:1,contrast:1,saturation:1,hue_rotate:0,grayscale:0,blur:0};
const finite=v=>typeof v==='number'&&Number.isFinite(v);
export function clipStyleDraft(clip){const effects=clip.effects??[];return {transition_in:{...(clip.transition_in??{kind:'cut',duration_seconds:0})},transition_out:{...(clip.transition_out??{kind:'cut',duration_seconds:0})},
  ...Object.fromEntries(definitions.map(([type,,,,factor])=>[type,(effects.find(e=>e.type===type)?.value??neutral[type])*factor]))};}
export function clipStyleChanges(clip,draft,{visual=true,reset=false}={}){
  const changes={},before=clipStyleDraft(clip),kinds=visual?['none','cut','fade','crossfade','slide']:['none','cut','fade','crossfade'];
  for(const key of['transition_in','transition_out']){const t=draft[key];if(t?.kind===before[key].kind&&t?.duration_seconds===before[key].duration_seconds)continue;
    if(!t||!kinds.includes(t.kind)||!finite(t.duration_seconds)||t.duration_seconds<0||t.duration_seconds>Math.min(5,clip.duration)+.000001||
      (['none','cut'].includes(t.kind)?t.duration_seconds!==0:t.duration_seconds<=0))throw Error('Transition cần loại phù hợp và thời lượng nằm trong clip.');
    if(t.kind!==before[key].kind||t.duration_seconds!==before[key].duration_seconds)changes[key]={...t};}
  if(visual){const effects=reset?[]:(clip.effects??[]).map(e=>({...e}));let edited=reset&&effects.length!==(clip.effects??[]).length;
    for(const[type,,lo,hi,factor]of definitions){if(draft[type]===before[type]&&!reset)continue;
      if(!finite(draft[type])||draft[type]<lo||draft[type]>hi)throw Error('Hiệu ứng cần số hữu hạn trong giới hạn.');edited=true;const index=effects.findIndex(e=>e.type===type),value=draft[type]/factor;
      if(value===neutral[type]){if(index>=0)effects.splice(index,1);}else if(index>=0)effects[index]={type,value};else effects.push({type,value});}
    if(edited)changes.effects=effects;}
  return changes;
}
const context=s=>JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.timeline?.version,s.timeline?.sha256,s.selected?.track?.track_id,s.selected?.clip?.clip_id,s.selected?.track?.locked,s.canEdit!==false,s.project?.archived===true,s.voice_input_current!==false]);
const key=s=>JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.timeline?.version,s.timeline?.sha256]);
const selectable=s=>Boolean(s.project?.id&&s.timeline?.sha256&&['video','audio'].includes(s.selected?.track?.type)&&s.selected?.clip?.asset_id&&!s.selected.clip.metadata?.narrated_generated_voice);
export function initializeClipStyle({root,dom=document,getState,onSave,onDirty=()=>{},onMessage=()=>{}}){
  root.replaceChildren();const create=(tag,text)=>{const n=dom.createElement(tag);if(text)n.textContent=text;return n;};
  const details=create('details'),summary=create('summary','Hiệu ứng & transition'),status=create('p'),grid=create('div'),effectGrid=create('div'),actions=create('div');
  grid.className=effectGrid.className='scene-grid';status.className='hint';actions.className='actions';details.append(summary,status,grid,effectGrid,actions);root.append(details);
  const controls={};for(const direction of['in','out']){const label=create('label',direction==='in'?'Transition đầu clip':'Transition cuối clip'),select=create('select'),duration=create('input');duration.type='number';duration.min='0';duration.max='5';duration.step='any';
    for(const[kind,name]of[['cut','Cắt thẳng'],['none','Không'],['fade','Fade'],['crossfade','Crossfade · cần clip kề/overlap'],['slide','Trượt hình']]){const o=create('option',name);o.value=kind;select.append(o);}
    label.append(select);grid.append(label);const time=create('label','Thời lượng (s)');time.append(duration);grid.append(time);controls['transition_'+direction]={kind:select,duration};}
  for(const[type,label,lo,hi]of definitions){const wrap=create('label',label),input=create('input');input.type='number';input.min=String(lo);input.max=String(hi);input.step='any';wrap.append(input);effectGrid.append(wrap);controls[type]=input;}
  const save=create('button','Lưu hiệu ứng & transition'),reset=create('button','Đặt về hiệu ứng mặc định'),discard=create('button','Bỏ chỉnh sửa');for(const n of[save,reset,discard]){n.type='button';n.className='secondary';actions.append(n);}
  let loaded=null,dirty=false,working=false,uncertain=null,resetEffects=false;
  const blocked=()=>{const s=getState();return !selectable(s)||loaded!==context(s)||working||uncertain===key(s)||s.canEdit===false||s.busy||s.active||s.project.archived||s.selected.track.locked||s.voice_input_current===false||s.dirty&&s.dirtyPart!=='style';};
  const inputs=()=>Object.values(controls).flatMap(c=>c.kind?[c.kind,c.duration]:[c]);
  function buttons(){const s=getState(),stop=blocked(),visual=s.selected?.track.type==='video';effectGrid.hidden=!visual;for(const n of inputs())n.disabled=stop;
    for(const c of[controls.transition_in,controls.transition_out]){for(const o of c.kind.children)if(o.value==='slide')o.disabled=!visual;c.duration.disabled=stop||['none','cut'].includes(c.kind.value);}
    save.disabled=stop||!dirty;reset.disabled=stop;discard.disabled=working||!dirty;}
  function fill(clip){const d=clipStyleDraft(clip);for(const[name,value]of Object.entries(d)){const c=controls[name];if(c.kind){c.kind.value=value.kind;c.duration.value=String(value.duration_seconds);}else c.value=String(value);}buttons();}
  function sync(){const s=getState();root.hidden=!selectable(s);if(loaded!==context(s)){loaded=context(s);dirty=false;resetEffects=false;onDirty(false);if(selectable(s))fill(s.selected.clip);}
    status.textContent='Lưu chỉ các giá trị đổi. Crossfade hình cần clip kề trong cùng track; crossfade audio cần khoảng overlap. Tạo preview, kiểm tra hình/âm thanh rồi duyệt lại.';buttons();}
  function changed(){if(blocked())return;dirty=true;onDirty(true);buttons();}
  const draft=()=>Object.fromEntries(Object.entries(controls).map(([name,c])=>[name,c.kind?{kind:c.kind.value,duration_seconds:c.duration.value.trim()===''?NaN:Number(c.duration.value)}:c.value.trim()===''?NaN:Number(c.value)]));
  async function apply(){if(blocked()||!dirty)return;const s=getState(),captured=context(s);let values;
    try{values=clipStyleChanges(s.selected.clip,draft(),{visual:s.selected.track.type==='video',reset:resetEffects});if(!Object.keys(values).length){dirty=false;onDirty(false);buttons();return;}}
    catch(error){onMessage(error.message,true);return;}
    working=true;buttons();try{const result=await onSave(values,{workspace_id:s.workspace_id,project_id:s.project.id,revision:s.project.revision,timeline_version:s.timeline.version,timeline_sha256:s.timeline.sha256,clip_id:s.selected.clip.clip_id});
      if(result!==true||captured===context(getState()))throw Error('Chưa xác nhận bản lưu mới. Đọc lại timeline trước khi thử tiếp.');dirty=false;onDirty(false);sync();}
    catch(error){uncertain=key(s);onMessage(error.message,true);if(captured!==context(getState()))sync();}finally{working=false;buttons();}}
  for(const input of inputs())input.addEventListener(input.tagName==='SELECT'?'change':'input',()=>{if(input.tagName==='SELECT'){const c=Object.values(controls).find(c=>c.kind===input);if(c){const cut=['none','cut'].includes(c.kind.value);c.duration.value=cut?'0':String(Math.min(.25,getState().selected?.clip.duration??.25));}}changed();});
  reset.addEventListener('click',()=>{if(blocked())return;const c=getState().selected.clip;fill({...c,effects:[],transition_in:{kind:'cut',duration_seconds:0},transition_out:{kind:'cut',duration_seconds:0}});resetEffects=true;changed();});
  function discardDraft(){if(working)return;dirty=false;resetEffects=false;onDirty(false);sync();if(selectable(getState()))fill(getState().selected.clip);buttons();}
  discard.addEventListener('click',discardDraft);save.addEventListener('click',apply);sync();return{sync,apply,discardDraft,isWorking:()=>working,isDirty:()=>dirty,controls,save,reset,discard};
}
