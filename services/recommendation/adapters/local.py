"""DB 없이 쓰는 로컬 구현. 데이터는 폴더 하나(기본 .reco-data/)에 JSON 으로 저장됩니다.

이 폴더를 압축해서 주고받으면 두 사람이 같은 데이터로 테스트할 수 있습니다.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

from ..contracts import Candidate, CollectedProduct, UserProfile


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class JsonCatalog:
    def __init__(self, root: str | Path):
        self.path = Path(root) / "products.json"
        raw = _read_json(self.path, {})
        self._items = {k: CollectedProduct.from_dict(v) for k, v in raw.items()}

    def upsert(self, products: Iterable[CollectedProduct]) -> int:
        n = 0
        for p in products:
            self._items[p.product_id] = p
            n += 1
        _write_json(self.path, {k: v.to_dict() for k, v in sorted(self._items.items())})
        return n

    def get_many(self, product_ids: Sequence[str]) -> dict[str, CollectedProduct]:
        return {i: self._items[i] for i in product_ids if i in self._items}

    def all_ids(self) -> list[str]:
        return sorted(self._items)


class JsonProfiles:
    def __init__(self, root: str | Path):
        self.path = Path(root) / "profiles.json"
        raw = _read_json(self.path, {})
        self._items = {k: UserProfile.from_dict(v) for k, v in raw.items()}

    def get(self, user_id: str) -> UserProfile | None:
        return self._items.get(user_id)

    def save(self, profile: UserProfile) -> None:
        self._items[profile.user_id] = profile
        _write_json(self.path, {k: v.to_dict() for k, v in sorted(self._items.items())})


class InMemoryVectorIndex:
    """전수 코사인 검색. 수천 건까지는 충분히 빠름. model 이 바뀌면 파일도 분리됨."""

    def __init__(self, root: str | Path | None, model_name: str):
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in model_name)
        self.path = Path(root) / f"vectors.{safe}.json" if root else None
        self._vecs: dict[str, list[float]] = _read_json(self.path, {}) if self.path else {}

    def upsert(self, items: Sequence[tuple[str, list[float]]]) -> None:
        for pid, vec in items:
            if not vec or not all(math.isfinite(v) for v in vec):
                raise ValueError(f"잘못된 벡터: {pid}")
            self._vecs[pid] = list(vec)
        if self.path:
            _write_json(self.path, self._vecs)

    def search(self, vector: list[float], limit: int) -> list[Candidate]:
        if not 1 <= limit <= 100:
            raise ValueError("limit 은 1~100")
        qn = math.sqrt(sum(v * v for v in vector)) or 1.0
        scored = []
        for pid, vec in self._vecs.items():
            if len(vec) != len(vector):
                continue
            dn = math.sqrt(sum(v * v for v in vec)) or 1.0
            scored.append(Candidate(pid, sum(a * b for a, b in zip(vector, vec)) / (qn * dn)))
        scored.sort(key=lambda c: (-c.score, c.product_id))
        return scored[:limit]
