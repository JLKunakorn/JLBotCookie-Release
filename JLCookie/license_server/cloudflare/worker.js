const encoder = new TextEncoder();

const CORS_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type,authorization,x-admin-token,x-session-token,x-discord-shop-token",
  "access-control-max-age": "86400",
};

function json(data, status = 200) {
  return Response.json(data, { status, headers: CORS_HEADERS });
}

function corsOk() {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

function b64ToBytes(value) {
  return Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
}

function bytesToB64(bytes) {
  let text = "";
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text);
}

function bytesToHex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(hex) {
  const clean = String(hex || "").replace(/[^a-f0-9]/gi, "");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i += 1) out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function randomHex(bytes = 16) {
  const data = new Uint8Array(bytes);
  crypto.getRandomValues(data);
  return bytesToHex(data);
}

function makeCode(prefix = "JL") {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  const hex = bytesToHex(bytes).toUpperCase();
  return `${prefix}-${hex.slice(0, 4)}-${hex.slice(4, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}`;
}

function cleanCode(value) {
  return String(value || "").trim().toUpperCase();
}

const TIERS = ["premium", "promax"];

function resolveTier(value) {
  const raw = cleanText(value, "premium").toLowerCase();
  return TIERS.includes(raw) ? raw : "premium";
}

function cleanText(value, fallback = "") {
  return String(value || fallback).trim();
}

function fileNameFromUrl(value, fallback = "") {
  const raw = cleanText(value);
  if (!raw) return fallback;
  try {
    const parsed = new URL(raw);
    const pathName = decodeURIComponent(parsed.pathname || "");
    const name = pathName.split("/").filter(Boolean).pop();
    return name || fallback;
  } catch (_) {
    const clean = raw.split(/[?#]/, 1)[0];
    const name = clean.split("/").filter(Boolean).pop();
    return name || fallback;
  }
}

function zipUrlFromDownloadUrl(value) {
  const raw = cleanText(value);
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    parsed.pathname = parsed.pathname.replace(/\.exe$/i, ".zip");
    return parsed.toString();
  } catch (_) {
    return raw.replace(/\.exe($|[?#])/i, ".zip$1");
  }
}

function releaseDownloadInfo(env, tier = "premium") {
  if (tier === "promax") {
    const downloadUrl = cleanText(env.PROMAX_DOWNLOAD_URL || env.DOWNLOAD_URL);
    const zipUrl = cleanText(env.PROMAX_ZIP_URL) || zipUrlFromDownloadUrl(downloadUrl);
    return {
      version: env.PROMAX_APP_VERSION || "V1.1.0 ProMax",
      download_url: downloadUrl,
      download_name: fileNameFromUrl(downloadUrl, "(Beta)JLBotPromax.exe"),
      zip_url: zipUrl,
      zip_name: fileNameFromUrl(zipUrl, "(Beta)JLBotPromax.zip"),
    };
  }

  const downloadUrl = cleanText(env.DOWNLOAD_URL);
  const zipUrl = cleanText(env.ZIP_URL) || zipUrlFromDownloadUrl(downloadUrl);
  return {
    version: env.APP_VERSION || "V1.1.0 Premium",
    download_url: downloadUrl,
    download_name: fileNameFromUrl(downloadUrl, "JLmain_Premium.exe"),
    zip_url: zipUrl,
    zip_name: fileNameFromUrl(zipUrl, "JLmain_Premium.zip"),
  };
}

function cleanUsername(value) {
  return String(value || "").trim().replace(/[^\w.@-]/g, "").slice(0, 40);
}

function maskCustomerName(value) {
  const raw = cleanText(value, "ลูกค้า").replace(/\s+/g, "");
  if (raw.length <= 1) return raw + "*****";
  if (raw.length <= 3) return raw[0] + "*****";
  return raw.slice(0, 3) + "*****";
}

function clampInt(value, fallback, min, max) {
  const n = Number(value || fallback);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, Math.floor(n)));
}

function resolveDurationDays(body, fallbackDays = 7) {
  if (body.duration_minutes !== undefined) {
    const minutes = Number(body.duration_minutes);
    if (Number.isFinite(minutes)) {
      return Math.max(1, Math.min(365 * 24 * 60, minutes)) / 1440;
    }
  }
  if (body.duration_seconds !== undefined) {
    const seconds = Number(body.duration_seconds);
    if (Number.isFinite(seconds)) {
      return Math.max(60, Math.min(365 * 86400, seconds)) / 86400;
    }
  }
  const rawDays = body.duration_days;
  if (rawDays !== undefined && rawDays !== null && rawDays !== "" && Number(rawDays) === 0) {
    return 0;
  }
  const days = Number(rawDays === undefined || rawDays === null || rawDays === "" ? fallbackDays : rawDays);
  if (!Number.isFinite(days)) return fallbackDays;
  return Math.max(1 / 1440, Math.min(365, days));
}

function isLifetimeDuration(days) {
  return Number(days) === 0;
}

function expiresAtForDuration(now, days) {
  return isLifetimeDuration(days) ? 0 : Math.floor(now + Number(days) * 86400);
}

async function signPayload(env, payload) {
  const raw = encoder.encode(JSON.stringify(payload));
  const key = await crypto.subtle.importKey(
    "pkcs8",
    b64ToBytes(env.PRIV_PKCS8_B64),
    { name: "Ed25519" },
    false,
    ["sign"],
  );
  const sig = new Uint8Array(await crypto.subtle.sign("Ed25519", key, raw));
  return json({ payload_b64: bytesToB64(raw), sig: bytesToHex(sig) });
}

async function readJson(req) {
  try {
    return await req.json();
  } catch (_) {
    return {};
  }
}

async function getConfig(env, key, fallback = "") {
  try {
    const row = await env.DB.prepare("SELECT value FROM app_config WHERE key = ?").bind(key).first();
    return row && row.value != null ? String(row.value) : fallback;
  } catch (_) {
    return fallback;
  }
}

function slipOkCreds(env, account) {
  if (String(account) === "3") {
    return {
      branchId: cleanText(env.SLIPOK_BRANCH_ID_3).replace(/^#/, ""),
      apiKey: cleanText(env.SLIPOK_API_KEY_3),
      label: "3",
      displayName: "บช3 (Xiaomi)",
    };
  }
  if (String(account) === "2") {
    return {
      branchId: cleanText(env.SLIPOK_BRANCH_ID_2).replace(/^#/, ""),
      apiKey: cleanText(env.SLIPOK_API_KEY_2),
      label: "2",
      displayName: "บช2 (Fxng)",
    };
  }
  return {
    branchId: cleanText(env.SLIPOK_BRANCH_ID).replace(/^#/, ""),
    apiKey: cleanText(env.SLIPOK_API_KEY),
    label: "1",
    displayName: "บช1 (JL)",
  };
}

const SLIPOK_QUOTA_LIMIT = 100;
const SLIPOK_QUOTA_RESERVE = 5;

function firstFiniteNumber(values, fallback = NaN) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return fallback;
}

async function callSlipOKQuota(creds) {
  try {
    const res = await fetch(`https://api.slipok.com/api/line/apikey/${encodeURIComponent(creds.branchId)}/quota`, {
      method: "GET",
      headers: { "x-authorization": creds.apiKey },
    });
    const text = await res.text();
    let data = {};
    try {
      data = JSON.parse(text);
    } catch (_) {
      data = {};
    }
    const quotaData = data && typeof data.data === "object" ? data.data : {};
    const resultData = data && typeof data.result === "object" ? data.result : {};
    const remaining = firstFiniteNumber([
      quotaData.quota,
      quotaData.remaining,
      quotaData.remainingQuota,
      quotaData.quotaRemaining,
      resultData.quota,
      resultData.remaining,
      data.quota,
      data.remaining,
    ]);
    const overQuota = firstFiniteNumber([quotaData.overQuota, resultData.overQuota, data.overQuota], 0);
    const specialQuota = firstFiniteNumber([quotaData.specialQuota, resultData.specialQuota, data.specialQuota], 0);
    const limit = firstFiniteNumber([
      quotaData.limit,
      quotaData.quotaLimit,
      quotaData.totalQuota,
      resultData.limit,
      data.limit,
    ], SLIPOK_QUOTA_LIMIT);
    const endDate = cleanText(quotaData.endDate || resultData.endDate || data.endDate);
    if (!res.ok || data.success === false || !Number.isFinite(remaining)) {
      return {
        ok: false,
        status: res.ok ? 502 : res.status,
        msg: cleanText(data.message || quotaData.message || resultData.message, `SlipOK quota HTTP ${res.status}`),
      };
    }
    return {
      ok: true,
      remaining: Math.max(0, remaining),
      overQuota: Math.max(0, Number.isFinite(overQuota) ? overQuota : 0),
      specialQuota: Math.max(0, Number.isFinite(specialQuota) ? specialQuota : 0),
      limit: Math.max(1, Number.isFinite(limit) ? limit : SLIPOK_QUOTA_LIMIT),
      endDate,
    };
  } catch (error) {
    return { ok: false, status: 502, msg: cleanText(error?.message, "SlipOK quota unavailable") };
  }
}

async function callSlipOK(creds, { slipName, slipMime, slipB64, amount }) {
  const form = new FormData();
  const blob = new Blob([b64ToBytes(slipB64)], { type: slipMime || "image/jpeg" });
  form.append("files", blob, slipName || "slip.jpg");
  form.append("log", "true");
  form.append("amount", String(amount));

  try {
    const res = await fetch(`https://api.slipok.com/api/line/apikey/${encodeURIComponent(creds.branchId)}`, {
      method: "POST",
      headers: { "x-authorization": creds.apiKey },
      body: form,
    });
    const text = await res.text();
    let data = {};
    try {
      data = JSON.parse(text);
    } catch (_) {
      data = {};
    }
    const slipData = data.data || {};
    const ok = res.ok && data.success !== false && slipData.success !== false && Boolean(slipData.transRef || slipData.amount);
    const codeNum = Number(data.code);
    const msgText = String(slipData.message || data.message || "");
    const quotaExhausted = !ok && (codeNum === 1004 || /quota|โควต้า|โควตา|เกินจำนวน|เกินโควต้า|limit/i.test(msgText));
    const accountUnavailable = !ok && [1001, 1002, 1003, 1004].includes(codeNum);
    if (!ok) {
      return {
        ok: false,
        status: res.ok ? 400 : res.status,
        msg: msgText || "SlipOK ตรวจสลิปไม่ผ่าน",
        quotaExhausted,
        accountUnavailable,
        account: creds.label,
      };
    }
    return {
      ok: true,
      msg: msgText || "SlipOK ตรวจสลิปผ่าน",
      trans_ref: slipData.transRef || "",
      receiver: slipData.receiver?.displayName || slipData.receiver?.name || "",
      amount: slipData.amount,
      account: creds.label,
    };
  } catch (_) {
    return {
      ok: false,
      status: 502,
      msg: "ติดต่อ SlipOK ไม่สำเร็จ",
      quotaExhausted: false,
      accountUnavailable: false,
      account: creds.label,
    };
  }
}

async function checkSlipOK(env, payload) {
  const account = await getConfig(env, "slipok_account", "1");
  const order = account === "3" ? [3] : account === "2" ? [2] : account === "auto" ? [1, 2, 3] : [1];
  const configured = order.map((n) => slipOkCreds(env, n)).filter((creds) => creds.branchId && creds.apiKey);
  if (!configured.length) return { enabled: false };
  if (!payload.slipB64) return { enabled: true, ok: false, status: 400, msg: "ไม่มีไฟล์สลิปสำหรับตรวจ SlipOK" };

  let last = null;
  for (const creds of configured) {
    const quota = await callSlipOKQuota(creds);
    if (!quota.ok) {
      last = {
        enabled: true,
        ok: false,
        status: quota.status || 502,
        msg: `${creds.displayName}: ${quota.msg}`,
        account: creds.label,
      };
      if (account === "auto") continue;
      break;
    }
    if (quota.remaining <= SLIPOK_QUOTA_RESERVE) {
      last = {
        enabled: true,
        ok: false,
        status: 429,
        msg: `${creds.displayName} เหลือ ${quota.remaining}/${SLIPOK_QUOTA_LIMIT} จึงสำรองไว้ ${SLIPOK_QUOTA_RESERVE} ครั้ง`,
        quotaExhausted: true,
        accountUnavailable: true,
        account: creds.label,
      };
      if (account === "auto") continue;
      break;
    }
    const result = await callSlipOK(creds, payload);
    result.enabled = true;
    if (result.ok) return result;
    last = result;
    if (!(account === "auto" && (result.quotaExhausted || result.accountUnavailable))) break;
  }
  return last || { enabled: false };
}

async function sha256Hex(value) {
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(String(value || ""))));
  return bytesToHex(hash);
}

async function hashPassword(password, saltHex = randomHex(16), iterations = 100000) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: hexToBytes(saltHex), iterations },
    key,
    256,
  );
  return `pbkdf2$${iterations}$${saltHex}$${bytesToHex(new Uint8Array(bits))}`;
}

async function verifyPassword(password, stored) {
  const parts = String(stored || "").split("$");
  if (parts.length !== 4 || parts[0] !== "pbkdf2") return false;
  const expected = await hashPassword(password, parts[2], Number(parts[1]) || 100000);
  return expected === stored;
}

const SHOP_PLANS = {
  "1d": { code: "1d", label: "Premium 1 วัน", duration_days: 1, amount: 15, max_seats: 1, tier: "premium" },
  "3d": { code: "3d", label: "Premium 3 วัน", duration_days: 3, amount: 35, max_seats: 1, tier: "premium" },
  "7d": { code: "7d", label: "Premium 7 วัน", duration_days: 7, amount: 70, max_seats: 1, tier: "premium" },
  "30d": { code: "30d", label: "Premium 30 วัน", duration_days: 30, amount: 250, max_seats: 1, tier: "premium" },
  "lifetime": { code: "lifetime", label: "Premium Lifetime", duration_days: 0, amount: 599, max_seats: 1, tier: "premium" },
  "1d_promax": { code: "1d_promax", label: "ProMax 1 วัน", duration_days: 1, amount: 59, max_seats: 1, tier: "promax" },
  "3d_promax": { code: "3d_promax", label: "ProMax 3 วัน", duration_days: 3, amount: 149, max_seats: 1, tier: "promax" },
  "7d_promax": { code: "7d_promax", label: "ProMax 7 วัน", duration_days: 7, amount: 199, max_seats: 1, tier: "promax" },
  "30d_promax": { code: "30d_promax", label: "ProMax 30 วัน", duration_days: 30, amount: 599, max_seats: 1, tier: "promax" },
  "lifetime_promax": { code: "lifetime_promax", label: "ProMax Lifetime", duration_days: 0, amount: 999, max_seats: 1, tier: "promax" },
};

function resolveShopPlan(value) {
  const raw = cleanText(value, "7d").toLowerCase();
  if (SHOP_PLANS[raw]) return SHOP_PLANS[raw];
  const isPromax = raw.includes("promax");
  if (raw.includes("lifetime") || raw.includes("ตลอดชีพ")) {
    return isPromax ? SHOP_PLANS["lifetime_promax"] : SHOP_PLANS["lifetime"];
  }
  if (raw.includes("30")) return isPromax ? SHOP_PLANS["30d_promax"] : SHOP_PLANS["30d"];
  if (raw.includes("3")) return isPromax ? SHOP_PLANS["3d_promax"] : SHOP_PLANS["3d"];
  if (raw.includes("1")) return isPromax ? SHOP_PLANS["1d_promax"] : SHOP_PLANS["1d"];
  return isPromax ? SHOP_PLANS["7d_promax"] : SHOP_PLANS["7d"];
}

