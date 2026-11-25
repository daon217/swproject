import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import tracemalloc
import unittest
from unittest.mock import Mock
from services.collector.synthetic_catalog.generate import generate,rows,record,encoded
from services.collector.synthetic_catalog.load_test import batches,deliver,reconcile,target
from services.collector.synthetic_catalog.test_api import TestStore,validate_record,create_server


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_streaming_resume_has_no_duplicates_and_all_synthetic_markers(self):
        root=self.root/'dataset'
        self.assertEqual(generate(root,1000,batch_size=137,max_parts=2)['committed'],274)
        self.assertTrue(generate(root,1000,batch_size=137)['complete'])
        data=list(rows(root));self.assertEqual(len(data),1000)
        self.assertEqual(len({r['record_id'] for r in data}),1000)
        self.assertTrue(all(r['synthetic'] is True and r['source']=='synthetic_catalog' for r in data))
        self.assertEqual({r['region'] for r in data},{'domestic','overseas'})
        self.assertEqual({r['condition'] for r in data},{'new','used'})
        self.assertTrue(all(r['condition']=='new' for r in data if r['category'] in ('food','cosmetics')))
        self.assertTrue(all(r['safe_to_consume'] is None for r in data))
        for r in data:validate_record(r)
        before=(root/'manifest.json').read_bytes();generate(root,1000,batch_size=137)
        self.assertEqual((root/'manifest.json').read_bytes(),before)
    def test_deterministic_records_and_currency_native_ranges(self):
        a=record(0,42,'0123456789abcdef');b=record(0,42,'0123456789abcdef')
        self.assertEqual(a,b);self.assertEqual(a['category'],'laptop');self.assertEqual(a['currency'],'KRW')
        self.assertTrue(300000<=int(a['price'])<=3000000)
        self.assertEqual(record(1,42,'0123456789abcdef')['currency'],'USD')
    def test_orphan_completed_part_adopted_only_after_deterministic_hash_check(self):
        root=self.root/'orphan';generate(root,11,batch_size=5,max_parts=1)
        manifest=json.loads((root/'manifest.json').read_text())
        with (root/'part-00001.jsonl').open('wb') as f:
            for i in range(5,10):f.write(encoded(record(i,42,manifest['dataset'])))
        result=generate(root,11,batch_size=5)
        self.assertEqual(result['committed'],11);self.assertEqual(len(list(rows(root))),11)
    def test_partial_resume_and_corruption_fail_without_reset(self):
        root=self.root/'partial';generate(root,10,batch_size=5,max_parts=1)
        (root/'part-00001.jsonl.partial').write_text('interrupted')
        self.assertTrue(generate(root,10,batch_size=5)['complete'])
        part=root/'part-00000.jsonl';part.write_text('corruption')
        with self.assertRaises(ValueError):generate(root,10,batch_size=5)
        self.assertEqual(part.read_text(),'corruption')
    def test_different_settings_and_unowned_directory_not_overwritten(self):
        root=self.root/'owned';generate(root,10)
        with self.assertRaises(ValueError):generate(root,11)
        with self.assertRaises(ValueError):generate(root,10,seed=43)
        other=self.root/'other';other.mkdir();(other/'keep.txt').write_text('keep')
        with self.assertRaises(ValueError):generate(other,10)
        self.assertEqual((other/'keep.txt').read_text(),'keep')
    def test_memory_bound_not_entire_dataset(self):
        tracemalloc.start()
        try:
            generate(self.root/'memory',10000,batch_size=1000)
            _,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        self.assertLess(peak,12000000)
    def test_only_explicit_loopback_test_target_allowed(self):
        for url in ('https://team.example.test','http://localhost:18779','http://127.0.0.1.evil.test:18779','http://127.0.0.1:18779/path','http://user:pass@127.0.0.1:18779','postgresql://127.0.0.1:5432'):
            with self.subTest(url=url),self.assertRaises(ValueError):target(url,'synthetic_test','isolated_test')
        with self.assertRaises(ValueError):target('http://127.0.0.1:18779','public','isolated_test')
        with self.assertRaises(ValueError):target('http://127.0.0.1:18779','synthetic_test','production')
    def test_test_store_duplicate_receipt_and_immutable_batch(self):
        root=self.root/'dataset';generate(root,20)
        store=TestStore(self.root/'synthetic_test.sqlite3','synthetic_test');payload=next(batches(root,'synthetic_test'))
        receipt=store.ingest(payload);self.assertEqual(receipt['state'],'applied')
        self.assertEqual(store.ingest(payload)['state'],'duplicate')
        self.assertEqual(store.receipt(payload['batch_key'])['count'],20)
        changed=copy.deepcopy(payload);changed['records']=changed['records'][:1]
        with self.assertRaises(ValueError):store.ingest(changed)
        with store.connection() as db:self.assertEqual(db.execute('select count(*) from synthetic_products').fetchone()[0],20)
    def test_loader_ack_resume_and_uncertain_request_receipt_reconciliation(self):
        root=self.root/'dataset';generate(root,20)
        store=TestStore(self.root/'synthetic_test.sqlite3','synthetic_test')
        def lost(payload):store.ingest(payload);raise TimeoutError('secret must not appear')
        state=self.root/'loader';call=Mock(side_effect=lost)
        args=(root,state,'http://127.0.0.1:18779','synthetic_test','isolated_test')
        self.assertEqual(deliver(*args,api=call)['status'],'held')
        self.assertEqual(deliver(*args,api=call)['status'],'held');self.assertEqual(call.call_count,1)
        key=next(batches(root,'synthetic_test'))['batch_key'];reconcile(state,store.receipt(key))
        self.assertEqual(deliver(*args,api=call)['acked_records'],20);self.assertEqual(call.call_count,1)
        self.assertNotIn('secret must not appear',(state/'test_import_ledger.json').read_text())
    def test_http_errors_do_not_auto_resend_and_bad_receipt_cannot_ack(self):
        root=self.root/'dataset';generate(root,10)
        for code in (401,429,503):
            state=self.root/str(code);api=Mock(return_value=(code,{}))
            args=(root,state,'http://127.0.0.1:18779','synthetic_test','isolated_test')
            self.assertEqual(deliver(*args,api=api)['status'],'held')
            deliver(*args,api=api);self.assertEqual(api.call_count,1)
            key=next(batches(root,'synthetic_test'))['batch_key']
            with self.assertRaises(ValueError):reconcile(state,{'batch_key':key,'sha256':'bad','state':'applied','count':10})
    def test_real_products_and_nonisolated_SQLite_paths_rejected(self):
        for path,namespace in [(self.root/'catalog.sqlite3','synthetic_test'),(self.root/'synthetic_test.sqlite3','production')]:
            with self.assertRaises(ValueError):TestStore(path,namespace)
        r=record(0,42,'0123456789abcdef');r['synthetic']=False
        with self.assertRaises(ValueError):validate_record(r)
    def test_server_is_loopback_only_and_no_default_token(self):
        with self.assertRaises(ValueError):create_server(self.root/'synthetic_test.sqlite3','synthetic_test','short',0)
        # Socket serving is tested separately under a loopback-only guard.
    def test_non_synthetic_DB_and_incomplete_dataset_cannot_be_loaded(self):
        file=self.root/'synthetic_misnamed.sqlite3'
        db=sqlite3.connect(file)
        try:db.execute('create table real_products (id text)');db.commit()
        finally:db.close()
        with self.assertRaises(ValueError):TestStore(file,'synthetic_test')
        dataset=self.root/'incomplete';generate(dataset,1000,batch_size=100,max_parts=1)
        api=Mock()
        with self.assertRaises(ValueError):deliver(dataset,self.root/'loader','http://127.0.0.1:18779','synthetic_test','isolated_test',api=api)
        api.assert_not_called()
    def test_extra_fields_or_region_currency_mismatch_are_not_accepted(self):
        row=record(0,42,'0123456789abcdef');row['description']='not part of synthetic schema'
        with self.assertRaises(ValueError):validate_record(row)
        row=record(0,42,'0123456789abcdef');row['currency']='USD'
        with self.assertRaises(ValueError):validate_record(row)
