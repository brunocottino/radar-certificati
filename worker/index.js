// Worker del sito: i file di docs/ sono serviti direttamente da Cloudflare (pagina, dati, raccolte, guida);
// qui arrivano solo gli indirizzi che non sono file. /certificato/<ISIN> diventa una pagina HTML vera
// (leggibile da Google e dalle IA senza JavaScript), costruita al volo dal gruppo api/v1/isin/<gg>.json:
// 14.000 pagine sempre aggiornate senza scrivere 14.000 file a ogni run.
const SITE = "https://radarcertificati.com";
const ISIN_RE = /^[A-Z]{2}[A-Z0-9]{9}\d$/;
const FREQ = { "1m": "mensile", "2m": "bimestrale", "3m": "trimestrale", "6m": "semestrale", "12m": "annuale" };

// stesso gruppo di isin_bucket in scraper/api.py: FNV-1a a 32 bit mod 256, due cifre esadecimali
function bucket(isin) {
  let h = 0x811c9dc5;
  for (const ch of isin) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0;
  return (h % 256).toString(16).padStart(2, "0");
}

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 2) => v == null || isNaN(v) ? null : Number(v).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: d });
const pct = (v, d = 2) => v == null ? null : num(v, d) + "%";
const day = s => { if (!s) return null; const [y, m, d] = String(s).slice(0, 10).split("-"); return d && `${d}/${m}/${y}`; };

async function asset(env, path) {
  const r = await env.ASSETS.fetch(new Request(SITE + path));
  return r.ok ? r.json() : null;
}

function page({ title, desc, canonical, body, ld, noindex }) {
  return `<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title><meta name="description" content="${esc(desc)}">
${noindex ? '<meta name="robots" content="noindex">' : `<link rel="canonical" href="${canonical}">`}
<meta property="og:type" content="website"><meta property="og:site_name" content="Radar Certificati"><meta property="og:locale" content="it_IT">
<meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(desc)}"><meta property="og:url" content="${canonical || SITE}">
<meta property="og:image" content="${SITE}/icon-512.png?v=10"><meta name="twitter:card" content="summary">
<link rel="icon" href="/icon.svg?v=10" type="image/svg+xml"><link rel="apple-touch-icon" href="/apple-touch-icon.png?v=10"><link rel="stylesheet" href="/seo.css?v=1">
${ld ? `<script type="application/ld+json">${JSON.stringify(ld).replace(/</g, "\\u003c")}</script>` : ""}
</head><body>
<header class="top"><div><a class="brand" href="/"><img src="/icon-192.png" alt="" width="32" height="32">Radar Certificati</a>
<nav><a href="/">Cerca nel radar</a><a href="/certificati/">Raccolte</a><a href="/guida-certificati">Guida</a></nav></div></header>
<main>${body}</main>
<footer class="foot"><div><p>Radar Certificati è uno screener gratuito e indipendente dei certificati d'investimento quotati in Italia (SeDeX, Cert-X/EuroTLX), aggiornato ogni giorno di borsa alle 09:35 e alle 16:15.</p>
<p>Dati indicativi raccolti da fonti pubbliche. Le probabilità sono stime statistiche, non previsioni né consulenza: prima di investire leggere KID e term sheet dell'emittente.</p></div></footer>
</body></html>`;
}

function spark(hist) {
  const pts = (hist || []).filter(r => r[1] && r[2]).map(r => [r[0], (r[1] + r[2]) / 2]);
  if (pts.length < 3) return "";
  const ys = pts.map(p => p[1]), lo = Math.min(...ys), hi = Math.max(...ys), w = 600, h = 110, pad = 6;
  const x = i => pad + i * (w - 2 * pad) / (pts.length - 1), y = v => hi === lo ? h / 2 : h - pad - (v - lo) * (h - 2 * pad) / (hi - lo);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p[1]).toFixed(1)}`).join("");
  return `<h2>Andamento del prezzo</h2><div class="card"><svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Prezzo medio dal ${day(pts[0][0])} al ${day(pts.at(-1)[0])}: da ${num(pts[0][1])} a ${num(pts.at(-1)[1])}"><path d="${d}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke" style="color:var(--accent)"/></svg>
