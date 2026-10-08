# Radar Certificati

Screener di certificati a cedola (softcallable/autocall, worst-of) quotati in Italia ed Europa.

- `scraper/` robot Playwright che ogni mattina legge le liste prodotti degli emittenti
- `.github/workflows/scrape.yml` esecuzione automatica nei giorni feriali + avvio manuale
- `docs/` sito statico (GitHub Pages) che legge `docs/data/certs.json`

Dati indicativi raccolti da fonti pubbliche: verificare sempre KID e term sheet dell'emittente.
