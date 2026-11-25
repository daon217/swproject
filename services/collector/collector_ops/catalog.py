"""Capabilities are separate from credentials, permissions and operational enablement."""
SOURCES={'serper':'serper_google_shopping','ebay':'ebay_browse','ebay_used':'ebay_browse','yes24':'yes24_api'}
BLOCKED={'bunjang':'partner_contract_and_storage_reuse_grant_required',
         'joongna':'official_product_access_and_storage_reuse_grant_unverified',
         'elevenst':'offline_adapter_only_no_reviewed_live_transport',
         'smartify':'legacy_feed_not_enrolled_for_scheduled_storage',
         'perfume_registry':'legacy_feed_not_enrolled_for_scheduled_storage',
         'yappy_kids':'legacy_feed_not_enrolled_for_scheduled_storage',
         'searchapi':'retired_use_serper'}
PROVIDERS=('domeggook',)+tuple(SOURCES)+tuple(BLOCKED)
