"""Elenco completo e neutro dei certificati quotati su SeDeX e Cert-X (EuroTLX) dalla directory
prodotti di live.euronext.com (Euronext è proprietaria di Borsa Italiana).

L'endpoint è quello che la pagina "Warrants & Certificates Milan" chiama per la sua tabella:
POST /it/product_directory/data/warrants-milan?mics=ETLX,SEDX con i parametri DataTables (start, length).
Ogni riga ha ISIN e mercato (nel link), simbolo, descrizione con il codice emittente, sottostante,
tipologia, strike, scadenza, denaro/lettera, ultimo prezzo e ora.

Uso diretto (esplorazione): python scraper/euronext.py [max_pagine] -> explore/euronext_*.json
"""
import asyncio
import html as _html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

BASE = "https://live.euronext.com"
LIST_PAGE = BASE + "/it/markets/milan/structured-products/list"
API = BASE + "/it/product_directory/data/warrants-milan?mics=ETLX%2CSEDX"
PAGE = 500
MARKET = {"SEDX": "SeDeX", "ETLX": "Cert-X"}

# codice emittente (prima parola della descrizione Euronext) -> emittente
ISSUERS = {
    "LQ": "Leonteq Securities", "LEO": "Leonteq Securities", "CGM": "Citigroup", "CIT": "Citigroup",
    "SGI": "Société Générale", "SG": "Société Générale", "SGE": "Société Générale", "BNP": "BNP Paribas",
    "BNPP": "BNP Paribas", "UC": "UniCredit", "UCB": "UniCredit", "UCG": "UniCredit", "HVB": "UniCredit",
    "VON": "Vontobel", "VT": "Vontobel", "VONT": "Vontobel", "MB": "Mediobanca", "MED": "Mediobanca",
    "ISP": "Intesa Sanpaolo", "IS": "Intesa Sanpaolo", "BAR": "Barclays", "BCL": "Barclays", "BARC": "Barclays",
    "GS": "Goldman Sachs", "GSI": "Goldman Sachs", "GSW": "Goldman Sachs", "MS": "Morgan Stanley", "MSB": "Morgan Stanley",
    "BBVA": "BBVA", "BBV": "BBVA", "NAT": "Natixis", "NTX": "Natixis", "MAR": "Marex", "MRX": "Marex",
    "AKR": "Banca Akros", "AKROS": "Banca Akros", "SMT": "Smart ETN", "SET": "Smart ETN", "EFG": "EFG International",
    "BIL": "BIL", "RAI": "Raiffeisen", "RCB": "Raiffeisen", "DB": "Deutsche Bank", "JPM": "J.P. Morgan",
    "UBS": "UBS", "CS": "Credit Suisse", "EQT": "Equita", "BPER": "BPER", "BPM": "Banco BPM", "ALE": "Aletti (Banco BPM)",
    "SPK": "Spark", "IXIS": "Natixis", "CA": "Crédit Agricole", "CACIB": "Crédit Agricole", "HSBC": "HSBC",
    "ING": "ING", "COM": "Commerzbank", "CBK": "Commerzbank", "DZ": "DZ Bank", "SWQ": "Swissquote", "WIS": "WisdomTree",
    "SMA": "Smart ETN", "IG": "IG", "BKB": "Basler Kantonalbank",
    # codici visti nella directory Euronext (ottobre 2026), dedotti da prefissi ISIN e simboli
    "BPA": "BNP Paribas", "UCH": "UniCredit", "GSF": "Goldman Sachs", "GSE": "Goldman Sachs", "GSG": "Goldman Sachs",
    "CFS": "Crédit Agricole", "CAG": "Crédit Agricole", "SAN": "Santander", "NSI": "Natixis", "NOM": "Nomura",
    "BPE": "BPER Banca", "JPS": "J.P. Morgan", "BVA": "BBVA", "MSI": "Morgan Stanley", "MBI": "Mediobanca",
    "AMU": "Amundi", "BP": "Banco BPM", "EXS": "Exane", "EXF": "Exane",
}

