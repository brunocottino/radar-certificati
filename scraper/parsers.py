"""Parser specifici per le API interne degli emittenti.

Ogni parser riceve (DISC, src, NOW, ctx): la cartella discovery/, la sorgente di
sources.py, il timestamp della run e il contesto Playwright già "scaldato" dalla
visita alla pagina della sorgente (cookie, consenso). Le chiamate alle API partono
da dentro una pagina del sito (fetch same-origin), così hanno gli stessi header
e cookie del browser. Restituisce una lista di certificati nello schema di
docs/data/certs.json.
"""
import asyncio
import json
import os
import random
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
    # tutto il gruppo 6 (investimento): cash collect, phoenix, express, bonus cap, protetti, fixed cash collect
    return list(out.values())


# ---------------------------------------------------------------- BNP Paribas: dettaglio per ISIN
# L'elenco productlist non restituisce tutti i certificati BNP quotati (molti arrivano solo da Euronext,
# senza cedola né barriera). La pagina prodotto usa due GET pubbliche per ISIN: keyvaluerow (cedola p.a.,
# barriera, trigger, memoria, frequenza, scadenza) e underlyingbasket (sottostanti con strike e distanze).
# A rotazione: 4 richieste in parallelo, al massimo BNP_DETAIL_BUDGET_MIN minuti per run, prima i certificati
# senza cedola (cash collect/phoenix, poi express, poi il resto); ogni ISIN si rilegge dopo 7 giorni.

BNP_DETAIL_STATE = Path(__file__).resolve().parent / "bnp_detail_state.json"
BNP_DETAIL_BUDGET_S = int(os.environ.get("BNP_DETAIL_BUDGET_MIN", "8")) * 60
BNP_V1 = "https://investimenti.bnpparibas.it/apiv2/api/v1/product/"
BNP_HDR = {"accept": "application/json", "content-type": "application/json", "clientid": "1", "languageid": "it", "countryid": ""}


def detail_queue(certs, issuer, state, days=7, need=None):
    """ISIN dell'emittente da (ri)leggere: prima quelli senza cedola, per tipo; poi i più vecchi."""
    from datetime import date as _date, timedelta
    today = _date.today()
    lev = re.compile(r"turbo|mini ?future|leva|leverage|warrant|tracker", re.I)
    old = (today - timedelta(days=days)).isoformat()
    iss = set(issuer) if isinstance(issuer, (tuple, list, set)) else {issuer}
    q = [c for c in certs if c.get("issuer") in iss and not lev.search(c.get("typeMarket") or c.get("type") or "")
         and (not c.get("maturity") or c["maturity"] >= today.isoformat()) and state.get(c["isin"], "") < old]
    kind = lambda c: (0 if re.search(r"cash collect|phoenix|coupon|cedol", c.get("typeMarket") or c.get("type") or "", re.I)
                      else 1 if re.search(r"express|autocall", c.get("typeMarket") or c.get("type") or "", re.I) else 2)
    if need:  # prima chi ha bisogno della scheda (es. cedola e prezzo ma senza strike dei sottostanti)
        q.sort(key=lambda c: (not need(c), not c.get("ask"), state.get(c["isin"], ""), c["isin"]))
    else:
        q.sort(key=lambda c: (c.get("couponPa") is not None, kind(c), state.get(c["isin"], ""), c["isin"]))
    return q


def needs_strikes(c):
    """Certificato interessante (cedola nota) a cui mancano gli strike dei sottostanti."""
    det = c.get("underlyingsDetail") or []
    return c.get("couponPa") is not None and not (det and all(u.get("strike") for u in det))


async def rotate(DISC, src, issuer, state_path, budget_s, one, log, days=7, par=4, pause=0.3, need=None):
    """Rotazione delle schede per ISIN di un emittente: 4 richieste in parallelo entro il budget di tempo.
    one(c) restituisce il certificato arricchito, None se la scheda non c'è, o solleva un'eccezione."""
    import time as _time
    from datetime import date as _date
    from run import DATA
    certs = json.loads(DATA.read_text()).get("certs", []) if DATA.exists() else []
    st = json.loads(state_path.read_text()) if state_path.exists() else {}
    todo = detail_queue(certs, issuer, st, days, need)
    log.update({"queue": len(todo), "read": 0, "withCoupon": 0, "missing": 0, "errors": 0, "samples": []})
    out, t0 = [], _time.time()

    async def wrap(c):
        try:
            cert = await one(c)
            st[c["isin"]] = _date.today().isoformat()
            if not cert:
                log["missing"] += 1
                return
            cert.pop("bid", None)
            cert.pop("ask", None)  # i prezzi restano quelli di Euronext
            cert.update(isin=c["isin"], issuer=c.get("issuer") or issuer, source=src["name"], updatedAt=NOW_OF(src))
            out.append(clean(cert))
            log["read"] += 1
            log["withCoupon"] += cert.get("couponPa") is not None
            if len(log["samples"]) < 3:
                log["samples"].append(cert)
        except Exception as e:
            log["errors"] += 1
            if len(log["samples"]) < 6:
                log["samples"].append({"isin": c["isin"], "err": repr(e)[:300]})

    try:
        for k in range(0, len(todo), par):
            if _time.time() - t0 > budget_s:
                log["stopped"] = "tempo esaurito"
                break
            await asyncio.gather(*(wrap(c) for c in todo[k:k + par]))
            await asyncio.sleep(pause)
            if log["errors"] > 40 and log["read"] < 5:
                log["stopped"] = "troppi errori"
                break
    finally:
        state_path.write_text(json.dumps(st, separators=(",", ":"), sort_keys=True))
        save(DISC, f"{src['name']}_parser.json", log)
    LAST_STATUS[src["name"]] = f"ok: {log['read']} schede lette ({log['withCoupon']} con cedola), {max(len(todo) - log['read'] - log['missing'] - log['errors'], 0)} in coda"
    return out


def NOW_OF(src):
    return src.get("_now")


