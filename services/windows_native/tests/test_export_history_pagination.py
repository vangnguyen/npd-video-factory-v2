"""Stable keyset history with real owned SQLite rows, no fabricated final artifacts."""
import json,unittest
from unittest.mock import patch
from services.windows_native.tests import test_manual_delivery as fixture
from services.windows_native.contracts import WorkflowError,digest

class ExportHistoryPaginationTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ManualDeliveryTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.ManualDeliveryTests.tearDownClass.__func__)
    setUp=fixture.ManualDeliveryTests.setUp
    tearDown=fixture.ManualDeliveryTests.tearDown
    request=fixture.ManualDeliveryTests.request

    def seed(self,amount):
        request=self.request(cover=False).model_dump(mode='json',exclude_none=True)
        with self.store.transaction() as con:
            binding,_,_=self.service.binding(self.project['id'],self.request(cover=False),con)
            for number in range(1,amount+1):
                values=['nexp_'+f'{number:032x}','wsp_native_local',self.project['id'],'pagination-fixture-'+str(number),digest(request),json.dumps(request),json.dumps(binding),
                    '2026-10-18T00:00:00+00:00','abandoned',None,None,None]
                con.execute('INSERT INTO native_manual_exports VALUES('+','.join('?' for _ in values)+')',values)

    def test_more_than_hundred_rows_reachable_once_with_equal_timestamp_tie_breaker(self):
        self.seed(105);before=self.store.get(self.project['id']);cursor=None;ids=[];sizes=[]
        while True:
            page=self.service.page(self.project['id'],before=cursor,limit=40);sizes.append(len(page['items']));ids.extend(v['export_id'] for v in page['items'])
            if not page['has_more']:self.assertIsNone(page['next_cursor']);break
            cursor=page['next_cursor']
        self.assertEqual(sizes,[40,40,25]);self.assertEqual(len(set(ids)),105)
        self.assertEqual(ids,sorted(ids,reverse=True));self.assertEqual(self.store.get(self.project['id']),before)
        self.assertEqual(len(self.service.page(self.project['id'])['items']),100)

    def test_cursor_cannot_cross_project_and_invalid_types_never_read_files(self):
        self.seed(2);cursor=self.service.page(self.project['id'],limit=1)['next_cursor'];other=self.store.create('Other project','No external provider')
        with patch.object(self.service,'get',side_effect=AssertionError('Invalid query cannot read exports')):
            with self.assertRaisesRegex(WorkflowError,'CURSOR_INVALID'):self.service.page(other['id'],before=cursor)
            for options in [{'limit':True},{'limit':0},{'limit':101},{'limit':1.0},{'before':'../private'}]:
                with self.subTest(options=options),self.assertRaisesRegex(WorkflowError,'QUERY_INVALID'):self.service.page(self.project['id'],**options)

    def test_caption_history_beyond_hundred_is_scoped_and_does_not_rewind_latest_version(self):
        before=self.store.get(self.project['id']);variants=json.dumps({'master':{'caption':'Explicit caption history fixture'}})
        with self.store.transaction() as con:
            con.executemany('INSERT INTO native_delivery_copy VALUES(?,?,?,?,?,?,?)',[
                ('wsp_native_local',self.project['id'],i,'caption-page-fixture-'+str(i),digest([i,variants]),variants,'2026-10-18T00:00:00+00:00') for i in range(1,106)])
        cursor=None;versions=[]
        while True:
            page=self.service.copies(self.project['id'],before_version=cursor,limit=40);versions.extend(v['version'] for v in page['items'])
            if not page['has_more']:break
            cursor=page['next_cursor']
        self.assertEqual(versions,list(range(105,0,-1)));self.assertEqual(self.store.get(self.project['id']),before)
        other=self.store.create('Other caption project','No provider');self.assertEqual(self.service.copies(other['id'],before_version=80)['items'],[])
        from services.windows_native.manual_delivery import CaptionSave
        saved=self.service.save_copy(self.project['id'],CaptionSave(expected_version=105,request_key='caption-after-page-fixture',variants={'master':{'caption':'New after browsing history'}}))
        self.assertEqual(saved['version'],106)
        for options in [{'before_version':True},{'before_version':0},{'before_version':2.0},{'limit':101}]:
            with self.subTest(options=options),self.assertRaisesRegex(WorkflowError,'QUERY_INVALID'):self.service.copies(self.project['id'],**options)

if __name__=='__main__':unittest.main()
