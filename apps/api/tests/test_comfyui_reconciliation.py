"""Read-only service lookup wires; no GPU, paid operation or genuine media."""
import json
import httpx,pytest
from app.comfyui_binary_result import checksum
from app.media_generation_scope import media_generation_scope
from app.media_intelligence_models import ImageGenerationInput
from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider,_stable_token
from app.media_generation_routes import generation_envelope,workflow_routes

TOKEN='explicit-reconciliation-wire-fixture-token-32'
PAYLOAD=ImageGenerationInput(prompt='EXPLICIT RECONCILIATION FIXTURE',seed=7)


def expected(payload=PAYLOAD):
    workflow,_,inputs=generation_envelope('image',payload,workflow_routes('image','npd-text-to-image-v1'))
    return {'workspace_id':'workspace-A','workflow_id':workflow,'inputs':inputs,
        'client_request_id':_stable_token('workspace-A','project-A','job-A',payload.model_dump_json(),workflow)}


def lookup_value(request):
    return {'job':{'workspace_id':'workspace-A','project_id':None,'job_id':'cui_saved_fixture','workflow_id':request['workflow_id'],
        'client_request_id':request['client_request_id'],'workflow_version':'1.0.0','status':'succeeded','progress':100,
        'result':{'artifact_reference':'fixture://reconciliation-metadata-only','fixture':True}},
        'request_sha256':checksum({'project_id':None,'workflow_version':None,**request})}


def provider(wire,**options):
    return ComfyUIBridgeGenerationProvider(bridge_url='http://explicit-fixture.test',modality='image',workflow_id='npd-text-to-image-v1',
        enabled=True,service_token=TOKEN,transport=httpx.MockTransport(wire),timeout_seconds=1,**options)


@pytest.mark.asyncio
async def test_lost_submission_looks_up_same_request_without_reposting_or_inventing_provider_ticket():
    calls=[];saved={};observations=[]
    async def observe(value):observations.append(value)
    def wire(request):
        calls.append((request.method,request.url.path));assert request.headers['Authorization']=='Bearer '+TOKEN
        assert request.headers['X-VF-Workspace-Id']=='workspace-A'
        if request.method=='POST':
            body=json.loads(request.content);saved.update(lookup_value(body));raise httpx.ReadError('EXPLICIT LOST SUBMISSION REPLY')
        assert request.url.path.endswith('/'+expected()['client_request_id']);return httpx.Response(200,json=saved)
    adapter=provider(wire,on_job=observe)
    with media_generation_scope(workspace_id='workspace-A',project_id='project-A',job_id='job-A'):
        with pytest.raises(httpx.ReadError):await adapter.generate(PAYLOAD)
        result=await adapter.reconcile(PAYLOAD)
    assert [method for method,_ in calls]==['POST','GET'] and result.provider_job_id=='cui_saved_fixture'
    assert observations[0]['phase']=='reconciled' and result.rights_status=='unknown' and result.actual_cost_vnd is None
    assert not result.production_eligible and not result.real_provider_tested and result.generation_provenance['fixture']
    assert TOKEN not in json.dumps(observations) and PAYLOAD.prompt not in json.dumps(observations)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['request_sha256','client_key','workspace','workflow','known_ticket','project'])
async def test_lookup_binding_drift_rejects_before_observation_cancel_poll_or_result(change):
    calls=[];observed=[];request=expected();value=lookup_value(request);options={}
    if change=='request_sha256':value['request_sha256']='0'*64
    if change=='client_key':value['job']['client_request_id']='foreign'
    if change=='workspace':value['job']['workspace_id']='foreign'
    if change=='workflow':value['job']['workflow_id']='npd-video-generation-v1'
    if change=='known_ticket':options['provider_job_id']='cui_other_ticket'
    payload=PAYLOAD
    if change=='project':
        payload=ImageGenerationInput(prompt=PAYLOAD.prompt,seed=7,operation='image_to_image',reference_images=['vf-reference://'+'a'*64])
        value=lookup_value(expected(payload));value['job']['project_id']='foreign'
        value['request_sha256']=checksum({'workflow_version':None,'project_id':'project-A',**expected(payload)})
    def wire(request):calls.append(request.method);return httpx.Response(200,json=value)
    async def observe(value):observed.append(value)
    adapter=provider(wire,on_job=observe,cancel_requested=lambda:True)
    with media_generation_scope(workspace_id='workspace-A',project_id='project-A',job_id='job-A'):
        with pytest.raises(ValueError):await adapter.reconcile(payload,**options)
    assert calls==['GET'] and not observed


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['absent','redirect','oversized','duplicate','extra','mime'])
async def test_unavailable_or_invalid_lookup_never_submits_redirects_or_leaks_response(fault):
    calls=[]
    def wire(request):
        calls.append((request.method,request.url.host))
        if fault=='absent':return httpx.Response(404,json={'secret':'private provider body'})
        if fault=='redirect':return httpx.Response(307,headers={'Location':'https://foreign.test/private'})
        if fault=='oversized':return httpx.Response(200,content=b'x'*65537,headers={'Content-Type':'application/json'})
        if fault=='duplicate':return httpx.Response(200,content=b'{"job":{},"job":{}}',headers={'Content-Type':'application/json'})
        value=lookup_value(expected())
        if fault=='extra':value['secret']='private provider body'
        if fault=='mime':return httpx.Response(200,json=value,headers={'Content-Type':'text/plain'})
        return httpx.Response(200,json=value)
    with media_generation_scope(workspace_id='workspace-A',project_id='project-A',job_id='job-A'):
        with pytest.raises(ValueError) as error:await provider(wire).reconcile(PAYLOAD)
    assert calls==[('GET','explicit-fixture.test')] and 'private provider body' not in str(error.value)


@pytest.mark.asyncio
async def test_invalid_known_ticket_fails_before_network_and_pending_cancel_targets_only_reconciled_job():
    calls=[];value=lookup_value(expected());value['job']['status']='running'
    def wire(request):
        calls.append((request.method,request.url.path))
        if request.method=='GET':return httpx.Response(200,json=value)
        assert request.url.path=='/v1/jobs/cui_saved_fixture/cancel';job={**value['job'],'status':'cancelled','error_code':'CANCELLED'}
        return httpx.Response(200,json=job)
    adapter=provider(wire,cancel_requested=lambda:True)
    with media_generation_scope(workspace_id='workspace-A',project_id='project-A',job_id='job-A'):
        with pytest.raises(ValueError):await adapter.reconcile(PAYLOAD,provider_job_id='../other')
        assert not calls
        with pytest.raises(RuntimeError,match='CANCELLED'):await adapter.reconcile(PAYLOAD,provider_job_id='cui_saved_fixture')
    assert [method for method,_ in calls]==['GET','POST']