LEVA_RX = re.compile(r"turbo|mini ?future|leva fissa|leverage|factor|covered warrant|\bwarrant|knock.?out|\bcall\b|\bput\b|stayhigh|stay high", re.I)
CATS = [
    ("Leva", LEVA_RX),
    ("Protetto", re.compile(r"protec|protet|garant|capital", re.I)),
    ("Bonus Cap", re.compile(r"bonus", re.I)),
    ("Cash Collect/Phoenix", re.compile(r"cash ?collect|phoenix|coupon|cedol|premium|fixed|memory|income|reverse conv|step ?down|digital", re.I)),
    ("Express", re.compile(r"express|athena|autocall", re.I)),
]

TAG = re.compile(r"<[^>]+>")


def text(s):
    return _html.unescape(TAG.sub("", s or "")).strip()


def num(s):
    """Numero dal testo Euronext: la pagina italiana usa "1.234,56", quella inglese "1,234.56"."""
    s = re.sub(r"[^\d,.\-]", "", s or "")
    if not s or s in "-.,":
        return None
    if "," in s and "." in s:  # il separatore che compare per ultimo è quello dei decimali
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:  # solo virgole: decimali all'italiana, oppure migliaia all'inglese ("1,234,567")
        s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3}){2,}", s) else s.replace(",", ".")
    elif s.count(".") > 1:  # "1.234.567" = migliaia all'italiana
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def category(ptype):
    for cat, rx in CATS:
        if rx.search(ptype or ""):
            return cat
    return "Altro"


def issuer_of(hover):
    code = (hover or "").split(" ")[0].upper()
    return ISSUERS.get(code) or (f"codice {code}" if code else None), code


def parse_row(r):
    m = re.search(r'href="[^"]*/([A-Z]{2}[A-Z0-9]{9}\d)-([A-Z]{4})"', r[0])
    if not m:
        return None
    isin, mic = m.group(1), m.group(2)
    hover = _html.unescape((re.search(r'data-title-hover="([^"]*)"', r[0]) or [None, ""])[1])
    issuer, code = issuer_of(hover)
    ptype = text(r[2])
    bidask = text(r[5])
    bid = ask = None
    if "/" in bidask:
        b, a = bidask.split("/", 1)
        bid, ask = num(b), num(a)
    und = text(r[1])
    cur = re.search(r"\b([A-Z]{3})\b", text(r[6]))
    return {
        "isin": isin, "market": MARKET.get(mic, mic), "mic": mic, "symbol": text(r[0]),
        "issuer": issuer, "issuerCode": code, "description": hover, "type": ptype, "category": category(ptype),
        "underlyings": [und] if und and und != "-" else None, "strike": num(text(r[3])),
        "maturity": text(r[4]) if re.match(r"\d{4}-\d{2}-\d{2}", text(r[4])) else None,
        "bid": bid or None, "ask": ask or None, "currency": cur.group(1) if cur else None,
        "lastPrice": num(text(r[6]).split()[-1]) if text(r[6]) else None, "lastTradeTime": text(r[7]),
        "url": (f"https://www.borsaitaliana.it/borsa/cw-e-certificates/eurotlx/scheda/{isin}-ETLX.html?lang=it" if mic == "ETLX"
                else f"https://www.borsaitaliana.it/borsa/cw-e-certificates/scheda/{isin}-SEDX.html?lang=it"),
    }


def form(start, length, draw):
    p = {"draw": draw, "start": start, "length": length, "iDisplayStart": start, "iDisplayLength": length,
         "order[0][column]": 0, "order[0][dir]": "asc", "search[value]": "", "search[regex]": "false",
         "args[display_datapoints]": "symbol,underlyingInstrument,productName,strike,maturity,ask,lastPrice,lastTradeTime"}
    for i in range(8):
        p.update({f"columns[{i}][data]": i, f"columns[{i}][name]": "", f"columns[{i}][searchable]": "true",
                  f"columns[{i}][orderable]": "true" if i < 3 else "false", f"columns[{i}][search][value]": "",
                  f"columns[{i}][search][regex]": "false"})
    return urlencode(p)


PARALLEL = 4


