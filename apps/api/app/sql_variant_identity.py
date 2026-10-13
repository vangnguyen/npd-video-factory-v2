"""Pure rebinding of manual storyboard drafts. Original evidence is never rewritten."""
import copy
from .content_models import ContentDocument
from .timeline_models import TimelineSnapshot
from .sql_variant_models import digest
from .sql_variant_repository import identity, SqlVariantError


def child_ids(member_id, asset_ids):
    return {'content_version_id': identity('pver_', member_id + '/content'),
            'timeline_id': identity('tln_', member_id + '/timeline'),
            'timeline_version_id': identity('tlv_', member_id + '/timeline/1'),
            'assets': {a: identity('ast_', member_id + '/asset/' + a) for a in sorted(asset_ids)}}


def center_crop(width, height, target_width, target_height):
    source_ratio, target_ratio = width / height, target_width / target_height
    w, h = ((target_ratio / source_ratio, 1.) if source_ratio >= target_ratio
            else (1., source_ratio / target_ratio))
    return {'x': (1. - w) / 2., 'y': (1. - h) / 2., 'width': w, 'height': h}


def derive_storyboard(value, copies):
    """Preserve timing/style/locks; only IDs, geometry and authority metadata change."""
    member, profile = value['member_id'], value['profile']
    ids = child_ids(member, value['source_assets'])
    content = copy.deepcopy(value['source_content']['snapshot']['content'])
    document = ContentDocument.model_validate(content)
    content['approved'] = False
    scene_map = {s.scene_id: identity('scene_', member + '/scene/' + s.scene_id) for s in document.scenes}
    for scene in content['scenes']:
        scene['scene_id'] = scene_map[scene['scene_id']]
        if scene.get('analysis_id'):
            raise SqlVariantError('SQL_VARIANT_S3_SOURCE_UNSUPPORTED')
        if scene.get('asset_id'):
            scene['asset_id'] = ids['assets'][scene['asset_id']]
        # Verification facts remain in the immutable parent record, not authority in the child.
        scene['official_render'] = False
    content = ContentDocument.model_validate(content).model_dump(mode='json')
    snapshot = copy.deepcopy(value['source_timeline'])
    TimelineSnapshot.model_validate(snapshot)
    metadata = snapshot['metadata']
    # Evidence tied to the parent is archived by the receipt. It cannot authorize the child.
    for key in ('approval', 'approved', 'reviewed_scene_selection', 'reviewed_local_scene_selection',
                'uploaded_audio_bindings_v1', 'narration_reflow'):
        metadata.pop(key, None)
    metadata.update(source_kind='storyboard_media', content_version_id=ids['content_version_id'],
        content_sha256=digest(content), reframe={'aspect_ratio': profile['aspect_ratio'],
            'fallback': 'center_crop', 'needs_attention': True, 'confidence': None},
        sql_variant_derivative={'schema_version': 'sql-variant-storyboard-lineage.v1',
            'family_id': value['family_id'], 'member_id': member,
            'master_project_id': value['master_project_id'], 'family_snapshot_sha256': value['family_snapshot_sha256'],
            'source_timeline_sha256': digest(value['source_timeline']),
            'source_content_sha256': digest(value['source_content']),
            'source_mode': 'storyboard_media', 'approval_inherited': False, 'new_inference_calls': 0})
    for track in snapshot['tracks']:
        # Semantic IDs are scoped by the new canonical timeline. reflow_snapshot requires trk_storyboard.
        for clip in track['clips']:
            clip['clip_id'] = identity('clip_', member + '/clip/' + clip['clip_id'])
            cm = clip['metadata']
            if cm.get('scene_id') in scene_map:
                cm['scene_id'] = scene_map[cm['scene_id']]
            if cm.get('analysis_id') or cm.get('transcript_id'):
                raise SqlVariantError('SQL_VARIANT_S3_SOURCE_UNSUPPORTED')
            if clip.get('asset_id'):
                source_id = clip['asset_id']
                clip['asset_id'] = ids['assets'][source_id]
                cm['source_checksum_sha256'] = copies[source_id]['sha256']
                cm['rights_status'] = 'unknown'
                cm['official_render'] = False
                if track['type'] == 'video':
                    dimensions = copies[source_id]['dimensions']
                    if dimensions is None:
                        raise SqlVariantError('SQL_VARIANT_S3_SOURCE_UNSUPPORTED')
                    crop = center_crop(*dimensions, profile['width'], profile['height'])
                    clip['crop'] = crop
                    point = {'time': clip['source_start'], **crop}
                    cm['reframe'] = {'schema_version': 1, 'keyframes': [point], 'aspect_ratio': profile['aspect_ratio'],
                        'confidence': None, 'fallback': 'center_crop', 'needs_attention': True,
                        'subject_tracking': 'NOT_CONFIGURED', 'source_width': dimensions[0],
                        'source_height': dimensions[1], 'time_space': 'source_seconds'}
    plan = metadata.get('media_plan')
    if isinstance(plan, list):
        for item in plan:
            if item.get('scene_id') in scene_map:
                item['scene_id'] = scene_map[item['scene_id']]
            if item.get('asset_id'):
                item['asset_id'] = ids['assets'][item['asset_id']]
                item['rights_status'] = 'unknown'
        metadata['media_plan_sha256'] = digest(plan)
    narration = metadata.get('narration_plan')
    if isinstance(narration, dict):
        for scene in narration.get('scenes', []):
            if scene.get('scene_id') in scene_map:
                scene['scene_id'] = scene_map[scene['scene_id']]
    snapshot.update(width=profile['width'], height=profile['height'], aspect_ratio=profile['aspect_ratio'],
        source_media_mutated=False, publish_requested=False)
    return ids, content, TimelineSnapshot.model_validate(snapshot).model_dump(mode='json')
