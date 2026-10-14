"""Radar Certificati - volatilità dei sottostanti e probabilità di tenuta barriera.

Gira dopo lo scraping e aggiorna docs/data/certs.json.

1. Mappa ogni sottostante a un ticker Yahoo (scraper/underlyings_map.json; il campo
   "manual" è una correzione a mano e non viene mai sovrascritto).
2. Scarica 1 anno di chiusure (Yahoo, fallback stooq) e calcola vol1y, vol3m e le
   correlazioni a coppie. Solo nella prima run del giorno: le run successive
   riusano scraper/risk_state.json.
3. Monte Carlo con moti browniani geometrici correlati (drift 0) per ogni
   certificato con prezzo, scadenza e distanza dalla barriera.

Uso: python scraper/risk.py [--offline] [--force]
  --offline  niente rete: usa solo cache e stato salvato (test)
  --force    ricalcola le volatilità anche se già fatte oggi
"""
import hashlib
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

import os
ROOT = Path(os.environ.get("RADAR_ROOT") or Path(__file__).resolve().parent.parent)
DATA = ROOT / "docs" / "data" / "certs.json"
MAP = ROOT / "scraper" / "underlyings_map.json"
STATE = ROOT / "scraper" / "risk_state.json"
PRICES = ROOT / "data" / "prices"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
TODAY = datetime.now(ZoneInfo("Europe/Rome")).date()
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
PAUSE = 0.5
N_EUROPEAN = 20_000
N_CONTINUOUS = 5_000
MIN_SIM = 0.6
OK_TYPES = {"EQUITY", "INDEX", "ETF"}
BAD_EXCH = {"PNK", "OTC", "OQB", "OQX", "OEM", "OBB"}  # OTC/pink sheets: liquidità scarsa
STOP = {"inc", "corp", "corporation", "co", "company", "spa", "s p a", "sa", "nv", "n v", "ag", "se", "plc", "ltd",
        "limited", "group", "holding", "holdings", "the", "adr", "class", "cl", "ordinary", "shares", "reg", "sab",
        "de", "cv", "asa", "oyj", "ab", "a s", "as", "bhd", "tbk", "kgaa", "s a", "n a", "com"}


# ---------------------------------------------------------------- utilità

