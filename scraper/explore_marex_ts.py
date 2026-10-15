"""Esplorazione: scarica i term sheet Marex di alcuni ISIN in explore/<ISIN>.pdf e il testo pdftotext."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright

OUT = Path("explore")
OUT.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as p:
        req = await p.request.new_context()
        for isin in sys.argv[1:]:
            d = json.loads(await (await req.get(f"https://fp.marex.com/api/{isin}")).text())
            docs = [x for x in d.get("documents") or [] if (x.get("fileName") or "").startswith("TS-")]
            (OUT / f"{isin}_api.json").write_text(json.dumps(d, indent=1))
            if not docs:
                continue
            doc = max(docs, key=lambda x: x["id"])
            body = await (await req.get(f"https://fp.marex.com/file/{isin}/{doc['id']}/{quote(doc['fileName'])}")).body()
            (OUT / f"{isin}.pdf").write_bytes(body)
            try:
                txt = subprocess.run(["pdftotext", "-layout", str(OUT / f"{isin}.pdf"), "-"], capture_output=True, text=True).stdout
                (OUT / f"{isin}.txt").write_text(txt)
            except Exception as e:
                print(isin, e)
            print(isin, len(body), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
