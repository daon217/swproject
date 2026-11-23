import copy
import json
from pathlib import Path
import tempfile
import unittest
from ..taxonomy import Taxonomy
from ..build import audit_source,plan,build,iter_records,source_fingerprint
from ..records import validate_record
from ..verify import verify
from ..mapping import link_record,validate_mapping
from ...generate import generate,encoded
from ...test_api import validate_record as legacy_validator


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'legacy';self.output=self.root/'classified'
        generate(self.source,64,batch_size=16);self.tax=Taxonomy()
    def tearDown(self):self.tmp.cleanup()
    def built_record(self):
        build(self.source,self.output,minimum_total=0,batch_size=20)
        return json.loads((self.output/'part-00000.jsonl').read_text(encoding='utf-8').splitlines()[0])
    def test_provisional_tree_has_11_majors_22_middles_44_leaves_and_no_official_IDs(self):
        self.assertEqual(len(self.tax.majors),11);self.assertEqual(len(self.tax.profiles),44)
        self.assertEqual(sum(n['level']==2 for n in self.tax.nodes.values()),22)
        self.assertEqual(set(self.tax.legacy),{'laptop','phone','food','book','clothing','furniture','cosmetics','toys'})
        self.assertFalse(self.tax.data['team_category_ids_authoritative'])
    def test_audit_finds_generic_names_missing_brands_specs_and_balances_total_not_per_category_million(self):
        audit=audit_source(self.source,self.tax)
        self.assertEqual(audit['missing_fields'],{'brand':64,'specifications':64,'category_path':64,'generic_name':64})
        allocation=plan(audit,self.tax,0)
        self.assertEqual((allocation['final_count'],allocation['additional_count']),(176,112))
        actual_like=dict(audit,count=1000000,majors={m:250000 if m==self.tax.majors[0] else 125000 for m in self.tax.majors[:7]},leaves={})
        self.assertEqual(plan(actual_like,self.tax)['final_count'],2750000)
    def test_full_enrichment_resume_preserves_original_IDs_bytes_and_validates_all_leaves(self):
        before=source_fingerprint(self.source)
        first=build(self.source,self.output,minimum_total=0,batch_size=20,max_parts=2)
        self.assertEqual(first['committed'],40);self.assertFalse(first['complete'])
        final=build(self.source,self.output,minimum_total=0,batch_size=20)
        self.assertTrue(final['complete'])
        report=verify(self.source,self.output,sample_path=self.root/'samples.jsonl')
        self.assertEqual((report['records'],report['legacy_enriched'],report['additional_records']),(176,64,112))
        self.assertEqual(report['duplicate_IDs'],0);self.assertEqual(report['required_fields_missing'],0)
        self.assertEqual(len(report['leaf_counts']),44)
        self.assertTrue(all(n==16 for n in report['major_counts'].values()))
        self.assertEqual(source_fingerprint(self.source),before)
        self.assertEqual(report['legacy_changes_in_separate_view']['names_enriched'],64)
        self.assertEqual(report['team_official_category_IDs_assigned'],0)
    def test_semantic_mutations_rejected_for_brand_specs_name_price_and_hierarchy(self):
        original=self.built_record()
        for field,value in [('brand','SYNTHETIC-다른브랜드'),('name','SYNTHETIC 잘못된 종류'),
                            ('specifications',{'capacity_ml':500}),('price','999999999'),
                            ('category_path',['식품','가공식품','파스타']),('category_ids',['SYN-CAT-01']),
                            ('team_category_id','invented-official-id')]:
            with self.subTest(field=field):
                bad=copy.deepcopy(original);bad[field]=value
                with self.assertRaises(ValueError):validate_record(bad,self.tax,0)
    def test_consume_only_new_categories_and_native_prices_are_not_fake_safety_claims(self):
        self.built_record();report=verify(self.source,self.output)
        self.assertGreater(report['conditions']['used'],0);self.assertGreater(report['conditions']['new'],0)
        self.assertGreater(report['regions']['overseas'],0);self.assertGreater(report['regions']['domestic'],0)
        for file in self.output.glob('part-*.jsonl'):
            for line in file.read_text(encoding='utf-8').splitlines():
                row=json.loads(line)
                if row['category_path'][0] in ('식품','뷰티'):self.assertEqual(row['condition'],'new')
                self.assertIsNone(row['ingredients']);self.assertIsNone(row['safe_to_consume'])
    def test_v1_test_importer_rejects_new_schema_instead_of_silently_dropping_category(self):
        with self.assertRaises(ValueError):legacy_validator(self.built_record())
    def test_source_overlap_and_reports_inside_input_are_rejected(self):
        with self.assertRaises(ValueError):build(self.source,self.source/'view',minimum_total=0)
        self.built_record();before=source_fingerprint(self.source)
        with self.assertRaises(ValueError):verify(self.source,self.output,sample_path=self.source/'part-00000.jsonl')
        self.assertEqual(source_fingerprint(self.source),before)
    def test_corrupt_output_or_changed_taxonomy_not_automatically_reset(self):
        self.built_record();part=self.output/'part-00000.jsonl';part.write_text('corrupt')
        with self.assertRaises(ValueError):build(self.source,self.output,minimum_total=0,batch_size=20)
        self.assertEqual(part.read_text(),'corrupt')
    def test_completed_orphan_part_adopted_without_duplicate_IDs(self):
        build(self.source,self.output,minimum_total=0,batch_size=20,max_parts=1)
        state=json.loads((self.output/'manifest.json').read_text(encoding='utf-8'))
        stream=iter_records(self.source,self.tax,state['audit'],state['allocation'],state['artifact'])
        for _ in range(20):next(stream)
        with (self.output/'part-00001.jsonl').open('wb') as file:
            for _ in range(20):file.write(encoded(next(stream)))
        build(self.source,self.output,minimum_total=0,batch_size=20)
        self.assertEqual(verify(self.source,self.output)['records'],176)
    def test_source_file_corruption_fails_closed_without_repairing_original(self):
        part=self.source/'part-00000.jsonl';part.write_text('source changed')
        with self.assertRaises(ValueError):build(self.source,self.output,minimum_total=0)
        self.assertEqual(part.read_text(),'source changed')
    def test_future_official_mapping_is_validated_link_table_and_does_not_mutate_record(self):
        row=self.built_record();original=copy.deepcopy(row)
        official={'revision':'SYNTHETIC-TEST-REVISION','source_reference':'SYNTHETIC fixture only', 'nodes':[
            {'id':'TEAM-1','level':1,'name':'대','parent_id':None},
            {'id':'TEAM-2','level':2,'name':'중','parent_id':'TEAM-1'},
            {'id':'TEAM-3','level':3,'name':'소','parent_id':'TEAM-2'}]}
        mapping={row['category_ids'][2]:'TEAM-3'}
        linked=link_record(row,self.tax,official,mapping)
        self.assertEqual(linked['team_category_id'],'TEAM-3');self.assertEqual(row,original)
        self.assertIsNone(link_record(row,self.tax,official,{})['team_category_id'])
        with self.assertRaises(ValueError):validate_mapping(self.tax,official,{row['category_ids'][2]:'TEAM-2'})
        bad=copy.deepcopy(official);bad['nodes'][2]['parent_id']='absent'
        with self.assertRaises(ValueError):validate_mapping(self.tax,bad,mapping)
    def test_invalid_tree_and_non_synthetic_source_rejected(self):
        raw=copy.deepcopy(self.tax.data);raw['nodes'][1]['parent_id']='missing'
        file=self.root/'invalid.json';file.write_text(json.dumps(raw),encoding='utf-8')
        with self.assertRaises(ValueError):Taxonomy(file)


if __name__=='__main__':unittest.main()
