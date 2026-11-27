from services.collector.homepage_crawler.crawler import keep, classify, to_krw, load_sites, parse_product

JSONLD = '<script type="application/ld+json">{"@type":"Product","name":"A","offers":{"@type":"Offer","price":"1,200","priceCurrency":"KRW"}}</script>'
AGG = '<script type="application/ld+json">{"@graph":[{"@type":"Product","name":"B","offers":{"@type":"AggregateOffer","lowPrice":"10","highPrice":"20"}}]}</script>'
OG = '<meta property="og:type" content="product"><meta property="og:title" content="C"><meta property="product:price:amount" content="500">'


def test_jsonld():
    assert parse_product(JSONLD, "u")["price"] == 1200


def test_aggregate_not_collapsed():
    p = parse_product(AGG, "u")
    assert p["price"] is None and (p["price_low"], p["price_high"]) == (10, 20)


def test_og_and_none():
    assert parse_product(OG, "u")["price"] == 500
    assert parse_product("<html></html>", "u") is None


def test_sites_loaded():
    assert len(load_sites()) == 37


def test_classify():
    assert classify("크림", {"name": "Nike 신발", "category": "shoes"}) == dict(kind="상품", channel="일반", review=None)
    assert classify("알리익스프레스", {"name": "비타민C"})["kind"] == "식품"
    assert classify("당근", {"name": "신라면 미개봉 5개"})["review"] is None
    assert classify("당근", {"name": "신라면 5개"})["review"]
    assert classify("당근", {"name": "의자"})["kind"] == "상품"


def test_to_krw():
    assert to_krw({"price": 10, "currency": "USD"})["price"] == 14000
    r = to_krw({"price": 5, "currency": "XYZ"})
    assert r["price"] is None and r["review"]
    assert to_krw({"price": None, "price_low": 1, "price_high": 2, "currency": "KRW"})["price_low"] == 1


def test_keep():
    assert keep({"kind": "식품", "allergen_status": "read"})
    assert keep({"kind": "식품", "allergen_status": "read_empty"})
    assert not keep({"kind": "식품", "allergen_status": "image_only"})
    assert not keep({"kind": "식품", "allergen_status": "unreadable"})
    assert keep({"kind": "상품", "allergen_status": "unreadable"})



from types import SimpleNamespace
import psycopg
import pytest
from services.collector.homepage_crawler import crawler as C


class FakeConn:
    closed = False
    def __init__(self, alive=True):
        self.alive = alive
    def execute(self, q):
        if not self.alive:
            raise psycopg.OperationalError("server closed the connection")
    def commit(self): pass
    def rollback(self): pass


def test_watch_survives_site_error(monkeypatch):
    seen = []
    def fake(name, home, max_pages, delay):
        seen.append(name)
        if name == "A":
            raise RuntimeError("boom")
        return "ok", [], 1
    monkeypatch.setattr(C, "crawl_site", fake)
    a = SimpleNamespace(dry_run=True, watch=True, max_pages=1, delay=0)
    C.run_cycle([("A", "https://a"), ("B", "https://b")], a, None)
    assert seen == ["A", "B"]  # A가 터져도 B까지 돈다
    a.watch = False
    with pytest.raises(RuntimeError):  # 한 번만 돌 때는 오류를 숨기지 않는다
        C.run_cycle([("A", "https://a")], a, None)


def test_rest_after_100_saved(monkeypatch):
    rows = [{"kind": "상품"}] * 60
    monkeypatch.setattr(C, "crawl_site", lambda *x: ("ok", rows, 1))
    monkeypatch.setattr(C, "save", lambda *x: None)
    naps = []
    monkeypatch.setattr(C.time, "sleep", naps.append)
    a = SimpleNamespace(dry_run=False, watch=True, max_pages=1, delay=0)
    left = C.run_cycle([("A", "u"), ("B", "u"), ("C", "u")], a, FakeConn())
    assert naps == [600] and left == 60  # 60+60=120에서 한 번 쉬고, 다시 60부터


def test_db_lost_stops_before_crawling(monkeypatch):
    called = []
    monkeypatch.setattr(C, "crawl_site", lambda *x: called.append(1))
    a = SimpleNamespace(dry_run=False, watch=True, max_pages=1, delay=0)
    with pytest.raises(C.DBLost):
        C.run_cycle([("A", "u")], a, FakeConn(alive=False))
    assert called == []


def test_db_lost_during_save_stops(monkeypatch):
    monkeypatch.setattr(C, "crawl_site", lambda *x: ("ok", [{"kind": "상품"}], 1))
    def boom(*x): raise psycopg.OperationalError("lost")
    monkeypatch.setattr(C, "save", boom)
    a = SimpleNamespace(dry_run=False, watch=True, max_pages=1, delay=0)
    with pytest.raises(C.DBLost):
        C.run_cycle([("A", "u"), ("B", "u")], a, FakeConn())



def test_canonical_url():
    from services.collector.homepage_crawler.crawler import canonical_url
    u = "https://www.yes24.com/product/goods/1?ReviewYn=Y"
    assert canonical_url('<link rel="canonical" href="https://www.yes24.com/product/goods/1">', u) == "https://www.yes24.com/product/goods/1"
    assert canonical_url('<link rel="canonical" href="https://evil.com/x">', u) == u
    assert canonical_url("<html></html>", u) == u
