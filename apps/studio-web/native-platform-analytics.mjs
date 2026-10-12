// Closed read DTO helpers. Cumulative counters never acquire a reporting interval.
const counterNames=new Set(['views','likes','comments','shares']);
const metricNames=new Set(['views','impressions','reach','watch_time','average_view_duration','completion_rate','likes','comments','shares','saves','followers_gained','clicks','ctr','revenue','rpm','observation_window_hours']);
export const analyticsMeta=platform=>['instagram_reels','facebook'].includes(platform);
export const analyticsCounter=platform=>platform==='tiktok'||analyticsMeta(platform);
export const analyticsMetricScope=platform=>platform==='tiktok'?'cumulative_video_counters':platform==='instagram_reels'?'lifetime_media_insights':platform==='facebook'?'cumulative_video_node_counters':null;
export function analyticsVersion(kind,platform){if(!['youtube','tiktok','instagram_reels','facebook'].includes(platform))throw new Error('Nền tảng analytics chưa được hỗ trợ.');return 'native-official-analytics-'+kind+(platform==='youtube'?'-v1':platform==='tiktok'?'-v2':'-v3');}
export function analyticsPost(value,platform){return typeof value==='string'&&(platform==='youtube'?/^[A-Za-z0-9_-]{11}$/.test(value):platform==='tiktok'?/^[1-9][0-9]{0,18}$/.test(value)&&BigInt(value)<=9223372036854775807n:analyticsMeta(platform)&&/^[1-9][0-9]{0,31}$/.test(value));}
export function analyticsMetaProfile(value,target){if(!value||Object.keys(value).sort().join(',')!=='api_version,login_type,page_id'||!/^v[1-9][0-9]{0,2}\.0$/.test(value.api_version??'')
  ||value.login_type!=='facebook_login'||!analyticsPost(value.page_id,'facebook')||!analyticsMeta(target?.platform)||target.platform==='facebook'&&value.page_id!==target.target_account_id)throw new Error('Cấu hình đọc Meta không đúng phạm vi.');return value;}
export function analyticsPublic(value){let count=0;function visit(v,depth){if(++count>300000||depth>30)throw new Error('Bằng chứng analytics quá lớn.');if(typeof v==='string'&&v.length>32768)throw new Error('Bằng chứng analytics quá lớn.');
  if(v&&typeof v==='object')for(const[k,c]of Object.entries(v)){if(/^(?:token|access_token|refresh_token|token_file|token_path|credential_file|credential_path|client_secret|secret|authorization|headers|upload_url|session_uri|private_path|signed_url|lease_url)$/i.test(k))throw new Error('Bằng chứng analytics chứa trường riêng tư.');visit(c,depth+1);}}visit(value,0);return value;}
export function analyticsCounterBinding(value,publication){analyticsPublic(value);const ids=value.remote_post_ids,expected=publication?.receipt?.public_post_ids;
  if(analyticsMeta(value.target?.platform)){const platform=value.target.platform,remote=publication?.receipt?.remote_post_id;
    if(value.schema_version!==analyticsVersion('publication-binding',platform)||value.metric_scope!==analyticsMetricScope(platform)
      ||!Array.isArray(ids)||ids.length!==1||!analyticsPost(ids[0],platform)||value.remote_post_id!==ids[0]||remote!==undefined&&remote!==ids[0])throw new Error('ID video Meta không đúng biên nhận.');return ids;}
  if(value.schema_version!==analyticsVersion('publication-binding','tiktok')||value.target?.platform!=='tiktok'||value.metric_scope!=='cumulative_video_counters'
    ||!Array.isArray(ids)||ids.length>20||new Set(ids).size!==ids.length||ids.some(id=>!analyticsPost(id,'tiktok'))
    ||expected!==undefined&&JSON.stringify(ids)!==JSON.stringify(expected)||value.remote_post_id!==null&&(!ids.includes(value.remote_post_id)||ids.length!==1)
    ||ids.length===1&&value.remote_post_id!==ids[0])throw new Error('ID bài đăng không đúng biên nhận TikTok.');return ids;}