async def bnp_details(DISC, src, NOW, ctx):
    src = {**src, "_now": NOW}
    page = await ctx.new_page()
    log = {}
    try:
        await page.goto(src["url"], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        await accept_cookies(page)

        async def one(c):
            isin = c["isin"]
            s1, t1 = await fetch(page, BNP_V1 + "keyvaluerow/" + isin, "GET", None, BNP_HDR)
            if s1 == 404:
                return None
            if s1 != 200:
                raise RuntimeError(f"keyvaluerow HTTP {s1}: {t1[:150]}")
            r = json.loads(t1).get("result") or {}
            if not r:
                return None
            s2, t2 = await fetch(page, BNP_V1 + "underlyingbasket/" + isin, "GET", None, BNP_HDR)
            items = (json.loads(t2).get("result") or {}).get("underlyingItems") if s2 == 200 else None
            f = r.get("first") or {}
            if items:
                r["underlyingItems"] = items
            elif f.get("underlyingName") and "," in f["underlyingName"]:  # paniere senza dettaglio: solo i nomi
                r["underlyingItems"] = [{"underlyingName": n.strip()} for n in f["underlyingName"].split(",") if n.strip()]
            r["isin"] = isin
            cert = bnp_cert(r, src, NOW)
            cert["market"] = c.get("market") or cert.get("market")
            if r.get("derivativeTypeName"):
                cert["type"] = r["derivativeTypeName"]
            return cert

        return await rotate(DISC, src, "BNP Paribas", BNP_DETAIL_STATE, BNP_DETAIL_BUDGET_S, one, log)
    finally:
        await page.close()


# ---------------------------------------------------------------- Vontobel: dettaglio per ISIN
# Le liste e il CSV di Vontobel coprono solo i prodotti "in vetrina" (~590): centinaia di certificati Vontobel
# quotati arrivano solo da Euronext, senza cedola. La pagina prodotto risponde per qualsiasi ISIN (la categoria
# nell'indirizzo non conta) e contiene in __NEXT_DATA__ tutti i dati: cedola p.a., per sottostante strike (8),
# barriera con % (58), trigger cedola con data (36), livello autocall con data (35), prezzo; tipo di barriera.

VONTOBEL_DETAIL_STATE = Path(__file__).resolve().parent / "vontobel_detail_state.json"
VONTOBEL_PAGE = "https://markets.vontobel.com/it-it/prodotti/investment/cash-collect-certificate/{}"


def vt_kf(kfs, name):
    """Valore (prezzo, %, data) di una key figure Vontobel per numero di nome."""
    for k in kfs or []:
        if k.get("name") != name:
            continue
        v = k.get("value") or {}
        if "keyFigure" in v:
            v = (v["keyFigure"] or {}).get("value") or {}
        if "first" in v:
            f, s = (v.get("first") or {}).get("value") or {}, (v.get("second") or {}).get("value") or {}
            return {"price": f.get("price"), "pct": s.get("percentage"), "date": (s.get("value") or "")[:10] or None}
        return {"price": v.get("price"), "pct": v.get("percentage"), "date": None}
    return {}


def vontobel_cert(html, c):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    ad = (json.loads(m.group(1)).get("props") or {}).get("pageProps", {}).get("additionalData") or {}
    d = ad.get("data") or {}
    if not d.get("isin"):
        return None
    ukf = {u.get("ulinsId"): u.get("keyFigures") for u in ad.get("underlyingKeyFigures") or []}
    unds, bars, trigs = [], [], []
    next_cpn = next_call = None
    for u in ad.get("underlyings") or []:
        k = ukf.get(u.get("ulinsId")) or []
        strike = vt_kf(k, 8).get("price")
        bar = vt_kf(k, 58)
        trg = vt_kf(k, 36)
        call = vt_kf(k, 35)
        last = (u.get("price") or {}).get("latest") or (u.get("price") or {}).get("previousClose")
        b = bar.get("price") or u.get("barrier")
        if bar.get("pct"):
            bars.append(bar["pct"] * 100)
        if strike and trg.get("price"):
            trigs.append(trg["price"] / strike * 100)
        next_cpn = next_cpn or trg.get("date")
        next_call = next_call or call.get("date")
        unds.append(clean({"name": u.get("name"), "strike": strike,
                           "dist": round((last - b) / last * 100, 4) if last and b else None,
                           "isin": u.get("isin") if ISIN_RE.fullmatch(u.get("isin") or "") else None}))
    dists = [u for u in unds if u.get("dist") is not None]
    worst = min(dists, key=lambda u: u["dist"]) if dists else None
    feats = {f.get("$type"): f for f in ad.get("primaryFeatures") or []}
    mat = (feats.get("ProductFeatureFinalFixingDto") or {}).get("date")
    mem = (feats.get("ProductFeatureCouponMemoryTypeDto") or {}).get("couponMemoryType")
    call = (feats.get("ProductFeatureCallabilityDto") or {}).get("callability")
    text = re.sub(r"<[^>]+>", " ", html[:400000])
    fm = re.search(r"Frequenza cedolare \(in mesi\)\D{0,80}?(\d+)", text)
    cpa = d.get("couponPerAnnum")
    return {
        "type": d.get("associationName"),
        "underlyings": [u["name"] for u in unds] or None,
        "underlyingsDetail": unds or None,
        "worstName": worst["name"] if worst else None,
        # barrierDistance di Vontobel è senza segno: prima la distanza calcolata dai prezzi (negativa sotto barriera)
        "distBarrier": worst["dist"] if worst else (round(d["barrierDistance"] * 100, 4) if d.get("barrierDistance") is not None else None),
        "barrierPct": round(min(bars), 2) if bars else (round(d["barrier"] / d["strikePrice"] * 100, 2) if d.get("barrier") and d.get("strikePrice") else None),
        "triggerPct": round(min(trigs), 2) if trigs else None,
        "barrierType": "scadenza" if d.get("barrierObservation") == 11 else ("continua" if d.get("barrierObservation") else None),
        "couponPa": round(cpa * 100, 4) if cpa else None,
        "freq": months_to_freq(fm.group(1)) if fm else None,
        "nominal": d.get("denomination") or d.get("issuePrice"),
        "maturity": (mat or "")[:10] or None,
        "memory": True if mem == 0 else None,
        "callable": "Autocall" if call == 2 else None,
        "nextCouponDate": next_cpn, "nextCallDate": next_call,
        "currency": d.get("currency"),
        "url": f"https://markets.vontobel.com/it-it/prodotti/investment/cash-collect-certificate/{c['isin']}",
    }


async def vontobel_details(DISC, src, NOW, ctx):
    src = {**src, "_now": NOW}

    async def one(c):
        r = await ctx.request.get(VONTOBEL_PAGE.format(c["isin"]), timeout=30000)
        if r.status == 404:
            return None
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return vontobel_cert(await r.text(), c)

    return await rotate(DISC, src, "Vontobel", VONTOBEL_DETAIL_STATE, int(os.environ.get("VONTOBEL_DETAIL_BUDGET_MIN", "6")) * 60, one, {})


# ---------------------------------------------------------------- Marex: term sheet per ISIN
# Marex non pubblica dati di prodotto, solo documenti: fp.marex.com/api/<ISIN> elenca i file e il term sheet
# (TS-<ISIN>-...PDF) ha sempre la stessa impaginazione: nominale, tabella sottostanti (strike e livello barriera
# con la % nell'intestazione), tabella cedole (barriera cedola, tasso per periodo, date), tabella autocall.
# Testo estratto con pdftotext -layout (poppler-utils). Distanze: le ricalcola risk.py da strike e chiusure.

MAREX_DETAIL_STATE = Path(__file__).resolve().parent / "marex_detail_state.json"
MAREX = "https://fp.marex.com"
MONTHS_EN = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                             "august", "september", "october", "november", "december"])}


