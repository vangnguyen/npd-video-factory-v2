"""Protected Native factory over the existing approved bridge/workflow contracts.

The server does not accept client graphs, endpoints, tokens or workflow routes.
Stub/unreviewed workflows remain NOT_CONFIGURED even with enabled credentials.
"""
import hashlib,json,sys
from pathlib import Path
from urllib.parse import urlsplit
from pydantic import Field,StrictBool,StrictInt,field_validator
from . import ingestion
from .backup import guard
from .contracts import WorkflowError,digest,file_sha
from app.models import StrictModel
from app.media_intelligence_models import ImageGenerationInput,VideoGenerationInput
from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider
from app.media_generation_routes import workflow_routes,generation_envelope

BRIDGE_ROOT=Path(__file__).resolve().parents[1]/'comfyui-bridge'
if str(BRIDGE_ROOT) not in sys.path:sys.path.insert(0,str(BRIDGE_ROOT))
from npd_comfyui_bridge.models import WorkflowManifest

MANIFEST=Path(__file__).resolve().parents[2]/'workflows/comfyui/manifest.json'


class GenerationCredential(StrictModel):
    bridge_url:str=Field(min_length=1,max_length=1000)
    service_token:str=Field(min_length=32,max_length=8192,repr=False)
    enabled:StrictBool=False

    @field_validator('service_token')
    @classmethod
    def clean(cls,value):
        if value.strip()!=value or any(ord(c)<33 for c in value):raise ValueError('GENERATION_KEY_INVALID')
        return value

    @field_validator('bridge_url')
    @classmethod
    def origin(cls,value):
        parsed=urlsplit(value)
        if (parsed.scheme not in ('http','https') or parsed.hostname not in ('127.0.0.1','::1','localhost','comfyui-bridge')
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/')
            or parsed.port is None or not 1<=parsed.port<=65535):raise ValueError('GENERATION_APPROVED_BRIDGE_ORIGIN_REQUIRED')
        return value.rstrip('/')


class GenerationRegistry(StrictModel):
    version:StrictInt=Field(ge=1,le=1)
    native_workspace_id:str=Field(min_length=1,max_length=100)
    comfyui:GenerationCredential|None=None
    workflow_manifest:str|None=Field(default=None,min_length=1,max_length=1000)


def approved_catalog(path):
    path=guard(path,exists=True)
    if path.stat().st_size>2*1024*1024:raise WorkflowError('NATIVE_GENERATION_MANIFEST_INVALID',400)
    raw=path.read_bytes()
    try:manifest=WorkflowManifest.model_validate(json.loads(raw))
    except (ValueError,TypeError):raise WorkflowError('NATIVE_GENERATION_MANIFEST_INVALID',400) from None
    rows={row.workflow_id:row for row in manifest.workflows}
    if len(rows)!=len(manifest.workflows):raise WorkflowError('NATIVE_GENERATION_MANIFEST_INVALID',400)
    fingerprints={};reviewed={}
    for key,row in rows.items():
        graph=guard(path.parent/row.graph_file,exists=True)
        if graph.parent!=path.parent or graph.stat().st_size>2*1024*1024:raise WorkflowError('NATIVE_GENERATION_MANIFEST_INVALID',400)
        graph_raw=graph.read_bytes();sha=hashlib.sha256(graph_raw).hexdigest();fingerprints[key]=digest({'definition':row.model_dump(mode='json',exclude_none=True),'graph_sha256':sha})
        executable=False
        if row.execution:
            try:
                document=json.loads(graph_raw);nodes=document.get('prompt',document) if isinstance(document,dict) else None
                executable=(isinstance(nodes,dict) and 1<=len(nodes)<=500
                    and all(isinstance(node,dict) and node.get('class_type') in row.execution.allowed_node_classes
                        and isinstance(node.get('inputs'),dict) and not set(node)-{'class_type','inputs','_meta'} for node in nodes.values())
                    and all(key in nodes for key in row.execution.output_nodes)
                    and all(binding.node_id in nodes and binding.input_name in nodes[binding.node_id]['inputs'] for binding in row.execution.bindings))
            except (ValueError,TypeError):executable=False
        reviewed[key]=bool(executable and row.execution.approval_kind=='owner_approved' and row.execution.graph_sha256==sha)
    return {'manifest_sha256':hashlib.sha256(raw).hexdigest(),'manifest_version':manifest.manifest_version,'definitions':rows,
        'workflow_sha256':fingerprints,'reviewed':reviewed}


