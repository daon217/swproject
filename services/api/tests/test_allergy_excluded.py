"""식품 추천이 알레르기로 비었을 때 화면에 이유를 넘기는지(DB 없이)."""
import asyncio

import pytest
from pydantic import ValidationError

from kkulpick.analyses import ResultMetadata, public_result


def result(metadata, domain="food"):
    row = {"analysis_id": "a", "state": "completed", "offer_ids": [], "selected_domain": domain,
           "page_session_id": "s", "page_revision": 1, "error_code": None,
           "result_metadata": ResultMetadata.model_validate(metadata).model_dump()}
    return asyncio.run(public_result(None, row, False))


def test_empty_food_result_explains_allergy_exclusions():
    out = result({"exclusions": {"allergen": 2, "unknown_ingredients": 5}})
    assert out["result_kind"] == "empty"
    assert out["allergy_excluded"] == {"allergen": 2, "unknown_ingredients": 5}


def test_no_reason_without_exclusions_or_for_products():
    assert result({})["allergy_excluded"] is None  # 예전에 저장된 결과(필드 없음)도 그대로
    assert result({"exclusions": {"allergen": 0, "unknown_ingredients": 0}})["allergy_excluded"] is None
    assert result({"exclusions": {"allergen": 1}}, domain="product")["allergy_excluded"] is None


def test_worker_cannot_send_unknown_or_negative_counts():
    with pytest.raises(ValidationError):
        ResultMetadata.model_validate({"exclusions": {"allergen": -1}})
    with pytest.raises(ValidationError):
        ResultMetadata.model_validate({"exclusions": {"other": 1}})
