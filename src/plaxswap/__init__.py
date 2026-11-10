"""Official Python client for the Plaxswap API.

Accept crypto payments (hosted checkout, payment links, signed webhooks) and quote crypto swaps.
Docs: https://plaxswap.com/developers/payments and https://plaxswap.com/developers
Standard library only (urllib, hmac, json). Python 3.8+.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, Optional, Union

__all__ = ["Plaxswap", "PlaxswapError", "WebhookSignatureError", "verify_signature", "construct_event", "sign", "SIGNATURE_HEADER"]
__version__ = "0.1.0"

DEFAULT_BASE_URL = "https://plaxswap.com"
SIGNATURE_HEADER = "x-px-signature"


class PlaxswapError(Exception):
    """An API error: HTTP status, the stable code and the plain-English message from the API."""

    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def __repr__(self) -> str:  # pragma: no cover
        return f"PlaxswapError(status={self.status}, code={self.code!r}, message={self.message!r})"


class Plaxswap:
    """Client for https://plaxswap.com/api/v1.

    api_key: a merchant key (pxs_test_... or pxs_live_...) for the payment gateway, or a partner key (pxk_...) for swaps.
    Keep it on your server.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = DEFAULT_BASE_URL, user_ip: Optional[str] = None, timeout: float = 30.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.user_ip = user_ip
        self.timeout = timeout
        self.payments = _Payments(self)
        self.payment_links = _PaymentLinks(self)
        self.gateway = _Gateway(self)
        self.swap = _Swap(self)

    def meta(self) -> Dict[str, Any]:
        """Service mode, the caller's country rules and time limits."""
        return self.request("GET", "/api/v1/meta")

    def coins(self) -> Dict[str, Any]:
        """Coins, networks and methods."""
        return self.request("GET", "/api/v1/coins")

    def request(self, method: str, path: str, body: Any = None, query: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
        """Low-level call for any endpoint in https://plaxswap.com/api/v1/openapi.json"""
        url = self.base_url + path
        q = {k: v for k, v in (query or {}).items() if v is not None}
        if q:
            url += "?" + urllib.parse.urlencode(q)
        h = {"Accept": "application/json", "User-Agent": f"plaxswap-python/{__version__}"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if self.user_ip:
            h["x-user-ip"] = self.user_ip
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                text = res.read().decode("utf-8")
                return json.loads(text) if text else None
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            try:
                err = (json.loads(text) or {}).get("error") or {}
            except ValueError:
                err = {}
            raise PlaxswapError(e.code, err.get("code") or f"http_{e.code}", err.get("message") or text[:200] or str(e), err.get("details")) from None
        except urllib.error.URLError as e:
            raise PlaxswapError(0, "network_error", str(e.reason)) from None


class _Payments:
    def __init__(self, c: Plaxswap):
        self._c = c

    def create(self, idempotency_key: Optional[str] = None, **params: Any) -> Dict[str, Any]:
        """Ask for a payment; send the payer to payment["checkoutUrl"].

        Example: create(amount="100", currency="USD", receive="usdt-tron", orderId="1042", idempotency_key="order-1042")
        """
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._c.request("POST", "/api/v1/payments", body=params, headers=headers)

    def retrieve(self, payment_id: str) -> Dict[str, Any]:
        return self._c.request("GET", f"/api/v1/payments/{urllib.parse.quote(payment_id, safe='')}")

    def list(self, **query: Any) -> Dict[str, Any]:
        """Newest first. Filters: status, orderId, createdFrom, createdTo, limit, cursor."""
        return self._c.request("GET", "/api/v1/payments", query=query)

    def cancel(self, payment_id: str) -> Dict[str, Any]:
        return self._c.request("POST", f"/api/v1/payments/{urllib.parse.quote(payment_id, safe='')}/cancel", body={})

    def simulate(self, payment_id: str, outcome: str, pay_currency: Optional[str] = None) -> Dict[str, Any]:
        """Test keys only: act out paid, partially_paid, overpaid, late, expired or failed."""
        body: Dict[str, Any] = {"outcome": outcome}
        if pay_currency:
            body["payCurrency"] = pay_currency
        return self._c.request("POST", f"/api/v1/payments/{urllib.parse.quote(payment_id, safe='')}/simulate", body=body)


class _PaymentLinks:
    def __init__(self, c: Plaxswap):
        self._c = c

    def create(self, **params: Any) -> Dict[str, Any]:
        """Create a "pay me exactly this amount" link. Keep manageToken: it is shown once."""
        return self._c.request("POST", "/api/v1/payment-links", body=params)

    def retrieve(self, link_id: str) -> Dict[str, Any]:
        return self._c.request("GET", f"/api/v1/payment-links/{urllib.parse.quote(link_id, safe='')}")

    def coins(self) -> Dict[str, Any]:
        return self._c.request("GET", "/api/v1/payment-links/coins")


class _Gateway:
    def __init__(self, c: Plaxswap):
        self._c = c

    def coins(self) -> Dict[str, Any]:
        """Coins you can receive, and what payers can pay each with. No key needed."""
        return self._c.request("GET", "/api/v1/gateway/coins")


class _Swap:
    def __init__(self, c: Plaxswap):
        self._c = c

    def coins(self) -> Dict[str, Any]:
        return self._c.request("GET", "/api/v1/dex/coins")

    def routes(self, from_: str, to: str, amount: str, **extra: Any) -> Dict[str, Any]:
        """Routes for a pair and amount, best first. amount is a decimal string in coin units, for example "0.015"."""
        body = {"from": from_, "to": to, "amount": amount, **extra}
        return self._c.request("POST", "/api/v1/dex/routes", body=body)

    def build(self, route_id: str) -> Dict[str, Any]:
        return self._c.request("POST", "/api/v1/dex/build", body={"routeId": route_id})

    def status(self, deposit_address: str) -> Dict[str, Any]:
        return self._c.request("GET", "/api/v1/dex/status", query={"depositAddress": deposit_address})


# ---------------------------------------------------------------- webhooks

class WebhookSignatureError(Exception):
    pass


def _parse(header: Optional[str]):
    t, v1 = None, []
    for part in str(header or "").split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if k == "t" and len(v) == 10 and v.isdigit():
            t = v
        if k == "v1" and len(v) == 64 and all(ch in "0123456789abcdef" for ch in v):
            v1.append(v)
    return t, v1


def _b(raw: Union[str, bytes]) -> bytes:
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def sign(raw_body: Union[str, bytes], secret: str, timestamp: Optional[int] = None) -> str:
    """The header Plaxswap would send for this body (useful in your own tests)."""
    t = int(timestamp if timestamp is not None else time.time())
    mac = hmac.new(secret.encode("utf-8"), f"{t}.".encode("utf-8") + _b(raw_body), hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def verify_signature(raw_body: Union[str, bytes], header: Optional[str], secret: str, tolerance: int = 300, now: Optional[float] = None) -> bool:
    """True when x-px-signature is valid for this exact raw body and was signed within `tolerance` seconds."""
    t, v1 = _parse(header)
    if not t or not v1 or not secret:
        return False
    if abs((now if now is not None else time.time()) - int(t)) > tolerance:
        return False
    expected = hmac.new(secret.encode("utf-8"), f"{t}.".encode("utf-8") + _b(raw_body), hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(sig, expected) for sig in v1)


def construct_event(raw_body: Union[str, bytes], header: Optional[str], secret: str, tolerance: int = 300) -> Dict[str, Any]:
    """Checks the signature, then parses the event ({"id", "event", "livemode", "createdAt", "data"})."""
    if not verify_signature(raw_body, header, secret, tolerance):
        raise WebhookSignatureError("Invalid or expired Plaxswap webhook signature")
    return json.loads(_b(raw_body).decode("utf-8"))
