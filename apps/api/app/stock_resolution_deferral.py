"""Bounded, fenced read-only stock waits using existing job status/provenance."""
import copy
import math
import re
import uuid
from dataclasses import dataclass
from sqlalchemy import update
from .db import utc_now
from .media_intelligence_db import MediaResolutionJobORM

KEY = 'stock_wire_execution'
MAX_WIRE_CYCLES = 3
CLAIM_SECONDS = 300


def clock_value(stamp):
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError('STOCK_RESOLUTION_CLOCK_INVALID')
    return float(stamp)


def due(value, stamp):
    stamp = clock_value(stamp)
    if value['claim_id'] is not None:
        return value['lease_until'] <= stamp
    return value['next_at'] is not None and value['next_at'] <= stamp


@dataclass(frozen=True)
class StockJobClaim:
    claim_id: str
    cycle: int
    allowed: bool


def state(row):
    value = row.provenance_json.get(KEY)
    if value is None:
        return {'schema_version':'sql-stock-wire-job.v1','completed_wire_cycles':0,
            'next_at':None,'claim_id':None,'lease_until':None,'wait_history':[]}
    if not isinstance(value,dict) or value.get('schema_version')!='sql-stock-wire-job.v1' \
            or type(value.get('completed_wire_cycles')) is not int or not 0<=value['completed_wire_cycles']<=MAX_WIRE_CYCLES \
            or not isinstance(value.get('wait_history'),list) or len(value['wait_history'])>100:
        raise ValueError('STOCK_RESOLUTION_WAIT_INVALID')
    for key in ('next_at','lease_until'):
        if value.get(key) is not None and (type(value[key]) not in (int,float) or not math.isfinite(value[key]) or value[key]<0):
            raise ValueError('STOCK_RESOLUTION_WAIT_INVALID')
    if (value.get('claim_id') is None)!=(value.get('lease_until') is None):
        raise ValueError('STOCK_RESOLUTION_WAIT_INVALID')
    if value.get('claim_id') is not None and (not isinstance(value['claim_id'],str)
            or not re.fullmatch(r'[a-f0-9]{32}',value['claim_id'])):
        raise ValueError('STOCK_RESOLUTION_WAIT_INVALID')
    return copy.deepcopy(value)


async def locked(session, job_id):
    # The first write takes the same row lock on PostgreSQL and SQLite.
    result=await session.execute(update(MediaResolutionJobORM).where(
        MediaResolutionJobORM.resolution_job_id==job_id).values(updated_at=MediaResolutionJobORM.updated_at))
    if result.rowcount!=1:raise KeyError(job_id)
    return await session.get(MediaResolutionJobORM,job_id,with_for_update=True,populate_existing=True)


def persist(row, value):
    row.provenance_json={**row.provenance_json,KEY:value}
    row.updated_at=utc_now()


async def claim(repository,job_id,stamp):
    stamp = clock_value(stamp)
    async with repository.session_factory() as session:
        async with session.begin():
            row=await locked(session,job_id)
            if row.capability!='stock_media' or row.paid:
                raise ValueError('STOCK_RESOLUTION_READ_ONLY_REQUIRED')
            value=state(row)
            if row.status not in {'queued','running'} or value['next_at'] is not None and value['next_at']>stamp \
                    or value['claim_id'] is not None and value['lease_until']>stamp:
                return StockJobClaim('',value['completed_wire_cycles']+1,False)
            if value['claim_id'] is not None:
                value['wait_history'].append({'code':'STOCK_CLAIM_EXPIRED','observed_at':stamp,
                    'outcome_unknown':True,'paid_replay_authorized':False})
            identity=uuid.uuid4().hex
            value.update(claim_id=identity,lease_until=stamp+CLAIM_SECONDS,next_at=None)
            row.status='running';row.progress=max(row.progress,10);persist(row,value)
            return StockJobClaim(identity,value['completed_wire_cycles']+1,True)


async def defer(repository,job_id,claim_id,*,code,next_at,wire_attempts,stamp):
    stamp = clock_value(stamp)
    if type(next_at) not in (int,float) or not math.isfinite(next_at) or next_at<stamp \
            or type(wire_attempts) is not int or wire_attempts<0:
        raise ValueError('STOCK_RESOLUTION_WAIT_INVALID')
    async with repository.session_factory() as session:
        async with session.begin():
            row=await locked(session,job_id);value=state(row)
            if row.status not in {'queued','running'} or value['claim_id']!=claim_id:return False
            if wire_attempts:value['completed_wire_cycles']+=1
            value['wait_history'].append({'code':code,'observed_at':stamp,'next_at':next_at,
                'wire_attempts':wire_attempts,'paid_operations':0,'retry_cycle_consumed':bool(wire_attempts)})
            if len(value['wait_history'])>100:raise ValueError('STOCK_RESOLUTION_WAIT_LIMIT')
            if value['completed_wire_cycles']>=MAX_WIRE_CYCLES:
                row.status='failed';row.error_code='STOCK_WIRE_RETRY_EXHAUSTED'
                value.update(next_at=None,claim_id=None,lease_until=None)
            else:
                row.status='queued';row.error_code=code
                value.update(next_at=next_at,claim_id=None,lease_until=None)
            row.failure_reason='Stock read scheduling evidence; no payment or publishing authorization.'
            persist(row,value)
    return True


async def release_claim(repository,job_id,claim_id):
    async with repository.session_factory() as session:
        async with session.begin():
            row=await locked(session,job_id);value=state(row)
            if row.status not in {'cancelled', 'succeeded'} and value['claim_id']==claim_id:
                value.update(claim_id=None,lease_until=None);persist(row,value)
