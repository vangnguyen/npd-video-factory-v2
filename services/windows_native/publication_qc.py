"""Publishing projection from bound, measured Native storyboard full QC."""
from .contracts import WorkflowError,digest

def project(job):
    qc=dict(job['result']['qc']);full=qc.get('full_quality')
    if full is None:return qc # Preserve certified legacy/Source QC envelopes.
    document=job['snapshot']['document'];measured=full.get('full_production_qc') or {}
    if (full.get('schema_version')!='native-storyboard-full-qc-v1' or full.get('status')!='passed' or measured.get('status')!='passed'
        or full.get('document_sha256')!=digest(document) or full.get('final_sha256')!=qc.get('final_sha256')
        or measured.get('checksum_sha256')!=qc.get('final_sha256') or qc.get('passed') is not True
        or qc.get('checks',{}).get('full_production_qc') is not True):
        raise WorkflowError('NATIVE_PUBLICATION_FULL_QC_BINDING_CHANGED',409)
    fields=('width','height','video_codec','audio_codec','duration_seconds','fps','sample_rate')
    if any(measured.get(name) is None for name in fields):raise WorkflowError('NATIVE_PUBLICATION_FULL_QC_BINDING_CHANGED',409)
    return {**qc,**{name:measured[name] for name in fields},'publishing_qc_basis':'bound_native_storyboard_full_qc'}
