"""DB 없이 추천을 돌려보는 명령줄 도구. 저장소 루트에서 실행:

  python -m services.recommendation.cli validate 수집파일.jsonl
  python -m services.recommendation.cli ingest 수집파일.jsonl
  python -m services.recommendation.cli profile services/recommendation/samples/profiles.sample.json
  python -m services.recommendation.cli recommend --user u-milk --query "아이 간식"
  python -m services.recommendation.cli import-observations 준서_observations.json
  python -m services.recommendation.cli --store pg --dsn "..." reindex   (DB+pgvector)
  python -m services.recommendation.cli pull-offers --api-base http://127.0.0.1:3000/backend --domain food

데이터 폴더는 --data (기본 .reco-data) 입니다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .adapters.local import InMemoryVectorIndex, JsonCatalog, JsonProfiles
from .adapters.offers_api import fetch_offers, observation_to_product, offer_to_product
from .contracts import CollectedProduct, ContractError, UserProfile
from .embedders import make_embedder
from .pipeline import Recommender
from .rankers import make_ranker


def read_jsonl(path: str):
    """(줄번호, 상품 또는 None, 오류목록) 을 차례로 돌려줌."""
    with open(path, encoding="utf-8") as f:
        for no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield no, CollectedProduct.from_dict(json.loads(line)), []
            except json.JSONDecodeError as e:
                yield no, None, [f"JSON 오류: {e}"]
            except ContractError as e:
                yield no, None, e.errors


def cmd_validate(a) -> int:
    ok = bad = no_info = 0
    for no, p, errs in read_jsonl(a.file):
        if errs:
            bad += 1
            print(f"{a.file}:{no}: " + " / ".join(errs))
        else:
            ok += 1
            if not (p.ingredients_raw or p.ingredients or p.allergen_notice_raw or p.allergens_declared):
                no_info += 1
                print(f"{a.file}:{no}: 경고: 성분 정보 없음 → 알레르기 사용자에게 추천 안 됨 ({p.product_id})")
    print(f"통과 {ok}건, 실패 {bad}건, 성분없음 {no_info}건")
    return 1 if bad else 0


def _pg_connect(dsn: str | None):
    import psycopg  # DB 모드에서만 필요

    if not dsn:
        raise SystemExit("DB 접속 문자열 필요: --dsn 또는 환경변수 KKULPICK_CATALOG_DSN")
    return psycopg.connect(dsn, autocommit=True)


def _recommender(a) -> Recommender:
    emb = make_embedder(a.embedder)
    if a.store == "pg":
        from .adapters.postgres import PgCatalog, PgVectorIndex

        conn = _pg_connect(a.dsn)
        return Recommender(PgCatalog(conn, a.domain_kind), PgVectorIndex(conn, a.model_id), emb, make_ranker(a.ranker))
    return Recommender(JsonCatalog(a.data), InMemoryVectorIndex(a.data, emb.name), emb, make_ranker(a.ranker))


def cmd_register_model(a) -> int:
    """임베딩 모델 계약 + HNSW 인덱스 등록. owner 계정 DSN 으로 한 번만."""
    from .adapters.postgres import register_model

    emb = make_embedder(a.embedder)
    with _pg_connect(a.owner_dsn) as conn:
        register_model(conn, a.model_id, emb, target=a.domain_kind)
    print(f"모델 등록: {a.model_id} ({emb.name}, {emb.dimensions}차원, {a.domain_kind})")
    return 0


def cmd_reindex(a) -> int:
    """저장소의 상품 전체를 다시 임베딩 (DB 모드에서는 pgvector 에 저장)."""
    rec = _recommender(a)
    ids = rec.catalog.all_ids()
    done = 0
    for i in range(0, len(ids), 64):
        done += rec.reindex(ids[i:i + 64])
    print(f"임베딩 {done}건 ({rec.embedder.name}) → {a.store}")
    return 0


def cmd_ingest(a) -> int:
    good, bad = [], 0
    for no, p, errs in read_jsonl(a.file):
        if errs:
            bad += 1
            print(f"{a.file}:{no}: 건너뜀: " + " / ".join(errs), file=sys.stderr)
        else:
            good.append(p)
    if a.store == "pg":
        raise SystemExit("pg 모드에서는 상품을 직접 넣지 않음: 수집기 -> API 로 넣고 reindex 실행")
    rec = _recommender(a)
    rec.catalog.upsert(good)
    n = rec.reindex([p.product_id for p in good])
    print(f"저장 {len(good)}건, 임베딩 {n}건 ({rec.embedder.name}), 실패 {bad}건 → {a.data}")
    return 1 if bad and not good else 0


def _store(a, products: list, bad: int, label: str) -> int:
    if a.store == "pg":
        raise SystemExit("pg 모드에서는 상품을 직접 넣지 않음: 수집기 -> API 로 넣고 reindex 실행")
    rec = _recommender(a)
    rec.catalog.upsert(products)
    n = rec.reindex([p.product_id for p in products])
    no_info = sum(1 for p in products if not (p.ingredients_raw or p.ingredients or p.allergen_notice_raw or p.allergens_declared))
    print(f"{label}: 저장 {len(products)}건, 임베딩 {n}건 ({rec.embedder.name}), 실패 {bad}건, "
          f"성분없음 {no_info}건(알레르기 사용자에게는 추천 안 됨) → {a.data}")
    return 1 if bad and not products else 0


def _convert(rows, fn, *args):
    good, bad = [], 0
    for i, row in enumerate(rows, 1):
        try:
            good.append(fn(row, *args))
        except (ContractError, KeyError, TypeError) as e:
            bad += 1
            print(f"{i}번째 건너뜀: {e}", file=sys.stderr)
    return good, bad


def cmd_import_observations(a) -> int:
    """수집기 Observation v2 파일(JSON 배열 또는 JSONL)을 바로 넣음."""
    text = Path(a.file).read_text(encoding="utf-8").strip()
    rows = json.loads(text) if text.startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]
    if a.domain != "all":
        rows = [r for r in rows if r.get("selected_domain") == a.domain]
    good, bad = _convert(rows, observation_to_product)
    return _store(a, good, bad, "observation")


def cmd_pull_offers(a) -> int:
    """백엔드 GET /v2/offers 에서 읽어서 넣음 (읽기 전용, 키 필요 없음)."""
    good, bad = _convert(fetch_offers(a.api_base, a.domain), offer_to_product, a.domain)
    return _store(a, good, bad, f"/v2/offers {a.domain}")


def cmd_profile(a) -> int:
    data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    repo = JsonProfiles(a.data)
    for d in data if isinstance(data, list) else [data]:
        repo.save(UserProfile.from_dict(d))
        print(f"프로필 저장: {d['user_id']}")
    return 0


def cmd_recommend(a) -> int:
    profile = JsonProfiles(a.data).get(a.user)
    if profile is None:
        print(f"프로필 없음: {a.user} (먼저 profile 명령으로 저장)", file=sys.stderr)
        return 2
    rec = _recommender(a)
    if a.live_check:
        from .used_check import HttpListingChecker

        hosts = os.getenv("CATALOG_URL_HOSTS", "").split(",")
        if not any(h.strip() for h in hosts):
            print("--live-check 에는 환경변수 CATALOG_URL_HOSTS(허용 판매처 호스트) 필요", file=sys.stderr)
            return 2
        rec.used_checker = HttpListingChecker(hosts)
    result = rec.recommend(profile, a.query, top_k=a.top_k, candidate_limit=a.candidates)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reco")
    ap.add_argument("--data", default=".reco-data", help="로컬 데이터 폴더")
    ap.add_argument("--embedder", default="hash", help="hash | st | st:<모델명>")
    ap.add_argument("--ranker", default="auto", help="auto(키 있으면 claude) | rule | claude | local(LOCAL_LLM_BASE_URL)")
    ap.add_argument("--store", default="local", choices=["local", "pg"], help="local(JSON) | pg(catalog DB+pgvector)")
    ap.add_argument("--dsn", default=os.getenv("KKULPICK_CATALOG_DSN"), help="pg 모드 app 계정 접속 문자열")
    ap.add_argument("--model-id", default=os.getenv("KKULPICK_EMBEDDING_MODEL_ID", "food-hash-384-v1"),
                    help="embedding_models.model_id")
    ap.add_argument("--kind", dest="domain_kind", default="food", choices=["food", "product"])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("validate"); s.add_argument("file"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("ingest"); s.add_argument("file"); s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("profile"); s.add_argument("file"); s.set_defaults(fn=cmd_profile)
    s = sub.add_parser("import-observations"); s.add_argument("file")
    s.add_argument("--domain", default="all", choices=["all", "food", "product"])
    s.set_defaults(fn=cmd_import_observations)
    s = sub.add_parser("pull-offers")
    s.add_argument("--api-base", default=os.getenv("KKULPICK_API_BASE", "http://127.0.0.1:3000/backend"))
    s.add_argument("--domain", default="food", choices=["food", "product"])
    s.set_defaults(fn=cmd_pull_offers)
    s = sub.add_parser("register-model")
    s.add_argument("--owner-dsn", default=os.getenv("KKULPICK_CATALOG_OWNER_DSN"))
    s.set_defaults(fn=cmd_register_model)
    s = sub.add_parser("reindex"); s.set_defaults(fn=cmd_reindex)
    s = sub.add_parser("recommend")
    s.add_argument("--user", required=True); s.add_argument("--query", default="")
    s.add_argument("--top-k", type=int, default=5); s.add_argument("--candidates", type=int, default=30)
    s.add_argument("--live-check", action="store_true", help="중고 후보를 판매 페이지에서 실시간 재확인")
    s.set_defaults(fn=cmd_recommend)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