// คืน plan code มาตรฐานตาม tier+ระยะเวลา (เช่น tier=promax, 30 วัน -> "30d_promax")
// กันปัญหาสต็อกถูก mint ด้วย base code ("30d") ทำให้ไม่ match กับออเดอร์/หน้าเว็บ (suffixed)
function canonicalPlanCode(plan, tier, durationDays) {
  const t = resolveTier(tier);
  const dur = Number(durationDays);
  const match = Object.values(SHOP_PLANS).find(
    (p) => resolveTier(p.tier) === t && Number(p.duration_days) === dur,
  );
  return match ? match.code : cleanText(plan, "7d");
}

function orderId() {
  return `ORDER-${Date.now().toString(36).toUpperCase()}-${randomHex(2).toUpperCase()}`;
}

function unauthorized() {
  return json({ ok: false, msg: "Token ผู้ดูแลไม่ถูกต้อง" }, 401);
}

function isAdmin(req, env) {
  const token = req.headers.get("x-admin-token") || "";
  return env.ADMIN_TOKEN && token === env.ADMIN_TOKEN;
}

async function sessionReply(env, user) {
  const now = Math.floor(Date.now() / 1000);
  const token = randomHex(32);
  const tokenHash = await sha256Hex(token);
  await env.DB.prepare(
    `INSERT INTO shop_sessions(token_hash, user_id, created_at, expires_at, last_seen_at)
     VALUES(?, ?, ?, ?, ?)`,
  ).bind(tokenHash, user.id, now, now + 30 * 86400, now).run();
  return {
    token,
    user: {
      id: user.id,
      username: user.username,
      customer_ref: user.customer_ref,
    },
  };
}

async function requireUser(req, env) {
  const raw = req.headers.get("authorization") || req.headers.get("x-session-token") || "";
  const token = raw.toLowerCase().startsWith("bearer ") ? raw.slice(7).trim() : raw.trim();
  if (!token) return null;
  const now = Math.floor(Date.now() / 1000);
  const tokenHash = await sha256Hex(token);
  const row = await env.DB.prepare(
    `SELECT shop_users.id, shop_users.username, shop_users.customer_ref, shop_sessions.expires_at
     FROM shop_sessions
     JOIN shop_users ON shop_users.id = shop_sessions.user_id
     WHERE shop_sessions.token_hash = ?`,
  ).bind(tokenHash).first();
  if (!row || Number(row.expires_at || 0) < now) {
    await env.DB.prepare("DELETE FROM shop_sessions WHERE token_hash = ?").bind(tokenHash).run();
    return null;
  }
  await env.DB.prepare("UPDATE shop_sessions SET last_seen_at = ? WHERE token_hash = ?").bind(now, tokenHash).run();
  return row;
}

function authRequired() {
  return json({ ok: false, msg: "กรุณาเข้าสู่ระบบ" }, 401);
}

function keyReply(row) {
  return {
    code: row.code,
    plan: row.plan,
    tier: row.tier || "premium",
    duration_days: row.duration_days,
    expires_at: row.expires_at,
    max_seats: row.max_seats,
    status: row.status,
    delivered_at: row.delivered_at,
    order_id: row.order_id,
    customer_ref: row.customer_ref,
    revoked: row.revoked,
  };
}

function shopOrderReply(row, includeSlip = false) {
  if (!row) return null;
  const out = {
    id: row.id,
    username: row.username,
    plan: row.plan,
    plan_label: row.plan_label,
    duration_days: row.duration_days,
    amount: row.amount,
    max_seats: row.max_seats,
    status: row.status,
    customer_ref: row.customer_ref,
    slip_name: row.slip_name,
    slip_mime: row.slip_mime,
    has_slip: Boolean(row.slip_b64),
    key_code: row.key_code,
    key_duration_days: row.key_duration_days,
    key_tier: row.key_tier,
    hwid_reset_count: Number(row.hwid_reset_count || 0),
    hwid_reset_quota: row.key_code
      ? (resetQuotaFor(row.key_tier, row.key_duration_days) >= RESET_QUOTA_UNLIMITED
        ? -1
        : resetQuotaFor(row.key_tier, row.key_duration_days))
      : null,
    created_at: row.created_at,
    approved_at: row.approved_at,
    rejected_at: row.rejected_at,
    admin_note: row.admin_note,
  };
  if (includeSlip) out.slip_b64 = row.slip_b64 || "";
  return out;
}

async function findDeliveredByOrder(env, orderId) {
  if (!orderId) return null;
  return env.DB.prepare(
    `SELECT code, plan, tier, duration_days, expires_at, max_seats, revoked, status,
            delivered_at, order_id, customer_ref
     FROM lic_keys
     WHERE order_id = ?`,
  ).bind(orderId).first();
}

async function markDelivered(env, code, orderId, customerRef, now) {
  const row = await env.DB.prepare(
    `SELECT code, plan, tier, duration_days, expires_at, max_seats, revoked, status,
            delivered_at, order_id, customer_ref
     FROM lic_keys
     WHERE code = ?`,
  ).bind(code).first();

  if (!row) return { ok: false, status: 404, msg: "ไม่พบคีย์ในสต็อก" };
  if (row.revoked) return { ok: false, status: 409, msg: "คีย์ถูกระงับ" };
  if (row.status === "delivered") {
    if (row.order_id === orderId) return { ok: true, row, reused: true };
    return { ok: false, status: 409, msg: "คีย์นี้ถูกส่งให้ออเดอร์อื่นแล้ว" };
  }
  if (row.status !== "stock") return { ok: false, status: 409, msg: "คีย์นี้ไม่ได้อยู่ในสต็อก" };

  const exp = expiresAtForDuration(now, row.duration_days);
  await env.DB.prepare(
    `UPDATE lic_keys
     SET status = 'delivered', delivered_at = ?, expires_at = ?, order_id = ?, customer_ref = ?
     WHERE code = ? AND status = 'stock' AND expires_at IS NULL`,
  ).bind(now, exp, orderId, customerRef, code).run();

  const delivered = await findDeliveredByOrder(env, orderId);
  if (!delivered || delivered.code !== code) {
    return { ok: false, status: 409, msg: "ส่งคีย์ไม่สำเร็จ กรุณาลองใหม่" };
  }
  return { ok: true, row: delivered, reused: false };
}

async function deliverStockKey(env, plan, durationDays, maxSeats, orderIdValue, customerRef, now, tier = "premium") {
  const existing = await findDeliveredByOrder(env, orderIdValue);
  if (existing) return { ok: true, reused: true, row: existing };

  for (let attempt = 0; attempt < 5; attempt += 1) {
    const candidate = await env.DB.prepare(
      `SELECT code
       FROM lic_keys
       WHERE status = 'stock'
         AND revoked = 0
         AND plan = ?
         AND duration_days = ?
         AND max_seats = ?
         AND tier = ?
       ORDER BY created_at ASC
       LIMIT 1`,
    ).bind(plan, durationDays, maxSeats, resolveTier(tier)).first();

    if (!candidate) return { ok: false, status: 409, msg: "คีย์ในสต็อกหมด" };

    try {
      const result = await markDelivered(env, candidate.code, orderIdValue, customerRef, now);
      if (result.ok) return result;
    } catch (_) {
      const afterRace = await findDeliveredByOrder(env, orderIdValue);
      if (afterRace) return { ok: true, reused: true, row: afterRace };
    }
  }
  return { ok: false, status: 409, msg: "ส่งคีย์ไม่สำเร็จ กรุณาลองใหม่" };
}

async function verify(req, env) {
  const body = await readJson(req);
  const code = cleanCode(body.key);
  const hwid = cleanText(body.hwid);
  const hwidV2 = cleanText(body.hwid_v2);
  const now = Math.floor(Date.now() / 1000);
  const deny = (msg) => signPayload(env, { ok: false, msg, hwid, iat: now });

  if (!code || !hwid) return deny("ข้อมูลคีย์/HWID ไม่ครบ");

  const row = await env.DB.prepare(
    `SELECT code, plan, tier, duration_days, expires_at, max_seats, revoked, status, delivered_at
     FROM lic_keys
     WHERE code = ?`,
  ).bind(code).first();

  if (!row) return deny("คีย์ไม่ถูกต้อง");
  if (row.revoked) return deny("คีย์ถูกระงับ");

  const lifetime = isLifetimeDuration(row.duration_days);
  if (row.status === "active_on_first_use" && !row.expires_at) {
    const activeExpiresAt = expiresAtForDuration(now, row.duration_days);
    await env.DB.prepare(
      `UPDATE lic_keys
       SET status = 'delivered', expires_at = ?, delivered_at = ?
       WHERE code = ?`
    ).bind(activeExpiresAt, now, code).run();
    row.status = "delivered";
    row.expires_at = activeExpiresAt;
    row.delivered_at = now;
  }

  if (row.status !== "delivered" || (!lifetime && !row.expires_at)) return deny("คีย์นี้ยังไม่ได้ถูกส่งจากร้าน");
  if (!lifetime && now > Number(row.expires_at)) return deny("คีย์หมดอายุ");

  const keyTier = resolveTier(row.tier || "premium");
  const releaseInfo = releaseDownloadInfo(env, keyTier);
  const contentKey = cleanText(env.CONTENT_KEY);
  if (keyTier === "promax" && !/^[0-9a-fA-F]{64}$/.test(contentKey)) {
    return deny("ระบบ ProMax ยังไม่พร้อมใช้งาน กรุณาติดต่อร้าน");
  }

  const seatRows = await env.DB.prepare("SELECT hwid, hwid_v2 FROM lic_seats WHERE code = ?").bind(code).all();
  const seats = seatRows.results || [];
  const matchedSeat = seats.find(
    (seat) => seat.hwid === hwid || (hwidV2 && seat.hwid_v2 === hwidV2),
  );
  if (!matchedSeat && seats.length >= Number(row.max_seats || 1)) {
    return deny("คีย์นี้ใช้ครบจำนวนเครื่องแล้ว");
  }

  if (matchedSeat) {
    await env.DB.prepare(
      `UPDATE lic_seats
       SET last_seen = ?,
           hwid_v2 = CASE WHEN hwid_v2 IS NULL OR hwid_v2 = '' THEN ? ELSE hwid_v2 END
       WHERE code = ? AND hwid = ?`,
    ).bind(now, hwidV2 || null, code, matchedSeat.hwid).run();
  } else {
    await env.DB.prepare(
      `INSERT INTO lic_seats(code, hwid, hwid_v2, first_seen, last_seen)
       VALUES(?, ?, ?, ?, ?)`,
    ).bind(code, hwid, hwidV2 || null, now, now).run();
  }

  return signPayload(env, {
    ok: true,
    code,
    plan: row.plan,
    // "tier" stays "pro" for backward compatibility with already-shipped clients
    // that gate on tier === "pro". Real Premium/Promax tier is in "key_tier".
    tier: "pro",
    key_tier: keyTier,
    exp: row.expires_at,
    delivered_at: row.delivered_at,
    hwid,
    iat: now,
    token_exp: now + 6 * 3600,
    app_version: releaseInfo.version,
    download_url: releaseInfo.download_url,
    download_name: releaseInfo.download_name,
    zip_url: releaseInfo.zip_url,
    zip_name: releaseInfo.zip_name,
    ...(keyTier === "promax" ? { content_key: contentKey } : {}),
  });
}

async function mint(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const tier = resolveTier(body.tier);
  const durationDays = resolveDurationDays(body, 7);
  const plan = canonicalPlanCode(body.plan, tier, durationDays);
  const count = clampInt(body.count, 1, 1, 200);
  const maxSeats = clampInt(body.max_seats, 1, 1, 5);
  const prefix = cleanText(body.prefix, "JL").replace(/[^A-Z0-9]/gi, "").slice(0, 6).toUpperCase() || "JL";
  const now = Math.floor(Date.now() / 1000);
  const codes = [];

  for (let i = 0; i < count; i += 1) {
    const code = makeCode(prefix);
    await env.DB.prepare(
      `INSERT INTO lic_keys(
         code, plan, tier, duration_days, expires_at, max_seats, revoked, status,
         delivered_at, order_id, customer_ref, created_at, note
       )
       VALUES(?, ?, ?, ?, NULL, ?, 0, 'stock', NULL, NULL, NULL, ?, ?)`,
    ).bind(code, plan, tier, durationDays, maxSeats, now, cleanText(body.note)).run();
    codes.push(code);
  }
  return json({ ok: true, status: "stock", tier, codes });
}

async function deliver(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const tier = resolveTier(body.tier);
  const durationDays = resolveDurationDays(body, 7);
  const plan = canonicalPlanCode(body.plan, tier, durationDays);
  const maxSeats = clampInt(body.max_seats, 1, 1, 5);
  const orderId = cleanText(body.order_id);
  const customerRef = cleanText(body.customer_ref);
  const now = Math.floor(Date.now() / 1000);

  if (!orderId) return json({ ok: false, msg: "กรุณาใส่เลขออเดอร์" }, 400);

  const result = await deliverStockKey(env, plan, durationDays, maxSeats, orderId, customerRef, now, tier);
  if (!result.ok) return json({ ok: false, msg: result.msg }, result.status || 409);
  return json({ ok: true, reused: result.reused, key: keyReply(result.row) });
}

async function deliverKey(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const code = cleanCode(body.key);
  const orderId = cleanText(body.order_id);
  const customerRef = cleanText(body.customer_ref);
  const now = Math.floor(Date.now() / 1000);

  if (!code) return json({ ok: false, msg: "กรุณาใส่คีย์" }, 400);
  if (!orderId) return json({ ok: false, msg: "กรุณาใส่เลขออเดอร์" }, 400);

  const existing = await findDeliveredByOrder(env, orderId);
  if (existing) return json({ ok: true, reused: true, key: keyReply(existing) });

  const result = await markDelivered(env, code, orderId, customerRef, now);
  if (!result.ok) return json({ ok: false, msg: result.msg }, result.status || 409);
  return json({ ok: true, reused: result.reused, key: keyReply(result.row) });
}

async function revoke(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const code = cleanCode(body.key);
  if (!code) return json({ ok: false, msg: "กรุณาใส่คีย์" }, 400);
  await env.DB.prepare("UPDATE lic_keys SET revoked = 1 WHERE code = ?").bind(code).run();
  return json({ ok: true, code });
}

async function extendKey(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const code = cleanCode(body.key);
  if (!code) return json({ ok: false, msg: "กรุณาใส่คีย์" }, 400);
  const hours = Number(body.hours);
  if (![6, 24].includes(hours)) return json({ ok: false, msg: "ระยะเวลาไม่ถูกต้อง" }, 400);
  const seconds = hours * 3600;
  const result = await env.DB.prepare(
    "UPDATE lic_keys SET expires_at = expires_at + ?, hwid_reset_count = 0 WHERE code = ? AND duration_days != 0 AND expires_at IS NOT NULL"
  ).bind(seconds, code).run();
  if (!result.meta || result.meta.changes === 0) {
    return json({ ok: false, msg: "คีย์นี้ยังไม่เปิดใช้งาน (ไม่มีวันหมดอายุให้ต่อ)" }, 400);
  }
  return json({ ok: true, code, hours });
}

async function resetSeats(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const code = cleanCode(body.key);
  if (!code) return json({ ok: false, msg: "กรุณาใส่คีย์" }, 400);
  await env.DB.prepare("DELETE FROM lic_seats WHERE code = ?").bind(code).run();
  return json({ ok: true, code });
}

