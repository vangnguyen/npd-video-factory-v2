"""Server-owned execution identity and bounded, content-free failure states."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ExecutionContext:
    workspace_id: str
    job_id: str
    retry_count: int
    project_id: str | None = None

    def __post_init__(self):
        if (not isinstance(self.workspace_id, str) or not 1 <= len(self.workspace_id) <= 200
                or any(c.isspace() or ord(c) < 33 for c in self.workspace_id)
                or not isinstance(self.job_id, str) or not re.fullmatch(r'cui_[a-zA-Z0-9_-]{1,80}', self.job_id)
                or type(self.retry_count) is not int or not 0 <= self.retry_count <= 10):
            raise ValueError('BRIDGE_EXECUTION_SCOPE_INVALID')
        if self.project_id is not None and (not isinstance(self.project_id, str) or not 1 <= len(self.project_id) <= 200
                or any(c.isspace() or ord(c) < 33 for c in self.project_id)):
            raise ValueError('BRIDGE_EXECUTION_SCOPE_INVALID')


class BackendExecutionError(RuntimeError):
    CODES = {'REMOTE_RECOVERY_REQUIRED', 'REMOTE_JOB_FAILED', 'REMOTE_CANCELLED',
             'REMOTE_RESULT_INVALID', 'REMOTE_NOT_SUBMITTED', 'REMOTE_POLL_FAILED'}

    def __init__(self, code, *, recovery_required=False):
        if code not in self.CODES or type(recovery_required) is not bool:
            raise ValueError('BRIDGE_FAILURE_INVALID')
        self.code, self.recovery_required = code, recovery_required
        self.status = 'cancelled' if code == 'REMOTE_CANCELLED' else 'failed'
        super().__init__(code)
