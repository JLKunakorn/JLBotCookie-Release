import fs from "node:fs/promises";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const source = await fs.readFile(new URL("./worker.js", import.meta.url), "utf8");
const moduleUrl = "data:text/javascript;base64," + Buffer.from(source).toString("base64");
const { default: worker } = await import(moduleUrl);

const adminPage = await worker.fetch(
  new Request("https://example.test/private-admin"),
  { ADMIN_PATH: "/private-admin" },
);
const adminHtml = await adminPage.text();
assert(adminPage.status === 200, "admin page route must render");
assert(adminHtml.includes('id="toggleOrdersBtn"'), "order hide/show button missing");
assert(adminHtml.includes('id="ordersPanel" style="overflow:auto; display:none"'), "orders must be hidden by default");
assert(adminHtml.includes('id="slipokAccount"'), "SlipOK account selector missing");
assert(adminHtml.includes('id="slipokQuotaStatus"'), "SlipOK quota cards missing");

const fakeDb = {
  prepare(sql) {
    const query = String(sql).replace(/\s+/g, " ").trim().toLowerCase();
    return {
      bind(...args) {
        return {
          first: async () => query.includes("from app_config") ? { value: "auto" } : null,
          all: async () => ({ results: [] }),
          run: async () => ({ meta: { changes: 1 } }),
        };
      },
      first: async () => null,
      all: async () => ({ results: [] }),
      run: async () => ({ meta: { changes: 1 } }),
    };
  },
};

const env = {
  ADMIN_TOKEN: "admin-test",
  DISCORD_SHOP_TOKEN: "discord-test",
  DB: fakeDb,
  SLIPOK_BRANCH_ID: "branch-1",
  SLIPOK_API_KEY: "key-1",
  SLIPOK_BRANCH_ID_2: "branch-2",
  SLIPOK_API_KEY_2: "key-2",
  SLIPOK_BRANCH_ID_3: "branch-3",
  SLIPOK_API_KEY_3: "key-3",
};

globalThis.fetch = async (url) => {
  const branch = /apikey\/(branch-\d)/.exec(String(url))?.[1];
  const remaining = { "branch-1": 5, "branch-2": 19, "branch-3": 100 }[branch];
  return Response.json({ success: true, data: { quota: remaining, overQuota: 0 } });
};

const slipResponse = await worker.fetch(
  new Request("https://example.test/api/admin/slipok-account", {
    headers: { "x-admin-token": env.ADMIN_TOKEN },
  }),
  env,
);
const slip = await slipResponse.json();
assert(slipResponse.status === 200 && slip.account === "auto", "SlipOK selected account must be restored");
assert(slip.accounts?.length === 3, "SlipOK must report all three accounts");
assert(slip.accounts[0].used === 95 && slip.accounts[0].available === false, "JL reserve rule mismatch");
assert(slip.accounts[1].used === 81 && slip.accounts[1].available === true, "Fxng quota mismatch");
assert(slip.accounts[2].used === 0 && slip.accounts[2].available === true, "Xiaomi quota mismatch");

const resetUnauthorized = await worker.fetch(
  new Request("https://example.test/api/shop/reset-device", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ code: "JL-TEST" }),
  }),
  env,
);
assert(resetUnauthorized.status === 401, "device reset route must exist and require customer login");

const plansResponse = await worker.fetch(
  new Request("https://example.test/api/discord-shop/plans", {
    headers: { "x-discord-shop-token": env.DISCORD_SHOP_TOKEN },
  }),
  env,
);
const plans = await plansResponse.json();
const expectedPrices = {
  "1d": 15,
  "3d": 35,
  "7d": 70,
  "30d": 250,
  "lifetime": 599,
  "1d_promax": 59,
  "3d_promax": 149,
  "7d_promax": 199,
  "30d_promax": 599,
  "lifetime_promax": 999,
};
assert(plans.plans?.length === 10, "all ten shop plans must be available");
for (const plan of plans.plans) {
  assert(plan.amount === expectedPrices[plan.code], `price mismatch for ${plan.code}`);
}
assert(plans.plans.find((plan) => plan.code === "lifetime")?.duration_days === 0, "Premium Lifetime duration mismatch");
assert(plans.plans.find((plan) => plan.code === "lifetime_promax")?.duration_days === 0, "ProMax Lifetime duration mismatch");

