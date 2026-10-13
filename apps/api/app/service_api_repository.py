"""Durable service command receipts; uncertain outcomes are never redispatched."""
import hashlib,json,uuid
from datetime import datetime
from sqlalchemy import JSON,DateTime,ForeignKey,String,Integer,UniqueConstraint,select
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy.exc import IntegrityError
from .db import Base,utc_now

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

class ServiceOperationORM(Base):
    __tablename__='service_api_operations'
    __table_args__=(UniqueConstraint('workspace_id','service_id','key_sha256',name='uq_service_api_workspace_key'),)
    operation_id:Mapped[str]=mapped_column(String(64),primary_key=True)
    workspace_id:Mapped[str]=mapped_column(String(64),ForeignKey('workspaces.workspace_id',ondelete='RESTRICT'),nullable=False)
    service_id:Mapped[str]=mapped_column(String(160),nullable=False)
    action:Mapped[str]=mapped_column(String(64),nullable=False)
    project_id:Mapped[str|None]=mapped_column(String(64),nullable=True)
    actor_ref:Mapped[str]=mapped_column(String(160),nullable=False)
    key_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    request_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    status:Mapped[str]=mapped_column(String(32),nullable=False)
    response_status:Mapped[int|None]=mapped_column(Integer,nullable=True)
    response_json:Mapped[dict|list|None]=mapped_column(JSON,nullable=True)
    response_sha256:Mapped[str|None]=mapped_column(String(64),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)

class OperationConflict(ValueError):pass

class ServiceOperationRepository:
    def __init__(self,factory):self.factory=factory
    async def reserve(self,*,workspace,service,action,project,actor,key,payload):
        fingerprint=digest({'action':action,'project':project,'actor':actor,'payload':payload})
        hashed=hashlib.sha256(key.encode()).hexdigest()
        async with self.factory() as session:
            old=await session.scalar(select(ServiceOperationORM).where(ServiceOperationORM.workspace_id==workspace,
                ServiceOperationORM.service_id==service,ServiceOperationORM.key_sha256==hashed))
            if old:
                if old.request_sha256!=fingerprint:raise OperationConflict('SERVICE_IDEMPOTENCY_CONFLICT')
                return old,True
            now=utc_now();row=ServiceOperationORM(operation_id='sop_'+uuid.uuid4().hex,workspace_id=workspace,service_id=service,
                action=action,project_id=project,actor_ref=actor,key_sha256=hashed,request_sha256=fingerprint,
                status='running',created_at=now,updated_at=now)
            session.add(row)
            try:await session.commit()
            except IntegrityError:
                await session.rollback()
                old=await session.scalar(select(ServiceOperationORM).where(ServiceOperationORM.workspace_id==workspace,
                    ServiceOperationORM.service_id==service,ServiceOperationORM.key_sha256==hashed))
                if not old or old.request_sha256!=fingerprint:raise OperationConflict('SERVICE_IDEMPOTENCY_CONFLICT')
                return old,True
            return row,False
    async def complete(self,identity,status,value):
        async with self.factory() as session:
            row=await session.get(ServiceOperationORM,identity,with_for_update=True)
            if row.status!='running':
                if row.response_status==status and row.response_sha256==digest(value) and row.response_json==value:return
                raise OperationConflict('SERVICE_OPERATION_CHANGED')
            row.response_status=status;row.response_json=value;row.response_sha256=digest(value)
            row.status='succeeded' if status<400 else 'rejected';row.updated_at=utc_now();await session.commit()
    async def uncertain(self,identity):
        async with self.factory() as session:
            row=await session.get(ServiceOperationORM,identity,with_for_update=True)
            if row and row.status=='running':row.status='uncertain';row.updated_at=utc_now();await session.commit()
    async def get(self,identity):
        async with self.factory() as session:return await session.get(ServiceOperationORM,identity)

    async def canonical_outcome(self,session,identity,status,value,kind):
        """The canonical write, receipt and secret-free outbox commit together."""
        from .service_outcome_events import event,reference
        row=await session.get(ServiceOperationORM,identity,with_for_update=True)
        if row is None or row.status!='running':raise OperationConflict('SERVICE_OPERATION_CHANGED')
        if not isinstance(value,dict) or value.get('workspace_id',row.workspace_id)!=row.workspace_id:
            raise OperationConflict('SERVICE_OUTCOME_SCOPE_INVALID')
        if row.project_id and value.get('project_id')!=row.project_id:raise OperationConflict('SERVICE_OUTCOME_SCOPE_INVALID')
        row.response_status=status;row.response_json=value;row.response_sha256=digest(value);row.status='succeeded';row.updated_at=utc_now()
        session.add(event(row,row.response_sha256,kind,status,reference(value)))
