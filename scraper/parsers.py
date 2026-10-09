"""Parser specifici per le API interne degli emittenti.

Ogni parser riceve (DISC, src, NOW, ctx): la cartella discovery/, la sorgente di
sources.py, il timestamp della run e il contesto Playwright già "scaldato" dalla
visita alla pagina della sorgente (cookie, consenso). Le chiamate alle API partono
da dentro una pagina del sito (fetch same-origin), così hanno gli stessi header
e cookie del browser. Restituisce una lista di certificati nello schema di
docs/data/certs.json.
"""
import json
import os
import re
from pathlib import Path

from run import ISIN_RE, accept_cookies, freq_of, norm, num, pdate


# ---------------------------------------------------------------- utilità

async def open_page(ctx, url):
    page = await ctx.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(2000)
    await accept_cookies(page)
    return page


async def fetch(page, url, method="GET", body=None, headers=None):
    """fetch() eseguita nella pagina: restituisce (status, testo)."""
    return await page.evaluate(
        """async ([url, method, body, headers]) => {
            const r = await fetch(url, {method, body, headers, credentials: 'include'});
            return [r.status, await r.text()];
        }""",
        [url, method, body, headers or {}],
    )


async def fetch_json(page, url, payload):
    st, txt = await fetch(page, url, "POST", json.dumps(payload),
                          {"content-type": "application/json", "accept": "application/json"})
    if st != 200:
        raise RuntimeError(f"{url} -> HTTP {st}: {txt[:300]}")
    return json.loads(txt)


def save(DISC, name, obj):
    (DISC / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1)[:3_000_000])


def clean(c):
    return {k: v for k, v in c.items() if v not in (None, "", [])}


def months_to_freq(m):
    return {1: "1m", 3: "3m", 6: "6m", 12: "12m"}.get(int(m)) if m else None


# ---------------------------------------------------------------- BNP Paribas

BNP_API = "https://investimenti.bnpparibas.it/apiv2/api/v1/productlist/"
BNP_BODY = {"clientId": 1, "languageId": "it", "countryId": "", "sortPreference": [], "filterSelections": [],
            "deeplinkParameters": None, "oldDeepLinkString": None, "firstUnderlyingIsin": None, "isBNL": None,
            "isDB": None, "responsetype": None, "productFlagFilter": 5, "isDirectionFilterCanBeDisabled": True,
            "derivativeTypeIds": [], "productSetIds": [22, 23], "productSubGroupIds": [], "productGroupIds": [6],
            "offset": 0, "limit": 50, "resolveSubPreset": True, "resolveOnlySelectedPresets": False,
            "allowLeverageGrouping": False}


def barrier_type(v):
    """Tipo di barriera dell'emittente -> "scadenza" | "continua" (None se non riconosciuto)."""
    n = norm(v)
    if re.search(r"maturity|scadenza|europe|final", n):
        return "scadenza"
    if re.search(r"continu|americ|daily|giornalier|intraday", n):
        return "continua"
    return None


def bnp_cert(r, src, NOW):
    f = r.get("first") or {}
    kf = r.get("keyFigures") or {}
    items = [u for u in r.get("underlyingItems") or [] if not u.get("isBasketIdentifier")]
    unds = [u.get("underlyingName") for u in items if u.get("underlyingName")] or [f.get("underlyingName")]
    dists = [u["distanceToKnockInPercent"] for u in items if u.get("distanceToKnockInPercent") is not None]
    dist = f.get("distanceToKnockInPercent")
    if dist is None and dists:
        dist = min(dists)
    worst = min((u for u in items if u.get("distanceToKnockInPercent") is not None),
                key=lambda u: u["distanceToKnockInPercent"]) if dists else None
    trig = None
    m = re.search(r"([\d.,]+)\s*%", f.get("nextCondition") or "")
    if m:
        trig = num(m.group(1))
    if trig is None:
        trig = f.get("knockInPercent2")
    act = r.get("autocallType")
    return clean({
        "isin": r["isin"], "issuer": src["issuer"], "source": src["name"],
        "type": r.get("derivativeTypeName"), "underlyings": unds,
        "underlyingsDetail": [clean({"name": u.get("underlyingName"), "strike": u.get("strikeAbsolute"),
                                     "dist": u.get("distanceToKnockInPercent"),
                                     "isin": u.get("underlyingISIN") if ISIN_RE.fullmatch(u.get("underlyingISIN") or "") else None})
                              for u in items] if items else None,
        "barrierType": barrier_type(items[0].get("barrierTypeName") if items else None),
        "worstName": worst.get("underlyingName") if worst else None,
        "couponPa": r.get("premiumPerAnnumPercent"),
        "freq": months_to_freq(kf.get("couponFrequency")) or freq_of(kf.get("couponFrequencyText")),
        "distBarrier": dist, "barrierPct": f.get("knockInPercent"), "triggerPct": trig,
        "maturity": pdate(kf.get("maturityDate") or r.get("maturityDate")),
        "bid": r.get("bid") or None, "ask": r.get("ask") or None,
        "nominal": kf.get("issuancePrice"),
        "callable": {1: "Callable emittente", 2: "Autocall"}.get(act),
        "memory": bool((r.get("config") or {}).get("hasMemoryEffect")),
        "currency": (r.get("currency") or {}).get("isoCode"), "market": r.get("exchange"),
        "nextCouponDate": pdate(f.get("nextObservationDate")),
        "url": f"https://investimenti.bnpparibas.it/product-details/{r['isin']}/",
        "updatedAt": NOW,
    })


