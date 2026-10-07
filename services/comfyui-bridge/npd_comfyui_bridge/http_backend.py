"""Reviewed HTTP execution with durable write reservation and decoded artifacts.

No graph, origin, credentials or result descriptor comes from the client DTO.
A retry reconciles the saved prompt; only a confirmed terminal failure/cancel
or definitive rejected submission permits a new prompt on an explicit retry.
"""
from __future__ import annotations
import asyncio
import hashlib
from datetime import datetime, timezone
import time
import uuid

from .binary_artifacts import ArtifactProvenance, BinaryArtifactStore, digest
from .dispatch_models import PromptDispatch
from .execution_context import BackendExecutionError, ExecutionContext
from .execution_models import VerifiedReferenceToken
from .graph_compiler import compile_reviewed_graph, validate_reviewed_graph
from .http_transport import ComfyHTTPTransport, ComfyTransportError, RemoteArtifact
from .job_store import SQLiteBridgeJobStore, checksum


def now():
    return datetime.now(timezone.utc)


class ReviewedHTTPComfyUIBackend:
    cooperative_cancellation = True

    def __init__(self, *, registry, transport: ComfyHTTPTransport,
                 job_store: SQLiteBridgeJobStore, artifacts: BinaryArtifactStore,
                 reference_resolver=None, poll_seconds=0.5):
        if (not isinstance(transport, ComfyHTTPTransport) or not isinstance(job_store, SQLiteBridgeJobStore)
                or not isinstance(artifacts, BinaryArtifactStore) or not 0.01 <= poll_seconds <= 10
                or reference_resolver is not None and not callable(reference_resolver)):
            raise ValueError('COMFY_HTTP_BACKEND_CONFIG_INVALID')
        self.registry, self.transport, self.job_store, self.artifacts = registry, transport, job_store, artifacts
        self.reference_resolver, self.poll_seconds = reference_resolver, poll_seconds

    @property
    def configured(self):
        if not self.transport.configured or not self.artifacts.validator.configured:
            return False
        for definition in self.registry.manifest.workflows:
            try:
                validate_reviewed_graph(registry=self.registry, definition=definition, allow_fixture=self.transport.fixture)
                return True
            except (ValueError, KeyError):
                continue
        return False

    def admit(self, *, workflow, inputs, workspace_id, project_id=None):
        if not self.configured:
            raise RuntimeError('COMFY_HTTP_NOT_CONFIGURED')
        validate_reviewed_graph(registry=self.registry, definition=workflow, allow_fixture=self.transport.fixture)
        self.registry.validate_inputs(workflow, inputs)
        references = inputs.get('reference_images', []) + ([inputs['mask_reference']] if inputs.get('mask_reference') else [])
        if references and self.reference_resolver is None:
            raise ValueError('VERIFIED_REFERENCE_NOT_CONFIGURED')
        if references and project_id is None:
            raise ValueError('REFERENCE_PROJECT_SCOPE_REQUIRED')

    def _update(self, record, **values):
        updated = PromptDispatch.model_validate({**record.model_dump(mode='python'), **values, 'updated_at': now()})
        return self.job_store.save_dispatch(updated, previous=record)

    def _result(self, context, workflow, record):
        artifact = self.artifacts.read(workspace_id=context.workspace_id, job_id=context.job_id, artifact_id=record.artifact_id)
        document = artifact.document
        provenance = document['provenance']
        if (document['checksum_sha256'] != record.artifact_sha256 or document['fixture'] != self.transport.fixture
                or provenance['remote_prompt_id'] != record.prompt_id or provenance['workflow_id'] != workflow.workflow_id
                or provenance['workflow_version'] != workflow.version or provenance['inputs_sha256'] != record.inputs_sha256
                or provenance['server_source_sha256'] != self.transport.server_source_sha256
                or provenance['graph_sha256'] != workflow.execution.graph_sha256):
            raise BackendExecutionError('REMOTE_RESULT_INVALID', recovery_required=True)
        return {'artifact_reference': 'vf-artifact://' + document['artifact_id'],
            'checksum_sha256': document['checksum_sha256'], 'workflow_id': workflow.workflow_id,
            'workflow_version': workflow.version, 'fixture': self.transport.fixture}

    @staticmethod
    def _output(history, workflow, record, graph):
        if not isinstance(history, dict):
            raise BackendExecutionError('REMOTE_RESULT_INVALID', recovery_required=True)
        prompt = history.get('prompt')
        status = history.get('status')
        # The stored prompt is checked but never copied into public results/logs.
        if (not isinstance(prompt, list) or len(prompt) < 3 or prompt[1] != record.prompt_id
                or not isinstance(prompt[2], dict) or digest(prompt[2]) != digest(graph)
                or not isinstance(status, dict) or status.get('status_str') != 'success'
                or status.get('completed') is not True or not isinstance(history.get('outputs'), dict)):
            raise BackendExecutionError('REMOTE_RESULT_INVALID', recovery_required=True)
        candidates = []
        video = workflow.capability in {'image_to_video', 'video_generation'}
        for node in workflow.execution.output_nodes:
            outputs = history['outputs'].get(node, {})
            if not isinstance(outputs, dict):
                raise BackendExecutionError('REMOTE_RESULT_INVALID', recovery_required=True)
            for media_type in ('images', 'video', 'videos', 'gifs'):
                items = outputs.get(media_type, [])
                if not isinstance(items, list) or len(items) > 10:
                    raise BackendExecutionError('REMOTE_RESULT_INVALID', recovery_required=True)
                for item in items:
                    if not isinstance(item, dict):
                        raise BackendExecutionError('REMOTE_RESULT_INVALID', recovery_required=True)
                    filename = item.get('filename', '')
                    suffix = filename.rsplit('.', 1)[-1].lower() if isinstance(filename, str) else ''
                    if suffix in ({'mp4'} if video else {'png', 'jpg', 'jpeg'}):
                        candidates.append(RemoteArtifact(filename=filename, subfolder=item.get('subfolder', ''), type=item.get('type')))
        # A one-artifact contract must not silently choose among batch outputs.
        if len(candidates) != 1:
            raise BackendExecutionError('REMOTE_RESULT_INVALID', recovery_required=True)
        return candidates[0]

    async def execute(self, *, workflow, inputs, progress, cancelled, context: ExecutionContext):
        self.admit(workflow=workflow, inputs=inputs, workspace_id=context.workspace_id, project_id=context.project_id)
        record = self.job_store.latest_dispatch(context)
        transport_sha = digest({'origin': self.transport.origin, 'server_source_sha256': self.transport.server_source_sha256,
            'fixture': self.transport.fixture})
        if record and (record.inputs_sha256 != checksum(inputs)
                or record.transport_sha256 is not None and record.transport_sha256 != transport_sha):
            raise BackendExecutionError('REMOTE_RECOVERY_REQUIRED', recovery_required=True)
        # Cancellation before a fresh dispatch is confirmed locally. A saved
        # write intent must instead reach the targeted remote reconciliation.
        has_remote_intent = record is not None and record.state not in {'failed', 'cancelled', 'not_submitted'}
        verified = {}
        references = inputs.get('reference_images', []) + ([inputs['mask_reference']] if inputs.get('mask_reference') else [])
        if references and record and record.transport_sha256 is None:
            raise BackendExecutionError('REMOTE_RECOVERY_REQUIRED', recovery_required=True)
        for reference in dict.fromkeys(references):
            if cancelled.is_set() and not has_remote_intent:
                raise BackendExecutionError('REMOTE_CANCELLED')
            token = await self.reference_resolver(workspace_id=context.workspace_id, project_id=context.project_id, source_reference=reference)
            if not isinstance(token, VerifiedReferenceToken):
                raise ValueError('VERIFIED_REFERENCE_NOT_CONFIGURED')
            verified[reference] = token
        graph = compile_reviewed_graph(registry=self.registry, definition=workflow, inputs=inputs,
            workspace_id=context.workspace_id, project_id=context.project_id, verified_references=verified, allow_fixture=self.transport.fixture)
        graph_sha, inputs_sha = checksum(graph), checksum(inputs)
        binding = checksum({'origin': self.transport.origin, 'server_source_sha256': self.transport.server_source_sha256,
            'definition_sha256': self.registry.fingerprint(workflow), 'graph_sha256': graph_sha,
            'inputs_sha256': inputs_sha, 'fixture': self.transport.fixture})
        if record and record.binding_sha256 != binding:
            raise BackendExecutionError('REMOTE_RECOVERY_REQUIRED', recovery_required=True)
        if record and record.state == 'completed' and record.artifact_id:
            return self._result(context, workflow, record)
        new = record is None or record.state in {'failed', 'cancelled', 'not_submitted'} and context.retry_count > record.retry_count
        if new:
            if cancelled.is_set():
                raise BackendExecutionError('REMOTE_CANCELLED')
            record = PromptDispatch(workspace_id=context.workspace_id, job_id=context.job_id,
                retry_count=context.retry_count, prompt_id=str(uuid.uuid4()), binding_sha256=binding,
                transport_sha256=transport_sha,
                graph_sha256=graph_sha, inputs_sha256=inputs_sha, state='dispatching', created_at=now(), updated_at=now())
            # FULL synchronous SQLite commit precedes the first network await.
            record = self.job_store.save_dispatch(record)
            try:
                await self.transport.submit_prompt(prompt_id=record.prompt_id, graph=graph)
            except ComfyTransportError as exc:
                record = self._update(record, state='uncertain' if exc.uncertain_dispatch else 'not_submitted')
                raise BackendExecutionError('REMOTE_RECOVERY_REQUIRED' if exc.uncertain_dispatch else 'REMOTE_NOT_SUBMITTED',
                    recovery_required=exc.uncertain_dispatch) from None
            record = self._update(record, state='submitted')
        elif record.state in {'failed', 'cancelled', 'not_submitted'}:
            code = {'failed': 'REMOTE_JOB_FAILED', 'cancelled': 'REMOTE_CANCELLED', 'not_submitted': 'REMOTE_NOT_SUBMITTED'}[record.state]
            raise BackendExecutionError(code)
        started = time.monotonic()
        try:
            # Percentages describe bridge lifecycle stages, not invented GPU progress.
            await progress(15)
            while True:
                if cancelled.is_set() and not record.cancel_attempted and record.state != 'completed':
                    record = self._update(record, cancel_attempted=True)
                    try:
                        await self.transport.cancel_job(record.prompt_id)
                    except ComfyTransportError:
                        # A lost cancellation reply is reconciled by exact job reads.
                        # Never resend this write or report cancellation from its ACK.
                        if record.state != 'completed':
                            record = self._update(record, state='uncertain')
                remote = await self.transport.get_job(record.prompt_id)
                if remote is None:
                    # An absent job after an interrupted write is not proof of rejection.
                    raise BackendExecutionError('REMOTE_RECOVERY_REQUIRED', recovery_required=True)
                status = remote['status']
                if status in {'failed', 'cancelled'}:
                    record = self._update(record, state=status)
                    raise BackendExecutionError('REMOTE_JOB_FAILED' if status == 'failed' else 'REMOTE_CANCELLED')
                if status == 'completed':
                    if record.state != 'completed':
                        record = self._update(record, state='completed', adapter_elapsed_seconds=time.monotonic() - started)
                    history = await self.transport.history(record.prompt_id)
                    descriptor = self._output(history, workflow, record, graph)
                    await progress(80)
                    content, mime = await self.transport.download_artifact(descriptor)
                    provenance = ArtifactProvenance(model=', '.join(workflow.required_model_identifiers)[:200] or 'unspecified-reviewed-model',
                        workflow_id=workflow.workflow_id, workflow_version=workflow.version,
                        graph_sha256=workflow.execution.graph_sha256, server_source_sha256=self.transport.server_source_sha256,
                        inputs_sha256=inputs_sha, prompt_sha256=hashlib.sha256(inputs['prompt'].encode()).hexdigest(), seed=inputs['seed'],
                        remote_prompt_id=record.prompt_id, source_reference_sha256=[verified[r].source_sha256 for r in dict.fromkeys(references)],
                        adapter_elapsed_seconds=record.adapter_elapsed_seconds)
                    artifact = await self.artifacts.register(workspace_id=context.workspace_id, job_id=context.job_id,
                        content=content, mime_type=mime, provenance=provenance, fixture=self.transport.fixture)
                    record = self._update(record, artifact_id=artifact.document['artifact_id'], artifact_sha256=artifact.document['checksum_sha256'])
                    await progress(95)
                    return self._result(context, workflow, record)
                await asyncio.sleep(self.poll_seconds)
        except ComfyTransportError:
            raise BackendExecutionError('REMOTE_POLL_FAILED', recovery_required=True) from None

    async def close(self):
        await self.transport.close()
