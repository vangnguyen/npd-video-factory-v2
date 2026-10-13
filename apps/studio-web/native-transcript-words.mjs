// Explicit manual source-word decisions; reads never dispatch ASR or approval.
const id=/^[a-f0-9]{32}$/,sha=/^[a-f0-9]{64}$/,trn=/^trn_[a-f0-9]{24}$/;
const assetId=/^[a-f0-9]{32}(?:\.[a-z0-9]{1,16}){1,3}$/,segmentId=/^seg_[a-f0-9]{24}$/,wordId=/^wrd_[a-f0-9]{24}$/;
export function validateWordReview(value,state){
  if(value?.schema_version!=='native-transcript-word-review.v1'||value.workspace_id!==state.workspace_id
    ||value.project_id!==state.project?.id||value.revision!==state.project?.revision||!Array.isArray(value.items)
    ||value.items.length>250||value.source_media_mutated!==false||value.provider_calls!==0||value.publishing_enabled!==false)
    throw Error('Nguồn hoặc phiên bản lời nói đã thay đổi. Đọc lại.');
  for(const item of value.items){
    if(!['audio','video'].includes(item.kind)||!assetId.test(item.asset_id)
      ||!(item.kind==='video'?/^ana_[a-f0-9]{24}$/.test(item.identity):assetId.test(item.identity))
      ||!sha.test(item.asset_sha256)||!sha.test(item.analysis_sha256)
      ||!trn.test(item.current?.transcript_id)||!Number.isInteger(item.current.version)||!Array.isArray(item.current.segments)
      ||!Array.isArray(item.versions)||item.current.segments.length>1000
      ||item.source_url!==`/api/projects/${value.project_id}/transcript-word-review/source/${item.asset_id}`)
      throw Error('Biên nhận lời nói không hợp lệ.');
    for(const s of item.current.segments){
      if(!segmentId.test(s.segment_id)||!Array.isArray(s.words)||s.words.length>2000||typeof s.text!=='string'||!Number.isFinite(s.start_seconds)
        ||!Number.isFinite(s.end_seconds)||s.end_seconds<=s.start_seconds)throw Error('Đoạn lời nói không hợp lệ.');
      let end=s.start_seconds;
      for(const w of s.words){if(!wordId.test(w.word_id)||typeof w.text!=='string'||!w.text.trim()||!Number.isFinite(w.start_seconds)
        ||!Number.isFinite(w.end_seconds)||w.start_seconds<end||w.end_seconds<=w.start_seconds||w.end_seconds>s.end_seconds)
        throw Error('Từ hoặc thời điểm trong biên nhận không hợp lệ.');end=w.end_seconds;}
    }
  }
  return value;
}
export function wordReviewPayload(value,item,segment,words,{start,end,acknowledged}){
  if(!acknowledged)throw Error('Nghe nguồn và xác nhận đã kiểm tra mốc thời gian trước khi lưu.');
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||!words.length||words.length>2000)
    throw Error('Mốc thời gian của đoạn không hợp lệ.');
  let previous=start;
  const reviews=words.map(w=>{
    if(typeof w.text!=='string'||!w.text.trim()||w.text.length>240||!Number.isFinite(w.start_seconds)
      ||!Number.isFinite(w.end_seconds)||w.start_seconds<previous||w.end_seconds<=w.start_seconds||w.end_seconds>end)
      throw Error('Các từ cần có chữ và mốc thời gian dương, liên tiếp trong đoạn.');
    previous=w.end_seconds;return {word_id:w.word_id??null,text:w.text.normalize('NFC'),start_seconds:w.start_seconds,end_seconds:w.end_seconds};
  });
  return {revision:value.revision,asset_sha256:item.asset_sha256,analysis_sha256:item.analysis_sha256,
    review:{expected_version:item.current.version,expected_transcript_id:item.current.transcript_id,
      expected_timeline_version:value.timeline_version,acknowledged:true,
      segments:[{segment_id:segment.segment_id,start_seconds:start,end_seconds:end,words:reviews}],
      note:'Studio explicit manual source-word and timing review'}};
}