async def bnp_api(DISC, src, NOW, ctx):
    page = await ctx.new_page()
    orig = []
    page.on("request", lambda q: orig.append(q) if "/productlist" in q.url and q.method == "POST" else None)
    await page.goto(src["url"], wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(2500)
    await accept_cookies(page)
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    out, log = {}, {"pages": []}
    hdr = {"content-type": "application/json", "accept": "application/json"}
    body0 = dict(BNP_BODY)
    if orig:
        q = orig[0]
        h = await q.all_headers()
        log["orig_headers"] = {k: v for k, v in h.items() if k.lower() != "cookie"}
        hdr = {k: v for k, v in h.items() if not k.startswith(":") and k.lower() not in
               ("content-length", "cookie", "host", "accept-encoding", "connection")}
        try:
            body0 = json.loads(q.post_data)
        except Exception:
            pass
        log["orig_body"] = body0
    try:
        for sets in (body0.get("productSetIds") or [22, 23], []):
            off, total = 0, None
            while total is None or off < total:
                body = {**body0, "productSetIds": sets, "offset": off, "limit": 50}
                r = await ctx.request.post(BNP_API, data=json.dumps(body), headers=hdr)
                txt = await r.text()
                if r.status != 200:
                    log["pages"].append({"sets": sets, "offset": off, "status": r.status, "err": txt[:500]})
                    break
                d = json.loads(txt)
                total = d.get("total") or 0
                res = d.get("result") or []
                log["pages"].append({"sets": sets, "offset": off, "got": len(res), "total": total})
                if not res:
                    break
                for x in res:
                    if x.get("isin") and x["isin"] not in out:
                        out[x["isin"]] = bnp_cert(x, src, NOW)
                off += len(res)
                if off > 5000:
                    break
    finally:
        save(DISC, f"{src['name']}_parser.json", log)
        await page.close()
    # solo prodotti a cedola/barriera (il gruppo 6 contiene anche protetti, tracker…)
    return [c for c in out.values() if c.get("couponPa") is not None or c.get("barrierPct") is not None]


# ---------------------------------------------------------------- sonde (Leonteq / SocGen / Marex)
# Questi siti non hanno esposto un'API prodotti al primo giro: le sonde provano
# endpoint candidati e salvano tutto in discovery/<nome>_probe.json.

def generic_items(obj, depth=0):
    """Trova la lista di dict più grande che contiene ISIN."""
    best = []
    if depth > 6:
        return best
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:5]) and ISIN_RE.search(json.dumps(obj[:3])):
            best = obj
        for x in obj[:3]:
            b = generic_items(x, depth + 1)
            if len(b) > len(best):
                best = b
    elif isinstance(obj, dict):
        for v in obj.values():
            b = generic_items(v, depth + 1)
            if len(b) > len(best):
                best = b
    return best


GEN_KEYS = [
    ("couponPa", r"coupon.*(p ?a|annu|year)|premium.*(p ?a|annu)|cedola.*(p ?a|annu)"),
    ("distBarrier", r"dist.*barr|buffer|distance.*(knock|barrier)"),
    ("barrierPct", r"^(barrier|barriera|knockin)( ?(level|pct|percent|%))?$"),
    ("triggerPct", r"trigger|coupon ?barrier"),
    ("maturity", r"matur|scadenz|expir|redemption ?date|final ?fixing"),
    ("bid", r"^bid( ?price)?$|denaro"), ("ask", r"^ask( ?price)?$|^offer( ?price)?$|lettera"),
    ("freq", r"freq"), ("type", r"product ?type|tipo"),
]


def flat(d, p=""):
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            out.update(flat(v, p + k + " "))
        else:
            out[p + k] = v
    return out


def generic_cert(it, src, NOW):
    f = flat(it)
    isin = next((v for k, v in f.items() if isinstance(v, str) and norm(k).endswith("isin") and ISIN_RE.fullmatch(v)), None)
    if not isin:
        m = ISIN_RE.search(json.dumps(it))
        isin = m and m.group(1)
    if not isin:
        return None
    c = {"isin": isin, "issuer": src["issuer"], "source": src["name"], "updatedAt": NOW, "url": src["url"]}
    for k, v in f.items():
        n = norm(k.split(" ")[-1]) if " " in k else norm(k)
        for key, rx in GEN_KEYS:
            if key not in c and re.search(rx, n):
                if key == "maturity":
                    v = pdate(v)
                elif key == "freq":
                    v = freq_of(v)
                elif key == "type":
                    v = v if isinstance(v, str) else None
                else:
                    v = num(v)
                if v not in (None, ""):
                    c[key] = v
                break
    for k, v in f.items():
        if re.search(r"underlying", k, re.I) and isinstance(v, list):
            names = [x.get("name") or x.get("underlyingName") for x in v if isinstance(x, dict)]
            if any(names):
                c["underlyings"] = [n for n in names if n]
                break
    return c