// Reset-quota ceiling per package tier. Lifetime packages (duration_days===0)
// get unlimited resets regardless of tier — checked before the tier lookup.
const RESET_QUOTA_BY_TIER = { premium: 2, promax: 5 };
const RESET_QUOTA_UNLIMITED = 999999;

function resetQuotaFor(tier, durationDays) {
  if (isLifetimeDuration(durationDays)) return RESET_QUOTA_UNLIMITED;
  return RESET_QUOTA_BY_TIER[resolveTier(tier)] ?? RESET_QUOTA_BY_TIER.premium;
}

async function resetShopDevice(req, env) {
  const user = await requireUser(req, env);
  if (!user) return authRequired();
  const body = await readJson(req);
  const code = cleanCode(body.code || body.key);
  if (!code) return json({ ok: false, msg: "กรุณาใส่คีย์" }, 400);

  const key = await env.DB.prepare(
    `SELECT lic_keys.code, lic_keys.duration_days, lic_keys.tier,
            COALESCE(lic_keys.hwid_reset_count, 0) AS hwid_reset_count
     FROM lic_keys
     WHERE lic_keys.code = ?
       AND EXISTS (
         SELECT 1
         FROM shop_orders
         WHERE shop_orders.key_code = lic_keys.code
           AND shop_orders.user_id = ?
           AND shop_orders.status = 'delivered'
       )`,
  ).bind(code, user.id).first();
  if (!key) return json({ ok: false, msg: "ไม่พบคีย์นี้ในบัญชีของคุณ" }, 404);

  const quota = resetQuotaFor(key.tier, key.duration_days);
  if (Number(key.hwid_reset_count || 0) >= quota) {
    return json({ ok: false, msg: "ใช้สิทธิ์รีเซ็ตเครื่องครบแล้ว" }, 409);
  }

  const ownershipGuard = `
    EXISTS (
      SELECT 1
      FROM shop_orders
      WHERE shop_orders.key_code = lic_keys.code
        AND shop_orders.user_id = ?
        AND shop_orders.status = 'delivered'
    )`;
  const results = await env.DB.batch([
    env.DB.prepare(
      `DELETE FROM lic_seats
       WHERE code = ?
         AND EXISTS (
           SELECT 1
           FROM lic_keys
           WHERE lic_keys.code = ?
             AND COALESCE(lic_keys.hwid_reset_count, 0) < ?
             AND ${ownershipGuard}
         )`,
    ).bind(code, code, quota, user.id),
    env.DB.prepare(
      `UPDATE lic_keys
       SET hwid_reset_count = COALESCE(hwid_reset_count, 0) + 1
       WHERE code = ?
         AND COALESCE(hwid_reset_count, 0) < ?
         AND ${ownershipGuard}`,
    ).bind(code, quota, user.id),
  ]);
  const updateResult = results[1];
  if (!updateResult?.meta || Number(updateResult.meta.changes || 0) !== 1) {
    return json({ ok: false, msg: "ใช้สิทธิ์รีเซ็ตเครื่องครบแล้ว" }, 409);
  }

  const updatedKey = await env.DB.prepare(
    "SELECT COALESCE(hwid_reset_count, 0) AS hwid_reset_count FROM lic_keys WHERE code = ?",
  ).bind(code).first();
  const resetCount = Math.min(quota, Number(updatedKey?.hwid_reset_count || 0));
  const remaining = Math.max(0, quota - resetCount);
  return json({
    ok: true,
    code,
    hwid_reset_count: resetCount,
    quota: quota >= RESET_QUOTA_UNLIMITED ? -1 : quota,
    remaining: quota >= RESET_QUOTA_UNLIMITED ? -1 : remaining,
    msg: quota >= RESET_QUOTA_UNLIMITED
      ? "รีเซ็ตเครื่องแล้ว (สิทธิ์ไม่จำกัด)"
      : `รีเซ็ตเครื่องแล้ว ใช้ได้อีก ${remaining} ครั้ง`,
  });
}

async function getSlipokAccount(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const account = await getConfig(env, "slipok_account", "1");
  const checkedAt = Math.floor(Date.now() / 1000);
  const settled = await Promise.allSettled([1, 2, 3].map(async (number) => {
    const creds = slipOkCreds(env, number);
    if (!creds.branchId || !creds.apiKey) {
      return {
        number: String(number),
        name: creds.displayName,
        configured: false,
        limit: SLIPOK_QUOTA_LIMIT,
        reserve: SLIPOK_QUOTA_RESERVE,
        checked_at: checkedAt,
      };
    }
    const quota = await callSlipOKQuota(creds);
    if (!quota.ok) {
      return {
        number: String(number),
        name: creds.displayName,
        configured: true,
        ok: false,
        error: quota.msg,
        limit: SLIPOK_QUOTA_LIMIT,
        reserve: SLIPOK_QUOTA_RESERVE,
        checked_at: checkedAt,
      };
    }
    const used = Math.max(0, quota.limit - quota.remaining + quota.overQuota);
    return {
      number: String(number),
      name: creds.displayName,
      configured: true,
      ok: true,
      used,
      remaining: quota.remaining,
      overQuota: quota.overQuota,
      special_quota: quota.specialQuota,
      end_date: quota.endDate,
      limit: quota.limit,
      reserve: SLIPOK_QUOTA_RESERVE,
      available: quota.remaining > SLIPOK_QUOTA_RESERVE,
      checked_at: checkedAt,
    };
  }));
  const accounts = settled.map((item, index) => {
    if (item.status === "fulfilled") return item.value;
    const creds = slipOkCreds(env, index + 1);
    return {
      number: String(index + 1),
      name: creds.displayName,
      configured: Boolean(creds.branchId && creds.apiKey),
      ok: false,
      error: cleanText(item.reason?.message, "อ่านโควตาไม่สำเร็จ"),
      limit: SLIPOK_QUOTA_LIMIT,
      reserve: SLIPOK_QUOTA_RESERVE,
      checked_at: checkedAt,
    };
  });
  return json({ ok: true, account, accounts, reserve: SLIPOK_QUOTA_RESERVE, checked_at: checkedAt });
}

async function setSlipokAccount(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const account = cleanText(body.account);
  if (!["1", "2", "3", "auto"].includes(account)) {
    return json({ ok: false, msg: "บัญชี SlipOK ไม่ถูกต้อง" }, 400);
  }
  await env.DB.prepare(
    "INSERT INTO app_config(key, value) VALUES('slipok_account', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
  ).bind(account).run();
  return json({ ok: true, account });
}

async function stock(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const rows = await env.DB.prepare(
    `SELECT plan, tier, duration_days, max_seats, COUNT(*) AS count
     FROM lic_keys
     WHERE status = 'stock' AND revoked = 0
     GROUP BY plan, tier, duration_days, max_seats
     ORDER BY tier, plan, duration_days, max_seats`,
  ).all();
  return json({ ok: true, stock: rows.results || [] });
}

async function listKeys(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const rows = await env.DB.prepare(
    `SELECT lic_keys.code, lic_keys.plan, lic_keys.tier, lic_keys.duration_days, lic_keys.expires_at,
            lic_keys.max_seats, lic_keys.revoked, lic_keys.status, lic_keys.delivered_at,
            lic_keys.order_id, lic_keys.customer_ref, lic_keys.created_at, lic_keys.note,
            COUNT(lic_seats.hwid) AS seat_count
     FROM lic_keys
     LEFT JOIN lic_seats ON lic_seats.code = lic_keys.code
     GROUP BY lic_keys.code
     ORDER BY lic_keys.created_at DESC
     LIMIT 300`,
  ).all();
  return json({ ok: true, keys: rows.results || [] });
}

async function shopPlans(env) {
  const rows = await env.DB.prepare(
    `SELECT plan, duration_days, max_seats, COUNT(*) AS count
     FROM lic_keys
     WHERE status = 'stock' AND revoked = 0
     GROUP BY plan, duration_days, max_seats`,
  ).all();
  const stockRows = rows.results || [];
  const plans = Object.values(SHOP_PLANS).map((plan) => {
    const stockCount = stockRows
      .filter((row) =>
        row.plan === plan.code &&
        Number(row.duration_days) === Number(plan.duration_days) &&
        Number(row.max_seats || 1) === Number(plan.max_seats || 1)
      )
      .reduce((sum, row) => sum + Number(row.count || 0), 0);
    return { ...plan, stock_count: stockCount };
  });
  return json({ ok: true, plans });
}

async function shopActivity(env) {
  const rows = await env.DB.prepare(
    `SELECT shop_orders.plan_label, shop_orders.approved_at, shop_orders.created_at,
            shop_orders.customer_ref, shop_users.username
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     WHERE shop_orders.status = 'delivered'
     ORDER BY shop_orders.approved_at DESC
     LIMIT 20`,
  ).all();
  const activity = (rows.results || []).map((row) => ({
    name: maskCustomerName(row.customer_ref || row.username),
    plan_label: row.plan_label,
    at: row.approved_at || row.created_at,
  }));
  return json({ ok: true, activity });
}

async function registerUser(req, env) {
  const body = await readJson(req);
  const username = cleanUsername(body.username);
  const password = cleanText(body.password);
  const customerRef = cleanText(body.customer_ref || body.line || body.contact).slice(0, 120);
  const now = Math.floor(Date.now() / 1000);

  if (username.length < 3) return json({ ok: false, msg: "ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร" }, 400);
  if (password.length < 6) return json({ ok: false, msg: "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร" }, 400);

  const passwordHash = await hashPassword(password);
  try {
    await env.DB.prepare(
      `INSERT INTO shop_users(username, password_hash, customer_ref, created_at, last_login_at)
       VALUES(?, ?, ?, ?, ?)`,
    ).bind(username, passwordHash, customerRef, now, now).run();
  } catch (_) {
    return json({ ok: false, msg: "ชื่อผู้ใช้นี้ถูกใช้แล้ว" }, 409);
  }

  const user = await env.DB.prepare(
    "SELECT id, username, customer_ref FROM shop_users WHERE username = ?",
  ).bind(username).first();
  return json({ ok: true, ...(await sessionReply(env, user)) });
}

async function loginUser(req, env) {
  const body = await readJson(req);
  const username = cleanUsername(body.username);
  const password = cleanText(body.password);
  const now = Math.floor(Date.now() / 1000);
  const user = await env.DB.prepare(
    "SELECT id, username, password_hash, customer_ref FROM shop_users WHERE username = ?",
  ).bind(username).first();

  if (!user || !(await verifyPassword(password, user.password_hash))) {
    return json({ ok: false, msg: "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง" }, 401);
  }

  await env.DB.prepare("UPDATE shop_users SET last_login_at = ? WHERE id = ?").bind(now, user.id).run();
  return json({ ok: true, ...(await sessionReply(env, user)) });
}

async function me(req, env) {
  const user = await requireUser(req, env);
  if (!user) return authRequired();
  return json({ ok: true, user: { id: user.id, username: user.username, customer_ref: user.customer_ref } });
}

async function createOrder(req, env) {
  const user = await requireUser(req, env);
  if (!user) return authRequired();
  const body = await readJson(req);
  const plan = resolveShopPlan(body.plan);
  const slipName = cleanText(body.slip_name).slice(0, 160);
  let slipMime = cleanText(body.slip_mime, "image/jpeg").slice(0, 80);
  let slipB64 = cleanText(body.slip_b64);
  const customerRef = cleanText(body.customer_ref || user.customer_ref || user.username).slice(0, 160);
  const now = Math.floor(Date.now() / 1000);

  const dataUrl = slipB64.match(/^data:([^;]+);base64,(.+)$/);
  if (dataUrl) {
    slipMime = dataUrl[1].slice(0, 80);
    slipB64 = dataUrl[2];
  }
  slipB64 = slipB64.replace(/\s+/g, "");

  if (!slipName && !slipB64) return json({ ok: false, msg: "กรุณาอัปโหลดสลิป" }, 400);
  if (slipB64 && !/^[A-Za-z0-9+/=]+$/.test(slipB64)) return json({ ok: false, msg: "ไฟล์สลิปไม่ถูกต้อง" }, 400);
  if (slipB64.length > 850000) return json({ ok: false, msg: "ไฟล์สลิปใหญ่เกินไป" }, 413);

  const slipCheck = await checkSlipOK(env, {
    slipName,
    slipMime,
    slipB64,
    amount: plan.amount,
  });
  if (slipCheck.enabled && !slipCheck.ok) {
    return json({ ok: false, msg: "ตรวจสลิปไม่ผ่าน: " + slipCheck.msg }, slipCheck.status || 400);
  }

  const id = orderId();
  let status = "pending_review";
  let keyCode = null;
  let approvedAt = null;
  let adminNote = null;
  let canAutoDeliver = slipCheck.enabled;

  if (slipCheck.enabled) {
    const transRef = cleanText(slipCheck.trans_ref).trim().toUpperCase();
    if (transRef) {
      try {
        const claim = await env.DB.prepare(
          "INSERT OR IGNORE INTO used_trans_refs(trans_ref, order_id, account, amount, used_at) VALUES(?,?,?,?,?)",
        ).bind(transRef, id, slipCheck.account || "", slipCheck.amount ?? null, now).run();
        if (!claim.meta || claim.meta.changes === 0) {
          return json({ ok: false, msg: "สลิปนี้ถูกใช้ไปแล้ว ไม่สามารถใช้ซ้ำได้" }, 409);
        }
      } catch (_) {
        canAutoDeliver = false;
      }
    } else {
      canAutoDeliver = false;
    }
  }

  if (slipCheck.enabled && !canAutoDeliver) {
    status = "payment_verified";
    adminNote = `SlipOK ผ่านแต่ตรวจสลิปซ้ำไม่ได้ (ไม่มี transRef/DB) -> ตรวจด้วยมือ: ${slipCheck.msg}`;
  }

  if (canAutoDeliver) {
    status = "payment_verified";
    adminNote = `SlipOK: ${slipCheck.msg}${slipCheck.trans_ref ? " / transRef " + slipCheck.trans_ref : ""}`;

    // Auto-approve and deliver key!
    const deliverResult = await deliverStockKey(
      env,
      plan.code,
      Number(plan.duration_days),
      Number(plan.max_seats || 1),
      id,
      customerRef,
      now,
      plan.tier
    );
    if (deliverResult.ok) {
      status = "delivered";
      keyCode = deliverResult.row.code;
      approvedAt = now;
      adminNote = `Auto-Approved by SlipOK: ${slipCheck.msg}${slipCheck.trans_ref ? " / transRef " + slipCheck.trans_ref : ""}`;
    } else {
      adminNote = `SlipOK OK but Stock Empty: ${slipCheck.msg}`;
    }
  }

  await env.DB.prepare(
    `INSERT INTO shop_orders(
       id, user_id, plan, plan_label, duration_days, amount, max_seats, status,
       customer_ref, slip_name, slip_mime, slip_b64, slip_uploaded_at,
       key_code, created_at, approved_at, rejected_at, admin_note
     )
     VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)`,
  ).bind(
    id,
    user.id,
    plan.code,
    plan.label,
    plan.duration_days,
    plan.amount,
    plan.max_seats,
    status,
    customerRef,
    slipName,
    slipMime,
    slipB64,
    now,
    keyCode,
    now,
    approvedAt,
    adminNote,
  ).run();

  const row = await env.DB.prepare(
    `SELECT shop_orders.*, shop_users.username
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     WHERE shop_orders.id = ?`,
  ).bind(id).first();
  return json({ ok: true, order: shopOrderReply(row) });
}

