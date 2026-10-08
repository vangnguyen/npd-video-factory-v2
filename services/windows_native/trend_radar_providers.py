"""Approved public RSS/Atom references; default registry makes no outbound calls."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from pydantic import Field
from app.models import StrictModel
from app.trend_providers import TrendSourceProvider, create_trend_provider_registry, TrendProviderNotConfigured
from .contracts import WorkflowError,digest
from .research import retrieve
from .trend_radar_models import SignalEvidence

def public_reference(value):
    from urllib.parse import urlsplit
    try:
        url=urlsplit(value)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.port not in (None,443) or url.fragment or len(value)>2000 or any(ord(c)<33 for c in value) or re.search(r'(?:api_key|token|secret|password)=',url.query,re.I):raise ValueError()
    except (ValueError,TypeError):raise WorkflowError('TREND_PUBLIC_REFERENCE_REQUIRED',400) from None
    return value

class FeedConfig(StrictModel):
    provider_key:str=Field(pattern=r'^rss-[a-z0-9][a-z0-9-]{1,100}$')
    display_name:str=Field(min_length=1,max_length=120)
    feed_url:str=Field(max_length=2000)
    country:str|None=Field(default=None,pattern=r'^[A-Z]{2}$')
    language:str|None=Field(default=None,pattern=r'^[a-z]{2,3}$')
    owner_access_approved:bool=Field(strict=True)

class FeedRegistry(StrictModel):
    schema_version:str=Field(pattern=r'^native-trend-feed-registry-v1$')
    workspace_id:str
    feeds:list[FeedConfig]=Field(max_length=20)

class ApprovedFeedProvider(TrendSourceProvider):
    source_type='news_rss';status='healthy';authorized_access=True
    def __init__(self,config,*,fetch=None,clock=lambda:datetime.now(timezone.utc)):
        self.config=config;self.provider_key=config.provider_key;self.display_name=config.display_name
        self.config_ref='owner-approved-feed:'+digest(config.model_dump(mode='json'))
        public_reference(config.feed_url)
        if not config.owner_access_approved:raise WorkflowError('TREND_FEED_OWNER_ACCESS_REQUIRED',400)
        self.fetch=fetch or (lambda url:retrieve(url,accepted_types=('application/rss+xml','application/atom+xml','application/xml','text/xml')))
        self.clock=clock
    async def collect_signals(self,request):
        import asyncio
        receipt=await asyncio.to_thread(self.fetch,self.config.feed_url)
        text=receipt['html']
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise WorkflowError('TREND_FEED_XML_UNSAFE',400)
        try:root=ET.fromstring(text)
        except ET.ParseError:raise WorkflowError('TREND_FEED_XML_INVALID',400) from None
        now=self.clock();results=[]
        def local(tag):return tag.rsplit('}',1)[-1]
        for item in [v for v in root.iter() if local(v.tag) in ('item','entry')][:1000]:
            fields={local(v.tag):v for v in item};title=''.join(fields['title'].itertext()).strip() if 'title' in fields else ''
            links=[v for v in item if local(v.tag)=='link' and v.attrib.get('rel','alternate')=='alternate']
            reference=(links[0].attrib.get('href') or links[0].text or '').strip() if links else ''
            if not title or not reference:continue
            public_reference(reference)
            if request.query and request.query.casefold() not in title.casefold():continue
            if request.country and request.country!=self.config.country:continue
            if request.language and request.language!=self.config.language:continue
            if request.locale:continue # Unavailable locale cannot match an explicit filter.
            date=next((fields[k].text for k in ('pubDate','published','updated') if k in fields),None);published=None
            if date:
                try:published=datetime.fromisoformat(date.replace('Z','+00:00'))
                except ValueError:
                    try:published=parsedate_to_datetime(date)
                    except (ValueError,TypeError):pass
                if published and (published.tzinfo is None or published>now):published=None
            results.append(SignalEvidence(source='news_rss',source_reference=reference,observed_at=now,country=self.config.country,
                language=self.config.language,topic=title[:300],published_at=published,evidence_summary=title[:1200],evidence_confidence=1,
                freshness='feed_retrieved_publication_separate'))
            if len(results)>=request.limit:break
        self.last_receipt={k:v for k,v in receipt.items() if k!='html'}|{'retained_xml':text,'feed_sha256':digest(text),'confidence_meaning':'exact title/source receipt; not truth or trend strength'}
        return results
    async def search_topic(self,topic,request):return await self.collect_signals(request.model_copy(update={'query':topic}))
    async def get_topic_metrics(self,topic):return {'views':None,'velocity':None,'acceleration':None,'reason':'RSS does not expose social performance metrics'}
    async def get_content_reference(self,source_reference):return {'source_reference':public_reference(source_reference),'reference_only':True,'download_allowed':False}

def registry(path=None,*,workspace,owner_enabled=False):
    result=create_trend_provider_registry(Path(__file__).parents[2]/'apps/api/app/fixtures/trend-signals.json',fixture_enabled=False)
    if path is None:
        if owner_enabled:raise WorkflowError('TREND_FEED_REGISTRY_REQUIRED',400)
        return result
    from .backup import guard
    path=guard(path,exists=True)
    if not path.is_file() or path.stat().st_size>65536:raise WorkflowError('TREND_FEED_REGISTRY_INVALID',400)
    try:value=FeedRegistry.model_validate_json(path.read_bytes())
    except ValueError:raise WorkflowError('TREND_FEED_REGISTRY_INVALID',400) from None
    if value.workspace_id!=workspace or not owner_enabled:raise WorkflowError('TREND_FEED_WORKSPACE_AND_ENABLEMENT_REQUIRED',400)
    if len({v.provider_key for v in value.feeds})!=len(value.feeds):raise WorkflowError('TREND_FEED_REGISTRY_INVALID',400)
    for config in value.feeds:result._providers[config.provider_key]=ApprovedFeedProvider(config)
    return result