export function analyticsCounterResult(result,request,profile=null){analyticsPublic(result);const e=result?.evidence,m=result?.metrics;
  if(analyticsMeta(result?.platform)){const platform=result.platform,mapping=platform==='instagram_reels'?{views:'views',reach:'reach',likes:'likes',comments:'comments',shares:'shares',saved:'saves'}:{views:'views','likes.summary.total_count':'likes','comments.summary.total_count':'comments'};
    const fields=['schema_version','api_version','metric_mapping','returned_metrics','metric_scope','query','coverage_end_date','observed_window_hours','normalized_units','unavailable_metrics','watch_time_unit_verified','completion_rate_supported','revenue_supported','provider_metric_semantics_real_verified'];
    const stable=v=>JSON.stringify(Object.entries(v??{}).sort());
    if(request?.platform!==platform||request.query!==null||request.metric_scope!==analyticsMetricScope(platform)||request.schema_version!==analyticsVersion('request',platform)
      ||!analyticsPost(request.remote_post_id,platform)||result.schema_version!==analyticsVersion('snapshot',platform)||result.remote_post_id!==request.remote_post_id
      ||result.provider_key!==(platform==='instagram_reels'?'instagram-graph-insights-api':'facebook-graph-video-insights-api')
      ||!e||Object.keys(e).sort().join(',')!==fields.sort().join(',')||e.schema_version!=='meta-analytics-counts-v1'||e.api_version!==profile?.api_version
      ||e.metric_scope!==analyticsMetricScope(platform)||e.query!==null||e.coverage_end_date!==null||e.observed_window_hours!==null
      ||['watch_time_unit_verified','completion_rate_supported','revenue_supported','provider_metric_semantics_real_verified'].some(k=>e[k]!==false)
      ||stable(e.metric_mapping)!==stable(mapping)||!Array.isArray(e.returned_metrics)||new Set(e.returned_metrics).size!==e.returned_metrics.length||e.returned_metrics.some(k=>typeof k!=='string'||!Object.hasOwn(mapping,k))
      ||!m||Object.keys(m).length!==metricNames.size||Object.keys(m).some(k=>!metricNames.has(k)))throw new Error('Quan sát Meta thiếu bằng chứng đúng phạm vi.');
    const present=new Set(e.returned_metrics.map(k=>mapping[k])),units={};
    for(const[k,v]of Object.entries(m))if(v!==null){if(!present.has(k)||!Number.isSafeInteger(v)||v<0)throw new Error('Chỉ số Meta không được xác minh.');units[k]='count';}
    if(stable(e.normalized_units)!==stable(units)||JSON.stringify(e.unavailable_metrics)!==JSON.stringify([...metricNames].filter(k=>m[k]===null)))throw new Error('Đơn vị hoặc chỉ số thiếu của Meta đã thay đổi.');return result;}
  if(request?.query!==null||request.metric_scope!=='cumulative_video_counters'||!analyticsPost(request.remote_post_id,'tiktok')
    ||result?.schema_version!==analyticsVersion('snapshot','tiktok')||result.platform!=='tiktok'||result.provider_key!=='tiktok-video-insights-api'||result.remote_post_id!==request.remote_post_id
    ||e?.query!==null||e.metric_scope!=='cumulative_video_counters'||e.observed_window_hours!==null||e.coverage_end_date!==null||!Number.isInteger(e.row_count)||![0,1].includes(e.row_count)
    ||e.owned_video_returned!==(e.row_count===1)||e.watch_time_supported!==false||e.completion_rate_supported!==false||e.revenue_supported!==false
    ||JSON.stringify(Object.entries(e.metric_mapping??{}).sort())!==JSON.stringify(Object.entries({view_count:'views',like_count:'likes',comment_count:'comments',share_count:'shares'}).sort())
    ||!m||Object.keys(m).length!==metricNames.size||Object.keys(m).some(k=>!metricNames.has(k)))throw new Error('Quan sát không đúng bộ đếm TikTok.');
  for(const[k,v]of Object.entries(m))if(!counterNames.has(k)&&v!==null||counterNames.has(k)&&v!==null&&(!Number.isSafeInteger(v)||v<0)||e.row_count===0&&v!==null)throw new Error('Chỉ số TikTok thiếu bằng chứng hoặc không hợp lệ.');return result;}
export function analyticsReportLabel(result){return result.platform==='instagram_reels'?'Chỉ số vòng đời của Reel Instagram; chưa xác minh thời gian xem và khoảng quan sát.':result.platform==='facebook'?'Bộ đếm video Facebook; chưa xác minh khoảng quan sát hoặc thời lượng xem.':analyticsCounter(result.platform)?'Bộ đếm lũy kế của bài đăng; không phải báo cáo theo khoảng ngày.':'Khoảng báo cáo: '+result.evidence.query.start_date+' → '+result.evidence.query.end_date+'.';}