def en_date(s):
    m = re.match(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", s.strip())
    if not m or m.group(2).lower() not in MONTHS_EN:
        return None
    return f"{m.group(3)}-{MONTHS_EN[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


def marex_ts(text, title=""):
    """Dati dal testo (pdftotext -layout) di un term sheet Marex."""
    from datetime import date as _date
    lines, prev = [], None
    for l in text.splitlines():  # il PDF ha il testo sovrapposto due volte: righe consecutive identiche
        if l.strip() and l != prev:
            lines.append(l)
        prev = l
    t = "\n".join(lines)
    out = {}
    m = re.search(r"Nominal Amount\s+([A-Z]{3})\s+([\d,.]+)", t)
    if m:
        out["nominal"] = float(m.group(2).replace(",", ""))
        out["currency"] = m.group(1)
    m = re.search(r"Final Fixing Date\s+(\d{1,2} [A-Za-z]+ \d{4})", t)
    out["maturity"] = en_date(m.group(1)) if m else None
    out["barrierType"] = "scadenza" if re.search(r"European observation", t) else ("continua" if re.search(r"American observation|continuous", t, re.I) else None)
    # tabella sottostanti: colonne dalla riga d'intestazione
    unds = []
    hi = next((i for i, l in enumerate(lines) if re.search(r"\bUnderlying\b", l) and "Related" in l), None)
    if hi is not None:
        h = lines[hi]
        c0, c1 = h.index("Underlying"), h.index("Related")
        pcts = []
        for l in lines[hi + 1:hi + 3]:
            pcts += re.findall(r"\(([\d.]+)%\)\*", l)
        # 3 colonne: iniziale (100%), strike (100%), barriera (x%); 2 colonne: iniziale (100%) e strike basso (x%)
        # che fa da barriera. In entrambi i casi la barriera è l'ultima % dell'intestazione, se sotto 100.
        bar = float(pcts[-1]) if len(pcts) >= 2 and float(pcts[-1]) < 100 else None
        cur = None
        for l in lines[hi + 1:hi + 60]:
            # fine tabella: la nota "* as determined…" o un titolo di sezione (solo maiuscole, es. GENERAL INFORMATION);
            # non "NV" o "SA" che sono il seguito del nome di un sottostante
            if l.lstrip().startswith("*") or (cur and re.fullmatch(r"[A-Z][A-Z &]{5,}", l.strip().lstrip("\x0c"))):
                break
            mi = re.match(r"\s*(\d+)\s", l)
            if mi and len(l) > c1 and re.search(r"[A-Z]{3} [\d,.]+", l):
                vals = re.findall(r"\b[A-Z]{3} ([\d,.]+)", l)
                cur = {"name": re.sub(r"^\s*\d+\s+", "", l[:c1]).strip(), "tk": (re.search(r"([A-Z0-9./]+ [A-Z]{2})(?: Equity| Index)?", l[c1:]) or [None, None])[1],
                       "strike": float(vals[0].replace(",", "")) if vals else None}  # livello iniziale = 100%
                unds.append(cur)
            elif re.search(r"BISHOPSGATE|Marex Financial|hello@marexfp", l):
                continue  # piè di pagina in mezzo alla tabella
            elif cur and len(l) > c0 and l[:c0].strip() == "":
                frag = l[max(c0 - 2, 0):c1].strip()
                if frag and not re.search(r"Exchange|Equity|Index", frag):
                    cur["name"] = (cur["name"] + " " + frag).strip()
        if bar:
            out["barrierPct"] = bar
    if unds:
        out["underlyings"] = [u["name"] for u in unds]
        out["underlyingsDetail"] = [clean({"name": u["name"], "strike": u["strike"]}) for u in unds]
    # cedole: n, barriera cedola %, tasso %, data determinazione, data pagamento
    ci, ei = t.find("Coupon Payment"), t.find("EARLY REDEMPTION")
    csec = t[ci:ei if ei > ci else len(t)] if ci >= 0 else ""
    rows = re.findall(r"^\s+\d+\s+([\d.]+)%\s+([\d.]+)%\s+(\d{1,2} [A-Za-z]+ \d{4})\s+\d{1,2} [A-Za-z]+ \d{4}\s*$", csec, re.M)
    today = _date.today().isoformat()
    if rows:
        ds = [en_date(r[2]) for r in rows]
        if len(ds) >= 2 and ds[0] and ds[-1]:
            months = max(1, round((_date.fromisoformat(ds[-1]) - _date.fromisoformat(ds[0])).days / 30.44 / (len(ds) - 1)))
        else:
            months = 12
        rates = [float(r[1]) for r in rows]
        out["couponPa"] = round(sorted(rates)[len(rates) // 2] * 12 / months, 4)
        out["freq"] = months_to_freq(months)
        out["triggerPct"] = float(rows[-1][0])
        out["nextCouponDate"] = next((d for d in ds if d and d >= today), None)
        out["memory"] = True if re.search(r"memory", title + " " + t[:3000], re.I) else None
    # autocall: N, livello %, importo %, data osservazione, data rimborso
    ac = re.findall(r"^\s+\d+\s+([\d.]+)%\s+([\d.]+)%\s+(\d{1,2} [A-Za-z]+ \d{4})\s+\d{1,2} [A-Za-z]+ \d{4}\s*$",
                    t[t.find("EARLY REDEMPTION"):] if "EARLY REDEMPTION" in t else "", re.M)
    if ac:
        out["callable"] = "Autocall"
        out["nextCallDate"] = next((en_date(r[2]) for r in ac if (en_date(r[2]) or "") >= today), None)
        if "couponPa" not in out:  # express: premio crescente nell'importo di rimborso anticipato
            amts = [float(r[1]) for r in ac]
            ds = [en_date(r[2]) for r in ac]
            if len(amts) >= 2 and amts[-1] > amts[0] and ds[0] and ds[-1]:
                yrs = (_date.fromisoformat(ds[-1]) - _date.fromisoformat(ds[0])).days / 365.25
                if yrs > 0:
                    out["couponPa"] = round((amts[-1] - amts[0]) / yrs, 4)
                    out["couponNote"] = "premio express annualizzato (pagato solo al richiamo)"
    return {k: v for k, v in out.items() if v not in (None, "", [])}


async def marex_details(DISC, src, NOW, ctx):
    import subprocess
    import tempfile
    src = {**src, "_now": NOW}

    async def one(c):
        r = await ctx.request.get(f"{MAREX}/api/{c['isin']}", timeout=30000)
        if r.status == 404:
            return None
        if r.status != 200:
            raise RuntimeError(f"api HTTP {r.status}")
        d = json.loads(await r.text())
        docs = [x for x in d.get("documents") or [] if re.match(r"TS-", x.get("fileName") or "")]
        if not docs:
            return None
        doc = max(docs, key=lambda x: x.get("id") or 0)  # l'ultima versione del term sheet
        from urllib.parse import quote
        pr = await ctx.request.get(f"{MAREX}/file/{c['isin']}/{doc['id']}/{quote(doc['fileName'])}", timeout=60000)
        body = await pr.body()
        if pr.status != 200 or body[:4] != b"%PDF":
            raise RuntimeError(f"pdf HTTP {pr.status}")
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(body)
            f.flush()
            text = await asyncio.to_thread(lambda: subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True,
                                                                    text=True, timeout=60).stdout)
        out = marex_ts(text, d.get("title") or "")
        if not out:
            return None
        out["type"] = re.sub(r"^\d+m\s+", "", (d.get("title") or "").split(" on ")[0]) or None
        out["url"] = f"{MAREX}/it/"
        return out

    return await rotate(DISC, src, "Marex", MAREX_DETAIL_STATE, int(os.environ.get("MAREX_DETAIL_BUDGET_MIN", "6")) * 60, one, {},
                        days=30)


# ---------------------------------------------------------------- Intesa Sanpaolo: dettaglio per ISIN
# Il sito prodottiequotazioni usa una GET pubblica per ISIN (rest/public/title/dossierbystock): premio
# condizionato per periodo e frequenza (-> cedola p.a. sul prezzo di emissione), barriera %, sottostanti con
# strike e distanza dalla barriera, autocall, scadenza. Stessa rotazione di BNP (scraper/intesa_detail_state.json).

INTESA_DETAIL_STATE = Path(__file__).resolve().parent / "intesa_detail_state.json"
INTESA_API = "https://prodottiequotazioni.intesasanpaolo.com/rest/public/title/dossierbystock?isin={}&language=it"
INTESA_SITE = "https://www.intesasanpaolo.prodottiequotazioni.com"
PER_YEAR = {"MENSILE": ("1m", 12), "BIMESTRALE": ("2m", 6), "TRIMESTRALE": ("3m", 4), "QUADRIMESTRALE": ("4m", 3),
            "SEMESTRALE": ("6m", 2), "ANNUALE": ("12m", 1)}


def intesa_cert(d, c):
    from datetime import datetime, timezone
    ci = (d.get("content") or {}).get("commonInfo") or {}
    if not ci:
        return None
    ug = ci.get("underlyingGroup") or {}
    unds = [u for u in ug.get("underlying") or [] if u.get("name")]
    dists = [u for u in unds if u.get("distanceToBarrierPct") is not None]
    worst = min(dists, key=lambda u: u["distanceToBarrierPct"]) if dists else None
    prem = num(re.sub(r"[^\d,.\-]", "", ci.get("conditionalPremium") or ci.get("fixedPremiumS") or "") or None)
    fr = PER_YEAR.get((ci.get("premiumFrequency") or "").upper().strip())
    issue = num(ci.get("issuePrice"))
    cpa = round(prem * fr[1] / issue * 100, 4) if prem and fr and issue else None
    ep = lambda v: datetime.fromtimestamp(v, timezone.utc).date().isoformat() if isinstance(v, (int, float)) and v > 0 else None
    name = ci.get("name") or ""
    return {
        "type": ci.get("typeProduct") or ci.get("certificateType"),
        "underlyings": [u["name"] for u in unds] or None,
        "underlyingsDetail": [clean({"name": u["name"], "strike": u.get("strike") or u.get("initialReferenceValue"),
                                     "dist": u.get("distanceToBarrierPct"),
                                     "isin": u.get("isin") if ISIN_RE.fullmatch(u.get("isin") or "") else None}) for u in unds] or None,
        "worstName": worst["name"] if worst else None,
        "distBarrier": worst["distanceToBarrierPct"] if worst else None,
        "barrierPct": num(ci.get("barrier")),
        "couponPa": cpa,
        "freq": fr[0] if fr else None,
        "nominal": issue,
        "maturity": ep(ci.get("maturity")),
        "memory": True if re.search(r"memory|memoria", name, re.I) else None,
        "callable": "Autocall" if ci.get("autocallable") else None,
        "currency": ci.get("curSymbol"),
        "url": f"{INTESA_SITE}/detail/{c['isin']}",
    }


async def intesa_details(DISC, src, NOW, ctx):
    src = {**src, "_now": NOW}
    hdr = {"accept": "application/json", "origin": INTESA_SITE, "referer": INTESA_SITE + "/"}

    async def one(c):
        r = await ctx.request.get(INTESA_API.format(c["isin"]), headers=hdr, timeout=30000)
        if r.status == 404:
            return None
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:150]}")
        return intesa_cert(json.loads(await r.text()), c)

    return await rotate(DISC, src, "Intesa Sanpaolo", INTESA_DETAIL_STATE, int(os.environ.get("INTESA_DETAIL_BUDGET_MIN", "5")) * 60, one, {})


