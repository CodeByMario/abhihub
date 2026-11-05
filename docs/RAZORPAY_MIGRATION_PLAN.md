# Razorpay Payment Gateway Migration Plan: AbhiHub

> **Status**: Ready for implementation
> **Replaces**: PhonePe (`methods/phonepe_service.py`, `routes/payments.py`, `routes/webhooks.py`)
> **Stack**: Flask · Supabase · Jinja2 · Vanilla JS

---

## 1. Architecture Comparison

| Component | Current (PhonePe) | Target (Razorpay Standard) |
| :--- | :--- | :--- |
| **SDK** | Custom REST V1/V2 | `razorpay>=1.4.1` Python SDK |
| **Order Creation** | Pre-generated ID in payload | Server-side `POST /v1/orders` |
| **Checkout UI** | Redirect URL or custom form | Hosted popup via `checkout.js` |
| **Client Callback** | Redirect with encoded data | `handler(response)` → POST to server |
| **Signature Verify** | SHA256 + Salt Key checksum | HMAC-SHA256 via SDK utility |
| **Webhooks** | Custom callback URL | `payment.captured` / `order.paid` events |
| **Idempotency** | None | Conditional DB update + unique constraint |

---

## 2. Phase 1 — Environment & Dependencies

### 2.1 Install SDK
Add to `requirements.txt`:
```
razorpay>=1.4.1
```

### 2.2 Environment Variables
Add to `.env` (never commit):
```env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
RAZORPAY_CURRENCY=INR
```

> **Go-live**: Replace `rzp_test_` with `rzp_live_` keys from Dashboard → Account & Settings → API Keys.

---

## 3. Phase 2 — Service Layer: `methods/razorpay_service.py`

Create this file. It owns all Razorpay interactions.

```python
"""
methods/razorpay_service.py
Razorpay gateway service — order creation, signature verification, webhook validation.
"""
import os
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from functools import partial

import razorpay

# ── Singleton client (initialized once per process) ───────────────────────────
_client = None


def get_client() -> razorpay.Client:
    global _client
    if _client is None:
        _client = razorpay.Client(auth=(
            os.environ['RAZORPAY_KEY_ID'],
            os.environ['RAZORPAY_KEY_SECRET'],
        ))
        # Patch a 10-second timeout on all outbound API calls
        _client.session.request = partial(_client.session.request, timeout=10)
    return _client


# ── Amount conversion ─────────────────────────────────────────────────────────
def to_paise(amount) -> int:
    """Convert INR float/Decimal to integer paise. Uses Decimal to avoid float precision bugs."""
    return int(
        (Decimal(str(amount)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    )


# ── Order creation ────────────────────────────────────────────────────────────
def create_order(amount_inr, receipt_id: str, notes: dict = None) -> dict:
    """
    Create a Razorpay order.
    amount_inr: price in rupees (e.g. 299.0)
    Returns full Razorpay order dict. Raises on failure.
    """
    data = {
        'amount': to_paise(amount_inr),
        'currency': os.getenv('RAZORPAY_CURRENCY', 'INR'),
        'receipt': receipt_id[:40],
    }
    if notes:
        data['notes'] = notes
    return get_client().order.create(data=data)


# ── Payment signature verification ───────────────────────────────────────────
def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str,
                             razorpay_signature: str) -> bool:
    """
    Verify HMAC-SHA256 signature. Returns True on success, False on tampered/invalid.
    NEVER skip this step before fulfilling an order.
    """
    try:
        get_client().utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        })
        return True
    except Exception:
        return False


# ── Webhook signature verification ───────────────────────────────────────────
def verify_webhook_signature(payload_body: bytes, signature: str) -> bool:
    """Verify X-Razorpay-Signature against raw webhook body bytes."""
    secret = os.environ['RAZORPAY_WEBHOOK_SECRET']
    try:
        get_client().utility.verify_webhook_signature(
            payload_body.decode('utf-8'), signature, secret
        )
        return True
    except Exception:
        return False


# ── Safe signature storage ────────────────────────────────────────────────────
def hash_signature(razorpay_signature: str) -> str:
    """Return SHA-256 hash of signature for DB storage. Never store raw signature."""
    return hashlib.sha256(razorpay_signature.encode()).hexdigest()
```

---

## 4. Phase 3 — Server Routes

### 4.1 Order Creation: `POST /api/payment/initiate`

In `routes/payments.py`:

