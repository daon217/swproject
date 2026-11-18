"""소병선 DB 가 확정되면 채울 자리 (아직 미구현).

할 일:
1. PgCatalog: CollectedProduct <-> catalog DB 행 변환 (catalog_items/foods + 성분 연결 테이블).
   성분 연결·알레르기 분류 테이블은 아직 없으므로 스키마 확정 후 작성.
2. PgProfiles: member DB 의 프로필/알레르기 테이블 (아직 없음).
3. PgVectorIndex: services/api/kkulpick/vectors.py 의 put()/candidates() 를 감싸면 됨.
   candidates() 는 item_id(uuid)를 돌려주므로, product_id("source:listing_id") <-> item_id
   매핑을 catalog 쪽 source listing 테이블에서 조회해야 함.

각 클래스는 ports.py 의 Protocol 과 같은 메서드를 가져야 하고,
tests/contract_suite.py 의 check_* 함수를 통과해야 합니다.
"""
from __future__ import annotations


class PgCatalog:  # pragma: no cover - DB 확정 전
    def __init__(self, conn):
        raise NotImplementedError("catalog DB 스키마 확정 후 구현")


class PgProfiles:  # pragma: no cover - DB 확정 전
    def __init__(self, conn):
        raise NotImplementedError("member DB 스키마 확정 후 구현")


class PgVectorIndex:  # pragma: no cover - DB 확정 전
    def __init__(self, conn, model_id: str):
        raise NotImplementedError("vectors.candidates() 를 감싸고 item_id <-> product_id 매핑 추가")
