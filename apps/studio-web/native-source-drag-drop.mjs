import {getClip,pixelsPerSecond,snapTime} from './studio-utils.mjs';
const finite=v=>typeof v==='number'&&Number.isFinite(v),integer=v=>Number.isSafeInteger(v)&&v>0;
const key=s=>JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.timeline?.version,s.timeline?.sha256]);
const context=s=>JSON.stringify([key(s),s.canEdit!==false,s.project?.archived===true,s.zoom,s.snapping]);
const ready=s=>s.project?.document?.canonical_timeline?.snapshot?.metadata?.native_auto_edit_schema==='native-auto-edit-timeline-v1'
  &&/^[a-f0-9]{32}$/.test(s.project.id??'')&&typeof s.workspace_id==='string'&&s.workspace_id.length>0
  &&integer(s.project.revision)&&integer(s.timeline?.version)&&/^[a-f0-9]{64}$/.test(s.timeline?.sha256??'')
  &&s.timeline.version===s.project.document.canonical_timeline.version&&s.timeline.sha256===s.project.document.canonical_timeline.sha256
  &&finite(s.timeline.snapshot?.duration_seconds)&&s.timeline.snapshot.duration_seconds>0;
const movable=found=>found&&!found.track.locked&&['video','audio','text'].includes(found.track.type)&&finite(found.clip.duration)&&found.clip.duration>0
  &&finite(found.clip.timeline_start)&&found.clip.timeline_start>=0&&!found.clip.metadata?.narrated_generated_voice;

// Move existing canonical clips only. Foreign DataTransfer payloads are ignored.
export function initializeSourceDragDrop({root,getState,onMove,onMessage=()=>{}}){
  let drag=null,working=false,uncertain=null;
  const blocked=s=>!ready(s)||working||s.canEdit===false||s.project.archived||s.busy||s.active||s.dirty||uncertain===key(s);
  function sync(){const s=getState();for(const el of root.querySelectorAll('[data-source-clip]'))el.draggable=!blocked(s)&&Boolean(movable(getClip(s.timeline,el.dataset.sourceClip)));}
  function cancel(){drag=null;}
  function start(event){
    cancel();const s=getState(),el=event.target?.closest?.('[data-source-clip]'),found=getClip(s.timeline,el?.dataset.sourceClip);
    if(blocked(s)||!movable(found)||!finite(event.clientX)){event.preventDefault();return;}
    const left=el.getBoundingClientRect().left;if(!finite(left)){event.preventDefault();return;}
    drag={clip_id:found.clip.clip_id,track_id:found.track.track_id,offset:Math.max(0,event.clientX-left),context:context(s),binding:key(s)};
    event.dataTransfer?.setData('text/plain',found.clip.clip_id);if(event.dataTransfer)event.dataTransfer.effectAllowed='move';
  }
  function over(event){const s=getState(),lane=event.target?.closest?.('[data-source-lane]');
    if(drag&&!blocked(s)&&drag.context===context(s)&&lane?.dataset.sourceLane===drag.track_id){event.preventDefault();if(event.dataTransfer)event.dataTransfer.dropEffect='move';}}
  async function drop(event){
    const move=drag;cancel();const s=getState(),lane=event.target?.closest?.('[data-source-lane]');
    if(!move||blocked(s)||move.context!==context(s)||lane?.dataset.sourceLane!==move.track_id||!finite(event.clientX))return;
    const found=getClip(s.timeline,move.clip_id),left=lane.getBoundingClientRect().left;
    if(!movable(found)||found.track.track_id!==move.track_id||!finite(left))return;
    event.preventDefault();const at=snapTime(Math.max(0,event.clientX-left-move.offset)/pixelsPerSecond(s.zoom),s.snapping);
    const linked=found.track.type==='video'&&found.track.kind==='source';
    if(!finite(at)||at> s.timeline.snapshot.duration_seconds+.000001||!linked&&at+found.clip.duration>s.timeline.snapshot.duration_seconds+.000001){
      onMessage('Vị trí kéo vượt thời lượng bản dựng. Chọn mốc nằm trong timeline.',true);return;}
    if(Math.abs(at-found.clip.timeline_start)<.000001)return;
    const binding={workspace_id:s.workspace_id,project_id:s.project.id,revision:s.project.revision,timeline_version:s.timeline.version,
      timeline_sha256:s.timeline.sha256,clip_id:move.clip_id,track_id:move.track_id};
    working=true;sync();
    try{const accepted=await onMove(at,binding);
      if(accepted!==true||key(getState())===move.binding)throw Error('Chưa xác nhận vị trí đã lưu. Mở lại timeline trước khi thử tiếp.');
    }catch(error){uncertain=move.binding;onMessage(error.message,true);}
    finally{working=false;sync();}
  }
  root.addEventListener('dragstart',start);root.addEventListener('dragover',over);root.addEventListener('drop',drop);root.addEventListener('dragend',cancel);
  sync();return{sync,cancel,isWorking:()=>working};
}
