// Explicit saved-learning projection and template reading; no automatic API work.
const labels={trend_radar:'Trend Radar',idea_engine:'Ý tưởng',media_planner:'Kế hoạch media',template_recommendations:'Mẫu phụ đề'};
const dimensions={trend_family:'Nhóm xu hướng',hook:'Mở đầu',duration:'Thời lượng',visual_strategy:'Hình ảnh',subtitle_style:'Phụ đề',voice_profile:'Giọng đọc',publishing_window:'Khung giờ đăng'};
const consumerDimensions={trend_radar:['trend_family'],idea_engine:['hook','duration'],media_planner:['visual_strategy','duration','voice_profile'],template_recommendations:['subtitle_style']};
const stable=v=>JSON.stringify(v,(_,c)=>c&&typeof c==='object'&&!Array.isArray(c)?Object.fromEntries(Object.keys(c).sort().map(k=>[k,c[k]])):c);
export function initializeNativeQualifiedLearning({api,getState,getBinding,root=document,onMessage=()=>{},onWorking=()=>{},uuid=()=>crypto.randomUUID()}){
  const card=root.getElementById('native-qualified-learning-card');card.replaceChildren();
  const node=(tag,text,id)=>{const n=root.createElement(tag);if(text)n.textContent=text;if(id)n.id='native-qualified-learning-'+id;return n;};
  const button=(text,id,permission='read')=>{const n=node('button',text,id);n.type='button';n.className='secondary';n.dataset.vfPermission=permission;return n;};
  const check=(text,id)=>{const n=node('input',null,id);n.type='checkbox';n.dataset.vfPermission='manage';const label=node('label',text);label.append(n);return[n,label];};
  const create=button('Dùng bằng chứng cho khuyến nghị kế hoạch','create','manage'),templates=button('Đọc khuyến nghị mẫu phụ đề','templates'),
    status=node('p','Chọn một khuyến nghị học đã lưu trước.','status'),consumers=node('div',null,'consumers'),suggestions=node('div',null,'suggestions'),detail=node('pre',null,'detail');
  const[ack,ackLabel]=check('Tôi hiểu đây là khuyến nghị để xem xét; không cho phép tự thay đổi media hoặc ngân sách.','ack'),
    [mock,mockLabel]=check('Tôi hiểu lịch sử mô phỏng không dùng để xếp hạng tín hiệu thật.','mock-ack');
  const link=node('a','Mở Trend Radar');link.href='/trends';detail.className='native-publication-evidence';consumers.className='native-analytics-metrics';
  card.append(node('summary','Đưa bằng chứng học vào kế hoạch'),node('p','Chọn bằng chứng đã lưu, xác nhận rồi tạo khuyến nghị cho Radar, ý tưởng, media và mẫu phụ đề. Không tự đọc API nền tảng, thay đổi timeline hay xuất bản.'),
    status,ackLabel,mockLabel,create,templates,link,consumers,suggestions,detail);
  let selection='',namespace='',generation=0,working=false,selected=null;const keys=new Map();
  const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),id=(v,p)=>typeof v==='string'&&new RegExp('^'+p+'_[a-f0-9]{32}$').test(v),finite=v=>typeof v==='number'&&Number.isFinite(v),
    learning=()=>getBinding()?.learning??null,base='/api/trends/learning/qualified';
  const context=()=>{const s=getState(),l=learning();return JSON.stringify([s.workspace_id,s.project?.id,s.project?.revision,s.project?.archived,s.dirty,s.active,s.canManage,l?.learning_id,l?.snapshot_sha256]);};
  function binding(){const s=getState(),l=learning(),scope=l?.snapshot?.scope;
    if(!l||!id(l.learning_id,'nols')||!sha(l.snapshot_sha256)||l.workspace_id!==s.workspace_id||l.project_id!==s.project?.id||typeof l.mock!=='boolean'||l.real_audience_observation!==!l.mock
      ||!scope||scope.workspace_id!==s.workspace_id||scope.mock!==l.mock||typeof scope.channel_profile_ref!=='string'||!/^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$/.test(scope.channel_profile_ref)||!sha(scope.channel_profile_sha256)
      ||!['youtube','tiktok','instagram_reels','facebook'].includes(scope.platform)||l.recommendation_only!==true||l.automatic_action!==false||!Array.isArray(l.dimensions)||l.dimensions.length!==7)throw new Error('Chọn bằng chứng học có phạm vi kênh hợp lệ.');return l;}
  function body(){const s=getState(),l=binding();if(!s.canManage||ack.checked!==true||l.mock&&mock.checked!==true)throw new Error('Cần quyền chủ sở hữu và xác nhận khuyến nghị.');
    return{schema_version:'native-qualified-learning-feedback-request-v1',project_id:l.project_id,learning_id:l.learning_id,expected_learning_sha256:l.snapshot_sha256,
      channel_profile_ref:l.snapshot.scope.channel_profile_ref,platform:l.snapshot.scope.platform,acknowledged_recommendation_only:true,acknowledged_protocol_mock:l.mock};}
  function controls(){const s=getState();let ready=false;try{body();ready=true;}catch{}create.disabled=working||s.busy||!ready;templates.disabled=working||s.busy||!selected;
    ack.disabled=mock.disabled=working||s.busy||!s.canManage;mockLabel.hidden=learning()?.mock!==true;}
  function sync(){const s=getState(),ns=JSON.stringify([s.workspace_id,s.project?.id]);if(ns!==namespace){namespace=ns;keys.clear();}
    const value=context();if(value!==selection){selection=value;generation++;selected=null;ack.checked=mock.checked=false;consumers.replaceChildren();suggestions.replaceChildren();detail.textContent='';status.textContent='Chọn khuyến nghị học đã lưu và xác nhận trước.';}controls();}
  async function run(fn){sync();const s=getState();if(working||s.busy||!s.project)return;const ticket=++generation,current=context();working=true;onWorking(true);controls();const accept=()=>ticket===generation&&current===context();
    try{await fn(s,accept);}catch(e){if(accept())onMessage(e.message,true);}finally{working=false;onWorking(false);sync();}}
  function validateResult(value,s,request){const r=value?.record,p=r?.payload,l=binding(),snap=l.snapshot;
    const expectedBinding={project_id:l.project_id,learning_id:l.learning_id,learning_sha256:l.snapshot_sha256,publication_id:l.publication_id,
      anchor_assessment_id:l.anchor_assessment_id,anchor_assessment_sha256:snap.request.expected_assessment_sha256,anchor_candidate_sha256:snap.anchor_candidate_sha256,
      anchor_result_snapshot_id:l.anchor_result_snapshot_id,winner_policy_sha256:snap.winner_policy_sha256,winner_factor_basis_sha256:snap.winner_factor_basis_sha256};
    const expectedConsumers=Object.fromEntries(Object.entries(consumerDimensions).map(([k,d])=>[k,l.dimensions.filter(v=>d.includes(v.dimension))]));
    if(value?.schema_version!=='native-qualified-learning-feedback-result-v1'||value.workspace_id!==s.workspace_id||typeof value.idempotent_replay!=='boolean'||!sha(value.record_sha256)
      ||value.recommendation_only!==true||value.automatic_application!==false||value.provider_calls!==0||value.publishing_enabled!==false||value.token_returned!==false
      ||r?.schema_version!=='native-trend-radar-record-v1'||typeof r.id!=='string'||!/^[a-f0-9]{32}$/.test(r.id)||r.version!==1||r.record_type!=='learning'||r.workspace_id!==s.workspace_id
      ||p?.schema_version!=='native-qualified-learning-feedback-v1'||stable(p.request)!==stable(request)||!sha(p.request_sha256)||stable(p.scope)!==stable(snap.scope)||stable(p.source_binding)!==stable(expectedBinding)
      ||stable(p.recommendations)!==stable(l.dimensions)||stable(p.consumers)!==stable(expectedConsumers)||p.status!==l.status||p.observation_count!==l.observation_count
      ||p.mock!==l.mock||p.real_audience_observation!==!l.mock||p.recommendation_only!==true||p.automatic_production!==false||p.autonomous_execution!==false||p.automatic_application!==false
      ||p.publishing_enabled!==false||p.provider_calls!==0||p.external_call!==false||p.token_returned!==false
      ||p.channel_selection?.profile_sha256!==snap.scope.channel_profile_sha256||p.channel_selection?.profile?.profile_ref!==snap.scope.channel_profile_ref)throw new Error('Khuyến nghị kế hoạch không đúng yêu cầu hoặc nguồn.');return value;}
  function render(){consumers.replaceChildren();suggestions.replaceChildren();detail.textContent=selected?JSON.stringify(selected,null,2):'';if(selected){const p=selected.record.payload;
    status.textContent='Đã lưu khuyến nghị kế hoạch · '+p.observation_count+' video khác nhau'+(p.mock?' · mô phỏng API; chưa có phản hồi khán giả thật.':' · quan sát nền tảng.')+' Chọn bản này tại Trend Radar khi phân tích.';
    for(const[k,values]of Object.entries(p.consumers)){const box=node('div');box.append(node('strong',labels[k]));for(const d of values){box.append(node('p',dimensions[d.dimension]+' · '+(d.state==='insufficient_data'?'Chưa đủ dữ liệu':d.state==='recommendations_available'?'Có khuyến nghị để xem xét':'Chưa có liên hệ tích cực')));
      for(const g of d.groups.filter(g=>g.state==='recommendation_candidate'))box.append(node('p',g.value+' · Nhóm '+g.sample_count+' / đối chiếu '+g.control_count+' · Chênh lệch '+g.score_difference));}consumers.append(box);}}controls();}
  async function createProjection(){await run(async(s,accept)=>{const request=body(),fp=stable(request);if(!keys.has(fp)){if(keys.size>=512)throw new Error('Đọc lịch sử trước khi tạo thêm khuyến nghị.');keys.set(fp,'native-qualified-learning-'+uuid());}
    const value=await api(base,{...request,request_key:keys.get(fp)});if(!accept())return;selected=validateResult(value,s,request);ack.checked=mock.checked=false;render();});}
  async function readTemplates(){await run(async(s,accept)=>{if(!selected)return;const expected=selected,value=await api(base+'/'+selected.record.id+'/templates');if(!accept())return;
    if(value?.schema_version!=='native-qualified-learning-template-suggestions-v1'||value.workspace_id!==s.workspace_id||value.projection_id!==expected.record.id||value.projection_sha256!==expected.record_sha256
      ||stable(value.source_binding)!==stable(expected.record.payload.source_binding)||!sha(value.catalog_sha256)||typeof value.catalog_version!=='string'||value.mock!==expected.record.payload.mock||value.real_audience_observation!==!value.mock
      ||value.recommendation_only!==true||value.automatic_application!==false||value.human_selection_required!==true||value.provider_calls!==0||value.publishing_enabled!==false||value.token_returned!==false
      ||!Array.isArray(value.suggestions)||value.suggestions.length>100||typeof value.suggestions_truncated!=='boolean'||!Array.isArray(value.unmatched_historical_styles))throw new Error('Khuyến nghị mẫu không đúng bằng chứng.');
    const groups=expected.record.payload.consumers.template_recommendations.flatMap(d=>d.groups);for(const t of value.suggestions){const g=groups.find(g=>g.value===t.recorded_subtitle_feature&&g.state==='recommendation_candidate');
      if(!g||typeof t.template_ref!=='string'||typeof t.name!=='string'||!t.style||typeof t.requires_word_timestamps!=='boolean'||t.historical_full_style_verified!==false||!['recorded_template_reference','recorded_style_fields_only'].includes(t.match_kind)
        ||t.human_selection_required!==true||t.automatic_application!==false||t.sample_count!==g.sample_count||t.control_count!==g.control_count||!finite(t.score_difference)||t.score_difference!==g.score_difference
        ||stable(t.snapshot_ids)!==stable(g.snapshot_ids)||stable(t.control_snapshot_ids)!==stable(g.control_snapshot_ids))throw new Error('Mẫu không có nhóm và đối chiếu hợp lệ.');}
    suggestions.replaceChildren();if(!value.suggestions.length)suggestions.append(node('p','Chưa có khuyến nghị mẫu đủ bằng chứng.'));for(const t of value.suggestions)suggestions.append(node('p',t.name+' · '+t.template_ref+(t.requires_word_timestamps?' · Cần thời điểm từng từ.':'')+' Chọn và lưu riêng trong phần phụ đề; chưa xác minh kiểu hiển thị lịch sử đầy đủ.'));
    detail.textContent=JSON.stringify({projection:expected,templates:value},null,2);});}
  create.addEventListener('click',createProjection);templates.addEventListener('click',readTemplates);ack.addEventListener('change',controls);mock.addEventListener('change',controls);sync();
  return{createProjection,readTemplates,sync,controls,isWorking:()=>working};
}
