"""Esplorazione: repository documenti Marex (fp.marex.com). Cerca un ISIN, salva chiamate XHR e link ai documenti."""
import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("explore")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


async def main():
    isins = sys.argv[1:] or ["IT0006756727"]
    rep = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(locale="it-IT", user_agent=UA)
        for isin in isins:
            page = await ctx.new_page()
            xhr = []

            async def on_resp(r):
                try:
                    if r.request.resource_type in ("xhr", "fetch", "document"):
                        t = await r.text() if "pdf" not in (r.headers.get("content-type") or "") else "<pdf>"
                        xhr.append({"url": r.url, "method": r.request.method, "post": r.request.post_data, "status": r.status,
                                    "ct": r.headers.get("content-type"), "body": t[:20000]})
                except Exception:
                    pass
            page.on("response", on_resp)
            info = {}
            try:
                await page.goto("https://fp.marex.com/it/", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)
                for lab in ("Accept", "Accetta", "Allow", "OK"):
                    bt = page.get_by_role("button", name=re.compile(lab, re.I))
                    if await bt.count():
                        try:
                            await bt.first.click(timeout=2000)
                        except Exception:
                            pass
                inp = page.locator("input").first
                await inp.fill(isin)
                await page.wait_for_timeout(800)
                await inp.press("Enter")
                await page.wait_for_timeout(2000)
                bt = page.get_by_text(re.compile("Find product", re.I))
                if await bt.count():
                    try:
                        await bt.first.click(timeout=3000)
                    except Exception:
                        pass
                await page.wait_for_timeout(8000)
                info["url"] = page.url
                info["text"] = re.sub(r"\s+", " ", await page.inner_text("body"))[:4000]
                info["links"] = await page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.innerText.trim().slice(0,80), a.href])")
            except Exception as e:
                info["error"] = repr(e)[:300]
            info["xhr"] = [(x["method"], x["url"][:300], x["status"], x["ct"], len(x["body"])) for x in xhr]
            for i, x in enumerate(xhr[:15]):
                (OUT / f"marex_{isin}_{i}.txt").write_text(f'{x["url"]}\n{x["post"]}\n{x["ct"]}\n\n{x["body"]}')
            rep[isin] = info
            await page.close()
        await b.close()
    (OUT / "marex_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
