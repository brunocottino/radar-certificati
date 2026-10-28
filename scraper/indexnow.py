"""Segnala ai motori di ricerca le pagine nuove o cambiate (protocollo IndexNow: Bing, Yandex, Seznam, Naver...).
Bing alimenta anche le ricerche di ChatGPT e Copilot. Nessun account: basta il file-chiave pubblicato in docs/.

Uso: python scraper/indexnow.py [--all]
  senza argomenti: home, guida, raccolte e schede dei certificati comparsi negli ultimi 3 giorni
  --all (o il lunedì mattina): tutte le pagine della sitemap
"""
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
HOST = "radarcertificati.com"
KEY = "f6edca7bde627e0e99f8b5d5929fbfc8"
NOW = datetime.now(ZoneInfo("Europe/Rome"))


def main():
    urls = re.findall(r"<loc>([^<]+)</loc>", (ROOT / "docs" / "sitemap.xml").read_text())
    full = "--all" in sys.argv or (NOW.weekday() == 0 and NOW.hour < 13)
    if not full:
        first = json.loads((ROOT / "history" / "_first_seen.json").read_text())
        since = (NOW.date() - timedelta(days=3)).isoformat()
        new = {i for i, d in first.items() if d >= since}
        urls = [u for u in urls if "/certificato/" not in u or u.rsplit("/", 1)[1] in new]
    print(f"[indexnow] {len(urls)} pagine ({'tutte' if full else 'nuove e raccolte'})")
    for i in range(0, len(urls), 10000):
        body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": urls[i:i + 10000]}).encode()
        req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(f"[indexnow] blocco {i // 10000 + 1}: HTTP {r.status}")
        except urllib.error.HTTPError as e:
            print(f"[indexnow] blocco {i // 10000 + 1}: HTTP {e.code} {e.read()[:200]!r}")


if __name__ == "__main__":
    main()