# ---------------------------------------------------------------- UniCredit (onemarkets)
# L'elenco prodotti è un frammento HTML (/it.omr-search.html) paginato via JS:
# lo sfogliamo cliccando "Pagina successiva" e leggendo la tabella a ogni pagina.

UC_COLS = [
    ("isin", r"^isin"), ("type", r"tipo di prodotto"), ("underlyings", r"^sottostante"),
    ("distBarrier", r"distanza dalla barriera"), ("maturity", r"^scadenza"),
    ("matPay", r"data di pagamento finale"), ("bid", r"^denaro"), ("ask", r"^lettera"),
    ("freq", r"frequenza"), ("autocall", r"autocall"), ("coupon", r"coupon condizionato"),
    ("yieldPa", r"rendimento potenziale annuo"), ("barrierPct", r"^barriera"), ("triggerPct", r"trigger"),
]
UC_PER_YEAR = {"1m": 12, "3m": 4, "6m": 2, "12m": 1}


def uc_rows(heads, rows, src, NOW, base):
    col = {}
    for i, h in enumerate(heads):
        n = norm(h)
        for k, rx in UC_COLS:
            if k not in col and re.search(rx, n):
                col[k] = i
                break
    if "isin" not in col:
        return []
    out = []
    for r in rows:
        g = lambda k: r[col[k]].strip() if k in col and col[k] < len(r) else None
        m = ISIN_RE.search(g("isin") or "")
        if not m:
            continue
        isin = m.group(1)
        freq = freq_of(g("freq")) if g("freq") not in (None, "-") else None
        bid, ask = num(g("bid")) or None, num(g("ask")) or None
        # "Coupon Condizionato" è un importo per certificato: va riportato in % del nominale
        coupon = num(g("coupon"))
        nominal = 1000 if (ask or bid or 0) > 400 else 100 if (ask or bid) else None
        if coupon is not None and nominal is None:
            nominal = 1000 if coupon > 5 else 100
        cpa = num(g("yieldPa"))
        if cpa is not None and not 0 < cpa < 40:
            cpa = None
        if coupon is not None and freq in UC_PER_YEAR:
            cpa = round(coupon / nominal * 100 * UC_PER_YEAR[freq], 4)
            if cpa > 40 and nominal == 100:  # importo su nominale 1000 con prezzo quotato in %
                nominal, cpa = 1000, round(cpa / 10, 4)
            if cpa > 40:
                cpa = None
        und = g("underlyings")
        out.append(clean({
            "isin": isin, "issuer": src["issuer"], "source": src["name"], "type": g("type"),
            "underlyings": [p.strip() for p in re.split(r"\s+/\s+|\s*;\s*", und) if p.strip()] if und and und != "-" else None,
            "distBarrier": num(g("distBarrier")), "barrierPct": num(g("barrierPct")), "triggerPct": num(g("triggerPct")),
            "maturity": pdate(g("maturity")) or pdate(g("matPay")),
            "bid": bid, "ask": ask, "nominal": nominal,
            "freq": freq, "couponPa": cpa,
            "callable": "Autocall" if norm(g("autocall")) in ("si", "yes") else None,
            "url": f"https://www.onemarkets.it/it.omr-redirect.html/{isin}",
            "updatedAt": NOW,
        }))
    return out