const signingKeys = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const privateKeyB64 = Buffer.from(await crypto.subtle.exportKey("pkcs8", signingKeys.privateKey)).toString("base64");
const lifetimeRow = {
  code: "JL-LIFETIME-TEST",
  plan: "lifetime",
  tier: "premium",
  duration_days: 0,
  expires_at: 0,
  max_seats: 1,
  revoked: 0,
  status: "delivered",
  delivered_at: Math.floor(Date.now() / 1000),
};
const lifetimeDb = {
  prepare(sql) {
    const query = String(sql).replace(/\s+/g, " ").trim().toLowerCase();
    return {
      bind() {
        return {
          first: async () => query.includes("from lic_keys") ? lifetimeRow : null,
          all: async () => ({ results: [] }),
          run: async () => ({ meta: { changes: 1 } }),
        };
      },
    };
  },
};
const lifetimeResponse = await worker.fetch(
  new Request("https://example.test/api/verify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ key: lifetimeRow.code, hwid: "HWID-LIFETIME-TEST" }),
  }),
  { DB: lifetimeDb, PRIV_PKCS8_B64: privateKeyB64 },
);
const lifetimeEnvelope = await lifetimeResponse.json();
const lifetimePayload = JSON.parse(Buffer.from(lifetimeEnvelope.payload_b64, "base64").toString("utf8"));
assert(lifetimePayload.ok === true && lifetimePayload.exp === 0, "Lifetime key must verify without an expiry timestamp");

const publicHtml = await fs.readFile(new URL("./public/index.html", import.meta.url), "utf8");
assert(publicHtml.includes('data-reset-device="${esc(order.key_code)}"'), "customer reset button missing");
assert(publicHtml.includes('postJson("/api/shop/reset-device", { code })'), "customer reset action missing");
for (const [planCode, price] of Object.entries(expectedPrices)) {
  assert(publicHtml.includes(`code: "${planCode}", price: ${price}`), `public plan missing: ${planCode}`);
}
assert(publicHtml.includes("https://discord.gg/zsky5XS7HU"), "Discord contact link missing");
assert(publicHtml.includes("Premium VS ProMax ต่างกันอย่างไร?"), "Premium/ProMax comparison missing");
assert(publicHtml.includes("ระบบแก้ CAPTCHA อัตโนมัติ"), "Premium feature list incomplete");
assert(publicHtml.includes("รีโรลไอดีอัตโนมัติได้ไม่จำกัดรอบ"), "ProMax feature list incomplete");
assert(publicHtml.includes("ไม่ส่งภาพเกมหรือคำสั่งเล่นไปประมวลผลบนเซิร์ฟเวอร์ของร้าน"), "local-processing disclosure missing");
assert(!publicHtml.includes("Local 100%"), "misleading Local 100% claim must not be published");
const tutorialVideoIds = ["PIKEcDoKbZY", "2tCCZyq2Znc", "A1NXQAv5N24", "lttfV0-onYw", "_TRvufTZv_I"];
for (const videoId of tutorialVideoIds) {
  assert(publicHtml.includes(videoId), `tutorial video missing: ${videoId}`);
}
assert((publicHtml.match(/class="video-thumb"/g) || []).length >= tutorialVideoIds.length, "tutorial thumbnails missing");
const scripts = [...publicHtml.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
for (const [index, match] of scripts.entries()) {
  if (/type=["']application\/ld\+json["']/i.test(match[0])) continue;
  new Function(match[1]);
}

assert(source.includes('keyTier === "promax" && !/^[0-9a-fA-F]{64}$/.test(contentKey)'), "ProMax content-key guard was lost");
assert(source.includes('if (!lifetime && now > Number(row.expires_at))'), "Lifetime verification guard missing");
assert(source.includes('lic_keys.duration_days = 0 OR lic_keys.expires_at IS NULL'), "Lifetime download access guard missing");
console.log("Backend restore tests passed: admin UI, SlipOK 3 accounts, device reset, 10 plans, Lifetime, public UI, contact, content-key guard");
