"""Existing eBay OAuth methods; constructor adapted for injected transport only.
No dotenv loading, backend imports, product float mapper or direct requests.
"""
import base64, math, threading, time
import requests
EBAY_SCOPE="https://api.ebay.com/oauth/api_scope"
EBAY_TOKEN_URL="https://api.ebay.com/identity/v1/oauth2/token"
class EbayOAuthError(RuntimeError):
    def __init__(self,message,http_status):
        super().__init__(message);self.http_status=http_status
class EbayOAuth:
    def __init__(self,client_id,client_secret,transport):
        self.client_id=client_id;self.client_secret=client_secret
        self._access_token=None;self._token_expires_at=0.0
        self._token_lock=threading.Lock();self.token_transport=transport

    def _invalidate_token(self, rejected_token: str) -> None:
        with self._token_lock:
            # Do not evict a newer token another concurrent request already obtained.
            if self._access_token == rejected_token:
                self._access_token = None
                self._token_expires_at = 0.0

    def _get_access_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Missing EBAY_CLIENT_ID or EBAY_CLIENT_SECRET in environment.")

        with self._token_lock:
            if self._access_token and time.monotonic() < self._token_expires_at:
                return self._access_token
            self._access_token = None
            self._token_expires_at = 0.0
            return self._mint_access_token()

    def _mint_access_token(self) -> str:
        # Called under _token_lock. Both paths validate/cache the same application
        # token; the engine path retains common transport throttling and retries.
        credentials = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        encoded = base64.b64encode(credentials).decode("ascii")
        options = {
            "headers": {"Authorization": f"Basic {encoded}",
                        "Content-Type": "application/x-www-form-urlencoded"},
            "data": {"grant_type": "client_credentials", "scope": EBAY_SCOPE},
        }
        requested_at = time.monotonic()
        if self.token_transport is not None:
            # CollectionError from the shared transport is already sanitized;
            # preserve its category/status/retry_after for diagnostics and resume.
            payload = self.token_transport.post_json(EBAY_TOKEN_URL, **options)
        else:
            try:
                response = requests.post(
                    EBAY_TOKEN_URL, timeout=15, allow_redirects=False, **options)
            except requests.RequestException:
                raise RuntimeError("eBay OAuth token request failed.") from None
            try:
                if response.status_code != 200:
                    raise EbayOAuthError(
                        f"eBay OAuth token request failed (HTTP {response.status_code}).",
                        response.status_code,
                    ) from None
                try:
                    payload = response.json()
                except ValueError:
                    raise RuntimeError("eBay OAuth returned invalid JSON.") from None
            finally:
                response.close()
        if not isinstance(payload, dict):
            raise RuntimeError("eBay OAuth returned an invalid response.")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token or any(
            not 33 <= ord(char) <= 126 for char in access_token
        ):
            raise RuntimeError("eBay OAuth response did not include a valid access token.")
        expires_in = payload.get("expires_in")
        try:
            lifetime = float(expires_in)
        except (TypeError, ValueError, OverflowError):
            raise RuntimeError("eBay OAuth response did not include a valid token lifetime.") from None
        if isinstance(expires_in, bool) or not math.isfinite(lifetime) or lifetime <= 0:
            raise RuntimeError("eBay OAuth response did not include a valid token lifetime.")
        expires_at = requested_at + lifetime - min(60.0, lifetime * 0.1)
        if time.monotonic() >= expires_at:
            raise RuntimeError("eBay OAuth token expired during acquisition.")
        self._access_token = access_token
        self._token_expires_at = expires_at
        return access_token
