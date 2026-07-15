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
const expectedPrices = { "1d": 15, "7d": 70, "30d": 250, "1d_promax": 49, "7d_promax": 199, "30d_promax": 399 };
assert(plans.plans?.length === 6, "all six shop plans must be available");
for (const plan of plans.plans) {
  assert(plan.amount === expectedPrices[plan.code], `price mismatch for ${plan.code}`);
}

const publicHtml = await fs.readFile(new URL("./public/index.html", import.meta.url), "utf8");
assert(publicHtml.includes('data-reset-device="${esc(order.key_code)}"'), "customer reset button missing");
assert(publicHtml.includes('postJson("/api/shop/reset-device", { code })'), "customer reset action missing");
const scripts = [...publicHtml.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
for (const [index, match] of scripts.entries()) {
  if (/type=["']application\/ld\+json["']/i.test(match[0])) continue;
  new Function(match[1]);
}

assert(source.includes('keyTier === "promax" && !/^[0-9a-fA-F]{64}$/.test(contentKey)'), "ProMax content-key guard was lost");
console.log("Backend restore tests passed: admin UI, SlipOK 3 accounts, device reset, prices, public UI, content-key guard");
