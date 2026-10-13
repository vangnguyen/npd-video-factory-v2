"""Owned short Windows roots; actual files/processes, synthetic stock responses."""
import asyncio,concurrent.futures,copy,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from app.stock_cache_policy import StockCachePolicy,StockResponseCache,StockCacheError,digest,io_path,linked,ordinary
from app.stock_media_providers import PexelsStockMediaProvider,StockProviderFailure
from services.windows_native.tests.test_stock_cache_binding import photo

SCOPE=digest('EXPLICIT OWNED CACHE WORKSPACE')
BINDING=digest('EXPLICIT NONCREDENTIAL EXECUTION BINDING')
CONFIG=digest('EXPLICIT NONCREDENTIAL PROVIDER CONFIGURATION')

class StockCacheLifecycleTests(unittest.TestCase):
    def setUp(self):
        base=Path('C:/vfct') if os.name=='nt' else Path(tempfile.gettempdir())
        base.mkdir(exist_ok=True)
        if linked(base):raise RuntimeError('Owned fixture base cannot be linked')
        base_io='\\\\?\\'+str(base.absolute()) if os.name=='nt' else str(base)
        self.temporary=tempfile.TemporaryDirectory(prefix='sc-',dir=base_io)
        self.root=ordinary(self.temporary.name);self.clock=[1000.]
        self.cache=self.make()
    def tearDown(self):self.temporary.cleanup()
    def make(self,*,root=None,scope=SCOPE,binding=BINDING,configuration=CONFIG,policy=None):
        return StockResponseCache(root or self.root/'cache',scope_sha256=scope,provider='pexels',binding_sha256=binding,
            execution_mode='fixture',configuration_sha256=configuration,policy=policy,clock=lambda:self.clock[0])
    def envelope(self,key,*,body=None,created=None,cache=None):
        cache=cache or self.cache;body=body or {'explicit_fixture':True,'value':'synthetic response'}
        return {'schema':2,'scope':cache.scope,'provider':cache.provider,'binding_sha256':cache.binding,'execution_mode':cache.mode,
            'configuration_sha256':cache.configuration,'key':key,'response':body,'sha256':digest(body),
            'created_at':self.clock[0] if created is None else created}
    def store(self,key,**changes):return self.cache.write(key,self.envelope(key,**changes))
    def files(self):return list(io_path(self.cache.directory).iterdir())

    def test_deterministic_oldest_key_eviction_counts_all_namespace_files_and_preserves_other_domains(self):
        self.cache=self.make(policy=StockCachePolicy(max_entries=4)) # two bounded controls plus two response files
        protected={}
        for domain in ('assets','originals','accepted-videos','generated-paid','raw-ASR','models','evidence','logs','database'):
            path=self.root/domain/'private-preserved.bin';path.parent.mkdir();path.write_bytes(('EXPLICIT PRESERVED '+domain).encode());protected[path]=path.read_bytes()
        keys=sorted(digest(str(i)) for i in range(3))
        self.store(keys[0]);self.store(keys[1]);report=self.store(keys[2])
        self.assertTrue(report['stored']);self.assertTrue(report['within_limits']);self.assertEqual(report['removed_entries'],1)
        self.assertEqual(report['namespace_entries'],4);self.assertEqual(report['verified_entries'],2)
        self.assertIsNone(self.cache.read(keys[0]));self.assertIsNotNone(self.cache.read(keys[1]))
        self.assertEqual(report['namespace_bytes'],sum(path.stat().st_size for path in self.files()))
        self.assertEqual({path:path.read_bytes() for path in protected},protected)
        self.assertFalse(report['quota_state_touched']);self.assertEqual(report['media_files_touched'],0)
        self.assertNotIn(str(self.root),json.dumps(report));self.assertNotIn('synthetic response',json.dumps(report))

    def test_byte_cap_age_cleanup_and_atomic_replacement_are_exact(self):
        self.cache=self.make(policy=StockCachePolicy(max_entries=10,max_bytes=4096,max_age_seconds=10,max_file_bytes=4096))
        first,second=digest('first'),digest('second')
        self.store(first,body={'padding':'x'*2100});self.clock[0]+=1
        report=self.store(second,body={'padding':'y'*2100})
        self.assertTrue(report['stored']);self.assertLessEqual(report['namespace_bytes'],4096);self.assertIsNone(self.cache.read(first))
        original=self.cache.read(second);names={path.name:path.read_bytes() for path in self.files()}
        with patch('app.stock_cache_policy._Access.replace',side_effect=OSError('EXPLICIT ATOMIC REPLACE INTERRUPTION')):
            with self.assertRaises(OSError):self.store(second,body={'padding':'z'*2100})
        self.assertEqual(self.cache.read(second),original);self.assertEqual({path.name:path.read_bytes() for path in self.files()},names)
        self.clock[0]+=10;self.assertIsNone(self.cache.read(second))
        report=self.cache.maintain();self.assertEqual(report['removed_entries'],1);self.assertEqual(report['namespace_entries'],2)
        self.assertFalse(any(path.name.endswith('.tmp') for path in self.files()))

    def test_schema1_foreign_binding_corrupt_oversize_are_protected_and_prevent_new_growth(self):
        self.cache=self.make(policy=StockCachePolicy(max_entries=3,max_file_bytes=1024))
        key=digest('known');self.store(key);directory=io_path(self.cache.directory)
        records={}
        old=self.envelope(digest('old'));old['schema']=1
        foreign=self.envelope(digest('foreign'));foreign['binding_sha256']='f'*64
        for identity,raw in [(digest('old'),json.dumps(old).encode()),(digest('foreign'),json.dumps(foreign).encode()),
                (digest('corrupt'),b'EXPLICIT MALFORMED RESPONSE JSON'),(digest('oversize'),b'x'*2048)]:
            path=directory/(identity+'.json');path.write_bytes(raw);records[path]=raw
        self.clock[0]+=86400;report=self.store(digest('new'))
        self.assertFalse(report['stored']);self.assertEqual(report['code'],'STOCK_CACHE_GROWTH_BLOCKED')
        self.assertEqual(report['protected_entries'],4);self.assertFalse(report['within_limits'])
        self.assertEqual(report['namespace_bytes'],sum(path.stat().st_size for path in self.files()))
        self.assertEqual({path:path.read_bytes() for path in records},records)
        with patch.object(self.cache,'_envelope',side_effect=AssertionError('Oversize file must not reach JSON parsing')):
            with self.assertRaisesRegex(StockCacheError,'STOCK_CACHE_INVALID'):self.cache.read(digest('oversize'))

    def test_cross_scope_root_and_configuration_do_not_leak_or_evict_foreign_cache(self):
        key=digest('same-request');self.store(key);old=(io_path(self.cache.directory)/(key+'.json')).read_bytes()
        foreign=self.make(binding='b'*64,configuration='c'*64,policy=StockCachePolicy(max_entries=3))
        with self.assertRaisesRegex(StockCacheError,'STOCK_CACHE_INVALID'):foreign.read(key)
        report=foreign.write(digest('new-config'),self.envelope(digest('new-config'),cache=foreign))
        self.assertFalse(report['stored']);self.assertEqual(report['protected_entries'],1)
        self.assertEqual((io_path(self.cache.directory)/(key+'.json')).read_bytes(),old)
        for other in (self.make(scope=digest('other-workspace')),self.make(root=self.root/'other-cache')):
            self.assertIsNone(other.read(key));self.assertEqual(other.maintain()['namespace_entries'],0)
        self.assertIsNotNone(self.cache.read(key))

    def test_scan_limits_and_unknown_nested_directory_fail_before_unverified_deletion(self):
        self.cache=self.make(policy=StockCachePolicy(max_entries=3,max_scan_entries=3))
        key=digest('known');self.store(key);original=(io_path(self.cache.directory)/(key+'.json')).read_bytes()
        extra=io_path(self.cache.directory)/'foreign.bin';extra.write_bytes(b'EXPLICIT FOREIGN')
        with self.assertRaisesRegex(StockCacheError,'STOCK_CACHE_SCAN_LIMIT'):self.store(digest('new'))
        self.assertEqual((io_path(self.cache.directory)/(key+'.json')).read_bytes(),original);self.assertEqual(extra.read_bytes(),b'EXPLICIT FOREIGN')
        cache=self.make(root=self.root/'nested-cache');identity=digest('nested-key');cache.write(identity,self.envelope(identity,cache=cache))
        nested=io_path(cache.directory)/'not-cache-domain';nested.mkdir();(nested/'original.mp4').write_bytes(b'EXPLICIT UNTOUCHED BYTES')
        report=cache.write(digest('blocked-growth'),self.envelope(digest('blocked-growth'),cache=cache))
        self.assertFalse(report['stored']);self.assertTrue(report['unknown_nested_bytes'])
        self.assertEqual((nested/'original.mp4').read_bytes(),b'EXPLICIT UNTOUCHED BYTES')

    @unittest.skipUnless(os.name=='nt','Actual Windows junction, pins and long paths')
    def test_actual_windows_junction_hardlink_and_ancestor_swap_guards(self):
        key=digest('known');self.store(key);target=io_path(self.cache.directory)/(key+'.json')
        outside=self.root/'owned-outside';outside.mkdir();outside_asset=outside/'preserved.json';outside_asset.write_bytes(b'EXPLICIT OUTSIDE CACHE')
        hard=io_path(self.cache.directory)/(digest('hard')+'.json');os.link(outside_asset,hard)
        with self.assertRaisesRegex(StockCacheError,'STOCK_CACHE_PATH_INVALID'):self.cache.read(digest('hard'))
        report=self.cache.maintain();self.assertEqual(report['protected_entries'],1);self.assertEqual(outside_asset.read_bytes(),b'EXPLICIT OUTSIDE CACHE')
        with self.cache.locked():
            with self.assertRaises(OSError):io_path(self.cache.directory).rename(io_path(self.cache.directory.with_name('swap')))
        junction_root=self.root/'junction-cache';junction_root.mkdir();link=junction_root/SCOPE
        completed=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
        self.assertEqual(completed.returncode,0,'Owned junction fixture was not created')
        try:
            with self.assertRaisesRegex(StockCacheError,'STOCK_CACHE_PATH_INVALID'):self.make(root=junction_root)
            self.assertEqual(outside_asset.read_bytes(),b'EXPLICIT OUTSIDE CACHE')
        finally:
            self.assertEqual(link.absolute().parent,self.root/'junction-cache')
            os.rmdir(link) # Remove this owned junction entry only; never recurse into its target.
        long=self.make(root=self.root/('long-owned-cache-'+'x'*100));long.write(key,self.envelope(key,cache=long))
        self.assertGreater(len(str(long.directory/(key+'.json'))),260);self.assertIsNotNone(long.read(key))

    def process(self,script,*arguments):
        return subprocess.Popen([sys.executable,'-X','utf8','-c',script,*map(str,arguments)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def test_two_process_writers_and_pinned_reader_remain_atomic_and_bounded(self):
        root=self.root/'process-cache';cache=self.make(root=root,policy=StockCachePolicy(max_entries=7));key=digest('shared-key')
        cache.write(key,self.envelope(key,body={'version':1},cache=cache))
        script="""import sys,time,json
from app.stock_cache_policy import StockResponseCache,StockCachePolicy,digest
c=StockResponseCache(sys.argv[1],scope_sha256=sys.argv[2],provider='pexels',binding_sha256=sys.argv[3],execution_mode='fixture',configuration_sha256=sys.argv[4],policy=StockCachePolicy(max_entries=7))
for n in range(12):
 k=digest([sys.argv[5],n]);b={'explicit_fixture':True,'writer':sys.argv[5],'n':n}
 c.write(k,{'schema':2,'scope':c.scope,'provider':c.provider,'binding_sha256':c.binding,'execution_mode':c.mode,'configuration_sha256':c.configuration,'key':k,'response':b,'sha256':digest(b),'created_at':time.time()})
print('OK')
"""
        writer1=self.process(script,root,SCOPE,BINDING,CONFIG,'process-one');writer2=self.process(script,root,SCOPE,BINDING,CONFIG,'process-two')
        for process in (writer1,writer2):
            out,error=process.communicate(timeout=20);self.assertEqual(process.returncode,0,error);self.assertEqual(out.strip(),'OK')
        report=cache.maintain();self.assertTrue(report['within_limits']);self.assertLessEqual(report['namespace_entries'],7)
        for path in io_path(cache.directory).glob('*.json'):
            body=json.loads(path.read_bytes());self.assertEqual(body['sha256'],digest(body['response']))
        key=digest('pinned-key');cache.write(key,self.envelope(key,body={'version':1},created=time.time(),cache=cache))
        replace_script=script.split('for n in range(12):')[0]+"\nk=sys.argv[5];b={'version':2};c.write(k,{'schema':2,'scope':c.scope,'provider':c.provider,'binding_sha256':c.binding,'execution_mode':c.mode,'configuration_sha256':c.configuration,'key':k,'response':b,'sha256':digest(b),'created_at':time.time()});print('OK')\n"
        with cache.locked() as access:
            fd=access.open(key+'.json',os.O_RDONLY)
            try:
                process=self.process(replace_script,root,SCOPE,BINDING,CONFIG,key)
                time.sleep(.25);self.assertIsNone(process.poll());raw=os.read(fd,4096);self.assertEqual(json.loads(raw)['response'],{'version':1})
            finally:os.close(fd)
        out,error=process.communicate(timeout=20);self.assertEqual(process.returncode,0,error);self.assertEqual(out.strip(),'OK')
        cache.clock=time.time;self.assertEqual(cache.read(key),{'version':2});self.assertFalse(any(p.name.endswith('.tmp') for p in io_path(cache.directory).iterdir()))

    def test_policy_is_strict_bounded_and_constructor_is_inert(self):
        root=self.root/'never-created';self.make(root=root);self.assertFalse(root.exists())
        for changes in ({'max_entries':True},{'max_age_seconds':86401},{'max_entries':2},{'max_bytes':0},
                {'max_scan_entries':3},{'max_file_bytes':2**31},{'lock_timeout_seconds':float('nan')}):
            with self.assertRaises(ValueError):StockCachePolicy(**changes)


class StockCacheAdapterLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        base=Path('C:/vfct') if os.name=='nt' else Path(tempfile.gettempdir());base.mkdir(exist_ok=True)
        base_io='\\\\?\\'+str(base.absolute()) if os.name=='nt' else str(base)
        self.temporary=tempfile.TemporaryDirectory(prefix='sa-',dir=base_io);self.root=ordinary(self.temporary.name);self.calls=[];self.adapters=[]
    async def asyncTearDown(self):
        for adapter in self.adapters:await adapter.aclose()
        self.temporary.cleanup()
    def adapter(self,**changes):
        def wire(request):self.calls.append(request);return httpx.Response(200,json={'photos':[photo()]})
        value=PexelsStockMediaProvider(api_key='explicit-cache-lifecycle-noncredential',enabled=True,cache_root=self.root/'cache',cache_scope='owned-cache-workspace',
            transport=httpx.MockTransport(wire),**changes);self.adapters.append(value);return value
    async def test_cache_binding_unchanged_policy_restart_hit_uses_zero_wire_and_does_not_consume_quota(self):
        adapter=self.adapter();first=await adapter.search_images('EXPLICIT RESPONSE QUERY',orientation='unknown',limit=1);await adapter.aclose()
        class NoQuotaAdmission:
            async def admit(self,*args):raise AssertionError('Cache hit must not admit a quota lease or wire call')
        restarted=self.adapter(cache_policy=StockCachePolicy(max_entries=10),wire_guard=NoQuotaAdmission(),require_wire_guard=True)
        self.assertEqual(adapter.cache_binding_sha256,restarted.cache_binding_sha256)
        result=await restarted.search_images('EXPLICIT RESPONSE QUERY',orientation='unknown',limit=1)
        self.assertEqual(len(self.calls),1);self.assertEqual(result[0].creator,first[0].creator);self.assertTrue(result[0].provenance['fixture'])
        report=await restarted.cache_maintenance();self.assertTrue(report['within_limits']);self.assertEqual(report['provider_calls'],0)
        self.assertFalse(report['quota_state_touched']);self.assertNotIn('EXPLICIT RESPONSE QUERY',json.dumps(report))
        restarted.cache_policy=StockCachePolicy(max_entries=11)
        with self.assertRaisesRegex(StockProviderFailure,'STOCK_CACHE_POLICY_CHANGED'):await restarted.search_images('EXPLICIT RESPONSE QUERY',orientation='unknown',limit=1)

    async def test_cache_io_wait_runs_off_event_loop_and_no_cache_lock_covers_quota_wire(self):
        adapter=self.adapter();await adapter.search_images('EXPLICIT FIRST',orientation='unknown',limit=1)
        cache=adapter._response_cache('owned-cache-workspace');ticks=[]
        def hold():
            with cache.locked():time.sleep(.2)
        holder=asyncio.create_task(asyncio.to_thread(hold));await asyncio.sleep(.04)
        async def tick():
            for _ in range(8):ticks.append(True);await asyncio.sleep(.01)
        await asyncio.gather(adapter.search_images('EXPLICIT FIRST',orientation='unknown',limit=1),tick(),holder)
        self.assertEqual(len(ticks),8);self.assertEqual(len(self.calls),1)
        class CheckingQuota:
            async def admit(self,provider,workspace,request_class):
                # A separate instance must be able to lock during wire admission.
                await asyncio.to_thread(cache.maintain);return 'explicit-quota-fixture'
            async def release(self,*args,**kwargs):pass
        adapter.wire_guard=CheckingQuota();adapter.require_wire_guard=True
        await adapter.search_images('EXPLICIT SECOND',orientation='unknown',limit=1);self.assertEqual(len(self.calls),2)

    async def test_valid_200_scan_race_retains_provider_body_without_growth_and_warm_hit_stays_zero_wire(self):
        adapter=self.adapter(cache_policy=StockCachePolicy(max_entries=3,max_scan_entries=3))
        await adapter.search_images('EXPLICIT WARM',orientation='unknown',limit=1)
        cache=adapter._response_cache('owned-cache-workspace')
        def wire(request):
            self.calls.append(request)
            (io_path(cache.directory)/'protected-unverified.txt').write_bytes(b'EXPLICIT NONCACHE FILE ADDED DURING WIRE')
            return httpx.Response(200,json={'photos':[photo()]})
        adapter._transport=httpx.MockTransport(wire);await adapter.aclose()
        result=await adapter.search_images('EXPLICIT SCAN RACE',orientation='unknown',limit=1)
        self.assertEqual(len(result),1);self.assertTrue(result[0].provenance['fixture']);self.assertFalse(result[0].production_eligible)
        self.assertEqual(len(self.calls),2)
        self.assertEqual(len(list(io_path(cache.directory).glob('*.json'))),1)
        diagnostic=adapter.cache_write_diagnostics();self.assertEqual(diagnostic['skipped_writes'],1);self.assertEqual(diagnostic['last_code'],'STOCK_CACHE_SCAN_LIMIT')
        self.assertFalse(diagnostic['cache_limits_bypassed']);self.assertFalse(diagnostic['provider_health_inferred'])
        class ForbiddenAdmission:
            async def admit(self,*args):raise AssertionError('Warm cache cannot request a new quota lease')
        adapter.wire_guard=ForbiddenAdmission();adapter.require_wire_guard=True
        await adapter.search_images('EXPLICIT WARM',orientation='unknown',limit=1)
        self.assertEqual(len(self.calls),2);self.assertEqual(adapter.cache_write_diagnostics(),diagnostic)

    async def test_post_200_disk_permission_or_busy_write_retains_response_and_opaque_diagnostic_only(self):
        adapter=self.adapter();await adapter.search_images('EXPLICIT WARM',orientation='unknown',limit=1)
        failures=[OSError('EXPLICIT PRIVATE PATH AND NONCREDENTIAL SENTINEL'),StockCacheError('STOCK_CACHE_BUSY'),StockCacheError('STOCK_CACHE_IO_FAILED')]
        for index,error in enumerate(failures):
            with patch.object(StockResponseCache,'write',side_effect=error):
                result=await adapter.search_images('EXPLICIT WRITE FAILURE '+str(index),orientation='unknown',limit=1)
            self.assertEqual(len(result),1);self.assertTrue(result[0].provenance['fixture'])
        diagnostic=adapter.cache_write_diagnostics();self.assertEqual(diagnostic['skipped_writes'],3)
        self.assertNotIn('PRIVATE PATH',json.dumps(diagnostic));self.assertNotIn('WRITE FAILURE',json.dumps(diagnostic));self.assertNotIn(str(self.root),json.dumps(diagnostic))
        calls=len(self.calls);await adapter.search_images('EXPLICIT WARM',orientation='unknown',limit=1);self.assertEqual(len(self.calls),calls)
        with patch.object(StockResponseCache,'write',side_effect=StockCacheError('STOCK_CACHE_PATH_INVALID')):
            with self.assertRaisesRegex(StockProviderFailure,'STOCK_CACHE_PATH_INVALID'):
                await adapter.search_images('EXPLICIT INVALID PATH',orientation='unknown',limit=1)
        self.assertEqual(adapter.cache_write_diagnostics(),diagnostic)

if __name__=='__main__':unittest.main()
