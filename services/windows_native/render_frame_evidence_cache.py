"""Eight byte-verified pixel measurements scoped to one reader/directory/workspace.

No PNG bytes, provider result, consent or billing are cached. Every hit rereads
the physical file SHA; a content change measures again and cannot retain old facts.
"""
from collections import OrderedDict
import copy,re,threading
from pathlib import Path
from .backup import guard
from .contracts import WorkflowError,file_sha


class RenderFrameEvidenceCache:
    def __init__(self,directory,workspace):
        if not isinstance(workspace,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',workspace):raise WorkflowError('RENDER_FRAME_CACHE_SCOPE_INVALID',400)
        self.directory=Path(directory).absolute();self.workspace=workspace;self._frozen=(self.directory,workspace)
        self._entries=OrderedDict();self._lock=threading.RLock()
    def check(self,directory):
        if (self.directory,self.workspace)!=self._frozen or Path(directory).absolute()!=self.directory:raise WorkflowError('RENDER_FRAME_CACHE_SCOPE_CHANGED')
        guard(self.directory,exists=True)
    def measure(self,path):
        from .render_frame_qc import image_evidence,MAX_PNG_BYTES
        self.check(self.directory);path=guard(path,exists=True)
        if self.directory not in path.parents or path.suffix!='.png' or not path.is_file() or not 0<path.stat().st_size<=MAX_PNG_BYTES:
            raise WorkflowError('RENDER_FRAME_CACHE_INPUT_INVALID')
        with self._lock:
            key=str(path);fingerprint=file_sha(path);old=self._entries.get(key)
            if old is not None and old[0]==fingerprint:
                self._entries.move_to_end(key);return copy.deepcopy(old[1])
            measured=image_evidence(path)
            if measured['sha256']!=fingerprint or file_sha(path)!=fingerprint:raise WorkflowError('RENDER_FRAME_CACHE_INPUT_CHANGED')
            self._entries[key]=(fingerprint,copy.deepcopy(measured));self._entries.move_to_end(key)
            while len(self._entries)>8:self._entries.popitem(last=False)
            return copy.deepcopy(measured)
