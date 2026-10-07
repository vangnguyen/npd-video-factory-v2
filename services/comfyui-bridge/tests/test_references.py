"""Actual local image decode; reference rights and GPU wires are explicit fixtures."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
from email.parser import BytesParser
from email.policy import default

import httpx
import pytest
from pydantic import ValidationError
from npd_comfyui_bridge.binary_artifacts import digest
from npd_comfyui_bridge.http_transport import ComfyHTTPTransport
from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore
from npd_comfyui_bridge.reference_models import ReferenceAdmission
from npd_comfyui_bridge.reference_stager import ScopedReferenceStager
from npd_comfyui_bridge.reference_store import ReferenceError, ReferenceStore
from test_binary_artifacts import tools, media
from test_bridge import load_bridge_app
from test_graph_compiler import registry_fixture, inputs
from test_http_backend import WireFixture, build, terminal


def admission(content, *, suffix='png', **changes):
    current = datetime.now(timezone.utc)
    values = {'workspace_id': 'workspace-A', 'project_id': 'project-A', 'asset_id': 'a'*32 + '.' + suffix,
        'content_sha256': hashlib.sha256(content).hexdigest(), 'mime_type': 'image/png' if suffix == 'png' else 'image/jpeg',
        'rights_status': 'owned', 'authorization_kind': 'registered_rights', 'rights_receipt_sha256': 'b'*64,
        'issued_at': current, 'expires_at': current + timedelta(minutes=30), 'fixture': True, **changes}
    return ReferenceAdmission.model_validate(values)


@pytest.mark.parametrize('changes', [{'rights_status': 'unknown'}, {'rights_status': 'restricted'},
    {'authorization_kind': 'explicit_owner_override', 'rights_status': 'unknown'}, {'fixture': 1},
    {'asset_id': '../private.png'}, {'mime_type': 'image/jpeg'}, {'graph': {}}, {'api_key': 'private'},
    {'expires_at': datetime.now(timezone.utc) + timedelta(days=1)}])
def test_admission_rejects_unauthorized_rights_graph_secret_path_fixture_and_unbounded_validity(changes):
    with pytest.raises(ValidationError): admission(b'fixture', **changes)


def test_owner_exception_preserves_known_raw_rights_that_still_require_scoped_review():
    # A copied registered asset can retain licensed metadata while requiring a
    # fresh project decision. The service assertion retains the actual status.
    value = admission(b'fixture', authorization_kind='explicit_owner_override', rights_status='licensed', fixture=False)
    assert value.rights_status == 'licensed' and value.authorization_kind == 'explicit_owner_override'
    with pytest.raises(ValidationError): admission(b'fixture', authorization_kind='explicit_owner_override', rights_status='restricted', fixture=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix', ['png', 'jpg'])
async def test_actual_image_registration_exact_replay_and_workspace_project_scope(tmp_path, tools, media, suffix):
    store = ReferenceStore(tmp_path / 'references', validator=tools, enabled=True)
    value = admission(media[suffix], suffix=suffix)
    document = await store.register(admission=value, content=media[suffix])
    assert document['media']['full_decode_passed'] and document['media']['decoded_video_frames'] == 1
    assert document['rights_independently_verified'] is False and document['publishing_authorized'] is False
    assert await store.register(admission=value, content=media[suffix]) == document
    loaded, path = store.read(workspace_id='workspace-A', project_id='project-A', source_reference=document['source_reference'])
    assert loaded == document and path.read_bytes() == media[suffix]
    for workspace, project in [('workspace-B', 'project-A'), ('workspace-A', 'project-B')]:
        with pytest.raises(ReferenceError): store.read(workspace_id=workspace, project_id=project, source_reference=document['source_reference'])
    second = await store.register(admission=admission(media[suffix], suffix=suffix, workspace_id='workspace-B'), content=media[suffix])
    assert second['reference_id'] != document['reference_id']


@pytest.mark.asyncio
async def test_bad_hash_magic_full_decode_or_disabled_intake_never_registers_content(tmp_path, tools, media):
    store = ReferenceStore(tmp_path / 'references', validator=tools)
    with pytest.raises(ReferenceError, match='NOT_CONFIGURED'):
        await store.register(admission=admission(media['png']), content=media['png'])
    store.enabled = True
    with pytest.raises(ReferenceError, match='CONTENT_INVALID'):
        await store.register(admission=admission(media['png']), content=media['jpg'])
    fake = b'\x89PNG\r\n\x1a\nheader only'
    with pytest.raises(RuntimeError): await store.register(admission=admission(fake), content=fake)
    assert not list(store.root.rglob('reference.json')) and not list(store.root.rglob('.partial-*'))


@pytest.mark.asyncio
async def test_expired_admission_changed_bytes_and_rehashed_scope_metadata_fail_closed(tmp_path, tools, media):
    store = ReferenceStore(tmp_path / 'references', validator=tools, enabled=True)
    value = admission(media['png']); document = await store.register(admission=value, content=media['png'])
    scope = {'workspace_id': value.workspace_id, 'project_id': value.project_id, 'source_reference': document['source_reference']}
    _, path = store.read(**scope)
    store.clock = lambda: value.expires_at
    with pytest.raises(ReferenceError, match='EXPIRED'): store.read(**scope)
    store.clock = lambda: value.issued_at
    original = path.read_bytes(); path.write_bytes(original+b'changed')
    with pytest.raises(ReferenceError): store.read(**scope)
    path.write_bytes(original)
    metadata = path.parent / 'reference.json'; wrapper = json.loads(metadata.read_bytes())
    wrapper['document']['admission']['project_id'] = 'project-B'; wrapper['sha256'] = digest(wrapper['document'])
    metadata.write_text(json.dumps(wrapper))
    with pytest.raises(ReferenceError): store.read(**{**scope, 'project_id': 'project-B'})


class InputWire:
    def __init__(self): self.content, self.calls, self.lost, self.reject, self.corrupt = {}, [], False, False, False
    async def handle(self, request):
        self.calls.append((request.method, request.url.path))
        assert request.headers['Authorization'] == 'Bearer explicit-reference-fixture-token'
        if request.method == 'GET':
            filename = request.url.params['filename']
            assert request.url.path == '/view' and request.url.params['type'] == 'input'
            if filename not in self.content: return httpx.Response(404, json={})
            content, mime = self.content[filename]
            return httpx.Response(200, content=content+b'corrupt' if self.corrupt else content, headers={'Content-Type': mime})
        assert request.url.path == '/upload/image'
        message = BytesParser(policy=default).parsebytes(('Content-Type: '+request.headers['Content-Type']+'\r\n\r\n').encode()+request.content)
        parts = {part.get_param('name', header='content-disposition'): part for part in message.iter_parts()}
        assert parts['overwrite'].get_payload(decode=True) == b'false' and parts['type'].get_payload(decode=True) == b'input'
        image = parts['image']; filename = image.get_filename()
        if self.reject: return httpx.Response(502, json={'secret': 'provider-secret private body'})
        assert filename not in self.content
        self.content[filename] = (image.get_payload(decode=True), image.get_content_type())
        if self.lost:
            self.lost = False
            return httpx.Response(502, json={'secret': 'provider-secret private body'})
        return httpx.Response(200, json={'name': filename, 'type': 'input', 'subfolder': ''})


async def staged(tmp_path, tools, media, wire):
    references = ReferenceStore(tmp_path / 'references', validator=tools, enabled=True)
    document = await references.register(admission=admission(media['png']), content=media['png'])
    store = SQLiteBridgeJobStore(tmp_path / 'jobs.sqlite3')
    transport = ComfyHTTPTransport(origin='http://127.0.0.1:8188', server_source_sha256='a'*64, enabled=True,
        bearer_token='explicit-reference-fixture-token', transport=httpx.MockTransport(wire.handle))
    stager = ScopedReferenceStager(references=references, transport=transport, job_store=store)
    return references, document, store, transport, stager


@pytest.mark.asyncio
async def test_upload_full_decoded_owned_bytes_no_overwrite_readback_and_restart_receipt(tmp_path, tools, media):
    wire = InputWire(); references, document, store, transport, stager = await staged(tmp_path, tools, media, wire)
    values = {'workspace_id': 'workspace-A', 'project_id': 'project-A', 'source_reference': document['source_reference']}
    try:
        token = await stager(**values)
        assert token.project_id == 'project-A' and token.source_sha256 == token.upload_sha256 == hashlib.sha256(media['png']).hexdigest()
        assert token.fixture and wire.calls == [('GET','/view'),('POST','/upload/image'),('GET','/view')]
        assert await stager(**values) == token and sum(m=='POST' for m,p in wire.calls) == 1
        row = store.connection.execute('SELECT document FROM bridge_reference_uploads').fetchone()[0]
        assert b'fixture-token' not in row and json.loads(row)['state'] == 'confirmed' and json.loads(row)['actual_cost_vnd'] is None
    finally: store.close(); await transport.close()
    reopened = SQLiteBridgeJobStore(tmp_path / 'jobs.sqlite3')
    second = ComfyHTTPTransport(origin='http://127.0.0.1:8188', server_source_sha256='a'*64, enabled=True,
        bearer_token='explicit-reference-fixture-token', transport=httpx.MockTransport(wire.handle))
    try:
        assert await ScopedReferenceStager(references=references, transport=second, job_store=reopened)(**values) == token
        assert sum(m=='POST' for m,p in wire.calls) == 1
    finally: reopened.close(); await second.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('accepted', [True, False])
async def test_lost_upload_reply_reads_reserved_name_and_never_repeats_unresolved_write(tmp_path, tools, media, accepted):
    wire = InputWire(); wire.lost = accepted; wire.reject = not accepted
    references, document, store, transport, stager = await staged(tmp_path, tools, media, wire)
    values = {'workspace_id': 'workspace-A', 'project_id': 'project-A', 'source_reference': document['source_reference']}
    try:
        with pytest.raises(ReferenceError, match='RECOVERY_REQUIRED'): await stager(**values)
        if accepted:
            assert (await stager(**values)).upload_sha256 == hashlib.sha256(media['png']).hexdigest()
        else:
            with pytest.raises(ReferenceError, match='RECOVERY_REQUIRED'): await stager(**values)
        assert sum(m=='POST' for m,p in wire.calls) == 1
    finally: store.close(); await transport.close()


@pytest.mark.asyncio
async def test_foreign_scope_untrusted_urls_and_corrupt_stored_input_cannot_make_prompt_or_upload_writes(tmp_path, tools, media):
    wire = InputWire(); references, document, store, transport, stager = await staged(tmp_path, tools, media, wire)
    values = {'workspace_id': 'workspace-A', 'project_id': 'project-A', 'source_reference': document['source_reference']}
    try:
        for change in [{'workspace_id':'foreign'},{'project_id':'foreign'},{'source_reference':'https://forbidden.invalid/private.png'},
                       {'source_reference':r'C:\private.png'}]:
            with pytest.raises(ReferenceError): await stager(**{**values,**change})
        assert not wire.calls
        await stager(**values); count = len(wire.calls)
        wire.corrupt = True
        with pytest.raises(ReferenceError): await stager(**values)
        assert len(wire.calls) == count+1 and sum(m=='POST' for m,p in wire.calls) == 1
        wire.corrupt = False; wire.content.clear()
        with pytest.raises(ReferenceError): await stager(**values)
        assert sum(m=='POST' for m,p in wire.calls) == 1
    finally: store.close(); await transport.close()


@pytest.mark.asyncio
async def test_authenticated_bounded_intake_uses_actual_decode_and_metadata_is_project_scoped(monkeypatch, tmp_path, tools, media):
    bootstrap=tmp_path/'bootstrap'; bootstrap.mkdir()
    app=load_bridge_app(monkeypatch,execution_enabled=False,tmp_path=bootstrap)
    references=ReferenceStore(tmp_path/'reference-http',validator=tools,enabled=True);app.state.reference_store=references
    value=admission(media['png']); metadata=json.dumps(value.model_dump(mode='json'))
    auth={'Authorization':'Bearer explicit-fixture-service-token-32-characters','X-VF-Workspace-Id':'workspace-A',
        'Content-Type':'image/png','X-VF-Reference-Admission':metadata}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post('/v1/references',content=media['png'])).status_code==401
            assert (await client.post('/v1/references',content=media['png'],headers={**auth,'X-VF-Workspace-Id':'foreign'})).status_code==422
            assert (await client.post('/v1/references',content=media['png'],headers={**auth,'Content-Length':str(33*1024**2)})).status_code==422
            assert (await client.post('/v1/references',content=b'bad',headers=auth)).status_code==422
            assert (await client.post('/v1/references',content=media['png'],headers={**auth,'Content-Length':'1'})).status_code==422
            async def oversized(): yield b'x'*(33*1024**2)
            assert (await client.post('/v1/references',content=oversized(),headers=auth)).status_code==413
            assert (await client.post('/v1/references',content=media['png'],headers={**auth,'X-VF-Reference-Admission':'{"workspace_id":"workspace-A","workspace_id":"foreign"}'})).status_code==422
            response=await client.post('/v1/references',content=media['png'],headers=auth)
            assert response.status_code==201; document=response.json(); assert document['media']['full_decode_passed']
            assert (await client.post('/v1/references',content=media['png'],headers=auth)).json()==document
            route='/v1/references/'+document['reference_id']
            assert (await client.get(route,headers=auth)).status_code==404
            assert (await client.get(route,headers={**auth,'X-VF-Project-Id':'foreign'})).status_code==404
            assert (await client.get(route,headers={**auth,'X-VF-Project-Id':'project-A'})).json()==document
            references.enabled=False
            assert (await client.post('/v1/references',content=media['png'],headers=auth)).status_code==503
    finally: await app.state.bridge_service.close()


@pytest.mark.asyncio
async def test_physical_reference_upload_compiles_pinned_graph_and_registers_actual_output(tmp_path, tools, media):
    registry, definition, _, _ = registry_fixture(tmp_path,reference=True)
    outputs = WireFixture(media['png']); input_wire=InputWire()
    async def all_wires(request):
        if request.url.path=='/upload/image' or request.url.path=='/view' and request.url.params.get('type')=='input':
            # Same protected token belongs to this explicitly shared GPU fixture.
            headers=httpx.Headers(request.headers);headers['Authorization']='Bearer explicit-reference-fixture-token'
            copied=httpx.Request(request.method,request.url,headers=headers,content=request.content)
            return await input_wire.handle(copied)
        return await outputs.handle(request)
    service, store, artifacts, payload=build(tmp_path,tools,outputs,registry=registry)
    transport=ComfyHTTPTransport(origin='http://127.0.0.1:8188',server_source_sha256='a'*64,enabled=True,
        bearer_token='explicit-fixture-gpu-token',transport=httpx.MockTransport(all_wires))
    service.backend.transport=transport
    references=ReferenceStore(tmp_path/'references',validator=tools,enabled=True)
    document=await references.register(admission=admission(media['png']),content=media['png'])
    service.backend.reference_resolver=ScopedReferenceStager(references=references,transport=transport,job_store=store)
    payload.project_id='project-A';payload.inputs=inputs(reference_images=[document['source_reference']])
    try:
        job=await service.submit(payload);done=await terminal(service,job.job_id)
        assert done.status=='succeeded' and done.project_id=='project-A'
        uploaded=next(iter(input_wire.content));graph=next(iter(outputs.prompts.values()))
        assert graph['3']['inputs']['image']==uploaded and input_wire.content[uploaded][0]==media['png']
        artifact=artifacts.read(workspace_id='workspace-A',job_id=job.job_id,artifact_id=done.result['artifact_reference'].removeprefix('vf-artifact://'))
        assert artifact.document['provenance']['source_reference_sha256']==[hashlib.sha256(media['png']).hexdigest()]
        assert artifact.document['media']['full_decode_passed'] and artifact.document['rights_status']=='unknown'
        assert sum(m=='POST' for m,p in input_wire.calls)==1 and len(outputs.prompts)==1
    finally: await service.close()


@pytest.mark.asyncio
async def test_fixture_source_never_reaches_live_transport_and_corrupt_upload_journal_never_writes(tmp_path,tools,media):
    wire=InputWire();references,document,store,transport,stager=await staged(tmp_path,tools,media,wire)
    live=ComfyHTTPTransport(origin='http://127.0.0.1:8188',server_source_sha256='a'*64,enabled=True)
    values={'workspace_id':'workspace-A','project_id':'project-A','source_reference':document['source_reference']}
    try:
        with pytest.raises(ReferenceError,match='FIXTURE_LIVE_FORBIDDEN'):
            await ScopedReferenceStager(references=references,transport=live,job_store=store)(**values)
        assert live._client is None and not wire.calls
        await stager(**values);count=len(wire.calls)
        with store.connection:store.connection.execute('UPDATE bridge_reference_uploads SET document=?',(b'{}',))
        with pytest.raises(RuntimeError,match='JOURNAL_INVALID'):await stager(**values)
        assert len(wire.calls)==count
    finally:store.close();await transport.close();await live.close()