class GenerationFactory:
    def __init__(self,credential,*,owner_enabled=False,transport=None,manifest_path=MANIFEST):
        if type(credential) is not GenerationCredential or type(owner_enabled) is not bool:raise WorkflowError('NATIVE_GENERATION_CONFIGURATION_INVALID',400)
        import httpx
        self.credential,self.manifest_path=credential.model_copy(deep=True),guard(manifest_path,exists=True)
        self.catalog=approved_catalog(self.manifest_path)
        self.mode='fixture' if isinstance(transport,httpx.MockTransport) else 'official';self.transport=transport
        self.enabled=owner_enabled and credential.enabled
        self.sha256=digest({'bridge_url':credential.bridge_url,'token_sha256':hashlib.sha256(credential.service_token.encode()).hexdigest(),
            'enabled':self.enabled,'mode':self.mode,'manifest_sha256':self.catalog['manifest_sha256'],'schema_version':'native-generation-provider-config-v1'})

    def selection(self,modality,payload):
        import httpx
        try:current_credential=GenerationCredential.model_validate(self.credential.model_dump())
        except (ValueError,TypeError):raise WorkflowError('NATIVE_GENERATION_PROVIDER_CONFIGURATION_CHANGED',409) from None
        current_mode='fixture' if isinstance(self.transport,httpx.MockTransport) else 'official'
        current_sha=digest({'bridge_url':current_credential.bridge_url,'token_sha256':hashlib.sha256(current_credential.service_token.encode()).hexdigest(),
            'enabled':self.enabled,'mode':current_mode,'manifest_sha256':self.catalog['manifest_sha256'],'schema_version':'native-generation-provider-config-v1'})
        if current_sha!=self.sha256 or current_mode!=self.mode or self.enabled and not current_credential.enabled:
            raise WorkflowError('NATIVE_GENERATION_PROVIDER_CONFIGURATION_CHANGED',409)
        current=approved_catalog(self.manifest_path)
        if current['manifest_sha256']!=self.catalog['manifest_sha256'] or current['workflow_sha256']!=self.catalog['workflow_sha256']:
            raise WorkflowError('NATIVE_GENERATION_WORKFLOW_CONFIGURATION_CHANGED',409)
        primary='npd-text-to-image-v1' if modality=='image' else 'npd-video-generation-v1'
        routes=workflow_routes(modality,primary);key,operation,_=generation_envelope(modality,payload,routes)
        definition=self.catalog['definitions'].get(key)
        if definition is None:raise WorkflowError('NATIVE_GENERATION_WORKFLOW_NOT_APPROVED',400)
        configured=self.enabled and (self.mode=='fixture' or self.catalog['reviewed'][key])
        return {'provider':'comfyui-'+modality,'workflow_id':key,'workflow_version':definition.version,'operation':operation,
            'workflow_sha256':self.catalog['workflow_sha256'][key],'manifest_sha256':self.catalog['manifest_sha256'],
            'provider_configuration_sha256':self.sha256,'mode':self.mode,'status':'CONFIGURED' if configured else 'NOT_CONFIGURED',
            'executable_workflow_reviewed':self.catalog['reviewed'][key],'real_provider_tested':False}

    def create(self,modality,payload,*,on_job=None,cancel_requested=None):
        selected=self.selection(modality,payload)
        return ComfyUIBridgeGenerationProvider(bridge_url=self.credential.bridge_url,modality=modality,
            workflow_id='npd-text-to-image-v1' if modality=='image' else 'npd-video-generation-v1',
            enabled=selected['status']=='CONFIGURED',service_token=self.credential.service_token,transport=self.transport,
            on_job=on_job,cancel_requested=cancel_requested)


def load(path,root,workspace,*,owner_enabled=False):
    path=guard(path,exists=True)
    if Path(root).absolute() in path.parents or path.stat().st_size>262144:raise WorkflowError('NATIVE_GENERATION_REGISTRY_MUST_BE_OUTSIDE_STATE',400)
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError()
            result[key]=value
        return result
    try:
        with path.open('rb') as file:raw=json.loads(file.read(262145),object_pairs_hook=pairs)
        registry=GenerationRegistry.model_validate(raw)
    except (ValueError,TypeError):raise WorkflowError('NATIVE_GENERATION_REGISTRY_INVALID',400) from None
    if registry.native_workspace_id!=workspace:raise WorkflowError('NATIVE_GENERATION_REGISTRY_WORKSPACE_MISMATCH',400)
    manifest=MANIFEST
    if registry.workflow_manifest is not None:
        candidate=Path(registry.workflow_manifest)
        if not candidate.is_absolute():raise WorkflowError('NATIVE_GENERATION_WORKFLOW_MANIFEST_MUST_BE_PROTECTED_ABSOLUTE',400)
        manifest=guard(candidate,exists=True)
        if guard(root) in manifest.parents:raise WorkflowError('NATIVE_GENERATION_WORKFLOW_MANIFEST_MUST_BE_OUTSIDE_STATE',400)
    return GenerationFactory(registry.comfyui,owner_enabled=owner_enabled,manifest_path=manifest) if registry.comfyui is not None else None
