"""Scoped existing thumbnails/pixel frames; never return video bytes as an image."""
from PIL import Image
from .contracts import WorkflowError
from .media import project_assets,media_path
from .media_frame_analysis import checked_path,frame_path,validate,linked

def image(path,root,*,expected_size=None):
    try:
        if linked(path) or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):raise ValueError()
        with Image.open(path) as value:
            if value.format not in {'JPEG','PNG'} or value.width*value.height>40_000_000 or expected_size and value.size!=expected_size:raise ValueError()
            value.verify()
        return path
    except Exception:raise WorkflowError('MEDIA_THUMBNAIL_IMAGE_INVALID') from None

def thumbnail(store,config,project_id,asset_id):
    if config.data_root.absolute()!=store.root.absolute():raise WorkflowError('MEDIA_THUMBNAIL_SCOPE_INVALID')
    project=store.get(project_id);asset=next((v for v in project_assets(project['document']) if v['id']==asset_id),None)
    if asset is None:raise WorkflowError('MEDIA_NOT_IN_PROJECT',404)
    if asset.get('kind') not in {'image','video'}:raise WorkflowError('MEDIA_THUMBNAIL_KIND_INVALID',400)
    selected=project['document'].get('source_thumbnail_selection')
    if selected is not None:
        from .source_thumbnail_review import validate_selection
        validate_selection(project)
    if selected is not None and selected.get('source_asset_id')==asset_id:
        from .source_thumbnail_review import selected_image
        return selected_image(store,config,project),'explicit_reviewed_source_frame'
    if asset.get('thumbnail_id'):
        return image(media_path(config,asset['thumbnail_id']),store.root/'assets'),'registered_ingest_thumbnail'
    source=checked_path(config,asset)
    if asset['kind']=='image':return image(source,store.root/'assets'),'original_image'
    # Existing hash-bound observations are CPU pixels, not reviewed provider
    # semantics, continuous tracking, a selected publication image or QC.
    for record in reversed(project['document'].get('media_frame_analyses',[])):
        raw=record['observation']
        if raw['asset_id']!=asset_id or raw['source_sha256']!=asset['sha256']:continue
        value=validate(record,project_id,asset)
        if value['thumbnail_candidate_ids']:
            frame=next(v for v in value['frames'] if v['frame_id']==value['thumbnail_candidate_ids'][0])
            path=frame_path(store.root,frame)
            return image(path,store.root/'jobs',expected_size=(frame['width'],frame['height'])),'saved_cpu_pixel_frame'
        break
    # A clearly labeled placeholder is never registered as an asset/result.
    from pathlib import Path
    return Path(__file__).resolve().parents[2]/'apps/studio-web/source-video-placeholder.svg','placeholder_no_measured_thumbnail'