UNICREDIT_DETAIL_STATE = Path(__file__).resolve().parent / "unicredit_detail_state.json"
UC_PAGE = "https://www.onemarkets.it/it/productpage.html/{}"


def unicredit_detail_cert(html, c):
    """Pagina prodotto onemarkets: "Valore Iniziale (Strike)" e "Barriera" elencano i livelli di ogni sottostante
    separati da " / ", nell'ordine dei sottostanti. Le distanze le calcola risk.py ogni giorno dalle chiusure."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", t)).replace("&nbsp;", " ")
    t = re.sub(r"(\| ?)+", "|", t)
    ms = re.search(r"\|Valore Iniziale \(Strike\)\|([^|]+)\|", t, re.I)
    mb = re.search(r"\|Barriera\|([^|]+)\|", t)
    if not ms:
        raise RuntimeError("pagina senza 'Valore Iniziale (Strike)'")
    strikes = [num(re.sub(r"[^\d,.]", "", x)) for x in ms.group(1).split(" / ")]
    bars = [num(re.sub(r"[^\d,.]", "", x)) for x in mb.group(1).split(" / ")] if mb else []
    names = c.get("underlyings") or []
    if len(strikes) != len(names) or not all(strikes):
        return {}  # ordine/numero non verificabile: meglio nessun dato che strike attribuiti al sottostante sbagliato
    if len(bars) != len(strikes):
        bars = [None] * len(strikes)
    pcts = {round(b / s * 100, 2) for s, b in zip(strikes, bars) if s and b}
    return {
        "underlyingsDetail": [clean({"name": n, "strike": s, "barrierLevel": b}) for n, s, b in zip(names, strikes, bars)],
        "barrierPct": c.get("barrierPct") or (pcts.pop() if len(pcts) == 1 else None),
    }


async def unicredit_details(DISC, src, NOW, ctx):
    """Strike e barriere per sottostante dalle pagine prodotto UniCredit (non cambiano: rilettura ogni 30 giorni)."""
    src = {**src, "_now": NOW}

    async def one(c):
        r = await ctx.request.get(UC_PAGE.format(c["isin"]), timeout=45000, headers={"accept-language": "it-IT,it;q=0.9"})
        if r.status == 404:
            return None
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return unicredit_detail_cert(await r.text(), c) or None

    return await rotate(DISC, src, "UniCredit", UNICREDIT_DETAIL_STATE,
                        int(os.environ.get("UNICREDIT_DETAIL_BUDGET_MIN", "4")) * 60, one, {}, days=30, par=3, pause=0.5, need=needs_strikes)


async def unicredit_pages(DISC, src, NOW, ctx):
    from run import extract_tables
    out, log, reqs = {}, [], []
    base = "https://www.onemarkets.it/it/search-page.investment.html?productCategory={0}&productgroupList={0}"
    for cat in src.get("categories", [129830054, 1050]):
        page = await ctx.new_page()
        page.on("request", lambda q: reqs.append({"url": q.url, "post": q.post_data}) if "omr-search" in q.url and len(reqs) < 5 else None)
        try:
            await page.goto(base.format(cat), wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2500)
            await accept_cookies(page)
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            total = None
            try:
                total = await page.locator(".headline-total").first.inner_text(timeout=5000)
            except Exception:
                pass
            prev_first = None
            for pno in range(1, src.get("max_pages", 80) + 1):
                tables = await extract_tables(page)
                got = []
                for t in tables:
                    heads = t["heads"]
                    rows = t["rows"]
                    if rows and len(heads) <= 1 and rows[0] and norm(rows[0][0]) == "isin":
                        heads, rows = rows[0], rows[1:]
                    got += uc_rows(heads, rows, src, NOW, base)
                first = got[0]["isin"] if got else None
                log.append({"cat": cat, "page": pno, "rows": len(got), "total": total})
                if not got or first == prev_first:
                    break
                prev_first = first
                for c in got:
                    out[c["isin"]] = {**out.get(c["isin"], {}), **c}
                nxt = page.locator('a[title="Pagina successiva"]').first
                if not await nxt.count():
                    break
                if "disabled" in (await nxt.evaluate("a => a.parentElement.className") or ""):
                    break
                await nxt.click(timeout=8000)
                # attende che la tabella cambi
                for _ in range(30):
                    await page.wait_for_timeout(500)
                    t2 = await extract_tables(page)
                    txt = json.dumps(t2)[:20000]
                    if first not in txt:
                        break
        except Exception as e:
            log.append({"cat": cat, "error": repr(e)[:500]})
        finally:
            await page.close()
    save(DISC, f"{src['name']}_parser.json", {"log": log, "omr_search_requests": reqs})
    return list(out.values())


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


LAST_STATUS = {}  # esito non numerico per sorgente (es. "saltata: già fatta oggi"), letto da run.py
LEONTEQ_STATE = Path(__file__).resolve().parent / "leonteq_state.json"
LEONTEQ_DETAIL_STATE = Path(__file__).resolve().parent / "leonteq_detail_state.json"


def leonteq_detail_cert(d):
    """Scheda per ISIN (api/product-model/details): per ogni sottostante fixing iniziale (strike), livello e
    distanza dalla barriera con il prezzo del momento; barriera % anche per i Multi Express che la ricerca non dà."""
    p = (d or {}).get("product") or {}
    ul = [u for u in (p.get("underlyingList") or {}).get("values") or [] if u.get("shortName")]
    if not p or not ul:
        return None
    det = []
    for u in ul:
        dist = num((u.get("distanceToBarrier") or {}).get("raw"))
        det.append(clean({"name": u["shortName"], "isin": u.get("isin") if ISIN_RE.fullmatch(u.get("isin") or "") else None,
                          "strike": num(u.get("rawInitialFixingLevel")), "barrierLevel": num(u.get("rawBarrierLevel")),
                          "dist": round(dist * 100, 4) if dist is not None else None}))
    dists = [u for u in det if u.get("dist") is not None]
    worst = min(dists, key=lambda u: u["dist"]) if dists else None
    return {
        "underlyings": [u["name"] for u in det],
        "underlyingsDetail": det,
        "worstName": worst["name"] if worst else None,
        "distBarrier": worst["dist"] if worst else None,
        "barrierPct": pct(lv(p, "barrier")),
        "triggerPct": pct(lv(p, "conditionalCouponTriggerLevel")),
        "detailAt": NOW_OF_DETAIL[0],
    }


NOW_OF_DETAIL = [None]


async def leonteq_details(DISC, src, NOW, ctx):
    """Schede Leonteq a rotazione: 2 alla volta con pause (sito protetto da Incapsula), rilettura ogni 3 giorni;
    fra una lettura e l'altra le distanze le aggiorna risk.py dagli strike e dalle chiusure."""
    src = {**src, "_now": NOW}
    NOW_OF_DETAIL[0] = NOW
    base = "https://certificati.leonteq.com"
    page = await ctx.new_page()
    await page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(6000)

    async def one(c):
        await asyncio.sleep(random.uniform(0.4, 1.2))
        st, txt = await fetch(page, f"{base}/api/product-model/details/isin/{c['isin']}?language_id=5", "GET", None,
                              {"accept": "application/json"})
        if st == 404:
            return None
        if st != 200:
            raise RuntimeError(f"HTTP {st}: {txt[:150]}")
        return leonteq_detail_cert(json.loads(txt))

    try:
        return await rotate(DISC, src, ("Leonteq Securities", "BIL"), LEONTEQ_DETAIL_STATE,
                            int(os.environ.get("LEONTEQ_DETAIL_BUDGET_MIN", "5")) * 60, one, {}, days=3, par=2, pause=1.0, need=needs_strikes)
    finally:
        await page.close()


