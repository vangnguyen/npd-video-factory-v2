"""Separate rendered-quality provider configuration; never asset-consent reuse."""
import hashlib,inspect,json,re
from typing import Literal
import httpx
from pydantic import Field,StrictInt,model_validator
from app.models import StrictModel
from app.openai_vision_provider import OpenAIVisionProvider
from .contracts import WorkflowError,digest,file_sha
from .official_account_tokens import protected_path,unique_pairs
from .vision_registry import VisionProfile
from .vision_credentials import NativeVisionKeyVault
from .render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor


class RenderVisionProfile(VisionProfile):
    schema_version:Literal['native-render-vision-profile-v1']='native-render-vision-profile-v1'
    profile_id:str=Field(pattern=r'^nrvp_[a-f0-9]{32}$')
    purpose:Literal['rendered_video_quality_review']='rendered_video_quality_review'


class RenderVisionRegistry(StrictModel):
    schema_version:Literal['native-render-vision-registry-v1']='native-render-vision-registry-v1'
    version:StrictInt=Field(ge=1,le=1)
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    profiles:list[RenderVisionProfile]=Field(default_factory=list,max_length=8)

    @model_validator(mode='after')
    def scoped_unique_profiles(self):
        if (len({p.profile_id for p in self.profiles})!=len(self.profiles)
            or len({p.key_receipt.credential_alias for p in self.profiles})!=len(self.profiles)
            or any(p.key_receipt.workspace_id!=self.workspace_id for p in self.profiles)):
            raise ValueError('Unique rendered-QC workspace profiles required')
        return self


