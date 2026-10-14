"""Radar Certificati - robot notturno.

Apre le liste prodotti degli emittenti con un browser vero (Playwright),
clicca "carica di più" finché serve, intercetta le risposte JSON delle API
interne e legge le tabelle HTML. Normalizza tutto nello schema del sito e
scrive docs/data/certs.json. Salva anche discovery/ per il debug.
"""
import asyncio, inspect, json, os, re, sys, time, unicodedata, traceback
from datetime import datetime, timezone, date
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data" / "certs.json"
DISC = ROOT / "discovery"
DISC.mkdir(exist_ok=True)
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
ONLY = set(a for a in sys.argv[1:])  # opzionale: nomi sorgenti

from sources import SOURCES  # noqa: E402

ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9%]+", " ", s).strip()


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[%\s€$]|EUR|CHF|USD", "", str(v))
    if s in ("", "-", "–", "n.d.", "n/a"):
        return None
    if re.match(r"^-?[\d.]+,\d+$", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.match(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def pdate(v):
    if not v:
        return None
    s = str(v).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", s)
    if m:
        y = int(m[3]); y = y + 2000 if y < 100 else y
        return f"{y:04d}-{int(m[2]):02d}-{int(m[1]):02d}"
    return None


def freq_of(v):
    s = norm(v)
    if not s:
        return None
    if re.match(r"^(1 ?m|mens|month|monat)", s): return "1m"
    if re.match(r"^(3 ?m|trim|quart|viertel)", s): return "3m"
    if re.match(r"^(6 ?m|sem|halb)", s): return "6m"
    if re.match(r"^(12 ?m|1 ?y|ann|year|jahr)", s): return "12m"
    return s[:8]


HEADER_MAP = [
    ("isin", r"^isin"),
    ("issuer", r"emittente|issuer"),
    ("underlyings", r"sottostant|underlying|basiswert|basket"),
    ("couponPa", r"cedola.*(p ?a|ann)|premio.*(p ?a|ann)|coupon.*(p ?a|ann)|cedola potenziale|rendimento potenziale|cedola pa"),
    ("freq", r"freq"),
    ("distBarrier", r"dist.*barr|distance.*barr|buffer|abstand"),
    ("triggerPct", r"trigger|soglia"),
    ("barrierPct", r"^barriera( %| capitale| livello)?$|barrier level|^barrier$|livello barriera"),
    ("maturity", r"scadenza|maturity|expiry|falligkeit"),
    ("bid", r"^den|denaro|^bid|geld"),
    ("ask", r"^let|lettera|^ask|brief"),
    ("callable", r"richiamo|callable|autocall"),
    ("type", r"^tipo|^prodotto|product type"),
]


def map_headers(heads):
    col = {}
    for i, h in enumerate(heads):
        n = norm(h)
        for k, rx in HEADER_MAP:
            if k not in col and re.search(rx, n):
                col[k] = i
                break
    return col


def rows_to_certs(heads, rows, src):
    col = map_headers(heads)
    out = []
    for r in rows:
        txt = " ".join(r)
        isin = None
        if "isin" in col and col["isin"] < len(r):
            m = ISIN_RE.search(r[col["isin"]] or "")
            isin = m and m.group(1)
        if not isin:
            m = ISIN_RE.search(txt)
            isin = m and m.group(1)
        if not isin:
            continue
        g = lambda k: r[col[k]] if k in col and col[k] < len(r) else None
        c = {"isin": isin, "issuer": src.get("issuer"), "source": src["name"], "url": src["url"], "updatedAt": NOW}
        if src.get("type"): c["type"] = src["type"]
        u = g("underlyings")
        if u:
            parts = [p.strip() for p in re.split(r"\s*[|;\n]\s*|,\s+(?=[A-Z0-9])", u) if p.strip()]
            c["underlyings"] = parts
        v = num(g("couponPa"));  c.update(couponPa=v) if v is not None else None
        f = freq_of(g("freq"));  c.update(freq=f) if f else None
        v = num(g("distBarrier")); c.update(distBarrier=v) if v is not None else None
        v = num(g("barrierPct")); c.update(barrierPct=v) if v is not None else None
        v = num(g("triggerPct")); c.update(triggerPct=v) if v is not None else None
        d = pdate(g("maturity")); c.update(maturity=d) if d else None
        v = num(g("bid")); c.update(bid=v) if v else None
        v = num(g("ask")); c.update(ask=v) if v else None
        if g("callable"): c["callable"] = g("callable")
        out.append(c)
    return out


async def extract_tables(page):
    return await page.evaluate(
        """() => [...document.querySelectorAll('table')].map(t => {
            const heads=[...t.querySelectorAll('thead th, thead td')].map(x=>x.innerText.trim());
            const h2 = heads.length?heads:[...(t.querySelector('tr')?.children||[])].map(x=>x.innerText.trim());
            const rows=[...t.querySelectorAll('tbody tr')].map(tr=>[...tr.children].map(td=>td.innerText.trim()));
            return {heads:h2, rows};
        })"""
    )


LOAD_MORE = re.compile(r"carica di pi|mostra (altri|di pi)|load more|show more|altri risultati|mehr laden|weitere", re.I)


async def click_load_more(page, max_clicks):
    clicks = 0
    for _ in range(max_clicks):
        btn = page.get_by_role("button", name=LOAD_MORE)
        if await btn.count() == 0:
            btn = page.locator("a, span, div[role=button]").filter(has_text=LOAD_MORE)
        if await btn.count() == 0:
            break
        try:
            await btn.first.scroll_into_view_if_needed(timeout=5000)
            await btn.first.click(timeout=8000)
            clicks += 1
            await page.wait_for_timeout(1500)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
        except Exception:
            break
    return clicks


async def accept_cookies(page):
    # cookie banner + eventuali disclaimer di residenza: clicca tutto ciò che somiglia a un consenso
    for name in [r"accett", r"accept", r"consent", r"agree", r"ok, ho capito", r"alle akzeptieren", r"tutti", r"^ok$", r"confermo", r"prosegui"]:
        try:
            b = page.get_by_role("button", name=re.compile(name, re.I))
            if await b.count():
                await b.first.click(timeout=3000)
                await page.wait_for_timeout(700)
        except Exception:
            pass


async def scrape_source(ctx, src):
    page = await ctx.new_page()
    captured = []

    async def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                return
            body = await resp.text()
            if len(body) < 200:
                return
            captured.append({"url": resp.url, "status": resp.status, "len": len(body),
                             "method": resp.request.method, "post": (resp.request.post_data or "")[:2000],
                             "isins": len(set(ISIN_RE.findall(body))), "body": body})
        except Exception:
            pass

    xhr = []

    def on_request(req):
        if req.resource_type in ("xhr", "fetch") and len(xhr) < 80:
            xhr.append({"method": req.method, "url": req.url[:400], "post": (req.post_data or "")[:1500]})

    page.on("response", on_response)
    page.on("request", on_request)
    t0 = time.time()
    info = {"name": src["name"], "url": src["url"]}
    try:
        await page.goto(src["url"], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        await accept_cookies(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        info["clicks"] = await click_load_more(page, src.get("max_clicks", 60))
        tables = await extract_tables(page)
        html = await page.content()
        info["isins_in_html"] = len(set(ISIN_RE.findall(html)))
        (DISC / f"{src['name']}.html").write_text(html[:3_000_000])
        certs = []
        for t in tables:
            certs += rows_to_certs(t["heads"], t["rows"], src)
        info["tables"] = [{"heads": t["heads"], "n": len(t["rows"]), "sample": t["rows"][:2]} for t in tables]
        info["from_tables"] = len(certs)
    except Exception as e:
        info["error"] = repr(e)
        certs = []
    # discovery delle API JSON
    api = sorted(captured, key=lambda x: -x["isins"])
    info["json"] = [{k: v for k, v in a.items() if k != "body"} for a in api[:25]]
    info["xhr"] = xhr
    info["final_url"] = page.url
    for i, a in enumerate(api[:5]):
        if a["isins"]:
            (DISC / f"{src['name']}_api{i}.json").write_text(a["body"][:5_000_000])
    for i, a in enumerate(sorted((a for a in captured if not a["isins"]), key=lambda x: -x["len"])[:3]):
        (DISC / f"{src['name']}_json{i}.json").write_text(a["body"][:1_000_000])
    info["secs"] = round(time.time() - t0, 1)
    await page.close()
    return certs, info


def has_price(c):
    return bool(c.get("bid")) and bool(c.get("ask"))


JUNK_UND = re.compile(r"^ISIN\b|^[A-Z]{2}[A-Z0-9]{9}\d$")


def clean_underlyings(c):
    """Toglie dai sottostanti le voci spurie lette dalle tabelle (es. "ISIN DE000…")."""
    if isinstance(c.get("underlyings"), list):
        c["underlyings"] = [u for u in c["underlyings"] if u and not JUNK_UND.match(str(u).strip())]
    return c


def merge(old, new):
    """Unisce i certificati nuovi all'archivio.

    Denaro e lettera si aggiornano solo in coppia: se una run non li trova entrambi
    restano i prezzi precedenti, con la loro data (priceAt).
    """
    by = {}
    for c in old:
        c = dict(c)
        if has_price(c) and not c.get("priceAt"):
            c["priceAt"] = c.get("updatedAt")
        by[c["isin"]] = c
    for c in new:
        fb = c.pop("_fallback", None) or {}
        prev = by.get(c["isin"], {})
        # campi di ripiego (es. da Euronext): solo se l'archivio non li ha già da una fonte più ricca
        c = {**{k: v for k, v in fb.items() if v not in (None, "", []) and prev.get(k) in (None, "", [])}, **c}
        c = {k: v for k, v in c.items() if v not in (None, "", [])}
        if has_price(c):
            c["priceAt"] = NOW
        else:
            c.pop("bid", None)
            c.pop("ask", None)
        by[c["isin"]] = {**by.get(c["isin"], {}), **c}
    today = date.today().isoformat()
    return [clean_underlyings(c) for c in by.values() if not c.get("maturity") or c["maturity"] >= today]


async def main():
    old_meta = json.loads(DATA.read_text()) if DATA.exists() else {}
    old = old_meta.get("certs", [])
    report = []
    found = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            locale="it-IT", timezone_id="Europe/Rome", viewport={"width": 1440, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        )
        for src in SOURCES:
            if ONLY and src["name"] not in ONLY:
                continue
            try:
                if src.get("skip_page"):  # sorgente servita solo dal parser
                    certs, info = [], {"name": src["name"], "url": src["url"]}
                else:
                    certs, info = await scrape_source(ctx, src)
            except Exception:
                certs, info = [], {"name": src["name"], "error": traceback.format_exc()[-800:]}
            # parser specifici (API) se presenti
            parser = src.get("parser")
            if parser:
                try:
                    mod = __import__("parsers", fromlist=[parser])
                    fn = getattr(mod, parser)
                    args = (DISC, src, NOW, ctx)[:len(inspect.signature(fn).parameters)]
                    extra = fn(*args)
                    if inspect.isawaitable(extra):
                        extra = await extra
                    info["from_parser"] = len(extra)
                    if getattr(mod, "LAST_STATUS", {}).get(src["name"]):
                        info["status"] = mod.LAST_STATUS[src["name"]]
                    certs += extra
                except Exception:
                    info["parser_error"] = traceback.format_exc()[-800:]
            info["certs"] = len({c["isin"] for c in certs})
            info["withPrice"] = len({c["isin"] for c in certs if has_price(c)})
            print(f"[{src['name']}] {info.get('certs')} certificati · {info.get('clicks', 0)} click · {info.get('secs')}s · errore={info.get('error', '-')}", flush=True)
            report.append(info)
            found += certs
        await browser.close()
    certs = merge(old, found)
    # stato per sorgente: quelle non eseguite in questa run mantengono i dati precedenti
    srcs = {s["name"]: s for s in old_meta.get("sources", [])}
    for r in report:
        prev = srcs.get(r["name"], {})
        if r.get("certs", 0) == 0 and prev.get("certs"):
            # sorgente bloccata o saltata: resta l'ultimo esito buono, con la sua data, e lo si segnala
            srcs[r["name"]] = {**prev, "status": r.get("status") or "bloccata", "lastAttempt": NOW}
        else:
            srcs[r["name"]] = {"name": r["name"], "certs": r.get("certs", 0), "updatedAt": NOW,
                               "withPrice": r.get("withPrice", 0), "status": "ok"}
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({"updatedAt": NOW, "count": len(certs),
                                "sources": list(srcs.values()),
                                "certs": certs}, ensure_ascii=False, separators=(",", ":")))
    (DISC / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"TOTALE in archivio: {len(certs)}")


if __name__ == "__main__":
    asyncio.run(main())
