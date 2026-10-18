"""Native manual delivery endpoints; authenticated by the existing HTTP boundary."""
import os
import re
from urllib.parse import quote,unquote
from pydantic import ValidationError
from .contracts import WorkflowError
from .manual_delivery import DeliveryCreate, CaptionSave, EXPORT_ID

BASE = r'/api/projects/([a-f0-9]{32})/exports'


def get(handler, path):
    if handler.path.partition('?')[2]:raise WorkflowError('EXPORT_QUERY_INVALID',400)
    match=re.fullmatch(BASE+r'(?:/('+EXPORT_ID+r')(?:/files/([^/]+))?)?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,export_id,filename=match.groups();service=handler.server.manual_delivery
    if filename:
        filename=unquote(filename)
        source=service.file(project,export_id,filename)
        return handler.file(source,video=filename.endswith('.mp4'),headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename), 'Cache-Control':'no-store'})
    return handler.reply(service.get(project,export_id) if export_id else service.page(project),headers={'Cache-Control':'no-store'})


def post(handler, path, body):
    service=handler.server.manual_delivery
    match=re.fullmatch(BASE+r'(?:/('+EXPORT_ID+r')/open-folder)?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,export_id=match.groups()
    if export_id:
        if body:raise WorkflowError('EXPORT_FIELDS_INVALID',400)
        if os.name!='nt' or not hasattr(os,'startfile'):raise WorkflowError('EXPORT_OPEN_FOLDER_UNAVAILABLE',400)
        value=service.get(project,export_id)
        if value['status']!='ready':raise WorkflowError('EXPORT_NOT_READY')
        os.startfile(value['output_location'])
        return {'opened':True,'externally_posted':False}
    try:payload=DeliveryCreate.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('EXPORT_FIELDS_INVALID',400) from None
    def authorized():
        if handler.server.access is not None:
            handler.server.access.authorize(handler.auth_session,'POST',handler.path)
    return service.create(project,payload,authorization_check=authorized)


def captions(handler, project, body=None):
    if body is None:return handler.server.manual_delivery.copies(project)
    try:payload=CaptionSave.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('EXPORT_CAPTION_FIELDS_INVALID',400) from None
    return handler.server.manual_delivery.save_copy(project,payload)