class NativeRenderVisionFactory:
    def __init__(self,profile,vault,*,operator_enabled=False,transport=None,registry_file=None,registry_sha256=None):
        if (type(profile) is not RenderVisionProfile or type(vault) is not NativeVisionKeyVault or type(operator_enabled) is not bool
            or transport is not None and type(transport) is not httpx.MockTransport or profile.key_receipt.workspace_id!=vault.workspace
            or (registry_file is None)!=(registry_sha256 is None)
            or registry_sha256 is not None and (type(registry_sha256) is not str or not re.fullmatch(r'[a-f0-9]{64}',registry_sha256))):
            raise WorkflowError('NATIVE_RENDER_VISION_CONFIGURATION_INVALID',400)
        self.profile=profile.model_copy(deep=True);self.vault=vault;self.root=vault.root;self.workspace=vault.workspace
        self.operator_enabled=operator_enabled;self.transport=transport;self.mock=transport is not None
        self.registry_file=protected_path(registry_file,self.root) if registry_file is not None else None
        self.registry_sha256=registry_sha256
        self._frozen=(vault,self.root,self.workspace,operator_enabled,transport,self.mock,self.registry_file,registry_sha256)
        self._profile=self.profile.model_dump(mode='json',warnings=False)
        self.sha256=digest({'schema_version':'native-render-vision-provider-configuration-v1','profile':self._profile,
            'operator_enabled':operator_enabled,'mock':self.mock,'registry_sha256':registry_sha256})
        self._sha256=self.sha256;self.check()

    def check(self):
        try:
            if type(self.profile) is not RenderVisionProfile or set(self.profile.__dict__)-set(RenderVisionProfile.model_fields):raise ValueError()
            parsed=RenderVisionProfile.model_validate(self.profile.model_dump(mode='json',warnings=False))
            if ((self.vault,self.root,self.workspace,self.operator_enabled,self.transport,self.mock,self.registry_file,self.registry_sha256)!=self._frozen
                or digest(parsed.model_dump(mode='json'))!=digest(self._profile) or self.sha256!=self._sha256
                or self.workspace!=self.vault.workspace or self.root!=self.vault.root or type(self.operator_enabled) is not bool
                or type(self.mock) is not bool or self.mock!=(self.transport is not None)
                or self.transport is not None and type(self.transport) is not httpx.MockTransport):raise ValueError()
            self.vault.check()
            if self.registry_file is not None and (protected_path(self.registry_file,self.root)!=self.registry_file or not self.registry_file.is_file()
                or not 1<=self.registry_file.stat().st_size<=262144 or file_sha(self.registry_file)!=self.registry_sha256):raise ValueError()
            return parsed
        except Exception:raise WorkflowError('NATIVE_RENDER_VISION_CONFIGURATION_CHANGED') from None

    def public(self):
        profile=self.check();mounted=self.vault.present(profile.key_receipt)
        costs=self.mock or profile.estimated_cost_vnd>0 and profile.input_vnd_per_million_tokens>0 and profile.output_vnd_per_million_tokens>0
        configured=self.operator_enabled and profile.enabled and mounted and costs
        return {'schema_version':'native-render-vision-provider-configuration-v1','workspace_id':self.workspace,
            'profile':profile.model_dump(mode='json'),'configuration_sha256':self.sha256,'mock':self.mock,
            'status':'CONFIGURED' if configured else 'NOT_CONFIGURED','credential_present':mounted,'credential_verified':False,
            'startup_decryption':False,'frame_limit':8,'input_dimension_limit':960,'provider_http_timeout_seconds':90,
            'controller_hard_timeout_seconds':120,'max_output_tokens':8000,'current_owner_consent_required':True,
            'original_render_required':True,'result_and_cost_journal_required':True,'asset_analysis_consent_reused':False,
            'provider_authorized':False,'automatic_dispatch':False,'publishing_enabled':False,'real_provider_tested':False}

    def provider(self,extractor,*,response_observer=None,admission_guard=None):
        profile=self.check()
        if self.public()['status']!='CONFIGURED':raise WorkflowError('NATIVE_RENDER_VISION_PROVIDER_NOT_CONFIGURED')
        if (type(extractor) is not NativeRenderEvidenceFrameExtractor or extractor.root!=self.root or extractor.workspace!=self.workspace
            or type(extractor.max_frames) is not int or not 1<=extractor.max_frames<=8):
            raise WorkflowError('NATIVE_RENDER_VISION_PROVIDER_INPUT_INVALID',400)
        callbacks=[v for v in (admission_guard,response_observer) if v is not None]
        if any(not callable(v) or inspect.iscoroutinefunction(v) or inspect.iscoroutinefunction(getattr(v,'__call__',None)) for v in callbacks):
            raise WorkflowError('NATIVE_RENDER_VISION_CONTROLLER_INVALID',400)
        if not self.mock and (admission_guard is None or response_observer is None):
            raise WorkflowError('NATIVE_RENDER_VISION_OWNER_CONTROLLER_REQUIRED',400)
        original=extractor.binding()
        if not original['matches_current_project_document']:raise WorkflowError('NATIVE_RENDER_VISION_CURRENT_RENDER_REQUIRED')
        def fence():
            self.check()
            if admission_guard is not None:
                decision=admission_guard()
                if decision is not None:
                    if inspect.iscoroutine(decision):decision.close()
                    raise WorkflowError('NATIVE_RENDER_VISION_CONTROLLER_INVALID',400)
            if self.public()['status']!='CONFIGURED' or digest(extractor.binding())!=digest(original):
                raise WorkflowError('NATIVE_RENDER_VISION_INPUT_OR_PROFILE_CHANGED')
        def resolve(alias):
            fence();current=self.check()
            if current.key_receipt.credential_alias!=alias:raise WorkflowError('NATIVE_RENDER_VISION_PROVIDER_NOT_CONFIGURED')
            key=self.vault.key(current.key_receipt);fence();return key
        fence()
        return OpenAIVisionProvider(credential_alias=profile.key_receipt.credential_alias,credential_resolver=resolve,
            frame_extractor=extractor,estimated_cost_vnd=profile.estimated_cost_vnd,
            input_vnd_per_million_tokens=profile.input_vnd_per_million_tokens,
            cached_input_vnd_per_million_tokens=profile.cached_input_vnd_per_million_tokens,
            output_vnd_per_million_tokens=profile.output_vnd_per_million_tokens,
            transport=self.transport,allow_zero_cost_contract_test=self.mock,response_observer=response_observer,dispatch_guard=fence)


def load(path,vault,*,operator_enabled=False):
    if type(vault) is not NativeVisionKeyVault or type(operator_enabled) is not bool:
        raise WorkflowError('NATIVE_RENDER_VISION_REGISTRY_INVALID',400)
    path=protected_path(path,vault.root)
    try:
        if not path.is_file() or not 1<=path.stat().st_size<=262144:raise ValueError()
        raw=path.read_bytes();registry=RenderVisionRegistry.model_validate(json.loads(raw,object_pairs_hook=unique_pairs));checksum=hashlib.sha256(raw).hexdigest()
        if registry.workspace_id!=vault.workspace or file_sha(path)!=checksum:raise ValueError()
        return {p.profile_id:NativeRenderVisionFactory(p,vault,operator_enabled=operator_enabled,registry_file=path,registry_sha256=checksum) for p in registry.profiles}
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_RENDER_VISION_REGISTRY_INVALID',400) from None
