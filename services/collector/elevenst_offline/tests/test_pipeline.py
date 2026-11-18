import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from ..parser import parse_listing, parse_snapshot, SchemaChanged
from ..collector import OfflineCollector, writer_lock
from ..validation import price, safe_url
from ..live import require_live_transport

T0 = '2026-11-18T00:00:00+00:00'
T1 = '2026-11-18T01:00:00+00:00'


def item(pid='fixture-1', option='OPT-1', **values):
    row = dict(id=pid, title='Synthetic test product', finalPrc='1,234', selPrc='9,999',
               linkUrl='https://m.11st.co.kr/products/' + pid,
               imageUrl='https://cdn.011st.com/image/synthetic.jpg', currency='KRW',
               sellerName='Synthetic shop', categoryName='Test category')
    if option is not None:
        row['optionId'] = option
    row.update(values)
    return row


def payload(items=None, page=1, next_page=None):
    return json.dumps({'data': {'products': [item()] if items is None else items,
                               'pagination': {'pageNo': page, 'hasMore': next_page is not None, 'nextPageNo': next_page}}})


def test_normalizes_common_fields_and_identity_evidence():
    row = parse_listing(payload(), T0)[0][0]
    assert (row['source'], row['source_listing_id'], row['variant_key']) == ('elevenst', 'fixture-1', 'OPT-1')
    assert row['price'] == row['unit_price'] == 1234
    assert row['seller'] == 'Synthetic shop' and row['category'] == 'Test category'
    assert row['price_field'] == 'finalPrc' and row['observed_at'] == T0
    assert row['storage_permission_status'] == row['reuse_permission_status'] == 'unverified'
    assert row['identity_evidence']['variant_key']['value'] == 'OPT-1'


@pytest.mark.parametrize('bad', [True, False, 12.9, float('nan'), float('inf'), -1, '-123', '12abc34', '1.99', '1e3', '1,23', '12원', {}, []])
def test_abnormal_price_cannot_be_coerced(bad):
    assert price(bad) is None
    rows, meta = parse_listing(payload([item(finalPrc=bad, selPrc='')]))
    assert rows == [] and meta['rejected']


def test_invalid_final_price_falls_back_to_valid_sale_price():
    row = parse_listing(payload([item(finalPrc='broken', selPrc='500')]))[0][0]
    assert row['price'] == 500 and row['price_field'] == 'selPrc'


@pytest.mark.parametrize('url', [
    'http://m.11st.co.kr/products/fixture-1', 'https://m.11st.co.kr.evil.test/products/fixture-1',
    'https://evil.test/products/fixture-1', 'https://user:pass@m.11st.co.kr/products/fixture-1',
    'https://m.11st.co.kr:444/products/fixture-1', 'https://m.11st.co.kr/products/other',
    'https://m.11st.co.kr/redirect?to=elsewhere', 'https://m.11st.co.kr/products/fixture-1%0a',
    'https://m.11st.co.kr/products/fixture-1\n',
])
def test_product_url_origin_path_and_native_id_are_checked(url):
    rows, meta = parse_listing(payload([item(linkUrl=url)]))
    assert rows == [] and meta['rejected']


@pytest.mark.parametrize('url', ['http://cdn.011st.com/a.jpg', 'https://evil.test/a.jpg',
                               'https://cdn.011st.com.evil.test/a.jpg', 'https://x@cdn.011st.com/a.jpg'])
def test_image_allowlist(url):
    assert parse_listing(payload([item(imageUrl=url)]))[0] == []


def test_legacy_purchase_route_and_protocol_relative_CDN():
    row = parse_listing(payload([item(linkUrl='https://www.11st.co.kr/product/SellerProductDetail.tmall?prdNo=fixture-1',
                                     imageUrl='//cdn.011st.com/image/a.jpg')]))[0][0]
    assert row['image_url'].startswith('https://cdn.011st.com/')


@pytest.mark.parametrize('values', [{'id': True}, {'id': {}}, {'id': 'x', 'productNo': 'different'},
                                   {'optionId': True}, {'optionId': 'one', 'optionNo': 'two'}])
def test_native_identifier_conflict_quarantines_instead_of_fabricating(values):
    rows, meta = parse_listing(payload([item(**values)]))
    assert rows == [] and meta['rejected']


def test_unknown_options_and_confirmed_absence_are_distinct():
    unknown = parse_listing(payload([item(option=None)]))[0][0]
    none = parse_listing(payload([item(option=None, hasOptions=False, options=[])]))[0][0]
    assert unknown['variant_key'] is None and unknown['identity_status'] == 'quarantine_required'
    assert none['variant_key'] is None and none['variant_scope'] == 'confirmed_none'
    assert none['identity_status'] == 'verified_native_tuple'


def test_options_not_deduped_by_product_id_or_name():
    rows, meta = parse_listing(payload([item(), item(title='renamed'), item(option='OPT-2')]))
    assert len(rows) == 2 and meta['duplicate_items'] == 1
    assert rows[0]['variant_key'] != rows[1]['variant_key']


@pytest.mark.parametrize('body', ['<html>blocked</html>', '{}', '[]', '{"data":{"unexpected":1}}'])
def test_schema_drift_is_not_successful_empty_collection(body):
    with pytest.raises(SchemaChanged):
        parse_listing(body)


def test_empty_pagination_and_non_advancing_page():
    rows, meta = parse_listing(payload([], page=2))
    assert rows == [] and meta['native_page'] == 2 and meta['next_page'] is None
    with pytest.raises(SchemaChanged):
        parse_listing(payload(next_page=1))