function isDiscordShop(req, env) {
  const token = cleanText(req.headers.get("x-discord-shop-token"));
  return Boolean(env.DISCORD_SHOP_TOKEN && token && token === env.DISCORD_SHOP_TOKEN);
}

function discordShopUnauthorized() {
  return json({ ok: false, msg: "Discord Shop token invalid" }, 401);
}

function discordOrderId(value) {
  const raw = cleanText(value).replace(/[^A-Za-z0-9_.-]/g, "").slice(0, 90);
  return raw ? `DISCORD-${raw}` : "";
}

async function ensureDiscordShopUser(env, now) {
  const tokenHash = await sha256Hex(env.DISCORD_SHOP_TOKEN || "");
  const username = `dc_${tokenHash.slice(0, 24)}`;
  let user = await env.DB.prepare(
    "SELECT id, username, customer_ref FROM shop_users WHERE username = ?",
  ).bind(username).first();
  if (user) return user;

  const passwordHash = await hashPassword(`discord-disabled-${randomHex(32)}`);
  await env.DB.prepare(
    "INSERT OR IGNORE INTO shop_users(username, password_hash, customer_ref, created_at) VALUES(?,?,?,?)",
  ).bind(username, passwordHash, "Discord Shop Service", now).run();
  user = await env.DB.prepare(
    "SELECT id, username, customer_ref FROM shop_users WHERE username = ?",
  ).bind(username).first();
  if (!user) throw new Error("Discord Shop user unavailable");
  return user;
}

async function discordShopPlans(req, env) {
  if (!isDiscordShop(req, env)) return discordShopUnauthorized();
  const rows = await env.DB.prepare(
    `SELECT plan, tier, duration_days, max_seats, COUNT(*) AS count
     FROM lic_keys
     WHERE status = 'stock' AND revoked = 0
     GROUP BY plan, tier, duration_days, max_seats`,
  ).all();
  const stockRows = rows.results || [];
  const plans = Object.values(SHOP_PLANS).map((plan) => {
    const stockCount = stockRows
      .filter((row) =>
        row.plan === plan.code &&
        resolveTier(row.tier) === resolveTier(plan.tier) &&
        Number(row.duration_days) === Number(plan.duration_days) &&
        Number(row.max_seats || 1) === Number(plan.max_seats || 1)
      )
      .reduce((sum, row) => sum + Number(row.count || 0), 0);
    return { ...plan, stock_count: stockCount };
  });
  return json({
    ok: true,
    plans,
    payment: { qr_url: `${new URL(req.url).origin}/assets/payment_qr.jpg` },
  });
}

async function discordOrderRow(env, id) {
  return env.DB.prepare(
    `SELECT shop_orders.*, shop_users.username
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     WHERE shop_orders.id = ?`,
  ).bind(id).first();
}

async function discordKeyRow(env, code) {
  if (!code) return null;
  return env.DB.prepare(
    `SELECT code, plan, tier, duration_days, expires_at, max_seats, revoked, status,
            delivered_at, order_id, customer_ref
     FROM lic_keys
     WHERE code = ?`,
  ).bind(code).first();
}

function discordDeliveredReply(env, order, key, reused = false) {
  const tier = resolveTier(key?.tier || (String(order?.plan || "").includes("promax") ? "promax" : "premium"));
  return {
    ok: true,
    reused,
    order: order ? shopOrderReply(order) : {
      id: key?.order_id || "",
      plan: key?.plan || "",
      plan_label: key?.plan || "",
      duration_days: key?.duration_days,
      status: "delivered",
      key_code: key?.code || "",
    },
    key: keyReply(key),
    release: { tier, ...releaseDownloadInfo(env, tier) },
  };
}

async function claimDiscordRole(req, env) {
  if (!isDiscordShop(req, env)) return discordShopUnauthorized();
  const body = await readJson(req);
  const code = cleanCode(body.code);
  const discordUserId = cleanText(body.discord_user_id);
  const now = Math.floor(Date.now() / 1000);

  if (!code) return json({ ok: false, msg: "คีย์ไม่ถูกต้อง" }, 400);
  if (!/^\d{17,20}$/.test(discordUserId)) {
    return json({ ok: false, msg: "Discord identity invalid" }, 400);
  }

  const key = await discordKeyRow(env, code);
  if (!key) return json({ ok: false, msg: "คีย์ไม่ถูกต้อง" }, 404);
  if (key.revoked) return json({ ok: false, msg: "คีย์ถูกระงับ" }, 409);
  if (key.status !== "delivered") return json({ ok: false, msg: "คีย์นี้ยังไม่ได้ถูกส่งจากร้าน" }, 409);

  const lifetime = isLifetimeDuration(key.duration_days);
  if (!lifetime && key.expires_at && now > Number(key.expires_at)) {
    return json({ ok: false, msg: "คีย์หมดอายุ", expired: true }, 409);
  }

  const tier = resolveTier(key.tier);
  const existing = await env.DB.prepare(
    "SELECT discord_user_id FROM discord_roles WHERE code = ?",
  ).bind(code).first();

  if (existing && existing.discord_user_id !== discordUserId) {
    return json({ ok: false, msg: "คีย์นี้ถูกใช้รับยศไปแล้วโดยบัญชี Discord อื่น" }, 409);
  }

  if (existing) {
    await env.DB.prepare(
      "UPDATE discord_roles SET tier = ?, is_lifetime = ?, last_checked_at = ? WHERE code = ?",
    ).bind(tier, lifetime ? 1 : 0, now, code).run();
  } else {
    await env.DB.prepare(
      `INSERT INTO discord_roles(code, discord_user_id, tier, is_lifetime, assigned_at, last_checked_at)
       VALUES(?, ?, ?, ?, ?, ?)`,
    ).bind(code, discordUserId, tier, lifetime ? 1 : 0, now, now).run();
  }

  return json({ ok: true, tier, is_lifetime: lifetime, expires_at: key.expires_at || null });
}

async function createDiscordShopOrder(req, env) {
  if (!isDiscordShop(req, env)) return discordShopUnauthorized();
  const body = await readJson(req);
  const planCode = cleanText(body.plan).toLowerCase();
  const plan = SHOP_PLANS[planCode];
  const id = discordOrderId(body.request_id);
  const discordUserId = cleanText(body.discord_user_id);
  const discordUsername = cleanText(body.discord_username).replace(/[\r\n\t]+/g, " ").slice(0, 80);
  const guildId = cleanText(body.guild_id);
  const slipName = cleanText(body.slip_name, "slip.jpg").slice(0, 160);
  const slipMime = cleanText(body.slip_mime, "image/jpeg").toLowerCase().slice(0, 80);
  const slipB64 = cleanText(body.slip_b64).replace(/\s+/g, "");
  const now = Math.floor(Date.now() / 1000);

  if (!plan) return json({ ok: false, msg: "แพ็กเกจไม่ถูกต้อง" }, 400);
  if (!id) return json({ ok: false, msg: "request_id invalid" }, 400);
  if (!/^\d{17,20}$/.test(discordUserId) || !/^\d{17,20}$/.test(guildId)) {
    return json({ ok: false, msg: "Discord identity invalid" }, 400);
  }
  if (!/^image\/(?:jpeg|jpg|png|webp|jfif)$/i.test(slipMime)) {
    return json({ ok: false, msg: "รองรับเฉพาะไฟล์รูป JPG, PNG หรือ WEBP" }, 400);
  }
  if (!slipB64 || !/^[A-Za-z0-9+/=]+$/.test(slipB64)) {
    return json({ ok: false, msg: "ไฟล์สลิปไม่ถูกต้อง" }, 400);
  }
  if (slipB64.length > 8 * 1024 * 1024) {
    return json({ ok: false, msg: "ไฟล์สลิปใหญ่เกิน 6 MB" }, 413);
  }

  const existingOrder = await discordOrderRow(env, id);
  if (existingOrder) {
    if (existingOrder.status === "delivered" && existingOrder.key_code) {
      const existingKey = await discordKeyRow(env, existingOrder.key_code);
      if (existingKey) return json(discordDeliveredReply(env, existingOrder, existingKey, true));
    }
    return json({ ok: false, msg: "คำสั่งซื้อนี้ถูกรับแล้ว", order: shopOrderReply(existingOrder) }, 409);
  }

  const deliveredBeforeOrder = await findDeliveredByOrder(env, id);
  if (deliveredBeforeOrder) {
    return json(discordDeliveredReply(env, null, deliveredBeforeOrder, true));
  }

  const stock = await env.DB.prepare(
    `SELECT code FROM lic_keys
     WHERE status = 'stock' AND revoked = 0 AND plan = ? AND tier = ?
       AND duration_days = ? AND max_seats = ?
     ORDER BY created_at ASC LIMIT 1`,
  ).bind(plan.code, resolveTier(plan.tier), plan.duration_days, plan.max_seats).first();
  if (!stock) return json({ ok: false, msg: "คีย์ในสต็อกแพ็กเกจนี้หมด" }, 409);

  const slipCheck = await checkSlipOK(env, {
    slipName,
    slipMime,
    slipB64,
    amount: plan.amount,
  });
  if (!slipCheck.enabled) {
    return json({ ok: false, msg: "SlipOK is not configured" }, 503);
  }
  if (!slipCheck.ok) {
    return json({ ok: false, msg: "ตรวจสลิปไม่ผ่าน: " + slipCheck.msg }, slipCheck.status || 400);
  }

  const verifiedAmount = Number(slipCheck.amount);
  if (!Number.isFinite(verifiedAmount) || Math.abs(verifiedAmount - Number(plan.amount)) > 0.001) {
    return json({ ok: false, msg: `ยอดในสลิปไม่ตรงกับแพ็กเกจ (ต้องชำระ ${plan.amount} บาท)` }, 400);
  }

  const transRef = cleanText(slipCheck.trans_ref).trim().toUpperCase();
  if (!transRef) return json({ ok: false, msg: "SlipOK response has no transRef" }, 502);
  const claim = await env.DB.prepare(
    "INSERT OR IGNORE INTO used_trans_refs(trans_ref, order_id, account, amount, used_at) VALUES(?,?,?,?,?)",
  ).bind(transRef, id, slipCheck.account || "", slipCheck.amount ?? null, now).run();
  if (!claim.meta || claim.meta.changes === 0) {
    const used = await env.DB.prepare("SELECT order_id FROM used_trans_refs WHERE trans_ref = ?").bind(transRef).first();
    if (!used || used.order_id !== id) {
      return json({ ok: false, msg: "สลิปนี้ถูกใช้ไปแล้ว ไม่สามารถใช้ซ้ำได้" }, 409);
    }
  }

  const customerRef = `Discord ${discordUsername || discordUserId} (${discordUserId})`.slice(0, 160);
  const user = await ensureDiscordShopUser(env, now);
  const deliverResult = await deliverStockKey(
    env,
    plan.code,
    plan.duration_days,
    plan.max_seats,
    id,
    customerRef,
    now,
    plan.tier,
  );
  const delivered = Boolean(deliverResult.ok);
  const keyCode = delivered ? deliverResult.row.code : null;
  const status = delivered ? "delivered" : "payment_verified";
  const approvedAt = delivered ? now : null;
  const adminNote = delivered
    ? `Discord Auto-Approved by SlipOK: ${slipCheck.msg} / account ${slipCheck.account || "?"}${transRef ? " / transRef " + transRef : ""}`
    : `Discord SlipOK OK but Stock Empty: ${slipCheck.msg}${transRef ? " / transRef " + transRef : ""}`;

  await env.DB.prepare(
    `INSERT OR IGNORE INTO shop_orders(
       id, user_id, plan, plan_label, duration_days, amount, max_seats, status,
       customer_ref, slip_name, slip_mime, slip_b64, slip_uploaded_at,
       key_code, created_at, approved_at, rejected_at, admin_note
     ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)`,
  ).bind(
    id,
    user.id,
    plan.code,
    plan.label,
    plan.duration_days,
    plan.amount,
    plan.max_seats,
    status,
    customerRef,
    slipName,
    slipMime,
    slipB64,
    now,
    keyCode,
    now,
    approvedAt,
    adminNote,
  ).run();

  const order = await discordOrderRow(env, id);
  if (!delivered) {
    return json({
      ok: false,
      payment_verified: true,
      order: shopOrderReply(order),
      msg: "ชำระเงินผ่านแล้ว แต่สต็อกเพิ่งหมด ระบบบันทึกออเดอร์ให้ผู้ดูแลแล้ว",
    }, 409);
  }
  return json(discordDeliveredReply(env, order, deliverResult.row, deliverResult.reused));
}

async function myOrders(req, env) {
  const user = await requireUser(req, env);
  if (!user) return authRequired();
  const rows = await env.DB.prepare(
    `SELECT shop_orders.*, shop_users.username,
            lic_keys.duration_days AS key_duration_days,
            lic_keys.tier AS key_tier,
            COALESCE(lic_keys.hwid_reset_count, 0) AS hwid_reset_count
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     LEFT JOIN lic_keys ON lic_keys.code = shop_orders.key_code
     WHERE shop_orders.user_id = ?
     ORDER BY shop_orders.created_at DESC
     LIMIT 100`,
  ).bind(user.id).all();
  return json({ ok: true, orders: (rows.results || []).map((row) => shopOrderReply(row)) });
}

async function myGifts(req, env) {
  const user = await requireUser(req, env);
  if (!user) return authRequired();
  const rows = await env.DB.prepare(
    `SELECT shop_gifts.*, lic_keys.expires_at, lic_keys.revoked
     FROM shop_gifts
     JOIN lic_keys ON lic_keys.code = shop_gifts.code
     WHERE shop_gifts.user_id = ?
     ORDER BY shop_gifts.created_at DESC`,
  ).bind(user.id).all();
  return json({ ok: true, gifts: rows.results || [] });
}

async function downloadInfo(req, env) {
  const user = await requireUser(req, env);
  if (!user) return authRequired();
  const now = Math.floor(Date.now() / 1000);
  const row = await env.DB.prepare(
    `SELECT shop_orders.*, shop_users.username, lic_keys.tier AS key_tier
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     LEFT JOIN lic_keys ON lic_keys.code = shop_orders.key_code
     WHERE shop_orders.user_id = ? AND shop_orders.status = 'delivered'
       AND (lic_keys.duration_days = 0 OR lic_keys.expires_at IS NULL OR lic_keys.expires_at > ?)
     ORDER BY
       CASE WHEN lic_keys.tier = 'promax' OR shop_orders.plan LIKE '%promax%' THEN 0 ELSE 1 END,
       shop_orders.approved_at DESC
     LIMIT 1`,
  ).bind(user.id, now).first();
  if (!row) return json({ ok: false, msg: "ยังไม่มีออเดอร์ที่อนุมัติแล้ว" }, 403);
  // ยึด tier ของคีย์จริงก่อน (เผื่อกรณี admin จ่ายคีย์ promax ให้ออเดอร์ที่ชื่อ plan ไม่มี promax)
  const isPromax = row.key_tier === "promax" || (row.plan && row.plan.includes("promax"));
  const tier = isPromax ? "promax" : "premium";
  const releaseInfo = releaseDownloadInfo(env, tier);
  const resp = {
    ok: true,
    version: releaseInfo.version,
    download_url: releaseInfo.download_url,
    download_name: releaseInfo.download_name,
    zip_url: releaseInfo.zip_url,
    zip_name: releaseInfo.zip_name,
    order: shopOrderReply(row),
  };
  // ProMax เป็น tier สูงกว่า -> เข้าถึง Premium ได้ด้วย แนบข้อมูลโหลด Premium เพิ่ม
  if (isPromax) {
    const premium = releaseDownloadInfo(env, "premium");
    resp.premium_download = {
      version: premium.version,
      download_url: premium.download_url,
      download_name: premium.download_name,
      zip_url: premium.zip_url,
      zip_name: premium.zip_name,
    };
  }
  return json(resp);
}

