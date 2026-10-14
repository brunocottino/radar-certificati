"""Esplorazione: le schede per ISIN (live.euronext.com e Borsa Italiana) contengono i dati contrattuali
(barriera, cedola, trigger, date di osservazione)? Salva in explore/ testo, coppie etichetta/valore e
risposte XHR con quelle parole. Uso: python scraper/explore_detail.py ISIN-MIC [ISIN-MIC ...]"""
import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("explore")
OUT.mkdir(exist_ok=True)
KEY = re.compile(r"barri|cedol|coupon|trigger|osservaz|observ|autocall|strike|premio|memoria|memory|knock|rimbors|redemption", re.I)
PAIRS_JS = """() => { const o = [];
  for (const tr of document.querySelectorAll('tr')) { const c = [...tr.children].map(x => x.innerText.trim()).filter(Boolean); if (c.length >= 2) o.push(c.slice(0, 6)); }
  for (const dt of document.querySelectorAll('dt')) { const dd = dt.nextElementSibling; if (dd) o.push([dt.innerText.trim(), dd.innerText.trim()]); }
  return o.slice(0, 600); }"""


async def visit(ctx, name, url):
    page = await ctx.new_page()
    xhr = []

    async def on_resp(r):
        try:
            if r.request.resource_type in ("xhr", "fetch"):
                t = await r.text()
                if KEY.search(t) or re.search(r"[A-Z]{2}[A-Z0-9]{9}\d", t):
                    xhr.append({"url": r.url[:500], "method": r.request.method, "post": (r.request.post_data or "")[:1500],
                                "status": r.status, "len": len(t), "body": t[:60000]})
        except Exception:
            pass

    page.on("response", on_resp)
    info = {"name": name, "url": url}
    try:
        resp = await page.goto(url, wait_until="commit", timeout=90000)
        info["status"] = resp.status if resp else None
        await page.wait_for_timeout(9000)
        for lab in ("Accetta tutti", "Accept all", "Accetta", "Accept", "OK"):
            b = page.get_by_role("button", name=re.compile("^" + lab, re.I))
            if await b.count():
                try:
                    await b.first.click(timeout=2000)
                    await page.wait_for_timeout(2500)
                except Exception:
                    pass
                break
        # schede/tab con i dettagli
        for lab in ("Caratteristiche", "Dettagli", "Product information", "Informazioni", "Characteristics", "Scheda"):
            t = page.get_by_text(re.compile(lab, re.I))
            if await t.count():
                try:
                    await t.first.click(timeout=2000)
                    await page.wait_for_timeout(3000)
                except Exception:
                    pass
        info["final_url"] = page.url
        txt = await page.inner_text("body")
        info["key_lines"] = [l.strip() for l in txt.splitlines() if KEY.search(l)][:150]
        info["pairs"] = [p for p in await page.evaluate(PAIRS_JS) if KEY.search(" ".join(p))][:200]
        (OUT / f"{name}.html").write_text((await page.content())[:2_000_000])
    except Exception as e:
        info["error"] = repr(e)[:400]
    info["xhr"] = [{k: v for k, v in x.items() if k != "body"} for x in xhr[:30]]
    for i, x in enumerate(xhr[:8]):
        (OUT / f"{name}_xhr{i}.txt").write_text(x["url"] + "\n" + x["post"] + "\n\n" + x["body"])
    await page.close()
    return info


async def main():
    targets = sys.argv[1:]
    rep = []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(locale="it-IT", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
        for t in targets:
            if "=" in t:  # nome=URL qualsiasi
                name, url = t.split("=", 1)
                info = await visit(ctx, name, url)
                print(f"[{name}] status={info.get('status')} righe={len(info.get('key_lines', []))} coppie={len(info.get('pairs', []))} xhr={len(info['xhr'])} err={info.get('error', '-')}", flush=True)
                rep.append(info)
                await asyncio.sleep(1.5)
                continue
            isin, mic = t.split("-")
            for src, url in (("euronext", f"https://live.euronext.com/it/product/structured-products/{isin}-{mic}"),
                             ("borsa", f"https://www.borsaitaliana.it/borsa/cw-e-certificates/scheda/{isin}-{mic}.html?lang=it")):
                info = await visit(ctx, f"{src}_{isin}", url)
                print(f"[{src} {isin}] status={info.get('status')} righe={len(info.get('key_lines', []))} coppie={len(info.get('pairs', []))} xhr={len(info['xhr'])} err={info.get('error', '-')}", flush=True)
                rep.append(info)
                await asyncio.sleep(1.5)
        await b.close()
    (OUT / "detail_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
