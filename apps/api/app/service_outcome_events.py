"""Versioned immutable service outcome outbox; private response content excluded."""
from datetime import datetime,timezone
from sqlalchemy import JSON,DateTime,ForeignKey,String,Integer,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,utc_now
from .service_api_repository import digest

VERSION='agent-hub-service-outcomes.v1'
EXTENDED_VERSION='agent-hub-service-outcomes.v2'
class ServiceOutcomeEventORM(Base):
    __tablename__='service_outcome_events'
    __table_args__=(UniqueConstraint('operation_id',name='uq_service_outcome_operation'),)
    sequence:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    event_id:Mapped[str]=mapped_column(String(64),unique=True,nullable=False)
    operation_id:Mapped[str]=mapped_column(String(64),ForeignKey('service_api_operations.operation_id',ondelete='RESTRICT'),nullable=False)
    workspace_id:Mapped[str]=mapped_column(String(64),ForeignKey('workspaces.workspace_id',ondelete='RESTRICT'),nullable=False)
    service_id:Mapped[str]=mapped_column(String(160),nullable=False)
    envelope_json:Mapped[dict]=mapped_column(JSON,nullable=False)
    envelope_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)

REFERENCES=('project_id','timeline_id','current_version_id','current_version','render_id','publication_id',
    'final_render_id','output_asset_id','version','status','mode','mock','external_action')
KINDS={'project.create':'project.create','timeline.write':'timeline.mutate','render.create':'render.queue','publication.create':'publication.finalize'}
EXTENDED_KINDS={'upload.write':'upload.initialize','preview.create':'preview.queue','approval.submit':'approval.decide'}
EXTENDED_REFERENCES=REFERENCES+('upload_id','preview_id','approval_id','package_id','timeline_version_id','timeline_version')

def reference(value,kind=None):
    keys=EXTENDED_REFERENCES if kind in EXTENDED_KINDS.values() else REFERENCES
    return {key:value[key] for key in keys if key in value}

def source_kind(operation):
    kind=KINDS.get(operation.action)
    if kind:return kind
    value=operation.response_json
    if not isinstance(value,dict):return None
    if operation.action=='upload.write' and value.get('upload_id') and value.get('status')=='initialized':
        return 'upload.initialize'
    if operation.action=='preview.create' and value.get('preview_id') and value.get('timeline_version_id'):
        return 'preview.queue'
    if (operation.action=='approval.submit' and value.get('approval_id') and value.get('decided_at')
        and value.get('reviewer_ref')==operation.actor_ref and value.get('status') in ('approved','changes_requested','rejected')):
        return 'approval.decide'
    return None

def envelope(operation,response_sha,kind,status,reference,stamp):
    identity='sevt_'+digest({'operation':operation.operation_id})[:48]
    version=EXTENDED_VERSION if kind in EXTENDED_KINDS.values() else VERSION
    return {'contract_version':version,'event_id':identity,'event_type':'service.operation.completed',
        'occurred_at':stamp.isoformat(),'payload':{'operation_id':operation.operation_id,'workspace_id':operation.workspace_id,
        'service_id':operation.service_id,'action':operation.action,'project_id':operation.project_id,'source_kind':kind,
        'canonical_reference':reference,'response_sha256':response_sha,'response_status':status,
        'actor_ref':operation.actor_ref,'recommendation_only':True,'automatic_execution':False,
        'publishing_enabled':False,'real_provider_acceptance':False}}
def event(operation,response_sha,kind,status,reference):
    stamp=utc_now();value=envelope(operation,response_sha,kind,status,reference,stamp)
    return ServiceOutcomeEventORM(event_id=value['event_id'],operation_id=operation.operation_id,workspace_id=operation.workspace_id,
        service_id=operation.service_id,envelope_json=value,envelope_sha256=digest(value),created_at=stamp)

def validate(item,operation):
    if (operation.status!='succeeded' or not isinstance(operation.response_json,dict)
        or digest(operation.response_json)!=operation.response_sha256):return False
    stamp=item.created_at
    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
    kind=source_kind(operation)
    expected=envelope(operation,operation.response_sha256,kind,operation.response_status,reference(operation.response_json,kind),stamp)
    return (kind is not None and item.workspace_id==operation.workspace_id and item.service_id==operation.service_id
        and item.event_id==expected['event_id'] and item.envelope_json==expected and item.envelope_sha256==digest(expected))
