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
- `history/` storico prezzi per ISIN + `_first_seen.json` (non pubblicato).
- `.github/workflows/scrape.yml` robot (09:35 e 16:15 Roma, + recuperi; GitHub ritarda anche di 6 ore);
  `diagnosi.yml` controlla dominio/sito. `cron/worker.js` orologio Cloudflare pronto ma NON attivo
  (serve un token GitHub dell'utente).

## Lavorare risparmiando contesto
- Non rileggere file interi: usa grep e sed -n su righe mirate; `index.html` è ~2000 righe.
- Log di GitHub Actions: chiedi poche righe (tail_lines piccolo) o salva su file e filtra con python.
- Prove del sito: `python3 -m http.server 8797` in `docs/` e script Playwright nella scratchpad;
  guarda solo le schermate necessarie.
- Commit diretti su main, messaggi in italiano con le righe Co-Authored-By/Claude-Session previste.
