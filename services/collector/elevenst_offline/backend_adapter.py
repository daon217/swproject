"""Authenticated Observation v2 and ListingExtension v1 delivery adapter for 11st offline records."""
import hashlib
import json
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from services.collector.domeggook_live.domeggook_backend import HTTPBackendTransport, safe_ack
from services.collector.domeggook_live.domeggook_backend_contract import Observation


def _resolve_variant(row):
    if row.get("identity_status") != "verified_native_tuple":
        raise ValueError("quarantined_or_unverified_identity")
    variant = row.get("variant_key")
    if variant:
        return variant
    if row.get("variant_scope") == "confirmed_none":
        return "default"
    raise ValueError("nonempty_native_variant_required")


def _check_permissions(row, cfg):
    test = cfg.get("backend_delivery", {}).get("mode") == "synthetic_test"
    if test:
        if row.get("source") != "elevenst_test" or urlsplit(row.get("product_url", "")).hostname != "store.example.test":
            raise PermissionError("synthetic_namespace_and_provenance_required")
    else:
        if row.get("source") != "elevenst":
            raise ValueError("source_not_approved")
        if not cfg.get("price_semantics_confirmed"):
            raise PermissionError("elevenst_price_eligibility_agreement_required")
        if row.get("storage_permission_status") != "approved" or row.get("reuse_permission_status") != "approved":
            raise PermissionError("explicit_storage_and_reuse_permission_required")


def prepare_elevenst_observation(row, cfg, *, selected_domain, condition="new", availability="available"):
    _check_permissions(row, cfg)
    variant = _resolve_variant(row)
    if condition not in ("new", "used") or selected_domain not in ("product", "food"):
        raise ValueError("explicit_domain_and_condition_required")
    if availability not in ("available", "out_of_stock", "ended"):
        raise ValueError("explicit_availability_required")
    stamp = row.get("observed_at") or row.get("collected_at")
    if not stamp or not row.get("product_name") or row.get("price") is None or not row.get("currency") or not row.get("product_url"):
        raise ValueError("required_observation_fields_missing")

    body = {
        "schema_version": 2,
        "source": row["source"],
        "source_listing_id": str(row["source_listing_id"]),
        "variant_key": variant,
        "observed_at": stamp,
        "result": "success",
        "selected_domain": selected_domain,
        "condition": condition,
        "name": row["product_name"],
        "price": str(Decimal(str(row["price"]))),
        "currency": row["currency"],
        "availability": availability,
        "url": row["product_url"],
    }
    if row.get("shipping_fee") is not None:
        body["shipping_fee"] = str(Decimal(str(row["shipping_fee"])))
    if row.get("description") is not None and cfg.get("allow_description"):
        body["description"] = row["description"]
    body["field_presence"] = sorted(
        k for k in ("name", "description", "price", "currency", "shipping_fee", "availability", "url") if k in body
    )
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    body["observation_key"] = f"{row['source']}:{digest}"
    settings = cfg.get("backend_delivery", {})
    Observation.model_validate(
        body,
        context={
            "hosts": settings.get("allowed_product_hosts", ["www.11st.co.kr", "m.11st.co.kr"]),
            "currencies": settings.get("currencies", ["KRW", "USD", "JPY", "EUR"]),
        },
    )
    return body


def prepare_elevenst_extension(row, cfg, *, matching_profile=None, food_evidence=None):
    _check_permissions(row, cfg)
    variant = _resolve_variant(row)
    stamp = row.get("observed_at") or row.get("collected_at")
    if not stamp:
        raise ValueError("observed_at_required")

    profile = dict(matching_profile or {})
    for target, src in (("brand", "brand"), ("category", "category"), ("seller_name", "seller"), ("image_url", "image_url")):
        if row.get(src) and target not in profile:
            profile[target] = row[src]
    if profile.get("image_url") and "image_urls" not in profile:
        profile["image_urls"] = [profile["image_url"]]

    body = {
        "schema_version": "listing-matching-extension-v1",
        "source": row["source"],
        "source_listing_id": str(row["source_listing_id"]),
        "variant_key": variant,
        "observed_at": stamp,
        "product_url": row.get("product_url"),
        "is_synthetic": cfg.get("backend_delivery", {}).get("mode") == "synthetic_test",
    }
    if profile:
        body["matching_profile"] = profile
    if food_evidence:
        body["food_evidence"] = dict(food_evidence)
    if "matching_profile" not in body and "food_evidence" not in body:
        raise ValueError("extension_metadata_empty")
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    body["observation_key"] = f"{row['source']}:ext:{digest}"
    return body


class ElevenstBackendAdapter:
    def __init__(self, cfg, transport: HTTPBackendTransport | None = None):
        self.cfg = cfg
        self.transport = transport

    def send(
        self,
        run_id,
        row,
        *,
        selected_domain="product",
        condition="new",
        availability="available",
        matching_profile=None,
        food_evidence=None,
    ):
        if not self.cfg.get("backend_enabled") or not self.cfg.get("backend_owner_approved"):
            return {"sent": False, "reason": "backend_disabled_or_owner_approval_missing"}
        if self.transport is None:
            raise ValueError("approved_transport_required")
        rid = str(UUID(str(run_id)))
        obs = prepare_elevenst_observation(
            row, self.cfg, selected_domain=selected_domain, condition=condition, availability=availability
        )
        status, ack = self.transport(f"/internal/v2/crawl-runs/{rid}/observations", obs)
        result = {
            "sent": status in (200, 201) and "state" in ack,
            "status": status,
            "applied": ack.get("state") == "applied",
            **ack,
        }
        if not result["applied"]:
            return result
        try:
            ext = prepare_elevenst_extension(row, self.cfg, matching_profile=matching_profile, food_evidence=food_evidence)
        except ValueError:
            return result
        ext_status, ext_ack = self.transport(f"/internal/v2/crawl-runs/{rid}/extensions", ext)
        result["extension_status"] = ext_status
        result["extension_applied"] = ext_ack.get("state") == "applied"
        result["extension_id"] = ext_ack.get("extension_id")
        return result
