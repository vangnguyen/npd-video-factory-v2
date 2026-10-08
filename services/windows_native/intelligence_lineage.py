"""Validate and project the approved research lineage inside existing native jobs."""
from .contracts import WorkflowError, digest
from .intelligence_models import ContentBrief, ContentIdea, ResearchFinding, ResearchRun, ResearchSource
from .research import validate_findings


def validate(lineage):
    from .intelligence_service import brief_content
    if not isinstance(lineage,dict) or lineage.get('schema_version')!='content-intelligence-lineage-v1' or lineage.get('sha256')!=digest({k:v for k,v in lineage.items() if k!='sha256'}):
        raise WorkflowError('CONTENT_INTELLIGENCE_LINEAGE_CHANGED')
    brief=ContentBrief.model_validate(lineage['brief']); idea=ContentIdea.model_validate(lineage['idea']); run=ResearchRun.model_validate(lineage['run'])
    if brief.status!='APPROVED' or not brief.approval or brief.idea_id!=idea.id or brief.idea_version!=idea.version or idea.run_id!=run.id or brief.run_id!=run.id:
        raise WorkflowError('CONTENT_INTELLIGENCE_APPROVAL_LINEAGE_INVALID')
    if lineage['approved_brief_sha256']!=digest(brief_content(lineage['brief'])) or brief.approval['brief_content_sha256']!=lineage['approved_brief_sha256']:
        raise WorkflowError('CONTENT_INTELLIGENCE_APPROVED_BRIEF_CHANGED')
    sources=[ResearchSource.model_validate(s) for s in lineage['sources']]; findings=[ResearchFinding.model_validate(f) for f in lineage['findings']]
    validate_findings(sources,findings)
    if set(run.source_ids)!={s.id for s in sources} or set(run.finding_ids)!={f.id for f in findings} or not set(idea.supporting_research)<={f.id for f in findings if f.kind=='SOURCED_FACT'} or not set(brief.source_references)<={s.id for s in sources}:
        raise WorkflowError('CONTENT_INTELLIGENCE_REFERENCES_INVALID')
    if brief.key_facts!=[next(f.claim for f in findings if f.id==identifier) for identifier in idea.supporting_research]:
        raise WorkflowError('CONTENT_INTELLIGENCE_FACTS_CHANGED')
    result={'schema_version':lineage['schema_version'],'research_run_id':run.id,'content_idea_id':idea.id,'content_idea_version':idea.version,'content_brief_id':brief.id,'content_brief_version':brief.version,'approved_brief_sha256':lineage['approved_brief_sha256'],'lineage_sha256':lineage['sha256'],'source_references':[{'id':s.id,'reference':s.reference,'content_sha256':s.content_sha256,'retrieved_at':s.retrieved_at.isoformat()} for s in sources]}
    if run.context.get('trend_radar') is not None:
        from .trend_radar_lineage import validate as validate_trend
        result['trend_radar']=validate_trend(run.context['trend_radar'])
    return result


def projection(doc):
    return validate(doc['content_intelligence']) if doc.get('content_intelligence') else None
