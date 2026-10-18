"""Bound Native encoder presets. Never accepts arbitrary FFmpeg or client graphs."""
from .contracts import WorkflowError,file_sha
from .hardening import durable_json

SCHEMA='native-export-encoder.v1'
QUALITY={'high':18,'standard':23,'small':27}
PRESENTATION='native-export-presentation.v1'


def presentation(snapshot):
    raw=snapshot.metadata.get('native_export_presentation')
    if raw is None:return {'schema_version':PRESENTATION,'burn_subtitles':True,'audio_included':True}
    if (not isinstance(raw,dict) or set(raw)!={'schema_version','burn_subtitles','audio_included'} or raw.get('schema_version')!=PRESENTATION
        or type(raw.get('burn_subtitles')) is not bool or type(raw.get('audio_included')) is not bool):raise WorkflowError('EXPORT_PRESENTATION_OPTIONS_INVALID')
    return dict(raw)


def render_projection(snapshot):
    options=presentation(snapshot);result=snapshot.model_copy(deep=True)
    for track in result.tracks:
        if not options['audio_included'] and track.type=='audio':track.muted=True
        if not options['burn_subtitles'] and track.kind=='subtitles':track.disabled=True
    return result


def output_options(document):
    from types import SimpleNamespace
    snapshot=(document.get('canonical_timeline') or {}).get('snapshot',{})
    fps=snapshot.get('fps',30)
    if type(fps) not in (int,float) or fps not in (24,25,30,60):raise WorkflowError('EXPORT_ENCODER_OPTIONS_INVALID')
    options=selection(document)
    return {**presentation(SimpleNamespace(metadata=snapshot.get('metadata',{}))),
        'schema_version':'native-export-render-options.v1','fps':int(fps),'crf':options['crf'] if options else 20,
        'quality_preset':options['quality_preset'] if options else 'legacy-standard'}


def preserve(value,canvas):
    if not canvas:return value
    metadata=canvas.get('metadata',{})
    keys=('native_export_encoder','native_export_presentation')
    if not any(key in metadata for key in keys):return value
    output_options({'canonical_timeline':{'snapshot':canvas}})
    import copy
    value['fps']=canvas['fps']
    for key in keys:
        if key in metadata:value['metadata'][key]=copy.deepcopy(metadata[key])
    return value


def selection(document):
    raw=(document.get('canonical_timeline') or {}).get('snapshot',{}).get('metadata',{}).get('native_export_encoder')
    if raw is None:return None
    if (not isinstance(raw,dict) or set(raw)!={'schema_version','quality_preset'} or raw.get('schema_version')!=SCHEMA
        or raw.get('quality_preset') not in QUALITY):raise WorkflowError('EXPORT_ENCODER_OPTIONS_INVALID')
    return {'schema_version':SCHEMA,'quality_preset':raw['quality_preset'],'crf':QUALITY[raw['quality_preset']]}


def write(document,directory):
    options=selection(document)
    if options is None:return
    durable_json(directory/'native-export-options.json',{**options,'render_manifest_sha256':file_sha(directory/'timeline-render.json')})
