# plaxswap

The official Python client for the [Plaxswap](https://plaxswap.com) API.

- **Accept crypto payments** on your site: create a payment, send the customer to the hosted checkout, and check the signed webhook. Docs: [Crypto payment gateway API](https://plaxswap.com/developers/payments).
- **Payment links**: ask for an exact amount of one coin; the payer can use any supported coin. See [crypto payment links](https://plaxswap.com/pay).
- **Swaps**: quote routes from KyberSwap, 0x, LI.FI, Relay and NEAR Intents, best return first, with every fee shown. See the [swap API guide](https://plaxswap.com/developers).

Standard library only. Python 3.8+.

## Install

```bash
pip install plaxswap
```

## Accept a payment

```python
import os
from plaxswap import Plaxswap

px = Plaxswap(api_key=os.environ["PLAXSWAP_KEY"])  # pxs_test_... or pxs_live_...

payment = px.payments.create(
    amount="100", currency="USD", receive="usdt-tron",
    orderId="1042", description="2 x T-shirt", returnUrl="https://shop.example/orders/1042",
    idempotency_key="order-1042",  # retries return the same payment
)
print(payment["checkoutUrl"])  # send the customer here
```

With a test key nothing real moves. Act out an outcome and get the same webhook a live payment sends:

```python
px.payments.simulate(payment["id"], "paid")
```

## Check the webhook (Flask)

```python
from flask import Flask, request
from plaxswap import construct_event, WebhookSignatureError

app = Flask(__name__)

@app.post("/plaxswap-webhook")
def webhook():
    try:
        event = construct_event(request.get_data(), request.headers.get("x-px-signature"), os.environ["PLAXSWAP_WEBHOOK_SECRET"])
    except WebhookSignatureError:
        return "", 400
    # Skip events you have seen (event["id"]), then read the payment back before you ship:
    payment = px.payments.retrieve(event["data"]["id"])
    if payment["status"] == "paid":
        pass  # fulfil order payment["orderId"]
    return "", 200
```

## Quote a swap

```python
px = Plaxswap()  # no key needed for quotes
routes = px.swap.routes("usdt-tron", "btc", "250")["routes"]
```

## Errors

Every failed call raises `PlaxswapError` with `status`, a stable `code` (for example `invalid_api_key`) and a plain-English `message` that is safe to show.

## Fees

Gateway: the customer pays the 1.5% platform fee at checkout; you pay 0.3% plus the network fee when you withdraw. Swaps: Plaxswap's fee is at most 0.3%, plus the route's own fee. Current figures: [plaxswap.com/fees](https://plaxswap.com/fees).

## Links

- [Plaxswap](https://plaxswap.com)
- [Payment gateway docs](https://plaxswap.com/developers/payments)
- [OpenAPI document](https://plaxswap.com/api/v1/openapi.json)
- [WooCommerce plugin](https://plaxswap.com/integrations/woocommerce)
- Support: support@plaxswap.com

MIT licence.
