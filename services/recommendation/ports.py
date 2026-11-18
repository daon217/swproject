"""저장소·모델 인터페이스 (포트).

파이프라인은 이 인터페이스만 압니다. 지금은 adapters/local.py (JSON 파일) 구현을 쓰고,
소병선 DB가 확정되면 adapters/ 에 같은 메서드를 가진 클래스를 하나 더 만들면 됩니다.
새 구현은 tests/contract_suite.py 를 통과하면 그대로 갈아끼울 수 있습니다.
"""
from __future__ import annotations

from typing import Iterable, Protocol, Sequence, runtime_checkable

from .contracts import Candidate, CollectedProduct, UserProfile


@runtime_checkable
class CatalogRepository(Protocol):
    """수집 상품 저장소. 이후 catalog DB(catalog_items/foods/ingredients...)로 대체."""

    def upsert(self, products: Iterable[CollectedProduct]) -> int: ...
    def get_many(self, product_ids: Sequence[str]) -> dict[str, CollectedProduct]: ...
    def all_ids(self) -> list[str]: ...


@runtime_checkable
class ProfileRepository(Protocol):
    """사용자 프로필 저장소. 이후 member DB 로 대체."""

    def get(self, user_id: str) -> UserProfile | None: ...
    def save(self, profile: UserProfile) -> None: ...


@runtime_checkable
class VectorIndex(Protocol):
    """임베딩 저장·검색. 이후 services/api/kkulpick/vectors.py (pgvector) 로 대체."""

    def upsert(self, items: Sequence[tuple[str, list[float]]]) -> None: ...
    def search(self, vector: list[float], limit: int) -> list[Candidate]: ...


class Embedder(Protocol):
    name: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class Ranker(Protocol):
    """안전 판정을 통과한 후보만 받아서 고르고 이유를 붙임."""

    name: str

    def rank(self, profile: UserProfile, query: str, items: list[tuple[CollectedProduct, float]],
             top_k: int) -> list[tuple[str, str]]: ...  # [(product_id, reason)]