export function validateWordReviewSave(response,state,value,item,body){
  const verified=validateWordReview(response,{...state,project:{...state.project,revision:value.revision+1}});
  const updated=verified.items.find(v=>v.kind===item.kind&&v.identity===item.identity),current=updated?.current;
  const provenance=current?.provenance,expectedTimeline=value.timeline_version===null||item.kind==='audio'
    ?value.timeline_version:value.timeline_version+1;
  if(!updated||updated.asset_id!==item.asset_id||updated.asset_sha256!==item.asset_sha256||updated.analysis_sha256!==item.analysis_sha256
    ||verified.timeline_version!==expectedTimeline||current.version!==item.current.version+1||current.transcript_id===item.current.transcript_id
    ||provenance?.derived_from_transcript_id!==item.current.transcript_id||current.is_original_evidence!==false
    ||provenance?.word_timestamp_policy!=='human_supplied_source_intervals'||provenance?.timing_independently_measured!==false
    ||current.segments.length!==item.current.segments.length)
    throw Error('Biên nhận bản sửa không khớp nguồn hoặc phiên bản. Đọc lại.');
  for(const review of body.review.segments){
    const segment=current.segments.find(s=>s.segment_id===provenance.segment_id_mapping?.[review.segment_id]);
    if(!segment||segment.start_seconds!==review.start_seconds||segment.end_seconds!==review.end_seconds||segment.confidence!==null
      ||segment.text!==review.words.map(w=>w.text.trim().normalize('NFC')).join(' ')||segment.words.length!==review.words.length
      ||segment.words.some((w,i)=>w.text!==review.words[i].text.trim().normalize('NFC')||w.start_seconds!==review.words[i].start_seconds
        ||w.end_seconds!==review.words[i].end_seconds||w.confidence!==null))
      throw Error('Biên nhận không giữ đúng chữ hoặc mốc thời gian đã gửi. Đọc lại.');
  }
  return verified;
}

