"""Pinned compilation only; graphs and approval references are explicit fixtures."""
import hashlib
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from npd_comfyui_bridge.execution_models import GraphInputBinding, VerifiedReferenceToken
from npd_comfyui_bridge.graph_compiler import compile_reviewed_graph
from npd_comfyui_bridge.workflows import WorkflowRegistry
from test_bridge import MANIFEST


def registry_fixture(tmp_path, *, reference=False):
    original = json.loads(MANIFEST.read_text(encoding='utf-8'))
    definition = next(item for item in original['workflows'] if item['workflow_id'] ==
        ('npd-image-to-image-v1' if reference else 'npd-text-to-image-v1'))
    graph = {'1': {'class_type': 'FixtureText', 'inputs': {'text': 'fixed template', 'seed': 1}},
        '2': {'class_type': 'FixtureCanvas', 'inputs': {'width': 512, 'height': 512}},
        '3': {'class_type': 'FixtureSave', 'inputs': {'image': 'fixed-owned.png', 'source': ['2', 0]}}}
    graph_path = tmp_path / definition['graph_file']; raw = json.dumps({'prompt': graph}).encode(); graph_path.write_bytes(raw)
    bindings = [{'parameter': 'prompt', 'node_id': '1', 'input_name': 'text'},
        {'parameter': 'seed', 'node_id': '1', 'input_name': 'seed'},
        {'parameter': 'aspect_ratio', 'node_id': '2', 'input_name': 'width', 'transform': 'aspect_width'},
        {'parameter': 'aspect_ratio', 'node_id': '2', 'input_name': 'height', 'transform': 'aspect_height'}]
    if reference:
        bindings.append({'parameter': 'reference_images', 'index': 0, 'node_id': '3', 'input_name': 'image', 'transform': 'verified_reference'})
    definition['execution'] = {'graph_sha256': hashlib.sha256(raw).hexdigest(), 'approval_reference': 'EXPLICIT TEST FIXTURE; not Owner approval',
        'approval_kind': 'explicit_fixture', 'allowed_node_classes': ['FixtureText', 'FixtureCanvas', 'FixtureSave'],
        'bindings': bindings, 'output_nodes': ['3'], 'aspect_dimensions': {'9:16': [576, 1024]}}
    manifest = tmp_path / 'manifest.json'; manifest.write_text(json.dumps({'manifest_version': 'explicit-fixture-v1', 'workflows': [definition]}))
    registry = WorkflowRegistry(manifest)
    return registry, registry.get(definition['workflow_id']), graph_path, graph


def inputs(**values): return {'prompt': 'Explicit scalar fixture', 'aspect_ratio': '9:16', 'seed': 27, **values}


def test_fixed_graph_nodes_model_choices_and_file_bytes_remain_unchanged(tmp_path):
    registry, definition, path, original = registry_fixture(tmp_path); original_bytes = path.read_bytes()
    graph = compile_reviewed_graph(registry=registry, definition=definition, inputs=inputs(), workspace_id='workspace-A', allow_fixture=True)
    assert graph['1']['inputs'] == {'text': 'Explicit scalar fixture', 'seed': 27}
    assert graph['2']['inputs'] == {'width': 576, 'height': 1024}
    assert graph['3'] == original['3'] and path.read_bytes() == original_bytes
    graph['1']['class_type'] = 'UntrustedMutation'
    again = compile_reviewed_graph(registry=registry, definition=definition, inputs=inputs(), workspace_id='workspace-A', allow_fixture=True)
    assert again['1']['class_type'] == 'FixtureText'


def test_repository_placeholders_and_fixture_approval_never_become_live_execution(tmp_path):
    registry = WorkflowRegistry(MANIFEST)
    with pytest.raises(ValueError, match='EXECUTION_NOT_CONFIGURED'):
        compile_reviewed_graph(registry=registry, definition=registry.get('npd-text-to-image-v1'), inputs=inputs(), workspace_id='workspace-A')
    fixture, definition, _, _ = registry_fixture(tmp_path)
    with pytest.raises(ValueError, match='FIXTURE_GRAPH_EXECUTION_FORBIDDEN'):
        compile_reviewed_graph(registry=fixture, definition=definition, inputs=inputs(), workspace_id='workspace-A')


def test_pinned_graph_hash_changes_fail_before_compilation(tmp_path):
    registry, definition, path, _ = registry_fixture(tmp_path)
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='CHECKSUM_CHANGED'):
        compile_reviewed_graph(registry=registry, definition=definition, inputs=inputs(), workspace_id='workspace-A', allow_fixture=True)


def test_references_need_matching_verified_uploaded_tokens_and_never_read_urls(tmp_path):
    registry, definition, _, _ = registry_fixture(tmp_path, reference=True)
    reference = 'https://untrusted.invalid/never-download.png'
    payload = inputs(reference_images=[reference])
    with pytest.raises(ValueError, match='VERIFIED_REFERENCE_NOT_CONFIGURED'):
        compile_reviewed_graph(registry=registry, definition=definition, inputs=payload, workspace_id='workspace-A', allow_fixture=True)
    token = VerifiedReferenceToken(workspace_id='workspace-A', source_reference=reference, source_sha256='a' * 64,
        uploaded_filename='owned-fixture.png', upload_sha256='b' * 64, fixture=True)
    graph = compile_reviewed_graph(registry=registry, definition=definition, inputs=payload, workspace_id='workspace-A',
        verified_references={reference: token}, allow_fixture=True)
    assert graph['3']['inputs']['image'] == 'owned-fixture.png'
    with pytest.raises(ValueError, match='SCOPE_INVALID'):
        compile_reviewed_graph(registry=registry, definition=definition, inputs=payload, workspace_id='workspace-B',
            verified_references={reference: token}, allow_fixture=True)
    with pytest.raises(ValidationError): token.model_copy(update={}).__class__(**{**token.model_dump(), 'uploaded_filename': '../private.png'})


def test_node_and_binding_declarations_reject_unreviewed_changes(tmp_path):
    registry, definition, _, _ = registry_fixture(tmp_path)
    definition.execution.allowed_node_classes = ['UnrelatedNode']
    with pytest.raises(ValueError, match='NODE_INVALID'):
        compile_reviewed_graph(registry=registry, definition=definition, inputs=inputs(), workspace_id='workspace-A', allow_fixture=True)


def test_legacy_definition_fingerprint_excludes_new_unconfigured_execution_field():
    registry = WorkflowRegistry(MANIFEST); definition = registry.get('npd-text-to-image-v1')
    old = definition.model_dump(mode='json'); old.pop('execution')
    graph_sha = hashlib.sha256((MANIFEST.parent / definition.graph_file).read_bytes()).hexdigest()
    expected = hashlib.sha256(json.dumps({'definition': old, 'graph_sha256': graph_sha}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    assert registry.fingerprint(definition) == expected


@pytest.mark.parametrize('parameter,index,transform', [('reference_images', 0, 'identity'),
    ('mask_reference', None, 'identity'), ('seed', 0, 'identity'), ('prompt', None, 'aspect_width')])
def test_reference_and_aspect_bindings_cannot_bypass_typed_transforms(parameter, index, transform):
    with pytest.raises(ValidationError): GraphInputBinding(parameter=parameter, node_id='1', input_name='image', index=index, transform=transform)