async def fetch_all(ctx, log, max_pages=None, pause_ms=800):
    """Scarica tutte le righe. Le richieste partono dalla pagina Euronext (cookie e header del browser)."""
    page = await ctx.new_page()
    out = {}
    try:
        api = API
        for i, url in enumerate([LIST_PAGE, LIST_PAGE.replace("/it/", "/en/"), LIST_PAGE]):
            try:  # basta l'origine del sito per le chiamate: non serve aspettare il caricamento completo
                await page.goto(url, wait_until="commit", timeout=90000)
                await page.wait_for_timeout(6000)
                api = API if "/it/" in url else API.replace("/it/", "/en/")
                break
            except Exception as e:
                log.setdefault("goto_errors", []).append(repr(e)[:200])
                await page.wait_for_timeout(10000 * (i + 1))
        else:
            raise RuntimeError("pagina Euronext non raggiungibile")
        for name in ("Accetta tutti", "Accept all", "Accetta", "Accept"):
            b = page.get_by_role("button", name=re.compile(name, re.I))
            if await b.count():
                try:
                    await b.first.click(timeout=3000)
                except Exception:
                    pass
                break
        # prima pagina: dà il totale; poi le altre a gruppi di PARALLEL in parallelo (prima erano in fila: 15 minuti)
        async def get(start, draw):
            for attempt in range(3):
                st, txt = await page.evaluate("""async ([url, body]) => {
                    const r = await fetch(url, {method: 'POST', body, credentials: 'include',
                      headers: {'content-type': 'application/x-www-form-urlencoded; charset=UTF-8', 'x-requested-with': 'XMLHttpRequest'}});
                    return [r.status, await r.text()];
                }""", [api, form(start, PAGE, draw)])
                if st == 200:
                    try:
                        return json.loads(txt)
                    except ValueError:
                        pass
                log.setdefault("errors", []).append({"start": start, "status": st, "attempt": attempt, "body": txt[:200]})
                await page.wait_for_timeout(4000 * (attempt + 1))
            return None

        def take(d, start):
            rows = (d or {}).get("aaData") or (d or {}).get("data") or []
            for r in rows:
                c = parse_row(r)
                if c:
                    out[c["isin"]] = c
            log.setdefault("pages", []).append({"start": start, "rows": len(rows)})

        first = await get(0, 1)
        if first is None:
            raise RuntimeError("prima pagina Euronext non disponibile")
        total = int(first.get("iTotalRecords") or first.get("recordsTotal") or 0)
        take(first, 0)
        starts = list(range(PAGE, total, PAGE))
        if max_pages:
            starts = starts[:max_pages - 1]
        for k in range(0, len(starts), PARALLEL):
            batch = starts[k:k + PARALLEL]
            res = await asyncio.gather(*(get(st, 2 + k + n) for n, st in enumerate(batch)))
            for st, d in zip(batch, res):
                take(d, st)
            await page.wait_for_timeout(pause_ms)
        missing = [p["start"] for p in log["pages"] if not p["rows"]]
        if missing:
            log["missing_pages"] = missing
        log["total"] = total
    finally:
        await page.close()
    log["fetched"] = len(out)
    return list(out.values())


async def _explore():
    from playwright.async_api import async_playwright
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else None
    outdir = Path("explore")
    outdir.mkdir(exist_ok=True)
    log = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(locale="it-IT", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
        certs = await fetch_all(ctx, log, max_pages)
        await b.close()
    stats = {
        "log": {k: v for k, v in log.items() if k != "pages"}, "pages": len(log.get("pages", [])),
        "by_category": Counter(c["category"] for c in certs).most_common(),
        "by_type": Counter(c["type"] for c in certs).most_common(120),
        "by_issuer_code": Counter((c["issuerCode"], c["issuer"]) for c in certs).most_common(120),
        "by_market": Counter(c["market"] for c in certs).most_common(),
        "with_price": sum(1 for c in certs if c["bid"] and c["ask"]),
        "with_price_no_leva": sum(1 for c in certs if c["bid"] and c["ask"] and c["category"] != "Leva"),
        "no_leva": sum(1 for c in certs if c["category"] != "Leva"),
        "sample": certs[:5],
    }
    (outdir / "euronext_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    (outdir / "euronext_all.json").write_text(json.dumps(certs, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({k: stats[k] for k in ("log", "pages", "by_category", "by_market", "with_price", "no_leva", "with_price_no_leva")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(_explore())