async def probe(DISC, src, NOW, ctx, start, calls):
    page = await ctx.new_page()
    seen = []
    page.on("request", lambda q: seen.append({"m": q.method, "url": q.url[:300], "post": (q.post_data or "")[:800]})
            if q.resource_type in ("xhr", "fetch") and len(seen) < 60 else None)
    res = {"start": start, "results": []}
    found = []
    try:
        await page.goto(start, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        await accept_cookies(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        res["final_url"] = page.url
        res["links"] = await page.evaluate(
            "() => [...new Set([...document.querySelectorAll('a[href]')].map(a=>a.href)"
            ".filter(h=>/prod|search|cerca|certif|finder|list/i.test(h)))].slice(0,80)")
        for method, url, body in calls:
            try:
                st, txt = await fetch(page, url, method, json.dumps(body) if body is not None else None,
                                      {"content-type": "application/json", "accept": "application/json"})
            except Exception as e:
                res["results"].append({"url": url, "error": repr(e)[:300]})
                continue
            entry = {"url": url, "method": method, "body": body, "status": st, "len": len(txt),
                     "isins": len(set(ISIN_RE.findall(txt))), "head": txt[:1500]}
            res["results"].append(entry)
            if st == 200 and entry["isins"]:
                try:
                    items = generic_items(json.loads(txt))
                    found += [c for c in (generic_cert(i, src, NOW) for i in items) if c]
                    entry["items"] = len(items)
                    entry["sample"] = items[:2]
                except Exception as e:
                    entry["parse_error"] = repr(e)[:200]
    finally:
        res["xhr"] = seen
        save(DISC, f"{src['name']}_probe.json", res)
        await page.close()
    return found


LEONTEQ_FILTERS = {"partner": "LEONTEQ", "regions": ["IT"], "language": "it", "currencies": [], "issuers": [],
                   "productCategories": [], "productGroups": [], "productTypes": [], "maturityRangeKey": [],
                   "distanceToBarriers": [], "barrierLevelRanges": [], "strikeLevelRanges": [], "underlyings": [],
                   "omni": "", "conditions": {}, "underlyingSearchString": "", "marketVenues": [], "assetClasses": [],
                   "barrierTypes": [], "countrySpecificTitles": [], "couponFrequencies": []}


def lv(p, k, f="raw"):
    v = p.get(k)
    return v.get(f) if isinstance(v, dict) else None


def pct(x):
    x = num(x)
    return round(x * 100, 4) if x is not None else None


# chiavi emittente della piattaforma Leonteq -> nome leggibile
LEONTEQ_ISSUERS = [
    (r"^leonteq.*guernsey", "Leonteq Securities (Guernsey)"), (r"^leonteq", "Leonteq Securities"),
    (r"^efg", "EFG International"), (r"^raiffeisen", "Raiffeisen"), (r"^swissquote", "Swissquote"),
    (r"^bil$", "BIL"), (r"^bkb$", "Basler Kantonalbank"), (r"^akb$", "Aargauische Kantonalbank"),
    (r"^deutsche ?bank", "Deutsche Bank"), (r"^standard ?chartered", "Standard Chartered"),
    (r"^corner ?bank", "Cornèr Banca"), (r"^mora", "Mora"), (r"^post ?finance", "PostFinance"),
    (r"^jpm|^jp ?morgan", "J.P. Morgan"),
]


def leonteq_issuer(p):
    """Emittente reale del prodotto (la piattaforma è sempre Leonteq)."""
    for k in ("issuer", "issuerName", "issuer-name", "issuerKey", "issuer-key", "issuerDisplayName"):
        v = p.get(k)
        if isinstance(v, dict):
            v = v.get("value") or v.get("raw") or v.get("name")
        if isinstance(v, str) and v.strip():
            v = v.strip()
            for rx, name in LEONTEQ_ISSUERS:
                if re.search(rx, v, re.I):
                    return name
            return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", v)
    return None


def leonteq_cert(p, src, NOW):
    isin = lv(p, "isin", "value")
    if not isin:
        return None
    ulist = [u for u in (p.get("underlyingList") or {}).get("values") or [] if u.get("shortName")]
    unds = [u.get("shortName") for u in ulist]
    sub = lv(p, "subtitle", "value") or ""
    ptype = lv(p, "product-type", "value")
    name = (lv(p, "name", "value") or "") + " " + (ptype or "")
    return clean({
        "isin": isin, "issuer": leonteq_issuer(p) or "Leonteq Securities", "platform": "Leonteq",
        "underlyingsDetail": [clean({"name": u.get("shortName"), "isin": u.get("isin")}) for u in ulist] or None,
        "barrierType": barrier_type(lv(p, "barrier-type", "value")),
        "source": src["name"], "type": ptype,
        "underlyings": unds or [x.strip() for x in (lv(p, "underlyings", "value") or "").split(",") if x.strip()],
        "couponPa": pct(lv(p, "conditional-coupon")) if lv(p, "conditional-coupon") is not None else pct(lv(p, "coupon")),
        "triggerPct": pct(lv(p, "conditionalCouponTriggerLevel")),
        "barrierPct": pct(lv(p, "barrier")),
        "distBarrier": pct(lv(p, "distance-to-barrier-level")),
        "maturity": pdate(lv(p, "redemption-date") or lv(p, "last-trading-date")),
        "bid": (p.get("bid") or {}).get("initialValue") or None,
        "ask": (p.get("ask") or {}).get("initialValue") or None,
        "nominal": num(lv(p, "issue-price")),
        "currency": lv(p, "currency", "value"),
        "callable": sub if re.search(r"call", sub, re.I) else ("Autocall" if re.search(r"express|autocall", name, re.I) else None),
        "memory": True if re.search(r"memory|memoria", name, re.I) else None,
        "market": ", ".join(m.get("marketVenue", "") for m in (p.get("listingMarkets") or {}).get("values") or []) or None,
        "url": f"https://certificati.leonteq.com/isin/{isin}",
        "updatedAt": NOW,
    })


async def leonteq_api(DISC, src, NOW, ctx):
    base = "https://certificati.leonteq.com"
    api = base + "/api/product-model/search"
    page = await ctx.new_page()
    orig = []
    page.on("request", lambda q: orig.append(q.post_data) if q.url == api and q.method == "POST" else None)
    log = {"pages": []}
    found = {}
    try:
        await page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        log["final"] = page.url
        body = json.loads(orig[0]) if orig else {
            "partner": "LEONTEQ", "currencies": [], "productCategories": [], "productGroups": [], "productTypes": [],
            "maturityRangeKey": [], "distanceToBarriers": [], "barrierLevelRanges": [], "strikeLevelRanges": [],
            "underlyings": [], "marketVenues": [], "assetClasses": [], "barrierTypes": [], "countrySpecificTitles": [],
            "couponFrequencies": [], "sortFields": [],
            "displayColumns": ["valor", "coupon", "conditionalCoupon", "underlying", "barrierPercentage", "currency",
                               "lastTradingDate", "bidAsk", "subscriptionEndDate", "documentLinks"],
            "language": "it", "regions": ["IT"]}
        # tutto il listino italiano: niente filtro emittente / nuove emissioni
        body.update({"issuers": [], "omni": "", "conditions": {"": True}, "resultsPerPage": 100})
        log["body"] = body
        pno, total = 1, None
        while total is None or (pno - 1) * 100 < total:
            # fetch dalla pagina (cookie/stato Incapsula del browser); se bloccata ricarica e riprova
            for attempt in range(3):
                try:
                    st, txt = await fetch(page, api, "POST", json.dumps({**body, "pageNumber": pno}),
                                          {"content-type": "application/json", "accept": "*/*"})
                except Exception as e:
                    st, txt = 0, repr(e)
                if st == 200:
                    break
                log["pages"].append({"page": pno, "attempt": attempt, "status": st, "err": txt[:300]})
                await page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(8000)
            if st != 200:
                break
            d = json.loads(txt)
            total = (d.get("searchMetadata") or {}).get("totalHits") or 0
            prods = d.get("products") or []
            log["pages"].append({"page": pno, "got": len(prods), "total": total})
            if pno == 1:
                log["sample"] = prods[:2]
            if not prods:
                break
            for p in prods:
                c = leonteq_cert(p, src, NOW)
                if c:
                    found[c["isin"]] = c
            pno += 1
            if pno > 60:
                break
    finally:
        # la ricerca non riporta l'emittente: lo ricaviamo filtrando per ciascun emittente
        # (solo per gli ISIN nuovi: gli altri hanno già l'emittente in archivio, e Incapsula
        #  blocca il runner se le richieste sono troppe)
        from run import DATA
        known = {}
        try:
            known = {c["isin"]: c["issuer"] for c in json.loads(DATA.read_text()).get("certs", [])
                     if c.get("platform") == "Leonteq" and c.get("issuer")}
        except Exception:
            pass
        unknown = [i for i in found if i not in known]
        log["issuer_unknown"] = len(unknown)
        for i, c in found.items():
            c["issuer"] = known.get(i, c["issuer"])
        if unknown:
            try:
                await leonteq_assign_issuers(page, api, body, {i: found[i] for i in unknown}, total, log)
            except Exception as e:
                log["issuer_error"] = repr(e)[:500]
        log["issuers"] = {}
        for c in found.values():
            log["issuers"][c["issuer"]] = log["issuers"].get(c["issuer"], 0) + 1
        save(DISC, f"{src['name']}_parser.json", log)
        await page.close()
    return list(found.values())


LEONTEQ_ISSUER_KEYS = ["Leonteq", "LeonteqGuernsey", "LeonteqTCM", "LeonteqGuernseyTCM", "LeonteqAMGuernsey", "BIL",
                       "EFG International Guernsey", "EFGInternationalFinanceGuernseyFLT", "EFG Int Hedge", "Raiffeisen",
                       "RaiffeisenAmsterdam", "Swissquote", "Swissquote Europe", "Mora", "Standard Chartered Bank London",
                       "BKB", "CornerBank2", "DeutscheBank"]


async def leonteq_assign_issuers(page, api, body, found, total, log):
    keys = LEONTEQ_ISSUER_KEYS
    try:
        st, txt = await fetch(page, "https://certificati.leonteq.com/content/main.json?language_id=5")
        if st == 200:
            keys = list((json.loads(txt).get("issuers") or {}).keys()) or keys
    except Exception:
        pass
    per = {}
    for key in keys:
        pno, hits = 1, None
        while hits is None or (pno - 1) * 100 < hits:
            await page.wait_for_timeout(1500)
            st, txt = await fetch(page, api, "POST", json.dumps({**body, "issuers": [key], "pageNumber": pno}),
                                  {"content-type": "application/json", "accept": "*/*"})
            if st != 200:
                per[key] = f"HTTP {st}"
                break
            d = json.loads(txt)
            hits = (d.get("searchMetadata") or {}).get("totalHits") or 0
            if total and hits >= total and len(keys) > 1:  # filtro ignorato: non assegnare
                per[key] = f"filtro ignorato ({hits})"
                break
            prods = d.get("products") or []
            for p in prods:
                isin = lv(p, "isin", "value")
                if isin in found:
                    found[isin]["issuer"] = leonteq_issuer({"issuer": key})
            per[key] = hits
            if not prods or pno >= 20:
                break
            pno += 1
    log["per_issuer"] = per


async def leonteq_probe(DISC, src, NOW, ctx):
    b = "https://certificati.leonteq.com/website-api/brochure/search"
    calls = [
        ("POST", b, {**LEONTEQ_FILTERS, "from": 0, "size": 100}),
        ("POST", b, {**LEONTEQ_FILTERS, "page": 0, "pageSize": 100}),
        ("POST", b + "/products", {**LEONTEQ_FILTERS, "page": 0, "pageSize": 100}),
        ("POST", b + "/results", {**LEONTEQ_FILTERS, "page": 0, "size": 100}),
        ("POST", b + "/filters", LEONTEQ_FILTERS),
    ]
    out = await probe(DISC, src, NOW, ctx, "https://certificati.leonteq.com/", calls)
    return out


async def socgen_probe(DISC, src, NOW, ctx):
    page = await open_page(ctx, src["url"])
    info = {"scripts": {}}
    try:
        await page.wait_for_timeout(4000)
        for _ in range(3):  # disclaimer di residenza (bottone "OK")
            ok = page.get_by_role("button", name=re.compile(r"^\s*ok\s*$", re.I))
            if await ok.count():
                try:
                    await ok.first.click(timeout=3000)
                except Exception:
                    pass
                await page.wait_for_timeout(2500)
        st, cfg = await fetch(page, "https://www.prodotti.societegenerale.it/EmcWebApi/api/AppConfig")
        info["appconfig"] = cfg[:20000]
        urls = await page.evaluate("() => performance.getEntriesByType('resource').map(e => e.name)"
                                   ".filter(u => /\\.js(\\?|$)/.test(u) && u.includes('societegenerale'))")
        info["script_urls"] = urls
        for u in urls[:40]:
            try:
                st, t = await fetch(page, u)
            except Exception as e:
                info["scripts"][u] = repr(e)[:200]
                continue
            hits = sorted(set(re.findall(r'["\'`]([^"\'`\s]{0,80}(?:EmcWebApi|api/|[Pp]roduct[A-Za-z]*/|[Ss]earch)[^"\'`\s]{0,120})["\'`]', t)))
            if hits:
                info["scripts"][u] = hits[:300]
        # bottoni presenti nella pagina di ricerca
        info["buttons"] = await page.evaluate("() => [...document.querySelectorAll('button,a.btn,[role=button]')].map(b=>b.innerText.trim()).filter(Boolean).slice(0,60)")
    except Exception as e:
        info["error"] = repr(e)[:500]
    finally:
        save(DISC, f"{src['name']}_js.json", info)
        await page.close()
    return await probe(DISC, src, NOW, ctx, src["url"], [])


async def marex_probe(DISC, src, NOW, ctx):
    calls = [("GET", "https://fp.marex.com/api/products", None), ("GET", "https://fp.marex.com/api/products?country=IT", None)]
    return await probe(DISC, src, NOW, ctx, src["url"], calls)


# ---------------------------------------------------------------- Société Générale
# Sito Angular con API EmcWebApi. Dopo l'avviso di residenza ("OK") la pagina di
# ricerca chiama ProductSearch/GridConfig e poi ProductSearch/Search (POST).
# Intercettiamo quella richiesta e la ripetiamo cambiando pagina finché ci sono risultati.

SG = "https://www.prodotti.societegenerale.it"
SG_API = SG + "/EmcWebApi/api/ProductSearch/"
SG_PAGE_KEYS = ("PageIndex", "pageIndex", "Page", "page", "PageNumber", "pageNumber", "CurrentPage", "currentPage")
SG_SIZE_KEYS = ("PageSize", "pageSize", "Take", "take", "Size", "size", "ItemsPerPage", "itemsPerPage")


def sg_key(d, keys):
    if isinstance(d, dict):
        for k in keys:
            if k in d:
                return d, k
        for v in d.values():
            r = sg_key(v, keys)
            if r:
                return r
    return None


def sg_cert(it, src, NOW):
    c = generic_cert(it, src, NOW)
    if not c:
        return None
    f = {norm(k): v for k, v in flat(it).items()}
    for k, v in f.items():
        if "underlying" in k and "name" in k and isinstance(v, str) and "underlyings" not in c:
            c["underlyings"] = [x.strip() for x in re.split(r"\s*[,;/]\s*", v) if x.strip()]
    c["url"] = f"{SG}/it/prodotto/{c['isin']}"
    return c


SG_CLASS_RX = re.compile(r"cash ?collect|phoenix|express|autocall|premium|fixed ?coupon|cedol|coupon|memory|income", re.I)


def sg_classes(obj, out=None):
    """Raccoglie {id: (nome, conteggio)} delle classificazioni prodotto da qualunque struttura JSON."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        cid = obj.get("ProductClassificationId")
        name = obj.get("DisplayName") or obj.get("Name")
        if isinstance(cid, int) and isinstance(name, str):
            out[cid] = (name.strip(), obj.get("ProductsCount"))
        for v in obj.values():
            sg_classes(v, out)
    elif isinstance(obj, list):
        for v in obj:
            sg_classes(v, out)
    return out


async def sg_get(page, path, params=None):
    from urllib.parse import urlencode
    url = SG_API + path + ("?" + urlencode(params, doseq=True) if params else "")
    st, txt = await fetch(page, url, "GET", None, {"accept": "application/json"})
    return url, st, txt


def sg_items(txt):
    d = json.loads(txt)
    if isinstance(d, dict):
        for k in ("Products", "products", "Items", "items", "Data", "data"):
            if isinstance(d.get(k), list):
                return d[k], d.get("TotalCount") or d.get("totalCount")
    return generic_items(d), None


def sg_cert_grid(it, grid, src, NOW):
    """Certificato da un elemento di Search usando le etichette di GridConfig (Name -> Label)."""
    from run import map_headers
    c = sg_cert(it, src, NOW)
    if not c or not grid:
        return c
    names = [g.get("Name") for g in grid]
    col = map_headers([re.sub(r"<[^>]+>|-", "", g.get("Label") or "") for g in grid])
    for key, idx in col.items():
        v = it.get(names[idx])
        if v in (None, "") or key in ("isin", "issuer"):
            continue
        if key == "maturity":
            v = pdate(v)
        elif key == "freq":
            v = freq_of(v)
        elif key in ("underlyings",):
            v = [x.strip() for x in re.split(r"\s*[,;/]\s*", str(v)) if x.strip()]
        elif key in ("type", "callable"):
            v = str(v)
        else:
            v = num(v)
        if v not in (None, "", []):
            c[key] = v
    return c


def sg_detail(c, d):
    """Arricchisce un certificato SocGen con il dettaglio Products/{isin} e con il nome prodotto."""
    f = {k: v for k, v in flat(d if isinstance(d, dict) else {}).items()}
    for k, v in f.items():
        n = norm(k)
        if v in (None, "", 0) or isinstance(v, (list, dict)):
            continue
        if "barrierPct" not in c and re.search(r"barrier.*(pct|perc|level)$|^barrier$", n) and num(v) and num(v) <= 100:
            c["barrierPct"] = num(v)
        elif "distBarrier" not in c and re.search(r"dist.*barr", n):
            c["distBarrier"] = num(v)
        elif "couponPa" not in c and re.search(r"(coupon|premi).*(p ?a|annu|yearly)", n):
            c["couponPa"] = num(v)
        elif "triggerPct" not in c and re.search(r"(coupon|premi).*(trigger|barrier|level)", n) and num(v) and num(v) <= 100:
            c["triggerPct"] = num(v)
        elif "nominal" not in c and re.search(r"nominal|denomination", n):
            c["nominal"] = num(v)
    for l in (d.get("Underlyings") or d.get("Assets") or []) if isinstance(d, dict) else []:
        if isinstance(l, dict) and (l.get("Name") or l.get("AssetName")):
            c.setdefault("underlyings", []).append(l.get("Name") or l.get("AssetName"))
    name = (d.get("Name") if isinstance(d, dict) else None) or c.get("name") or ""
    m = re.search(r"\bsu (.+)$", name)
    if m and not c.get("underlyings"):
        c["underlyings"] = [x.strip() for x in re.split(r",\s*|\s+e\s+", m.group(1)) if x.strip()]
    if re.search(r"memory|memoria", name, re.I):
        c["memory"] = True
    if not c.get("nominal") and (c.get("ask") or c.get("bid") or 0) > 400:
        c["nominal"] = 1000
    c.pop("name", None)


async def socgen_api(DISC, src, NOW, ctx):
    """Tentativo 3: apre la ricerca filtrata per classificazione, intercetta la GET a
    ProductSearch/Search fatta dal sito e la ripete cambiando pagina."""
    from urllib.parse import urlsplit, parse_qsl, urlencode
    page = await ctx.new_page()
    seen = []
    page.on("request", lambda q: seen.append(q.url) if "ProductSearch/Search?" in q.url else None)
    log = {"classes": {}, "runs": []}
    found = {}
    try:
        await page.goto(src["url"], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await accept_cookies(page)
        for _ in range(4):  # avviso di residenza
            loc = page.get_by_role("button", name=re.compile(r"^\s*ok\s*$", re.I))
            try:
                if not await loc.count():
                    break
                await loc.first.click(timeout=3000)
            except Exception:
                break
            await page.wait_for_timeout(3000)

        url, st, txt = await sg_get(page, "ProductClassificationsWithProductsCount")
        classes = sg_classes(json.loads(txt)) if st == 200 else {}
        log["classes"] = {k: v for k, v in classes.items()}
        cand = [k for k, (n, c) in classes.items() if SG_CLASS_RX.search(n) and c != 0]
        log["candidates"] = {k: classes[k] for k in cand}

        for cid in cand[:10]:
            run = {"cid": cid, "name": classes[cid][0]}
            log["runs"].append(run)
            _, st, gtxt = await sg_get(page, "GridConfig", {"productClassificationId": cid})
            grid = json.loads(gtxt) if st == 200 else []
            run["grid"] = [(g.get("Name"), g.get("Label")) for g in grid] if isinstance(grid, list) else str(grid)[:500]
            # la pagina di ricerca filtrata: il sito fa la sua GET a Search
            seen.clear()
            await page.goto(f"{SG}/product-search?productClassificationId={cid}", wait_until="domcontentloaded", timeout=60000)
            for _ in range(20):
                await page.wait_for_timeout(1000)
                if seen:
                    break
            run["site_urls"] = seen[:5]
            base = seen[0] if seen else SG_API + "Search?" + urlencode({"ProductClassificationId": cid})
            q = dict(parse_qsl(urlsplit(base).query, keep_blank_values=True))
            run["site_params"] = q
            pkey = next((k for k in q if re.search(r"page.?(num|index)?$", k, re.I) and not re.search(r"size", k, re.I)), None)
            skey = next((k for k in q if re.search(r"page.?size|take|items", k, re.I)), None)
            if skey:
                q[skey] = "100"
            pkey = pkey or ("PageNum" if q.keys() and next(iter(q))[0].isupper() else "pageNum")
            start = int(q.get(pkey) or 1)
            run["pages"] = []
            for n in range(start, start + 200):
                q[pkey] = str(n)
                u = SG_API + "Search?" + urlencode(q)
                st, txt = await fetch(page, u, "GET", None, {"accept": "application/json"})
                if st != 200:
                    run["pages"].append({"n": n, "status": st, "err": txt[:300]})
                    break
                items, total = sg_items(txt)
                if n == start:
                    run["head"] = txt[:2000]
                    run["sample"] = items[:2]
                new = 0
                for it in items:
                    c = sg_cert_grid(it, grid if isinstance(grid, list) else [], src, NOW)
                    if c and c["isin"] not in found:
                        c["type"] = c.get("type") or classes[cid][0]
                        c["name"] = it.get("Name")
                        found[c["isin"]] = c
                        new += 1
                run["pages"].append({"n": n, "items": len(items), "new": new, "total": total})
                if not new:
                    break
        # dettaglio di ogni prodotto: barriera, cedola, sottostanti (se esposti)
        for i, c in enumerate(list(found.values())[:400]):
            try:
                st, txt = await fetch(page, SG_API.replace("ProductSearch/", "Products/") + c["isin"], "GET", None,
                                      {"accept": "application/json"})
                if st != 200:
                    continue
                d = json.loads(txt)
                if i == 0:
                    log["detail_sample"] = txt[:12000]
                sg_detail(c, d)
            except Exception as e:
                log.setdefault("detail_errors", []).append(repr(e)[:200])
        for c in found.values():
            if c.get("name"):
                sg_detail(c, {})
    except Exception as e:
        log["error"] = repr(e)[:800]
    finally:
        log["found"] = len(found)
        save(DISC, f"{src['name']}_parser.json", log)
        await page.close()
    return list(found.values())


# ---------------------------------------------------------------- Borsa Italiana per ISIN
# Per i certificati UniCredit già in archivio: denaro e lettera dalla scheda pubblica di
# Borsa Italiana (SeDeX, poi Cert-X), con ripiego su Teleborsa. 1 richiesta al secondo,
# prima le cedole mensili; se il tempo della run finisce, la run successiva riparte
# dagli ISIN non ancora visitati nel ciclo (scraper/borsa_state.json).

BI = "https://www.borsaitaliana.it/borsa/cw-e-certificates/scheda/{isin}-{mkt}.html?lang=it"
BI_MARKETS = (("SEDX", "SeDeX"), ("ETLX", "Cert-X"))
TELEBORSA = "https://www.teleborsa.it/Ricerca?q={isin}"
BORSA_STATE = Path(__file__).resolve().parent / "borsa_state.json"
BORSA_BUDGET_S = int(os.environ.get("BORSA_BUDGET_MIN", "35")) * 60
BID_RX = re.compile(r"^(prezzo )?(denaro|bid)( \(?eur\)?)?$")
ASK_RX = re.compile(r"^(prezzo )?(lettera|ask|offer)( \(?eur\)?)?$")

LABEL_PAIRS_JS = """() => {
  const out = [];
  for (const tr of document.querySelectorAll('tr')) {
    const cells = [...tr.children].map(td => td.innerText.trim()).filter(Boolean);
    for (let i = 0; i + 1 < cells.length; i += 2) out.push([cells[i], cells[i + 1]]);
  }
  for (const dt of document.querySelectorAll('dt')) {
    const dd = dt.nextElementSibling; if (dd) out.push([dt.innerText.trim(), dd.innerText.trim()]);
  }
  // etichetta e valore in elementi fratelli (layout a griglia)
  for (const el of document.querySelectorAll('span,div,strong,label,th')) {
    if (el.children.length) continue;
    const t = el.innerText.trim();
    if (/^(prezzo )?(denaro|lettera|bid|ask)$/i.test(t)) {
      const sib = el.nextElementSibling || el.parentElement?.nextElementSibling;
      if (sib) out.push([t, sib.innerText.trim()]);
    }
  }
  return out.slice(0, 400);
}"""


def borsa_prices(pairs):
    bid = ask = None
    for k, v in pairs:
        n = norm(k)
        val = num(v.split("\n")[0]) if v else None
        if bid is None and BID_RX.search(n):
            bid = val
        elif ask is None and ASK_RX.search(n):
            ask = val
    return bid or None, ask or None


def borsa_queue(certs, state, today):
    """ISIN UniCredit non scaduti, prima le cedole mensili, esclusi quelli già fatti nel ciclo."""
    live = [c for c in certs if c.get("issuer") == "UniCredit" and (not c.get("maturity") or c["maturity"] >= today)]
    done = set(state.get("done", []))
    todo = [c for c in live if c["isin"] not in done]
    if not todo:  # ciclo completo: ne inizia uno nuovo
        state.update({"cycleStart": today, "done": []})
        todo = live
    todo.sort(key=lambda c: (c.get("freq") != "1m", c.get("freq") is None, c["isin"]))
    return todo


async def borsa_isin(DISC, src, NOW, ctx):
    from datetime import date as _date
    import time as _time
    from run import DATA
    certs = json.loads(DATA.read_text()).get("certs", []) if DATA.exists() else []
    state = json.loads(BORSA_STATE.read_text()) if BORSA_STATE.exists() else {}
    today = _date.today().isoformat()
    todo = borsa_queue(certs, state, today)
    log = {"queue": len(todo), "cycleStart": state.get("cycleStart"), "samples": [], "fails": 0}
    page = await ctx.new_page()
    await page.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "font", "media") else r.continue_())
    out, t_start, t_last = [], _time.time(), 0.0

    async def visit(url):
        nonlocal t_last
        wait = 1.0 - (_time.time() - t_last)  # al massimo 1 richiesta al secondo
        if wait > 0:
            await page.wait_for_timeout(int(wait * 1000))
        t_last = _time.time()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return resp.status if resp else 0

    try:
        for c in todo:
            if _time.time() - t_start > BORSA_BUDGET_S:
                log["stopped"] = "tempo esaurito"
                break
            isin, got = c["isin"], None
            for code, label in BI_MARKETS:
                url = BI.format(isin=isin, mkt=code)
                try:
                    st = await visit(url)
                except Exception as e:
                    st = repr(e)[:80]
                if st != 200 or isin not in page.url:
                    continue
                if not log.get("cookies"):
                    await accept_cookies(page)
                    log["cookies"] = True
                pairs = await page.evaluate(LABEL_PAIRS_JS)
                bid, ask = borsa_prices(pairs)
                if len(log["samples"]) < 3:
                    log["samples"].append({"url": url, "pairs": pairs[:80]})
                    (DISC / f"borsa_{isin}_{code}.html").write_text((await page.content())[:1_500_000])
                if bid or ask or ISIN_RE.search(await page.inner_text("body")):
                    got = {"url": url.replace("?lang=it", ""), "market": label, "bid": bid, "ask": ask}
                    break
            if got is None:  # ripiego: Teleborsa
                try:
                    st = await visit(TELEBORSA.format(isin=isin))
                    if st == 200:
                        bid, ask = borsa_prices(await page.evaluate(LABEL_PAIRS_JS))
                        if bid or ask:
                            got = {"url": page.url, "market": None, "bid": bid, "ask": ask}
                        if len(log["samples"]) < 5 and not log.get("teleborsa_sample"):
                            log["teleborsa_sample"] = {"url": page.url, "status": st}
                            (DISC / f"teleborsa_{isin}.html").write_text((await page.content())[:1_500_000])
                except Exception:
                    pass
            state.setdefault("done", []).append(isin)
            if got is None:
                log["fails"] += 1
                continue
            out.append(clean({"isin": isin, "issuer": "UniCredit", "source": "borsa_isin", "url": got["url"],
                              "market": got["market"], "bid": got["bid"], "ask": got["ask"], "updatedAt": NOW}))
    finally:
        await page.close()
        state.update({"lastRun": NOW, "lastVisited": len(out) + log["fails"],
                      "remaining": len([c for c in todo if c["isin"] not in set(state.get("done", []))])})
        BORSA_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
        log.update({k: state[k] for k in ("lastVisited", "remaining")})
        log["withPrice"] = sum(1 for c in out if c.get("bid") and c.get("ask"))
        save(DISC, f"{src['name']}_parser.json", log)
    return out
