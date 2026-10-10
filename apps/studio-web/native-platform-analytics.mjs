// Closed read DTO helpers. Cumulative counters never acquire a reporting interval.
const counterNames=new Set(['views','likes','comments','shares']);
const metricNames=new Set(['views','impressions','reach','watch_time','average_view_duration','completion_rate','likes','comments','shares','saves','followers_gained','clicks','ctr','revenue','rpm','observation_window_hours']);
export const analyticsCounter=platform=>platform==='tiktok';
export function analyticsVersion(kind,platform){if(!['youtube','tiktok'].includes(platform))throw new Error('Nền tảng analytics chưa được hỗ trợ.');return 'native-official-analytics-'+kind+(platform==='youtube'?'-v1':'-v2');}
export function analyticsPost(value,platform){return typeof value==='string'&&(platform==='youtube'?/^[A-Za-z0-9_-]{11}$/.test(value):platform==='tiktok'&&/^[1-9][0-9]{0,18}$/.test(value)&&BigInt(value)<=9223372036854775807n);}
export function analyticsPublic(value){let count=0;function visit(v,depth){if(++count>300000||depth>30)throw new Error('Bằng chứng analytics quá lớn.');if(typeof v==='string'&&v.length>32768)throw new Error('Bằng chứng analytics quá lớn.');
  if(v&&typeof v==='object')for(const[k,c]of Object.entries(v)){if(/^(?:token|access_token|refresh_token|token_file|token_path|credential_file|credential_path|client_secret|secret|authorization|headers|upload_url|session_uri|private_path|signed_url|lease_url)$/i.test(k))throw new Error('Bằng chứng analytics chứa trường riêng tư.');visit(c,depth+1);}}visit(value,0);return value;}
export function analyticsCounterBinding(value,publication){analyticsPublic(value);const ids=value.remote_post_ids,expected=publication?.receipt?.public_post_ids;
  if(value.schema_version!==analyticsVersion('publication-binding','tiktok')||value.target?.platform!=='tiktok'||value.metric_scope!=='cumulative_video_counters'
    ||!Array.isArray(ids)||ids.length>20||new Set(ids).size!==ids.length||ids.some(id=>!analyticsPost(id,'tiktok'))
    ||expected!==undefined&&JSON.stringify(ids)!==JSON.stringify(expected)||value.remote_post_id!==null&&(!ids.includes(value.remote_post_id)||ids.length!==1)
    ||ids.length===1&&value.remote_post_id!==ids[0])throw new Error('ID bài đăng không đúng biên nhận TikTok.');return ids;}
export function analyticsCounterResult(result,request){analyticsPublic(result);const e=result?.evidence,m=result?.metrics;
  if(request?.query!==null||request.metric_scope!=='cumulative_video_counters'||!analyticsPost(request.remote_post_id,'tiktok')
    ||result?.schema_version!==analyticsVersion('snapshot','tiktok')||result.platform!=='tiktok'||result.provider_key!=='tiktok-video-insights-api'||result.remote_post_id!==request.remote_post_id
    ||e?.query!==null||e.metric_scope!=='cumulative_video_counters'||e.observed_window_hours!==null||e.coverage_end_date!==null||!Number.isInteger(e.row_count)||![0,1].includes(e.row_count)
    ||e.owned_video_returned!==(e.row_count===1)||e.watch_time_supported!==false||e.completion_rate_supported!==false||e.revenue_supported!==false
    ||JSON.stringify(Object.entries(e.metric_mapping??{}).sort())!==JSON.stringify(Object.entries({view_count:'views',like_count:'likes',comment_count:'comments',share_count:'shares'}).sort())
    ||!m||Object.keys(m).length!==metricNames.size||Object.keys(m).some(k=>!metricNames.has(k)))throw new Error('Quan sát không đúng bộ đếm TikTok.');
  for(const[k,v]of Object.entries(m))if(!counterNames.has(k)&&v!==null||counterNames.has(k)&&v!==null&&(!Number.isSafeInteger(v)||v<0)||e.row_count===0&&v!==null)throw new Error('Chỉ số TikTok thiếu bằng chứng hoặc không hợp lệ.');return result;}
export function analyticsReportLabel(result){return analyticsCounter(result.platform)?'Bộ đếm lũy kế của bài đăng; không phải báo cáo theo khoảng ngày.':'Khoảng báo cáo: '+result.evidence.query.start_date+' → '+result.evidence.query.end_date+'.';}
