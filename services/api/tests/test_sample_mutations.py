"""One-at-a-time mutations of a sanitized, real-crawl-shaped sample.

The original uploaded 300 records are never modified or committed. This fixture
retains the first record's field shape, currency and price; identity/name/URL are
synthetic. These tests verify merging, not the truth of a shop's price or stock.
"""
import copy
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from kkulpick.api import app
from test_database import pg

pytestmark = pytest.mark.skipif(
    os.getenv("CATALOG_INTEGRATION") != "1",
    reason="requires disposable migrated PostgreSQL",
)

# Each case starts from a fresh baseline and changes only the stated input.
CASES = [
    ("exact_replay", {}, 200, None, {}),
    ("reused_key_changed_price", {"price": "2.5"}, 409, None, {}),
    ("newer_price", {"price": "2.5"}, 201, "updated", {"price": Decimal("2.5")}),
    ("moved_url", {"url": "https://store.example.test/moved"}, 201, "updated",
     {"current_url": "https://store.example.test/moved"}),
    ("out_of_stock", {"availability": "out_of_stock"}, 201, "updated", {"availability": "out_of_stock"}),
    ("sale_ended", {"availability": "ended"}, 201, "updated", {"availability": "ended"}),
    ("used_condition", {"condition": "used"}, 201, "updated", {"condition": "used"}),
    ("unknown_keeps_known_condition", {"condition": "unknown"}, 201, "unchanged", {}),
    ("renamed", {"name": "Renamed sample"}, 201, "updated", {"name": "Renamed sample"}),
    ("description_added", {"description": "New detail"}, 201, "updated", {"description": "New detail"}),
    ("older_price", {"price": "0.5"}, 201, "stale", {}),
    ("same_time_conflict", {"price": "2.5"}, 201, "quarantined", {}),
    ("newer_identical_values", {}, 201, "unchanged", {}),
    ("negative_price", {"price": "-1"}, 422, None, {}),
    ("numeric_price_not_string", {"price": 2.5}, 422, None, {}),
    ("invalid_currency_format", {"currency": "aud"}, 422, None, {}),
    ("missing_paired_currency", {}, 422, None, {}),
    ("invalid_availability", {"availability": "selling"}, 422, None, {}),
    ("unallowed_url_host", {"url": "https://unapproved.example/product"}, 422, None, {}),
    ("missing_identity", {"source_listing_id": None}, 201, "quarantined", {}),
    ("presence_mismatch", {}, 422, None, {}),
    ("future_timestamp", {}, 422, None, {}),
    ("timezone_missing", {}, 422, None, {}),
    ("timeout", {}, 201, "failed", {}),
    ("blocked", {}, 201, "failed", {}),
    ("not_found", {}, 201, "updated", {"availability": "suspect"}),
    ("omitted_optional_fields", {"price": "2.5"}, 201, "updated", {"price": Decimal("2.5")}),
    ("clear_description_explicitly", {"description": None}, 201, "updated", {"description": None}),
    ("new_variant", {"variant_key": "sample-option-2"}, 201, "created", {}),
    ("unknown_field", {"unexpected": "value"}, 422, None, {}),
    ("large_but_valid_price", {"price": "99999"}, 201, "quarantined", {}),
    ("unknown_three_letter_currency", {"currency": "ZZZ"}, 422, None, {}),
    ("domain_identity_conflict", {"selected_domain": "food"}, 201, "quarantined", {}),
]


