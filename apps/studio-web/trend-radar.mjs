export const radarViews=[['trending-now','Trending Now'],['rising-fast','Rising Fast'],['breakout','Breakout'],['early-signals','Early Signals'],['cross-platform','Cross-platform'],['low-competition','Low Competition'],['high-monetization','High Monetization Potential'],['near-saturation','Near Saturation']];
const labels={velocity:'Tốc độ tăng',acceleration:'Gia tốc',cross_platform_spread:'Lan rộng nhiều nền tảng',engagement_quality:'Chất lượng tương tác',novelty:'Độ mới',channel_fit:'Phù hợp kênh',format_fit:'Phù hợp định dạng',monetization_fit:'Phù hợp mục tiêu thương mại',saturation:'Bão hòa',competition:'Cạnh tranh',rights_risk:'Rủi ro quyền sử dụng',policy_risk:'Rủi ro chính sách'};
const defaults={velocity:1.3,acceleration:1.2,cross_platform_spread:1.2,engagement_quality:1,novelty:1,channel_fit:1,format_fit:.9,monetization_fit:.8,saturation:1.1,competition:.9,rights_risk:1.3,policy_risk:1.2};
export const supportsTrendRadar=s=>s?.capabilities?.native_trend_radar===true;
export function learningSummary(value,workspace){
  const p=value?.payload;if(value?.schema_version!=='native-trend-radar-record-v1'||value.workspace_id!==workspace||value.record_type!=='learning'||typeof p?.scope?.mock!=='boolean')throw new Error('Lịch sử học khác không gian hoặc nguồn.');
  if(p.schema_version==='native-qualified-learning-feedback-v1'||p.source_binding||p.consumers){
    if(p.schema_version!=='native-qualified-learning-feedback-v1'||p.mock!==p.scope.mock||p.real_audience_observation!==!p.mock||!Number.isInteger(p.observation_count)||p.observation_count<0||p.observation_count>100
      ||p.recommendation_only!==true||p.automatic_application!==false||p.provider_calls!==0||p.publishing_enabled!==false||typeof p.source_binding?.learning_id!=='string'||!/^nols_[a-f0-9]{32}$/.test(p.source_binding.learning_id)
      ||typeof p.source_binding.learning_sha256!=='string'||!/^[a-f0-9]{64}$/.test(p.source_binding.learning_sha256))throw new Error('Bản học có nguồn không hợp lệ.');
    return{count:p.observation_count,label:p.mock?'Mô phỏng API':'Quan sát API nền tảng',qualified:true};
  }
  if(!Array.isArray(p.observations)||p.observations.length>100||p.scope.real_audience_observation!==false||p.recommendation_only!==true||p.autonomous_execution!==false)throw new Error('Bản học thử nghiệm không hợp lệ.');
  return{count:p.observations.length,label:p.scope.mock?'Thử nghiệm':'Chưa cấu hình',qualified:false};
}
export function publicLink(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!u.hash?u.href:null;}catch{return null;}}
export function validateRadarPage(value,workspace){
  if(value?.schema_version!=='native-trend-radar-page-v1'||value.workspace_id!==workspace||!Array.isArray(value.items)||value.items.length>100||value.automatic_production!==false||value.publishing_enabled!==false)throw new Error('Dữ liệu Radar khác không gian hiện tại.');
  for(const v of value.items){const p=v.payload,r=p?.ranking;
    if(!/^[a-f0-9]{32}$/.test(v.id)||v.record_type!=='assessment'||v.workspace_id!==workspace||!/^[a-f0-9]{64}$/.test(v.sha256)||r?.estimated!==true||r.recommendation_only!==true||r.autonomous_execution!==false||!Number.isFinite(r.personalized_planning_score)||r.personalized_planning_score<0||r.personalized_planning_score>100||typeof p.mock!=='boolean'||p.automatic_production!==false||!p.cluster_snapshot?.payload?.topic)throw new Error('Kết quả xếp hạng chưa có ràng buộc hợp lệ.');
  }return value;
}
function node(dom,tag,text){const el=dom.createElement(tag);if(text!=null)el.textContent=String(text);return el;}
export function radarCard(dom,value,{canEdit=false,onSelect=()=>{},onDetail=()=>{}}={}){
  const p=value.payload,c=p.cluster_snapshot.payload,r=p.ranking,article=node(dom,'article');article.dataset.assessmentId=value.id;
  article.append(node(dom,'h3',c.topic),node(dom,'p',`${c.lifecycle} · ${c.platforms.join(', ')} · ${p.mock?'Dữ liệu thử nghiệm':'Tín hiệu có nguồn'}`),
    node(dom,'p',`Điểm gợi ý: ${r.personalized_planning_score} / 100 · ${r.history_state==='insufficient_data'?'Chưa đủ lịch sử':'Có liên hệ mô tả với lịch sử'}`),
    node(dom,'p',`${c.signal_ids.length} tín hiệu · ${c.first_observed_at} → ${c.last_observed_at}`));
  const details=node(dom,'button','Xem nguồn và cách chấm điểm');details.className='secondary';details.addEventListener('click',()=>onDetail(value));
  const choose=node(dom,'button','Chọn để nghiên cứu & tạo ý tưởng');choose.className='primary';choose.disabled=!canEdit;choose.addEventListener('click',()=>{if(!choose.disabled)return onSelect(value);});
  article.append(details,choose);return article;
}
export function mountRadar({dom=globalThis.document,api,session,navigate=url=>globalThis.location.assign(url),newKey=()=>crypto.randomUUID()}={}){
  if(!supportsTrendRadar(session))throw new Error('Máy chủ chưa hỗ trợ Trend Radar.');
  const $=id=>dom.getElementById(id),workspace=session.access?.workspace_id||'wsp_native_local',permissions=session.access?.permissions||['read','edit','manage'];
  const canEdit=permissions.includes('edit'),canManage=permissions.includes('manage');let view='trending-now',busy=false,next=null,config=null,profiles=null,timer=null;
  const keys=new Map();const key=(operation,data)=>{const signature=JSON.stringify([operation,data]);if(!keys.has(signature))keys.set(signature,newKey());return keys.get(signature);};
  function message(text,error=false){$('radar-message').hidden=false;$('radar-message').textContent=text;$('radar-message').className='message'+(error?' error':'');}
  function controls(){for(const id of ['radar-refresh'])$(id).disabled=busy||!canEdit;for(const id of ['radar-collect','radar-save-learning'])$(id).disabled=busy||!canManage;
    const provider=config?.providers.find(v=>v.provider_key===$('radar-provider').value);$('radar-collect').disabled||= !provider?.authorized_access||['not_configured','unavailable'].includes(provider?.status)||provider.source_type==='fixture'&&!$('radar-fixture-ack').checked;
    $('radar-save-learning').disabled||=!$('radar-fixture-ack').checked;}
  const guarded=fn=>async()=>{if(busy)return;busy=true;controls();try{await fn();}catch(e){message(e.message,true);}finally{busy=false;controls();}};
  async function post(path,data,operation){const body={...data,request_key:key(operation,data)};const result=await api(path,{method:'POST',body:JSON.stringify(body)});keys.delete(JSON.stringify([operation,data]));return result;}
  function filters(offset=0){const query=new URLSearchParams({view,channel:$('radar-channel').value,target_platform:$('radar-platform').value,objective:$('radar-objective').value,days:$('radar-days').value,offset:String(offset),limit:'25'});
    for(const [id,key] of [['radar-filter-platform','platform'],['radar-country','country'],['radar-language','language'],['radar-filter-niche','niche'],['radar-filter-format','format']])if($(id).value.trim())query.set(key,$(id).value.trim());return query;}
  async function results(append=false){const value=validateRadarPage(await api('/api/trends/radar?'+filters(append?next:0)),workspace);if(!append)$('radar-results').replaceChildren();
    if(!value.items.length&&!append)$('radar-results').append(node(dom,'p','Chưa có cơ hội khớp bộ lọc. Thu thập tín hiệu từ nguồn đã cấu hình rồi phân tích cho kênh.'));
    for(const item of value.items)$('radar-results').append(radarCard(dom,item,{canEdit,onDetail:guarded(()=>detail(item)),onSelect:guarded(async()=>{
      const handoff=await post('/api/trends/handoff',{assessment_id:item.id,expected_sha256:item.sha256,acknowledged:true},'handoff');
      if(handoff.record_type!=='handoff'||handoff.workspace_id!==workspace||!/^[a-f0-9]{32}$/.test(handoff.payload.research_run_id)||handoff.payload.production_dispatch!==false)throw new Error('Chuyển nghiên cứu chưa được xác nhận.');
      navigate('/intelligence?run='+handoff.payload.research_run_id);
    })}));next=value.next_offset;$('radar-more').hidden=next==null;
    for(const button of $('radar-views').children)button.setAttribute('aria-selected',String(button.dataset.view===view));return value;}
  async function detail(item){const value=await api('/api/trends/records/'+item.id);if(value.record?.workspace_id!==workspace||value.record.id!==item.id||value.sha256!==item.sha256)throw new Error('Cơ hội đã thay đổi; tải lại Radar.');
    const root=$('radar-detail');root.hidden=false;root.replaceChildren(node(dom,'h2',item.payload.cluster_snapshot.payload.topic),node(dom,'p','Điểm và vòng đời là ước tính. Chỉ dùng liên kết để nghiên cứu; chọn cơ hội chưa phê duyệt sản xuất hoặc quyền dùng media.'));
    for(const record of value.signals){const s=record.payload.signal,article=node(dom,'article');article.append(node(dom,'h3',s.topic||s.keyword),node(dom,'p',`${s.source} · Quan sát ${s.observed_at} · Công bố ${s.published_at||'chưa rõ'}`));
      const href=publicLink(s.source_reference);if(href){const link=node(dom,'a','Mở nguồn tham khảo');link.href=href;link.target='_blank';link.rel='noopener noreferrer';article.append(link);}
      article.append(node(dom,'p',s.evidence_summary),node(dom,'p',['views','likes','comments','shares','saves','velocity','acceleration'].map(k=>`${k}: ${s[k]??'chưa có'}`).join(' · ')));root.append(article);}
    const explain=node(dom,'details');explain.append(node(dom,'summary','Chi tiết điểm, bằng chứng nhóm và lịch sử xếp hạng'),node(dom,'pre',JSON.stringify({score:item.payload.score,ranking:item.payload.ranking,similarity:item.payload.cluster_snapshot.payload.similarity_evidence},null,2)));root.append(explain);
    if(value.cluster_history?.length){root.append(node(dom,'h3','Vòng đời đã lưu · ước tính'));
      for(const version of value.cluster_history)root.append(node(dom,'p',`${version.payload.as_of} · ${version.payload.lifecycle} · ${version.payload.signal_ids.length} tín hiệu`));}
    if(value.signal_observation_history?.length){root.append(node(dom,'h3','Các lần quan sát nguồn'));
      for(const record of value.signal_observation_history){const s=record.payload.signal;root.append(node(dom,'p',`${s.source} · ${s.observed_at} · lượt xem ${s.views??'chưa có'} · tốc độ ${s.velocity??'chưa có'} · gia tốc ${s.acceleration??'chưa có'}`));}
      root.append(node(dom,'p','Lịch sử được giới hạn theo số bản đã lưu; dữ liệu thiếu và thời điểm quan sát không chứng minh độ phủ đầy đủ của nền tảng.'));}
  }
  async function saved(){const [collections,learning]=await Promise.all([api('/api/trends/collections'),api('/api/trends/learning')]);
    if(collections.workspace_id!==workspace||learning.workspace_id!==workspace)throw new Error('Lịch sử khác không gian hiện tại.');$('radar-collections').replaceChildren();
    for(const value of collections.items.slice(0,10))$('radar-collections').append(node(dom,'p',`${value.payload.request.provider_key} · ${value.payload.status} · ${value.payload.signal_ids.length} tín hiệu${value.payload.cached_collection_id?' · dùng bản đã lưu':''}${value.payload.failure_code?' · '+value.payload.failure_code:''}`));
    const selected=$('radar-learning').value;$('radar-learning').replaceChildren(node(dom,'option','Chưa dùng lịch sử'));$('radar-learning').children[0].value='';
    for(const value of learning.items.filter(v=>v.payload.scope.channel_profile_ref===$('radar-channel').value&&v.payload.scope.platform===$('radar-platform').value&&v.payload.status!=='not_configured')){const summary=learningSummary(value,workspace),option=node(dom,'option',`${summary.label} · ${summary.count} bài · ${value.created_at}`);option.value=value.id;$('radar-learning').append(option);}
    if([...$('radar-learning').children].some(v=>v.value===selected))$('radar-learning').value=selected;
    clearTimeout(timer);if(collections.items.some(v=>['queued','running'].includes(v.payload.status)))timer=setTimeout(()=>saved().catch(e=>message(e.message,true)),2000);
  }
  for(const [name,label] of radarViews){const button=node(dom,'button',label);button.dataset.view=name;button.setAttribute('role','tab');button.setAttribute('aria-controls','radar-results');button.addEventListener('click',guarded(async()=>{view=name;await results();}));$('radar-views').append(button);}
  for(const [name,value] of Object.entries(defaults)){const label=node(dom,'label',labels[name]),input=node(dom,'input');input.id='radar-weight-'+name;input.type='number';input.min='0';input.max='10';input.step='.1';input.value=String(value);label.append(input);$('radar-weights').append(label);}
  $('radar-provider').addEventListener('change',controls);$('radar-fixture-ack').addEventListener('change',controls);
  $('radar-collect').addEventListener('click',guarded(async()=>{if(!canManage)throw new Error('Cần quyền chủ sở hữu.');await post('/api/trends/collections',{provider_key:$('radar-provider').value,
    query:$('radar-query').value.trim()||null,country:$('radar-country').value.trim()||null,language:$('radar-language').value.trim()||null,fixture_acknowledged:$('radar-fixture-ack').checked},'collect');await saved();message('Đã lưu yêu cầu thu thập. Chờ kết quả rồi phân tích cho kênh.');}));
  $('radar-refresh').addEventListener('click',guarded(async()=>{if(!canEdit)throw new Error('Cần quyền biên tập.');await post('/api/trends/refresh',{channel_profile_ref:$('radar-channel').value,platform:$('radar-platform').value,
    business_objective:$('radar-objective').value,lookback_days:Number($('radar-days').value),learning_snapshot_id:$('radar-learning').value||null,
    weights:Object.fromEntries(Object.keys(defaults).map(k=>[k,Number($('radar-weight-'+k).value)])),clustering:{similarity_threshold:Number($('radar-similarity').value),maximum_gap_days:Number($('radar-gap').value)}},'refresh');await results();message('Đã lưu xếp hạng mới. Chọn cơ hội để nghiên cứu và duyệt ý tưởng.');}));
  $('radar-save-learning').addEventListener('click',guarded(async()=>{if(!canManage||!$('radar-fixture-ack').checked)throw new Error('Cần quyền chủ sở hữu và xác nhận dữ liệu thử nghiệm.');
    const value=await post('/api/trends/learning',{channel_profile_ref:$('radar-channel').value,platform:$('radar-platform').value,provider_mode:'fixture',fixture_acknowledged:true},'learning');
    $('radar-learning-state').textContent=`Đã lưu ${value.payload.observations.length} bài thử nghiệm cùng kênh; khuyến nghị chỉ mang tính mô tả. Thiếu dữ liệu vẫn được ghi rõ.`;await saved();}));
  $('radar-reload').addEventListener('click',guarded(async()=>{await saved();await results();}));$('radar-more').addEventListener('click',guarded(()=>results(true)));
  for(const id of ['radar-channel','radar-platform','radar-objective','radar-filter-platform','radar-filter-niche','radar-filter-format','radar-country','radar-language'])$(id).addEventListener('change',guarded(async()=>{await saved();await results();}));
  async function load(){const [sources,channels]=await Promise.all([api('/api/trends/providers'),api('/api/channel-profiles')]);config=sources;profiles=channels;
    if(config.workspace_id!==workspace)throw new Error('Nguồn Radar khác không gian hiện tại.');
    $('radar-provider').replaceChildren();for(const v of config.providers){const option=node(dom,'option',`${v.display_name} · ${v.status}`);option.value=v.provider_key;option.disabled=!v.authorized_access||['not_configured','unavailable'].includes(v.status);$('radar-provider').append(option);}
    const configured=config.providers.find(v=>v.authorized_access&&!['not_configured','unavailable'].includes(v.status));if(configured)$('radar-provider').value=configured.provider_key;
    $('radar-source-state').textContent=configured?'Chỉ dùng nguồn đã được cấu hình cho không gian này. Số liệu thiếu được giữ là chưa có.':'Chưa có nguồn được cấu hình. Chủ sở hữu có thể cấu hình nguồn RSS đã cho phép hoặc API được ủy quyền.';
    $('radar-channel').replaceChildren();for(const v of profiles.profiles){const option=node(dom,'option',v.name);option.value=v.profile_ref;$('radar-channel').append(option);}
    await saved();await results();controls();return {sources,channels};}
  controls();return {load,results,saved,close:()=>clearTimeout(timer)};
}
if(typeof document!=='undefined'&&document.getElementById('radar-results'))(async()=>{const message=document.getElementById('radar-message');try{
  let csrf;const api=async(path,options={})=>{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json','X-VF-CSRF':csrf||'',...(options.headers||{})}});const value=await response.json();if(!response.ok)throw new Error(value.code||'Không tải được dữ liệu.');return value;};
  const session=await api('/api/session');csrf=session.csrf;const shell=await import('./studio-shell.mjs');shell.loadStudioShellStyles();shell.mountStudioShell({page:'trends',context:'Theo dõi nguồn và lựa chọn cơ hội',capabilities:session.capabilities});
  if(session.access?.mode==='registry'){const access=await import('./native-access.mjs');access.installNativeAccess(session);}
  await mountRadar({api,session}).load();
}catch(e){message.hidden=false;message.textContent=e.message;message.className='message error';}})();