def test_resume_dedup_and_native_next_page(tmp_path):
    body = payload([item(), item('fixture-2')], next_page=2)
    first = OfflineCollector(tmp_path).replay(body, max_items=1)
    assert first['cursor'] == 1 and not first['complete']
    second = OfflineCollector(tmp_path).replay(body)
    assert second['resumed_from'] == 1 and second['new_listing_ids'] == 1
    assert second['complete'] and second['next_page'] == 2
    again = OfflineCollector(tmp_path).replay(body)
    assert again['processed'] == again['new_listing_ids'] == 0
    different_page = OfflineCollector(tmp_path).replay(payload(page=2))
    assert different_page['new_listing_ids'] == 0 and different_page['known_offers'] == 1
    assert OfflineCollector(tmp_path).status()['unique_listing_ids'] == 2


def test_newer_price_and_name_keep_identity_and_stale_response_cannot_replace(tmp_path):
    collector = OfflineCollector(tmp_path)
    collector.replay(payload(), observed_at=T0)
    result = collector.replay(payload([item(finalPrc='100', title='Renamed')]), observed_at=T1)
    assert result['known_offers'] == 1 and result['new_listing_ids'] == 0
    collector.replay(payload([item(finalPrc='1')]), observed_at=T0)
    row = next(iter(collector.records.values()))
    assert len(collector.records) == 1 and row['price'] == 100 and row['observed_at'] == T1


def test_checkpoint_contains_only_identity_control_metadata(tmp_path):
    OfflineCollector(tmp_path).replay(payload(), observed_at=T0)
    raw = (tmp_path / 'checkpoint.json').read_text(encoding='utf-8')
    for content in ('Synthetic', '1234', 'https://', 'product_name', 'image_url', 'seller', 'category', 'finalPrc'):
        assert content not in raw
    assert 'fixture-1' in raw and 'OPT-1' in raw


def test_atomic_write_failure_preserves_checkpoint_and_memory(tmp_path, monkeypatch):
    collector = OfflineCollector(tmp_path)
    collector.replay(payload(), observed_at=T0)
    before = collector.path.read_bytes()
    module = importlib.import_module(OfflineCollector.__module__)
    with monkeypatch.context() as scoped:
        scoped.setattr(module.os, 'replace', lambda *_: (_ for _ in ()).throw(OSError('synthetic failure')))
        with pytest.raises(OSError):
            collector.replay(payload([item('fixture-2')]), observed_at=T1)
    assert collector.path.read_bytes() == before and len(collector.records) == 1
    recovered = OfflineCollector(tmp_path).replay(payload([item('fixture-2')]), observed_at=T1)
    assert recovered['new_listing_ids'] == 1
    assert not list(tmp_path.glob('*.tmp'))


def test_writer_lock_blocks_concurrent_checkpoint_writer(tmp_path):
    with writer_lock(tmp_path):
        with pytest.raises(OSError):
            OfflineCollector(tmp_path).replay(payload())
    assert not (tmp_path / 'checkpoint.json').exists()


def test_corrupt_checkpoint_is_preserved(tmp_path):
    target = tmp_path / 'checkpoint.json'
    target.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        OfflineCollector(tmp_path).replay(payload())
    assert target.read_text(encoding='utf-8') == '{broken'


def test_dry_run_status_live_have_no_writes_or_network(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *_: pytest.fail('network forbidden'))
    directory = tmp_path / 'absent'
    collector = OfflineCollector(directory)
    assert collector.status()['live_enabled'] is False
    assert collector.replay(payload(), dry_run=True)['processed'] == 1
    with pytest.raises(PermissionError):
        require_live_transport()
    assert not directory.exists() and collector.records == {}


def test_snapshot_provenance_and_unconfirmed_option_retained_in_quarantine():
    original = dict(source='elevenst', product_id='fixture-1', product_name='Archived', price=500,
                    product_url='https://m.11st.co.kr/products/fixture-1', image_url='https://cdn.011st.com/a.jpg',
                    collected_at=T0, variant_key='unproven')
    body = json.dumps([original, dict(source='other')])
    row = parse_snapshot(body)[0][0]
    assert row['source_listing_id'] == original['product_id'] and row['observed_at'] == T0
    assert row['variant_key'] is None and row['identity_status'] == 'quarantine_required'
    assert row['evidence']['raw_internal_response_available'] is False
    assert row['currency'] is None and row['condition'] is None


def test_timestamp_must_include_timezone():
    with pytest.raises(ValueError):
        parse_listing(payload(), '2026-11-18')


def test_independent_cli(tmp_path):
    source = tmp_path / 'synthetic.json'
    source.write_text(payload(), encoding='utf-8')
    module = __package__.rsplit('.tests', 1)[0]
    root = Path(__file__).resolve().parents[4]
    # Full repo package name when running the installed integration.
    command = [sys.executable, '-B', '-m', 'services.collector.elevenst_offline', '--state-dir', str(tmp_path / 'state')]
    for args in (['--status'], ['--input', str(source), '--dry-run']):
        result = subprocess.run(command + args, cwd=root, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert 'Synthetic' not in result.stdout
    live = subprocess.run(command + ['--live'], cwd=root, capture_output=True, text=True)
    assert live.returncode == 2 and not (tmp_path / 'state').exists()


def test_common_contract_compatible_with_domeggook_validator():
    from services.collector.domeggook_live.product_contract import normalize
    row = parse_listing(payload(), T0)[0][0]
    normalized = normalize(row, source='elevenst')
    assert normalized['product_id'] == 'fixture-1' and normalized['variant_key'] == 'OPT-1'
