/* belt-picks: the belt network's Cloudflare Worker (free tier, one KV namespace bound as BELT).
 *
 *   POST /pick        {site, league, key, pick, uid, name}   one visitor's call on the current belt game
 *   GET  /standings   ?site=bh&league=nhl[&uid=]             the league's leaderboard (10-minute cache)
 *   GET  /standings   ?site=all[&uid=]                       every belt, every site, summed
 *   POST /subscribe   {belt, sub}                            a web-push subscription for one belt ("bh:nhl", "cfb", "cbb", "wcbb")
 *   POST /unsubscribe {belt, endpoint}
 *   POST /notify      {belt, reign, title, body, url}        from CI, with the X-Notify-Key header; one push per reign
 *   GET  /health
 *
 * Picks are only accepted for the game each site currently lists as open (its api/picks.json), and
 * only before kickoff, so nobody can post a call after the result. Grading reads the same file.
 * Secrets: NOTIFY_KEY (CI), VAPID_PRIVATE_JWK (JSON), VAPID_PUBLIC (base64url, 65 bytes), VAPID_SUBJECT.
 */

const SITES = {
  bh: (lg) => `https://beltholders.com/${lg}/api/picks.json`,
  cbb: () => "https://collegebasketballbelt.com/api/picks.json",
  wcbb: () => "https://collegebasketballbelt.com/women/api/picks.json",
  cfb: () => "https://collegefootballbelt.com/api/picks.json",
};
const ORIGINS = ["https://beltholders.com", "https://collegebasketballbelt.com", "https://collegefootballbelt.com", "http://localhost:8765"];
const STANDINGS_TTL = 600;         // seconds the computed leaderboard is reused
const PICKS_TTL = 120;             // seconds a site's picks.json is reused for validation/grading
const TOP = 100;

const mem = new Map();             // per-isolate cache of picks.json

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const cors = {
      "access-control-allow-origin": ORIGINS.includes(origin) ? origin : ORIGINS[0],
      "access-control-allow-methods": "GET,POST,OPTIONS",
      "access-control-allow-headers": "content-type,x-notify-key",
      "access-control-max-age": "86400",
      "vary": "Origin",
    };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    const json = (body, status = 200, extra = {}) =>
      new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...cors, ...extra } });
    try {
      if (url.pathname === "/health") return json({ ok: true, time: new Date().toISOString() });
      if (url.pathname === "/pick" && request.method === "POST") return json(...(await postPick(request, env, ctx)));
      if (url.pathname === "/standings" && request.method === "GET") return json(...(await getStandings(url, env, ctx)));
      if (url.pathname === "/subscribe" && request.method === "POST") return json(...(await subscribe(request, env)));
      if (url.pathname === "/unsubscribe" && request.method === "POST") return json(...(await unsubscribe(request, env)));
      if (url.pathname === "/notify" && request.method === "POST") return json(...(await notify(request, env, ctx)));
      return json({ error: "not found" }, 404);
    } catch (e) {
      return json({ error: "server error", detail: String(e && e.message || e) }, 500);
    }
  },
};

// ------------------------------------------------------------------ helpers --

