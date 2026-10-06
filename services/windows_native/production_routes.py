"""Uses the native HTTP handler's existing session, origin and CSRF guards."""
import re
from .contracts import WorkflowError
from .production_intelligence import ProductionIntelligence


def service(handler):
    current = getattr(handler.server, 'production_intelligence', None)
    if current is None:
        current = ProductionIntelligence(handler.server.config, handler.server.store, handler.server.intelligence)
        handler.server.production_intelligence = current
    return current


def get(handler, path):
    current = service(handler)
    if path == '/api/production/queue':
        return current.queue()
    if path == '/api/production/calendar':
        return current.calendar()
    if path == '/api/production/profiles':
        return current.profiles()
    if path == '/api/production/library':
        return current.library()
    match = re.fullmatch(r'/api/production/batches/([A-Za-z0-9_-]{8,100})', path)
    if match:
        return current.planning.batch_receipt(match[1])
    match = re.fullmatch(r'/api/production/briefs/([0-9a-f]{32})/preflight', path)
    if match:
        return current.brief_preflight(match[1])
    match = re.fullmatch(r'/api/production/planning/([0-9a-f]{32})(/history)?', path)
    if match:
        return current.planning.history(match[1]) if match[2] else current.find(match[1])
    match = re.fullmatch(r'/api/production/videos/([0-9a-f]{32})', path)
    if match:
        return current.video(match[1])
    raise WorkflowError('ROUTE_NOT_FOUND', 404)


def post(handler, path, body):
    if not isinstance(body, dict):
        raise WorkflowError('PRODUCTION_FIELDS_INVALID', 400)
    current = service(handler)
    if path == '/api/production/batch':
        return current.batch(body)
    match = re.fullmatch(r'/api/production/briefs/([0-9a-f]{32})/approve', path)
    if match:
        return current.approve_brief(match[1], body)
    match = re.fullmatch(r'/api/production/planning/([0-9a-f]{32})', path)
    if match:
        changes = body.get('changes')
        if not isinstance(changes, dict):
            raise WorkflowError('PLANNING_FIELDS_INVALID', 400)
        return current.save_planning(match[1], body.get('version'), changes, body.get('reviewer'))
    raise WorkflowError('ROUTE_NOT_FOUND', 404)
