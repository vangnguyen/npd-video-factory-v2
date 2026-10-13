"""Actual restart cache/worker boundaries; synthetic HTTP only, no network/key."""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

import httpx

from app.stock_media_providers import (PexelsStockMediaProvider, PixabayStockMediaProvider,
    StockProviderFailure, cache_io_path, digest as cache_digest, stock_request_scope)
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.pipeline import Config
from services.windows_native.stock import NativeStock
from services.windows_native.stock_models import StockSearch
from services.windows_native.stock_registry import StockCredential, StockFactory
from services.windows_native.store import Store


def photo(creator='EXPLICIT SYNTHETIC CREATOR'):
    return {'id':11,'width':640,'height':360,'url':'https://www.pexels.com/photo/explicit-fixture-11/',
        'photographer':creator,'alt':'EXPLICIT MOCK CACHE EVIDENCE',
        'src':{'original':'https://images.pexels.com/photos/11/explicit-fixture.png'}}


def pixabay_image():
    return {'id':31,'user':'EXPLICIT SYNTHETIC CREATOR','pageURL':'https://pixabay.com/photos/explicit-fixture-31/',
        'webformatURL':'https://cdn.pixabay.com/photo/explicit-fixture_640.png','webformatWidth':640,'webformatHeight':360,
        'imageWidth':640,'imageHeight':360,'tags':'explicit fixture'}


class DeniedWire(httpx.AsyncBaseTransport):
    """An official-shaped adapter must miss fixture cache, then hit this denial."""
    def __init__(self):self.attempts=0
    async def handle_async_request(self,request):
        self.attempts+=1
        raise AssertionError('EXPLICIT TEST DENIES ALL NETWORK/OFFICIAL DISPATCH')


class SharedStockCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # The owned lifecycle also uses extended Windows paths, so its normal
        # TemporaryDirectory cleanup can remove files longer than MAX_PATH.
        directory='\\\\?\\'+str(Path(tempfile.gettempdir()).resolve()) if os.name=='nt' else None
        self.temporary=tempfile.TemporaryDirectory(prefix='vf-stock-cache-tests-',dir=directory)
        self.root=Path(self.temporary.name)/'cache';self.scope='wsp_explicit_cache_fixture';self.calls=[];self.adapters=[]

    def tearDown(self):self.temporary.cleanup()

    async def asyncTearDown(self):
        for adapter in self.adapters:await adapter.aclose()

    def mocked(self,**overrides):
        def respond(request):
            self.calls.append(request)
            return httpx.Response(200,json={'photos':[photo()]})
        kwargs={'api_key':'explicit-fixture-noncredential','enabled':True,'cache_root':self.root,
            'cache_scope':self.scope,'transport':httpx.MockTransport(respond),**overrides}
        value=PexelsStockMediaProvider(**kwargs);self.adapters.append(value);return value

    async def search(self,adapter):return await adapter.search_images('EXPLICIT CACHE QUERY',orientation='portrait',limit=1)

    def cache_file(self):return next(self.root.rglob('*.json'))

    async def test_fixture_cache_cannot_be_relabelled_official_after_restart(self):
        first=self.mocked();original=(await self.search(first))[0];await first.aclose()
        denied=DeniedWire();changed=self.mocked(transport=denied)
        with self.assertRaises(AssertionError):await self.search(changed)
        self.assertEqual(denied.attempts,1);self.assertEqual(len(self.calls),1)
        self.assertTrue(original.provenance['fixture']);self.assertEqual(original.provenance['cache_execution_mode'],'fixture')
        self.assertNotEqual(first.cache_binding_sha256,changed.cache_binding_sha256)

    async def test_restarted_same_execution_binding_uses_cache_with_fixture_origin_and_zero_requests(self):
        first=self.mocked(cache_configuration_sha256='a'*64);original=(await self.search(first))[0];await first.aclose()
        restarted=self.mocked(cache_configuration_sha256='a'*64)
        counter=[]
        async def observe(request):counter.append(request)
        restarted._http().event_hooks['request'].append(observe)
        cached=(await self.search(restarted))[0]
        self.assertEqual(counter,[]);self.assertEqual(len(self.calls),1)
        self.assertEqual(cached.provenance['cache_binding_sha256'],original.provenance['cache_binding_sha256'])
        self.assertTrue(cached.provenance['fixture']);self.assertEqual(cached.creator,original.creator)
        envelope=json.loads(self.cache_file().read_text())
        self.assertEqual(envelope['schema'],2);self.assertEqual(envelope['execution_mode'],'fixture')
        self.assertEqual(envelope['configuration_sha256'],'a'*64)
        self.assertNotIn('explicit-fixture-noncredential',self.cache_file().read_text())

    async def test_credential_or_configuration_rotation_does_not_reuse_prior_response(self):
        first=self.mocked(cache_configuration_sha256='a'*64);await self.search(first);await first.aclose()
        rotated_key=self.mocked(api_key='explicit-rotated-noncredential',cache_configuration_sha256='a'*64)
        await self.search(rotated_key)
        rotated_config=self.mocked(cache_configuration_sha256='b'*64);await self.search(rotated_config)
        self.assertEqual(len(self.calls),3);self.assertEqual(len(list(self.root.rglob('*.json'))),3)
        self.assertEqual(len({value.cache_binding_sha256 for value in [first,rotated_key,rotated_config]}),3)

    async def test_unbound_legacy_cache_is_retained_and_not_consumed_by_new_execution(self):
        first=self.mocked();self.root.mkdir()
        params={'query':'EXPLICIT CACHE QUERY','per_page':1,'orientation':'portrait'}
        key=cache_digest({'provider':'pexels','path':'/v1/search','params':params,'schema':1})
        legacy=first._cache_path(self.scope,key);legacy.parent.mkdir(parents=True)
        body={'photos':[photo('EXPLICIT LEGACY UNBOUND CREATOR')]}
        legacy.write_text(json.dumps({'schema':1,'scope':cache_digest(self.scope),'key':key,
            'created_at':time.time(),'response':body,'sha256':cache_digest(body)}))
        prior=legacy.read_bytes();result=(await self.search(first))[0]
        self.assertEqual(result.creator,'EXPLICIT SYNTHETIC CREATOR');self.assertEqual(len(self.calls),1)
        self.assertEqual(legacy.read_bytes(),prior);self.assertEqual(len(list(self.root.rglob('*.json'))),2)

    async def test_relocated_foreign_mode_cache_fails_before_wire(self):
        first=self.mocked();await self.search(first);raw=self.cache_file().read_bytes()
        denied=DeniedWire();official=self.mocked(transport=denied)
        key=cache_digest({'provider':'pexels','path':'/v1/search',
            'params':{'query':'EXPLICIT CACHE QUERY','per_page':1,'orientation':'portrait'},'schema':2,
            'binding_sha256':official.cache_binding_sha256})
        foreign=official._cache_path(self.scope,key);foreign.write_bytes(raw)
        with self.assertRaisesRegex(StockProviderFailure,'STOCK_CACHE_INVALID'):await self.search(official)
        self.assertEqual(denied.attempts,0)

    async def test_mode_and_binding_metadata_corruption_or_nonfinite_age_is_rejected(self):
        first=self.mocked();await self.search(first);file=self.cache_file();original=json.loads(file.read_text())
        for mutate in [lambda value:value.update(execution_mode='official'),lambda value:value.update(binding_sha256='f'*64),
                lambda value:value.update(configuration_sha256='e'*64),lambda value:value.update(created_at=float('nan')),
                lambda value:value.update(schema=True)]:
            value=copy.deepcopy(original);mutate(value);file.write_text(json.dumps(value))
            with self.assertRaisesRegex(StockProviderFailure,'STOCK_CACHE_INVALID'):await self.search(first)
        self.assertEqual(len(self.calls),1)

    async def test_cache_workspace_and_physical_root_scope_remain_independent(self):
        first=self.mocked(cache_scope=None)
        with stock_request_scope('workspace-A'):await self.search(first)
        with stock_request_scope('workspace-B'):await self.search(first)
        moved=self.mocked(cache_root=Path(self.temporary.name)/'different-root',cache_scope='workspace-A')
        await self.search(moved)
        self.assertEqual(len(self.calls),3);self.assertNotEqual(first.cache_binding_sha256,moved.cache_binding_sha256)

    @unittest.skipUnless(os.name=='nt','Actual Windows long-path IO')
    async def test_long_owned_windows_cache_root_can_write_and_reuse_the_response(self):
        # Production callers pass an ordinary C:\ path. Only owned cleanup has
        # the extended prefix; the adapter must apply it after its path guards.
        ordinary=Path(self.temporary.name.removeprefix('\\\\?\\'))
        long_root=ordinary/('explicit-owned-cache-'+'x'*95)
        adapter=self.mocked(cache_root=long_root)
        self.assertFalse(str(adapter.cache_root).startswith('\\\\?\\'))
        first=(await self.search(adapter))[0];await adapter.aclose()
        restarted=self.mocked(cache_root=long_root)
        repeated=(await self.search(restarted))[0]
        self.assertEqual(len(self.calls),1)
        self.assertEqual(repeated.provenance['cache_binding_sha256'],first.provenance['cache_binding_sha256'])
        self.assertTrue(repeated.provenance['fixture'])
        files=list(cache_io_path(long_root).rglob('*.json'))
        self.assertEqual(len(files),1);self.assertGreater(len(str(files[0])),260)
        self.assertEqual(list(cache_io_path(long_root).rglob('*.tmp')),[])

    async def test_mutating_execution_origin_or_credential_refuses_even_a_cache_hit(self):
        first=self.mocked();await self.search(first);first.mock_transport_used=False
        with self.assertRaisesRegex(StockProviderFailure,'STOCK_CACHE_CONFIGURATION_CHANGED'):await self.search(first)
        first.mock_transport_used=True;first._api_key='explicit-replaced-noncredential'
        with self.assertRaisesRegex(StockProviderFailure,'STOCK_CACHE_CONFIGURATION_CHANGED'):await self.search(first)
        self.assertEqual(len(self.calls),1)

    async def test_any_orientation_omits_provider_filter_and_reuses_unknown_equivalent(self):
        pexels=self.mocked();await pexels.search_images('EXPLICIT ANY',orientation='any',limit=1)
        await pexels.search_images('EXPLICIT ANY',orientation='unknown',limit=1)
        self.assertEqual(len(self.calls),1);self.assertNotIn('orientation',self.calls[0].url.params)
        pix_calls=[]
        def respond(request):pix_calls.append(request);return httpx.Response(200,json={'hits':[pixabay_image()]})
        pixabay=PixabayStockMediaProvider(api_key='explicit-pixabay-noncredential',enabled=True,cache_root=self.root,
            cache_scope=self.scope,transport=httpx.MockTransport(respond));self.adapters.append(pixabay)
        result=await pixabay.search_images('EXPLICIT ANY',orientation='any',limit=1)
        self.assertEqual(len(result),1);self.assertNotIn('orientation',pix_calls[0].url.params)
        self.assertTrue(result[0].provenance['fixture'])

    def test_optional_configuration_hash_requires_exact_sha256(self):
        for value in ['', 'A'*64, True, 'fixture-config']:
            with self.assertRaisesRegex(ValueError,'STOCK_CACHE_CONFIGURATION_INVALID'):
                self.mocked(cache_configuration_sha256=value)


class NativeStockCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='sc-')
        self.root=Path(self.temporary.name)/'state';self.store=Store(self.root);self.config=Config(data_root=self.root)
        self.project=self.store.create('EXPLICIT STOCK CACHE TEST','EXPLICIT MOCK QUERY');self.calls=[];self.services=[]
        self.credential=StockCredential(api_key='explicit-factory-noncredential',enabled=True)

    def tearDown(self):
        for service in self.services:service.close()
        self.temporary.cleanup()

    def service(self,transport,credential=None):
        factory=StockFactory('pexels',credential or self.credential,owner_enabled=True,transport=transport)
        value=NativeStock(self.store,self.config,workspace_id='wsp_explicit_native_cache',factories={'pexels':factory})
        self.services.append(value);return value,factory

    def wire(self,request):self.calls.append(request);return httpx.Response(200,json={'photos':[photo()]})

    def search(self,service,key,*,official=False,orientation='portrait'):
        payload=StockSearch(revision=self.project['revision'],provider='pexels',query='EXPLICIT CACHE QUERY',media_type='image',
            orientation=orientation,limit=1,fixture_acknowledged=not official,external_acknowledged=official,request_key=key)
        job,_=service.create(self.project['id'],payload,actor='explicit-fixture-owner')
        service.process();return service.get(self.project['id'],job['stock_id'])

    def test_worker_mode_rotation_does_not_promote_fixture_cache_or_rewrite_history(self):
        first,factory=self.service(httpx.MockTransport(self.wire));fixture_job=self.search(first,'native-cache-fixture-seed')
        before=self.store.get(self.project['id']);first.close()
        denied=DeniedWire();changed,other=self.service(denied)
        official_job=self.search(changed,'native-cache-official-shaped',official=True)
        self.assertNotEqual(factory.sha256,other.sha256);self.assertEqual(denied.attempts,1)
        self.assertNotEqual(official_job['status'],'succeeded');self.assertIsNone(official_job['result'])
        self.assertEqual(first.get(self.project['id'],fixture_job['stock_id']),fixture_job)
        self.assertEqual(self.store.get(self.project['id']),before)
        self.assertTrue(fixture_job['result']['mock']);self.assertTrue(fixture_job['result']['candidates'][0]['provenance']['fixture'])

    def test_native_factory_config_hash_bound_reuse_and_orientation_journal_preserved(self):
        service,factory=self.service(httpx.MockTransport(self.wire));value=self.search(service,'native-cache-any-seed',orientation='any')
        self.assertEqual(value['status'],'succeeded');self.assertEqual(value['snapshot']['request']['orientation'],'any')
        candidate=value['result']['candidates'][0]
        self.assertEqual(candidate['provenance']['cache_configuration_sha256'],factory.sha256)
        self.assertNotIn('orientation',self.calls[0].url.params);service.close()
        restarted,_=self.service(httpx.MockTransport(self.wire));repeat=self.search(restarted,'native-cache-any-reuse',orientation='any')
        self.assertEqual(repeat['status'],'succeeded');self.assertEqual(repeat['result']['fixture_wire_attempts'],0)
        self.assertEqual(len(self.calls),1);self.assertEqual(repeat['snapshot']['provider_configuration_sha256'],factory.sha256)
        expected=digest({'provider':'pexels','key_sha256':hashlib.sha256(self.credential.api_key.encode()).hexdigest(),
            'enabled':True,'mode':'fixture','schema_version':'native-stock-provider-config-v1'})
        self.assertEqual(factory.sha256,expected)

    def test_factory_mutation_cannot_dispatch_under_its_previous_mode_or_credential_hash(self):
        service,factory=self.service(httpx.MockTransport(self.wire))
        fixture_job=self.search(service,'native-cache-frozen-mode')
        factory.transport=DeniedWire()
        with self.assertRaisesRegex(WorkflowError,'NATIVE_STOCK_PROVIDER_CONFIGURATION_CHANGED'):
            factory.create(self.root,service.cache_scope)
        self.assertEqual(factory.transport.attempts,0)
        factory.transport=httpx.MockTransport(self.wire)
        factory.credential=StockCredential(api_key='explicit-replaced-noncredential',enabled=True)
        with self.assertRaisesRegex(WorkflowError,'NATIVE_STOCK_PROVIDER_CONFIGURATION_CHANGED'):
            factory.create(self.root,service.cache_scope)
        self.assertEqual(service.get(self.project['id'],fixture_job['stock_id']),fixture_job)


if __name__=='__main__':unittest.main()