function clean(s, max) {
  return String(s == null ? "" : s).replace(/[<>&"'\u0000-\u001f]/g, "").trim().slice(0, max);
}

async function picksFile(site, league, env) {
  const f = SITES[site];
  if (!f) return null;
  const u = env && env.TEST_PICKS_URL ? env.TEST_PICKS_URL : f(league);
  const hit = mem.get(u);
  if (hit && Date.now() - hit.at < PICKS_TTL * 1000) return hit.doc;
  const r = await fetch(u, { cf: { cacheTtl: PICKS_TTL, cacheEverything: true }, headers: { "user-agent": "belt-picks worker" } });
  if (!r.ok) return null;
  const doc = await r.json();
  mem.set(u, { at: Date.now(), doc });
  return doc;
}

function validLeague(site, league) {
  if (site === "bh") return /^[a-z0-9]{2,12}$/.test(league);
  return league === site;
}

// ------------------------------------------------------------------- picks --

async function postPick(request, env, ctx) {
  const b = await request.json().catch(() => null);
  if (!b) return [{ error: "bad json" }, 400];
  const site = clean(b.site, 8), league = clean(b.league, 12), key = clean(b.key, 160), pick = clean(b.pick, 80);
  const uid = clean(b.uid, 32), name = clean(b.name, 24);
  if (!SITES[site] || !validLeague(site, league)) return [{ error: "unknown belt" }, 400];
  if (!/^[a-f0-9]{16,32}$/.test(uid)) return [{ error: "bad uid" }, 400];
  const doc = await picksFile(site, league, env);
  if (!doc || !doc.open) return [{ error: "no open game" }, 409];
  if (doc.open.key !== key) return [{ error: "that game is not open", open: doc.open.key }, 409];
  if (pick !== doc.open.holder && pick !== doc.open.challenger) return [{ error: "pick must be the holder or the challenger" }, 400];
  if (doc.open.kickoff_utc && Date.now() >= Date.parse(doc.open.kickoff_utc)) return [{ error: "locked at kickoff" }, 409];
  const rec = { pick, at: new Date().toISOString(), name };
  await env.BELT.put(`p:${site}:${league}:${key}:${uid}`, JSON.stringify(rec), { expirationTtl: 400 * 86400 });
  if (name) await env.BELT.put(`u:${uid}`, JSON.stringify({ name, at: rec.at }), { expirationTtl: 400 * 86400 });
  ctx.waitUntil(indexLeague(env, site, league));
  ctx.waitUntil(env.BELT.delete(`s:${site}:${league}`));   // standings recompute on the next request
  return [{ ok: true, pick, open: doc.open.key }];
}

async function indexLeague(env, site, league) {
  const raw = await env.BELT.get("idx");
  const idx = raw ? JSON.parse(raw) : [];
  const k = `${site}:${league}`;
  if (!idx.includes(k)) { idx.push(k); await env.BELT.put("idx", JSON.stringify(idx)); }
}

async function listAll(env, prefix) {
  const out = [];
  let cursor;
  do {
    const page = await env.BELT.list({ prefix, cursor, limit: 1000 });
    out.push(...page.keys);
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return out;
}

async function leagueTable(env, site, league) {
  // every pick in the league, graded against the site's results; cached 10 minutes
  const cacheKey = `s:${site}:${league}`;
  const cached = await env.BELT.get(cacheKey);
  if (cached) return JSON.parse(cached);
  const doc = await picksFile(site, league, env);
  const results = (doc && doc.results) || {};
  const keys = await listAll(env, `p:${site}:${league}:`);
  const players = {};
  const vals = await Promise.all(keys.map((k) => env.BELT.get(k.name)));
  keys.forEach((k, i) => {
    const parts = k.name.split(":");          // p, site, league, key(may contain ':'? no -- keys use |), uid
    const uid = parts[parts.length - 1];
    const gameKey = parts.slice(3, -1).join(":");
    const rec = vals[i] ? JSON.parse(vals[i]) : null;
    if (!rec) return;
    const p = players[uid] || (players[uid] = { uid, name: "", w: 0, l: 0, pending: 0, last: "", nameAt: "" });
    if (rec.name && rec.at >= p.nameAt) { p.name = rec.name; p.nameAt = rec.at; }
    const winner = results[gameKey];
    if (winner === undefined || winner === null || winner === "") p.pending += 1;
    else if (winner === rec.pick) p.w += 1;
    else p.l += 1;
    if (rec.at > p.last) p.last = rec.at;
  });
  const table = { site, league, updated: new Date().toISOString(), players: Object.values(players) };
  await env.BELT.put(cacheKey, JSON.stringify(table), { expirationTtl: STANDINGS_TTL });
  return table;
}

function rank(players, uid) {
  const rows = players.filter((p) => p.w + p.l + p.pending > 0)
    .sort((a, b) => b.w - a.w || a.l - b.l || b.pending - a.pending || (b.last > a.last ? 1 : -1));
  let you = null;
  const top = rows.slice(0, TOP).map((p, i) => ({ rank: i + 1, name: p.name || "Anonymous", w: p.w, l: p.l, pending: p.pending }));
  const i = rows.findIndex((p) => p.uid === uid);
  if (i >= 0) you = { rank: i + 1, name: rows[i].name || "Anonymous", w: rows[i].w, l: rows[i].l, pending: rows[i].pending };
  return { players: rows.length, top, you };
}

async function getStandings(url, env) {
  const site = clean(url.searchParams.get("site"), 8), league = clean(url.searchParams.get("league"), 12);
  const uid = clean(url.searchParams.get("uid"), 32);
  if (site === "all") {
    const raw = await env.BELT.get("idx");
    const idx = raw ? JSON.parse(raw) : [];
    const merged = {};
    for (const k of idx) {
      const [s, lg] = k.split(":");
      const t = await leagueTable(env, s, lg);
      for (const p of t.players) {
        const m = merged[p.uid] || (merged[p.uid] = { uid: p.uid, name: "", w: 0, l: 0, pending: 0, last: "" });
        m.w += p.w; m.l += p.l; m.pending += p.pending;
        if (p.name && p.last >= m.last) m.name = p.name;
        if (p.last > m.last) m.last = p.last;
      }
    }
    return [{ site: "all", belts: idx.length, updated: new Date().toISOString(), ...rank(Object.values(merged), uid) }, 200, { "cache-control": "public, max-age=120" }];
  }
  if (!SITES[site] || !validLeague(site, league)) return [{ error: "unknown belt" }, 400];
  const t = await leagueTable(env, site, league);
  return [{ site, league, updated: t.updated, ...rank(t.players, uid) }, 200, { "cache-control": "public, max-age=120" }];
}

// --------------------------------------------------------------- web push --

async function sha16(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].slice(0, 16).map((x) => x.toString(16).padStart(2, "0")).join("");
}

function validBelt(belt) {
  return /^(bh:[a-z0-9]{2,12}|cfb|cbb|wcbb|all)$/.test(belt);
}

async function subscribe(request, env) {
  const b = await request.json().catch(() => null);
  if (!b || !b.sub || !b.sub.endpoint || !b.sub.keys || !b.sub.keys.p256dh || !b.sub.keys.auth) return [{ error: "bad subscription" }, 400];
  const belt = clean(b.belt, 16);
  if (!validBelt(belt)) return [{ error: "unknown belt" }, 400];
  const okEndpoint = /^https:\/\//.test(b.sub.endpoint) || (env.TEST_PICKS_URL && /^http:\/\/127\.0\.0\.1/.test(b.sub.endpoint));
  if (!okEndpoint || b.sub.endpoint.length > 1024) return [{ error: "bad endpoint" }, 400];
  const id = await sha16(b.sub.endpoint);
  await env.BELT.put(`sub:${belt}:${id}`, JSON.stringify({ endpoint: b.sub.endpoint, keys: { p256dh: b.sub.keys.p256dh, auth: b.sub.keys.auth }, at: new Date().toISOString() }),
    { expirationTtl: 400 * 86400 });
  return [{ ok: true, belt }];
}

async function unsubscribe(request, env) {
  const b = await request.json().catch(() => null);
  if (!b || !b.endpoint) return [{ error: "bad request" }, 400];
  const belt = clean(b.belt, 16);
  if (!validBelt(belt)) return [{ error: "unknown belt" }, 400];
  await env.BELT.delete(`sub:${belt}:${await sha16(b.endpoint)}`);
  return [{ ok: true }];
}

async function notify(request, env, ctx) {
  if (!env.NOTIFY_KEY || request.headers.get("x-notify-key") !== env.NOTIFY_KEY) return [{ error: "forbidden" }, 403];
  const b = await request.json().catch(() => null);
  if (!b) return [{ error: "bad json" }, 400];
  const belt = clean(b.belt, 16), reign = clean(b.reign, 40);
  if (!validBelt(belt) || !reign) return [{ error: "belt and reign required" }, 400];
  const mark = `n:${belt}:${reign}`;
  if (await env.BELT.get(mark)) return [{ ok: true, sent: 0, skipped: "already notified" }];
  await env.BELT.put(mark, new Date().toISOString(), { expirationTtl: 400 * 86400 });
  const payload = JSON.stringify({ title: clean(b.title, 120), body: clean(b.body, 240), url: String(b.url || "").slice(0, 300), tag: `belt-${belt}` });
  const subs = await listAll(env, `sub:${belt}:`);
  let sent = 0, dropped = 0, failed = 0;
  const work = async () => {
    for (const k of subs) {
      const raw = await env.BELT.get(k.name);
      if (!raw) continue;
      const sub = JSON.parse(raw);
      try {
        const status = await sendPush(env, sub, payload);
        if (status === 201 || status === 200) sent += 1;
        else if (status === 404 || status === 410) { dropped += 1; await env.BELT.delete(k.name); }
        else failed += 1;
      } catch (e) { failed += 1; }
    }
    await env.BELT.put(`${mark}:result`, JSON.stringify({ sent, dropped, failed, subs: subs.length }), { expirationTtl: 30 * 86400 });
  };
  ctx.waitUntil(work());
  return [{ ok: true, queued: subs.length }];
}

// RFC 8291 (aes128gcm) + RFC 8292 (VAPID), on WebCrypto only.
const te = new TextEncoder();
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = (s) => { s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "="; return Uint8Array.from(atob(s), (c) => c.charCodeAt(0)); };
const cat = (...arrs) => { const n = arrs.reduce((a, x) => a + x.length, 0); const out = new Uint8Array(n); let o = 0; for (const x of arrs) { out.set(x, o); o += x.length; } return out; };

async function hkdf(salt, ikm, info, len) {
  const key = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt, info }, key, len * 8));
}

