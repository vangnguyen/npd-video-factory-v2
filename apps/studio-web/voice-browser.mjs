const statuses={queued:'Đang chờ tạo mẫu',running:'Đang tạo mẫu trên máy',ready:'Có mẫu nghe thật',failed:'Tạo mẫu chưa thành công',outcome_unknown:'Lần tạo trước bị gián đoạn · cần thử lại chủ động'};
export const usableVoice=voice=>['source_licensed','owner_declared'].includes(voice?.definition?.rights_status);
export const auditionUrl=value=>/^\/api\/voice-auditions\/nsample_[a-f0-9]{32}\/audio$/.test(value??'')?value:null;
export function voiceDescription(preset){const m=preset?.metadata??{};return typeof m.description==='string'&&m.description.trim()?m.description:'Chưa phân loại chất giọng';}
export function initializeVoiceBrowser({root,api,voices=[],catalog={},dom=globalThis.document,getCharacter=()=>null,getTrialText=()=>'',onSelect=null,onMessage=()=>{},canEdit=()=>true}){
  let items=[],timer=null,disposed=false,pending=new Set(),audioPlaying=null;
  const node=(tag,text,parent,attrs={})=>{const n=dom.createElement(tag);if(text!==null)n.textContent=text;for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));parent.append(n);return n;};
  root.replaceChildren();const info=node('p','',root,{class:'hint'}),list=node('div',null,root,{class:'voice-card-grid'});const cards=[];
  const say=(e)=>onMessage(e.message??String(e),true);
  function stopOtherAudio(chosen){for(const value of dom.querySelectorAll('audio[data-voice-audition]'))if(value!==chosen)value.pause();audioPlaying=chosen;}
  async function load(){try{const result=await api('/api/voice-auditions');if(disposed)return;if(!Array.isArray(result?.items)||result.inference_dispatched!==false)throw Error('Chưa đọc được trạng thái mẫu giọng.');items=result.items;refresh();
      if(items.some(v=>['queued','running'].includes(v.state)))timer=setTimeout(load,2500);
    }catch(error){if(!disposed)say(error);}}
  function match(voice,kind,text){return items.find(v=>v.voice_id===voice.voice_id&&v.voice_version===voice.version&&v.kind===kind&&(kind==='sample'||v.text===text));}
  async function audition(card,kind){if(disposed)return;const voice=card.voice,text=getTrialText()?.trim(),existing=match(voice,kind,text);
    try{if(kind==='dialogue'&&!text)throw Error('Nhập ít nhất một câu thoại cho nhân vật trước khi nghe thử.');
      if(existing?.state==='ready'&&!card.corrupt){play(card,existing);return;}
      if(existing&&['queued','running'].includes(existing.state))return;
      if(!canEdit())throw Error('Cần quyền chỉnh sửa và chờ tác vụ hiện tại xong trước khi tạo mẫu.');
      pending.add(voice.voice_id+kind);refresh();const result=await api('/api/voice-auditions',{method:'POST',body:JSON.stringify({voice_id:voice.voice_id,voice_version:voice.version,kind,...(kind==='dialogue'?{text}:{}),...(existing?{retry:true}:{})})});
      if(!/^nsample_[a-f0-9]{32}$/.test(result?.sample_id??'')||result.human_listening_accepted!==false)throw Error('Chưa xác nhận yêu cầu mẫu. Tải lại trạng thái trước khi thử tiếp.');
      card.corrupt=false;items=[result,...items.filter(v=>v.sample_id!==result.sample_id)];if(result.state==='ready')play(card,result);clearTimeout(timer);await load();
    }catch(error){say(error);}finally{pending.delete(voice.voice_id+kind);refresh();}}
  function play(card,item){const url=auditionUrl(item.audio_url);if(!url){say(Error('Nguồn mẫu nghe chưa hợp lệ.'));return;}stopOtherAudio(card.audio);card.audio.src=url;card.audio.hidden=false;card.audio.play().catch(()=>{card.state.textContent='Mẫu sẵn sàng. Bấm phát để nghe.';});}
  const order=new Map((catalog.voices??[]).map((v,i)=>[v.provider_voice_id,i]));
  const ordered=[...voices].sort((a,b)=>(order.get(a.definition.provider_voice_id)??999)-(order.get(b.definition.provider_voice_id)??999));
  for(const voice of ordered){const preset=catalog.voices?.find(v=>v.provider_voice_id===voice.definition.provider_voice_id),card=node('article',null,list,{class:'voice-card'});
    node('h3',voice.definition.display_name,card);node('p',voiceDescription(preset),card);node('p',[preset?.locale??voice.definition.locale,preset?.metadata?.region].filter(Boolean).join(' · '),card,{class:'hint'});
    node('p',`Nguồn local · ${preset?.installed?'Đã cài':'Chưa xác minh cài đặt'} · ${usableVoice(voice)?'Có căn cứ quyền':'Cần kiểm tra quyền'}`,card,{class:'hint'});
    const state=node('p','',card,{role:'status','aria-live':'polite'}),actions=node('div',null,card,{class:'actions'}),sample=node('button','Nghe mẫu',actions,{type:'button'}),trial=node('button','Nghe thử câu thoại',actions,{type:'button'});
    const choose=onSelect?node('button','',actions,{type:'button',class:'primary'}):null;
    const audio=node('audio',null,card,{controls:'',preload:'none','data-voice-audition':''});audio.hidden=true;
    const rights=node('details',null,card);node('summary','Quyền sử dụng & nguồn',rights);node('p',voice.definition.license??'Chưa có giấy phép',rights);node('p',voice.definition.permission_reference??'Chưa có căn cứ',rights);
    const href=voice.definition.source_reference;if(/^https:\/\/(huggingface.co|github.com)\//.test(href??''))node('a','Xem nguồn giấy phép',rights,{href,target:'_blank',rel:'noopener noreferrer'});
    node('p','Mẫu tạo bằng preset này; chọn giọng cho vai không phải duyệt chất lượng audio hoặc video sau này.',rights,{class:'hint'});
    const value={voice,state,sample,trial,choose,audio};cards.push(value);sample.addEventListener('click',()=>audition(value,'sample'));trial.addEventListener('click',()=>audition(value,'dialogue'));
    audio.addEventListener('play',()=>{stopOtherAudio(audio);state.textContent='Đang phát mẫu';});audio.addEventListener('ended',()=>refresh());audio.addEventListener('error',()=>{value.corrupt=true;state.textContent='Không phát được mẫu · bấm Thử lại để kiểm tra và tạo lại khi tệp bị hỏng.';sample.textContent='Thử lại mẫu nghe';});
    choose?.addEventListener('click',()=>{const c=getCharacter();if(c&&usableVoice(voice)&&canEdit())onSelect(voice,c);});
  }
  function refresh(){const ready=new Set(items.filter(v=>v.state==='ready'&&v.kind==='sample').map(v=>v.voice_id));info.textContent=`${catalog.voices?.length??0} preset phát hiện · ${voices.filter(usableVoice).length} giọng trong thư viện có căn cứ quyền · ${voices.filter(v=>ready.has(v.voice_id)).length} mẫu nghe thật. Chưa ghi nhận Owner duyệt chất lượng.`;
    for(const c of cards){const sample=match(c.voice,'sample'),trial=match(c.voice,'dialogue',getTrialText()?.trim()),waiting=sample&&['queued','running'].includes(sample.state);c.state.textContent=audioPlaying===c.audio&&!c.audio.paused?'Đang phát mẫu':statuses[sample?.state]??'Chưa tạo mẫu nghe';
      if(sample?.error_code)c.state.textContent+=' · thử lại sau khi kiểm tra runtime hoặc tác vụ đang chạy';
      c.sample.textContent=sample&&['failed','outcome_unknown'].includes(sample.state)?'Thử tạo mẫu lại':'Nghe mẫu';
      c.sample.disabled=!usableVoice(c.voice)||Boolean(waiting)||pending.has(c.voice.voice_id+'sample')||(!canEdit()&&sample?.state!=='ready');
      c.trial.disabled=!usableVoice(c.voice)||!getTrialText()?.trim()||pending.has(c.voice.voice_id+'dialogue')||trial&&['queued','running'].includes(trial.state)||!canEdit()&&trial?.state!=='ready';
      if(c.choose){const character=getCharacter();c.choose.textContent=character?(character.selected_voice_id===c.voice.voice_id?'Đang chọn cho ':'Chọn cho ')+character.name:'Chọn nhân vật trước';c.choose.disabled=!character||!canEdit()||!usableVoice(c.voice);}
      if(sample?.state==='ready'&&!c.audio.src){c.audio.src=auditionUrl(sample.audio_url)??'';c.audio.hidden=!c.audio.src;}
    }}
  refresh();void load();return {refresh,dispose(){disposed=true;clearTimeout(timer);for(const c of cards)c.audio.pause();}};
}