@pytest.mark.parametrize("case,patch,status,kind,changes", CASES, ids=[c[0] for c in CASES])
def test_sample_mutation(case, patch, status, kind, changes):
    start = datetime.now(UTC) - timedelta(days=2)
    source = "mutation_" + uuid4().hex
    baseline = {
        "schema_version": 2, "source": source,
        "observed_at": start.isoformat(), "result": "success",
        "selected_domain": "product", "source_listing_id": "sample-product-1",
        "variant_key": "sample-option-1", "condition": "new",
        "name": "Sample socket header", "price": "1.1", "currency": "AUD",
        "availability": "available",
        "url": "https://store.example.test/products/sample/default-title",
        "field_presence": ["name", "price", "currency", "availability", "url"],
        "observation_key": "baseline",
    }
    if case in {"omitted_optional_fields", "clear_description_explicitly"}:
        baseline.update(description="Keep this detail", shipping_fee="0.5")
        baseline["field_presence"] += ["description", "shipping_fee"]

    incoming = copy.deepcopy(baseline)
    incoming.update(observation_key="mutation", observed_at=(start + timedelta(seconds=10)).isoformat())
    incoming.update(patch)
    for field in ("description", "shipping_fee"):
        if field in patch and field not in incoming["field_presence"]:
            incoming["field_presence"].append(field)
    if case == "exact_replay":
        incoming = copy.deepcopy(baseline)
    elif case == "reused_key_changed_price":
        incoming["observation_key"] = baseline["observation_key"]
    elif case == "older_price":
        incoming["observed_at"] = (start - timedelta(seconds=10)).isoformat()
    elif case == "same_time_conflict":
        incoming["observed_at"] = baseline["observed_at"]
    elif case == "missing_paired_currency":
        incoming.pop("currency")
        incoming["field_presence"].remove("currency")
    elif case == "presence_mismatch":
        incoming["field_presence"].remove("price")
    elif case == "future_timestamp":
        incoming["observed_at"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    elif case == "timezone_missing":
        incoming["observed_at"] = start.replace(tzinfo=None).isoformat()
    elif case in {"timeout", "blocked", "not_found"}:
        for field in incoming["field_presence"]:
            incoming.pop(field)
        incoming.update(result=case, field_presence=[])
    elif case == "omitted_optional_fields":
        for field in ("description", "shipping_fee"):
            incoming.pop(field)
            incoming["field_presence"].remove(field)

    path = f"/internal/v2/crawl-runs/{uuid4()}/observations"
    headers = {"Authorization": "Bearer " + os.environ["COLLECTOR_TOKEN"]}
    with TestClient(app) as api, pg() as db:
        created = api.post(path, json=baseline, headers=headers)
        assert created.status_code == 201, created.text
        offer_id = created.json()["offer_id"]

        def current():
            with db.cursor(row_factory=dict_row) as cur:
                return cur.execute(
                    """SELECT o.price,o.currency,o.shipping_fee,o.current_url,
                       o.availability,o.condition,i.name,i.description
                       FROM app.offers o JOIN app.catalog_items i USING(item_id)
                       WHERE o.offer_id=%s""", (offer_id,),
                ).fetchone()

        before = current()
        response = api.post(path, json=incoming, headers=headers)
        body = response.json()
        assert response.status_code == status, response.text
        if kind:
            assert body["change_kind"] == kind, body
        if case == "exact_replay":
            assert body["observation_id"] == created.json()["observation_id"]
        if case == "reused_key_changed_price":
            assert body["detail"] == "PAYLOAD_CONFLICT"
        reasons = {
            "same_time_conflict": "SAME_TIME_CONFLICT",
            "missing_identity": "MISSING_IDENTITY",
            "domain_identity_conflict": "IDENTITY_CONFLICT",
            "large_but_valid_price": "PRICE_ANOMALY",
        }
        if case in reasons:
            assert body["state"] == "quarantine"
            assert body["error_code"] == reasons[case]
        after = current()
        assert after == before | changes, (case, before, after, changes)

        offers = db.execute("SELECT count(*) FROM app.offers WHERE source=%s", (source,)).fetchone()[0]
        assert offers == (2 if case == "new_variant" else 1)
        if status == 201 and kind not in {"quarantined", "created"}:
            assert body["offer_id"] == offer_id
        if case == "new_variant":
            assert body["offer_id"] != offer_id

        # HTTP rejection/replay cannot create an extra observation or history.
        observations = db.execute(
            "SELECT count(*) FROM app.crawl_observations WHERE source=%s", (source,),
        ).fetchone()[0]
        assert observations == (1 if status in {200, 409, 422} else 2)
        counts = {}
        expected_history = {
            "price_history": 1 + int(bool(changes.keys() & {"price", "currency", "shipping_fee"})),
            "offer_url_history": 1 + int("current_url" in changes),
            "offer_changes": 1 + int(bool(changes)),
        }
        for table, expected in expected_history.items():
            counts[table] = db.execute(
                f"SELECT count(*) FROM app.{table} WHERE offer_id=%s", (offer_id,),
            ).fetchone()[0]
            assert counts[table] == expected, (case, table, counts[table])
        if changes:
            audit = db.execute(
                """SELECT before_data,after_data FROM app.offer_changes
                   WHERE offer_id=%s AND observation_id=%s""",
                (offer_id, body["observation_id"]),
            ).fetchone()
            assert audit is not None
            assert set(audit[0]) == set(audit[1]) == set(changes)
            for field, value in changes.items():
                assert str(audit[0][field]) == str(before[field])
                assert str(audit[1][field]) == str(value)

        # Check public listing visibility as well as the stored row.
        query = "/v2/offers?selected_domain=product&source=" + source
        visible = api.get(query).json()["items"]
        expected_visible = 0 if case in {"out_of_stock", "sale_ended", "used_condition", "not_found"} else offers
        assert len(visible) == expected_visible
        assert len(api.get(query + "&condition=all&availability=all").json()["items"]) == offers

        result = {
            "case": case, "http": status, "kind": body.get("change_kind"),
            "error": body.get("error_code"), "before": before, "after": after,
            "offers": offers, "observations": observations, "history": counts,
            "result": "PASS",
        }
        print("MUTATION_RESULT " + json.dumps(result, default=str, ensure_ascii=False))
        if summary := os.getenv("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as out:
                out.write(f"- PASS **{case}**: HTTP {status}, {body.get('change_kind', 'rejected')}; "
                          f"price={after['price']} {after['currency']}, "
                          f"state={after['availability']}, offers={offers}, history={counts}\n")

