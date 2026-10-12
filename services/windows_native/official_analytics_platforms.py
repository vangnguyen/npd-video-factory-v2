"""Closed official read profiles and actual receipt post selection; no I/O."""
from app.analytics_official import video_id, TT_MAPPING
from .contracts import WorkflowError
from .official_analytics_models import Collect, CounterCollect, MetaCollect
from app import analytics_meta

PROVIDERS = {'youtube': 'youtube-analytics-api', 'tiktok': 'tiktok-video-insights-api',
    'instagram_reels':'instagram-graph-insights-api','facebook':'facebook-graph-video-insights-api'}
PUBLISHING_KEYS = {'youtube': 'youtube-data-api-publishing', 'tiktok': 'tiktok-content-posting-api',
    'instagram_reels':'instagram-graph-api-publishing','facebook':'facebook-graph-api-publishing'}
COST_PROVIDERS = {platform:'official-'+platform+'-analytics' for platform in PROVIDERS}


def version(name, platform):
    if platform not in PROVIDERS:
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PLATFORM_NOT_CONFIGURED')
    return 'native-official-analytics-' + name + ('-v1' if platform == 'youtube' else '-v2' if platform=='tiktok' else '-v3')


def valid_video_id(platform,value):
    return (analytics_meta.object_id if platform in analytics_meta.PLATFORMS else video_id)(platform,value)


def validate_request(target, request):
    if (target.platform not in PROVIDERS or target.provider_key != PUBLISHING_KEYS[target.platform]
        or type(request) is not (Collect if target.platform == 'youtube' else CounterCollect if target.platform=='tiktok' else MetaCollect)
        or type(request) is MetaCollect and request.platform!=target.platform):
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PLATFORM_REQUEST_REQUIRED', 400)


def receipt_posts(publication):
    receipt = publication.get('receipt'); platform = publication['snapshot']['target']['platform']
    if platform not in PROVIDERS or publication['status'] != 'completed' or receipt is None:
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_QUALIFIED_RECEIPT_REQUIRED')
    if platform != 'tiktok':
        return [valid_video_id(platform, receipt['remote_post_id'])]
    ids = receipt.get('public_post_ids')
    if (not isinstance(ids, list) or len(ids) > 20 or len(set(ids)) != len(ids)
        or receipt.get('public_visibility_confirmed') is not bool(ids)):
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_RECEIPT_POSTS_INVALID')
    return [video_id(platform, value) for value in ids]


def selected_post(publication, request):
    posts = receipt_posts(publication)
    remote = publication['receipt']['remote_post_id'] if type(request) is Collect else request.remote_post_id
    if remote not in posts:
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_ACTUAL_RECEIPT_POST_REQUIRED')
    return remote


def counter_evidence(evidence):
    """Keep the Display API's cumulative counters distinct from dated reports."""
    return {**evidence, 'query': None, 'coverage_end_date': None,
        'owned_video_returned': evidence['row_count'] == 1}


def validate_counter_result(metrics, evidence):
    if (set(evidence) != {'metric_mapping', 'row_count', 'metric_scope', 'observed_window_hours',
                         'watch_time_supported', 'completion_rate_supported', 'revenue_supported',
                         'query', 'coverage_end_date', 'owned_video_returned'}
        or evidence['metric_mapping'] != TT_MAPPING or type(evidence['row_count']) is not int
        or evidence['row_count'] not in (0, 1) or evidence['metric_scope'] != 'cumulative_video_counters'
        or evidence['query'] is not None or evidence['coverage_end_date'] is not None
        or evidence['observed_window_hours'] is not None
        or evidence['owned_video_returned'] is not (evidence['row_count'] == 1)
        or any(evidence[k] is not False for k in ('watch_time_supported', 'completion_rate_supported', 'revenue_supported'))
        or any(v is not None for k, v in metrics.items() if k not in TT_MAPPING.values())
        or any(v is not None and (type(v) not in (int, float) or v != int(v) or v > 2**53 - 1) for v in metrics.values())
        or evidence['row_count'] == 0 and any(v is not None for v in metrics.values())):
        raise ValueError('Changed cumulative counter evidence')


def validate_meta_result(metrics,evidence,platform,api_version):
    mapping=analytics_meta.IG_MAPPING if platform=='instagram_reels' else analytics_meta.FB_MAPPING
    scope='lifetime_media_insights' if platform=='instagram_reels' else 'cumulative_video_node_counters'
    keys={'schema_version','api_version','metric_mapping','returned_metrics','metric_scope','query','coverage_end_date',
        'observed_window_hours','normalized_units','unavailable_metrics','watch_time_unit_verified',
        'completion_rate_supported','revenue_supported','provider_metric_semantics_real_verified'}
    from app.analytics_models import NormalizedMetrics
    if (platform not in analytics_meta.PLATFORMS or not isinstance(metrics,dict)
        or set(metrics)!=set(NormalizedMetrics.model_fields) or not isinstance(evidence,dict) or set(evidence)!=keys
        or evidence['schema_version']!='meta-analytics-counts-v1' or evidence['api_version']!=api_version
        or evidence['metric_mapping']!=mapping or evidence['metric_scope']!=scope
        or any(evidence[key] is not None for key in ('query','coverage_end_date','observed_window_hours'))
        or any(evidence[key] is not False for key in ('watch_time_unit_verified','completion_rate_supported',
            'revenue_supported','provider_metric_semantics_real_verified'))):raise ValueError('Changed Meta metric evidence')
    returned=evidence['returned_metrics']
    if (not isinstance(returned,list) or any(type(key) is not str or key not in mapping for key in returned)
        or len(returned)!=len(set(returned))):raise ValueError('Changed Meta reported fields')
    for key,value in metrics.items():
        if value is not None:
            if key not in {mapping[name] for name in returned}:raise ValueError('Unreported Meta metric')
            analytics_meta.number(value,count=True)
    if (evidence['unavailable_metrics']!=[key for key in NormalizedMetrics.model_fields if metrics[key] is None]
        or evidence['normalized_units']!={key:'count' for key,value in metrics.items() if value is not None}):
        raise ValueError('Changed Meta availability or units')
