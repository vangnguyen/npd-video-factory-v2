"""Native manual delivery endpoints; authenticated by the existing HTTP boundary."""
import os
import re
from urllib.parse import quote,unquote,parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .manual_delivery import DeliveryCreate, CaptionSave, RecreatePackage, EXPORT_ID

BASE = r'/api/projects/([a-f0-9]{32})/exports'


def get(handler, path):
    match=re.fullmatch(BASE+r'(?:/('+EXPORT_ID+r')(?:/files/([^/]+))?)?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,export_id,filename=match.groups();service=handler.server.manual_delivery
    query=handler.path.partition('?')[2];options={}
    if query:
        try:
            values=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
            if export_id or set(values)-{'before','limit'} or any(len(v)!=1 for v in values.values()):raise ValueError()
            if 'before' in values:
                before=values['before'][0]
                if not re.fullmatch(EXPORT_ID,before):raise ValueError()
                options['before']=before
            if 'limit' in values:
                if not re.fullmatch(r'[1-9][0-9]{0,2}',values['limit'][0]):raise ValueError()
                options['limit']=int(values['limit'][0])
                if options['limit']>100:raise ValueError()
        except ValueError:raise WorkflowError('EXPORT_QUERY_INVALID',400) from None
    if filename:
        filename=unquote(filename)
        source=service.file(project,export_id,filename)
        return handler.file(source,video=filename.endswith('.mp4'),headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename), 'Cache-Control':'no-store'})
    return handler.reply(service.get(project,export_id) if export_id else service.page(project,**options),headers={'Cache-Control':'no-store'})


def post(handler, path, body):
    service=handler.server.manual_delivery
    match=re.fullmatch(BASE+r'(?:/('+EXPORT_ID+r')/(open-folder|recreate-package|resume|abandon))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,export_id,action=match.groups()
    def authorized():
        if handler.server.access is not None:
            handler.server.access.authorize(handler.auth_session,'POST',handler.path)
    if action in ('resume','abandon'):
        if body:raise WorkflowError('EXPORT_FIELDS_INVALID',400)
        return getattr(service,action)(project,export_id,authorization_check=authorized)
    if action=='recreate-package':
        try:payload=RecreatePackage.model_validate(body)
        except (ValidationError,TypeError):raise WorkflowError('EXPORT_FIELDS_INVALID',400) from None
        return service.recreate(project,export_id,payload,authorization_check=authorized)
    if export_id:
        if body:raise WorkflowError('EXPORT_FIELDS_INVALID',400)
        if os.name!='nt' or not hasattr(os,'startfile'):raise WorkflowError('EXPORT_OPEN_FOLDER_UNAVAILABLE',400)
        value=service.get(project,export_id)
        if value['status']!='ready':raise WorkflowError('EXPORT_NOT_READY')
        os.startfile(value['output_location'])
        return {'opened':True,'externally_posted':False}
    try:payload=DeliveryCreate.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('EXPORT_FIELDS_INVALID',400) from None
    return service.create(project,payload,authorization_check=authorized)


def captions(handler, project, body=None):
    if body is None:
        query=handler.path.partition('?')[2];options={}
        if query:
            try:
                values=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
                if set(values)-{'before_version','limit'} or any(len(v)!=1 or not re.fullmatch(r'[1-9][0-9]{0,9}',v[0]) for v in values.values()):raise ValueError()
                options={k:int(v[0]) for k,v in values.items()}
            except ValueError:raise WorkflowError('EXPORT_QUERY_INVALID',400) from None
        return handler.server.manual_delivery.copies(project,**options)
    try:payload=CaptionSave.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('EXPORT_CAPTION_FIELDS_INVALID',400) from None
    return handler.server.manual_delivery.save_copy(project,payload)


def covers(handler,path,*,write=False):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/delivery-covers(?:/(ncov_[a-f0-9]{32})/image)?',path)
    if not match or handler.path.partition('?')[2]:raise WorkflowError('EXPORT_QUERY_INVALID',400)
    project,identifier=match.groups();service=handler.server.manual_delivery.covers
    if not write:
        if identifier:
            source,row=service.read(project,identifier)
            raw=source.read_bytes();handler.send_response(200);handler.common(row['content_type'],len(raw),{'Cache-Control':'no-store'});handler.end_headers();handler.wfile.write(raw)
            return
        return handler.reply(service.page(project),headers={'Cache-Control':'no-store'})
    if identifier:raise WorkflowError('ROUTE_NOT_FOUND',404)
    try:length=int(handler.headers.get('Content-Length','0'));revision=int(handler.headers.get('X-VF-Revision','0'))
    except ValueError:raise WorkflowError('EXPORT_COVER_HEADERS_INVALID',400) from None
    from .delivery_covers import MAX_BYTES
    if handler.headers.get('Transfer-Encoding') or not 0<length<=MAX_BYTES:raise WorkflowError('EXPORT_COVER_MAX_8MB',400)
    raw=handler.rfile.read(length)
    if len(raw)!=length:raise WorkflowError('EXPORT_COVER_INCOMPLETE',400)
    def authorized():
        if handler.server.access is not None:handler.server.access.authorize(handler.auth_session,'POST',handler.path)
    return handler.reply(service.upload(project,revision,raw,unquote(handler.headers.get('X-VF-Filename','cover')),
        handler.headers.get('Content-Type','').split(';')[0],authorization_check=authorized),headers={'Cache-Control':'no-store'})
