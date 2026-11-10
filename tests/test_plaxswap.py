import hashlib, hmac, json, unittest
from unittest import mock
import plaxswap
from plaxswap import Plaxswap, PlaxswapError, verify_signature, construct_event, sign

SECRET = "whsec_test_123"
BODY = '{"id":"evt_3k9q2m7x8c1v5b4n","event":"payment.paid","livemode":false,"data":{"id":"pay_7m2k9q4x8c1v5b3n","object":"payment","status":"paid"}}'
T = 1794000000
HEX = hmac.new(SECRET.encode(), f"{T}.{BODY}".encode(), hashlib.sha256).hexdigest()


class Webhooks(unittest.TestCase):
    def test_valid(self): self.assertTrue(verify_signature(BODY, f"t={T},v1={HEX}", SECRET, now=T + 10))
    def test_bytes_body(self): self.assertTrue(verify_signature(BODY.encode(), f"t={T},v1={HEX}", SECRET, now=T))
    def test_several_v1(self): self.assertTrue(verify_signature(BODY, f"t={T},v1={'0'*64},v1={HEX}", SECRET, now=T))
    def test_changed_body(self): self.assertFalse(verify_signature(BODY + " ", f"t={T},v1={HEX}", SECRET, now=T))
    def test_old(self): self.assertFalse(verify_signature(BODY, f"t={T},v1={HEX}", SECRET, now=T + 301))
    def test_wrong_secret(self): self.assertFalse(verify_signature(BODY, f"t={T},v1={HEX}", "whsec_other", now=T))
    def test_missing(self): self.assertFalse(verify_signature(BODY, None, SECRET))
    def test_sign(self): self.assertEqual(sign(BODY, SECRET, T), f"t={T},v1={HEX}")
    def test_construct(self):
        ev = construct_event(BODY, sign(BODY, SECRET), SECRET)
        self.assertEqual(ev["event"], "payment.paid"); self.assertEqual(ev["data"]["id"], "pay_7m2k9q4x8c1v5b3n")
    def test_construct_bad(self):
        with self.assertRaises(plaxswap.WebhookSignatureError): construct_event(BODY, "t=1,v1=x", SECRET)


class FakeResp:
    def __init__(self, body): self.body = body
    def read(self): return json.dumps(self.body).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Client(unittest.TestCase):
    def test_create_payment(self):
        seen = {}
        def fake(req, timeout=None):
            seen["url"], seen["method"], seen["headers"], seen["body"] = req.full_url, req.get_method(), dict(req.header_items()), json.loads(req.data)
            return FakeResp({"id": "pay_0000000000000001", "object": "payment", "status": "pending"})
        with mock.patch("urllib.request.urlopen", fake):
            p = Plaxswap(api_key="pxs_test_x").payments.create(amount="100", currency="USD", receive="usdt-tron", orderId="1042", idempotency_key="order-1042")
        self.assertEqual(p["id"], "pay_0000000000000001")
        self.assertEqual(seen["url"], "https://plaxswap.com/api/v1/payments")
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer pxs_test_x")
        self.assertEqual(seen["headers"]["Idempotency-key"], "order-1042")
        self.assertEqual(seen["body"], {"amount": "100", "currency": "USD", "receive": "usdt-tron", "orderId": "1042"})

    def test_error(self):
        import urllib.error, io
        def fake(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":{"code":"invalid_api_key","message":"That key is wrong."}}'))
        with mock.patch("urllib.request.urlopen", fake):
            with self.assertRaises(PlaxswapError) as cm: Plaxswap(api_key="bad").payments.retrieve("pay_x")
        self.assertEqual((cm.exception.status, cm.exception.code), (401, "invalid_api_key"))


if __name__ == "__main__":
    unittest.main()