async function listShopOrders(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const rows = await env.DB.prepare(
    `SELECT shop_orders.*, shop_users.username
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     ORDER BY shop_orders.created_at DESC
     LIMIT 300`,
  ).all();
  return json({ ok: true, orders: (rows.results || []).map((row) => shopOrderReply(row)) });
}

const BANGKOK_OFFSET_SECONDS = 7 * 60 * 60;

function accountingBoundaries(now = Math.floor(Date.now() / 1000)) {
  const today = Math.floor((now + BANGKOK_OFFSET_SECONDS) / 86400) * 86400 - BANGKOK_OFFSET_SECONDS;
  const shifted = new Date((now + BANGKOK_OFFSET_SECONDS) * 1000);
  const month = Math.floor(Date.UTC(shifted.getUTCFullYear(), shifted.getUTCMonth(), 1) / 1000) - BANGKOK_OFFSET_SECONDS;
  return {
    now,
    today,
    last7: today - 6 * 86400,
    month,
    last30: today - 29 * 86400,
  };
}

function accountingPeriod(revenue, orders) {
  return {
    revenue: Number(revenue || 0),
    orders: Number(orders || 0),
  };
}

async function getAccounting(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const boundary = accountingBoundaries();
  const [summary, tierResult, dailyResult] = await Promise.all([
    env.DB.prepare(
      `SELECT
         COALESCE(SUM(CASE WHEN approved_at >= ? THEN amount ELSE 0 END), 0) AS today_revenue,
         COALESCE(SUM(CASE WHEN approved_at >= ? THEN 1 ELSE 0 END), 0) AS today_orders,
         COALESCE(SUM(CASE WHEN approved_at >= ? THEN amount ELSE 0 END), 0) AS seven_day_revenue,
         COALESCE(SUM(CASE WHEN approved_at >= ? THEN 1 ELSE 0 END), 0) AS seven_day_orders,
         COALESCE(SUM(CASE WHEN approved_at >= ? THEN amount ELSE 0 END), 0) AS month_revenue,
         COALESCE(SUM(CASE WHEN approved_at >= ? THEN 1 ELSE 0 END), 0) AS month_orders,
         COALESCE(SUM(amount), 0) AS total_revenue,
         COUNT(*) AS total_orders
       FROM shop_orders
       WHERE status = 'delivered' AND approved_at IS NOT NULL`,
    ).bind(boundary.today, boundary.today, boundary.last7, boundary.last7, boundary.month, boundary.month).first(),
    env.DB.prepare(
      `SELECT
         CASE WHEN lic_keys.tier = 'promax' OR shop_orders.plan LIKE '%promax%' THEN 'promax' ELSE 'premium' END AS tier,
         COALESCE(SUM(CASE WHEN shop_orders.approved_at >= ? THEN shop_orders.amount ELSE 0 END), 0) AS today_revenue,
         COALESCE(SUM(CASE WHEN shop_orders.approved_at >= ? THEN 1 ELSE 0 END), 0) AS today_orders,
         COALESCE(SUM(CASE WHEN shop_orders.approved_at >= ? THEN shop_orders.amount ELSE 0 END), 0) AS seven_day_revenue,
         COALESCE(SUM(CASE WHEN shop_orders.approved_at >= ? THEN 1 ELSE 0 END), 0) AS seven_day_orders,
         COALESCE(SUM(CASE WHEN shop_orders.approved_at >= ? THEN shop_orders.amount ELSE 0 END), 0) AS month_revenue,
         COALESCE(SUM(CASE WHEN shop_orders.approved_at >= ? THEN 1 ELSE 0 END), 0) AS month_orders,
         COALESCE(SUM(shop_orders.amount), 0) AS total_revenue,
         COUNT(*) AS total_orders
       FROM shop_orders
       LEFT JOIN lic_keys ON lic_keys.code = shop_orders.key_code
       WHERE shop_orders.status = 'delivered' AND shop_orders.approved_at IS NOT NULL
       GROUP BY tier
       ORDER BY tier`,
    ).bind(boundary.today, boundary.today, boundary.last7, boundary.last7, boundary.month, boundary.month).all(),
    env.DB.prepare(
      `SELECT
         date(approved_at + 25200, 'unixepoch') AS sale_date,
         COALESCE(SUM(amount), 0) AS revenue,
         COUNT(*) AS orders
       FROM shop_orders
       WHERE status = 'delivered' AND approved_at >= ?
       GROUP BY sale_date
       ORDER BY sale_date DESC`,
    ).bind(boundary.last30).all(),
  ]);

  const row = summary || {};
  const tiers = { premium: null, promax: null };
  for (const item of tierResult.results || []) {
    const tier = item.tier === "promax" ? "promax" : "premium";
    tiers[tier] = {
      today: accountingPeriod(item.today_revenue, item.today_orders),
      last_7_days: accountingPeriod(item.seven_day_revenue, item.seven_day_orders),
      current_month: accountingPeriod(item.month_revenue, item.month_orders),
      all_time: accountingPeriod(item.total_revenue, item.total_orders),
    };
  }
  for (const tier of ["premium", "promax"]) {
    if (!tiers[tier]) {
      tiers[tier] = {
        today: accountingPeriod(0, 0),
        last_7_days: accountingPeriod(0, 0),
        current_month: accountingPeriod(0, 0),
        all_time: accountingPeriod(0, 0),
      };
    }
  }

  return json({
    ok: true,
    timezone: "Asia/Bangkok",
    generated_at: boundary.now,
    periods: {
      today: accountingPeriod(row.today_revenue, row.today_orders),
      last_7_days: accountingPeriod(row.seven_day_revenue, row.seven_day_orders),
      current_month: accountingPeriod(row.month_revenue, row.month_orders),
      all_time: accountingPeriod(row.total_revenue, row.total_orders),
    },
    tiers,
    daily_30_days: (dailyResult.results || []).map((item) => ({
      date: item.sale_date,
      revenue: Number(item.revenue || 0),
      orders: Number(item.orders || 0),
    })),
  });
}

