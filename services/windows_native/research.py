"""Actual public-source retrieval, with exact quotations and explicit uncertainty."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import gzip
import io
import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit
from .contracts import WorkflowError, canonical, digest, normalize
from .intelligence_models import ResearchFinding, ResearchSource, stamp


class ResearchProvider(ABC):
    key: str

    @abstractmethod
    def research(self, query, context):
        """Return sources, structured findings and provider metadata, or explicit failure."""


def public_target(reference):
    if not isinstance(reference,str) or len(reference)>2000 or any(ord(c)<33 for c in reference):
        raise WorkflowError("RESEARCH_PUBLIC_HTTPS_URL_REQUIRED",400)
    try:
        url=urlsplit(reference)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.port not in (None,443) or url.fragment:
            raise ValueError()
        if re.search(r'(?:api_key|token|secret|password)=',url.query,re.I):
            raise ValueError()
        addresses=socket.getaddrinfo(url.hostname,443,type=socket.SOCK_STREAM)
        ips={r[4][0] for r in addresses}
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError()
        return url, sorted(ips)[0]
    except (ValueError,OSError):
        raise WorkflowError("RESEARCH_PUBLIC_HTTPS_URL_REQUIRED",400) from None


def retrieve(reference, max_bytes=2*1024*1024, *, accepted_types=('text/html','text/plain')):
    requested=reference
    for _ in range(4):
        url,address=public_target(reference)
        connection=http.client.HTTPSConnection(url.hostname,443,timeout=15,context=ssl.create_default_context())
        # Pin the validated public address; TLS still verifies the original hostname.
        connection._create_connection=lambda target,timeout,source_address=None: socket.create_connection((address,443),timeout,source_address)
        try:
            connection.request('GET',(url.path or '/')+('?' + url.query if url.query else ''),headers={'User-Agent':'VideoFactory-Research/1.0','Accept':'text/html,text/plain','Accept-Encoding':'identity'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location: raise WorkflowError('RESEARCH_REDIRECT_INVALID')
                reference=urljoin(reference,location)
                continue
            if response.status!=200: raise WorkflowError('RESEARCH_HTTP_ERROR',http_status=response.status)
            content_type=response.getheader('Content-Type','')
            if content_type.split(';')[0].lower() not in accepted_types:
                raise WorkflowError('RESEARCH_TEXT_SOURCE_REQUIRED')
            raw=response.read(max_bytes+1)
            if not raw or len(raw)>max_bytes: raise WorkflowError('RESEARCH_SOURCE_SIZE_LIMIT')
            encoding=response.getheader('Content-Encoding','identity').lower()
            decoded=raw
            if encoding=='gzip':
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed: decoded=compressed.read(max_bytes+1)
                except (OSError,EOFError): raise WorkflowError('RESEARCH_SOURCE_COMPRESSION_INVALID') from None
                if len(decoded)>max_bytes: raise WorkflowError('RESEARCH_SOURCE_SIZE_LIMIT')
            elif encoding not in ('identity',''): raise WorkflowError('RESEARCH_SOURCE_COMPRESSION_UNSUPPORTED')
            charset=re.search(r'charset=([\w-]+)',content_type,re.I)
            try: text=decoded.decode(charset[1] if charset else 'utf-8',errors='strict')
            except (LookupError,UnicodeError): raise WorkflowError('RESEARCH_SOURCE_ENCODING_INVALID') from None
            return {'requested_url':requested,'final_url':reference,'status':200,'content_type':content_type,'content_encoding':encoding,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw),'decoded_bytes':len(decoded),'html':text}
        except (OSError,http.client.HTTPException):
            raise WorkflowError('RESEARCH_RETRIEVAL_FAILED') from None
        finally:
            connection.close()
    raise WorkflowError('RESEARCH_REDIRECT_LIMIT')


class ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored=0; self.title_depth=0; self.title=[]; self.parts=[]; self.publication=None

    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg'): self.ignored+=1
        if tag=='title': self.title_depth+=1
        if not self.ignored and tag in ('p','h1','h2','h3','li','div','br','article','section'): self.parts.append('\n')
        if tag=='meta':
            data=dict(attrs)
            if data.get('property',data.get('name','')).lower() in ('article:published_time','datepublished','date'):
                self.publication=data.get('content')

    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg') and self.ignored: self.ignored-=1
        if tag=='title' and self.title_depth: self.title_depth-=1
        if not self.ignored and tag in ('p','h1','h2','h3','li','div','article','section'): self.parts.append('\n')

    def handle_data(self,data):
        if not self.ignored:
            self.parts.append(data)
            if self.title_depth: self.title.append(data)


def source_from_receipt(receipt):
    parser=ReadableHTML(); parser.feed(receipt['html'])
    paragraphs=[normalize(p) for p in ''.join(parser.parts).split('\n') if normalize(p)]
    text='\n'.join(paragraphs)[:100000]
    publication=None
    if parser.publication:
        try:
            publication=datetime.fromisoformat(parser.publication.replace('Z','+00:00'))
            if publication.tzinfo is None: publication=None
            if publication and publication>stamp(): publication=None
        except ValueError: pass
    if len(text)<50: raise WorkflowError('RESEARCH_SOURCE_NO_READABLE_TEXT')
    return ResearchSource(source_type='web',reference=receipt['final_url'],title=normalize(''.join(parser.title))[:500] or receipt['final_url'],
        timestamp=publication,retrieved_at=stamp(),publication_date_known=publication is not None,text=text,content_sha256=digest(text),
        provenance={'origin':'actual_https_retrieval','provider':'public-web-excerpts-v1'},
        raw_provenance={k:v for k,v in receipt.items() if k!='html'})


class PublicWebResearchProvider(ResearchProvider):
    key='public-web-excerpts-v1'

    def __init__(self, receipts, fetch=retrieve):
        self.receipts=receipts; self.fetch=fetch

    def research(self,query,context):
        urls=context.get('source_urls',[])
        if not isinstance(urls,list) or not 1<=len(urls)<=5 or any(not isinstance(u,str) for u in urls):
            raise WorkflowError('RESEARCH_SOURCE_URLS_REQUIRED_1_TO_5',400)
        if len(set(urls))!=len(urls): raise WorkflowError('RESEARCH_DUPLICATE_SOURCE_URL',400)
        sources=[]; findings=[]
        tokens={t.casefold() for t in re.findall(r'\w+',query) if len(t)>2}
        for url in urls:
            receipt=self.fetch(url)
            receipt['retained_html_sha256']=digest(receipt['html'])
            receipt['storage_format']='utf8-exact-bytes-v2'
            source=source_from_receipt(receipt)
            directory=self.receipts/source.id; directory.mkdir(parents=True,exist_ok=False)
            (directory/'retrieval.json').write_bytes(canonical({k:v for k,v in receipt.items() if k!='html'}))
            (directory/'source.html').write_bytes(receipt['html'].encode('utf-8'))
            (directory/'source-text.txt').write_bytes(source.text.encode('utf-8'))
            sources.append(source)
            ranked=[]
            for paragraph in source.text.split('\n'):
                if 60<=len(paragraph)<=3000:
                    matches=len(tokens & {t.casefold() for t in re.findall(r'\w+',paragraph)})
                    if matches: ranked.append((matches,paragraph))
            for _,quote in sorted(ranked,key=lambda pair:-pair[0])[:3]:
                findings.append(ResearchFinding(run_id=context['run_id'],kind='SOURCED_FACT',claim=quote,
                    source_references=[{'source_id':source.id,'quote':quote}],relevance=min(1,_/max(1,len(tokens))),confidence=.7,
                    timestamp_relevance='Source publication: '+source.timestamp.isoformat() if source.timestamp else 'Publication date unknown; retrieval is not publication',
                    grounding='SOURCE_REPORTED',provenance={'origin':'exact_source_excerpt','truth_verified':False,'confidence_meaning':'quote provenance, not probability of truth'}))
        if not findings: raise WorkflowError('RESEARCH_NO_RELEVANT_SOURCED_FINDINGS')
        findings.append(ResearchFinding(run_id=context['run_id'],kind='UNCERTAIN',claim='Nguồn trích dẫn chưa chứng minh giá, tiến độ, pháp lý hoặc hiệu quả đầu tư tại thời điểm sản xuất. Cần kiểm tra riêng trước khi dùng.',
            source_references=[],relevance=1,confidence=0,timestamp_relevance='Current claims unresolved',grounding='UNRESOLVED',provenance={'origin':'research_limit','provider':self.key}))
        validate_findings(sources,findings)
        return sources,findings,{'provider':self.key,'model':None,'actual_retrievals':len(urls),'automated_truth_verification':False,'discovery':'explicit public source URLs; no search metrics','paid_calls':0}


def validate_findings(sources,findings):
    by_id={s.id:s for s in sources}
    for source in sources:
        if digest(source.text)!=source.content_sha256: raise WorkflowError('RESEARCH_SOURCE_HASH_MISMATCH')
    for finding in findings:
        for citation in finding.source_references:
            source=by_id.get(citation.source_id)
            if source is None or citation.quote not in source.text:
                raise WorkflowError('RESEARCH_QUOTE_NOT_IN_RETRIEVED_SOURCE')
