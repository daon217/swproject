"""Offline regressions: search summaries are not stock evidence."""
import copy
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from .. import normalize
from ..adapters import Adapter, EBAY
from ..ebay_credentials import load_ebay_env
from ..http import ProviderError
from ..probe import bounded_lookup, inspect_item, plan
from .fixtures import config, ebay

AT = datetime.now(timezone.utc).isoformat()


class EbayEnrichmentTests(unittest.TestCase):
    def normalize(self, row):
        return normalize.ebay(row, AT, config('ebay_browse'))

    def test_complete_condition_table_and_subtype_preservation(self):
        for identity, common, subtype in [
            ('1000','new','new'), ('1500',None,'new_other_open_box'),
            ('1750',None,'new_with_defects'), ('2000',None,'certified_refurbished'),
            ('2010',None,'excellent_refurbished'), ('2020',None,'very_good_refurbished'),
            ('2030',None,'good_refurbished'), ('2500',None,'seller_refurbished'),
            ('2750','used','like_new'), ('2990','used','pre_owned_excellent'),
            ('3000','used','used'), ('3010','used','pre_owned_fair'),
            ('4000','used','very_good'), ('5000','used','good'),
            ('6000','used','acceptable'), ('7000',None,'for_parts_or_not_working')]:
            with self.subTest(identity=identity):
                row = ebay();row['conditionId'] = identity;row.pop('condition')
                if identity in ('2750', '3000', '4000'):
                    row['condition'] = {'2750':'Like New', '3000':'Used', '4000':'Very Good'}[identity]
                result = self.normalize(row)
                self.assertEqual(result['condition'], common)
                self.assertEqual(result['condition_detail'], subtype)
                self.assertEqual(result['observation'] is not None, common is not None)
                if result['observation']:
                    self.assertNotIn('condition_detail', result['observation'])

    def test_absent_id_uses_exact_label_but_explicit_null_unknown_or_conflict_held(self):
        row = ebay();row.pop('conditionId')
        self.assertEqual(self.normalize(row)['condition'], 'new')
        for identity, label in [(None, 'New'), ('9999', 'New'), ('1000', 'Used'), ('3000', 'New')]:
            with self.subTest(identity=identity, label=label):
                row.update(conditionId=identity, condition=label)
                self.assertIsNone(self.normalize(row)['observation'])

    def test_no_substring_guesses_or_grading_as_used(self):
        for label in ['new-ish', 'Unknown', 'Almost New', 'Graded', 'Ungraded']:
            row = ebay();row.pop('conditionId');row['condition'] = label
            self.assertIsNone(self.normalize(row)['condition'])

    def test_category_dependent_ids_without_label_do_not_guess_wear_condition(self):
        for identity in ('2750', '3000', '4000'):
            row = ebay();row['conditionId'] = identity;row.pop('condition')
            result = self.normalize(row)
            self.assertIsNone(result['condition'])
            self.assertEqual(result['condition_reason'], 'category_condition_requires_label')
        for identity in ['2750', '3000', '4000']:
            row = ebay();row.update(conditionId=identity, condition='Graded')
            self.assertIsNone(self.normalize(row)['condition'])

    def test_limited_stock_is_available_without_inventing_quantity(self):
        row = ebay();row['estimatedAvailabilities'] = [{'estimatedAvailabilityStatus': 'LIMITED_STOCK'}]
        result = self.normalize(row)
        self.assertEqual(result['observation']['availability'], 'available')
        self.assertIsNone(result['stock_quantity'])
        self.assertTrue(result['purchase_available'])
        self.assertEqual(result['quantity_kind'], 'unknown')

    def test_stock_and_limited_stock_options_agree_on_purchase_availability(self):
        row = ebay();row['estimatedAvailabilities'].append({'estimatedAvailabilityStatus': 'LIMITED_STOCK'})
        self.assertEqual(self.normalize(row)['availability'], 'available')

    def test_real_adapter_search_to_detail_enriches_incomplete_summary_in_mock(self):
        row = ebay();row['conditionId'] = '2750';row['condition'] = 'Like New'
        row['estimatedAvailabilities'] = [{'estimatedAvailabilityStatus': 'LIMITED_STOCK'}]
        summary = {key: value for key, value in row.items() if key not in ('conditionId', 'estimatedAvailabilities')}
        http = Mock();http.state = {'requests': []};http.task_id = 'SYNTHETIC'
        http.get_json.side_effect = [{'itemSummaries': [summary], 'total': 1}, row]
        adapter = Adapter(config('ebay_browse'), http, retry_auth=False)
        adapter.oauth = Mock();adapter.oauth._get_access_token.return_value = 'SYNTHETIC_TOKEN'
        result = bounded_lookup(adapter, adapter.cfg, 3)
        self.assertEqual((result['success'], result['held'], result['failed']), (1, 0, 0))
        self.assertEqual(http.get_json.call_count, 2)
        self.assertEqual(result['products'][0]['evidence']['condition_detail'], 'like_new')
        self.assertEqual(result['products'][0]['evidence']['quantity_kind'], 'unknown')

    def test_unknown_status_or_quantity_only_not_inferred_from_price_or_listing(self):
        for entries in [[], [{'estimatedAvailableQuantity': 10}], [{'estimatedAvailabilityStatus': 'FUTURE_VALUE'}],
                        [{'estimatedAvailabilityStatus': 'IN_STOCK'}, {}]]:
            with self.subTest(entries=entries):
                row = ebay();row['estimatedAvailabilities'] = entries
                result = self.normalize(row)
                self.assertIsNone(result['observation'])
                self.assertIsNone(result['stock_quantity'])
                self.assertIsNone(result['purchase_available'])

    def test_threshold_and_repeated_delivery_options_never_become_exact_or_summed(self):
        entry = {'estimatedAvailabilityStatus': 'IN_STOCK', 'availabilityThreshold': 10,
                 'availabilityThresholdType': 'MORE_THAN', 'estimatedAvailableQuantity': 12}
        row = ebay();row['estimatedAvailabilities'] = [copy.deepcopy(entry), copy.deepcopy(entry)]
        result = self.normalize(row)
        self.assertIsNone(result['stock_quantity'])
        self.assertEqual(len(result['quantity_estimates']), 2)
        self.assertEqual(result['quantity_estimates'][0]['estimatedAvailableQuantity'], 12)
        self.assertNotIn('stock_quantity', result['observation'])

    def test_out_of_stock_does_not_invent_exact_zero(self):
        row = ebay();row['estimatedAvailabilities'] = [{'estimatedAvailabilityStatus': 'OUT_OF_STOCK'}]
        result = self.normalize(row)
        self.assertEqual(result['availability'], 'out_of_stock')
        self.assertFalse(result['purchase_available'])
        self.assertIsNone(result['stock_quantity'])

    def test_conflicting_status_or_quantities_are_held(self):
        for entries in [
            [{'estimatedAvailabilityStatus': 'IN_STOCK'}, {'estimatedAvailabilityStatus': 'OUT_OF_STOCK'}],
            [{'estimatedAvailabilityStatus': 'IN_STOCK', 'estimatedAvailableQuantity': 0}],
            [{'estimatedAvailabilityStatus': 'OUT_OF_STOCK', 'estimatedRemainingQuantity': 4}],
            [{'estimatedAvailabilityStatus': 'IN_STOCK', 'estimatedAvailableQuantity': True}],
            [{'estimatedAvailabilityStatus': 'IN_STOCK', 'availabilityThreshold': -1}],
            None, [None],
        ]:
            with self.subTest(entries=entries):
                row = ebay();row['estimatedAvailabilities'] = entries
                self.assertIsNone(self.normalize(row)['availability'])

    def test_end_date_overrides_stock_and_invalid_dates_hold(self):
        row = ebay();row['itemEndDate'] = (datetime.fromisoformat(AT)-timedelta(seconds=1)).isoformat()
        self.assertEqual(self.normalize(row)['availability'], 'ended')
        for value in ['2026-11-22T14:00:00', 'not a date', None]:
            row['itemEndDate'] = value
            self.assertIsNone(self.normalize(row)['availability'])
        row['itemEndDate'] = (datetime.fromisoformat(AT)+timedelta(hours=1)).isoformat()
        self.assertEqual(self.normalize(row)['availability'], 'available')

    def test_detail_fetch_uses_native_id_and_never_search_stock_fallback(self):
        adapter = Adapter(config('ebay_browse'), Mock())
        row = ebay();row.pop('estimatedAvailabilities')
        adapter.ebay_get = Mock(return_value=row)
        detail = adapter.detail(row['itemId'])
        adapter.ebay_get.assert_called_once_with(EBAY + 'item/v1%7C123456789%7C0')
        self.assertIsNone(self.normalize(detail)['availability'])
        adapter.ebay_get.reset_mock()
        with self.assertRaises(ProviderError):adapter.detail('https://evil.test/1')
        adapter.ebay_get.assert_not_called()
        adapter.ebay_get.return_value = {**row, 'itemId': 'v1|999|0'}
        with self.assertRaises(ProviderError):adapter.detail(row['itemId'])

    def test_lookup_search_then_three_details_deduplicates_and_reports_checks(self):
        adapter = Adapter(config('ebay_browse'), Mock())
        rows = []
        for number in range(4):
            row = ebay();row['itemId'] = f'v1|{123456789 + number}|0';rows.append(row)
        summaries = [{k: v for k, v in row.items() if k != 'estimatedAvailabilities'} for row in rows]
        adapter.search = Mock(return_value=(summaries, True))
        adapter.detail = Mock(side_effect=lambda identity: next(row for row in rows if row['itemId'] == identity))
        result = bounded_lookup(adapter, adapter.cfg, 3)
        self.assertEqual((result['success'], result['held'], result['failed']), (3, 0, 0))
        self.assertEqual(result['provider_detail_calls'], 3)
        self.assertEqual(result['backend_HTTP_requests'], 0)
        self.assertEqual(adapter.search.call_count, 1)
        self.assertTrue(all(all(product['checks'].values()) for product in result['products']))
        self.assertNotIn('SYNTHETIC merchant', str(result))
        self.assertNotIn('123456789', str(result))
        adapter.search.return_value = ([summaries[0], summaries[0], summaries[1]], False)
        adapter.detail.reset_mock()
        self.assertEqual(bounded_lookup(adapter, adapter.cfg, 3)['selected_count'], 2)
        self.assertEqual(adapter.detail.call_count, 2)

    def test_detail_failure_stops_further_requests(self):
        adapter = Adapter(config('ebay_browse'), Mock())
        adapter.search = Mock(return_value=([ebay(), {**ebay(), 'itemId': 'v1|222|0'}], False))
        adapter.detail = Mock(side_effect=ProviderError('provider_HTTP_error', 429))
        result = bounded_lookup(adapter, adapter.cfg, 3)
        self.assertEqual((result['failed'], result['held'], adapter.detail.call_count), (1, 1, 1))

    def test_sample_disables_auth_refresh_but_worker_default_preserved(self):
        http = Mock();http.state = {'requests': []};http.task_id = 'test'
        http.get_json.side_effect = ProviderError('provider_HTTP_error', 401)
        adapter = Adapter(config('ebay_browse'), http, retry_auth=False)
        adapter.oauth = Mock();adapter.oauth._get_access_token.return_value = 'SYNTHETIC_TOKEN'
        with self.assertRaises(ProviderError):adapter.ebay_get(EBAY + 'item_summary/search')
        self.assertEqual(adapter.oauth._get_access_token.call_count, 1)
        self.assertEqual(http.get_json.call_count, 1)
        self.assertTrue(Adapter(config('ebay_browse'), http).retry_auth)

    def test_idempotency_body_unchanged_for_existing_complete_offer(self):
        row = ebay();first = self.normalize(row)['observation']
        row['estimatedAvailabilities'][0]['estimatedAvailableQuantity'] = 4
        self.assertEqual(first, self.normalize(row)['observation'])
        row['conditionDescription'] = 'Native detail information'
        self.assertEqual(first, self.normalize(row)['observation'])

    def test_hold_reason_is_specific_and_summary_does_not_export_raw_data(self):
        adapter = Adapter(config('ebay_browse'), Mock())
        row = ebay();row['conditionId'] = '1500';row['condition'] = 'Open box'
        row.pop('estimatedAvailabilities')
        result, _ = inspect_item(adapter, row)
        self.assertIn('condition_subtype_not_representable_in_v2', result['reasons'])
        self.assertIn('missing_native_availability', result['reasons'])
        self.assertEqual(result['evidence']['condition_detail'], 'new_other_open_box')

    def test_production_plan_is_five_requests_with_no_network(self):
        cfg = config('ebay_browse')
        with patch.dict(os.environ, {'EBAY_CLIENT_ID': 'SYNTHETIC', 'EBAY_CLIENT_SECRET': 'SYNTHETIC'}):
            result = plan(cfg, 3)
        self.assertEqual(result['planned_HTTP_requests_max'], 5)
        self.assertEqual(result['planned_detail_requests_max'], 3)
        self.assertEqual(result['retries'], 0)
        self.assertEqual(result['environment'], 'Production')


