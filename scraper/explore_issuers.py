"""Esplorazione: dove trovare cedola, barriera e trigger dei certificati che oggi arrivano solo da Euronext.
BNP (API productlist e dettaglio), Société Générale (classi e Products/{isin}), liste Vontobel express,
pagine prodotto degli altri emittenti (con le risposte XHR). Tutto in explore/."""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright.async_api import async_playwright

import parsers
from explore_detail import visit

OUT = Path("explore")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
REP = {}


def dump(name, obj):
    (OUT / name).write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=1)[:4_000_000])


async def bnp(ctx):
    rep = REP.setdefault("bnp", {})
    page = await ctx.new_page()
    calls = []

    async def on_resp(r):
        if "/apiv2/" in r.url:
            try:
                calls.append({"url": r.url, "method": r.request.method, "post": r.request.post_data,
                              "headers": {k: v for k, v in (await r.request.all_headers()).items() if k.lower() != "cookie"},
                              "status": r.status, "body": (await r.text())[:30000]})
            except Exception:
                pass
    page.on("response", on_resp)
    await page.goto("https://investimenti.bnpparibas.it/product-details/XS2502585859/", wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_timeout(6000)
    await parsers.accept_cookies(page)
    await page.wait_for_timeout(6000)
    dump("bnp_detail_calls.json", calls)
    rep["detail_calls"] = [(c["method"], c["url"][:160], c["status"], len(c["body"])) for c in calls]
    # productlist: totali con filtri diversi
    hdr = {"content-type": "application/json", "accept": "application/json"}
    lst = next((c for c in calls if "productlist" in c["url"]), None)
    if lst:
        hdr = {k: v for k, v in lst["headers"].items() if not k.startswith(":") and k.lower() not in ("content-length", "host", "accept-encoding", "connection")}
    tot = {}
    for label, extra in (("g6_sets2223", {}), ("g6_allsets", {"productSetIds": []}), ("nogroup", {"productSetIds": [], "productGroupIds": []}),
                         ("flag0", {"productSetIds": [], "productFlagFilter": 0}), ("flag1", {"productSetIds": [], "productFlagFilter": 1})):
        body = {**parsers.BNP_BODY, **extra, "offset": 0, "limit": 5}
        st, txt = await parsers.fetch(page, parsers.BNP_API, "POST", json.dumps(body), hdr)
        try:
            d = json.loads(txt)
            tot[label] = {"status": st, "total": d.get("total"), "isins": [x.get("isin") for x in d.get("result") or []]}
            if label == "g6_allsets":
                dump("bnp_list_sample.json", d)
        except Exception:
            tot[label] = {"status": st, "txt": txt[:300]}
    rep["productlist_totals"] = tot
    # i 3 ISIN mancanti: compaiono nell'elenco completo?
    seen, off = set(), 0
    body = {**parsers.BNP_BODY, "productSetIds": [], "limit": 50}
    while off < 6000:
        st, txt = await parsers.fetch(page, parsers.BNP_API, "POST", json.dumps({**body, "offset": off}), hdr)
        if st != 200:
            rep["full_err"] = [off, st, txt[:200]]
            break
        res = json.loads(txt).get("result") or []
        if not res:
            break
        seen.update(x.get("isin") for x in res)
        off += len(res)
    rep["full_count"] = len(seen)
    rep["missing_in_full"] = {i: i in seen for i in ("XS2502585859", "XS3278063279", "XS3261346350")}
    await page.close()


async def socgen(ctx):
    rep = REP.setdefault("socgen", {})
    page = await ctx.new_page()
    await page.goto(parsers.SG + "/product-search", wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_timeout(4000)
    await parsers.accept_cookies(page)
    for _ in range(4):
        loc = page.get_by_role("button", name=re.compile(r"^\s*ok\s*$", re.I))
        try:
            if not await loc.count():
                break
            await loc.first.click(timeout=3000)
        except Exception:
            break
        await page.wait_for_timeout(3000)
    url, st, txt = await parsers.sg_get(page, "ProductClassificationsWithProductsCount")
    rep["classes_status"] = st
    try:
        rep["classes"] = parsers.sg_classes(json.loads(txt))
    except Exception as e:
        rep["classes_err"] = repr(e)
    dump("sg_classes.json", txt)
    for isin in ("XS2395098432", "XS2878491922", "XS2878555247"):
        st, txt = await parsers.fetch(page, parsers.SG_API.replace("ProductSearch/", "Products/") + isin, "GET", None, {"accept": "application/json"})
        rep[f"detail_{isin}"] = [st, len(txt)]
        dump(f"sg_detail_{isin}.json", txt)
    await page.close()


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await b.new_context(locale="it-IT", timezone_id="Europe/Rome", user_agent=UA, viewport={"width": 1440, "height": 1000})
        for fn in (bnp, socgen):
            try:
                await fn(ctx)
            except Exception as e:
                REP.setdefault(fn.__name__, {})["error"] = repr(e)[:500]
            print(fn.__name__, json.dumps(REP.get(fn.__name__), ensure_ascii=False)[:1500], flush=True)
        V = "https://markets.vontobel.com/it-it/prodotti/investment/"
        pages = {
            "vt_express": V + "express-certificate",
            "vt_multi_express": V + "multi-express-certificate",
            "vt_detail": "https://markets.vontobel.com/it-it/prodotti/investment/express-certificate/DE000VY27782",
            "medio": "https://www.mediobanca.com/it/prodotti-di-investimento/certificati.html",
            "medio_isin": "https://www.mediobanca.com/it/prodotti-di-investimento/certificati/scheda.html?isin=IT0005717027",
            "barclays": "https://www.investimenti.barclays.it/",
            "barclays_isin": "https://www.investimenti.barclays.it/prodotti/XS3188986858",
            "gs": "https://www.gsmarkets.it/it/prodotti/GB00BVJTWC03",
            "marex": "https://fp.marex.com/it/product/IT0006756727",
            "intesa": "https://www.intesasanpaolo.prodottiequotazioni.com/it/prodotti/dettaglio?isin=XS3212528692",
            "natixis": "https://equityderivatives.natixis.com/it/product/IT0006776402",
            "bpm": "https://www.bancobpm.it/certificati/IT0005712408",
            "ubs": "https://keyinvest-it.ubs.com/prodotto/detail/DE000WA197W1",
        }
        for name, url in pages.items():
            info = await visit(ctx, name, url)
            REP.setdefault("pages", {})[name] = {k: info.get(k) for k in ("status", "final_url", "error")} | {
                "key_lines": info.get("key_lines", [])[:40], "pairs": info.get("pairs", [])[:40],
                "xhr": [(x["method"], x["url"][:200], x["status"], x["len"]) for x in info.get("xhr", [])]}
            print(name, info.get("status"), info.get("final_url"), len(info.get("key_lines", [])), flush=True)
        await b.close()
    dump("issuers_report.json", REP)


if __name__ == "__main__":
    asyncio.run(main())