<p class="note">Prezzo medio tra denaro e lettera, ${pts.length} rilevazioni dal ${day(pts[0][0])} al ${day(pts.at(-1)[0])}: minimo ${num(lo)}, massimo ${num(hi)}, ultimo ${num(pts.at(-1)[1])}.</p></div>`;
}

function certPage(isin, c, hist, hubs) {
  const unds = c.underlyings || [];
  const undTxt = unds.length > 3 ? unds.slice(0, 3).join(", ") + ` e altri ${unds.length - 3}` : unds.join(", ") || "sottostanti non indicati";
  const type = c.type || c.category || "Certificato";
  const freq = FREQ[c.freq];
  const price = c.bid && c.ask ? `${num(c.bid)} / ${num(c.ask)}${c.currency && c.currency !== "EUR" ? " " + c.currency : ""}` : null;
  const prob = c.probBarrierHold != null ? Math.round(c.probBarrierHold * 100) : null;
  const iss = hubs?.issuers?.[c.issuer], cat = hubs?.families?.filter(f => new RegExp(f[2], "i").test(`${c.type || ""} ${c.callable || ""} ${c.typeMarket || ""}`)) || [];
  const tick = new Map((c.underlyingsRisk || []).map(u => [u.name, u.ticker]));

  // descrizione in parole: è quella che leggono motori e assistenti
  const s = [];
  s.push(`Il certificato <b>${esc(isin)}</b> è un <b>${esc(type)}</b> emesso da ${esc(c.issuer || "emittente non indicato")}${c.platform && c.platform !== c.issuer ? ` (piattaforma ${esc(c.platform)})` : ""}${c.market ? `, quotato su ${esc(c.market)}` : ""}, con sottostante ${unds.length > 1 ? "i titoli" : ""} ${esc(undTxt)}.`);
  if (c.couponPa) s.push(`Prevede una cedola${c.triggerPct ? " condizionata" : ""} del <b>${pct(c.couponPa)} annuo</b>${freq ? `, pagata con frequenza ${freq}` : ""}${c.triggerPct ? `, se ${unds.length > 1 ? "tutti i sottostanti sono" : "il sottostante è"} sopra il ${pct(c.triggerPct, 1)} dello strike` : ""}${c.memory ? ", con effetto memoria (le cedole non pagate vengono recuperate)" : ""}.`);
  if (c.barrierPct) s.push(`La barriera capitale è al <b>${pct(c.barrierPct, 1)}</b> dello strike${c.barrierType ? ` (osservazione ${c.barrierType === "continua" ? "continua" : "solo a scadenza"})` : ""}${c.distBarrier != null ? `; il sottostante peggiore${c.worstName ? `, ${esc(c.worstName)},` : ""} ${c.distBarrier >= 0 ? `può scendere ancora del ${pct(c.distBarrier, 1)} prima di toccarla` : `è <b class="bad">sotto la barriera</b> (${pct(c.distBarrier, 1)})`}` : ""}.`);
  if (c.autocallPct || c.callable) s.push(`Rimborso anticipato: ${esc(c.callable || "previsto")}${c.autocallPct ? ` se i sottostanti sono sopra il ${pct(c.autocallPct, 1)} dello strike` : ""}${c.nextCallDate ? `, prossima data ${day(c.nextCallDate)}` : ""}.`);
  if (c.maturity) s.push(`Scadenza il <b>${day(c.maturity)}</b>.`);
  if (price) s.push(`Ultimo prezzo denaro/lettera: ${price}${c.nominal ? ` su nominale ${num(c.nominal)}` : ""}${c.priceAt ? ` (${day(c.priceAt)})` : ""}.`);
  if (prob != null) s.push(`Probabilità stimata che la barriera tenga fino a scadenza: <b>${prob}%</b> (simulazione statistica sulla volatilità storica, non una previsione).`);

  const kv = [["ISIN", isin], ["Emittente", c.issuer], ["Tipologia", type], ["Mercato", c.market], ["Cedola annua", pct(c.couponPa)],
    ["Frequenza cedola", freq], ["Effetto memoria", c.memory == null ? null : c.memory ? "Sì" : "No"], ["Trigger cedola", pct(c.triggerPct, 1)],
    ["Barriera capitale", pct(c.barrierPct, 1)], ["Tipo barriera", c.barrierType], ["Distanza dalla barriera", pct(c.distBarrier, 1)],
    ["Livello autocall", pct(c.autocallPct, 1)], ["Prossima cedola", day(c.nextCouponDate)], ["Prossimo richiamo", day(c.nextCallDate)],
    ["Scadenza", day(c.maturity)], ["Denaro / lettera", price], ["Nominale", num(c.nominal)], ["Prob. tenuta barriera", prob != null ? prob + "%" : null],
    ["Settore", c.sector]].filter(r => r[1] != null && r[1] !== "");

  const det = new Map((c.underlyingsDetail || []).map(u => [u.name, u]));
  const risk = new Map((c.underlyingsRisk || []).map(u => [u.name, u]));
  const undRows = unds.map(n => {
    const d = det.get(n) || {}, r = risk.get(n) || {}, t = tick.get(n), hub = t && hubs?.tickers?.[t];
    return `<tr><td>${hub ? `<a href="/certificati/${hub}">${esc(n)}</a>` : esc(n)}</td><td class="r">${num(d.strike, 4) ?? "–"}</td><td class="r">${pct(d.dist ?? r.dist, 1) ?? "–"}</td><td class="r">${r.vol1y != null ? pct(r.vol1y * 100, 0) : "–"}</td></tr>`;
  }).join("");

  const links = [];
  if (iss) links.push(`<a href="/certificati/${iss}">Tutti i certificati ${esc(c.issuer)}</a>`);
  for (const f of cat) links.push(`<a href="/certificati/${f[1]}">Certificati ${esc(f[0])}</a>`);
  for (const n of unds) { const h = hubs?.tickers?.[tick.get(n)]; if (h) links.push(`<a href="/certificati/${h}">Certificati su ${esc(n)}</a>`); }
  if (c.sector && hubs?.sectors?.[c.sector]) links.push(`<a href="/certificati/${hubs.sectors[c.sector]}">Settore ${esc(c.sector)}</a>`);

  const title = `${isin} · ${type} su ${undTxt} | Radar Certificati`;
  const desc = [`${type} di ${c.issuer || "emittente n.d."} su ${undTxt}`, c.couponPa && `cedola ${pct(c.couponPa)} annua`,
    c.barrierPct && `barriera ${pct(c.barrierPct, 1)}`, c.distBarrier != null && `distanza ${pct(c.distBarrier, 1)}`,
    c.maturity && `scadenza ${day(c.maturity)}`].filter(Boolean).join(", ") + ". Prezzo, probabilità di tenuta della barriera e storico.";
  const url = `${SITE}/certificato/${isin}`;
  const ld = [{
    "@context": "https://schema.org", "@type": "FinancialProduct", name: `${type} ${isin}`, identifier: isin, url,
    description: desc, category: c.category || type, provider: c.issuer ? { "@type": "Organization", name: c.issuer } : undefined,
    ...(c.couponPa ? { annualPercentageRate: c.couponPa } : {}),
    additionalProperty: kv.map(([k, v]) => ({ "@type": "PropertyValue", name: k, value: String(v) })),
  }, {
    "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [
      { "@type": "ListItem", position: 1, name: "Radar Certificati", item: SITE + "/" },
      ...(iss ? [{ "@type": "ListItem", position: 2, name: c.issuer, item: `${SITE}/certificati/${iss}` }] : []),
      { "@type": "ListItem", position: iss ? 3 : 2, name: isin, item: url }],
  }];
  const body = `<p class="crumbs"><a href="/">Radar Certificati</a> › ${iss ? `<a href="/certificati/${iss}">${esc(c.issuer)}</a> › ` : ""}${esc(isin)}</p>
