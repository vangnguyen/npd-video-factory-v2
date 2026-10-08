"""Versioned opt-in storyboard review sequence; historical projects stay exact."""
from .contracts import WorkflowError,digest
POLICY={'id':'native-narrated-storyboard-workflow-v1','version':1,'measured_timing_apply_required':True,
        'audible_preview_required':True,'human_production_approval_required':True,'automatic_render':False,'automatic_publish':False}
def reference():return {'id':POLICY['id'],'version':POLICY['version'],'sha256':digest(POLICY)}
def selections(*,production_quality=False,narrated_workflow=False):
    if type(production_quality) is not bool:raise WorkflowError('PRODUCTION_QUALITY_SELECTION_INVALID',400)
    if type(narrated_workflow) is not bool:raise WorkflowError('NARRATED_WORKFLOW_SELECTION_INVALID',400)
    if narrated_workflow and not production_quality:raise WorkflowError('NARRATED_WORKFLOW_PRODUCTION_QUALITY_REQUIRED',400)
    result={}
    if production_quality:
        from .north_star_quality import policy_reference
        result['production_quality']=policy_reference()
    if narrated_workflow:result['narrated_workflow']=reference()
    return result
def required(document):
    value=document.get('narrated_workflow')
    if value is None:return False
    if value!=reference():raise WorkflowError('NARRATED_WORKFLOW_POLICY_CHANGED_REVIEW_REQUIRED',409)
    from .auto_edit_timeline import is_auto_edit
    return not is_auto_edit(document)
def require_measured(document):
    if required(document) and not document.get('prepared_narration'):raise WorkflowError('NARRATION_MEASURED_TIMING_REQUIRED',400)
