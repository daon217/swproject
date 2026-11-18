"""Extension boundary for a future reviewed official/affiliate API transport.

No internal API URL, HTTP implementation, credentials or enable-by-env switch lives
here. Approval alone cannot enable a transport that has not been implemented/tested.
"""
from typing import Protocol


class OfficialAPITransport(Protocol):
    def search(self, query: str, page: int) -> str:
        """Return a reviewed official API response; enforce its request budget."""
        ...


def require_live_transport():
    raise PermissionError('elevenst_LIVE_disabled: official_or_affiliate_permission_and_reviewed_transport_required')
