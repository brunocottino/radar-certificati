# Radar Certificati

Screener di certificati a cedola (softcallable/autocall, worst-of) quotati in Italia ed Europa.

- `scraper/` robot Playwright che legge liste prodotti e API interne degli emittenti
- `.github/workflows/scrape.yml` esecuzione automatica + avvio manuale
- `docs/` sito statico (GitHub Pages) che legge `docs/data/certs.json`; installabile come app (manifest + service worker)

## Orari

Il workflow gira dal lunedì al venerdì alle 9:20 e 14:20 UTC, cioè a borsa aperta:
11:20 e 16:20 con l'ora legale, 10:20 e 15:20 con l'ora solare.
Il primo step (`scraper/borsa.py`) salta le run programmate nei giorni di chiusura di Borsa Italiana
(1/1, Venerdì Santo, Lunedì dell'Angelo, 1/5, 15/8, 24/12, 25/12, 26/12, 31/12). Le run manuali girano sempre.

## Prezzi

Denaro e lettera si aggiornano solo in coppia. Se una run non li trova, restano i prezzi precedenti e
`priceAt` indica quando sono stati rilevati; il sito li evidenzia in arancione dopo 2 giorni lavorativi.

## Esplorazione (debug)

La cartella `discovery/` (HTML, risposte JSON, log dei parser) è sempre allegata alla run come artifact.
Il branch `discovery` viene aggiornato solo lanciando il workflow a mano con `debug = true`.

## Sorgenti

| Sorgente | Come |
|---|---|
| Vontobel | tabelle HTML delle liste prodotti |
| Leonteq | API `product-model/search` paginata; `issuer` = emittente reale, `platform` = "Leonteq" |
| BNP Paribas | API `productlist` paginata |
| UniCredit (onemarkets) | tabella paginata |
| Société Générale | API `EmcWebApi/api/ProductSearch`: classificazioni → GridConfig → `Search` in GET (`ProductClassificationId`, `PageNum`) dopo l'avviso di residenza, più dettaglio `Products/{isin}`. Funziona dal 3° tentativo; il listino quotato di SG ha solo la classe "Cash Collect Worst-Of" (27 prodotti a ottobre 2026) |
| Marex | sonda, nessuna API trovata |

## Note

- `docs/_headers` (noindex, cache breve dei dati) vale su hosting che lo supporta (Netlify, Cloudflare Pages).
  GitHub Pages lo ignora: lì valgono il `<meta name="robots" content="noindex">` della pagina e la cache
  fissa di 10 minuti, aggirata dal sito con `?t=` sulla richiesta dei dati.

Dati indicativi raccolti da fonti pubbliche: verificare sempre KID e term sheet dell'emittente.
