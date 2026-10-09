"""Narrow Google loopback callback; no generic session or CSRF bypass."""
import asyncio
from .contracts import WorkflowError

PATH='/oauth/google/callback'
MESSAGES={
    'received':('Authorization received','Return to Studio to review the connection and confirm the account. Publishing requires separate approval.'),
    'mock':('Protocol mock completed','This is a synthetic protocol result. Return to Studio to review its history.'),
    'denied':('Authorization declined','Return to Studio to review the request or prepare a new authorization.'),
    'attention':('Authorization needs review','Return to Studio to review the original operation. Do not retry an unknown outcome.'),
    'invalid':('Authorization could not complete','Return to Studio to review the request or prepare a new authorization.'),
}

def boundary(handler):
    port=handler.server.server_port;host=f'127.0.0.1:{port}'
    if handler.headers.get_all('Host',[])!=[host]:raise WorkflowError('LOOPBACK_HOST_REQUIRED',403)
    # External top-level redirects have no Studio SameSite session cookie.
    # Private state and the still-current saved Owner authorize only exchange.
    origins=handler.headers.get_all('Origin',[])
    if origins and origins not in ([f'http://{host}'],['https://accounts.google.com']):raise WorkflowError('SAME_ORIGIN_REQUIRED',403)
    for name,allowed in (('Sec-Fetch-Mode',{'navigate'}),('Sec-Fetch-Dest',{'document'}),('Sec-Fetch-Site',{'none','same-origin','cross-site'})):
        values=handler.headers.get_all(name,[])
        if values and (len(values)!=1 or values[0] not in allowed):raise WorkflowError('CROSS_SITE_REQUEST_BLOCKED',403)
    lengths=handler.headers.get_all('Content-Length',[])
    if handler.headers.get_all('Transfer-Encoding',[]) or lengths and lengths!=['0']:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CALLBACK_INVALID',400)
    if handler.path.split('?',1)[0]!=PATH or '?' not in handler.path or len(handler.path)>len(PATH)+1+8192 or '#' in handler.path:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CALLBACK_INVALID',400)
    return f'http://{host}{PATH}'

def dispatch(handler):
    """Always a fixed private response; never reflect query or provider details."""
    key='invalid';status=400
    # Do not leave an unconsumed private request body on a keep-alive connection.
    handler.close_connection=True
    try:
        redirect=boundary(handler);operations=handler.server.google_oauth
        if operations is None:raise WorkflowError('NATIVE_GOOGLE_OAUTH_NOT_CONFIGURED',503)
        value=asyncio.run(operations.callback(handler.path.partition('?')[2],redirect_uri=redirect))
        if value['status']=='succeeded':key='mock' if value['snapshot']['mock'] else 'received';status=200
        elif value['failure_code']=='GOOGLE_OAUTH_CONSENT_DENIED':key='denied';status=200
        else:key='attention';status=409
    except WorkflowError as error:
        status=403 if error.code in {'LOOPBACK_HOST_REQUIRED','SAME_ORIGIN_REQUIRED','CROSS_SITE_REQUEST_BLOCKED'} else 400
    except Exception:
        # No exception string, project, authority, code, state or token escapes.
        key='attention';status=409
    title,message=MESSAGES[key]
    raw=('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>'+title+'</title><main><h1>'+title+'</h1><p>'+message+'</p><p><a href="/">Return to Studio</a></p></main></html>').encode('utf-8')
    handler.send_response(status);handler.common('text/html; charset=utf-8',len(raw));handler.end_headers();handler.wfile.write(raw)