export function initializeTranscriptWords({api,getState,root=document,onMessage=()=>{},onWorking=()=>{},onSaved=async()=>{},onDirty=()=>{}}){
  const card=root.getElementById('native-transcript-words-card');card.hidden=false;card.replaceChildren();
  const node=(tag,text,name)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(name)n.id='native-transcript-words-'+name;return n;};
  const button=(text,name)=>{const n=node('button',text,name);n.type='button';n.className='secondary';return n;};
  const read=button('Đọc lời nói đã lưu','read'),source=node('select',null,'source'),segmentChoice=node('select',null,'segment'),
    playerRegion=node('div',null,'player'),start=node('input',null,'start'),end=node('input',null,'end'),
    rows=node('div',null,'rows'),previous=button('Trang trước','previous'),next=button('Trang sau','next'),
    add=button('Thêm từ / cụm','add'),cancel=button('Hủy sửa đoạn','cancel'),save=button('Lưu mốc thời gian đã kiểm tra','save'),ack=node('input',null,'ack'),
    status=node('p','Đọc transcript trước. Kết quả ASR gốc và video luôn được giữ nguyên.','status');
  for(const input of [start,end]){input.type='number';input.min='0';input.step='.001';}
  ack.type='checkbox';const acknowledge=node('label','Tôi đã nghe nguồn và kiểm tra các mốc thời gian của đoạn này.');acknowledge.prepend(ack);
  const bounds=node('div');bounds.className='native-word-bounds';
  const left=node('label','Đầu đoạn (giây)'),right=node('label','Cuối đoạn (giây)');left.append(start);right.append(end);bounds.append(left,right);
  card.append(node('summary','Review từ & mốc thời gian nguồn'),node('p','Mốc ASR là ước lượng. Bản sửa tay cần review; lưu không duyệt video hoặc chạy lại nhận diện.'),
    read,source,segmentChoice,playerRegion,bounds,rows,previous,next,add,cancel,acknowledge,save,status);
  let working=false,generation=0,scope='',value=null,item=null,selected=null,page=0,words=[],dirty=false;
  const fields=new Map();const context=()=>{const s=getState();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.canEdit,s.active,s.project?.archived]);};
  const unrelated=()=>{const s=getState();return s.dirty&&s.dirtyPart!=='transcript_words';};
  function controls(){const s=getState(),blocked=working||s.busy;
    const edit=!blocked&&s.canEdit&&!s.active&&!s.project?.archived&&!unrelated()&&selected;
    read.disabled=blocked||!s.project||dirty||unrelated();source.disabled=blocked||dirty;segmentChoice.disabled=blocked||dirty;
    for(const n of [start,end,ack,add,save])n.disabled=!edit;
    for(const n of fields.values())for(const input of Object.values(n))input.disabled=!edit;
    previous.disabled=blocked||page===0;next.disabled=blocked||(page+1)*25>=words.length;
    cancel.disabled=blocked||!dirty;
  }
  function sync(){const current=context();if(scope!==current){scope=current;generation++;value=null;item=null;selected=null;words=[];dirty=false;
    source.replaceChildren();segmentChoice.replaceChildren();rows.replaceChildren();playerRegion.replaceChildren();fields.clear();ack.checked=false;}controls();}
  function mark(){dirty=true;ack.checked=false;onDirty(true);controls();}
  function capture(){for(const[i,f]of fields){words[i]={...words[i],text:f.text.value,
    start_seconds:f.start.value===''?NaN:Number(f.start.value),end_seconds:f.end.value===''?NaN:Number(f.end.value)};}}
  function renderWords(){rows.replaceChildren();fields.clear();
    words.slice(page*25,(page+1)*25).forEach((word,index)=>{const position=page*25+index,box=node('div');box.className='native-word-row';
      const text=node('input'),from=node('input'),until=node('input'),remove=button('Bỏ','remove-'+position);
      text.type='text';text.maxLength=240;text.value=word.text;for(const n of [from,until]){n.type='number';n.min='0';n.step='.001';}
      from.value=Number.isFinite(word.start_seconds)?word.start_seconds:'';until.value=Number.isFinite(word.end_seconds)?word.end_seconds:'';
      const a=node('label','Từ / cụm'),b=node('label','Bắt đầu'),c=node('label','Kết thúc');a.append(text);b.append(from);c.append(until);box.append(a,b,c,remove);rows.append(box);
      fields.set(position,{text,start:from,end:until,remove});for(const n of [text,from,until])n.addEventListener('input',mark);
      remove.addEventListener('click',()=>{capture();words.splice(position,1);page=Math.min(page,Math.max(0,Math.ceil(words.length/25)-1));mark();renderWords();});
    });controls();status.textContent=selected?`Bản ${item.current.version} · trang ${page+1} · ${words.length} từ/cụm. Giữ mốc theo giây của nguồn gốc.`:'Chọn một đoạn lời nói.';}
  function selectSegment(){selected=item?.current.segments.find(s=>s.segment_id===segmentChoice.value)??null;page=0;
    words=structuredClone(selected?.words??[]);start.value=selected?.start_seconds??'';end.value=selected?.end_seconds??'';ack.checked=false;renderWords();}
  function selectSource(){item=value?.items.find(v=>v.kind+'/'+v.identity===source.value)??null;segmentChoice.replaceChildren();
    for(const s of item?.current.segments??[]){const option=node('option',`${s.start_seconds}–${s.end_seconds}s · ${s.text.slice(0,60)}`);option.value=s.segment_id;segmentChoice.append(option);}
    segmentChoice.value=item?.current.segments[0]?.segment_id??'';
    playerRegion.replaceChildren();if(item){const player=node(item.kind==='audio'?'audio':'video');player.controls=true;player.preload='metadata';player.src=item.source_url;playerRegion.append(player);}
    selectSegment();}
  async function run(fn){sync();const s=getState();if(working||s.busy||!s.project)return;const expected=context(),ticket=++generation;
    working=true;onWorking(true);controls();const accept=()=>expected===context()&&ticket===generation;
    try{await fn(s,accept);}catch(e){if(accept())onMessage(e.message,true);}finally{working=false;onWorking(false);sync();}}
  async function load(){await run(async(s,accept)=>{if(dirty||unrelated())throw Error('Lưu hoặc hủy bản sửa đang mở trước khi đọc lại.');
    const response=await api('/api/projects/'+s.project.id+'/transcript-word-review');if(!accept())return;
    value=validateWordReview(response,s);source.replaceChildren();for(const v of value.items){const option=node('option',v.filename+' · bản '+v.current.version);option.value=v.kind+'/'+v.identity;source.append(option);}
    source.value=value.items.length?value.items[0].kind+'/'+value.items[0].identity:'';selectSource();});}
  async function submit(){capture();await run(async(s,accept)=>{if(!s.canEdit||s.active||s.project.archived||unrelated()||!item||!selected)
      throw Error('Dự án hiện không cho phép sửa lời nói.');
    const body=wordReviewPayload(value,item,selected,words,{start:start.value===''?NaN:Number(start.value),
      end:end.value===''?NaN:Number(end.value),acknowledged:ack.checked});
    const response=await api('/api/projects/'+s.project.id+'/transcript-word-review/'+item.kind+'/'+item.identity,body);
    if(!accept())return;
    validateWordReviewSave(response,s,value,item,body);
    dirty=false;onDirty(false);onMessage('Đã lưu bản sửa từ/mốc mới, giữ nguyên ASR gốc. Kiểm tra phụ đề và preview rồi duyệt lại video.');await onSaved(response);
  });}
  read.addEventListener('click',load);source.addEventListener('change',selectSource);segmentChoice.addEventListener('change',selectSegment);
  for(const n of [start,end])n.addEventListener('input',mark);
  previous.addEventListener('click',()=>{capture();page=Math.max(0,page-1);renderWords();});next.addEventListener('click',()=>{capture();page++;renderWords();});
  add.addEventListener('click',()=>{capture();words.push({word_id:null,text:'',start_seconds:NaN,end_seconds:NaN});page=Math.floor((words.length-1)/25);mark();renderWords();});
  cancel.addEventListener('click',()=>{dirty=false;onDirty(false);selectSegment();});
  save.addEventListener('click',submit);sync();return {load,save:submit,sync,controls,isWorking:()=>working,fields,currentBinding:()=>({value,item,selected,words})};
}
