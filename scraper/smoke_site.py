"""Prova del sito pubblicato con un browser vero: caricamento, ricerca, modalità ISIN, scheda, telefono.
Scrive smoke/report.json e alcune schermate."""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

SITE = sys.argv[1] if len(sys.argv) > 1 else "https://radar-certificati.cottinob.workers.dev/"
OUT = Path("smoke"); OUT.mkdir(exist_ok=True)


async def main():
    rep = {"site": SITE, "errors": []}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1400, "height": 950})
        pg.on("pageerror", lambda e: rep["errors"].append(str(e)))
        await pg.goto(SITE, wait_until="domcontentloaded")
        await pg.wait_for_selector("#vtb tr.r, .card", timeout=60000)
        rep["status"] = await pg.text_content("#status")
        rep["count_default"] = await pg.text_content("#count")
        rep["chips"] = await pg.locator("#chips .chip").all_text_contents()
        rep["banner"] = await pg.locator("#banner").is_visible()
        await pg.screenshot(path=str(OUT / "home.png"))
        await pg.fill("#q", "intesa enel")
        await pg.wait_for_timeout(1200)
        rep["count_intesa_enel"] = await pg.text_content("#count")
        first = await pg.evaluate("() => document.querySelector('#vtb tr.r, .card')?.dataset.open")
        await pg.fill("#q", first or "")
        await pg.wait_for_timeout(2500)
        rep["isin"] = first
        rep["isin_box"] = (await pg.text_content("#isinbox") or "")[:300]
        await pg.screenshot(path=str(OUT / "isin.png"))
        await pg.fill("#q", "IT0000000000")
        await pg.wait_for_timeout(800)
        rep["isin_absent"] = (await pg.text_content("#isinbox") or "").strip()[:200]
        await pg.fill("#q", "")
        await pg.wait_for_timeout(800)
        await pg.click("#reset")
        await pg.wait_for_timeout(800)
        rep["count_all"] = await pg.text_content("#count")
        await pg.select_option("#f-cat", "Leva") if await pg.locator("#f-cat option[value=Leva]").count() else None
        await pg.evaluate("() => { const c = document.querySelector('#f-lev'); c.checked = true; c.dispatchEvent(new Event('input', {bubbles: true})) }")
        await pg.wait_for_timeout(9000)
        rep["count_with_leva"] = await pg.text_content("#count")
        m = await b.new_page(viewport={"width": 390, "height": 844})
        await m.goto(SITE, wait_until="domcontentloaded")
        await m.wait_for_selector(".card", timeout=60000)
        rep["mobile_scroll_width"] = await m.evaluate("document.documentElement.scrollWidth")
        await m.screenshot(path=str(OUT / "mobile.png"))
        await b.close()
    (OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False, indent=1))


asyncio.run(main())
