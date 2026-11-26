"""소병선 catalog DB(pgvector) 어댑터.

- PgVectorIndex: services/api/kkulpick/vectors.py 의 put()/candidates() 를 그대로 감쌉니다.
  추천 쪽 상품 id("source:listing#variant") <-> DB item_id(uuid) 는 app.offers 로 바꿉니다.
- PgCatalog: app.offers + app.catalog_items 를 읽어 CollectedProduct 로 돌려줍니다 (읽기 전용).
  상품 쓰기는 수집기 -> POST /internal/v2/crawl-runs/.../observations 경로로만 합니다.
- register_model(): 임베딩 모델 계약 + HNSW 인덱스 등록. **owner 계정**으로 한 번만 실행.

아직 DB 에 성분 저장 자리가 없어서 PgCatalog 가 돌려주는 상품은 성분이 비어 있습니다
(= 알레르기 사용자에게는 추천 안 됨). 식품-성분 테이블이 생기면 _INGREDIENTS_SQL 만 채우면 됩니다.

연결 예:
    import psycopg
    conn = psycopg.connect("host=127.0.0.1 port=5433 dbname=kkulpick_catalog user=kkulpick_catalog_app password=...",
                           autocommit=True)
"""
from __future__ import annotations

import os
from typing import Iterable, Sequence

from ..contracts import Candidate, CollectedProduct


def _vectors():
    try:  # api 컨테이너 안 (services/api 가 패키지 루트)
        from kkulpick import vectors
    except ImportError:  # 저장소 루트에서 실행
        from services.api.kkulpick import vectors
    return vectors


def max_staleness_hours() -> int:
    """RECO_MAX_STALENESS_HOURS: drop offers whose sale was not confirmed within this many hours.
    0 (default) keeps every available offer; stale ones are only flagged on cards by the API."""
    return max(0, int(os.getenv('RECO_MAX_STALENESS_HOURS', '0')))


def split_product_id(product_id: str) -> tuple[str, str, str]:
    """"demo:cookie-001#default" -> ("demo", "cookie-001", "default"). DB 는 variant_key 가 필수."""
    source, sep, rest = product_id.partition(":")
    if not sep or not source or not rest:
        raise ValueError(f"상품 id 형식 아님: {product_id!r}")
    listing, _, variant = rest.partition("#")
    return source, listing, variant


def join_product_id(source: str, listing: str, variant: str) -> str:
    return f"{source}:{listing}#{variant}" if variant else f"{source}:{listing}"


def register_model(owner_conn, model_id: str, embedder, target: str = "food",
                   input_template: str = "name | category | brand | description | 성분: ingredients",
                   revision: str = "main") -> None:
    """embedding_models 에 계약을 넣고 HNSW 인덱스를 만듦. 계약은 바꿀 수 없으니 바뀌면 새 model_id 로."""
    v = _vectors()
    v.register(owner_conn, v.Contract(model_id=model_id, target=target, encoder_name=embedder.name,
                                      revision=revision, dimensions=embedder.dimensions,
                                      input_template=input_template, query_prefix="", document_prefix="",
                                      normalize=True))
    owner_conn.execute("UPDATE app.embedding_models SET is_serving=true WHERE model_id=%s", (model_id,))


class PgVectorIndex:
    def __init__(self, conn, model_id: str):
        self.conn, self.model_id = conn, model_id
        self._v = _vectors()

    def _items(self, product_ids: Sequence[str]) -> dict[str, tuple[str, int]]:
        """product_id -> (item_id, content_version)."""
        keys = [split_product_id(p) for p in product_ids]
        if not keys:
            return {}
        rows = self.conn.execute(
            """SELECT o.source, o.source_listing_id, o.variant_key, i.item_id::text, i.content_version
               FROM app.offers o JOIN app.catalog_items i USING(item_id)
               WHERE (o.source, o.source_listing_id, o.variant_key) IN
                     (SELECT * FROM unnest(%s::text[], %s::text[], %s::text[]))""",
            ([k[0] for k in keys], [k[1] for k in keys], [k[2] or "default" for k in keys])).fetchall()
        found = {(s, l, v): (iid, ver) for s, l, v, iid, ver in rows}
        out = {}
        for pid, (s, l, v) in zip(product_ids, keys):
            hit = found.get((s, l, v or "default"))
            if hit:
                out[pid] = hit
        return out

    def upsert(self, items: Sequence[tuple[str, list[float]]]) -> None:
        ids = self._items([pid for pid, _ in items])
        missing = [pid for pid, _ in items if pid not in ids]
        if missing:
            raise KeyError(f"DB offers 에 없는 상품: {missing[:5]}")
        for pid, vec in items:
            item_id, version = ids[pid]
            self._v.put(self.conn, self.model_id, item_id, version, vec)

    def search(self, vector: list[float], limit: int) -> list[Candidate]:
        hours = max_staleness_hours()
        rows = self._v.candidates(self.conn, self.model_id, vector, limit, available_only=True,
                                  max_staleness_hours=hours)
        if not rows:
            return []
        # item 하나에 판매처(offer)가 여럿일 수 있음 -> 판매 중인 것 중 가장 싼 offer 로 대표
        reps = {iid: join_product_id(src, l, v) for iid, src, l, v in self.conn.execute(
            """SELECT DISTINCT ON (item_id) item_id::text, source, source_listing_id, variant_key
               FROM app.offers WHERE item_id = ANY(%s::uuid[]) AND availability='available'
                 AND (%s = 0 OR last_seen_at > now() - make_interval(hours => %s))
               ORDER BY item_id, price, offer_id""",
            ([str(r[0]) for r in rows], hours, hours)).fetchall()}
        return [Candidate(reps[str(iid)], round(1.0 - float(dist), 6)) for iid, dist in rows if str(iid) in reps]


