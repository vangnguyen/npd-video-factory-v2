"""Lifecycle hooks and cancellation use explicit wire fixtures, never GPU work."""
import copy,json
import httpx,pytest
from app.media_generation_scope import media_generation_scope
from app.media_intelligence_models import ImageGenerationInput
from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider

TOKEN='explicit-lifecycle-wire-fixture-token-32-characters'


def job(status='queued',progress=10):return {'job_id':'cui_lifecycle_fixture','workspace_id':'workspace-A','workflow_id':'npd-text-to-image-v1',
    'workflow_version':'1.0.0','status':status,'progress':progress,'provider_private_body':'SECRET MUST NOT APPEAR IN HOOK',
    'result':{'artifact_reference':'fixture://lifecycle-only','fixture':True}}


async def generate(handler,**options):
    adapter=ComfyUIBridgeGenerationProvider(bridge_url='http://explicit-fixture-bridge',modality='image',workflow_id='npd-text-to-image-v1',
        enabled=True,service_token=TOKEN,transport=httpx.MockTransport(handler),**options)
    with media_generation_scope(workspace_id='workspace-A',project_id='project-A',job_id='resolution-A'):
        return await adapter.generate(ImageGenerationInput(prompt='PRIVATE PROMPT MUST NOT APPEAR IN HOOK',seed=17))


@pytest.mark.asyncio
async def test_observations_are_bound_content_free_exact_progress_and_do_not_mutate_provider_job():
    events=[];polls=0
    def handler(request):
        nonlocal polls
        assert request.headers['Authorization']=='Bearer '+TOKEN
        if request.method=='POST':return httpx.Response(202,json=job())
        polls+=1;return httpx.Response(200,json=job('running',35) if polls==1 else job('succeeded',100))
    async def observe(value):events.append(copy.deepcopy(value));value['progress']=999
    result=await generate(handler,on_job=observe)
    assert [event['progress'] for event in events]==[10,35,100]
    assert [event['phase'] for event in events]==['submitted','polled','polled']
    assert [event['status'] for event in events]==['queued','running','succeeded']
    assert all(event['provider_job_id']=='cui_lifecycle_fixture' and event['workspace_id']=='workspace-A' for event in events)
    assert all('SECRET' not in json.dumps(event) and 'PRIVATE PROMPT' not in json.dumps(event) and TOKEN not in json.dumps(event) for event in events)
    assert result.provider_job_id=='cui_lifecycle_fixture' and result.generation_provenance['fixture']
    assert result.rights_status=='unknown' and result.actual_cost_vnd is None and not result.production_eligible


@pytest.mark.asyncio
async def test_cancel_targets_exact_scoped_job_once_and_never_uses_global_interrupt():
    events=[];calls=[];cancel=[False]
    async def observe(value):events.append(value);cancel[0]=True
    def handler(request):
        calls.append((request.method,request.url.path));assert request.headers['X-VF-Workspace-Id']=='workspace-A'
        if request.url.path=='/v1/jobs':return httpx.Response(202,json=job())
        assert request.method=='POST' and request.url.path=='/v1/jobs/cui_lifecycle_fixture/cancel'
        return httpx.Response(200,json=job('cancelled',10))
    with pytest.raises(RuntimeError,match='BRIDGE_FAILURE'):
        await generate(handler,on_job=observe,cancel_requested=lambda:cancel[0])
    assert calls==[('POST','/v1/jobs'),('POST','/v1/jobs/cui_lifecycle_fixture/cancel')]
    assert [event['phase'] for event in events]==['submitted','cancel_requested','cancel_response']
    assert events[-1]['status']=='cancelled'


@pytest.mark.asyncio
async def test_cancellation_racing_success_retains_actual_result_instead_of_false_cancel():
    events=[];cancel=[False]
    async def observe(value):events.append(value);cancel[0]=True
    def handler(request):return httpx.Response(202 if request.url.path=='/v1/jobs' else 200,json=job('queued' if request.url.path=='/v1/jobs' else 'succeeded',100))
    result=await generate(handler,on_job=observe,cancel_requested=lambda:cancel[0])
    assert result.provider_job_id=='cui_lifecycle_fixture' and events[-1]['status']=='succeeded'
    assert events[-1]['phase']=='cancel_response' and result.generation_provenance['fixture']


@pytest.mark.asyncio
@pytest.mark.parametrize('hook,error',[(lambda:True,'CANCELLED_BEFORE_SUBMISSION'),(lambda:1,'CANCEL_HOOK_INVALID')])
async def test_cancelled_before_submit_and_nonboolean_hook_make_zero_requests(hook,error):
    def handler(_request):raise AssertionError('No provider dispatch expected')
    with pytest.raises((RuntimeError,ValueError),match=error):await generate(handler,cancel_requested=hook)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[{'progress':True},{'progress':101},{'status':'invented'},{'workflow_version':'x'*41}])
async def test_malformed_progress_status_or_version_rejected_before_observation(change):
    events=[]
    async def observe(value):events.append(value)
    with pytest.raises(ValueError,match='OBSERVATION_INVALID'):
        await generate(lambda _request:httpx.Response(202,json={**job(),**change}),on_job=observe)
    assert events==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[{'job_id':'cui_foreign'},{'workspace_id':'workspace-B'},{'workflow_id':'npd-upscale-v1'}])
async def test_foreign_cancel_receipt_never_updates_observer(change):
    events=[];cancel=[False]
    async def observe(value):events.append(value);cancel[0]=True
    def handler(request):return httpx.Response(202 if request.url.path=='/v1/jobs' else 200,json=job() if request.url.path=='/v1/jobs' else {**job('cancelled'),**change})
    with pytest.raises(ValueError,match='BINDING_INVALID'):await generate(handler,on_job=observe,cancel_requested=lambda:cancel[0])
    assert [event['phase'] for event in events]==['submitted','cancel_requested']


@pytest.mark.asyncio
async def test_unknown_cancel_outcome_is_not_retried_or_exposes_provider_body():
    calls=[];cancel=[False]
    async def observe(_value):cancel[0]=True
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(202,json=job()) if request.url.path=='/v1/jobs' else httpx.Response(503,text='SECRET provider failure body')
    with pytest.raises(RuntimeError,match='TARGETED_CANCEL_HTTP_FAILED') as error:
        await generate(handler,on_job=observe,cancel_requested=lambda:cancel[0])
    assert 'SECRET' not in str(error.value) and len(calls)==2


@pytest.mark.asyncio
async def test_observer_failure_after_submission_does_not_resubmit_or_poll():
    calls=[]
    def handler(request):calls.append(request.url.path);return httpx.Response(202,json=job())
    async def observe(_value):raise RuntimeError('EXPLICIT DURABLE JOURNAL FAILURE FIXTURE')
    with pytest.raises(RuntimeError,match='JOURNAL FAILURE'):await generate(handler,on_job=observe)
    assert calls==['/v1/jobs']


@pytest.mark.asyncio
async def test_unavailable_progress_stays_null_in_completed_observation():
    events=[];value=job('succeeded');value.pop('progress')
    async def observe(item):events.append(item)
    await generate(lambda _request:httpx.Response(202,json=value),on_job=observe)
    assert len(events)==1 and events[0]['progress'] is None and events[0]['status']=='succeeded'
