"""Esplorazione: scarica URL con richieste HTTP semplici (niente JavaScript) dal contesto Playwright.
Uso: python scraper/explore_http.py nome=URL [nome=URL ...]  -> explore/<nome>.txt"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("explore")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


async def main():
    async with async_playwright() as p:
        req = await p.request.new_context(user_agent=UA, extra_http_headers={"Accept-Language": "it-IT,it;q=0.9"})
        for t in sys.argv[1:]:
            name, url = t.split("=", 1)
            try:
                r = await req.get(url, timeout=60000, max_redirects=0)
                body = await r.body()
                txt = body.decode("utf-8", "replace")
                if "charset=windows-1252" in txt[:3000].lower() or "iso-8859" in txt[:3000].lower():
                    txt = body.decode("cp1252", "replace")
                (OUT / f"{name}.txt").write_text(f"{url}\n{r.status} {dict(r.headers)}\n\n{txt}")
                print(name, r.status, len(body), flush=True)
            except Exception as e:
                print(name, "errore", repr(e)[:300], flush=True)
            await asyncio.sleep(1.5)


if __name__ == "__main__":
    asyncio.run(main())
