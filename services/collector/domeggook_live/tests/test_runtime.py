import contextlib,copy,io,json,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
from ..runtime import STATE_ROOT,now
from ..domeggook_operations import configuration,budget_delay,main,PermittedStore
from ..domeggook_open import OpenClient,SafeAPIError
from ..domeggook_pipeline import normalize_detail
from ..domeggook_options import option_offers
from ..stable_identity import native_tuple
from ..progress import save
from .fixtures import fixture
PKG=__package__.rsplit('.tests',1)[0]

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        STATE_ROOT.mkdir(parents=True,exist_ok=True);self.tmp=tempfile.TemporaryDirectory(prefix='runtime_',dir=STATE_ROOT)
        self.root=Path(self.tmp.name).resolve();self.root.relative_to(STATE_ROOT);self.cfg=configuration()
    def tearDown(self):self.tmp.cleanup()
    def test_window_and_KST_daily_budget_preserve_legacy_counts(self):
        stamp=datetime(2026,11,18,13,tzinfo=timezone.utc)
        recent=[{'at':(stamp-timedelta(minutes=5)).isoformat()}]*12
        self.assertGreater(budget_delay(recent,self.cfg,stamp)[0],0)
        self.assertEqual(budget_delay([],self.cfg,stamp,legacy=recent)[0],0)
        daily=[{'at':(stamp-timedelta(hours=2)).isoformat()}]*120
        self.assertEqual(budget_delay(daily,self.cfg,stamp)[1],'daily_budget_wait')
    def test_blocked_HTTP_and_HTTP200_API_error_persist_hold(self):
        for index,(status,body) in enumerate(((403,{}),(429,{}),(200,{'code':'403'}))):
            path=self.root/f'ledger{index}.json';save(path,{'requests':[],'hold':None,'current_internal_cap':2})
            with patch(PKG+'.domeggook_open.read_key',return_value='SYNTHETIC_SECRET'):client=OpenClient(ledger_path=path)
            response=Mock(status_code=status,headers={},content=b'{}');response.json.return_value=body
            client.session=Mock();client.session.get.return_value=response
            with self.assertRaises(SafeAPIError):client.get('getItemView',no='88000001')
            before=client.session.get.call_count
            with self.assertRaises(SafeAPIError):client.get('getItemView',no='88000001')
            self.assertEqual(client.session.get.call_count,before);self.assertNotIn('SYNTHETIC_SECRET',path.read_text())
    def test_unfinished_reservation_never_auto_resends(self):
        path=self.root/'reserved.json';save(path,{'requests':[{'at':now(),'status':'reserved'}],'hold':None})
        with patch(PKG+'.domeggook_open.read_key',return_value='SYNTHETIC_SECRET'):client=OpenClient(ledger_path=path)
        self.assertTrue(client.state['hold'])
        with self.assertRaises(SafeAPIError):client.get('getItemView',no='88000001')
    def test_option_name_change_and_order_preserve_native_identity(self):
        listing,payload=fixture();row=normalize_detail(listing,payload,now());first,_=option_offers(row)
        changed=copy.deepcopy(row)
        for value in changed['native_options']['data'].values():value['name']='SYNTHETIC renamed'
        changed['native_options']['data']=dict(reversed(list(changed['native_options']['data'].items())))
        self.assertEqual({native_tuple(r) for r in first},{native_tuple(r) for r in option_offers(changed)[0]})
        self.assertEqual(first[0]['unit_price'],1100);self.assertEqual(first[1]['stock_quantity'],0)
    def test_MOQ_purchase_unit_and_unknown_shipping_not_exact_total(self):
        listing,payload=fixture();payload['qty']['domeUnit']='10';payload['deli']['dome']={'type':'수량별비례'}
        row=normalize_detail(listing,payload,now())
        self.assertEqual(row['minimum_purchase_quantity'],10);self.assertEqual(row['unit_price'],900)
        self.assertEqual(row['minimum_product_total'],9000);self.assertIsNone(row['estimated_minimum_checkout_total'])
        self.assertFalse(row['checkout_total_is_exact'])
    def test_license_false_and_unverified_metadata_not_persisted(self):
        listing,payload=fixture();payload['desc']['license']['usable']='false'
        row=normalize_detail(listing,payload,now());offers,_=option_offers(row)
        self.assertIsNone(row['description_html']);self.assertEqual(row['detail_image_urls'],[])
        store=PermittedStore(self.root,self.cfg);store.put(offers[0]);self.assertFalse(store.path.exists())
    def test_old_modes_and_dryrun_are_keyless_and_write_free(self):
        with (patch(PKG+'.domeggook_open.read_key',side_effect=AssertionError('must not read key')),
              patch(PKG+'.domeggook_discovery.save',side_effect=AssertionError('must not write'))):
            for mode in ('--once','--watch','--discover-once','--discover-watch','--refresh-once','--status'):
                with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main([mode,'--dry-run']),0)
    def test_request_ledger_cannot_be_reset(self):
        path=self.root/'request_ledger.json';save(path,{'requests':[{'at':now()}]})
        with self.assertRaises(ValueError):save(path,{'requests':[]})
