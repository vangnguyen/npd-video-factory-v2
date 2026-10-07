"""Compile only pinned reviewed source files and explicitly bound scalar inputs.

This module performs no HTTP, local asset lookup or GPU execution. Live callers
must independently verify owner admission and any uploaded reference tokens.
"""
import copy
import hashlib
import json
import math
from .job_store import linked
from .execution_models import VerifiedReferenceToken


def compile_reviewed_graph(*, registry, definition, inputs,
                           workspace_id, verified_references=None, allow_fixture=False):
    approved = registry.get(definition.workflow_id, definition.version)
    if approved.model_dump(mode='json', exclude_none=True) != definition.model_dump(mode='json', exclude_none=True):
        raise ValueError('GRAPH_DEFINITION_NOT_IN_MANIFEST')
    execution = definition.execution
    if execution is None:
        raise ValueError('APPROVED_GRAPH_EXECUTION_NOT_CONFIGURED')
    registry.validate_inputs(definition, inputs)
    if execution.approval_kind == 'explicit_fixture' and not allow_fixture:
        raise ValueError('FIXTURE_GRAPH_EXECUTION_FORBIDDEN')
    path = registry.manifest_path.parent / definition.graph_file
    if linked(path) or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('APPROVED_GRAPH_PATH_INVALID')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != execution.graph_sha256:
        raise ValueError('APPROVED_GRAPH_CHECKSUM_CHANGED')
    try:
        document = json.loads(raw)
    except ValueError:
        raise ValueError('APPROVED_GRAPH_INVALID') from None
    graph = document.get('prompt', document) if isinstance(document, dict) else None
    if not isinstance(graph, dict) or not 1 <= len(graph) <= 500:
        raise ValueError('APPROVED_GRAPH_NOT_EXECUTABLE')
    allowed = set(execution.allowed_node_classes)
    for node_id, node in graph.items():
        if (not isinstance(node_id, str) or not isinstance(node, dict) or node.get('class_type') not in allowed
                or not isinstance(node.get('inputs'), dict) or set(node) - {'class_type', 'inputs', '_meta'}):
            raise ValueError('APPROVED_GRAPH_NODE_INVALID')
    if any(node not in graph for node in execution.output_nodes):
        raise ValueError('APPROVED_GRAPH_OUTPUT_MISSING')
    result = copy.deepcopy(graph)
    for binding in execution.bindings:
        if binding.node_id not in result or binding.input_name not in result[binding.node_id]['inputs']:
            raise ValueError('APPROVED_GRAPH_BINDING_MISSING')
        if binding.parameter not in inputs:
            raise ValueError('APPROVED_GRAPH_PARAMETER_MISSING')
        value = inputs[binding.parameter]
        if binding.index is not None:
            if not isinstance(value, list) or len(value) <= binding.index:
                raise ValueError('APPROVED_GRAPH_REFERENCE_MISSING')
            value = value[binding.index]
        if binding.transform == 'verified_reference':
            token = (verified_references or {}).get(value)
            if not isinstance(token, VerifiedReferenceToken):
                raise ValueError('VERIFIED_REFERENCE_NOT_CONFIGURED')
            if token.workspace_id != workspace_id or token.source_reference != value or token.fixture and not allow_fixture:
                raise ValueError('VERIFIED_REFERENCE_SCOPE_INVALID')
            value = token.uploaded_filename
        elif binding.transform in {'aspect_width', 'aspect_height'}:
            dimensions = execution.aspect_dimensions.get(value)
            if not dimensions:
                raise ValueError('APPROVED_GRAPH_ASPECT_NOT_CONFIGURED')
            value = dimensions[0 if binding.transform == 'aspect_width' else 1]
        if (not isinstance(value, (str, int, float, bool)) or
                isinstance(value, float) and not math.isfinite(value)):
            raise ValueError('APPROVED_GRAPH_NON_SCALAR_INPUT')
        result[binding.node_id]['inputs'][binding.input_name] = value
    # No graph node/class or unbound model choice came from client input.
    return result