```python
@payments_bp.route('/api/payment/initiate', methods=['POST'])
@auth_required
def initiate_payment():
    from methods.razorpay_service import create_order

    data = request.get_json(silent=True) or {}
    doc_id = str(data.get('doc_id', '')).strip()
    user = session.get('user', {})
    user_id = user.get('uid')

    if not doc_id:
        return jsonify({'success': False, 'error': 'doc_id required'}), 400

    # SECURITY: Always derive amount from DB, never trust client-submitted amount
    client = init_supabase()
    doc = client.table('documents').select('price, title').eq('id', doc_id).single().execute()
    if not doc.data:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    price = doc.data['price']
    receipt_id = f"doc_{doc_id}_{user_id}"[:40]

    try:
        order = create_order(
            amount_inr=price,
            receipt_id=receipt_id,
            notes={'doc_id': doc_id, 'user_id': user_id}
        )
    except Exception as e:
        logging.error(f"[RZP] Order creation failed: {e}")
        return jsonify({'success': False, 'error': 'Payment service unavailable'}), 502

    client.table('credit_transactions').insert({
        'user_id': user_id,
        'order_id': order['id'],
        'amount': float(price),
        'status': 'pending',
        'doc_id': doc_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }).execute()

    # key_id is public — safe to return. NEVER return key_secret.
    return jsonify({
        'success': True,
        'key_id': os.environ['RAZORPAY_KEY_ID'],
        'order_id': order['id'],
        'amount': order['amount'],
        'currency': order['currency'],
        'prefill': {
            'name': user.get('display_name', ''),
            'email': user.get('email', ''),
            'contact': user.get('phone', ''),
        }
    })
```

---

### 4.2 Payment Verification: `POST /api/payment/verify`

```python
@payments_bp.route('/api/payment/verify', methods=['POST'])
@auth_required
def verify_payment():
    from methods.razorpay_service import verify_payment_signature, hash_signature

    data = request.get_json(silent=True) or {}
    rzp_order_id   = str(data.get('razorpay_order_id', '')).strip()
    rzp_payment_id = str(data.get('razorpay_payment_id', '')).strip()
    rzp_signature  = str(data.get('razorpay_signature', '')).strip()

    if not all([rzp_order_id, rzp_payment_id, rzp_signature]):
        return jsonify({'success': False, 'error': 'Missing fields'}), 400

    user_id = session['user']['uid']
    client = init_supabase()

    # SECURITY: Cross-check order belongs to this user and is still pending
    txn = client.table('credit_transactions') \
        .select('*') \
        .eq('order_id', rzp_order_id) \
        .eq('user_id', user_id) \
        .eq('status', 'pending') \
        .single().execute()

    if not txn.data:
        logging.warning(f"[RZP] Order mismatch or already processed: {rzp_order_id} uid={user_id}")
        return jsonify({'success': False, 'error': 'Invalid or already processed order'}), 400

    # SECURITY: Verify HMAC signature before any fulfillment
    if not verify_payment_signature(rzp_order_id, rzp_payment_id, rzp_signature):
        logging.error(f"[RZP] Signature FAILED: order={rzp_order_id} pay={rzp_payment_id}")
        client.table('payment_errors').insert({
            'user_id': user_id, 'order_id': rzp_order_id,
            'payment_id': rzp_payment_id, 'reason': 'signature_mismatch',
            'created_at': datetime.now(timezone.utc).isoformat()
        }).execute()
        return jsonify({'success': False, 'error': 'Payment verification failed'}), 400

    # Atomic idempotency guard — only update if not already captured
    update = client.table('credit_transactions') \
        .update({
            'status': 'captured',
            'payment_id': rzp_payment_id,
            'rzp_sig_hash': hash_signature(rzp_signature),  # Store hash, never raw
            'captured_at': datetime.now(timezone.utc).isoformat(),
        }) \
        .eq('order_id', rzp_order_id) \
        .neq('status', 'captured') \
        .execute()

    if not update.data:
        return jsonify({'success': True, 'message': 'Already processed'}), 200

    # TODO: Grant document access / creator credits here
    return jsonify({
        'success': True,
        'redirect_url': f'/payment/receipt?order_id={rzp_order_id}'
    })
```

---

### 4.3 Webhook Handler: `POST /api/webhooks/razorpay`

In `routes/webhooks.py`:

```python
@webhooks_bp.route('/api/webhooks/razorpay', methods=['POST'])
def razorpay_webhook():
    from methods.razorpay_service import verify_webhook_signature

    signature = request.headers.get('X-Razorpay-Signature', '')

    # SECURITY: Verify webhook authenticity before any processing
    if not verify_webhook_signature(request.get_data(), signature):
        logging.warning('[RZP WEBHOOK] Invalid signature — rejected')
        return jsonify({'error': 'Invalid signature'}), 400

    payload = request.get_json(silent=True) or {}
    event = payload.get('event')
    payment = payload.get('payload', {}).get('payment', {}).get('entity', {})
    order_id = payment.get('order_id')
    payment_id = payment.get('id')

    if event == 'payment.captured' and order_id:
        client = init_supabase()
        result = client.table('credit_transactions') \
            .update({'status': 'captured', 'payment_id': payment_id,
                     'captured_at': datetime.now(timezone.utc).isoformat()}) \
            .eq('order_id', order_id) \
            .neq('status', 'captured') \
            .execute()
        logging.info(f'[RZP WEBHOOK] {"Captured" if result.data else "Already processed"}: {order_id}')

    elif event == 'payment.failed' and order_id:
        client = init_supabase()
        client.table('credit_transactions') \
            .update({'status': 'failed'}).eq('order_id', order_id).execute()

    return jsonify({'status': 'ok'}), 200
```

---

## 5. Phase 4 — Frontend: `templates/payment.html`

Replace PhonePe section with:

```html
<!-- Deferred load — does NOT block page render -->
<script src="https://checkout.razorpay.com/v1/checkout.js" defer></script>

<button id="rzp-pay-btn">Pay ₹{{ amount }}</button>

<script>
document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('rzp-pay-btn');

  btn.addEventListener('click', async function (e) {
    e.preventDefault();
    btn.disabled = true;

    // Step 1: Create Razorpay order on server
    let orderData;
    try {
      const res = await fetch('/api/payment/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: '{{ doc_id }}' })
      });
      orderData = await res.json();
      if (!orderData.success) throw new Error(orderData.error);
    } catch (err) {
      alert('Could not start payment: ' + err.message);
      btn.disabled = false;
      return;
    }

    // Step 2: Open Razorpay checkout modal
    const options = {
      key:         orderData.key_id,
      amount:      orderData.amount,
      currency:    orderData.currency,
      name:        'AbhiHub',
      description: 'Document Purchase',
      order_id:    orderData.order_id,
      prefill:     orderData.prefill,
      theme:       { color: '#6366f1' },
      timeout:     600,
      modal: {
        confirm_close: true,
        ondismiss: function () { btn.disabled = false; }
      },

      // Step 3: Send to server for verification BEFORE any fulfillment
      handler: async function (response) {
        try {
          const vRes = await fetch('/api/payment/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(response)
          });
          const vData = await vRes.json();
          if (!vData.success) throw new Error(vData.error || 'Verification failed');
          window.location.href = vData.redirect_url;
        } catch (err) {
          // Payment went through but verification failed — show payment ID for support
          alert(
            'Payment received (ID: ' + response.razorpay_payment_id + ') but ' +
            'confirmation failed. Please contact support with this ID.'
          );
          btn.disabled = false;
        }
      }
    };

    const rzp = new Razorpay(options);
    rzp.on('payment.failed', function (resp) {
      alert('Payment failed: ' + resp.error.description);
      btn.disabled = false;
    });
    rzp.open();
  });
});
</script>
```

---

## 6. Phase 5 — Database Migration

Run against Supabase:

```sql
-- Add new columns to existing credit_transactions table
ALTER TABLE credit_transactions
  ADD COLUMN IF NOT EXISTS payment_id    TEXT,
  ADD COLUMN IF NOT EXISTS rzp_sig_hash  TEXT,       -- SHA-256 hash only, never raw signature
  ADD COLUMN IF NOT EXISTS captured_at   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS doc_id        TEXT;

-- Idempotency: prevent duplicate order processing at DB level
ALTER TABLE credit_transactions
  ADD CONSTRAINT unique_order_id UNIQUE (order_id);

-- Fraud/error monitoring table
CREATE TABLE IF NOT EXISTS payment_errors (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     TEXT,
  order_id    TEXT,
  payment_id  TEXT,
  reason      TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

**Status mapping from PhonePe**:

| PhonePe | Razorpay |
|---|---|
| `PAYMENT_SUCCESS` | `captured` |
| `PAYMENT_PENDING` | `pending` / `authorized` |
| `PAYMENT_ERROR` | `failed` |

---

## 7. Test Plan

| Scenario | Input | Expected |
|---|---|---|
| Successful card | Visa `4100 2800 0000 1007` | `status=captured` in DB, receipt redirect |
| Failed card | Razorpay error test card | `status=failed`, no credit allocated |
| Signature tamper | Modify `razorpay_signature` before POST | 400, logged to `payment_errors` |
| Price tamper | Send wrong amount in initiate body | Ignored — server reads price from DB |
| Duplicate webhook | Replay `payment.captured` event | 200, `already_processed`, no double-credit |
| UPI success | `success@razorpay` | Captured, redirect |
| UPI failure | `failure@razorpay` | Failure handler fires, button re-enabled |
| Network drop on verify | Kill server mid-handler | User shown support message with payment ID |
| Wrong user's order | Cross-user `order_id` in verify body | 400, order mismatch |

---

## 8. Go-Live Checklist

- [ ] Add `razorpay>=1.4.1` to `requirements.txt` and redeploy.
- [ ] Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` in production env.
- [ ] Run Phase 5 DB migration SQL on Supabase.
- [ ] Confirm `UNIQUE (order_id)` constraint is active on `credit_transactions`.
- [ ] Register webhook URL in Razorpay Dashboard → Webhooks. Enable `payment.captured`, `payment.failed`, `order.paid`.
- [ ] Enable **Auto-Capture** in Dashboard → Account & Settings → Payment Capture.
- [ ] Add Razorpay IP allowlist at Nginx/WAF level for `/api/webhooks/razorpay`.
- [ ] Apply `Flask-Limiter` rate limit on webhook route: `100/minute`.
- [ ] Swap `rzp_test_` keys to `rzp_live_` keys.
- [ ] Run 1 real ₹1 live transaction and verify settlement + DB status = `captured`.
- [ ] Confirm `payment_errors` table is monitored / alerting configured.
- [ ] Define rollback: `PAYMENT_PROVIDER=phonepe` feature flag to re-enable PhonePe if needed.

---

## 2. Architecture Comparison

| Component | Current (PhonePe) | Target (Razorpay Standard) |
| :--- | :--- | :--- |
| **SDK / Client** | Custom REST API calls (V1/V2) | `razorpay` Python SDK / Standard REST |
| **Order Creation** | Pre-generated order ID sent in payload | Server-side `POST /orders` via Razorpay API |
| **Checkout UI** | Redirect URL or custom UI | Hosted popup modal via `checkout.js` |
| **Client Callback** | Redirect to redirect_url with encoded data | `handler(response)` callback with `order_id`, `payment_id`, `signature` |
| **Security Verification** | Checksum verification (SHA256 + Salt Key) | HMAC SHA-256 (`order_id + "|" + razorpay_payment_id`, `key_secret`) |
| **Async Webhooks** | Custom callback URL | Webhook endpoint listening for `payment.captured` & `order.paid` |

---

## 3. Migration Roadmap & Step-by-Step Breakdown