function accountingCsvCell(value) {
  let text = String(value ?? "");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function bangkokDateTime(epoch) {
  const number = Number(epoch || 0);
  if (!number) return "";
  return new Date((number + BANGKOK_OFFSET_SECONDS) * 1000).toISOString().slice(0, 19).replace("T", " ");
}

async function exportAccountingCsv(req, env, url) {
  if (!isAdmin(req, env)) return unauthorized();
  const period = cleanText(url.searchParams.get("period"), "month").toLowerCase();
  const boundary = accountingBoundaries();
  const starts = {
    today: boundary.today,
    "7d": boundary.last7,
    month: boundary.month,
    all: 0,
  };
  if (!(period in starts)) return json({ ok: false, msg: "ช่วงเวลารายงานไม่ถูกต้อง" }, 400);
  const rows = await env.DB.prepare(
    `SELECT
       shop_orders.id,
       shop_orders.approved_at,
       CASE WHEN lic_keys.tier = 'promax' OR shop_orders.plan LIKE '%promax%' THEN 'ProMax' ELSE 'Premium' END AS tier,
       shop_orders.plan,
       shop_orders.plan_label,
       shop_orders.amount,
       shop_orders.customer_ref,
       shop_users.username,
       payment.account AS slipok_account,
       payment.trans_ref
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     LEFT JOIN lic_keys ON lic_keys.code = shop_orders.key_code
     LEFT JOIN (
       SELECT order_id, MAX(account) AS account, MAX(trans_ref) AS trans_ref
       FROM used_trans_refs
       GROUP BY order_id
     ) AS payment ON payment.order_id = shop_orders.id
     WHERE shop_orders.status = 'delivered'
       AND shop_orders.approved_at IS NOT NULL
       AND shop_orders.approved_at >= ?
     ORDER BY shop_orders.approved_at DESC`,
  ).bind(starts[period]).all();
  const header = ["เลขออเดอร์", "วันที่อนุมัติ (Asia/Bangkok)", "รุ่น", "รหัสแพ็ก", "ชื่อแพ็ก", "รายได้ (บาท)", "ลูกค้า", "บัญชีเว็บ", "บัญชี SlipOK", "เลขอ้างอิงสลิป"];
  const lines = [header.map(accountingCsvCell).join(",")];
  for (const row of rows.results || []) {
    lines.push([
      row.id,
      bangkokDateTime(row.approved_at),
      row.tier,
      row.plan,
      row.plan_label,
      Number(row.amount || 0),
      row.customer_ref,
      row.username,
      row.slipok_account,
      row.trans_ref,
    ].map(accountingCsvCell).join(","));
  }
  return new Response(`\uFEFF${lines.join("\r\n")}`, {
    headers: {
      ...CORS_HEADERS,
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="jlcookie-accounting-${period}.csv"`,
      "cache-control": "no-store",
    },
  });
}

async function shopOrderSlip(req, env, url) {
  if (!isAdmin(req, env)) return unauthorized();
  const id = cleanText(url.searchParams.get("order_id"));
  if (!id) return json({ ok: false, msg: "กรุณาใส่เลขออเดอร์" }, 400);
  const row = await env.DB.prepare(
    `SELECT shop_orders.*, shop_users.username
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     WHERE shop_orders.id = ?`,
  ).bind(id).first();
  if (!row) return json({ ok: false, msg: "ไม่พบออเดอร์" }, 404);
  return json({ ok: true, order: shopOrderReply(row, true) });
}

async function approveShopOrder(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const id = cleanText(body.order_id);
  const now = Math.floor(Date.now() / 1000);
  if (!id) return json({ ok: false, msg: "กรุณาใส่เลขออเดอร์" }, 400);

  const order = await env.DB.prepare(
    `SELECT shop_orders.*, shop_users.username
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     WHERE shop_orders.id = ?`,
  ).bind(id).first();
  if (!order) return json({ ok: false, msg: "ไม่พบออเดอร์" }, 404);
  if (order.status === "delivered" && order.key_code) return json({ ok: true, reused: true, order: shopOrderReply(order) });
  if (order.status === "rejected") return json({ ok: false, msg: "ออเดอร์นี้ถูกปฏิเสธแล้ว" }, 409);

  const tier = resolveTier(body.tier);
  const result = await deliverStockKey(
    env,
    order.plan,
    Number(order.duration_days),
    Number(order.max_seats || 1),
    order.id,
    order.customer_ref || order.username,
    now,
    tier
  );
  if (!result.ok) return json({ ok: false, msg: result.msg }, result.status || 409);

  await env.DB.prepare(
    `UPDATE shop_orders
     SET status = 'delivered', key_code = ?, approved_at = ?, admin_note = ?
     WHERE id = ?`,
  ).bind(result.row.code, now, cleanText(body.admin_note), id).run();

  const updated = await env.DB.prepare(
    `SELECT shop_orders.*, shop_users.username
     FROM shop_orders
     JOIN shop_users ON shop_users.id = shop_orders.user_id
     WHERE shop_orders.id = ?`,
  ).bind(id).first();
  return json({ ok: true, reused: result.reused, order: shopOrderReply(updated), key: keyReply(result.row) });
}

async function rejectShopOrder(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const id = cleanText(body.order_id);
  const note = cleanText(body.admin_note || body.note).slice(0, 300);
  const now = Math.floor(Date.now() / 1000);
  if (!id) return json({ ok: false, msg: "กรุณาใส่เลขออเดอร์" }, 400);
  await env.DB.prepare(
    `UPDATE shop_orders
     SET status = 'rejected', rejected_at = ?, admin_note = ?
     WHERE id = ? AND status != 'delivered'`,
  ).bind(now, note, id).run();
  return json({ ok: true, order_id: id });
}

async function createFreeLicenseKey(env, { tier, durationDays, plan, maxSeats, note, customerRef, prefix = "FREE" }) {
  const now = Math.floor(Date.now() / 1000);
  const code = makeCode(prefix);
  await env.DB.prepare(
    `INSERT INTO lic_keys(
       code, plan, tier, duration_days, expires_at, max_seats, revoked, status,
       delivered_at, order_id, customer_ref, created_at, note
     )
      VALUES(?, ?, ?, ?, NULL, ?, 0, 'active_on_first_use', NULL, NULL, ?, ?, ?)`
  ).bind(code, plan, tier, durationDays, maxSeats, customerRef, now, note).run();
  return { code, now };
}

async function generateFreeKey(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const tier = resolveTier(body.tier);
  const durationDays = resolveDurationDays(body, 7);
  const plan = canonicalPlanCode(body.plan, tier, durationDays);
  const maxSeats = Number(body.max_seats || 1);
  const note = cleanText(body.note, "Free Key").slice(0, 300);
  const created = await createFreeLicenseKey(env, {
    tier,
    durationDays,
    plan,
    maxSeats,
    note,
    customerRef: "Free Key",
  });

  return json({ ok: true, code: created.code, tier });
}

async function sendGift(req, env) {
  if (!isAdmin(req, env)) return unauthorized();
  const body = await readJson(req);
  const username = cleanText(body.username).trim();
  if (!username) return json({ ok: false, msg: "กรุณาใส่ชื่อลูกค้า" }, 400);
  const user = await env.DB.prepare(
    "SELECT id, username, customer_ref FROM shop_users WHERE username = ?",
  ).bind(username).first();
  if (!user) return json({ ok: false, msg: "ไม่พบบัญชีลูกค้านี้" }, 400);

  const tier = resolveTier(body.tier);
  const durationDays = resolveDurationDays(body, 7);
  const plan = canonicalPlanCode(body.plan, tier, durationDays);
  const note = cleanText(body.note, "Gift Key").slice(0, 300);
  const customerRef = cleanText(user.customer_ref || user.username, user.username);
  const created = await createFreeLicenseKey(env, {
    tier,
    durationDays,
    plan,
    maxSeats: 1,
    note,
    customerRef,
  });

  await env.DB.prepare(
    `INSERT INTO shop_gifts(user_id, code, tier, plan, duration_days, note, created_at, claimed_at)
     VALUES(?, ?, ?, ?, ?, ?, ?, NULL)`,
  ).bind(user.id, created.code, tier, plan, durationDays, note, created.now).run();

  return json({ ok: true, code: created.code, tier, plan, duration_days: durationDays, username: user.username });
}

function html(body) {
  return new Response(body, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function adminPage() {
  return html(`<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <title>จัดการคีย์ JLCookie</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #20150f;
      --panel: #302116;
      --panel2: #3a2a1e;
      --line: #5a3b25;
      --text: #f5e6d0;
      --muted: #c9b79b;
      --gold: #ffd23f;
      --caramel: #c8783c;
      --mint: #7ed957;
      --berry: #ff6b6b;
      --input: #1a110c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 "Segoe UI", Tahoma, sans-serif;
    }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 24px; }
    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
    }
    h1, h2 { margin: 0; }
    h1 { color: var(--gold); font-size: 26px; }
    h2 { color: var(--gold); font-size: 17px; margin-bottom: 12px; }
    .sub { color: var(--muted); margin-top: 4px; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 16px;
      min-width: 0;
    }
    .span4 { grid-column: span 4; }
    .span6 { grid-column: span 6; }
    .span8 { grid-column: span 8; }
    .span12 { grid-column: span 12; }
    label { display: block; color: var(--muted); font-weight: 700; margin: 10px 0 5px; }
    input, select {
      width: 100%;
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--input);
      color: var(--text);
      padding: 0 10px;
      outline: none;
    }
    input:focus, select:focus { border-color: var(--gold); }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
    .buttons { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    button {
      min-height: 36px;
      border: 0;
      border-radius: 8px;
      background: var(--caramel);
      color: #21140c;
      font-weight: 800;
      padding: 0 14px;
      cursor: pointer;
    }
    button.secondary { background: var(--panel2); color: var(--text); border: 1px solid var(--line); }
    button.danger { background: var(--berry); color: #fff; }
    button.ok { background: var(--mint); }
    button:disabled { opacity: .55; cursor: default; }
    .status {
      min-height: 36px;
      background: #160e09;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      color: var(--muted);
      white-space: pre-wrap;
    }
    .metrics { display: grid; grid-template-columns: repeat(6, minmax(90px, 1fr)); gap: 10px; }
    .accountingMetrics { grid-template-columns: repeat(4, minmax(140px, 1fr)); }
    .metric {
      background: #160e09;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      min-height: 68px;
    }
    .metric b { display: block; color: var(--text); font-size: 22px; margin-bottom: 2px; }
    .metric span { color: var(--muted); font-size: 12px; font-weight: 700; }
    .toolbar {
      display: grid;
      grid-template-columns: 2fr 1fr 1fr auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 12px;
    }
    .tableMeta {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .muted { color: var(--muted); }
    .nowrap { white-space: nowrap; }
    .keyCell code { display: block; margin-bottom: 5px; }
    .detail { color: var(--muted); font-size: 11px; line-height: 1.55; }
    .emptyRow { color: var(--muted); text-align: center; padding: 18px 7px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid var(--line); padding: 8px 7px; text-align: left; vertical-align: top; }
    th { color: var(--gold); font-size: 12px; }
    td { color: var(--text); font-size: 12px; }
    code { color: var(--gold); user-select: all; }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--panel2);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .pill.stock { color: var(--gold); }
    .pill.delivered { color: var(--mint); }
    .pill.pending_review { color: var(--gold); }
    .pill.payment_verified { color: var(--blue); }
    .pill.rejected { color: var(--berry); }
    .pill.revoked { color: var(--berry); }
    .pill.expired { color: var(--berry); }
    .pill.active_on_first_use { color: #f59e0b; border-color: #f59e0b; }
    .mini { min-height: 26px; padding: 0 8px; font-size: 12px; }
    .mini-select {
      height: 26px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--input);
      color: var(--text);
      padding: 0 4px;
      font-size: 12px;
      outline: none;
    }
    @media (max-width: 900px) {
      .span4, .span6, .span8 { grid-column: span 12; }
      .row, .row3, .toolbar, .metrics, .accountingMetrics { grid-template-columns: 1fr; }
      header { align-items: stretch; flex-direction: column; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>จัดการหลังบ้าน JL Bot Cookie</h1>
        <div class="sub">ออเดอร์ลูกค้า · ตรวจสลิป · ส่งคีย์จากสต็อก · ล้างเครื่อง · ระงับคีย์</div>
      </div>
      <div class="buttons">
        <button class="secondary" id="refreshBtn">รีเฟรช</button>
        <button class="secondary" id="clearTokenBtn">ล้าง Token</button>
      </div>
    </header>

    <div class="grid">
      <section class="card span8">
        <h2>Token ผู้ดูแล</h2>
        <input id="adminToken" type="password" placeholder="วาง Token ผู้ดูแลที่นี่">
        <div class="buttons">
          <button class="ok" id="saveTokenBtn">ใช้ Token</button>
        </div>
      </section>
      <section class="card span4">
        <h2>สถานะ</h2>
        <div id="status" class="status">พร้อมใช้งาน</div>
      </section>

      <section class="card span12">
        <h2>ภาพรวมคีย์</h2>
        <div class="metrics" id="overviewStats">
          <div class="metric"><b>0</b><span>ในสต็อก</span></div>
          <div class="metric"><b>0</b><span>ใช้งานอยู่</span></div>
          <div class="metric"><b>0</b><span>หมดอายุ</span></div>
          <div class="metric"><b>0</b><span>ระงับแล้ว</span></div>
          <div class="metric"><b>0</b><span>เครื่องที่ผูก</span></div>
          <div class="metric"><b>0</b><span>รอตรวจสลิป</span></div>
        </div>
      </section>

      <section class="card span12">
        <h2>บัญชีรายได้</h2>
        <div class="tableMeta">
          <strong id="accountingUpdated">กำลังรอโหลดข้อมูล</strong>
          <button class="mini secondary" id="accountingRefreshBtn" type="button">รีเฟรชรายได้</button>
          <span>นับเฉพาะออเดอร์ที่ส่งคีย์สำเร็จแล้ว · เวลาไทย (Asia/Bangkok)</span>
        </div>
        <div class="metrics accountingMetrics" id="accountingStats">
          <div class="metric"><b>฿0</b><span>วันนี้ · 0 ออเดอร์</span></div>
          <div class="metric"><b>฿0</b><span>7 วันล่าสุด · 0 ออเดอร์</span></div>
          <div class="metric"><b>฿0</b><span>เดือนนี้ · 0 ออเดอร์</span></div>
          <div class="metric"><b>฿0</b><span>รวมทั้งหมด · 0 ออเดอร์</span></div>
        </div>
        <div class="row" style="margin-top:10px">
          <div class="status" id="accountingPremium">Premium เดือนนี้: ฿0 · 0 ออเดอร์</div>
          <div class="status" id="accountingPromax">ProMax เดือนนี้: ฿0 · 0 ออเดอร์</div>
        </div>
        <div class="buttons">
          <button class="secondary mini" data-accounting-export="today">CSV วันนี้</button>
          <button class="secondary mini" data-accounting-export="7d">CSV 7 วัน</button>
          <button class="secondary mini" data-accounting-export="month">CSV เดือนนี้</button>
          <button class="secondary mini" data-accounting-export="all">CSV ทั้งหมด</button>
        </div>
        <div style="overflow:auto; max-height:280px; margin-top:12px">
          <table>
            <thead><tr><th>วันที่</th><th>รายได้</th><th>จำนวนออเดอร์</th></tr></thead>
            <tbody id="accountingDailyBody"><tr><td class="emptyRow" colspan="3">กำลังรอโหลดข้อมูล</td></tr></tbody>
          </table>
        </div>
      </section>

      <section class="card span12">
        <h2>ออเดอร์ลูกค้า</h2>
        <div class="tableMeta">
          <strong id="orderCountText">ยังไม่มีข้อมูล</strong>
          <button class="mini secondary" id="toggleOrdersBtn" type="button" aria-expanded="false" aria-controls="ordersPanel">แสดง</button>
          <span>ลูกค้าอัปสลิป → ผู้ดูแลอนุมัติ → ระบบส่งคีย์จากสต็อกให้อัตโนมัติ</span>
        </div>
        <div id="ordersPanel" style="overflow:auto; display:none">
          <table>
            <thead>
              <tr><th>ออเดอร์</th><th>สถานะ</th><th>แพ็ก/ยอด</th><th>ลูกค้า</th><th>วันที่</th><th>คีย์</th><th>จัดการ</th></tr>
            </thead>
            <tbody id="ordersBody"></tbody>
          </table>
        </div>
      </section>

      <section class="card span4">
        <h2>สร้างสต็อกคีย์</h2>
        <div class="row3">
          <div>
            <label>แพ็ก</label>
            <select id="mintPlan">
              <option value="1d" data-tier="premium" data-days="1">Premium 1 วัน</option>
              <option value="3d" data-tier="premium" data-days="3">Premium 3 วัน</option>
              <option value="7d" data-tier="premium" data-days="7">Premium 7 วัน</option>
              <option value="30d" data-tier="premium" data-days="30">Premium 30 วัน</option>
              <option value="lifetime" data-tier="premium" data-days="0">Premium Lifetime</option>
              <option value="1d_promax" data-tier="promax" data-days="1">ProMax 1 วัน</option>
              <option value="3d_promax" data-tier="promax" data-days="3">ProMax 3 วัน</option>
              <option value="7d_promax" data-tier="promax" data-days="7">ProMax 7 วัน</option>
              <option value="30d_promax" data-tier="promax" data-days="30">ProMax 30 วัน</option>
              <option value="lifetime_promax" data-tier="promax" data-days="0">ProMax Lifetime</option>
            </select>
          </div>
          <div><label>จำนวนคีย์</label><input id="mintCount" type="number" min="1" max="200" value="10"></div>
          <div><label>จำนวนเครื่อง</label><input id="mintSeats" type="number" min="1" max="5" value="1"></div>
        </div>
        <label>หมายเหตุ</label><input id="mintNote" placeholder="ไม่บังคับ">
        <div class="buttons"><button id="mintBtn">สร้างคีย์เข้าสต็อก</button></div>
      </section>

      <section class="card span4">
        <h2>สรุปสต็อก</h2>
        <div id="stockTable" class="status">ยังไม่มีข้อมูล</div>
      </section>

      <section class="card span4">
        <h2>สร้างคีย์ฟรี (เริ่มนับเมื่อเริ่มใช้)</h2>
        <div class="row3">
          <div>
            <label>ระยะเวลา</label>
            <select id="freePlan">
              <option value="1d">1 วัน</option>
              <option value="3d">3 วัน</option>
              <option value="7d">7 วัน</option>
              <option value="30d">30 วัน</option>
              <option value="lifetime">Lifetime</option>
            </select>
          </div>
          <div>
            <label>จำนวนเครื่อง</label>
            <input id="freeSeats" type="number" min="1" max="5" value="1">
          </div>
          <div>
            <label>เทียร์ (Tier)</label>
            <select id="freeTier">
              <option value="premium">Premium</option>
              <option value="promax">Promax</option>
            </select>
          </div>
        </div>
        <label>หมายเหตุ</label>
        <input id="freeNote" placeholder="คีย์ฟรี / กิจกรรม">
        <div class="buttons">
          <button id="freeBtn" class="ok">สร้างคีย์ฟรี</button>
        </div>
        <div id="freeResult" style="margin-top:10px; font-weight:bold; color:var(--gold); font-family:monospace; font-size:12px; text-align:center; word-break:break-all;"></div>
      </section>

      <section class="card span4">
        <h2>ส่งของขวัญ/คีย์ฟรี</h2>
        <label>บัญชีลูกค้า</label>
        <input id="giftUsername" placeholder="username ที่ลูกค้าใช้ล็อกอินเว็บ">
        <label>แพ็กของขวัญ</label>
        <select id="giftPlan">
          <option value="1d" data-tier="premium" data-days="1">Premium 1 วัน</option>
          <option value="3d" data-tier="premium" data-days="3">Premium 3 วัน</option>
          <option value="7d" data-tier="premium" data-days="7">Premium 7 วัน</option>
          <option value="30d" data-tier="premium" data-days="30">Premium 30 วัน</option>
          <option value="lifetime" data-tier="premium" data-days="0">Premium Lifetime</option>
          <option value="1d_promax" data-tier="promax" data-days="1">ProMax 1 วัน</option>
          <option value="3d_promax" data-tier="promax" data-days="3">ProMax 3 วัน</option>
          <option value="7d_promax" data-tier="promax" data-days="7">ProMax 7 วัน</option>
          <option value="30d_promax" data-tier="promax" data-days="30">ProMax 30 วัน</option>
          <option value="lifetime_promax" data-tier="promax" data-days="0">ProMax Lifetime</option>
        </select>
        <label>หมายเหตุ</label>
        <input id="giftNote" placeholder="เช่น ชดเชยปิดปรับปรุง / โปรโมชัน">
        <div class="buttons">
          <button id="giftBtn" class="ok">ส่งของขวัญ</button>
        </div>
        <div id="giftResult" style="margin-top:10px; font-weight:bold; color:var(--gold); font-family:monospace; font-size:12px; text-align:center; word-break:break-all;"></div>
      </section>

      <section class="card span12">
        <h2>บัญชี SlipOK (ตรวจสลิป)</h2>
        <div class="toolbar">
          <div>
            <label>บัญชีที่ใช้ตรวจสลิป</label>
            <select id="slipokAccount">
              <option value="1">บช1 (JL)</option>
              <option value="2">บช2 (Fxng)</option>
              <option value="3">บช3 (Xiaomi)</option>
              <option value="auto">อัตโนมัติ (JL → Fxng → Xiaomi, สลับเมื่อเหลือ 5)</option>
            </select>
          </div>
          <div class="buttons">
            <button class="secondary" id="slipokRefreshBtn">รีเฟรชโควตา</button>
            <button class="secondary" id="slipokSaveBtn">บันทึกบัญชี</button>
          </div>
        </div>
        <div id="slipokStatus" style="font-size:12px; margin-top:6px; font-family:monospace;"></div>
        <div id="slipokQuotaStatus" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; margin-top:10px;"></div>
      </section>

      <section class="card span12">
        <h2>ค้นหาและจัดการคีย์</h2>
        <div class="toolbar">
          <div>
            <label>ค้นหา</label>
            <input id="keySearch" placeholder="คีย์ / ออเดอร์ / ลูกค้า / หมายเหตุ">
          </div>
          <div>
            <label>สถานะ</label>
            <select id="statusFilter">
              <option value="all">ทุกสถานะ</option>
              <option value="stock">ในสต็อก</option>
              <option value="active">ใช้งานอยู่</option>
              <option value="expired">หมดอายุ</option>
              <option value="revoked">ระงับแล้ว</option>
            </select>
          </div>
          <div>
            <label>แพ็ก</label>
            <select id="planFilter"><option value="all">ทุกแพ็ก</option></select>
          </div>
          <div class="buttons">
            <button class="secondary" id="clearFilterBtn">ล้างตัวกรอง</button>
          </div>
        </div>
        <div class="tableMeta">
          <span id="keyCountText">ยังไม่มีข้อมูล</span>
          <span>แสดงคีย์ล่าสุดสูงสุด 300 รายการ</span>
        </div>
        <div style="overflow:auto">
          <table>
            <thead>
              <tr><th>คีย์</th><th>สถานะ</th><th>แพ็ก/อายุ</th><th>ลูกค้า/ออเดอร์</th><th>วันที่</th><th>เครื่อง</th><th>จัดการ</th></tr>
            </thead>
            <tbody id="keysBody"></tbody>
          </table>
        </div>
      </section>
    </div>
  </div>

<script>
const $ = (id) => document.getElementById(id);
const statusBox = $("status");
let adminToken = sessionStorage.getItem("jl_admin_token") || "";
let allKeys = [];
let allStock = [];
let allOrders = [];
let ordersVisible = false;
$("adminToken").value = adminToken;

function setStatus(text, ok) {
  statusBox.textContent = text;
  statusBox.style.color = ok === false ? "var(--berry)" : ok === true ? "var(--mint)" : "var(--muted)";
}

function token() {
  adminToken = $("adminToken").value.trim();
  if (!adminToken) throw new Error("กรุณาใส่ Token ผู้ดูแล");
  return adminToken;
}

async function api(path, options) {
  const init = options || {};
  init.headers = Object.assign({"x-admin-token": token()}, init.headers || {});
  const res = await fetch(path, init);
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.msg || data.error || ("HTTP " + res.status));
  return data;
}

function baht(value) {
  return "฿" + new Intl.NumberFormat("th-TH", { maximumFractionDigits: 2 }).format(Number(value || 0));
}

function accountingMetric(item, label) {
  const value = item || { revenue: 0, orders: 0 };
  return '<div class="metric"><b>' + esc(baht(value.revenue)) + '</b><span>' + esc(label) + ' · ' + esc(value.orders || 0) + ' ออเดอร์</span></div>';
}

function renderAccounting(data) {
  const periods = data.periods || {};
  $("accountingStats").innerHTML =
    accountingMetric(periods.today, "วันนี้") +
    accountingMetric(periods.last_7_days, "7 วันล่าสุด") +
    accountingMetric(periods.current_month, "เดือนนี้") +
    accountingMetric(periods.all_time, "รวมทั้งหมด");
  const premium = data.tiers?.premium?.current_month || { revenue: 0, orders: 0 };
  const promax = data.tiers?.promax?.current_month || { revenue: 0, orders: 0 };
  $("accountingPremium").textContent = "Premium เดือนนี้: " + baht(premium.revenue) + " · " + premium.orders + " ออเดอร์";
  $("accountingPromax").textContent = "ProMax เดือนนี้: " + baht(promax.revenue) + " · " + promax.orders + " ออเดอร์";
  $("accountingUpdated").textContent = "อัปเดตล่าสุด " + fmtTime(data.generated_at);
  const daily = data.daily_30_days || [];
  $("accountingDailyBody").innerHTML = daily.length ? daily.map((row) =>
    '<tr><td>' + esc(row.date) + '</td><td><b>' + esc(baht(row.revenue)) + '</b></td><td>' + esc(row.orders) + '</td></tr>'
  ).join("") : '<tr><td class="emptyRow" colspan="3">ยังไม่มีรายได้จากออเดอร์ที่ส่งคีย์สำเร็จ</td></tr>';
}

async function loadAccounting() {
  const button = $("accountingRefreshBtn");
  button.disabled = true;
  $("accountingUpdated").textContent = "กำลังโหลดข้อมูลรายได้...";
  try {
    const data = await api("/api/admin/accounting");
    renderAccounting(data);
  } catch (error) {
    $("accountingUpdated").textContent = "โหลดข้อมูลรายได้ไม่สำเร็จ: " + error.message;
    throw error;
  } finally {
    button.disabled = false;
  }
}

async function downloadAccounting(period) {
  const res = await fetch("/api/admin/accounting.csv?period=" + encodeURIComponent(period), {
    headers: { "x-admin-token": token() },
  });
  if (!res.ok) {
    let message = "HTTP " + res.status;
    try {
      const data = await res.json();
      message = data.msg || data.error || message;
    } catch (_) {}
    throw new Error(message);
  }
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = "jlcookie-accounting-" + period + ".csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

function durationLabel(days) {
  const n = Number(days || 0);
  if (n === 0) return "Lifetime";
  if (n > 0 && n < 1) return Math.round(n * 1440) + " นาที";
  if (Number.isInteger(n)) return n + " วัน";
  return Number(n.toFixed(3)) + " วัน";
}

function fmtTime(epoch) {
  if (!epoch) return "-";
  return new Date(Number(epoch) * 1000).toLocaleString("th-TH", { hour12: false });
}

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function keyState(row) {
  if (row.revoked) return "revoked";
  if (row.status === "stock") return "stock";
  if (row.status === "active_on_first_use") return "active_on_first_use";
  if (row.status === "delivered" && row.expires_at && nowSeconds() > Number(row.expires_at)) return "expired";
  if (row.status === "delivered") return "active";
  return row.status || "unknown";
}

function statusText(row) {
  const state = keyState(row);
  if (state === "revoked") return "ระงับแล้ว";
  if (state === "stock") return "ในสต็อก";
  if (state === "active_on_first_use") return "รอเปิดใช้งาน";
  if (state === "expired") return "หมดอายุ";
  if (state === "active") return "ใช้งานอยู่";
  return row.status || "-";
}

function pill(row) {
  const state = keyState(row);
  return '<span class="pill ' + esc(state) + '">' + esc(statusText(row)) + '</span>';
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function refresh() {
  const [stock, keys, orders] = await Promise.all([
    api("/api/admin/stock"),
    api("/api/admin/keys"),
    api("/api/admin/shop-orders"),
  ]);
  allStock = stock.stock || [];
  allKeys = keys.keys || [];
  allOrders = orders.orders || [];
  renderStock(allStock);
  renderOverview();
  renderOrders();
  populatePlanFilter();
  renderKeys();
  setStatus("โหลดข้อมูลแล้ว: " + allKeys.length + " คีย์ · " + allOrders.length + " ออเดอร์", true);
}

function renderStock(rows) {
  if (!rows.length) {
    $("stockTable").textContent = "ไม่มีคีย์ในสต็อก";
    return;
  }
  $("stockTable").innerHTML = rows.map((r) =>
    '<div><span class="pill stock">' + esc(r.plan) + '</span> ' +
    durationLabel(r.duration_days) + ' · เครื่อง ' + esc(r.max_seats) + ' · <b>' + esc(r.count) + '</b> คีย์</div>'
  ).join("");
}

function renderOverview() {
  const stockCount = allStock.reduce((sum, r) => sum + Number(r.count || 0), 0);
  const activeCount = allKeys.filter((r) => keyState(r) === "active").length;
  const expiredCount = allKeys.filter((r) => keyState(r) === "expired").length;
  const revokedCount = allKeys.filter((r) => keyState(r) === "revoked").length;
  const seatCount = allKeys.reduce((sum, r) => sum + Number(r.seat_count || 0), 0);
  const pendingOrderCount = allOrders.filter((r) => ["pending_review", "payment_verified"].includes(r.status)).length;
  $("overviewStats").innerHTML =
    '<div class="metric"><b>' + esc(stockCount) + '</b><span>ในสต็อก</span></div>' +
    '<div class="metric"><b>' + esc(activeCount) + '</b><span>ใช้งานอยู่</span></div>' +
    '<div class="metric"><b>' + esc(expiredCount) + '</b><span>หมดอายุ</span></div>' +
    '<div class="metric"><b>' + esc(revokedCount) + '</b><span>ระงับแล้ว</span></div>' +
    '<div class="metric"><b>' + esc(seatCount) + '</b><span>เครื่องที่ผูก</span></div>' +
    '<div class="metric"><b>' + esc(pendingOrderCount) + '</b><span>รอตรวจสลิป</span></div>';
}

function populatePlanFilter() {
  const select = $("planFilter");
  const current = select.value || "all";
  const plans = Array.from(new Set(allKeys.map((r) => r.plan).filter(Boolean))).sort();
  select.innerHTML = '<option value="all">ทุกแพ็ก</option>' + plans.map((p) => '<option value="' + esc(p) + '">' + esc(p) + '</option>').join("");
  select.value = plans.includes(current) ? current : "all";
}

function filteredKeys() {
  const q = $("keySearch").value.trim().toLowerCase();
  const state = $("statusFilter").value;
  const plan = $("planFilter").value;
  return allKeys.filter((r) => {
    if (state !== "all" && keyState(r) !== state) return false;
    if (plan !== "all" && r.plan !== plan) return false;
    if (!q) return true;
    const haystack = [
      r.code,
      r.plan,
      r.order_id,
      r.customer_ref,
      r.note,
      statusText(r),
    ].join(" ").toLowerCase();
    return haystack.includes(q);
  });
}

function dateBlock(row) {
  return '<div class="detail">' +
    'สร้าง: ' + esc(fmtTime(row.created_at)) + '<br>' +
    'ส่ง: ' + esc(fmtTime(row.delivered_at)) + '<br>' +
    'หมด: ' + esc(fmtTime(row.expires_at)) +
    '</div>';
}

function customerBlock(row) {
  const note = row.note ? '<br><span class="detail">หมายเหตุ: ' + esc(row.note) + '</span>' : "";
  return '<div>' + esc(row.customer_ref || "-") +
    '<br><span class="detail">ออเดอร์: ' + esc(row.order_id || "-") + '</span>' +
    note + '</div>';
}

function planBlock(row) {
  const tierColor = row.tier === "promax" ? "var(--gold)" : "var(--muted)";
  const tierLabel = String(row.tier || "premium").toUpperCase();
  return '<div><b>' + esc(row.plan || "-") + '</b> <span style="font-size:10px; font-weight:bold; color:' + tierColor + '">[' + tierLabel + ']</span><br><span class="detail">' + durationLabel(row.duration_days) + '</span></div>';
}

function seatBlock(row) {
  return '<span class="nowrap">' + esc(row.seat_count || 0) + '/' + esc(row.max_seats || 1) + '</span>';
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  const input = document.createElement("textarea");
  input.value = text;
  input.style.position = "fixed";
  input.style.left = "-9999px";
  document.body.appendChild(input);
  input.focus();
  input.select();
  const ok = document.execCommand("copy");
  input.remove();
  return ok;
}

function renderKeys() {
  const rows = filteredKeys();
  $("keyCountText").textContent = "แสดง " + rows.length + " จาก " + allKeys.length + " คีย์";
  if (!rows.length) {
    $("keysBody").innerHTML = '<tr><td class="emptyRow" colspan="7">ไม่พบคีย์ตามตัวกรองนี้</td></tr>';
    return;
  }
  $("keysBody").innerHTML = rows.map((r) => {
    const actions =
      '<button class="mini ok" data-copy="' + esc(r.code) + '">คัดลอกคีย์</button> ' +
      '<button class="mini secondary" data-fill="' + esc(r.code) + '">เลือก</button> ' +
      '<button class="mini secondary" data-extend="' + esc(r.code) + '" data-hours="6">+6ชม.</button> ' +
      '<button class="mini secondary" data-extend="' + esc(r.code) + '" data-hours="24">+1วัน</button> ' +
      '<button class="mini secondary" data-reset="' + esc(r.code) + '">ล้างเครื่อง</button> ' +
      '<button class="mini danger" data-revoke="' + esc(r.code) + '">ระงับ</button>';
    return '<tr>' +
      '<td class="keyCell"><code>' + esc(r.code) + '</code><span class="detail">' + esc(r.note || "") + '</span></td>' +
      '<td>' + pill(r) + '</td>' +
      '<td>' + planBlock(r) + '</td>' +
      '<td>' + customerBlock(r) + '</td>' +
      '<td>' + dateBlock(r) + '</td>' +
      '<td>' + seatBlock(r) + '</td>' +
      '<td>' + actions + '</td>' +
    '</tr>';
  }).join("");
}

function orderStatusText(status) {
  if (status === "pending_review") return "รอตรวจสลิป";
  if (status === "payment_verified") return "ตรวจสลิปผ่าน";
  if (status === "delivered") return "ส่งคีย์แล้ว";
  if (status === "rejected") return "ไม่ผ่าน";
  return status || "-";
}

function orderPill(row) {
  return '<span class="pill ' + esc(row.status || "") + '">' + esc(orderStatusText(row.status)) + '</span>';
}

function orderDateBlock(row) {
  return '<div class="detail">' +
    'สร้าง: ' + esc(fmtTime(row.created_at)) + '<br>' +
    'อัปสลิป: ' + esc(fmtTime(row.slip_uploaded_at)) + '<br>' +
    'อนุมัติ: ' + esc(fmtTime(row.approved_at)) +
    '</div>';
}

function orderCustomerBlock(row) {
  const note = row.admin_note ? '<br><span class="detail">หมายเหตุ: ' + esc(row.admin_note) + '</span>' : "";
  return '<div>' + esc(row.customer_ref || row.username || "-") +
    '<br><span class="detail">บัญชี: ' + esc(row.username || "-") + '</span>' +
    '<br><span class="detail">สลิป: ' + esc(row.slip_name || "-") + '</span>' +
    note + '</div>';
}

function orderPlanBlock(row) {
  return '<div><b>' + esc(row.plan_label || row.plan || "-") + '</b><br>' +
    '<span class="detail">ยอด ' + esc(row.amount || 0) + ' บาท · ' + esc(row.max_seats || 1) + ' เครื่อง</span></div>';
}

function renderOrders() {
  $("orderCountText").textContent = "ออเดอร์ล่าสุด " + allOrders.length + " รายการ";
  if (!ordersVisible) {
    $("ordersBody").innerHTML = "";
    return;
  }
  if (!allOrders.length) {
    $("ordersBody").innerHTML = '<tr><td class="emptyRow" colspan="7">ยังไม่มีออเดอร์จากลูกค้า</td></tr>';
    return;
  }
  $("ordersBody").innerHTML = allOrders.map((r) => {
    const keyHtml = r.key_code ? '<code>' + esc(r.key_code) + '</code>' : '<span class="detail">ยังไม่ได้ส่งคีย์</span>';
    const actions = [
      '<button class="mini secondary" data-slip="' + esc(r.id) + '">ดูสลิป</button>',
    ];
    if (["pending_review", "payment_verified"].includes(r.status)) {
      actions.push('<select class="mini-select" id="approveTier-' + esc(r.id) + '"><option value="premium">Premium</option><option value="promax">Promax</option></select>');
      actions.push('<button class="mini ok" data-approve="' + esc(r.id) + '">อนุมัติ</button>');
      actions.push('<button class="mini danger" data-reject="' + esc(r.id) + '">ไม่ผ่าน</button>');
    }
    if (r.key_code) actions.push('<button class="mini ok" data-copy="' + esc(r.key_code) + '">คัดลอกคีย์</button>');
    return '<tr>' +
      '<td><b>' + esc(r.id) + '</b></td>' +
      '<td>' + orderPill(r) + '</td>' +
      '<td>' + orderPlanBlock(r) + '</td>' +
      '<td>' + orderCustomerBlock(r) + '</td>' +
      '<td>' + orderDateBlock(r) + '</td>' +
      '<td class="keyCell">' + keyHtml + '</td>' +
      '<td>' + actions.join(" ") + '</td>' +
    '</tr>';
  }).join("");
}

function setOrdersVisible(visible) {
  ordersVisible = Boolean(visible);
  $("ordersPanel").style.display = ordersVisible ? "block" : "none";
  $("toggleOrdersBtn").textContent = ordersVisible ? "ซ่อน" : "แสดง";
  $("toggleOrdersBtn").setAttribute("aria-expanded", ordersVisible ? "true" : "false");
  renderOrders();
}

$("toggleOrdersBtn").onclick = () => setOrdersVisible(!ordersVisible);

async function openOrderSlip(orderIdValue) {
  const data = await api("/api/admin/shop-order-slip?order_id=" + encodeURIComponent(orderIdValue));
  const order = data.order || {};
  if (!order.slip_b64) throw new Error("ออเดอร์นี้ไม่มีไฟล์สลิป");
  const mime = order.slip_mime || "image/jpeg";
  const win = window.open("", "_blank");
  if (!win) throw new Error("เปิดหน้าดูสลิปไม่สำเร็จ");
  win.document.write('<!doctype html><title>' + esc(order.id) + '</title><body style="margin:0;background:#160e09;display:grid;place-items:center;min-height:100vh"><img style="max-width:100%;max-height:100vh" src="data:' + esc(mime) + ';base64,' + order.slip_b64 + '"></body>');
  win.document.close();
}

async function postJson(path, body) {
  return api(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

$("saveTokenBtn").onclick = async () => {
  sessionStorage.setItem("jl_admin_token", token());
  await Promise.allSettled([
    refresh(),
    loadSlipokAccount(),
    loadAccounting(),
  ]).then((results) => {
    const failed = results.find((item) => item.status === "rejected");
    if (failed) setStatus(failed.reason?.message || "โหลดข้อมูลบางส่วนไม่สำเร็จ", false);
  });
};
$("clearTokenBtn").onclick = () => {
  sessionStorage.removeItem("jl_admin_token");
  $("adminToken").value = "";
  setStatus("ล้าง Token แล้ว", true);
};
$("refreshBtn").onclick = () => Promise.allSettled([refresh(), loadSlipokAccount(), loadAccounting()]).then((results) => {
  const failed = results.find((item) => item.status === "rejected");
  if (failed) setStatus(failed.reason?.message || "โหลดข้อมูลบางส่วนไม่สำเร็จ", false);
});
$("accountingRefreshBtn").onclick = () => loadAccounting().catch((e) => setStatus(e.message, false));
document.querySelectorAll("[data-accounting-export]").forEach((button) => {
  button.onclick = async () => {
    const period = button.getAttribute("data-accounting-export");
    button.disabled = true;
    try {
      await downloadAccounting(period);
      setStatus("ดาวน์โหลดรายงานบัญชี CSV แล้ว", true);
    } catch (error) {
      setStatus("ดาวน์โหลดรายงานไม่สำเร็จ: " + error.message, false);
    } finally {
      button.disabled = false;
    }
  };
});
$("keySearch").oninput = renderKeys;
$("statusFilter").onchange = renderKeys;
$("planFilter").onchange = renderKeys;
$("clearFilterBtn").onclick = () => {
  $("keySearch").value = "";
  $("statusFilter").value = "all";
  $("planFilter").value = "all";
  renderKeys();
};

$("ordersBody").onclick = async (ev) => {
  const btn = ev.target.closest("button");
  if (!btn) return;
  const slipId = btn.getAttribute("data-slip");
  const approveId = btn.getAttribute("data-approve");
  const rejectId = btn.getAttribute("data-reject");
  const copyKey = btn.getAttribute("data-copy");
  if (slipId) {
    await openOrderSlip(slipId).catch((e) => setStatus(e.message, false));
    return;
  }
  if (approveId) {
    const tierSel = document.getElementById("approveTier-" + approveId);
    const tierVal = tierSel ? tierSel.value : "premium";
    const data = await postJson("/api/admin/shop-orders/approve", { order_id: approveId, tier: tierVal }).catch((e) => ({ error: e.message }));
    if (data.error) return setStatus(data.error, false);
    const copied = data.key && data.key.code ? await copyText(data.key.code).catch(() => false) : false;
    await refresh();
    setStatus("อนุมัติออเดอร์แล้ว: " + approveId + " (" + tierVal.toUpperCase() + ")" + (data.key ? " · " + data.key.code : "") + (copied ? " · คัดลอกแล้ว" : ""), true);
    return;
  }
  if (rejectId) {
    const note = prompt("เหตุผลที่ไม่ผ่าน", "ตรวจสลิปไม่ผ่าน") || "";
    const data = await postJson("/api/admin/shop-orders/reject", { order_id: rejectId, admin_note: note }).catch((e) => ({ error: e.message }));
    if (data.error) return setStatus(data.error, false);
    await refresh();
    setStatus("ทำเครื่องหมายออเดอร์ไม่ผ่านแล้ว: " + rejectId, true);
    return;
  }
  if (copyKey) {
    const copied = await copyText(copyKey).catch(() => false);
    setStatus((copied ? "คัดลอกคีย์แล้ว: " : "คัดลอกไม่สำเร็จ: ") + copyKey, copied);
  }
};

$("mintBtn").onclick = async () => {
  const option = $("mintPlan").selectedOptions[0];
  const body = {
    plan: $("mintPlan").value,
    count: Number($("mintCount").value || 1),
    max_seats: Number($("mintSeats").value || 1),
    tier: option ? option.dataset.tier : "premium",
    duration_days: option ? Number(option.dataset.days || 7) : 7,
    note: $("mintNote").value.trim(),
  };
  const data = await postJson("/api/admin/mint", body).catch((e) => ({ error: e.message }));
  if (data.error) return setStatus(data.error, false);
  await refresh();
  setStatus("สร้างคีย์แล้ว: " + data.codes.join(", "), true);
};

$("keysBody").onclick = async (ev) => {
  const btn = ev.target.closest("button");
  if (!btn) return;
  const copyKey = btn.getAttribute("data-copy");
  const fillKey = btn.getAttribute("data-fill");
  const extendKey = btn.getAttribute("data-extend");
  const extendHours = Number(btn.getAttribute("data-hours") || 0);
  const resetKey = btn.getAttribute("data-reset");
  const revokeKey = btn.getAttribute("data-revoke");
  if (copyKey) {
    const copied = await copyText(copyKey).catch(() => false);
    setStatus((copied ? "คัดลอกคีย์แล้ว: " : "เลือกคีย์แล้ว แต่คัดลอกไม่สำเร็จ: ") + copyKey, copied);
    return;
  }
  if (fillKey) {
    setStatus("เลือกคีย์แล้ว: " + fillKey, true);
    return;
  }
  if (resetKey) {
    const data = await postJson("/api/admin/reset-seats", { key: resetKey }).catch((e) => ({ error: e.message }));
    if (data.error) return setStatus(data.error, false);
    await refresh();
    setStatus("ล้างเครื่องของคีย์แล้ว: " + resetKey, true);
    return;
  }
  if (extendKey) {
    const label = extendHours === 24 ? "1 วัน" : extendHours + " ชั่วโมง";
    const data = await postJson("/api/admin/extend", { key: extendKey, hours: extendHours }).catch((e) => ({ error: e.message }));
    if (data.error) return setStatus(data.error, false);
    await refresh();
    setStatus("ต่ออายุคีย์แล้ว +" + label + ": " + extendKey, true);
    return;
  }
  if (revokeKey) {
    if (!confirm("ต้องการระงับคีย์ " + revokeKey + " ใช่ไหม?")) return;
    const data = await postJson("/api/admin/revoke", { key: revokeKey }).catch((e) => ({ error: e.message }));
    if (data.error) return setStatus(data.error, false);
    await refresh();
    setStatus("ระงับคีย์แล้ว: " + revokeKey, true);
  }
};

$("freeBtn").onclick = async () => {
  const plan = $("freePlan").value;
  const max_seats = Number($("freeSeats").value || 1);
  const note = $("freeNote").value.trim() || "Free Key";
  const tier = $("freeTier").value;

  const durationDaysMap = {
    "1d": 1,
    "3d": 3,
    "7d": 7,
    "30d": 30,
    "lifetime": 0
  };

  const body = {
    plan: plan,
    duration_days: Object.prototype.hasOwnProperty.call(durationDaysMap, plan) ? durationDaysMap[plan] : 7,
    max_seats: max_seats,
    note: note,
    tier: tier
  };

  $("freeResult").textContent = "กำลังสร้าง...";
  const data = await postJson("/api/admin/generate-free-key", body).catch((e) => ({ error: e.message }));
  if (data.error) {
    $("freeResult").style.color = "var(--berry)";
    $("freeResult").textContent = data.error;
    return setStatus(data.error, false);
  }

  $("freeResult").style.color = "var(--gold)";
  $("freeResult").textContent = "สร้างสำเร็จ: " + data.code;
  const copied = await copyText(data.code).catch(() => false);
  await refresh();
  setStatus("สร้างคีย์ฟรีเรียบร้อย: " + data.code + (copied ? " (คัดลอกลงคลิปบอร์ดแล้ว)" : ""), true);
};

$("giftBtn").onclick = async () => {
  const option = $("giftPlan").selectedOptions[0];
  const body = {
    username: $("giftUsername").value.trim(),
    plan: $("giftPlan").value,
    tier: option ? option.dataset.tier : "premium",
    duration_days: option ? Number(option.dataset.days || 7) : 7,
    note: $("giftNote").value.trim() || "Gift Key",
  };

  $("giftResult").textContent = "กำลังส่ง...";
  const data = await postJson("/api/admin/send-gift", body).catch((e) => ({ error: e.message }));
  if (data.error) {
    $("giftResult").style.color = "var(--berry)";
    $("giftResult").textContent = data.error;
    return setStatus(data.error, false);
  }

  $("giftResult").style.color = "var(--gold)";
  $("giftResult").textContent = "ส่งสำเร็จ: " + data.code;
  const copied = await copyText(data.code).catch(() => false);
  await refresh();
  setStatus("ส่งของขวัญให้ " + data.username + " แล้ว: " + data.code + (copied ? " (คัดลอกลงคลิปบอร์ดแล้ว)" : ""), true);
};

function slipokAccountLabel(account) {
  if (account === "1") return "บช1 (JL)";
  if (account === "2") return "บช2 (Fxng)";
  if (account === "3") return "บช3 (Xiaomi)";
  return "อัตโนมัติ (JL → Fxng → Xiaomi)";
}

function renderSlipokQuotas(accounts) {
  const root = $("slipokQuotaStatus");
  root.textContent = "";
  for (const item of accounts || []) {
    const card = document.createElement("div");
    card.style.cssText = "border:1px solid var(--line);border-radius:10px;padding:10px;background:rgba(255,255,255,.025);font-family:monospace;font-size:12px;";
    const title = document.createElement("div");
    title.style.cssText = "font-weight:700;margin-bottom:5px;color:var(--gold);";
    title.textContent = item.name;
    const value = document.createElement("div");
    if (!item.configured) {
      value.textContent = "ยังไม่ได้ตั้งค่า API";
    } else if (!item.ok) {
      value.textContent = "อ่านโควตาไม่สำเร็จ: " + (item.error || "ไม่ทราบสาเหตุ");
      value.style.color = "#ff8a8a";
    } else {
      value.textContent = item.used + "/" + item.limit + " (เหลือ " + item.remaining + ")" +
        (item.special_quota ? " · โควตาพิเศษ " + item.special_quota : "") +
        (item.end_date ? " · หมดรอบ " + item.end_date : "") +
        (item.available ? "" : " • หยุดใช้");
      value.style.color = item.available ? "#7ee787" : "#ff8a8a";
    }
    card.appendChild(title);
    card.appendChild(value);
    root.appendChild(card);
  }
}

async function loadSlipokAccount() {
  const button = $("slipokRefreshBtn");
  button.disabled = true;
  $("slipokStatus").textContent = "กำลังตรวจโควตา SlipOK ทั้ง 3 บัญชี...";
  $("slipokQuotaStatus").textContent = "กำลังโหลด...";
  try {
    const data = await api("/api/admin/slipok-account");
    if (data && data.account) {
      $("slipokAccount").value = data.account;
      const label = slipokAccountLabel(data.account);
      $("slipokStatus").textContent = "กำลังใช้: " + label;
      $("slipokStatus").style.color = "var(--muted)";
      renderSlipokQuotas(data.accounts);
    }
    return data;
  } catch (error) {
    const message = "โหลดโควตา SlipOK ไม่สำเร็จ: " + error.message;
    $("slipokStatus").textContent = message;
    $("slipokStatus").style.color = "var(--berry)";
    $("slipokQuotaStatus").textContent = message;
    throw error;
  } finally {
    button.disabled = false;
  }
}

$("slipokRefreshBtn").onclick = () => loadSlipokAccount().catch((e) => setStatus(e.message, false));

$("slipokSaveBtn").onclick = async () => {
  const account = $("slipokAccount").value;
  const data = await postJson("/api/admin/slipok-account", { account }).catch((e) => ({ error: e.message }));
  if (data.error) return setStatus(data.error, false);
  const label = slipokAccountLabel(account);
  $("slipokStatus").textContent = "กำลังใช้: " + label;
  setStatus("เปลี่ยนบัญชี SlipOK แล้ว: " + label, true);
  loadSlipokAccount().catch((e) => setStatus(e.message, false));
};

if (adminToken) {
  refresh().catch((e) => setStatus(e.message, false));
  loadSlipokAccount().catch((e) => setStatus(e.message, false));
  loadAccounting().catch((e) => setStatus(e.message, false));
}
</script>
</body>
</html>`);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return corsOk();
    if ((req.method === "GET" || req.method === "HEAD") && url.pathname === "/" && env.ASSETS) {
      return env.ASSETS.fetch(req);
    }
    if (req.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, app: "jlcookie-license", mode: "stock-delivery" });
    }
    const adminPath = cleanText(env.ADMIN_PATH, "/admin");
    if (req.method === "GET" && url.pathname === adminPath) return adminPage();
    if (req.method === "GET" && (url.pathname === "/admin" || url.pathname === "/admin/") && adminPath !== "/admin") {
      return json({ ok: false, msg: "ไม่พบเส้นทางนี้" }, 404);
    }
    if (req.method === "POST" && url.pathname === "/api/verify") return verify(req, env);
    if (req.method === "GET" && url.pathname === "/api/discord-shop/plans") return discordShopPlans(req, env);
    if (req.method === "POST" && url.pathname === "/api/discord-shop/orders") return createDiscordShopOrder(req, env);
    if (req.method === "POST" && url.pathname === "/api/discord-shop/claim-role") return claimDiscordRole(req, env);
    if (req.method === "GET" && url.pathname === "/api/shop/plans") return shopPlans(env);
    if (req.method === "GET" && url.pathname === "/api/shop/activity") return shopActivity(env);
    if (req.method === "POST" && url.pathname === "/api/auth/register") return registerUser(req, env);
    if (req.method === "POST" && url.pathname === "/api/auth/login") return loginUser(req, env);
    if (req.method === "GET" && url.pathname === "/api/me") return me(req, env);
    if (req.method === "POST" && url.pathname === "/api/shop/reset-device") return resetShopDevice(req, env);
    if (req.method === "GET" && url.pathname === "/api/download-info") return downloadInfo(req, env);
    if (req.method === "POST" && url.pathname === "/api/orders") return createOrder(req, env);
    if (req.method === "GET" && url.pathname === "/api/orders") return myOrders(req, env);
    if (req.method === "GET" && url.pathname === "/api/gifts") return myGifts(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/mint") return mint(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/deliver") return deliver(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/deliver-key") return deliverKey(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/generate-free-key") return generateFreeKey(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/send-gift") return sendGift(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/revoke") return revoke(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/extend") return extendKey(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/reset-seats") return resetSeats(req, env);
    if (req.method === "GET" && url.pathname === "/api/admin/stock") return stock(req, env);
    if (req.method === "GET" && url.pathname === "/api/admin/keys") return listKeys(req, env);
    if (req.method === "GET" && url.pathname === "/api/admin/slipok-account") return getSlipokAccount(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/slipok-account") return setSlipokAccount(req, env);
    if (req.method === "GET" && url.pathname === "/api/admin/accounting") return getAccounting(req, env);
    if (req.method === "GET" && url.pathname === "/api/admin/accounting.csv") return exportAccountingCsv(req, env, url);
    if (req.method === "GET" && url.pathname === "/api/admin/shop-orders") return listShopOrders(req, env);
    if (req.method === "GET" && url.pathname === "/api/admin/shop-order-slip") return shopOrderSlip(req, env, url);
    if (req.method === "POST" && url.pathname === "/api/admin/shop-orders/approve") return approveShopOrder(req, env);
    if (req.method === "POST" && url.pathname === "/api/admin/shop-orders/reject") return rejectShopOrder(req, env);
    if ((req.method === "GET" || req.method === "HEAD") && env.ASSETS) return env.ASSETS.fetch(req);
    return json({ ok: false, msg: "ไม่พบเส้นทางนี้" }, 404);
  },
};
