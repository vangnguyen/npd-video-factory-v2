"""Inert, purpose-bound analytics resolver over explicit selected OAuth grants."""
from pathlib import Path
from .contracts import WorkflowError,digest
from .google_oauth_selections import NativeGoogleOAuthSelections

class AnalyticsSelectionResolver:
    def __init__(self,binding,root,workspace):
        self.binding=binding.model_copy(deep=True);self.root=Path(root).absolute();self.workspace=workspace
        self.frozen=(digest(binding.model_dump(mode='json')),self.root,workspace);self.service=None;self.frozen_service=None
    def check(self):
        if (digest(self.binding.model_dump(mode='json')),self.root,self.workspace)!=self.frozen or self.service is not self.frozen_service:raise WorkflowError('NATIVE_GOOGLE_ANALYTICS_RESOLVER_CHANGED')
        if self.service is not None:
            if type(self.service) is not NativeGoogleOAuthSelections or self.service.purpose!='analytics' or self.service.store.root.absolute()!=self.root or self.service.workspace!=self.workspace:raise WorkflowError('NATIVE_GOOGLE_ANALYTICS_RESOLVER_CHANGED')
            self.service.check()
    def attach(self,service):
        self.check()
        if self.service is not None:raise WorkflowError('NATIVE_GOOGLE_ANALYTICS_RESOLVER_ALREADY_ATTACHED')
        if type(service) is not NativeGoogleOAuthSelections or service.purpose!='analytics' or service.store.root.absolute()!=self.root or service.workspace!=self.workspace:raise WorkflowError('NATIVE_GOOGLE_ANALYTICS_RESOLVER_CHANGED')
        service.check();slot=service.oauth.slots.get(self.binding.google_oauth_slot_id)
        if slot is None or slot.client.purpose!='analytics' or slot.target!=self.binding.target or slot.client.credential_alias!=self.binding.credential_alias:raise WorkflowError('NATIVE_GOOGLE_ANALYTICS_SLOT_CHANGED')
        self.service=self.frozen_service=service;self.check()
    def available(self,*,mock):
        self.check()
        if self.service is None:return False
        try:
            value,_=self.service.active(self.binding.google_oauth_slot_id,self.binding.target)
            return value['snapshot']['mock'] is mock
        except WorkflowError:return False
    def __call__(self,target):
        self.check()
        if self.service is None or target!=self.binding.target:raise WorkflowError('NATIVE_GOOGLE_ANALYTICS_SELECTION_REQUIRED')
        return self.service.credential(self.binding.google_oauth_slot_id,target)
