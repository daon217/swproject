from crawler import rank, keep, classify, to_krw, load_sites, parse_product

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
    sites = load_sites()
    assert len(sites) >= 50 and len({h for _, h in sites}) == len(sites)  # 50곳 이상, 도메인 중복 없음


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


def test_rank_prefers_product_ids():
    urls = ["https://x.com/about", "https://x.com/Product/Category/Display/001001046", "https://x.com/product/pod/main", "https://x.com/product/goods/199633047"]
    assert sorted(urls, key=rank)[0].endswith("199633047")


def test_embedded_json():
    html = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"goods":{"goodsName":"감자칩","salePrice":"1,500"}}}}</script>'
    p = parse_product(html, "u")
    assert p["name"] == "감자칩" and p["price"] == 1500 and p["source"] == "embedded"
    html2 = '<script>window.__INITIAL_STATE__ = {"item":{"title":"컵","price":3000}};</script>'
    assert parse_product(html2, "u")["price"] == 3000
