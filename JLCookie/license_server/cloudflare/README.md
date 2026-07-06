# JLCookie License Server (Cloudflare Worker + D1)

ระบบนี้ใช้แบบ stock key:

1. สร้าง key เก็บไว้ใน stock ก่อน
2. ลูกค้าจ่ายเงินและระบบร้านเช็คสลิปผ่าน
3. ร้านเรียก admin API เพื่อส่ง key
4. เวลาของ key เริ่มนับตอน API ส่ง key สำเร็จ
5. บอทใช้ `/api/verify` เพื่อตรวจ key, วันหมดอายุ, HWID seat

ยังไม่รวมระบบเช็คสลิปจริง เช่น SlipOK/EasySlip. จุดนั้นค่อยต่อให้เรียก `/api/admin/deliver` หลังสลิปผ่าน

## Setup

1. Install Wrangler and log in:

```bat
npm install -g wrangler
wrangler login
```

2. Create D1:

```bat
wrangler d1 create jlcookie_license
copy wrangler.toml.example wrangler.toml
```

Paste the returned database id into `wrangler.toml`.

3. Apply schema:

```bat
wrangler d1 execute jlcookie_license --file schema.sql
```

If you already deployed the older schema, run this once instead:

```bat
wrangler d1 execute jlcookie_license --file migration_stock_delivery.sql
wrangler d1 execute jlcookie_license --file migration_shop_users_orders.sql
```

4. Generate signing keys from project root:

```bat
pip install cryptography
python tools\make_license_keypair.py
```

Set Worker secrets:

```bat
wrangler secret put PRIV_PKCS8_B64
wrangler secret put ADMIN_TOKEN
```

5. Deploy:

```bat
wrangler deploy
```

6. Copy `license_config.release.json` from the project root to `license_config.json` before building a release, or fill these values manually:

- `required`: `true`
- `api_url`: `https://YOUR-WORKER.workers.dev/api/verify`
- `public_key_hex`: value printed by `tools\make_license_keypair.py`

## Stock Flow

Quick local test without copying the admin token manually:

```bat
powershell -ExecutionPolicy Bypass -File test_flow.ps1
```

The script reads `admin.local.json`, mints one stock key, verifies that stock key is blocked, delivers it, then verifies that the delivered key works.

Create stock keys:

```bat
curl -X POST https://YOUR-WORKER.workers.dev/api/admin/mint ^
  -H "content-type: application/json" ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN" ^
  -d "{\"plan\":\"7d\",\"duration_days\":7,\"count\":20,\"max_seats\":1}"
```

Check stock count:

```bat
curl https://YOUR-WORKER.workers.dev/api/admin/stock ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN"
```

Deliver a key after payment/slip passes. The server picks one stock key and starts its expiry now:

```bat
curl -X POST https://YOUR-WORKER.workers.dev/api/admin/deliver ^
  -H "content-type: application/json" ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN" ^
  -d "{\"plan\":\"7d\",\"duration_days\":7,\"max_seats\":1,\"order_id\":\"ORDER-1001\",\"customer_ref\":\"line:user123\"}"
```

The response contains the key to show/send to the customer:

```json
{
  "ok": true,
  "reused": false,
  "key": {
    "code": "JL-XXXX-XXXX-XXXX-XXXX",
    "expires_at": 1783260000,
    "status": "delivered",
    "order_id": "ORDER-1001"
  }
}
```

If the shop already holds the stock key and only needs to start the timer, call:

```bat
curl -X POST https://YOUR-WORKER.workers.dev/api/admin/deliver-key ^
  -H "content-type: application/json" ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN" ^
  -d "{\"key\":\"JL-XXXX-XXXX-XXXX-XXXX\",\"order_id\":\"ORDER-1001\",\"customer_ref\":\"line:user123\"}"
```

`order_id` is idempotent. Calling delivery again with the same `order_id` returns the same key, not a new one.

## Verify / Revoke

Verify key from bot/client:

```bat
curl -X POST https://YOUR-WORKER.workers.dev/api/verify ^
  -H "content-type: application/json" ^
  -d "{\"key\":\"JL-XXXX-XXXX-XXXX-XXXX\",\"hwid\":\"TEST-HWID\"}"
```

Stock keys that are not delivered yet will fail with `คีย์นี้ยังไม่ได้ถูกส่งจากร้าน`.

Revoke key:

```bat
curl -X POST https://YOUR-WORKER.workers.dev/api/admin/revoke ^
  -H "content-type: application/json" ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN" ^
  -d "{\"key\":\"JL-XXXX-XXXX-XXXX-XXXX\"}"
```

Reset HWID/seat for a key:

```bat
curl -X POST https://YOUR-WORKER.workers.dev/api/admin/reset-seats ^
  -H "content-type: application/json" ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN" ^
  -d "{\"key\":\"JL-XXXX-XXXX-XXXX-XXXX\"}"
```

List latest keys:

```bat
curl https://YOUR-WORKER.workers.dev/api/admin/keys ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN"
```

Admin panel:

```text
https://YOUR-WORKER.workers.dev/admin
```

Paste `ADMIN_TOKEN` from `admin.local.json` into the page.

Customer website:

```text
https://YOUR-WORKER.workers.dev/
```

Health check:

```text
https://YOUR-WORKER.workers.dev/health
```

## Shop / User Flow

The website should call these APIs:

```text
GET  /api/shop/plans
GET  /api/shop/activity
POST /api/auth/register
POST /api/auth/login
GET  /api/me
POST /api/orders
GET  /api/orders
GET  /api/download-info
```

Use `Authorization: Bearer CUSTOMER_SESSION_TOKEN` for `/api/me`, `/api/orders`, and `/api/download-info`.

Create an order after the customer uploads a slip:

```bat
curl -X POST https://YOUR-WORKER.workers.dev/api/orders ^
  -H "content-type: application/json" ^
  -H "authorization: Bearer CUSTOMER_SESSION_TOKEN" ^
  -d "{\"plan\":\"7d\",\"customer_ref\":\"line:user123\",\"slip_name\":\"slip.jpg\",\"slip_mime\":\"image/jpeg\",\"slip_b64\":\"BASE64_IMAGE\"}"
```

Admin order review:

```bat
curl https://YOUR-WORKER.workers.dev/api/admin/shop-orders ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN"

curl -X POST https://YOUR-WORKER.workers.dev/api/admin/shop-orders/approve ^
  -H "content-type: application/json" ^
  -H "x-admin-token: YOUR_ADMIN_TOKEN" ^
  -d "{\"order_id\":\"ORDER-...\"}"
```

Approving an order calls the same stock delivery logic as `/api/admin/deliver`, so the key timer starts when the admin approves the slip. Set `DOWNLOAD_URL` as a Worker secret if the customer account page should show the latest program download link:

```bat
wrangler secret put DOWNLOAD_URL
```

## Important

If a third-party shop sends stock keys by itself but cannot call `/api/admin/deliver-key`, the license server cannot know the delivery time. For expiry to start when the key is sent, the shop/backend must call one of the delivery APIs.
