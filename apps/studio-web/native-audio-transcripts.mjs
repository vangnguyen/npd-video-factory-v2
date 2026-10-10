// Reads saved normalized audio transcripts; initialization never dispatches ASR.
const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),positive=v=>Number.isSafeInteger(v)&&v>=1;
function transcript(v){
  if(!v||!/^trn_[a-z0-9_-]{4,60}$/i.test(v.transcript_id??'')||!/^ana_[a-z0-9_-]{4,60}$/i.test(v.analysis_id??'')||!/^ast_[a-z0-9_-]{4,60}$/i.test(v.asset_id??'')||!positive(v.version)
    ||typeof v.is_original_evidence!=='boolean'||!['vi','en'].includes(v.language)||!Array.isArray(v.segments)||!v.segments.length||v.segments.length>1000||!Number.isFinite(Date.parse(v.created_at)))throw Error('Bản nhận diện không đúng hợp đồng.');
  const confidence=x=>x===null||typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=1;
  if(!confidence(v.confidence))throw Error('Độ tin cậy lời nói không hợp lệ.');
  let end=0,wordOrdinal=-1;const ids=new Set();
  for(const[i,s]of v.segments.entries()){
    if(!/^seg_[a-z0-9_-]{4,60}$/i.test(s.segment_id??'')||ids.has(s.segment_id)||s.ordinal!==i||!Number.isFinite(s.start_seconds)||!Number.isFinite(s.end_seconds)
      ||s.start_seconds<end||s.end_seconds<=s.start_seconds||s.end_seconds>600||typeof s.text!=='string'||!s.text.trim()||s.text.length>4000||!confidence(s.confidence)||!Array.isArray(s.words))throw Error('Đoạn lời nói không hợp lệ.');
    ids.add(s.segment_id);end=s.end_seconds;let previous=s.start_seconds;
    for(const w of s.words){if(!/^wrd_[a-z0-9_-]{4,60}$/i.test(w.word_id??'')||ids.has(w.word_id)||!Number.isSafeInteger(w.ordinal)||w.ordinal<=wordOrdinal||typeof w.text!=='string'||!w.text.trim()
        ||!Number.isFinite(w.start_seconds)||!Number.isFinite(w.end_seconds)||w.start_seconds<previous||w.end_seconds<=w.start_seconds||w.end_seconds>s.end_seconds||!confidence(w.confidence))throw Error('Timestamp từng từ không hợp lệ.');
      ids.add(w.word_id);wordOrdinal=w.ordinal;previous=w.end_seconds;}
  }
  return v;
}
export function validateAudioTranscripts(v,s,revision=s.project?.revision){
  if(v?.schema_version!=='native-audio-transcripts-v1'||v.workspace_id!==s.workspace_id||v.project_id!==s.project?.id||v.revision!==revision
    ||v.timeline_version!==null&&!positive(v.timeline_version)||v.publishing_enabled!==false||v.human_review_required!==true||v.provider_calls!==0||v.source_media_mutated!==false||!Array.isArray(v.items)||v.items.length>50)throw Error('Lời nói không đúng dự án hoặc phiên bản.');
  const seen=new Set();for(const r of v.items){if(typeof r.asset_id!=='string'||!/^[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}$/.test(r.asset_id)||seen.has(r.asset_id)||!sha(r.asset_sha256)||!sha(r.analysis_sha256)
      ||typeof r.filename!=='string'||!r.filename||r.filename.length>200||!Array.isArray(r.versions)||r.versions.length<1||r.versions.length>51)throw Error('Nguồn lời nói không hợp lệ.');seen.add(r.asset_id);
    transcript(r.original);transcript(r.current);if(!r.original.is_original_evidence||r.original.version!==1||r.current.analysis_id!==r.original.analysis_id||r.current.asset_id!==r.original.asset_id)throw Error('Nguồn nhận diện đã thay đổi.');
    const ids=new Set();for(const[i,t]of r.versions.entries()){transcript(t);if(t.version!==i+1||ids.has(t.transcript_id)||t.asset_id!==r.original.asset_id||t.analysis_id!==r.original.analysis_id||t.is_original_evidence!==(i===0))throw Error('Lịch sử lời nói không hợp lệ.');ids.add(t.transcript_id);}
    if(JSON.stringify(r.versions[0])!==JSON.stringify(r.original)||JSON.stringify(r.versions.at(-1))!==JSON.stringify(r.current))throw Error('Phiên bản nhận diện chưa khớp lịch sử.');
  }
  function privacy(x,depth=0){if(depth>30)throw Error('Bản nhận diện quá sâu.');if(x&&typeof x==='object')for(const[k,c]of Object.entries(x)){if(/^(token|access_token|refresh_token|token_path|credential_path|authorization|private_path)$/i.test(k))throw Error('Bản nhận diện chứa dữ liệu riêng tư.');privacy(c,depth+1);}}
  privacy(v);return v;
}
export function initializeNativeAudioTranscripts({api,getState,root=document,onWorking=()=>{},onSaved=async()=>{},onMessage=()=>{}}){
  const card=root.getElementById('native-audio-transcripts-card');card.hidden=false;card.replaceChildren();
  const node=(tag,text,name)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(name)n.id='native-audio-transcripts-'+name;return n;};
  const button=(text,name,permission)=>{const n=node('button',text,name);n.type='button';n.className='secondary';n.dataset.vfPermission=permission;return n;};
  const read=button('Đọc lời nói đã nhận diện','read','read'),save=button('Lưu bản lời nói mới','save','edit'),restore=button('Tạo bản mới từ nhận diện gốc','restore','edit'),
    selection=node('select',null,'selection'),segments=node('div',null,'segments'),status=node('p','Upload audio và bấm Phân tích nếu cần nhận diện. Đọc dữ liệu đã lưu trước khi sửa.','status');
  card.append(node('summary','Lời nói từ audio nguồn'),node('p','Nhận diện có thể sai. Sửa chữ giữ bản gốc và thời điểm của đoạn; phụ đề theo từng từ cần được căn lại cho đoạn đã sửa.'),read,selection,segments,save,restore,status);
  let working=false,scope='',generation=0,value=null,selected=null;const fields=new Map();
  const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.canEdit,s.dirty,s.active,s.project?.archived]);};
  function controls(){const s=getState(),blocked=working||s.busy;read.disabled=blocked||!s.project;selection.disabled=blocked||!value?.items.length;
    const editable=!blocked&&s.canEdit&&!s.dirty&&!s.active&&!s.project?.archived&&selected;
    save.disabled=!editable;restore.disabled=!editable||selected.current.is_original_evidence;for(const input of fields.values())input.disabled=!editable;}
  function sync(){const next=context();if(next!==scope){scope=next;generation++;selected=null;value=null;selection.replaceChildren();segments.replaceChildren();fields.clear();}controls();}
  function render(){selection.replaceChildren();for(const r of value?.items??[]){const o=node('option',r.filename+' · bản '+r.current.version);o.value=r.asset_id;selection.append(o);}selection.value=selected?.asset_id??'';
    segments.replaceChildren();fields.clear();for(const segment of selected?.current.segments??[]){const label=node('label',segment.start_seconds+' → '+segment.end_seconds+' giây'),input=node('textarea');input.value=segment.text;input.maxLength=4000;input.rows=2;label.append(input);segments.append(label);fields.set(segment.segment_id,input);}controls();}
  async function run(fn){sync();const s=getState();if(working||s.busy||!s.project)return;const expected=context(),ticket=++generation;working=true;onWorking(true);controls();const accept=()=>expected===context()&&ticket===generation;
    try{await fn(s,accept);}catch(e){if(accept())onMessage(e.message,true);}finally{working=false;onWorking(false);sync();}}
  const path=s=>'/api/projects/'+s.project.id+'/audio-transcripts';
  async function load(){await run(async(s,accept)=>{const response=await api(path(s));if(!accept())return;value=validateAudioTranscripts(response,s);selected=value.items[0]??null;render();status.textContent=value.items.length?'Chọn audio và kiểm tra từng đoạn trước khi lưu.':'Chưa có lời nhận diện từ audio nguồn.';});}
  async function submit(fromOriginal=false){await run(async(s,accept)=>{if(!s.canEdit||s.dirty||s.active||s.project.archived||!selected)throw Error('Đọc lời nói khi dự án có thể chỉnh sửa trước.');
    const old=selected,base=fromOriginal?old.original:old.current;
    if(fromOriginal&&old.current.is_original_evidence)throw Error('Bản lời nói đang là bản nhận diện gốc.');
    const edits=base.segments.map(seg=>({segment_id:seg.segment_id,text:fromOriginal?seg.text:fields.get(seg.segment_id)?.value}));
    if(edits.some(e=>typeof e.text!=='string'||!e.text.trim()||e.text.length>4000))throw Error('Mỗi đoạn cần chữ, tối đa 4.000 ký tự.');
    const response=await api(path(s)+'/'+old.asset_id,{revision:s.project.revision,asset_sha256:old.asset_sha256,analysis_sha256:old.analysis_sha256,
      edit:{expected_version:old.current.version,base_transcript_id:base.transcript_id,expected_timeline_version:value.timeline_version,segments:edits,note:fromOriginal?'Studio explicit original audio transcript restoration':'Studio explicit audio transcript text edit'}});
    if(!accept())return;if(typeof response.changed!=='boolean')throw Error('Biên nhận chỉnh lời nói không hợp lệ.');
    const verified=validateAudioTranscripts(response,s,s.project.revision+(response.changed?1:0)),updated=verified.items.find(r=>r.asset_id===old.asset_id);
    if(!updated||updated.asset_sha256!==old.asset_sha256||updated.analysis_sha256!==old.analysis_sha256||JSON.stringify(updated.original)!==JSON.stringify(old.original)
      ||updated.current.version!==old.current.version+(response.changed?1:0)||verified.timeline_version!==value.timeline_version)throw Error('Nguồn hoặc phiên bản lời nói đã thay đổi.');
    if(updated.current.segments.length!==base.segments.length)throw Error('Số đoạn trả về đã thay đổi.');
    for(const[i,segment]of updated.current.segments.entries()){
      const source=base.segments[i],text=edits[i].text.normalize('NFC');
      if(segment.text!==text||segment.start_seconds!==source.start_seconds||segment.end_seconds!==source.end_seconds||
        text!==source.text&&(segment.words.length||segment.confidence!==null))throw Error('Chữ hoặc thời điểm trả về khác bản sửa đã yêu cầu.');
    }
    value=verified;selected=updated;render();status.textContent=response.changed?'Đã lưu bản lời nói mới. Dự án cần được duyệt lại.':'Chữ chưa thay đổi.';await onSaved(response);});}
  selection.addEventListener('change',()=>{selected=value?.items.find(r=>r.asset_id===selection.value)??null;render();});
  read.addEventListener('click',load);save.addEventListener('click',()=>submit(false));restore.addEventListener('click',()=>submit(true));
  sync();return{load,save:()=>submit(false),restore:()=>submit(true),sync,controls,isWorking:()=>working,currentBinding:()=>({selected,value}),fields};
}
