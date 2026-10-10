"""Closed official read profiles and actual receipt post selection; no I/O."""
from app.analytics_official import video_id, TT_MAPPING
from .contracts import WorkflowError
from .official_analytics_models import Collect, CounterCollect

PROVIDERS = {'youtube': 'youtube-analytics-api', 'tiktok': 'tiktok-video-insights-api'}
PUBLISHING_KEYS = {'youtube': 'youtube-data-api-publishing', 'tiktok': 'tiktok-content-posting-api'}
COST_PROVIDERS = {'youtube': 'official-youtube-analytics', 'tiktok': 'official-tiktok-analytics'}


def version(name, platform):
    if platform not in PROVIDERS:
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PLATFORM_NOT_CONFIGURED')
    return 'native-official-analytics-' + name + ('-v1' if platform == 'youtube' else '-v2')


def validate_request(target, request):
    if (target.platform not in PROVIDERS or target.provider_key != PUBLISHING_KEYS[target.platform]
        or type(request) is not (Collect if target.platform == 'youtube' else CounterCollect)):
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PLATFORM_REQUEST_REQUIRED', 400)


def receipt_posts(publication):
    receipt = publication.get('receipt'); platform = publication['snapshot']['target']['platform']
    if platform not in PROVIDERS or publication['status'] != 'completed' or receipt is None:
        raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_QUALIFIED_RECEIPT_REQUIRED')
    if platform == 'youtube':
        return [video_id(platform, receipt['remote_post_id'])]
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
