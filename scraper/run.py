"""Radar Certificati - robot notturno.

Apre le liste prodotti degli emittenti con un browser vero (Playwright),
clicca "carica di più" finché serve, intercetta le risposte JSON delle API
interne e legge le tabelle HTML. Normalizza tutto nello schema del sito e
scrive docs/data/certs.json. Salva anche discovery/ per il debug.
"""
import asyncio, json, os, re, sys, time, unicodedata, traceback
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
    for name in [r"accett", r"accept", r"consent", r"agree", r"ok, ho capito", r"alle akzeptieren", r"tutti"]:
        try:
            b = page.get_by_role("button", name=re.compile(name, re.I))
            if await b.count():
                await b.first.click(timeout=3000)
                await page.wait_for_timeout(500)
                return
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

    page.on("response", on_response)
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
    for i, a in enumerate(api[:5]):
        if a["isins"]:
            (DISC / f"{src['name']}_api{i}.json").write_text(a["body"][:5_000_000])
    for i, a in enumerate(sorted((a for a in captured if not a["isins"]), key=lambda x: -x["len"])[:3]):
        (DISC / f"{src['name']}_json{i}.json").write_text(a["body"][:1_000_000])
    info["secs"] = round(time.time() - t0, 1)
    await page.close()
    return certs, info


def merge(old, new):
    by = {c["isin"]: c for c in old}
    for c in new:
        prev = by.get(c["isin"], {})
        m = {**prev, **{k: v for k, v in c.items() if v not in (None, "", [])}}
        by[c["isin"]] = m
    today = date.today().isoformat()
    return [c for c in by.values() if not c.get("maturity") or c["maturity"] >= today]


async def main():
    old = json.loads(DATA.read_text()).get("certs", []) if DATA.exists() else []
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
                certs, info = await scrape_source(ctx, src)
            except Exception:
                certs, info = [], {"name": src["name"], "error": traceback.format_exc()[-800:]}
            # parser specifici (API) se presenti
            parser = src.get("parser")
            if parser:
                try:
                    mod = __import__("parsers", fromlist=[parser])
                    extra = getattr(mod, parser)(DISC, src, NOW)
                    info["from_parser"] = len(extra)
                    certs += extra
                except Exception:
                    info["parser_error"] = traceback.format_exc()[-800:]
            info["certs"] = len({c["isin"] for c in certs})
            print(f"[{src['name']}] {info.get('certs')} certificati · {info.get('clicks', 0)} click · {info.get('secs')}s · errore={info.get('error', '-')}", flush=True)
            report.append(info)
            found += certs
        await browser.close()
    certs = merge(old, found)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({"updatedAt": NOW, "count": len(certs),
                                "sources": [{"name": r["name"], "certs": r.get("certs", 0)} for r in report],
                                "certs": certs}, ensure_ascii=False, separators=(",", ":")))
    (DISC / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"TOTALE in archivio: {len(certs)}")


if __name__ == "__main__":
    asyncio.run(main())
