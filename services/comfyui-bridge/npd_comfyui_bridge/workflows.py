from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .models import WorkflowDefinition, WorkflowManifest


class WorkflowRegistry:
    def __init__(self, manifest_path: Path):
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
        Draft202012Validator(definition.input_schema).validate(inputs)

    def validate_output(self, definition: WorkflowDefinition, output: dict) -> None:
        Draft202012Validator(definition.output_schema).validate(output)
