from __future__ import annotations

import json
import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator

from .models import WorkflowDefinition, WorkflowManifest
from .job_store import linked


class WorkflowRegistry:
    def __init__(self, manifest_path: Path):
        if linked(manifest_path) or manifest_path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('APPROVED_MANIFEST_PATH_INVALID')
        self.manifest_path = manifest_path.resolve()
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.manifest = WorkflowManifest.model_validate(payload)
        identifiers = [item.workflow_id for item in self.manifest.workflows]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("ComfyUI workflow IDs must be unique")
        self._definitions = {item.workflow_id: item for item in self.manifest.workflows}
        for definition in self.manifest.workflows:
            graph = (self.manifest_path.parent / definition.graph_file).resolve()
            if self.manifest_path.parent not in graph.parents or not graph.is_file():
                raise ValueError(f"approved workflow graph is missing: {definition.graph_file}")
            Draft202012Validator.check_schema(definition.input_schema)
            Draft202012Validator.check_schema(definition.output_schema)

    def get(self, workflow_id: str, version: str | None = None) -> WorkflowDefinition:
        try:
            definition = self._definitions[workflow_id]
        except KeyError as exc:
            raise KeyError("workflow is not in the approved allowlist") from exc
        if version is not None and version != definition.version:
            raise KeyError("workflow version is not in the approved allowlist")
        return definition

    def validate_inputs(self, definition: WorkflowDefinition, inputs: dict) -> None:
        def reject_graph(value):
            if isinstance(value, dict):
                if any(key in {'graph', 'prompt_graph', 'workflow_graph', 'model_weights'} for key in value):
                    raise ValueError('ARBITRARY_CLIENT_GRAPH_FORBIDDEN')
                for item in value.values():
                    reject_graph(item)
            elif isinstance(value, list):
                for item in value:
                    reject_graph(item)
        reject_graph(inputs)
        Draft202012Validator(definition.input_schema).validate(inputs)

    def validate_output(self, definition: WorkflowDefinition, output: dict) -> None:
        Draft202012Validator(definition.output_schema).validate(output)

    def fingerprint(self, definition: WorkflowDefinition) -> str:
        graph = self.manifest_path.parent / definition.graph_file
        if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in [graph, *graph.parents]):
            raise ValueError('APPROVED_WORKFLOW_PATH_INVALID')
        if graph.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('APPROVED_WORKFLOW_TOO_LARGE')
        value = {'definition': definition.model_dump(mode='json', exclude_none=True), 'graph_sha256': hashlib.sha256(graph.read_bytes()).hexdigest()}
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