class EbayCredentialsTests(unittest.TestCase):
    def test_explicit_loader_ignores_other_variables_and_rejects_conflicts_atomically(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            file = Path(directory) / '.env'
            file.write_text('EBAY_CLIENT_ID="SYNTHETIC-ID"\nEBAY_CLIENT_SECRET=SYNTHETIC-SECRET\nOTHER=ignored\n')
            load_ebay_env(file)
            self.assertNotIn('OTHER', os.environ)
            self.assertEqual(os.environ['EBAY_CLIENT_ID'], 'SYNTHETIC-ID')
            os.environ.pop('EBAY_CLIENT_ID');os.environ['EBAY_CLIENT_SECRET'] = 'CONFLICT'
            with self.assertRaises(ValueError):load_ebay_env(file)
            self.assertNotIn('EBAY_CLIENT_ID', os.environ)

    def test_duplicate_empty_or_invalid_values_do_not_modify_process(self):
        for text in ['EBAY_CLIENT_ID=x\nEBAY_CLIENT_ID=y\nEBAY_CLIENT_SECRET=z',
                     'EBAY_CLIENT_ID=\nEBAY_CLIENT_SECRET=z', 'EBAY_CLIENT_ID=x\nEBAY_CLIENT_SECRET="bad']:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
                file = Path(directory) / '.env';file.write_text(text)
                with self.assertRaises(ValueError):load_ebay_env(file)
                self.assertNotIn('EBAY_CLIENT_ID', os.environ)