<h1>${esc(type)} su ${esc(undTxt)}</h1><p class="sub">ISIN ${esc(isin)} · ${esc(c.issuer || "")}${c.updatedAt ? ` · dati del ${day(c.updatedAt)}` : ""}</p>
<p class="lead">${s.join(" ")}</p>
<div class="btns"><a class="btn primary" href="/#isin=${isin}&q=${isin}">Apri nel radar: grafici, rendimento, confronto</a>${c.url ? `<a class="btn" href="${esc(c.url)}" rel="nofollow noopener" target="_blank">Scheda dell'emittente</a>` : ""}
<a class="btn" href="https://www.borsaitaliana.it/borsa/cw-e-certificates/scheda/${isin}-SEDX.html?lang=it" rel="nofollow noopener" target="_blank">Borsa Italiana</a></div>
<h2>Dati principali</h2><div class="card"><dl class="kv">${kv.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl></div>
${unds.length ? `<h2>Sottostanti</h2><div class="tw"><table><thead><tr><th>Sottostante</th><th class="r">Strike</th><th class="r">Distanza barriera</th><th class="r">Volatilità 1 anno</th></tr></thead><tbody>${undRows}</tbody></table></div>` : ""}
${spark(hist)}
${links.length ? `<h2>Certificati simili</h2><ul class="tags">${links.map(l => `<li>${l}</li>`).join("")}</ul>` : ""}
<p class="note">Fonte: ${esc(c.source || "fonti pubbliche")}${c.priceSource ? `; prezzi: ${esc(c.priceSource)}` : ""}. Le informazioni possono essere incomplete o non aggiornate: verificare sempre KID e term sheet.</p>`;
  return page({ title, desc, canonical: url, body, ld });
}

function notFound(isin) {
  const body = `<h1>Certificato non trovato</h1><p class="lead">${isin ? `L'ISIN <b>${esc(isin)}</b> non è nell'archivio del radar (forse scaduto o rimborsato).` : "Pagina inesistente."}</p>
<div class="btns"><a class="btn primary" href="/">Cerca nel radar</a>${isin ? `<a class="btn" href="https://www.borsaitaliana.it/borsa/cw-e-certificates/scheda/${esc(isin)}-SEDX.html?lang=it" rel="nofollow noopener">Cercalo su Borsa Italiana</a>` : ""}</div>`;
  return new Response(page({ title: "Non trovato | Radar Certificati", desc: "Pagina non trovata", body, noindex: true }),
    { status: 404, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=600" } });
}

export default {
  async fetch(request, env) {
    const u = new URL(request.url);
    const m = u.pathname.match(/^\/certificato\/([A-Za-z0-9]{12})\/?$/);
    if (!m) return notFound(null);
    const isin = m[1].toUpperCase();
    if (m[1] !== isin || u.pathname.endsWith("/")) return Response.redirect(`${u.origin}/certificato/${isin}`, 301);
    if (!ISIN_RE.test(isin)) return notFound(isin);
    const [g, hubs] = await Promise.all([asset(env, `/api/v1/isin/${bucket(isin)}.json`), asset(env, "/certificati/hubs.json").catch(() => null)]);
    const e = g?.certificates?.[isin];
    if (!e) return notFound(isin);
    return new Response(certPage(isin, e.certificate, e.history, hubs), {
      headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=1800" },
    });
  },
};
