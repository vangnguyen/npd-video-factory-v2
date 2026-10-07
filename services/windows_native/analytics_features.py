"""Extract only explicit frozen Native render features; unknown semantics stay null."""
from .contracts import digest
from . import ingestion
from app.analytics_models import VideoFeatureMetadata


def capture(publication,job,stamp):
    snapshot=publication['snapshot'];document=job['snapshot']['document']
    timeline=(document.get('canonical_timeline') or {}).get('snapshot') or {}
    metadata=timeline.get('metadata') or {};tracks=timeline.get('tracks') or []
    clips=[clip for track in tracks if not track.get('disabled') for clip in track.get('clips',[]) if not clip.get('disabled')]
    scene_ids={clip.get('metadata',{}).get('scene_id') or clip.get('metadata',{}).get('shot_id')
        for clip in clips if clip.get('kind') not in ('subtitle','audio','music','metadata')}
    scene_ids.discard(None)
    subtitle=metadata.get('subtitle_template_ref')
    if not subtitle:
        choices={clip.get('metadata',{}).get('template_ref') for clip in clips if clip.get('kind') in ('subtitle','subtitles')}
        choices.discard(None);subtitle=next(iter(choices)) if len(choices)==1 else None
    # Do not infer semantic hook/topic/niche labels from filenames or later project state.
    lineage=document.get('content_intelligence') or {};idea=lineage.get('idea') or {};brief=lineage.get('brief') or {}
    explicit=document.get('analytics_features') or {}
    evidence={'project_metadata_source':'native_published_render_request_snapshot','publication_snapshot_sha256':publication['snapshot_sha256'],
        'render_job_id':job['id'],'job_snapshot_sha256':snapshot['job_snapshot_sha256'],
        'canonical_timeline_sha256':snapshot['canonical_timeline_sha256'],'final_sha256':snapshot['final_sha256'],
        'feature_context_sha256':digest(document),'current_project_metadata_used':False,
        'exact_publishing_time_available':False,'provider_posted_time':None,'source_is_dry_run':True,
        'semantic_labels_verified':False,'production_cost_vnd':None,
        'frozen_subtitle_style':metadata.get('subtitle_style'),'subtitle_catalog_id_verified':subtitle is not None}
    return VideoFeatureMetadata(feature_snapshot_id='nftr_'+digest([publication['publication_id'],publication['snapshot_sha256']])[:32],
        project_id=publication['project_id'],publication_id=publication['publication_id'],
        idea_id=idea.get('id'),trend_cluster_id=explicit.get('trend_cluster_id'),hook_type=explicit.get('hook_type'),
        duration_seconds=job.get('result',{}).get('qc',{}).get('duration_seconds'),scene_count=len(scene_ids) if scene_ids else None,
        subtitle_template=subtitle,voice_profile=explicit.get('voice_profile'),music_profile=explicit.get('music_profile'),
        visual_strategy=explicit.get('visual_strategy'),niche=explicit.get('niche'),topic=explicit.get('topic') or brief.get('topic'),
        cta=explicit.get('cta') or brief.get('cta'),publishing_time=None,evidence=evidence,captured_at=stamp).model_dump(mode='json')
