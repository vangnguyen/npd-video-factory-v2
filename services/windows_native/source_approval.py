"""Read-only source-preview binding for an explicit Native human review."""
import json
from types import SimpleNamespace
from .auto_edit_timeline import validate_document
from .contracts import WorkflowError, digest, file_sha
from .media import project_assets
from .source_assets import canonical_assets
from .source_preview import PROFILE,resolve_assets


def reviewed_preview(root,project):
    resolve_assets(SimpleNamespace(data_root=root),project)
    state=validate_document(project['document'])
    if state['snapshot']['metadata']['native_project_id']!=project['id']:
        raise WorkflowError('AUTO_EDIT_TIMELINE_PROJECT_MISMATCH')
    if not any(track['type']=='video' and not track['disabled'] and any(
        not clip['disabled'] and clip['opacity']>0 for clip in track['clips']) for track in state['snapshot']['tracks']):
        raise WorkflowError('AUTO_EDIT_ENABLED_VIDEO_REQUIRED',400)
    assets={asset['id']:asset for asset in canonical_assets(project['document'])}
    for track in state['snapshot']['tracks']:
        for clip in track['clips']:
            if track['disabled'] or clip['disabled'] or not clip['asset_id']:continue
            if assets.get(clip['metadata'].get('native_asset_id'),{}).get('rights_confirmed') is not True:
                raise WorkflowError('MEDIA_RIGHTS_CONFIRMATION_REQUIRED',400)
    key=digest({'project':project['id'],'timeline':state['sha256'],'revision':project['revision'],'preview_profile':PROFILE})
    folder=root/'shot-previews'/key
    try:
        record=json.loads((folder/'preview.json').read_bytes())
        manifest=json.loads((folder/'render-manifest.json').read_bytes())
        if (record['status']!='READY' or record['project_id']!=project['id'] or record['revision']!=project['revision']
            or record['timeline_sha256']!=state['sha256'] or record['timeline_version']!=state['version']
            or record['preview_profile']!=PROFILE or record['manifest']!=manifest
            or manifest.get('playable') is not True or manifest.get('fixture') is not False
            or manifest.get('timeline_sha256')!=state['sha256'] or manifest.get('timeline_version')!=state['version']
            or file_sha(folder/'preview.mp4')!=record['sha256']
            or file_sha(folder/'render-manifest.json')!=record['manifest_sha256']):
            raise ValueError('preview binding mismatch')
    except (OSError,ValueError,KeyError,TypeError):
        raise WorkflowError('AUTO_EDIT_CURRENT_PREVIEW_REVIEW_REQUIRED',400) from None
    return {'id':key,'sha256':record['sha256'],'manifest_sha256':record['manifest_sha256'],
        'timeline_version':state['version'],'timeline_sha256':state['sha256'],'profile':PROFILE,
        'final_render_parity':False,'final_video_review_required':True}


def validate_render_approval(job):
    approval=job['snapshot'].get('approval');document=job['snapshot']['document']
    state=validate_document(document)
    if (not approval or approval.get('revision')!=job['revision'] or approval.get('snapshot_sha256')!=digest(document)
            or approval.get('render_mode')!='source_footage' or not approval.get('reviewed_preview')
            or approval['reviewed_preview'].get('timeline_sha256')!=state['sha256']
            or approval['reviewed_preview'].get('timeline_version')!=state['version']
            or state['snapshot']['metadata']['native_project_id']!=job['project_id']):
        raise WorkflowError('AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER',400)
    return approval
