import http.server
import threading
from datetime import UTC, datetime, timedelta

import pytest

from services.recommendation.adapters.local import InMemoryVectorIndex, JsonCatalog
from services.recommendation.contracts import CollectedProduct, UserProfile
from services.recommendation.embedders import HashEmbedder
from services.recommendation.pipeline import Recommender
from services.recommendation.rankers import RuleRanker
from services.recommendation.used_check import (AVAILABLE, ENDED, UNKNOWN, HttpListingChecker, LiveStatus,
                                                verify_used)

PAGES = {
    "/ok": (200, '<script type="application/ld+json">{"offers":{"availability":"https://schema.org/InStock"}}</script>'),
    "/sold": (200, '<script type="application/ld+json">{"@graph":[{"offers":[{"availability":"SoldOut"}]}]}</script>'),
    "/reserved": (200, "<div class='badge'>예약중</div>"),
    "/plain": (200, "<html>상품 설명만 있음</html>"),
    "/gone": (410, ""),
    "/blocked": (403, ""),
    "/away": (302, ""),
}


@pytest.fixture(scope="module")
def server():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            code, body = PAGES.get(self.path, (404, ""))
            self.send_response(code)
            if code == 302:
                self.send_header("Location", "http://evil.example/x")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def used(i, url="https://x.test/p", **kw):
    return CollectedProduct.from_dict({"source": "u", "source_listing_id": i, "name": f"중고 {i}", "url": url,
                                       "condition": "used", "category": "product", **kw})


@pytest.mark.parametrize("path,status", [("/ok", AVAILABLE), ("/sold", ENDED), ("/reserved", ENDED),
                                         ("/plain", UNKNOWN), ("/gone", ENDED), ("/blocked", UNKNOWN),
                                         ("/missing", ENDED), ("/away", UNKNOWN)])
def test_http_checker(server, path, status):
    c = HttpListingChecker(["127.0.0.1"], schemes=("http",), timeout=2)
    assert c.check(used("a", server + path)).status == status


def test_http_checker_refuses_other_hosts_and_http():
    c = HttpListingChecker(["shop.test"])
    assert c.check(used("a", "https://other.test/p")).status == UNKNOWN
    assert c.check(used("a", "http://shop.test/p")).status == UNKNOWN


class FakeChecker:
    def __init__(self, status):
        self.status, self.calls = status, []

    def check(self, p):
        self.calls.append(p.product_id)
        return LiveStatus(p.product_id, self.status.get(p.product_id, UNKNOWN), "fake", "")


def test_verify_used_skips_new_fresh_and_stored_ended():
    now = datetime.now(UTC)
    fresh = used("fresh", availability="available", checked_at=(now - timedelta(minutes=2)).isoformat())
    stale = used("stale", availability="available", checked_at=(now - timedelta(hours=2)).isoformat())
    ended = used("ended", availability="ended")
    new = CollectedProduct.from_dict({"source": "n", "source_listing_id": "1", "name": "신품"})
    fc = FakeChecker({"u:stale": AVAILABLE})
    out = verify_used([fresh, stale, ended, new], fc)
    assert fc.calls == ["u:stale"]
    assert out["u:fresh"].status == AVAILABLE and out["u:ended"].status == ENDED and "n:1" not in out


def test_verify_used_times_out_as_unknown():
    import time

    class Slow:
        def check(self, p):
            time.sleep(1)
            return LiveStatus(p.product_id, AVAILABLE, "", "")

    assert verify_used([used("a")], Slow(), budget_s=0.1)["u:a"].status == UNKNOWN


def _rec(tmp_path, products, checker):
    cat = JsonCatalog(tmp_path)
    cat.upsert(products)
    r = Recommender(cat, InMemoryVectorIndex(None, "t"), HashEmbedder(), RuleRanker(), used_checker=checker)
    r.reindex()
    return r


def test_pipeline_used_rules(tmp_path):
    items = [used(str(i)) for i in range(6)] + [
        CollectedProduct.from_dict({"source": "n", "source_listing_id": "1", "name": "중고 아님 신품"}),
        CollectedProduct.from_dict({"source": "n", "source_listing_id": "2", "name": "품절 신품",
                                    "availability": "out_of_stock"})]
    fc = FakeChecker({f"u:{i}": AVAILABLE for i in range(6) if i != 1})
    r = _rec(tmp_path, items, fc)

    off = r.recommend(UserProfile("u"), "중고", top_k=8)
    assert all(not p.product_id.startswith("u:") for p in off.picks) and fc.calls == []
    assert any("중고 6건 숨김" in n for n in off.notes)
    assert "n:2" in {v.product_id for v in off.excluded}

    on = r.recommend(UserProfile("u", include_used=True), "중고", top_k=8)
    used_picks = [p.product_id for p in on.picks if p.product_id.startswith("u:")]
    assert len(used_picks) == 3 and "u:1" not in used_picks  # 최대 3개, 판매종료 제외
    assert any(v.product_id == "u:1" and "중고 재확인" in v.reasons[0] for v in on.excluded)


def test_food_never_shows_used(tmp_path):
    food_used = used("f", category="food")
    r = _rec(tmp_path, [food_used], FakeChecker({"u:f": AVAILABLE}))
    assert r.recommend(UserProfile("u", include_used=True), "중고").picks == []
