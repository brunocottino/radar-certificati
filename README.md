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
| Borsa Italiana (`borsa_isin`) | complemento prezzi: per gli ISIN UniCredit in archivio ancora senza denaro e lettera, scheda pubblica di Borsa Italiana (`<ISIN>-SEDX`, poi `-ETLX`; ripiego Teleborsa). Playwright, 1 richiesta al secondo, prima le cedole mensili, al massimo 20 minuti per run; la run successiva riprende da dove si è fermata (`scraper/borsa_state.json`). Aggiorna solo denaro/lettera (`priceSource`, `priceUrl`) |
| Société Générale | API `EmcWebApi/api/ProductSearch`: classificazioni → GridConfig → `Search` in GET (`ProductClassificationId`, `PageNum`) dopo l'avviso di residenza, più dettaglio `Products/{isin}`. Funziona dal 3° tentativo; il listino quotato di SG ha solo la classe "Cash Collect Worst-Of" (27 prodotti a ottobre 2026) |
| Marex | sonda, nessuna API trovata |

## API

API JSON pubblica, in sola lettura, con CORS aperto (`Access-Control-Allow-Origin: *`), rigenerata a ogni run.
Base: `https://radar-certificati.cottinob.workers.dev/api/v1/`

| Indirizzo | Contenuto |
|---|---|
| `certificates.json` | `{version, updatedAt, count, disclaimer, certificates: [...]}`: tutti i certificati con tutti i campi |
| `isin/<ISIN>.json` | un certificato: `{version, updatedAt, disclaimer, certificate}` |
| `underlyings.json` | sottostanti con ticker Yahoo, `vol1y`, `vol3m`, `volUsed`, data di aggiornamento |
| `meta.json` | totali per emittente, orari delle run, metodologia del modello |
| `schema.json` | descrizione in italiano di ogni campo |

```js
const BASE = "https://radar-certificati.cottinob.workers.dev/api/v1/";
const { certificates } = await fetch(BASE + "certificates.json").then(r => r.json());
const solidi = certificates.filter(c => c.probBarrierHold >= 0.85 && c.probMethod !== "solo_peggiore");
const uno = await fetch(BASE + "isin/DE000BD0HR17.json").then(r => r.ok ? r.json() : null);
```

Cache: 5 minuti (`Cache-Control: public, max-age=300`). Gli header CORS sono in `docs/_headers`
(serviti dall'hosting Cloudflare; GitHub Pages li ignora). Ogni run verifica `meta.json` e scrive l'esito nel riepilogo della run.

### Volatilità e probabilità di tenuta barriera (`scraper/risk.py`)

- Sottostanti mappati a ticker Yahoo con la ricerca per ISIN (se l'emittente lo fornisce) o per nome: si accettano solo
  EQUITY/INDEX/ETF con nome simile (≥ 0,6). Mappa in `scraper/underlyings_map.json`; per correggere a mano scrivere il ticker
  nel campo `"manual"` (`"-"` = nessun ticker): non viene mai sovrascritto. I nomi senza ticker vengono ricercati di nuovo dopo 7 giorni.
- 1 anno di chiusure giornaliere (Yahoo, fallback stooq), cache in `data/prices/` (non pubblicata). `vol1y`, `vol3m` =
  dev. std. dei log-rendimenti × √252; nel modello `max(vol1y, vol3m)`. Correlazioni a coppie a date allineate.
  Solo nella prima run del giorno; le successive riusano `scraper/risk_state.json`.
- Monte Carlo a ogni run (le distanze cambiano): moti browniani geometrici correlati, drift 0, fino a scadenza.
  Barriera a scadenza: 20.000 scenari; barriera continua: 5.000 scenari a passi giornalieri. Seed fisso per ISIN.
- `probMethod`: `mc_europea`, `mc_continua`, `solo_peggiore` (nota solo la distanza del peggiore → limite superiore).

**Limiti del modello.** Volatilità storica (non implicita), rendimenti normali senza salti né code grasse, nessun richiamo
anticipato (se il certificato viene richiamato prima, la barriera conta meno), nessun rischio emittente né effetto cambio.
Barriera di tipo non dichiarato trattata come barriera a scadenza. Con barriera continua i passi giornalieri guardano solo le
chiusure. Correlazione non disponibile = 0. Le probabilità sono stime statistiche, non previsioni né consulenza.

## Note

- `docs/_headers` (noindex, cache breve dei dati) vale su hosting che lo supporta (Netlify, Cloudflare Pages).
  GitHub Pages lo ignora: lì valgono il `<meta name="robots" content="noindex">` della pagina e la cache
  fissa di 10 minuti, aggirata dal sito con `?t=` sulla richiesta dei dati.

Dati indicativi raccolti da fonti pubbliche: verificare sempre KID e term sheet dell'emittente.