async def leonteq_api(DISC, src, NOW, ctx):
    """Leonteq è protetta da Incapsula: al massimo una ricerca completa al giorno, con pause tra le pagine."""
    from datetime import date as _date
    st = json.loads(LEONTEQ_STATE.read_text()) if LEONTEQ_STATE.exists() else {}
    today = _date.today().isoformat()
    if st.get("lastSuccess", "")[:10] == today and not os.environ.get("LEONTEQ_FORCE"):
        LAST_STATUS[src["name"]] = "saltata: ricerca completa già fatta oggi"
        return []
    out = await _leonteq_search(DISC, src, NOW, ctx)
    st["lastAttempt"] = NOW
    if out:
        st["lastSuccess"] = NOW
        st["lastCount"] = len(out)
    else:
        LAST_STATUS[src["name"]] = "bloccata dal firewall del sito (Incapsula)"
    LEONTEQ_STATE.write_text(json.dumps(st, indent=1))
    return out


async def _leonteq_search(DISC, src, NOW, ctx):
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
            await page.wait_for_timeout(2500 + random.randint(0, 2500))  # pausa tra le pagine
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


# ---------------------------------------------------------------- Euronext: elenco completo SeDeX e Cert-X
# Elenco neutro di tutti gli strumenti quotati con denaro/lettera (vedi scraper/euronext.py). Per i
# certificati d'investimento i dati di mercato (mercato, denaro, lettera, tipologia di borsa) vengono
# aggiornati a ogni run; emittente, sottostanti, scadenza e link valgono solo dove l'archivio non ha
# già i dati più ricchi delle API degli emittenti (chiave "_fallback", gestita da run.merge).
# I certificati a leva vanno in docs/data/leva.json, caricato dal sito solo su richiesta.