async function vapidHeader(env, endpoint) {
  const aud = new URL(endpoint).origin;
  const jwk = JSON.parse(env.VAPID_PRIVATE_JWK);
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const head = b64u(te.encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const claims = b64u(te.encode(JSON.stringify({ aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: env.VAPID_SUBJECT || "mailto:hello@beltholders.com" })));
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, te.encode(`${head}.${claims}`));
  return `vapid t=${head}.${claims}.${b64u(sig)}, k=${env.VAPID_PUBLIC}`;
}

async function sendPush(env, sub, payload) {
  const uaPub = unb64u(sub.keys.p256dh);            // 65 bytes, uncompressed
  const auth = unb64u(sub.keys.auth);               // 16 bytes
  const asKeys = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const asPub = new Uint8Array(await crypto.subtle.exportKey("raw", asKeys.publicKey));
  const uaKey = await crypto.subtle.importKey("raw", uaPub, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: uaKey }, asKeys.privateKey, 256));
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const keyInfo = cat(te.encode("WebPush: info\0"), uaPub, asPub);
  const ikm = await hkdf(auth, shared, keyInfo, 32);
  const cek = await hkdf(salt, ikm, te.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hkdf(salt, ikm, te.encode("Content-Encoding: nonce\0"), 12);
  const plain = cat(te.encode(payload), new Uint8Array([2]));     // one record, delimiter 0x02
  const aes = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const cipher = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, aes, plain));
  const rs = new Uint8Array([0, 0, 16, 0]);                        // record size 4096
  const body = cat(salt, rs, new Uint8Array([asPub.length]), asPub, cipher);
  const r = await fetch(sub.endpoint, {
    method: "POST",
    headers: { "content-encoding": "aes128gcm", "content-type": "application/octet-stream", "ttl": "86400", "urgency": "normal",
               "authorization": await vapidHeader(env, sub.endpoint) },
    body,
  });
  return r.status;
}
