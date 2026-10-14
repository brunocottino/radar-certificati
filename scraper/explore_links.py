"""Esplorazione: per ogni pagina salva i link interessanti (prodotti, certificati, ISIN) e le chiamate XHR/fetch.
Uso: python scraper/explore_links.py nome=URL [...] -> explore/links_report.json, explore/<nome>_xhrN.txt"""
import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("explore")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
INTEREST = re.compile(r"prodott|product|certific|isin|scheda|detail|dettagl|search|ricerca|[A-Z]{2}[A-Z0-9]{9}\d", re.I)
NOISE = re.compile(r"cookielaw|onetrust|google|doubleclick|facebook|hotjar|civiccomputing|acsbapp|analytics|\.css|\.woff|\.png|\.jpg|\.svg", re.I)


async def visit(ctx, name, url):
    page = await ctx.new_page()
    xhr = []

    async def on_resp(r):
        try:
            if r.request.resource_type in ("xhr", "fetch") and not NOISE.search(r.url):
                t = await r.text()
                xhr.append({"url": r.url, "method": r.request.method, "post": (r.request.post_data or "")[:800], "status": r.status, "len": len(t), "body": t[:40000]})
        except Exception:
            pass
    page.on("response", on_resp)
    info = {"url": url}
    try:
        resp = await page.goto(url, wait_until="commit", timeout=60000)
        info["status"] = resp.status if resp else None
        await page.wait_for_timeout(8000)
        for lab in ("Accetta tutti", "Accetta", "Accept all", "Accept", "OK", "Confermo", "Prosegui", "Continua"):
            b = page.get_by_role("button", name=re.compile("^\\s*" + lab, re.I))
            if await b.count():
                try:
                    await b.first.click(timeout=2000)
                    await page.wait_for_timeout(2500)
                except Exception:
                    pass
        await page.wait_for_timeout(5000)
        for _ in range(3):
            await page.mouse.wheel(0, 1500)
            await page.wait_for_timeout(1500)
        info["final_url"] = page.url
        info["title"] = await page.title()
        links = await page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.innerText.trim().slice(0,60), a.href])")
        info["links"] = [l for l in links if INTEREST.search(l[1]) or INTEREST.search(l[0])][:120]
        txt = await page.inner_text("body")
        info["text"] = re.sub(r"\s+", " ", txt)[:3000]
    except Exception as e:
        info["error"] = repr(e)[:300]
    info["xhr"] = [(x["method"], x["url"][:250], x["status"], x["len"]) for x in xhr[:40]]
    for i, x in enumerate(xhr[:12]):
        (OUT / f"{name}_xhr{i}.txt").write_text(x["url"] + "\n" + x["post"] + "\n\n" + x["body"])
    await page.close()
    return info


async def main():
    rep = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await b.new_context(locale="it-IT", timezone_id="Europe/Rome", user_agent=UA, viewport={"width": 1440, "height": 1000})
        for t in sys.argv[1:]:
            name, url = t.split("=", 1)
            rep[name] = await visit(ctx, name, url)
            print(name, rep[name].get("status"), rep[name].get("final_url"), len(rep[name].get("links", [])), len(rep[name]["xhr"]), flush=True)
            (OUT / "links_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