### Phase 1: Environment & Dependencies
1. **Dependencies**:
   - Add `razorpay>=1.4.1` to [requirements.txt](file:///e:/Users/abhihub/New%20folder/abhihub/requirements.txt).
2. **Environment Configuration**:
   - Register the following variables in server configuration:
     - `RAZORPAY_KEY_ID`: Dashboard Key ID (rzp_test_... / rzp_live_...)
     - `RAZORPAY_KEY_SECRET`: Secret Key
     - `RAZORPAY_WEBHOOK_SECRET`: Secret configured during webhook setup
     - `RAZORPAY_CURRENCY`: Default `INR`
     - `RAZORPAY_AUTO_CAPTURE`: `1` (or configure via Dashboard)

---

### Phase 2: Service Layer (`methods/razorpay_service.py`)
Create a dedicated service module encapsulating all Razorpay interactions:
1. **Client Initialization**:
   ```python
   import razorpay
   client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))
   ```
2. **Order Creation**:
   - Method: `create_order(amount_in_rupees: float, receipt_id: str, notes: dict) -> dict`
   - Converts amount to smallest currency subunit (paise: `int(round(amount * 100))`).
   - Calls `client.order.create(data={...})` and returns `order_id`.
3. **Payment Signature Verification**:
   - Method: `verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature) -> bool`
   - Uses `client.utility.verify_payment_signature(...)`.
4. **Webhook Signature Verification**:
   - Method: `verify_webhook_signature(payload_body: bytes, signature: str, secret: str) -> bool`
   - Uses `client.utility.verify_webhook_signature(...)`.

---

### Phase 3: Server Routes & Controller Updates

#### 1. Order Creation Endpoint (`/api/payment/initiate` in [routes/payments.py](file:///e:/Users/abhihub/New%20folder/abhihub/routes/payments.py))
- Replace PhonePe payment token generation with Razorpay order creation.
- Return to frontend:
  ```json
  {
    "success": true,
    "key_id": "RAZORPAY_KEY_ID",
    "order_id": "order_EK9d...",
    "amount": 50000,
    "currency": "INR",
    "prefill": { "name": "...", "email": "...", "contact": "..." }
  }
  ```

#### 2. Payment Verification Endpoint (`/api/payment/verify` in [routes/payments.py](file:///e:/Users/abhihub/New%20folder/abhihub/routes/payments.py))
- Accepts `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`.
- **Mandatory Step**: Verify server-side HMAC signature using internal order record and `RAZORPAY_KEY_SECRET`.
- On valid signature:
  - Transition order status in Supabase (`credit_transactions`) to `captured` / `completed`.
  - Grant document access / allocate creator credits.
  - Return `{ "success": true, "redirect_url": "/payment/receipt?order_id=..." }`.

#### 3. Webhook Handler (`/api/webhooks/razorpay` in [routes/webhooks.py](file:///e:/Users/abhihub/New%20folder/abhihub/routes/webhooks.py))
- Verify `X-Razorpay-Signature` against raw request payload.
- Listen for events:
  - `payment.captured`: Settle transaction if not already marked.
  - `payment.failed`: Update transaction log with failure reason.
  - `order.paid`: Redundant confirmation of full order settlement.

---

### Phase 4: Frontend Checkout Integration

#### 1. Template Update ([templates/payment.html](file:///e:/Users/abhihub/New%20folder/abhihub/templates/payment.html))
1. Include Razorpay script:
   ```html
   <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
   ```
2. Replace PhonePe UI branding with Razorpay / Clean Neutral AbhiHub Checkout.
3. Configure `options` object:
   ```javascript
   const options = {
     key: data.key_id,
     amount: data.amount,
     currency: "INR",
     name: "AbhiHub",
     description: "Document Purchase",
     order_id: data.order_id,
     handler: function (response) {
       // Send response to server for verification
       verifyPaymentOnServer(response);
     },
     prefill: {
       name: user.name,
       email: user.email,
       contact: user.phone
     },
     theme: {
       color: "#6366f1"
     },
     modal: {
       ondismiss: function() {
         showPaymentCancelledAlert();
       }
     }
   };
   const rzp = new Razorpay(options);
   rzp.on('payment.failed', function(resp) {
     handlePaymentFailure(resp.error);
   });
   rzp.open();
   ```

---

### Phase 5: Database Schema & Transaction Records
- In `credit_transactions` / `transactions.py`:
  - Store `order_id` (Razorpay `order_xxxx`).
  - Store `payment_id` (Razorpay `pay_xxxx`).
  - Store `signature` in metadata / admin notes.
  - Ensure status mappings:
    - PhonePe `PAYMENT_SUCCESS` -> Razorpay `captured` / `paid`.
    - PhonePe `PAYMENT_PENDING` -> Razorpay `attempted` / `authorized`.
    - PhonePe `PAYMENT_ERROR` -> Razorpay `failed`.

---

## 4. Testing & Verification Plan

1. **Card Testing (Test Mode)**:
   - Success: Visa `4100 2800 0000 1007` (Any future MM/YY, 3-digit CVV).
   - Failure: Simulating error test cards for insufficient funds and card expired.
2. **UPI Testing**:
   - `success@razorpay` -> Validates instant capture.
   - `failure@razorpay` -> Validates failure handler and retry loop.
3. **Signature Tampering Check**:
   - Ensure modified `razorpay_signature` fails validation and rejects fulfillment.
4. **Idempotency & Webhook Tests**:
   - Ensure webhook replay does not duplicate credit or document allocation.

---

## 5. Go-Live Cutover Checklist

- [ ] Enable **Auto-Capture** in Razorpay Dashboard (`Account & Settings` -> `Payment Capture`).
- [ ] Register Webhook endpoint URL in Razorpay Dashboard (`Account & Settings` -> `Webhooks`).
- [ ] Swap API keys in production configuration from `rzp_test_...` to `rzp_live_...`.
- [ ] Conduct 1 real end-to-end low-value transaction (e.g. ₹1) and initiate refund to verify settling.
- [ ] Archive/deprecate PhonePe service routes safely.