_INGREDIENTS_SQL = """SELECT item_id::text, ingredients_raw, ingredients, allergen_notice_raw,
                             cross_contact_raw, allergens_declared
                      FROM app.foods WHERE item_id = ANY(%s::uuid[])"""


class PgCatalog:
    def __init__(self, conn, kind: str = "food"):
        if kind not in ("food", "product"):
            raise ValueError("kind 는 food | product")
        self.conn, self.kind = conn, kind

    def upsert(self, products: Iterable[CollectedProduct]) -> int:
        raise NotImplementedError("DB 상품 쓰기는 수집기 -> /internal/v2/crawl-runs/{run}/observations 로만")

    def name_matches(self, keywords: Sequence[str], limit: int = 20) -> list[str]:
        """이름에 검색어가 그대로 들어 있는 판매 중 상품(벡터 점수 보완용). 검색어가 없으면 빈 목록."""
        words = [w for w in keywords if w][:5]
        if not words:
            return []
        patterns = ['%' + ''.join('\\' + ch if ch in '\\%_' else ch for ch in w) + '%' for w in words]
        rows = self.conn.execute(
            """SELECT o.source, o.source_listing_id, o.variant_key FROM app.offers o JOIN app.catalog_items i USING(item_id)
               WHERE o.kind=%s AND o.availability='available' AND i.name ILIKE ANY(%s)
               ORDER BY o.price, o.offer_id LIMIT %s""", (self.kind, patterns, limit)).fetchall()
        return [join_product_id(*r) for r in rows]

    def all_ids(self) -> list[str]:
        rows = self.conn.execute("SELECT source, source_listing_id, variant_key FROM app.offers WHERE kind=%s "
                                 "ORDER BY offer_id", (self.kind,)).fetchall()
        return [join_product_id(*r) for r in rows]

    def offer_ids(self, product_ids: Sequence[str]) -> dict[str, str]:
        keys = [split_product_id(p) for p in product_ids]
        if not keys:
            return {}
        rows = self.conn.execute('''SELECT source,source_listing_id,variant_key,offer_id::text
            FROM app.offers WHERE kind=%s AND availability='available'
            AND (source,source_listing_id,variant_key) IN
              (SELECT * FROM unnest(%s::text[],%s::text[],%s::text[]))''',
            (self.kind, [k[0] for k in keys], [k[1] for k in keys], [k[2] or 'default' for k in keys])).fetchall()
        return {join_product_id(s, l, v): oid for s, l, v, oid in rows}

    def get_many(self, product_ids: Sequence[str]) -> dict[str, CollectedProduct]:
        keys = [split_product_id(p) for p in product_ids]
        if not keys:
            return {}
        rows = self.conn.execute(
            """SELECT o.source, o.source_listing_id, o.variant_key, i.name, i.description, o.price::text,
                      o.currency, o.current_url, o.price_observed_at,
                      o.condition, o.availability, o.last_checked_at,
                      i.brand, i.category, i.image_url,
                      f.ingredients_raw, f.ingredients, f.allergen_notice_raw,
                      f.cross_contact_raw, f.allergens_declared
               FROM app.offers o
               JOIN app.catalog_items i USING(item_id)
               LEFT JOIN app.foods f USING(item_id)
               WHERE o.kind=%s AND o.availability='available' AND (o.source, o.source_listing_id, o.variant_key) IN
                     (SELECT * FROM unnest(%s::text[], %s::text[], %s::text[]))""",
            (self.kind, [k[0] for k in keys], [k[1] for k in keys], [k[2] or "default" for k in keys])).fetchall()
        out = {}
        for (s, l, v, name, desc, price, cur, url, seen, cond, avail, checked,
             brand, cat, img_url, ing_raw, ing_list, notice_raw, cross_raw, declared) in rows:
            pid = join_product_id(s, l, v)
            ing = [str(x) for x in ing_list if str(x).strip()] if isinstance(ing_list, list) and ing_list else None
            dec = [str(x) for x in declared if str(x).strip()] if isinstance(declared, list) and declared else []
            out[pid] = CollectedProduct.from_dict({
                k: x for k, x in {"source": s, "source_listing_id": f"{l}#{v}" if v else l, "name": name,
                                  "description": desc, "category": cat or self.kind, "brand": brand,
                                  "image_url": img_url, "price": price, "currency": cur,
                                  "url": url, "collected_at": seen.isoformat() if seen else None,
                                  "condition": cond, "availability": avail,
                                  "checked_at": checked.isoformat() if checked else None,
                                  "ingredients_raw": ing_raw, "ingredients": ing,
                                  "allergen_notice_raw": notice_raw,
                                  "allergens_declared": dec or None,
                                  "cross_contact_raw": cross_raw}.items()
                if x is not None})
        # 요청한 id 철자(variant 생략 등) 그대로 돌려주기
        return {p: out[join_product_id(*(k[0], k[1], k[2] or "default"))] for p, k in zip(product_ids, keys)
                if join_product_id(k[0], k[1], k[2] or "default") in out}


class PgProfiles:  # pragma: no cover - member DB 프로필 연결은 다음 단계
    def __init__(self, conn):
        raise NotImplementedError("member DB 의 ingredient_filter(avoid/prefer) -> UserProfile 변환은 다음 단계")
