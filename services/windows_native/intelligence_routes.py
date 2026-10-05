"""Studio adapter retaining the native session/origin/CSRF boundary."""
import re
from pydantic import ValidationError
from .contracts import WorkflowError, digest


def get(handler,path):
    service=handler.server.intelligence
    if path=='/api/intelligence/config': return service.profiles()
    if path=='/api/intelligence/queue': return service.queue()
    if path=='/api/intelligence/runs': return service.store.list('ResearchRun')
    match=re.fullmatch(r'/api/intelligence/runs/([0-9a-f]{32})',path)
    if match: return service.bundle(match[1])
    match=re.fullmatch(r'/api/intelligence/records/([0-9a-f]{32})/history',path)
    if match: return service.store.history(match[1])
    match=re.fullmatch(r'/api/intelligence/projects/([0-9a-f]{32})/lineage',path)
    if match:
        from .intelligence_lineage import projection
        project=service.production.get(match[1]); result=projection(project['document'])
        if not result: raise WorkflowError('CONTENT_INTELLIGENCE_LINEAGE_NOT_FOUND',404)
        return {**result,'project_id':project['id'],'project_revision':project['revision'],'script_sha256':digest(project['document']['proposal']),
                'jobs':[{'id':j['id'],'kind':j['kind'],'status':j['status'],'revision':j['revision'],'snapshot_lineage_sha256':j['snapshot']['document']['content_intelligence']['sha256'],'final_sha256':(j['result'] or {}).get('qc',{}).get('final_sha256'),'final_review':j['final_review']} for j in project['jobs']]}
    raise WorkflowError('ROUTE_NOT_FOUND',404)


def post(handler,path,body):
    service=handler.server.intelligence
    try:
        if path=='/api/intelligence/runs': return service.create(body.get('query'),body.get('profile_id'),body.get('source_urls'))
        match=re.fullmatch(r'/api/intelligence/runs/([0-9a-f]{32})/(research|ideas)',path)
        if match:
            service.enqueue(match[1],body.get('version'),match[2],body.get('request_key'))
            return service.bundle(match[1])
        match=re.fullmatch(r'/api/intelligence/ideas/([0-9a-f]{32})/(select|edit|reject)',path)
        if match:
            identifier,action=match[1],match[2]
            if action=='select': service.select(identifier,body.get('version'),body.get('opportunity_version'),body.get('reviewer'))
            else: service.edit_idea(identifier,body.get('version'),body.get('changes',{}),body.get('reviewer'),'reject' if action=='reject' else 'edit')
            return service.bundle(service.store.get(identifier,'ContentIdea')['run_id'])
        match=re.fullmatch(r'/api/intelligence/briefs/([0-9a-f]{32})/(edit|approve|send)',path)
        if match:
            identifier,action=match[1],match[2]
            if action=='send':
                project=service.send(identifier,body.get('version'))
                return {'project_id':project['id'],'production_dispatch':False,'next':'human_script_review'}
            if action=='approve': service.approve_brief(identifier,body.get('version'),body.get('reviewer'),body.get('acknowledged'),body.get('note',''))
            else: service.edit_brief(identifier,body.get('version'),body.get('changes',{}),body.get('reviewer'))
            return service.bundle(service.store.get(identifier,'ContentBrief')['run_id'])
        match=re.fullmatch(r'/api/intelligence/opportunities/([0-9a-f]{32})/(reject|review)',path)
        if match:
            human=service.human(body.get('reviewer'),note=body.get('note',''))
            if match[2]=='reject' and not human['note']: raise WorkflowError('INTELLIGENCE_REJECTION_REASON_REQUIRED',400)
            with service.store.transaction() as con:
                opportunity=service.store.get(match[1],'Opportunity',con)
                if opportunity['production_project_id']: raise WorkflowError('INTELLIGENCE_ALREADY_IN_PRODUCTION_CREATE_NEW_RUN')
                if opportunity['brief_id']:
                    brief=service.store.get(opportunity['brief_id'],'ContentBrief',con)
                    service.store.put('ContentBrief',{**brief,'status':'DRAFT','approval':None},brief['version'],con)
                value=service.store.put('Opportunity',{**opportunity,'status':'REJECTED' if match[2]=='reject' else 'REVIEWING'},body.get('version'),con)
                service.store.decision(con,opportunity['id'],'human_'+match[2]+'_opportunity',human)
            return value
    except (ValidationError,TypeError): raise WorkflowError('INTELLIGENCE_FIELDS_INVALID',400) from None
    raise WorkflowError('ROUTE_NOT_FOUND',404)
