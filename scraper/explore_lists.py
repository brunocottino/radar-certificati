"""Esplorazione: dove si trova un elenco completo e neutro degli ISIN quotati su SeDeX e Cert-X?

Apre le pagine candidate con Playwright, accetta i cookie, registra le chiamate XHR/fetch
con le risposte JSON o HTML che contengono ISIN, prova a paginare e salva tutto in explore/.
Non scrive dati del sito: serve solo a scegliere la fonte (vedi README, sezione Sorgenti).
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import accept_cookies  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "explore"
OUT.mkdir(exist_ok=True)
ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")

CANDIDATES = [
    ("bi_ricerca_sedex", "https://www.borsaitaliana.it/borsa/cw-e-certificates/ricerca-avanzata.html?lang=it"),
    ("bi_lista_sedex", "https://www.borsaitaliana.it/borsa/cw-e-certificates/lista.html?lang=it"),
    ("bi_certx", "https://www.borsaitaliana.it/borsa/cw-e-certificates/eurotlx/ricerca-avanzata.html?lang=it"),
    ("bi_home_cw", "https://www.borsaitaliana.it/borsa/cw-e-certificates/home.html?lang=it"),
    ("euronext_sp", "https://live.euronext.com/en/markets/milan/structured-products/list"),
    ("euronext_sp_it", "https://live.euronext.com/it/markets/milan/structured-products/list"),
    ("euronext_products", "https://live.euronext.com/en/products/structured-products"),
]


async def explore(ctx, name, url):
    page = await ctx.new_page()
    seen = []

    async def on_resp(r):
        try:
            if r.request.resource_type not in ("xhr", "fetch", "document"):
                return
            body = await r.text()
            n = len(set(ISIN.findall(body)))
            seen.append({"url": r.url[:600], "method": r.request.method, "status": r.status,
                         "post": (r.request.post_data or "")[:3000], "ct": r.headers.get("content-type", ""),
                         "len": len(body), "isins": n, "body": body[:200000] if n else body[:3000]})
        except Exception:
            pass

    page.on("response", on_resp)
    info = {"name": name, "url": url}
    t0 = time.time()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await accept_cookies(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        info["final_url"] = page.url
        info["title"] = await page.title()
        html = await page.content()
        info["isins_in_html"] = len(set(ISIN.findall(html)))
        (OUT / f"{name}.html").write_text(html[:3_000_000])
        # moduli e pulsanti: servono per capire filtri (emittente, tipologia) e paginazione
        info["forms"] = await page.evaluate("""() => [...document.querySelectorAll('select')].map(s => ({
            name: s.name || s.id, options: [...s.options].slice(0, 80).map(o => [o.value, o.text.trim()])})).slice(0, 20)""")
        info["buttons"] = await page.evaluate("""() => [...document.querySelectorAll('button,input[type=submit],a.btn,[role=button]')]
            .map(b => (b.innerText || b.value || '').trim()).filter(Boolean).slice(0, 60)""")
        info["links"] = await page.evaluate("""() => [...new Set([...document.querySelectorAll('a[href]').values()].map(a => a.href)
            .filter(h => /certif|cw-e|structured|lista|search|ricerca|page=|pagina/i.test(h)))].slice(0, 120)""")
        # prova a premere "cerca" se c'è
        for label in ("Cerca", "Search", "Mostra risultati", "Applica", "Filtra"):
            b = page.get_by_role("button", name=re.compile(label, re.I))
            if await b.count():
                try:
                    await b.first.click(timeout=4000)
                    await page.wait_for_timeout(5000)
                    info["clicked"] = label
                    html2 = await page.content()
                    info["isins_after_click"] = len(set(ISIN.findall(html2)))
                    (OUT / f"{name}_after.html").write_text(html2[:3_000_000])
                except Exception as e:
                    info["click_error"] = repr(e)[:200]
                break
    except Exception as e:
        info["error"] = repr(e)[:500]
    info["secs"] = round(time.time() - t0, 1)
    seen.sort(key=lambda x: -x["isins"])
    info["requests"] = [{k: v for k, v in s.items() if k != "body"} for s in seen[:40]]
    for i, s in enumerate(seen[:6]):
        if s["isins"] or "json" in s["ct"]:
            (OUT / f"{name}_resp{i}.txt").write_text(s["body"])
    await page.close()
    return info


async def main():
    only = set(sys.argv[1:])
    report = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(locale="it-IT", timezone_id="Europe/Rome", viewport={"width": 1440, "height": 1000},
                                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
        for name, url in CANDIDATES:
            if only and name not in only:
                continue
            info = await explore(ctx, name, url)
            print(f"[{name}] isin html={info.get('isins_in_html')} dopo click={info.get('isins_after_click')} "
                  f"max xhr={max([r['isins'] for r in info['requests']] or [0])} errore={info.get('error', '-')}", flush=True)
            report.append(info)
        await browser.close()
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
