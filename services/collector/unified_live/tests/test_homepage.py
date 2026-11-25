import copy,json,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from bs4 import BeautifulSoup
from services.collector.unified_live.mock import fixture_config,FakeHTTP,product
from services.collector.unified_live.engine import URLWorker
from services.collector.unified_live.storefront import platform,classify,navigation
from services.collector.unified_live.homepage import profile,main
from services.collector.unified_live.parser import normalize
from services.collector.unified_live.transport import Wait,decode_response
from services.collector.collector_ops.mock import SimulatedDelivery

BASE='https://store.example.test'
def item(i='one',price='12.00',state='InStock'):
 p=json.loads(product(price,state).split('application/ld+json">')[1].split('</script>')[0]);p.update(productID='SYNTHETIC-'+i,sku='SKU-'+i,url=BASE+'/products/'+i)
 return '<script type="application/ld+json">'+json.dumps(p)+'</script>'
class HomepageTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.cfg=fixture_config();self.cfg.update(homepage_crawl=True,mode='general',provider_min_interval_seconds=7200,queries=[],search_url_template='',start_urls=[BASE+'/'],max_pages_per_cycle=5);self.now=datetime.now(timezone.utc)-timedelta(hours=6)
 def tearDown(self):self.temp.cleanup()
 def setup_worker(self):
  h=FakeHTTP();h.pages={BASE+'/':(200,'<script>Shopify.shop="demo";</script><nav><a href="/collections/keys">Keyboards</a></nav>'),BASE+'/collections/keys':(200,'<a href="/products/one">One</a><a rel="next" href="?page=2">Next</a>'),BASE+'/collections/keys?page=2':(200,'<a href="/products/one?utm_source=x">dup</a><a href="/products/two">Two</a>'),BASE+'/products/one':(200,item()),BASE+'/products/two':(200,item('two'))}
  b=SimulatedDelivery(dict(self.cfg,test_extensions_enabled=True),self.root/self.cfg['source'],clock=lambda:self.now);w=URLWorker(self.cfg,self.root,transport=h,delivery=b,clock=lambda:self.now);return w,h,b
 def cycle(self,w):
  n=w.state['totals'].get('cycles_completed',0)
  for _ in range(30):
   w.step()
   if w.state['totals'].get('cycles_completed',0)>n:return
  self.fail('bounded cycle did not complete')
 def test_home_category_pagination_detail_queue_and_7200_schedule(self):
  w,h,b=self.setup_worker();self.cycle(w);self.assertEqual(w.state['totals']['products_extracted'],2);self.assertEqual(len(b.fake_API.calls),2);self.assertEqual(w.report()['effective_interval_seconds'],7200);self.assertEqual(w.report()['platform'],'shopify');self.assertEqual(len(b.state['entries']),2);self.assertEqual(len(w.delivery.extras.data['extensions']),2);self.assertEqual((datetime.fromisoformat(w.state['next_cycle_at'])-self.now).total_seconds(),7200);w.close()
 def test_repeat_unchanged_then_price_and_stock_change(self):
  w,h,b=self.setup_worker();self.cycle(w);self.now+=timedelta(seconds=7200);self.cycle(w);self.assertEqual(len(b.fake_API.calls),2)
  self.now+=timedelta(seconds=7200);h.pages[BASE+'/products/one']=(200,item(price='10.00',state='OutOfStock'));self.cycle(w);self.assertEqual(len(b.fake_API.calls),3);last=b.fake_API.calls[-1][1];self.assertEqual((last['price'],last['availability']),('10.00','out_of_stock'));w.close()
 def test_category_with_one_nested_product_is_not_home_product(self):
  w,h,b=self.setup_worker();p=json.loads(item().split('application/ld+json">')[1].split('</script>')[0]);h.pages[BASE+'/']=(200,'<script type="application/ld+json">'+json.dumps({'@type':'ItemList','itemListElement':[{'@type':'ListItem','item':p}]})+'</script>');self.cycle(w);self.assertEqual(len(b.fake_API.calls),1);self.assertEqual(b.fake_API.calls[0][1]['url'],BASE+'/products/one');w.close()
 def test_four_platforms_are_evidence_detection_not_permissions(self):
  for name,html in [('cafe24','<div class="xans-product-detail">'),('godomall','<meta name="generator" content="Godomall">'),('makeshop','<a href="/shop/shopdetail.html?branduid=1">'),('shopify','<script src="https://cdn.shopify.com/x.js">')]:
   with self.subTest(name=name):self.assertEqual(platform(BeautifulSoup(html,'html.parser')),name)
 def test_platform_routes_and_categories(self):
  for path,expected in [('/product/list.html?cate_no=1','auto'),('/product/detail.html?product_no=1','detail'),('/goods/goods_list.php?cateCd=1','auto'),('/goods/goods_view.php?goodsNo=1','detail'),('/shop/shopbrand.html?xcode=1','auto'),('/shop/shopdetail.html?branduid=1','detail'),('/products/category/nintendo','auto'),('/collections/all','auto'),('/collections/all/products/book','detail')]:
   with self.subTest(path=path):self.assertEqual(classify(BASE+path),expected)
 def test_no_cart_auth_cross_origin_or_nofollow_traversal(self):
  html='<nav><a href="/women">Women</a><a href="/login">login</a><a href="https://evil.test/products/a">evil</a><a rel="nofollow" href="/products/b">no</a><a href="/cart">cart</a><a href="/products/a?api_key=secret">secret</a></nav>'
  details,categories,_=navigation(BeautifulSoup(html,'html.parser'),BASE+'/');self.assertEqual(details,[]);self.assertEqual(categories,[BASE+'/women'])
 def test_navigation_budget_prevents_infinite_category_expansion(self):
  self.cfg['max_pages_per_cycle']=1;w,h,b=self.setup_worker();self.cycle(w);self.assertEqual(len(h.state['requests']),1);self.assertEqual(len(b.fake_API.calls),0);w.close()
 def test_sitemap_uses_real_worker_and_rejects_external_loc(self):
  w,h,b=self.setup_worker();h.pages[BASE+'/']=(200,'<h1>Shop</h1>');from urllib.robotparser import RobotFileParser
  h.robots=RobotFileParser();h.robots.parse(['User-agent: *','Allow: /','Sitemap: '+BASE+'/sitemap.xml']);h.pages[BASE+'/sitemap.xml']=(200,'<urlset><url><loc>'+BASE+'/products/one</loc></url><url><loc>https://evil.test/products/b</loc></url></urlset>');self.cycle(w);self.assertEqual(len(b.fake_API.calls),1);self.assertEqual(len(h.state['requests']),3);w.close()
 def test_bad_detail_does_not_stop_other_product(self):
  w,h,b=self.setup_worker();h.pages[BASE+'/products/one']=(200,'<script type="application/ld+json">{"@type":"Product","offers":[],"hasVariant":true}</script>');self.cycle(w);self.assertEqual(len(b.fake_API.calls),1);self.assertEqual(w.state['totals']['products_held'],1);w.close()
 def test_captcha_stops_source_without_requesting_next_page(self):
  w,h,b=self.setup_worker();h.pages[BASE+'/']=(200,'<title>CAPTCHA</title><a href="/products/one">one</a>');w.step();w.step();self.assertEqual(w.state['hold'],'access_challenge_stop');self.assertEqual(len(h.state['requests']),1);w.close()
 def test_native_table_condition_is_used_but_not_defaulted(self):
  html=item().replace('https://schema.org/UsedCondition','')+'<table><tr><th>Condition</th><td>New</td></tr></table>';r=normalize(html,BASE+'/products/one',self.now.isoformat(),self.cfg);self.assertEqual(r['condition'],'new')
  r=normalize(item().replace('https://schema.org/UsedCondition',''),BASE+'/products/one',self.now.isoformat(),self.cfg);self.assertEqual(r['observation']['condition'],'unknown')
 def test_missing_image_is_held_in_homepage_mode(self):
  r=normalize(item().replace('https://store.example.test/image/1.jpg',''),BASE+'/products/one',self.now.isoformat(),self.cfg);self.assertIsNone(r['observation']);self.assertIn('image_url',r['missing_fields'])
 def test_platform_CSS_keeps_native_price_currency_condition(self):
  html='<div class="xans-product-detail"><div class="headingArea"><h2>Native keyboard</h2></div></div><span id="span_product_price_text">12.00</span><div class="xans-product-image"><img class="BigImage" src="/image.jpg"></div><meta itemprop="priceCurrency" content="USD"><link itemprop="availability" href="https://schema.org/InStock"><link itemprop="itemCondition" href="https://schema.org/NewCondition"><span itemprop="seller">Native seller</span>'
  r=normalize(html,BASE+'/products/one',self.now.isoformat(),self.cfg);self.assertEqual(r['name'],'Native keyboard');self.assertEqual(r['price'],'12.00');self.assertIsNotNone(r['observation'])
 def test_profile_defaults_do_not_grant_or_send(self):
  p=profile(BASE+'/',{});self.assertFalse(p['enabled']);self.assertFalse(p['backend_enabled']);self.assertEqual(p['rights'],{});self.assertTrue(p['homepage_crawl'])
 def test_one_homepage_registration_never_overwrites_existing_policy(self):
  f=self.root/'policy.json';f.write_text('{}');args=['--url',BASE+'/','--policy',str(f),'--state-dir',str(self.root),'--register'];self.assertEqual(main(args),0);f.write_text('{"requests_per_hour":10}');self.assertEqual(main(args),2)
 def test_homepage_plan_performs_no_HTTP(self):
  f=self.root/'policy.json';f.write_text('{}')
  with patch('services.collector.unified_live.transport.SafeHTTP.__init__',side_effect=AssertionError('no network')):self.assertEqual(main(['--url',BASE+'/','--policy',str(f),'--state-dir',str(self.root),'--plan']),0)
 def test_EUC_KR_CP949_require_declared_charset(self):
  text='<meta charset="euc-kr"><h1>실제 상품</h1>';self.assertEqual(decode_response(text.encode('euc-kr'),'text/html'),text)
  self.assertEqual(decode_response('신품'.encode('cp949'),'text/html; charset=cp949'),'신품')
  with self.assertRaises(Wait):decode_response('신품'.encode('cp949'),'text/html')
 def test_unsupported_encoding_is_not_network_uncertainty(self):
  with self.assertRaisesRegex(Wait,'unsupported_declared_charset'):decode_response(b'abc','text/html; charset=utf-7')

 def test_native_OG_aliases_and_product_image_alt_are_not_guessed(self):
  html='<meta property="og:price" content="91.99"><meta property="og:currency" content="EUR"><meta property="og:availability" content="In stock"><div class="product-info-wrapper"><h2 class="title">Native game</h2></div><img alt="Native game" src="/game.jpg">'
  cfg=dict(self.cfg,currencies=['EUR']);r=normalize(html,BASE+'/products/one',self.now.isoformat(),cfg);self.assertEqual(r['price'],'91.99');self.assertEqual(r['currency'],'EUR');self.assertEqual(r['availability'],'available');self.assertEqual(r['metadata']['image_url'],BASE+'/game.jpg');self.assertEqual(r['condition'],'unknown');self.assertEqual(r['observation']['condition'],'unknown')

 def test_browser_abort_keeps_original_budget_wait_for_worker_retry(self):
  import types
  from services.collector.unified_live.render import PlaywrightRenderer
  class Context:
   def route_web_socket(self,*args):pass
   def add_init_script(self,*args):pass
   def route(self,_,fn):self.fn=fn
   def new_page(self):return self
   def goto(self,*args,**kwargs):
    request=types.SimpleNamespace(method='GET',resource_type='document',url=BASE+'/')
    self.fn(types.SimpleNamespace(request=request,abort=lambda:None));raise RuntimeError('aborted by original budget limit')
   def close(self):pass
  c=Context();browser=types.SimpleNamespace(new_context=lambda **kw:c,close=lambda:None)
  p=types.SimpleNamespace(chromium=types.SimpleNamespace(launch=lambda **kw:browser))
  class Manager:
   def __enter__(self):return p
   def __exit__(self,*args):pass
  api=types.ModuleType('playwright.sync_api');api.sync_playwright=lambda:Manager()
  def fetch(_):raise Wait('budget_wait',self.now+timedelta(hours=1))
  http=types.SimpleNamespace(host='store.example.test',fetch=fetch,clock=lambda:self.now)
  with patch.dict('sys.modules',{'playwright':types.ModuleType('playwright'),'playwright.sync_api':api}),self.assertRaisesRegex(Wait,'budget_wait'):PlaywrightRenderer().render(BASE+'/',http)

 def test_optional_seller_is_not_an_extra_Observation_v2_requirement(self):
  r=normalize(item().replace('"name": "SYNTHETIC seller"','"name": null'),BASE+'/products/one',self.now.isoformat(),self.cfg);self.assertIsNone(r['seller']);self.assertIsNotNone(r['observation']);self.assertNotIn('seller',r['observation']);self.assertFalse(r['metadata']['normalization_evidence']['storefront_identity']['legal_seller_verified'])

 def test_existing_fleet_registration_keeps_explicit_homepage_traversal(self):
  from services.collector.unified_live.fleet import registration
  site={'enabled':True,'adapter_name':'generic_html','domain':'store.example.test','marketplace_id':'marketplace-fixture','search_url_template':None,'kind':'general','country':None,'crawl_interval_seconds':7200}
  approval=dict(self.cfg['rights'],allowed_hosts=['store.example.test'],homepage_crawl=True,currencies=['USD'],max_pages_per_cycle=6)
  cfg=registration(site,approval);self.assertTrue(cfg['homepage_crawl']);self.assertEqual(cfg['start_urls'],[BASE+'/']);self.assertEqual(cfg['max_pages_per_cycle'],6)
