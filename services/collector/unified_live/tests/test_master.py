import copy
from datetime import datetime,timezone,timedelta
import io,json,os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from contextlib import redirect_stdout
from services.collector.unified_live.discovery import DiscoveryStore,MetadataHTTP,catalogue_links,probe,select_adapter,marketplace_id,main as discovery_main
from services.collector.unified_live.fleet import FleetSupervisor,registration
from services.collector.unified_live.analysis import analyze,opensearch_template
from services.collector.unified_live.parser import normalize,native_money
from services.collector.unified_live.mock import fixture_config,product,FakeHTTP
from services.collector.unified_live.engine import URLWorker
from services.collector.unified_live.local_receipt import ReceiptStore
from services.collector.unified_live.public_sources import PublicReader,feed_probe,mcp_probe
from services.collector.unified_live.feeds import FeedWorker,validate as validate_feed
from services.collector.unified_live.food import evidence
from services.collector.unified_live.food_lookup import gtin,record_evidence,attach,FoodHTTP
from services.collector.unified_live.transport import Wait
from services.collector.collector_ops.mock import SimulatedDelivery
from services.collector.domeggook_live.domeggook_delivery import atomic,load

class MasterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.now=datetime.now(timezone.utc);self.cfg=fixture_config()
    def tearDown(self):self.tmp.cleanup()
    def store(self):return DiscoveryStore(self.root/'discovery',clock=lambda:self.now)
    def candidate(self,store):
        ident=store.add({'name':'SYNTHETIC shop','domain':'store.example.test'},'SYNTHETIC_DIRECTORY')
        site=store.state['sites'][ident]
        site.update(access_policy='metadata_accessible',product_quality_verified=True,capabilities={'jsonld_product_count':1},search_url_template='https://store.example.test/search?q={query}')
        return ident
    def approval(self):
        return dict(self.cfg['rights'],allowed_hosts=['store.example.test'],backend_owner_approved=True,price_semantics_confirmed=True,
            backend_enabled=True,currencies=['USD'],queries=['SYNTHETIC'],provider_min_interval_seconds=60)
    def test_seed_directory_19_disabled_and_duplicate_domains(self):
        data=json.loads((Path(__file__).parents[1]/'seed_sites.json').read_text(encoding='utf-8'));store=self.store();store.ingest(data['sites'],data['reference'])
        self.assertEqual(store.report()['candidates'],19);self.assertEqual(store.report()['enabled'],0)
        ident=store.add({'domain':'ebay.com','enabled':True,'collection_permission':'approved'},'SYNTHETIC')
        self.assertEqual(store.report()['candidates'],19);self.assertFalse(store.state['sites'][ident]['enabled'])
    def test_remote_directory_cannot_set_quality_or_entitlements(self):
        store=self.store();ident=store.add({'domain':'store.example.test','enabled':True,'product_quality_verified':True,'adapter':'arbitrary_shell'},'SYNTHETIC')
        self.assertFalse(store.state['sites'][ident]['product_quality_verified']);self.assertFalse(store.evaluate(ident,self.approval())['enabled'])
    def test_activation_requires_quality_storage_backend_and_expiry(self):
        store=self.store();ident=self.candidate(store);approval=self.approval()
        self.assertTrue(store.evaluate(ident,approval)['enabled'])
        self.now+=timedelta(days=2);self.assertFalse(store.evaluate(ident,approval)['enabled'])
        self.assertEqual(len(store.state['sites']),1)
    def test_registration_maps_source_specific_grant_without_team_category_IDs(self):
        store=self.store();ident=self.candidate(store);approval=self.approval();site=store.evaluate(ident,approval)
        cfg=registration(site,approval);self.assertTrue(cfg['source'].startswith('html_'));self.assertEqual(cfg['allowed_product_hosts'],['store.example.test'])
        bad=dict(approval,allowed_hosts=['other.example.test'])
        with self.assertRaises(ValueError):registration(site,bad)
    def test_adapter_priority_and_partner_blocks(self):
        for host,known,expected in [('www.ebay.com','ebay','ebay'),('m.bunjang.co.kr','blocked_partner_required','blocked_partner_required'),('shop.example.test',None,'generic_jsonld')]:
            with self.subTest(host=host):self.assertEqual(select_adapter({'domain':host,'existing_adapter':known,'official_api_available':True,'capabilities':{'jsonld_product_count':1}},{'api_entitlement_confirmed':True}),expected)
    def test_metadata_reader_cannot_fetch_arbitrary_products_or_secrets(self):
        reader=MetadataHTTP('store.example.test',['https://store.example.test/developers'],self.root,clock=lambda:self.now)
        self.assertTrue(reader.permitted('https://store.example.test/developers'));self.assertFalse(reader.permitted('https://store.example.test/product/1'))
        self.now+=timedelta(hours=2);self.assertFalse(reader.permitted('https://store.example.test/developers'))
    def test_probe_quality_does_not_grant_backend_storage_or_activation(self):
        store=self.store();ident=store.add({'domain':'store.example.test'},'SYNTHETIC')
        html='<form action="/search"><input name="keyword"></form>'+product()
        fake=Mock();fake.fetch.return_value=(200,html)
        site=probe(store,ident,http_factory=lambda *a:fake)
        self.assertTrue(site['supports_price']);self.assertIn('{query}',site['search_url_template']);self.assertFalse(site['enabled'])
        self.assertTrue(site['product_quality_verified']);self.assertIsNotNone(site['last_success_at']);self.assertIsNotNone(site['last_metadata_success_at'])
    def test_metadata_only_does_not_claim_product_collection_success(self):
        store=self.store();ident=store.add({'domain':'store.example.test'},'SYNTHETIC');fake=Mock();fake.fetch.return_value=(200,'<form action="/search"><input name="q"></form>')
        site=probe(store,ident,http_factory=lambda *a:fake);self.assertIsNone(site['last_success_at']);self.assertFalse(site['product_quality_verified'])
    def test_bad_directory_candidate_does_not_block_other_publishers(self):
        store=self.store();store.ingest([{'domain':'127.0.0.1'},{'domain':'store.example.test'}],'SYNTHETIC')
        self.assertEqual(store.report()['candidates'],1);self.assertEqual(store.state['totals']['rejected_candidates'],1)
    def test_OpenSearch_template_and_entity_rejection(self):
        text='<OpenSearchDescription><Url type="text/html" template="https://store.example.test/search?q={searchTerms}&amp;page={startPage?}"/></OpenSearchDescription>'
        self.assertEqual(opensearch_template(text,self.cfg['base_url']),'https://store.example.test/search?q={query}&page={page}')
        with self.assertRaises(ValueError):opensearch_template('<!DOCTYPE a [<!ENTITY x "a">]><a/>',self.cfg['base_url'])
    def test_product_preview_grant_expiry_is_checked_at_request_time(self):
        reader=MetadataHTTP('store.example.test',[self.cfg['base_url']],self.root,clock=lambda:self.now);target='https://store.example.test/item/1'
        approval=dict(self.approval(),expires_at=(self.now+timedelta(seconds=1)).isoformat());reader.allow_product(target,approval)
        self.assertTrue(reader.permitted(target));self.now+=timedelta(seconds=2);self.assertFalse(reader.permitted(target))
    def test_base_transport_refuses_mutating_methods_before_network(self):
        reader=MetadataHTTP('store.example.test',[self.cfg['base_url']],self.root,clock=lambda:self.now)
        with self.assertRaises(ValueError):reader._request('DELETE',self.cfg['base_url'])
        self.assertEqual(reader.state['requests'],[])
    def test_catalogue_cross_publisher_candidate_is_disabled_not_fetched(self):
        store=self.store();ident=store.add({'domain':'store.example.test','metadata_urls':['https://store.example.test/.well-known/api-catalog']},'SYNTHETIC')
        fake=Mock();fake.fetch.return_value=(200,json.dumps({'linkset':[{'anchor':'https://store.example.test','item':[{'href':'https://new.example.test/catalogue'}]}]}))
        probe(store,ident,http_factory=lambda *a:fake)
        self.assertEqual(len(store.state['sites']),2);self.assertEqual(fake.fetch.call_count,1);self.assertEqual(store.report()['enabled'],0)
    def test_metadata_failure_is_site_local_and_keeps_previous_state(self):
        store=self.store();one=store.add({'domain':'one.example.test'},'SYNTHETIC');two=store.add({'domain':'two.example.test'},'SYNTHETIC')
        fake=Mock();fake.fetch.side_effect=Wait('robots_disallowed',hold=True)
        probe(store,one,http_factory=lambda *a:fake)
        self.assertEqual(store.state['sites'][two]['verification_status'],'candidate');self.assertFalse(store.state['sites'][one]['enabled'])
    def test_discovery_cli_offline_scan_restart_and_no_product_activation(self):
        args=['--state-dir',str(self.root/'cli')]
        with redirect_stdout(io.StringIO()):self.assertEqual(discovery_main(args+['--scan']),0);self.assertEqual(discovery_main(args+['--watch','--max-ticks','1']),0)
        store=DiscoveryStore(self.root/'cli');self.assertEqual(store.report()['candidates'],19);self.assertEqual(store.report()['enabled'],0)
    def test_JSONLD_graph_offer_seller_and_full_type_URI(self):
        graph={'@graph':[{'@id':'#p','@type':'https://schema.org/Product','name':'SYNTHETIC lamp','url':self.cfg['base_url'],'itemCondition':'https://schema.org/UsedCondition','offers':{'@id':'#o'}},
            {'@id':'#o','@type':'Offer','price':'12.00','priceCurrency':'USD','availability':'https://schema.org/InStock','seller':{'@id':'#s'}},
            {'@id':'#s','@type':'Organization','name':'SYNTHETIC seller'}]}
        html='<script type="application/ld+json">'+json.dumps(graph)+'</script>'
        result=normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg);self.assertIsNotNone(result['observation']);self.assertEqual(result['seller'],'SYNTHETIC seller')
    def test_conflicting_graph_identity_does_not_select_arbitrary_offer(self):
        html='<script type="application/ld+json">'+json.dumps({'@graph':[{'@id':'#o','@type':'Offer','price':'1'},{'@id':'#o','@type':'Offer','price':'2'}]})+'</script>'
        with self.assertRaises(ValueError):normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg)
    def test_OpenGraph_price_currency_and_native_condition(self):
        fields={'og:type':'product','og:title':'SYNTHETIC lamp','product:price:amount':'$1,234.50','product:price:currency':'USD',
            'product:condition':'used','product:availability':'available','og:image':'/image.png'}
        html=''.join(f'<meta property="{k}" content="{v}">' for k,v in fields.items())+'<div itemprop="seller"><span itemprop="name">SYNTHETIC seller</span></div>'
        result=normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg)
        self.assertEqual(result['price'],'1234.50');self.assertIsNotNone(result['observation']);self.assertTrue(result['metadata']['image_url'].endswith('/image.png'))
    def test_money_does_not_guess_currency_or_price_ranges(self):
        for price,currency in [('$12.00',None),('10-20','USD'),('12,30','EUR'),('NaN','USD')]:
            with self.subTest(price=price),self.assertRaises(ValueError):native_money(price,currency)
        self.assertEqual(native_money('₩12,000원','KRW'),'12000')
    def test_search_form_inference_does_not_use_login_or_POST(self):
        html='<form method="post" action="/private"><input name="q"></form><form action="/login"><input type="password"><input name="q"></form><form action="/search"><input name="keyword"></form>'
        result=analyze(html,self.cfg['base_url']);self.assertEqual(result['search_url_template'],'https://store.example.test/search?keyword={query}');self.assertFalse(result['permission_inferred'])
    def test_semantic_microdata_and_conflicting_prices(self):
        html='<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">SYNTHETIC item</span><meta itemprop="price" content="10"><meta itemprop="priceCurrency" content="USD"><link itemprop="itemCondition" href="https://schema.org/UsedCondition"><link itemprop="availability" href="https://schema.org/InStock"><span itemprop="seller">SYNTHETIC seller</span></div>'
        self.assertIsNotNone(normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg)['observation'])
        html+='<meta itemprop="price" content="20">'
        result=normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg);self.assertIn('price',result['missing_fields'])
    def test_food_table_extraction_maintains_direct_and_facility_separation(self):
        html=product()+'<table><tr><th>원재료명 및 함량</th><td>밀 60%, 설탕</td></tr><tr><th>알레르기 유발물질</th><td>밀, 우유</td></tr><tr><th>혼입 가능성</th><td>땅콩</td></tr></table>'
        result=normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg)
        ev=evidence(result['food_input'],source='html_synthetic',url=self.cfg['base_url'],at=self.now.isoformat())
        self.assertIn('wheat',ev['allergens_declared']);self.assertIn('peanut',ev['allergens_possible_cross_contact']);self.assertIsNone(ev['safe_to_consume'])
    def test_category_mapping_and_country_are_operator_supplied(self):
        html=product().replace('"@type": "Product"','"@type": "Product", "category":"Keyboard"')
        cfg=dict(self.cfg,country='US',category_mapping={'Keyboard':'operator:electronics/keyboards'})
        result=normalize(html,cfg['base_url'],self.now.isoformat(),cfg)
        self.assertEqual(result['metadata']['country'],'US');self.assertEqual(result['metadata']['category_mapped'],'operator:electronics/keyboards')
    def test_last_changed_time_stays_on_unchanged_recheck(self):
        box=SimulatedDelivery(self.cfg,self.root/self.cfg['source'],clock=lambda:self.now);worker=URLWorker(self.cfg,self.root,transport=FakeHTTP(),delivery=box,clock=lambda:self.now)
        worker.step();worker.step();target=next(iter(worker.state['known']));first=worker.state['known'][target]['last_changed_at']
        self.now+=timedelta(seconds=60);worker.step();worker.step()
        self.assertEqual(first,worker.state['known'][target]['last_changed_at']);self.assertNotEqual(first,worker.state['known'][target]['last_checked_at']);worker.close()
    def test_missing_persisted_outbox_fails_before_HTTP(self):
        box=SimulatedDelivery(self.cfg,self.root/self.cfg['source'],clock=lambda:self.now);worker=URLWorker(self.cfg,self.root,transport=FakeHTTP(),delivery=box,clock=lambda:self.now);worker.step();worker.step();worker.close()
        self.assertTrue(load(worker.path,{})['checkpoint_outbox_seen']);box.path.unlink()
        with self.assertRaises(ValueError):URLWorker(self.cfg,self.root,transport=FakeHTTP(),clock=lambda:self.now)
    def test_fleet_starts_only_locally_approved_and_revocation_stops_own_child(self):
        store=self.store();ident=self.candidate(store);store.save();approval=self.approval();child=Mock();child.poll.return_value=None
        create=Mock(return_value=child);fleet=FleetSupervisor(self.root/'fleet',store.root,{ident:approval},clock=lambda:self.now,popen=create)
        with patch.dict(os.environ,{'COLLECTOR_RUN_APPROVED':'no'}):fleet.tick()
        create.assert_not_called()
        with patch.dict(os.environ,{'COLLECTOR_RUN_APPROVED':'yes'}):fleet.tick()
        self.assertEqual(create.call_count,1);self.assertEqual(fleet.report()['running_children'],1)
        self.assertNotIn('shell',create.call_args.kwargs)
        fleet.grants={};fleet.tick();child.terminate.assert_called_once();self.assertEqual(fleet.report()['running_children'],0)
    def test_fleet_failed_child_backoff_does_not_reset_source_state(self):
        store=self.store();ident=self.candidate(store);store.save();child=Mock();child.poll.return_value=None;child.returncode=2
        create=Mock(return_value=child);fleet=FleetSupervisor(self.root/'fleet',store.root,{ident:self.approval()},clock=lambda:self.now,popen=create)
        with patch.dict(os.environ,{'COLLECTOR_RUN_APPROVED':'yes'}):
            fleet.tick();child.poll.return_value=2;fleet.tick();fleet.tick()
        self.assertEqual(create.call_count,1);self.assertEqual(fleet.state['sources'][ident]['process_state'],'restart_backoff');fleet.close()
    def test_busy_discovery_keeps_workers_but_does_not_ignore_grant_revocation(self):
        store=self.store();ident=self.candidate(store);store.save();child=Mock();child.poll.return_value=None
        fleet=FleetSupervisor(self.root/'fleet',store.root,{ident:self.approval()},clock=lambda:self.now,popen=Mock(return_value=child))
        with patch.dict(os.environ,{'COLLECTOR_RUN_APPROVED':'yes'}):
            fleet.tick()
            with patch.object(fleet,'desired',side_effect=OSError('busy')):
                fleet.tick();child.terminate.assert_not_called();fleet.grants={};fleet.tick();child.terminate.assert_called_once()
        fleet.close()
    def test_food_percentage_out_of_range_is_reviewed_even_with_declared_allergens(self):
        data=evidence({'name':'SYNTHETIC','category':'electronics','ingredients':'밀 150%','allergens':'밀'},source='html_synthetic',url=self.cfg['base_url'],at=self.now.isoformat())
        self.assertIn('wheat',data['allergens_declared']);self.assertTrue(data['requires_review']);self.assertIsNone(data['safe_to_consume'])
    def test_SQLite_receipt_exact_replay_and_payload_conflict(self):
        body=normalize(product(),self.cfg['base_url'],self.now.isoformat(),self.cfg)['observation']
        store=ReceiptStore(self.root/'collector_test_lab.sqlite',['store.example.test'],['USD'])
        self.assertEqual(store.receive(body)[0],201);self.assertEqual(store.receive(body)[0],200)
        changed=dict(body,price='999');self.assertEqual(store.receive(changed)[0],409);self.assertEqual(store.counts()['observations'],1)
        store.path.unlink();self.assertFalse(store.path.exists())
    def test_SQLite_receipt_updated_unchanged_503_and_namespace(self):
        with self.assertRaises(ValueError):ReceiptStore(self.root/'production.sqlite',[],[])
        store=ReceiptStore(self.root/'collector_test_lab.sqlite',['store.example.test'],['USD'])
        body=normalize(product(),self.cfg['base_url'],self.now.isoformat(),self.cfg)['observation'];store.fail_next=True
        self.assertEqual(store.receive(body)[0],503);self.assertEqual(store.counts()['observations'],0);store.receive(body)
        body=normalize(product('10.00'),self.cfg['base_url'],self.now.isoformat(),self.cfg)['observation'];self.assertEqual(store.receive(body)[1]['change_kind'],'updated')
    def test_public_lookup_fixed_paths_read_tools_and_product_caps(self):
        reader=PublicReader('yappy_kids',self.root,maximum=1,clock=lambda:self.now)
        with self.assertRaises(ValueError):reader.tool('create_order',{})
        with self.assertRaises(ValueError):reader.tool('search_products',{'query':'x','limit':50,'page':0})
        self.assertFalse(reader.permitted('https://www.yappykids.com/private'))
        reader.reserve(reader.policy['api']);self.assertFalse(reader.permitted(reader.policy['api']))
    def test_public_feed_reuses_native_converter_and_inspects_only_three(self):
        reader=Mock();reader.provider='smartify';reader.policy={'feed':'https://smartify.in/product-feed.xml'};reader.clock.return_value=self.now
        reader.fetch.return_value=(200,self.xml(5));results=[]
        result=feed_probe(reader,3,on_valid=results.append)
        self.assertEqual(result['valid_products'],3);self.assertEqual(len(results),3);self.assertTrue(all(r['source']=='smartify' for r in results))
    def test_public_MCP_detail_missing_fields_held_not_assumed_new(self):
        reader=Mock();reader.policy={'host':'www.yappykids.com'};reader.clock.return_value=self.now
        item={'id':1,'name':'SYNTHETIC','price':'10','currency':'EUR','availability':'in_stock','url':'https://www.yappykids.com/product/1'}
        reader.tool.side_effect=[{'products':[item]},item]
        result=mcp_probe(reader,3,'SYNTHETIC');self.assertEqual(result['held_products'],1);self.assertIn('condition',result['products'][0]['reasons']);self.assertIn('seller',result['products'][0]['reasons'])
    def feed_cfg(self):
        cfg=copy.deepcopy(self.cfg);cfg.update(source='smartify',base_url='https://smartify.in/',allowed_product_hosts=['smartify.in'],currencies=['INR'],mode='general',
            provider_min_interval_seconds=7200,max_products_per_cycle=1,merchant_name='SYNTHETIC merchant',merchant_reference='SYNTHETIC publisher evidence')
        return cfg
    def xml(self,n=2):
        return '<rss xmlns:g="http://base.google.com/ns/1.0"><channel>'+''.join(f'<item><g:id>SYNTHETIC-{i}</g:id><g:mpn>SKU-{i}</g:mpn><g:title>SYNTHETIC lamp {i}</g:title><g:link>https://smartify.in/products/SYNTHETIC-{i}</g:link><g:price>100 INR</g:price><g:condition>new</g:condition><g:availability>in_stock</g:availability></item>' for i in range(n))+'</channel></rss>'
    def feed_worker(self,cfg=None,http=None,directory=None):
        cfg=cfg or self.feed_cfg();http=http or Mock();http.state={'requests':[],'hold':None};http.fetch.return_value=(200,self.xml())
        root=directory or self.root;box=SimulatedDelivery(cfg,root/cfg['source'],clock=lambda:self.now)
        return FeedWorker(cfg,root,http=http,delivery=box,clock=lambda:self.now)
    def test_feed_7200_schedule_rotates_and_skips_unchanged(self):
        self.now-=timedelta(hours=4)
        worker=self.feed_worker();worker.step();self.assertEqual(worker.state['cursor'],1)
        worker.step();self.assertEqual(worker.state['totals']['products_success'],1)
        self.now+=timedelta(seconds=7200);worker.step();self.assertEqual(worker.state['cursor'],0)
        self.now+=timedelta(seconds=7200);worker.step();self.assertEqual(worker.delivery.data['totals']['unchanged'],1)
        self.assertEqual(len(worker.delivery.box.fake_API.calls),2);worker.close()
    def test_feed_requires_storage_and_native_merchant_evidence(self):
        cfg=self.feed_cfg();cfg['merchant_reference']=None;worker=self.feed_worker(cfg);worker.step()
        self.assertEqual(worker.state['totals']['merchant_publisher_evidence_required'],1);self.assertEqual(worker.delivery.pending_count(),0);worker.close()
    def test_feed_transient_retry_exhaustion_keeps_history(self):
        worker=self.feed_worker();worker.http.fetch.side_effect=lambda *a:(_ for _ in ()).throw(Wait('server_error',self.now+timedelta(seconds=60)))
        for _ in range(3):worker.step();self.now+=timedelta(seconds=120)
        self.assertIn('retry_exhausted',worker.state['hold']);self.assertEqual(worker.state['attempts'],3);worker.close()
    def test_feed_uncertain_and_interrupted_tasks_do_not_reset(self):
        worker=self.feed_worker();worker.state['inflight']=True;worker.save();worker.close()
        restored=self.feed_worker();self.assertIn('interrupted',restored.state['hold']);restored.close()
    def test_feed_missing_fields_and_native_used_state_are_not_invented(self):
        worker=self.feed_worker();worker.http.fetch.return_value=(200,self.xml().replace('<g:condition>new</g:condition>',''))
        worker.step();self.assertEqual(worker.state['totals']['products_held'],1);self.assertEqual(worker.delivery.pending_count(),0);worker.close()
    def test_feed_cannot_shorten_7200_or_change_merchant_host(self):
        cfg=self.feed_cfg();cfg['provider_min_interval_seconds']=60
        with self.assertRaises(ValueError):validate_feed(cfg)
        cfg=self.feed_cfg();cfg['allowed_product_hosts']=['other.example.test']
        with self.assertRaises(ValueError):validate_feed(cfg)
    def test_feed_description_changes_require_separate_content_storage_grant(self):
        cfg=self.feed_cfg();worker=self.feed_worker(cfg)
        document=self.xml().replace('<g:condition>new</g:condition>','<g:description>SYNTHETIC description</g:description><g:condition>new</g:condition>')
        worker.http.fetch.return_value=(200,document);worker.step()
        self.assertNotIn('description',worker.delivery.box.fake_API.calls[0][1]);worker.close()
        cfg['rights']['allowed_uses'].append('description_storage');worker=self.feed_worker(cfg,directory=self.root/'licensed')
        worker.http.fetch.return_value=(200,self.xml().replace('<g:condition>new</g:condition>','<g:description>SYNTHETIC description</g:description><g:condition>new</g:condition>'))
        worker.step();self.assertEqual(worker.state['totals']['products_success'],1)
        self.assertEqual(worker.delivery.box.fake_API.calls[0][1]['description'],'SYNTHETIC description')
        self.assertTrue(worker.state['known']);worker.close()
    def test_food_detected_without_labels_stays_unknown_and_requires_contract(self):
        data=evidence({'name':'식품 시리얼','category':'food'},source='html_synthetic',url=self.cfg['base_url'],at=self.now.isoformat())
        self.assertTrue(data['food_detected']);self.assertEqual(data['allergen_status'],'not_reported');self.assertIsNone(data['safe_to_consume'])
    def test_food_GTIN_exact_match_not_listing_ID_or_name(self):
        record={'code':'3017620422003','product_name':'SYNTHETIC food','ingredients_text':'milk, sugar','allergens':'en:milk','traces':'en:peanuts'}
        result=attach({'gtin':'3017620422003'},record,self.now.isoformat())
        self.assertIn('milk',result['allergens_declared']);self.assertTrue(result['requires_review']);self.assertIsNone(result['safe_to_consume'])
        with self.assertRaises(ValueError):attach({'source_listing_id':'3017620422003','name':'SYNTHETIC food'},record,self.now.isoformat())
        with self.assertRaises(ValueError):gtin('3017620422004')
    def test_food_inferred_tags_not_promoted_to_label_declaration(self):
        result=record_evidence({'code':'3017620422003','ingredients_text':'milk','allergens_tags':['en:milk'],'traces_tags':['en:peanuts']},'3017620422003',self.now.isoformat())
        self.assertIsNone(result['allergens_declared']);self.assertIsNone(result['allergens_possible_cross_contact']);self.assertEqual(result['allergen_status'],'not_reported')
    def test_food_API_policy_gate_blocks_without_contact_registration_and_license(self):
        reader=FoodHTTP('3017620422003',self.root,'','',False,clock=lambda:self.now)
        with self.assertRaises(Wait):reader.lookup('3017620422003')
        self.assertEqual(reader.state['requests'],[])
    def test_GTIN_metadata_keeps_merchant_identity_distinct(self):
        html=product().replace('"@type": "Product"','"@type": "Product", "gtin13":"3017620422003"')
        result=normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg)
        self.assertEqual(result['metadata']['native_gtins'][0]['value'],'03017620422003');self.assertEqual(result['product_number'],'SYNTHETIC-1')

if __name__=='__main__':unittest.main()