LEVA_COLS = ["isin", "issuer", "typeMarket", "underlyings", "maturity", "bid", "ask", "market", "strike", "currency"]


async def euronext_list(DISC, src, NOW, ctx):
    import euronext
    from run import DATA
    log = {}
    rows = await euronext.fetch_all(ctx, log)
    save(DISC, f"{src['name']}_parser.json", log)
    inv, lev = [], []
    for c in rows:
        und = c.get("underlyings") or []
        if len(und) == 1 and "/" in und[0]:
            und = [u.strip() for u in und[0].split("/") if u.strip()]
        base = {"isin": c["isin"], "market": c["market"], "bid": c["bid"], "ask": c["ask"], "currency": c["currency"],
                "typeMarket": c["type"], "issuerCode": c["issuerCode"],
                "updatedAt": NOW}
        fb = {"issuer": c["issuer"], "underlyings": und or None, "maturity": c["maturity"], "type": c["type"],
              "url": c["url"], "source": "euronext"}
        if euronext.category(c["type"]) == "Leva":
            lev.append({**base, **fb})
        else:
            inv.append(clean({**base, "_fallback": clean(fb)}))
    if lev:
        (DATA.parent / "leva.json").write_text(json.dumps({
            "version": 1, "updatedAt": NOW, "count": len(lev), "cols": LEVA_COLS,
            "rows": [[c.get(k) for k in LEVA_COLS] for c in sorted(lev, key=lambda x: x["isin"])]},
            ensure_ascii=False, separators=(",", ":")))
    LAST_STATUS[src["name"]] = f"ok: {len(inv)} d'investimento, {len(lev)} a leva (file separato)"
    return inv


# ---------------------------------------------------------------- Citi (CitiFirst Italia)
# API pubblica JSON con tutti i prodotti attivi: barriera, strike dei sottostanti, calendario dei
# richiami, scadenza, denaro e cedola (campo "manualField" o nel nome: "Cpn: 12.00%").

CITI_API = "https://www.citivelocity.com/rcs/eppublic/v1/content/citifirst/product?content_json.status=Active&content_json.country=it"


