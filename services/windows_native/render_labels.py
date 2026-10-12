"""Optional frozen render text; legacy documents never consult mutable config."""
import re
from pathlib import Path
from typing import Literal
from pydantic import Field,model_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest

CATALOG=Path(__file__).parent/'profiles/render-labels.json'
LEGACY_ILLUSTRATION='Phối cảnh minh họa'
REF=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$'
BRAND=r'^[a-z][a-z0-9-]{2,49}$'

class Labels(StrictModel):
    profile_ref:str=Field(pattern=REF)
    illustration_label:str=Field(min_length=1,max_length=40)
    @model_validator(mode='after')
    def literal_line(self):
        if self.illustration_label!=self.illustration_label.strip() or any(ord(c)<32 or ord(c)==127 for c in self.illustration_label):
            raise ValueError('Render label must be one literal nonblank line')
        return self

class Override(Labels):
    brand_id:str=Field(pattern=BRAND)

class Catalog(StrictModel):
    schema_version:Literal['native-render-label-catalog-v1']
    defaults:Labels
    brand_overrides:list[Override]=Field(max_length=50)
    @model_validator(mode='after')
    def unique(self):
        if len({v.brand_id for v in self.brand_overrides})!=len(self.brand_overrides):raise ValueError('Duplicate brand label')
        return self

class Frozen(StrictModel):
    schema_version:Literal['native-frozen-render-labels-v1']
    brand_id:str=Field(pattern=BRAND)
    labels:Labels
    labels_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

def freeze(brand_id):
    if not isinstance(brand_id,str) or not re.fullmatch(BRAND,brand_id):raise WorkflowError('RENDER_LABEL_BRAND_INVALID',400)
    try:
        catalog=Catalog.model_validate_json(CATALOG.read_bytes())
        override=next((v for v in catalog.brand_overrides if v.brand_id==brand_id),None)
        labels=Labels.model_validate(override.model_dump(exclude={'brand_id'}) if override else catalog.defaults).model_dump(mode='json')
    except (ValueError,OSError):raise WorkflowError('RENDER_LABEL_CONFIGURATION_INVALID',503) from None
    value={'schema_version':'native-frozen-render-labels-v1','brand_id':brand_id,'labels':labels,'labels_sha256':digest(labels)}
    return {**value,'snapshot_sha256':digest(value)}

def bind(document):
    selection=document.get('brand_template')
    if selection:document['render_labels']=freeze(selection['brand']['id'])

def resolve(document):
    if 'render_labels' not in document:return LEGACY_ILLUSTRATION
    try:
        raw=document['render_labels'];value=Frozen.model_validate(raw).model_dump(mode='json')
        if value!=raw or value['brand_id']!=document['brand_template']['brand']['id'] or value['labels_sha256']!=digest(value['labels']):raise ValueError()
        if value['snapshot_sha256']!=digest({k:v for k,v in value.items() if k!='snapshot_sha256'}):raise ValueError()
        return value['labels']['illustration_label']
    except (KeyError,TypeError,ValueError):raise WorkflowError('RENDER_LABEL_SNAPSHOT_CHANGED') from None