def log(*a):
    print("[risk]", *a, flush=True)


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def clean_name(s):
    """Nome per la ricerca: senza note tra parentesi, simboli e code tipo ' - Barriera US'."""
    s = re.sub(r"\([^)]*\)|®|™|\*", " ", str(s or ""))
    s = re.sub(r"\s+-\s+barriera.*$", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def core(s):
    """Nome normalizzato senza forme societarie, per il confronto di similarità."""
    words = [w for w in norm(clean_name(s)).split() if w not in STOP]
    return " ".join(words)


def similarity(a, b):
    a, b = core(a), core(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    r = SequenceMatcher(None, a, b).ratio()
    # "amazon" vs "amazon com": il nome breve contenuto all'inizio del lungo
    if b.startswith(a + " ") or a.startswith(b + " "):
        r = max(r, 0.8)
    return round(r, 3)


def http_json(url, retries=2):
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == retries:
                raise
            time.sleep(2 * (i + 1))


def http_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode()


def load(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def dump(p, obj, compact=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) if compact
                 else json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True))


# ---------------------------------------------------------------- sottostanti dei certificati

def split_list(name):
    """'A2A, NextEra, RWE, Veolia' (un solo campo) -> 4 nomi; i nomi con una virgola restano interi."""
    parts = [p.strip() for p in str(name).split(",") if p.strip()]
    return parts if len(parts) >= 3 else [str(name).strip()]


def cert_underlyings(c):
    """[(nome, dist|None, isin|None)] del certificato."""
    det = c.get("underlyingsDetail") or []
    if det:
        return [(u.get("name"), u.get("dist"), u.get("isin")) for u in det if u.get("name")]
    out = []
    for u in c.get("underlyings") or []:
        for n in split_list(u):
            out.append((n, None, None))
    return out


def all_underlyings(certs):
    found = {}
    for c in certs:
        for name, _, isin in cert_underlyings(c):
            k = core(name) or norm(name)
            if not k:
                continue
            e = found.setdefault(k, {"name": clean_name(name), "isin": None})
            if isin and ISIN_RE.match(isin):
                e["isin"] = isin
    return found


# ---------------------------------------------------------------- mappa nome -> ticker

def yahoo_search(q):
    url = "https://query1.finance.yahoo.com/v1/finance/search?" + urllib.parse.urlencode(
        {"q": q, "quotesCount": 8, "newsCount": 0, "listsCount": 0, "enableFuzzyQuery": "false"})
    return http_json(url).get("quotes") or []


def pick(quotes, name, by_isin=False):
    """Primo risultato accettabile: tipo EQUITY/INDEX/ETF e nome simile (>= 0.6).
    Con la ricerca per ISIN l'identità è già certa: basta il tipo."""
    best = None
    for q in quotes:
        if q.get("quoteType") not in OK_TYPES or q.get("exchange") in BAD_EXCH:
            continue
        ynames = [q.get("shortname") or "", q.get("longname") or ""]
        sim = max(similarity(name, y) for y in ynames)
        sym = (q.get("symbol") or "").split(".")[0].lstrip("^")
        if norm(clean_name(name)).replace(" ", "") == norm(sym).replace(" ", ""):
            sim = max(sim, 0.9)  # "AMD" -> AMD
        ok = by_isin or sim >= MIN_SIM
        if ok and (best is None or sim > best[1] + 0.05):
            best = (q, sim)
    if not best:
        return None
    q, sim = best
    return {"ticker": q["symbol"], "yahooName": q.get("longname") or q.get("shortname"),
            "type": q.get("quoteType"), "exchange": q.get("exchange"), "score": sim}


def update_map(unds, offline):
    m = load(MAP, {})
    retry_before = (TODAY - timedelta(days=7)).isoformat()
    searched = 0
    for k, u in sorted(unds.items()):
        e = m.setdefault(k, {"name": u["name"], "isin": None, "ticker": None, "manual": None})
        if u.get("isin") and not e.get("isin"):
            e["isin"] = u["isin"]
            e.pop("checkedAt", None)  # con l'ISIN vale la pena riprovare
        if e.get("manual") is not None or offline:
            continue
        if e.get("checkedAt") and (e.get("ticker") or e["checkedAt"] >= retry_before):
            continue
        res = None
        try:
            if e.get("isin"):
                res = pick(yahoo_search(e["isin"]), e["name"], by_isin=True)
                time.sleep(PAUSE)
            if not res:
                res = pick(yahoo_search(clean_name(e["name"])), e["name"])
                time.sleep(PAUSE)
        except Exception as ex:
            log("ricerca fallita", e["name"], repr(ex)[:120])
            time.sleep(PAUSE)
            continue
        searched += 1
        e.update({"ticker": None, "yahooName": None, "type": None, "exchange": None, "score": None})
        if res:
            e.update(res)
        e["checkedAt"] = TODAY.isoformat()
    dump(MAP, m)
    log(f"mappa: {len(m)} nomi, {searched} ricerche nuove")
    return m


def ticker_of(m, name):
    e = m.get(core(name) or norm(name)) or {}
    t = e.get("manual") if e.get("manual") is not None else e.get("ticker")
    return t if t and t != "-" else None


# ---------------------------------------------------------------- prezzi e volatilità

def stooq_symbol(t):
    if t.startswith("^"):
        return None
    return t.lower() + ".us" if "." not in t else None


def fetch_closes(ticker, offline):
    """[(data, chiusura)] dell'ultimo anno; cache giornaliera in data/prices/ (non pubblicata)."""
    f = PRICES / (re.sub(r"[^A-Za-z0-9._^-]", "_", ticker) + ".json")
    cached = load(f, None)
    if cached and (offline or cached.get("fetchedAt") == TODAY.isoformat()):
        return [tuple(x) for x in cached["closes"]]
    if offline:
        return []
    closes = []
    try:
        d = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?range=1y&interval=1d")
        r = d["chart"]["result"][0]
        ts, cl = r.get("timestamp") or [], r["indicators"]["quote"][0].get("close") or []
        closes = [(datetime.fromtimestamp(t, timezone.utc).date().isoformat(), c) for t, c in zip(ts, cl) if c]
    except Exception as ex:
        log("chart Yahoo fallito", ticker, repr(ex)[:100])
    time.sleep(PAUSE)
    if len(closes) < 40 and stooq_symbol(ticker):
        try:
            since = (TODAY - timedelta(days=370)).strftime("%Y%m%d")
            txt = http_text(f"https://stooq.com/q/d/l/?s={stooq_symbol(ticker)}&i=d&d1={since}")
            rows = [r.split(",") for r in txt.strip().splitlines()[1:]]
            closes = [(r[0], float(r[4])) for r in rows if len(r) > 4 and r[4] not in ("", "null")]
        except Exception as ex:
            log("stooq fallito", ticker, repr(ex)[:100])
        time.sleep(PAUSE)
    if closes:
        dump(f, {"fetchedAt": TODAY.isoformat(), "closes": closes}, compact=True)
    return closes


def log_returns(closes):
    c = np.array([x[1] for x in closes], dtype=float)
    return np.diff(np.log(c))


def vols(closes):
    r = log_returns(closes)
    v1 = float(np.std(r[-252:], ddof=1) * math.sqrt(252)) if len(r) >= 40 else None
    v3 = float(np.std(r[-63:], ddof=1) * math.sqrt(252)) if len(r) >= 20 else None
    return v1, v3


def correlation(ca, cb):
    """Correlazione dei log-rendimenti a date allineate (solo date comuni)."""
    a, b = dict(ca), dict(cb)
    days = sorted(set(a) & set(b))
    if len(days) < 40:
        return None
    ra = np.diff(np.log([a[d] for d in days]))
    rb = np.diff(np.log([b[d] for d in days]))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return round(float(np.corrcoef(ra, rb)[0, 1]), 4)


def update_state(certs, m, offline, force):
    st = load(STATE, {})
    if st.get("date") == TODAY.isoformat() and not force:
        log("volatilità già calcolate oggi: riuso", STATE.name)
        return st
    tickers = sorted({t for c in certs for n, _, _ in cert_underlyings(c) if (t := ticker_of(m, n))})
    log(f"scarico prezzi per {len(tickers)} ticker")
    closes, und = {}, {}
    for t in tickers:
        cl = fetch_closes(t, offline)
        if not cl:
            continue
        closes[t] = cl
        v1, v3 = vols(cl)
        if v1 is None and v3 is None:
            continue
        und[t] = {"vol1y": round(v1, 4) if v1 else None, "vol3m": round(v3, 4) if v3 else None,
                  "volUsed": round(max(x for x in (v1, v3) if x is not None), 4),
                  "observations": len(cl), "lastClose": cl[-1][1], "lastDate": cl[-1][0], "updatedAt": NOW}
    # correlazioni solo per le coppie che compaiono insieme in un certificato
    pairs = set()
    for c in certs:
        ts = sorted({t for n, _, _ in cert_underlyings(c) if (t := ticker_of(m, n)) and t in und})
        pairs |= {(a, b) for i, a in enumerate(ts) for b in ts[i + 1:]}
    corr = {}
    for a, b in sorted(pairs):
        r = correlation(closes[a], closes[b])
        if r is not None:
            corr[f"{a}|{b}"] = r
    st = {"date": TODAY.isoformat(), "updatedAt": NOW, "underlyings": und, "corr": corr}
    dump(STATE, st)
    log(f"volatilità: {len(und)} ticker, {len(corr)} correlazioni")
    return st


# ---------------------------------------------------------------- distanza dai prezzi dei sottostanti

def refresh_distance(c, m, st):
    """Per i certificati con distanza non aggiornata dall'emittente (distAt valorizzato): se sono noti
    strike di ogni sottostante e barriera %, ricalcola le distanze dalle ultime chiusure.
    Altrimenti resta l'ultima distanza nota con la sua data (distAt)."""
    det, bp = c.get("underlyingsDetail") or [], c.get("barrierPct")
    # solo se la distanza non arriva fresca dall'emittente: distanza vecchia (distAt) o strike senza distanze (es. Citi)
    if not c.get("distAt") and any(u.get("dist") is not None for u in det):
        return False
    if not det or not bp or not all(u.get("strike") for u in det):
        return False
    U = st.get("underlyings", {})
    rows = []
    for u in det:
        v = U.get(ticker_of(m, u.get("name")) or "")
        if not v or not v.get("lastClose"):
            return False
        # strike e chiusura devono essere confrontabili (stessa quotazione e valuta): altrimenti niente distanza
        if not 0.2 <= v["lastClose"] / u["strike"] <= 5:
            c["distNote"] = f"strike di {u.get('name')} non confrontabile con la chiusura di {ticker_of(m, u.get('name'))}"
            return False
        rows.append((u, v))
    for u, v in rows:
        u["dist"] = round((1 - u["strike"] * bp / 100 / v["lastClose"]) * 100, 2)
    w = min(rows, key=lambda r: r[0]["dist"])
    c.update({"distBarrier": w[0]["dist"], "worstName": w[0].get("name"),
              "distAt": min(v["lastDate"] for _, v in rows), "distSource": "chiusure sottostanti"})
    return True


# ---------------------------------------------------------------- Monte Carlo

def nearest_corr(c):
    """Matrice di correlazione definita positiva più vicina (autovalori tagliati, diagonale 1)."""
    w, v = np.linalg.eigh((c + c.T) / 2)
    w = np.clip(w, 1e-6, None)
    a = v @ np.diag(w) @ v.T
    d = np.sqrt(np.diag(a))
    a = a / np.outer(d, d)
    np.fill_diagonal(a, 1.0)
    return a


def cholesky(c):
    try:
        return np.linalg.cholesky(c), False
    except np.linalg.LinAlgError:
        return np.linalg.cholesky(nearest_corr(c)), True


def seed_of(isin):
    return int(hashlib.sha256(isin.encode()).hexdigest()[:8], 16)


def mc_hold(levels, sig, corr, T, continuous, seed):
    """Probabilità che tutti i sottostanti restino sopra la barriera.

    levels: S0/B per sottostante; sig: volatilità annue; corr: matrice di correlazione.
    Moto browniano geometrico con drift 0 sul prezzo: ln S_t/B = ln L - σ²t/2 + σ W_t.
    """
    rng = np.random.default_rng(seed)
    L, _ = cholesky(corr)
    x0 = np.log(levels)
    if not continuous:
        z = rng.standard_normal((N_EUROPEAN, len(levels))) @ L.T
        xT = x0 - 0.5 * sig ** 2 * T + sig * math.sqrt(T) * z
        return float(np.mean(np.all(xT >= 0, axis=1)))
    if np.any(x0 < 0):
        return 0.0  # barriera continua già toccata
    steps = max(1, int(math.ceil(T * 252)))
    dt = T / steps
    x = np.tile(x0, (N_CONTINUOUS, 1))
    alive = np.ones(N_CONTINUOUS, dtype=bool)
    drift, vol = -0.5 * sig ** 2 * dt, sig * math.sqrt(dt)
    for _ in range(steps):
        x += drift + vol * (rng.standard_normal((N_CONTINUOUS, len(levels))) @ L.T)
        alive &= np.all(x >= 0, axis=1)
    return float(np.mean(alive))


def years_to(d):
    try:
        return (date.fromisoformat(d) - TODAY).days / 365.25
    except Exception:
        return None


def risk_for(c, m, st):
    """Campi di rischio di un certificato (None dove mancano i dati)."""
    und = cert_underlyings(c)
    U = st.get("underlyings", {})
    rows = []
    for name, dist, _ in und:
        t = ticker_of(m, name)
        v = U.get(t) if t else None
        rows.append({"name": name, "ticker": t, "vol1y": v and v["vol1y"], "vol3m": v and v["vol3m"],
                     "dist": dist, "_vol": v and v["volUsed"]})
    out = {"probBarrierHold": None, "probMethod": None, "probHorizonYears": None, "worstVol": None,
           "underlyingsRisk": [{k: r[k] for k in ("name", "ticker", "vol1y", "vol3m", "dist")} for r in rows] or None,
           "riskAt": NOW}
    T = years_to(c.get("maturity"))
    dist = c.get("distBarrier")
    if not (c.get("bid") and c.get("ask")) or T is None or T <= 0 or dist is None or not rows:
        return out
    T = min(T, 15.0)
    continuous = c.get("barrierType") == "continua"
    full = all(r["dist"] is not None and r["_vol"] for r in rows)
    if full:
        sel = rows
        method = "mc_continua" if continuous else "mc_europea"
    else:
        # nota solo la distanza del peggiore: un solo sottostante (limite superiore se sono più d'uno)
        wn = c.get("worstName")
        w = next((r for r in rows if wn and r["name"] == wn), None) or (rows[0] if len(rows) == 1 else None)
        if w is not None and w["_vol"]:
            vol = w["_vol"]
        elif len(rows) > 1 and all(r["_vol"] for r in rows):
            vol = max(r["_vol"] for r in rows)  # peggiore non identificato: la vol più alta (prudente)
            out["probNote"] = "peggiore non identificato: usata la volatilità più alta tra i sottostanti"
        else:
            return out
        sel = [{"name": w["name"] if w else None, "dist": dist, "_vol": vol, "ticker": w and w["ticker"]}]
        method = ("mc_continua" if continuous else "mc_europea") if len(rows) == 1 else "solo_peggiore"
    dists = np.array([r["dist"] for r in sel], dtype=float)
    if np.any(dists >= 100):
        return out
    levels = 1.0 / (1.0 - dists / 100.0)
    sig = np.array([r["_vol"] for r in sel], dtype=float)
    n = len(sel)
    corr = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = sorted((sel[i]["ticker"] or "", sel[j]["ticker"] or ""))
            rho = st.get("corr", {}).get(f"{a}|{b}")
            if a == b and a:
                rho = 1.0
            corr[i, j] = corr[j, i] = rho if rho is not None else 0.0  # correlazione ignota: 0 (prudente)
    p = mc_hold(levels, sig, corr, T, continuous, seed_of(c["isin"]))
    if c.get("distAt") and (TODAY - date.fromisoformat(c["distAt"][:10])).days > 3:
        out["probNote"] = ((out.get("probNote") + "; ") if out.get("probNote") else "") + \
            f"distanza dalla barriera del {c['distAt'][:10]}"
    worst = int(np.argmin(dists))
    out.update({"probBarrierHold": round(p, 3), "probMethod": method, "probHorizonYears": round(T, 2),
                "worstVol": round(float(sig[worst]), 4)})
    return out


# ---------------------------------------------------------------- main

def main():
    offline = "--offline" in sys.argv
    force = "--force" in sys.argv
    meta = json.loads(DATA.read_text())
    certs = meta["certs"]
    # solo i sottostanti dei certificati con distanza dalla barriera: per gli altri la probabilità non si calcola
    unds = all_underlyings([c for c in certs if c.get("distBarrier") is not None or c.get("underlyingsDetail")])
    log(f"{len(certs)} certificati, {len(unds)} sottostanti distinti")
    first_today = load(STATE, {}).get("date") != TODAY.isoformat() or force
    m = update_map(unds, offline or not first_today)
    st = update_state(certs, m, offline, force)
    t0, n_prob, n_dist = time.time(), 0, 0
    for c in certs:
        for k in ("probBarrierHold", "probMethod", "probHorizonYears", "worstVol", "underlyingsRisk", "riskAt", "probNote"):
            c.pop(k, None)
        n_dist += refresh_distance(c, m, st)
        r = risk_for(c, m, st)
        c.update({k: v for k, v in r.items() if k != "probNote" or v})
        n_prob += r["probBarrierHold"] is not None
    meta["riskAt"] = NOW
    DATA.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
    mapped = sum(1 for k in unds if ticker_of(m, unds[k]["name"]))
    log(f"sottostanti mappati {mapped}/{len(unds)}; certificati con probabilità {n_prob}; distanze ricalcolate {n_dist}; MC {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
