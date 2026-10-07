"""Native same-origin/session/CSRF/RBAC adapter; no provider browser automation."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError

from .contracts import WorkflowError
from .publication_models import NativePublicationCreate, NativePublishApproval, NativePublicationAction

ID = r'[a-f0-9]{32}'
PUBLICATION = r'npub_[a-f0-9]{32}'


def actor(handler):
    session = getattr(handler, 'auth_session', None)
    return session.principal.token_id if session else 'loopback-owner'


def get(handler, path):
    match = re.fullmatch(r'/api/projects/(' + ID + r')/publications(?:/(' + PUBLICATION + r'))?', path)
    if not match: raise WorkflowError('ROUTE_NOT_FOUND', 404)
    project, publication = match.groups()
    params = parse_qs(handler.path.partition('?')[2], keep_blank_values=True)
    if publication:
        if params: raise WorkflowError('NATIVE_PUBLICATION_PAGE_INVALID', 400)
        return handler.server.publications.get(project, publication)
    if set(params) - {'limit', 'cursor'} or any(len(values) != 1 for values in params.values()):
        raise WorkflowError('NATIVE_PUBLICATION_PAGE_INVALID', 400)
    try: limit = int(params.get('limit', ['25'])[0])
    except ValueError: raise WorkflowError('NATIVE_PUBLICATION_PAGE_INVALID', 400) from None
    return handler.server.publications.page(project, limit=limit, cursor=params.get('cursor', [None])[0])


def post(handler, path, body):
    match = re.fullmatch(r'/api/projects/(' + ID + r')/publications(?:/(' + PUBLICATION + r')/(approve|cancel|dry-run))?', path)
    if not match: raise WorkflowError('ROUTE_NOT_FOUND', 404)
    project, publication, action = match.groups(); service = handler.server.publications
    try:
        if action is None:
            value, replay = service.create(project, NativePublicationCreate.model_validate(body), actor=actor(handler))
            return {**value, 'idempotent_replay': replay}
        if action == 'approve': return service.approve(project, publication, NativePublishApproval.model_validate(body), actor=actor(handler))
        payload = NativePublicationAction.model_validate(body)
        if action == 'cancel': return service.cancel(project, publication, payload, actor=actor(handler))
        return service.process(project=project, identity=publication, fingerprint=payload.expected_fingerprint) or service.get(project, publication)
    except (ValidationError, TypeError): raise WorkflowError('NATIVE_PUBLICATION_FIELDS_INVALID', 400) from None
