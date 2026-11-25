"""Minimal ProductCandidate shape reused from crawler_engine.models."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProductCandidate:
    product_name: str | None = None
    price_text: str | None = None
    price: int | None = None
    currency: str = 'KRW'
    source: str | None = None
    seller: str | None = None
    condition: str | None = None
    country: str = 'KR'
    product_url: str | None = None
    image_url: str | None = None
    description: str | None = None
    confidence: float = 0
    raw: dict[str, Any] = field(default_factory=dict)
