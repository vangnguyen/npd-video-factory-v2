"""Read-only lost-submission lookup, bound to the complete frozen request."""
import asyncio,json,re
from .comfyui_binary_result import checksum


async def lookup(client,request,*,provider_job_id=None,timeout_seconds=30):
    if provider_job_id is not None and (not isinstance(provider_job_id,str) or not re.fullmatch(r'cui_[A-Za-z0-9_-]{1,80}',provider_job_id)):
        raise ValueError('COMFYUI_RECONCILIATION_TICKET_INVALID')
    async with asyncio.timeout(timeout_seconds):
        async with client.stream('GET','/v1/jobs/by-client-request/'+request['client_request_id']) as response:
            if response.status_code!=200:raise ValueError('COMFYUI_RECONCILIATION_LOOKUP_REQUIRED')
            if response.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('COMFYUI_RECONCILIATION_RESULT_INVALID')
            content=bytearray()
            async for chunk in response.aiter_bytes():
                if len(chunk)>65536-len(content):raise ValueError('COMFYUI_RECONCILIATION_RESULT_INVALID')
                content.extend(chunk)
    def pairs(items):
        values={}
        for key,value in items:
            if key in values:raise ValueError('COMFYUI_RECONCILIATION_RESULT_INVALID')
            values[key]=value
        return values
    try:value=json.loads(bytes(content),object_pairs_hook=pairs)
    except (ValueError,TypeError):raise ValueError('COMFYUI_RECONCILIATION_RESULT_INVALID') from None
    normalized={'project_id':None,'workflow_version':None,**request}
    if (not isinstance(value,dict) or set(value)!={'job','request_sha256'} or not isinstance(value.get('job'),dict)
        or value.get('request_sha256')!=checksum(normalized) or value['job'].get('client_request_id')!=request['client_request_id']
        or provider_job_id is not None and value['job'].get('job_id')!=provider_job_id):raise ValueError('COMFYUI_RECONCILIATION_BINDING_INVALID')
    return value['job']
