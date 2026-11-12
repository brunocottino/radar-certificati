# Radar Certificati — note per Claude

Rispondi in italiano, breve. L'utente non vuole fare passaggi tecnici: fai tu, chiedi solo se indispensabile.
Niente token/routine di Claude per pianificare il robot. Non usare certificatiederivati.it. Niente Netlify.

## Struttura
- `docs/` sito statico (Cloudflare Worker `radar-certificati`, config `wrangler.jsonc`, deploy a ogni push su main).
  Domini: radarcertificati.com, www.radarcertificati.com, radar-certificati.cottinob.workers.dev.
  Tutto il JS/CSS è in `docs/index.html` (IIFE vanilla). Dopo ogni modifica: alza `CACHE` in `docs/sw.js`
  e verifica la sintassi estraendo lo script più lungo e `node --check`.
- `scraper/` robot Python: `run.py` (sorgenti, merge, controlli di plausibilità), `parsers.py` (emittenti),
  `risk.py` (volatilità, distanze, probabilità), `api.py` (lista, API, storico), `sectors.py` (settori).
- Motori di ricerca e IA: `worker/index.js` (main in `wrangler.jsonc`) crea al volo `/certificato/<ISIN>`;
  `scraper/seo.py` (+ testi in `guida.py`) scrive `docs/certificati/`, `guida-certificati.html`, `sitemap.xml`, `llms.txt`;
  `scraper/indexnow.py` segnala le pagine a Bing & co. (chiave in `docs/<chiave>.txt`).
  `seo.py` scrive anche `note-legali.html` e `metodologia.html`, le liste (sotto la pari, barriera bassa, in scadenza, calendario cedole)
  e le raccolte tipologia × emittente; ogni pagina porta l'avvertenza `WARN` («non è una raccomandazione»): non toglierla e non usare
  parole da consiglio (es. «scelte», «da comprare»). Indirizzo unico: il worker rimanda www al dominio principale e mette noindex
  su workers.dev (`run_worker_first` in `wrangler.jsonc`: il worker passa per primo sulle pagine, non su /api, /data, /fonts).
- `history/` storico prezzi per ISIN + `_first_seen.json` (non pubblicato).
- `.github/workflows/scrape.yml` robot (09:35 e 16:15 Roma, + recuperi; GitHub ritarda anche di 6 ore);
  `diagnosi.yml` controlla dominio/sito. orologio Cloudflare in `worker/index.js` (scheduled, crons in `wrangler.jsonc`):
  funziona solo con il segreto GH_TOKEN nel Worker `radar-certificati` (token GitHub dell'utente, Actions: write).
  Il segreto oggi manca (/api/orologio → chiave:false): il ripiego è `sentinella.yml`, workflow sempre acceso che
  si riavvia da solo ogni ~5h50 e avvia il robot nelle finestre se la fascia non è pubblicata (nessun token).

## Lavorare risparmiando contesto
- Non rileggere file interi: usa grep e sed -n su righe mirate; `index.html` è ~2000 righe.
- Log di GitHub Actions: chiedi poche righe (tail_lines piccolo) o salva su file e filtra con python.
- Prove del sito: `python3 -m http.server 8797` in `docs/` e script Playwright nella scratchpad;
  guarda solo le schermate necessarie.
- Commit diretti su main, messaggi in italiano con le righe Co-Authored-By/Claude-Session previste.
