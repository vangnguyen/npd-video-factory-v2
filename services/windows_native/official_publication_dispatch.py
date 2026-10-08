"""One durable, fenced official upload decision before any provider request."""
from dataclasses import dataclass,field
import re
from .contracts import WorkflowError

@dataclass(frozen=True)
class Ticket:
    publication_id:str
    workspace_id:str
    project_id:str
    snapshot_sha256:str
    approval_id:str
    operation:str
    version:int
    intent_id:str=field(repr=False)
    def __post_init__(self):
        if (not isinstance(self.publication_id,str) or not re.fullmatch(r'nopu_[a-f0-9]{32}',self.publication_id)
            or not isinstance(self.workspace_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',self.workspace_id)
            or not isinstance(self.project_id,str) or not re.fullmatch(r'[a-f0-9]{32}',self.project_id)
            or not isinstance(self.snapshot_sha256,str) or not re.fullmatch(r'[a-f0-9]{64}',self.snapshot_sha256)
            or not isinstance(self.approval_id,str) or not re.fullmatch(r'nopa_[a-f0-9]{32}',self.approval_id)
            or self.operation not in ('init','chunk','reconcile') or type(self.version) is not int or self.version<2
            or not isinstance(self.intent_id,str) or not re.fullmatch(r'[a-f0-9]{32}',self.intent_id)):
            raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_TICKET_INVALID',400)