def citi_freq(dates):
    ds = sorted(d for d in dates if d)
    if len(ds) < 2:
        return None
    from datetime import date as _d
    gaps = sorted((_d.fromisoformat(b) - _d.fromisoformat(a)).days for a, b in zip(ds, ds[1:]))
    g = gaps[len(gaps) // 2]
    return "1m" if g < 45 else "3m" if g < 120 else "6m" if g < 240 else "12m"


def citi_cert(item, src, NOW):
    j = item.get("content_json") or {}
    isin = (j.get("ISIN") or item.get("businessId") or "").upper()
    if not ISIN_RE.fullmatch(isin):
        return None
    name = j.get("productName") or j.get("productHeader") or ""
    calls = j.get("periodAutoCall") or []
    freq = citi_freq([p.get("endDate") for p in calls])
    cpa, mf = None, j.get("manualField") or {}
    for k, v in mf.items():
        m = re.search(r"([\d.,]+)\s*%", str(v))
        if m and re.search(r"coupon|cedola|premio", k, re.I):
            per = num(m.group(1))
            f = next((v for rx, v in ((r"mensil|month", "1m"), (r"trimestr|quarter", "3m"), (r"semestr|semi", "6m"), (r"annual|annu", "12m"))
                      if re.search(rx, k, re.I)), None) or freq
            cpa = per * {"1m": 12, "3m": 4, "6m": 2, "12m": 1}.get(f, 1) if per is not None else None
            freq = f or freq
            break
    if cpa is None:
        m = re.search(r"Cpn:\s*([\d.,]+)\s*%", name)
        cpa = num(m.group(1)) if m else None  # nel nome è la cedola annua
    from datetime import date as _d
    today = _d.today().isoformat()
    nxt = next((p for p in sorted(calls, key=lambda p: p.get("endDate") or "") if (p.get("endDate") or "") >= today), None)
    unds = j.get("underlyingFields") or []
    return clean({
        "isin": isin, "issuer": "Citigroup", "source": src["name"], "type": j.get("productType"),
        "underlyings": [u.get("name") for u in unds if u.get("name")],
        "underlyingsDetail": [clean({"name": u.get("name"), "isin": u.get("isin"), "strike": u.get("initialPriceLevel")}) for u in unds] or None,
        "barrierPct": j.get("downsideKnockInBar"), "barrierType": "scadenza" if "Maturity" in (j.get("downsideStyle") or "") else None,
        "couponPa": round(cpa, 4) if cpa else None, "freq": freq,
        "memory": True if re.search(r"memory", name, re.I) else None,
        "callable": "Autocall" if calls else None,
        "autocallPct": nxt.get("autocallLevel") if nxt else None, "nextCallDate": nxt.get("endDate") if nxt else None,
        "maturity": pdate(j.get("maturity")), "nominal": j.get("denomination"),
        "currency": j.get("issueCurrency"), "url": j.get("url") or f"https://www.citivelocity.com/citifirst/it/{isin.lower()}",
        "updatedAt": NOW,
    })


async def citi_api(DISC, src, NOW, ctx):
    log, out = {"pages": []}, {}
    for page in range(0, 1):  # senza parametri l'API restituisce già tutti i prodotti (pageSize massimo)
        r = await ctx.request.get(CITI_API, headers={"accept": "application/json"}, timeout=90000)
        if r.status != 200:
            log["pages"].append({"page": page, "status": r.status})
            break
        d = await r.json()
        data = d.get("data") or {}
        items = data.get("content") or []
        n0 = len(out)
        for it in items:
            c = citi_cert(it, src, NOW)
            if c:
                out[c["isin"]] = c
        log["pages"].append({"page": page, "items": len(items), "new": len(out) - n0,
                             "meta": {k: v for k, v in data.items() if k != "content"}})
        if page == 0:
            log["sample"] = items[:1]
        if not items or len(out) == n0 or data.get("last") is True:
            break
    save(DISC, f"{src['name']}_parser.json", log)
    return list(out.values())


# ---------------------------------------------------------------- Borsa Italiana: scheda per ISIN
# Per i certificati ancora senza barriera (in genere quelli arrivati solo dall'elenco Euronext): barriera
# capitale %, emittente (ragione sociale), nome commerciale (memoria), sottostanti, categoria di Borsa.
# A rotazione: 1 richiesta al secondo, al massimo SCHEDA_BUDGET_MIN minuti per run, prima le cedole;
# la run successiva riparte dagli ISIN non ancora visitati (scraper/scheda_state.json).

SCHEDA_STATE = Path(__file__).resolve().parent / "scheda_state.json"
SCHEDA_BUDGET_S = int(os.environ.get("SCHEDA_BUDGET_MIN", "5")) * 60  # le schede degli emittenti coprono ormai quasi tutto
SCHEDA_URL = {"SeDeX": "https://www.borsaitaliana.it/borsa/cw-e-certificates/scheda/{}-SEDX.html?lang=it",
              "Cert-X": "https://www.borsaitaliana.it/borsa/cw-e-certificates/eurotlx/scheda/{}-ETLX.html?lang=it"}
LEGAL_NAMES = [(r"vontobel", "Vontobel"), (r"bnp", "BNP Paribas"), (r"unicredit|hvb|hypovereins", "UniCredit"),
               (r"soci[eé]t[eé] g[eé]n[eé]rale|sg issuer", "Société Générale"), (r"intesa", "Intesa Sanpaolo"),
               (r"barclays", "Barclays"), (r"mediobanca", "Mediobanca"), (r"leonteq", "Leonteq Securities"),
               (r"goldman", "Goldman Sachs"), (r"marex", "Marex"), (r"citi", "Citigroup"), (r"\bubs\b", "UBS"),
               (r"deutsche bank", "Deutsche Bank"), (r"cr[eé]dit agricole", "Crédit Agricole"), (r"banco bpm|aletti", "Banco BPM"),
               (r"santander", "Santander"), (r"natixis", "Natixis"), (r"nomura", "Nomura"), (r"morgan stanley", "Morgan Stanley"),
               (r"bper", "BPER Banca"), (r"j\.?p\.? ?morgan", "J.P. Morgan"), (r"bbva|bilbao", "BBVA"), (r"akros", "Banca Akros"),
               (r"smart etn", "Smart ETN"), (r"\bbil\b|internationale [aà] luxembourg", "BIL"), (r"efg", "EFG International"),
               (r"amundi", "Amundi"), (r"exane", "Exane"), (r"ubs", "UBS")]


def legal_to_issuer(s):
    for rx, name in LEGAL_NAMES:
        if re.search(rx, s or "", re.I):
            return name
    return (s or "").title() or None


def scheda_pairs(html):
    pairs = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        cells = [c for c in cells if c]
        if len(cells) >= 2:
            pairs.setdefault(cells[0], cells[1])
    return pairs


async def borsa_scheda(DISC, src, NOW, ctx):
    import html as _html
    import time as _time
    from datetime import date as _date
    from run import DATA
    certs = json.loads(DATA.read_text()).get("certs", []) if DATA.exists() else []
    st = json.loads(SCHEDA_STATE.read_text()) if SCHEDA_STATE.exists() else {}
    today = _date.today().isoformat()
    lev = re.compile(r"turbo|mini ?future|leva|leverage|warrant", re.I)
    live = [c for c in certs if not c.get("barrierPct") and c.get("market") in SCHEDA_URL
            and not lev.search(c.get("typeMarket") or c.get("type") or "") and (not c.get("maturity") or c["maturity"] >= today)]
    done = set(st.get("done", []))
    todo = [c for c in live if c["isin"] not in done]
    if not todo:
        st = {"cycleStart": today, "done": []}
        todo = live
    prio = lambda c: (0 if re.search(r"cash collect|phoenix|coupon|cedol", c.get("typeMarket") or c.get("type") or "", re.I)
                      else 1 if re.search(r"express", c.get("typeMarket") or "", re.I) else 2, c["isin"])
    todo.sort(key=prio)
    log = {"queue": len(todo), "visited": 0, "withBarrier": 0, "errors": 0, "samples": []}
    out, t0 = [], _time.time()
    for c in todo:
        if _time.time() - t0 > SCHEDA_BUDGET_S:
            log["stopped"] = "tempo esaurito"
            break
        t1 = _time.time()
        try:
            r = await ctx.request.get(SCHEDA_URL[c["market"]].format(c["isin"]), timeout=30000)
            html = _html.unescape(await r.text()) if r.status == 200 else ""
        except Exception:
            html = ""
        st.setdefault("done", []).append(c["isin"])
        log["visited"] += 1
        p = scheda_pairs(html) if c["isin"] in html else {}
        if not p:
            log["errors"] += 1
        else:
            if len(log["samples"]) < 3:
                log["samples"].append({"isin": c["isin"], "pairs": p})
            bar = num((p.get("Barriera Capitale %") or "").replace("+", ""))
            name = p.get("Nome Commerciale") or ""
            legal = legal_to_issuer(p.get("Emittente"))
            und = [u.strip() for u in (p.get("Sottostante") or "").split("/") if u.strip()]
            cert = {"isin": c["isin"], "commercialName": name or None, "issuerLegal": p.get("Emittente"),
                    "_fallback": clean({"barrierPct": bar, "underlyings": und or None,
                                        "memory": True if re.search(r"memory|memoria", name, re.I) else None,
                                        "maturity": pdate(p.get("Scadenza"))})}
            if legal and (not c.get("issuer") or str(c.get("issuer")).startswith("codice ")):
                cert["issuer"] = legal
            if bar:
                log["withBarrier"] += 1
            out.append(clean(cert))
        await asyncio.sleep(max(0, 1.0 - (_time.time() - t1)))  # 1 richiesta al secondo
    st["lastRun"] = NOW
    st["remaining"] = max(0, len(todo) - log["visited"])
    SCHEDA_STATE.write_text(json.dumps(st))
    save(DISC, f"{src['name']}_parser.json", log)
    LAST_STATUS[src["name"]] = f"ok: {log['visited']} schede lette, {log['withBarrier']} con barriera, {st['remaining']} in coda"
    return out
