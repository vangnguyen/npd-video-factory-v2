"""Protected official API configuration; loading a key does not enable calls."""
import hashlib,json
from pathlib import Path
from pydantic import Field,StrictBool,field_validator
from .backup import guard
from .contracts import WorkflowError,digest
from . import ingestion
from app.models import StrictModel
from app.stock_media_providers import PexelsStockMediaProvider,PixabayStockMediaProvider


class StockCredential(StrictModel):
    api_key:str=Field(min_length=1,max_length=8192)
    enabled:StrictBool=False

    @field_validator('api_key')
    @classmethod
    def clean(cls,value):
        if value.strip()!=value or any(ord(character)<33 for character in value):raise ValueError('STOCK_KEY_INVALID')
        return value


class StockRegistry(StrictModel):
    version:int
    native_workspace_id:str=Field(min_length=1,max_length=100)
    pexels:StockCredential|None=None
    pixabay:StockCredential|None=None


class StockFactory:
    def __init__(self,key,credential,*,owner_enabled=False,transport=None):
        self.key=key;self.credential=credential;self.enabled=bool(owner_enabled and credential.enabled)
        import httpx
        self.mode='fixture' if isinstance(transport,httpx.MockTransport) else 'official';self.transport=transport
        self.sha256=digest({'provider':key,'key_sha256':hashlib.sha256(credential.api_key.encode()).hexdigest(),
            'enabled':self.enabled,'mode':self.mode,'schema_version':'native-stock-provider-config-v1'})

    def create(self,root,scope):
        adapter={'pexels':PexelsStockMediaProvider,'pixabay':PixabayStockMediaProvider}[self.key]
        return adapter(api_key=self.credential.api_key,enabled=self.enabled,cache_root=root/'stock-cache',cache_scope=scope,
            timeout_seconds=10,max_download_bytes=250*1024*1024,transport=self.transport)


def load(path,root,workspace,*,owner_enabled=False):
    path=guard(Path(path),exists=True)
    if Path(root).absolute() in path.parents or path.stat().st_size>262144:raise WorkflowError('NATIVE_STOCK_REGISTRY_MUST_BE_OUTSIDE_STATE',400)
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('Duplicate registry key')
            value[key]=item
        return value
    try:
        with path.open('rb') as file:raw=json.loads(file.read(262145),object_pairs_hook=pairs)
        if not isinstance(raw,dict) or type(raw.get('version')) is not int or raw['version']!=1:raise ValueError()
        registry=StockRegistry.model_validate(raw)
    except (ValueError,TypeError):raise WorkflowError('NATIVE_STOCK_REGISTRY_INVALID',400) from None
    if registry.native_workspace_id!=workspace:raise WorkflowError('NATIVE_STOCK_REGISTRY_WORKSPACE_MISMATCH',400)
    return {key:StockFactory(key,value,owner_enabled=owner_enabled) for key in ['pexels','pixabay'] if (value:=getattr(registry,key)) is not None}
