# Radar Certificati

Screener di certificati a cedola (softcallable/autocall, worst-of) quotati in Italia ed Europa.

- `scraper/` robot Playwright che legge liste prodotti e API interne degli emittenti
- `.github/workflows/scrape.yml` esecuzione automatica + avvio manuale
- `docs/` sito statico (GitHub Pages) che legge `docs/data/certs.json`; installabile come app (manifest + service worker)

## Orari

Il workflow gira dal lunedì al venerdì alle **09:35** e alle **16:15** ora di Roma (Europe/Rome), sia con l'ora legale
sia con l'ora solare, solo nei giorni di borsa. GitHub usa l'UTC, quindi ogni orario ha due cron:

| Cron (UTC) | Ora legale (+0200) | Ora solare (+0100) |
|---|---|---|
| `35 7,8 * * 1-5` | 07:35 UTC = 09:35 | 08:35 UTC = 09:35 |
| `15 14,15 * * 1-5` | 14:15 UTC = 16:15 | 15:15 UTC = 16:15 |

Il primo step ("Orario di Roma") legge da `github.event.schedule` quale cron è partito e da `TZ=Europe/Rome date +%z`
il fuso del giorno: la run prosegue solo se l'orario UTC giusto per quel fuso è già passato e la fascia di oggi non è
ancora stata pubblicata (il commit dei dati di una run programmata si chiama `Dati certificati <data> 09:35` o `… 16:15`).
Così l'occorrenza dell'altro fuso salta, un ritardo di GitHub non fa perdere la run giusta e non ci sono doppioni.
GitHub però ritarda di ore o salta del tutto le run programmate (il 16/10 sono partite con 5 ore di ritardo, il 19/10
nessuna): per questo ci sono anche cron di recupero, `5 9,10,11 * * 1-5` per la fascia delle 09:35 e `50 14,15,16 * * 1-5`
per quella delle 16:15. Se la fascia è già pubblicata si fermano al primo step; altrimenti la recuperano.
Poi `scraper/borsa.py` salta i giorni di chiusura di Borsa Italiana (1/1, Venerdì Santo, Lunedì dell'Angelo, 1/5,
15/8, 24/12, 25/12, 26/12, 31/12). Le run manuali partono sempre, senza controlli d'orario.

## Prezzi

Denaro e lettera si aggiornano solo in coppia. Se una run non li trova, restano i prezzi precedenti e
`priceAt` indica quando sono stati rilevati; il sito li evidenzia in arancione dopo 2 giorni lavorativi.

## Esplorazione (debug)

La cartella `discovery/` (HTML, risposte JSON, log dei parser) è sempre allegata alla run come artifact.
Il branch `discovery` viene aggiornato solo lanciando il workflow a mano con `debug = true`.

## Sorgenti

| Sorgente | Come |
|---|---|
| **Euronext** (elenco completo) | `scraper/euronext.py`: la directory prodotti di live.euronext.com (Euronext è proprietaria di Borsa Italiana) espone in JSON paginato tutti gli strumenti di SeDeX e Cert-X: `POST /it/product_directory/data/warrants-milan?mics=ETLX,SEDX` (parametri DataTables `start`/`length`, 500 righe per pagina, 4 pagine in parallelo con 3 tentativi ciascuna). Ogni riga ha ISIN, mercato, simbolo, codice emittente, sottostante, tipologia di borsa, strike, scadenza, **denaro/lettera**. A ottobre 2026: 42.394 strumenti, di cui 29.031 a leva (in `docs/data/leva.json`, caricati dal sito solo su richiesta) e 13.363 d'investimento. Emittente, sottostanti, scadenza e link valgono solo dove l'archivio non ha già i dati più ricchi delle API degli emittenti. Funziona; la ricerca avanzata di Borsa Italiana invece non espone un elenco interrogabile (moduli senza risultati JSON) |
| Vontobel | tabelle HTML delle liste prodotti (cash collect, multi cash collect, express, bonus cap, fixed cash collect, phoenix) |
| Leonteq | API `product-model/search` paginata; `issuer` = emittente reale, `platform` = "Leonteq". Il sito è protetto da Incapsula, che blocca spesso i runner GitHub: al massimo una ricerca completa al giorno (`scraper/leonteq_state.json`), pause di 2,5-5 s tra le pagine; se bloccata restano i dati dell'ultima ricerca riuscita e la sorgente risulta "bloccata" |
| BNP Paribas | API `productlist` paginata, tutto il gruppo investimento (cash collect, phoenix, express, bonus cap, protetti) |
| UniCredit (onemarkets) | tabella paginata |
| Vontobel (`vontobel_dettaglio`) | le liste e il CSV ufficiale (`/cms/productdownload/export_it-it-csv`) coprono solo i ~590 prodotti in vetrina; centinaia di Vontobel quotati arrivano solo da Euronext. La pagina prodotto (`/it-it/prodotti/investment/<categoria qualsiasi>/<ISIN>`) contiene in `__NEXT_DATA__` cedola p.a., e per ogni sottostante strike, barriera %, trigger cedola e livello autocall con le date: stessa rotazione, 6 minuti per run (`scraper/vontobel_detail_state.json`) |
| Marex (`marex_dettaglio`) | Marex non pubblica dati, solo documenti: `fp.marex.com/api/<ISIN>` elenca i file, il term sheet `TS-<ISIN>-…PDF` (testo con `pdftotext -layout`) ha nominale, sottostanti con strike e barriera %, tabella cedole (barriera cedola, tasso per periodo, date) e autocall. Per gli Express senza cedola: premio di rimborso anticipato annualizzato. Le distanze le calcola `risk.py` da strike e chiusure. Rotazione, 6 minuti per run, rilettura dopo 30 giorni |
| Intesa Sanpaolo (`intesa_dettaglio`) | GET pubblica `rest/public/title/dossierbystock?isin=` di prodottiequotazioni.intesasanpaolo.com: premio per periodo e frequenza (→ cedola p.a.), barriera, strike e distanze dei sottostanti, autocall, scadenza. Stessa rotazione, 5 minuti per run |
| BNP Paribas (`bnp_dettaglio`) | per i certificati BNP che arrivano solo da Euronext: GET pubbliche per ISIN `apiv2/api/v1/product/keyvaluerow/<ISIN>` (cedola p.a., barriera, trigger, memoria, frequenza) e `underlyingbasket/<ISIN>` (sottostanti con strike e distanze). A rotazione, 4 richieste in parallelo, 8 minuti per run, prima i certificati senza cedola; ogni ISIN si rilegge dopo 7 giorni (`scraper/bnp_detail_state.json`) |
| Société Générale | API `EmcWebApi/api/ProductSearch`: classificazioni → GridConfig → `Search` in GET (`ProductClassificationId`, `PageNum`) dopo l'avviso di residenza, più dettaglio `Products/{isin}`. Funziona dal 3° tentativo; il listino quotato di SG ha solo la classe "Cash Collect Worst-Of" (27 prodotti a ottobre 2026) |
| Citigroup | API pubblica CitiFirst (`citivelocity.com/rcs/eppublic/v1/content/citifirst/product?...country=it`, senza parametri di paginazione): cedola (campo `manualField` o "Cpn: x%" nel nome), frequenza dal calendario dei richiami, barriera, strike dei sottostanti, prossimo richiamo, memoria. Le distanze si ricalcolano da strike e chiusure (`risk.py`), solo se strike e chiusura sono confrontabili |
| Borsa Italiana (`borsa_scheda`) | schede per ISIN (`/scheda/<ISIN>-SEDX.html`, Cert-X `/eurotlx/scheda/<ISIN>-ETLX.html`) per i certificati ancora senza barriera: barriera capitale %, emittente (sostituisce i codici Euronext ignoti), nome commerciale (memoria), sottostanti. Niente cedola: le schede non la riportano. A rotazione, 1 richiesta/s, 5 minuti per run (~280 schede), prima cash collect/phoenix poi express; ripresa da `scraper/scheda_state.json` |

### Orologio Cloudflare (avvio puntuale)

GitHub ritarda di ore o salta le run programmate (il 26/10 nessuna delle 5 del mattino è partita). Un piccolo Worker
Cloudflare (`cron/worker.js`, piano gratuito) avvia il workflow alle 09:35 e 16:15 di Roma con l'input `auto`:
la run salta da sola se la fascia è già pubblicata o la borsa è chiusa. I cron di GitHub restano come riserva.
Configurazione: Worker con il codice di `cron/worker.js`, Cron Triggers `35,40 7,8 * * 1-5` e `15,20 14,15 * * 1-5`,
segreto `GH_TOKEN` (token GitHub fine-grained, solo questo repository, permesso Actions: Read and write).

### Verifica

L'ultimo step controlla che entro 5 minuti dal push il sito (`radar-certificati.cottinob.workers.dev`, dove il robot
pubblica i dati) serva il nuovo `updatedAt`, altrimenti la run fallisce.

Indirizzo pubblico: **https://radarcertificati.com** (dominio Cloudflare collegato allo stesso Worker; l'indirizzo
`workers.dev` resta attivo e il controllo usa quello, che non dipende dal DNS).

Il repository è privato: GitHub Actions ha 2.000 minuti gratuiti al mese e ogni run ne usa 15-45.

## API

API JSON pubblica, in sola lettura, con CORS aperto (`Access-Control-Allow-Origin: *`), rigenerata a ogni run.
Base: `https://radarcertificati.com/api/v1/`

| Indirizzo | Contenuto |
|---|---|
| `certificates.json` | `{version, updatedAt, count, disclaimer, certificates: [...]}`: tutti i certificati con tutti i campi |
| `isin/<gg>.json` | i certificati del gruppo `gg` con lo storico prezzi: `{version, updatedAt, disclaimer, certificates: {ISIN: {certificate, history}}}`. Il gruppo è FNV-1a a 32 bit dell'ISIN modulo 256, in esadecimale a due cifre (vedi `isin_bucket` qui sotto): 256 file invece di uno per ISIN, così ogni pubblicazione resta leggera |
| `underlyings.json` | sottostanti con ticker Yahoo, `vol1y`, `vol3m`, `volUsed`, data di aggiornamento |
| `meta.json` | totali per emittente, orari delle run, metodologia del modello |
| `schema.json` | descrizione in italiano di ogni campo |

```js
const BASE = "https://radarcertificati.com/api/v1/";
const { certificates } = await fetch(BASE + "certificates.json").then(r => r.json());
const solidi = certificates.filter(c => c.probBarrierHold >= 0.85 && c.probMethod !== "solo_peggiore");
const isin_bucket = s => { let h = 0x811c9dc5; for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0; return (h % 256).toString(16).padStart(2, "0"); };
const gruppo = await fetch(BASE + `isin/${isin_bucket("DE000BD0HR17")}.json`).then(r => r.json());
const uno = gruppo.certificates["DE000BD0HR17"];  // {certificate, history}
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
- Il prezzo non serve al calcolo: la probabilità si calcola per ogni certificato con distanza, scadenza e volatilità.
- `probMethod`: `mc_europea`, `mc_continua`, `solo_peggiore` (nota solo la distanza del peggiore → limite superiore).

**Limiti del modello.** Volatilità storica (non implicita), rendimenti normali senza salti né code grasse, nessun richiamo
anticipato (se il certificato viene richiamato prima, la barriera conta meno), nessun rischio emittente né effetto cambio.
Barriera di tipo non dichiarato trattata come barriera a scadenza. Con barriera continua i passi giornalieri guardano solo le
chiusure. Correlazione non disponibile = 0. Le probabilità sono stime statistiche, non previsioni né consulenza.

## Punteggio e ricerca (sito)

Il sito calcola nel browser, per ogni certificato:

- **Rendimento annuo** (la soglia dei profili): cedole annue più la differenza tra rimborso (100) e prezzo lettera,
  divisa per gli anni residui (almeno 3 mesi), il tutto sul prezzo lettera. Sotto barriera il rimborso è stimato al livello
  attuale del peggiore (o nessun recupero, se il livello non è noto). Oltre il 40% è segnalato con "!": il mercato prezza una
  perdita probabile.
- **Rendimento atteso**: `P(tenuta) × rendimento se tiene + (1 − P) × rendimento se si rompe` (rimborso ≈ 85% del livello
  barriera, metà delle cedole, perdita spalmata su almeno un anno). Informativo, non filtra di default.
- **Margine in dev. std**: distanza del worst-of dalla barriera divisa per volatilità × √anni residui.
- **Punteggio 0-100**: media pesata di Rendimento annuo (pieno a 14% prudente, 20% bilanciato, 28% aggressivo),
  Sicurezza del peggiore (probabilità e distanza), Affidabilità cedola (distanza dal trigger), Liquidità (spread, prezzo
  aggiornato) e Qualità (classe A/B/C indicativa dell'emittente, memoria, dati completi). Sotto barriera ×0,35, cedola sospesa ×0,8.
- **Profili** (i dati mancanti non escludono, salvo la cedola, necessaria per il rendimento):

| Profilo | Rend. annuo | Dist. barriera | Prob. tenuta | Trigger | Scadenza | Spread |
|---|---|---|---|---|---|---|
| Prudente | 8-25% | ≥ 35% | ≥ 75% | ≥ 5% | ≤ 5 anni | ≤ 2% |
| Bilanciato | 12-35% | ≥ 25% | ≥ 50% | — | ≤ 6 anni | ≤ 3% |
| Aggressivo | 16-50% | ≥ 15% | — | — | ≤ 8 anni | ≤ 4% |

- **Obiettivi rapidi**: rendita mensile, sotto la pari, scadenza breve, memoria, cedola in pagamento, peggiore lontano.
- I prezzi anomali (< 1 o > 300% del nominale) sono esclusi; il robot scarta anche le lettere oltre 5 volte il nominale.

## Il sito

### Il mio portafoglio e analisi globale

Nella pagina Portafoglio, oltre al costruttore automatico, "Il mio portafoglio": certificati scelti a mano (dalla scheda
con "+ Portafoglio" o cercandoli nella pagina) con l'importo di ciascuno, salvati nel browser. Per entrambe le modalità:
- correlazione tra i certificati (rendimenti settimanali medi dei loro sottostanti, ultimo anno), correlazione media,
  numero effettivo di scommesse indipendenti, sottostanti in comune;
- simulazione congiunta (3.000 scenari): sottostanti con volatilità storica e correlazioni stimate, esito di ogni
  certificato alla sua scadenza (barriera a scadenza, niente richiamo, cedole intere se la barriera tiene e per metà se
  si rompe, rimborso pari al peggiore): probabilità che nessuna barriera si rompa (confrontata con il calcolo
  indipendente), barriere rotte in media, esito mediano, scenario sfavorevole (5° percentile), probabilità di perdita.
I rendimenti settimanali vengono da `docs/data/returns.json`, scritto da `risk.py` a ogni run dalla cache dei prezzi.

### Settori

Ogni sottostante ha un settore (`scraper/sectors.py`): Banche, Assicurazioni, Finanza, Tecnologia, Telecom e media, Energia,
Utility, Auto, Industria e difesa, Trasporti e turismo, Consumi e lusso, Salute, Materie prime, Immobiliare, Crypto, Indici,
Tassi e credito, Valute. Prima le regole sul nome (indici settoriali come EURO STOXX Banks, società note, tassi, valute),
poi il settore e l'industria Yahoo del ticker (`risk.py` li raccoglie per i titoli che le regole non riconoscono, 80 per run).
Il certificato prende il settore comune a tutti i sottostanti, altrimenti è "Misto" (con la composizione).
Sul sito: etichetta su schede e dettaglio, colonna in tabella, filtro "Settore" (più settori insieme = panieri fatti solo di
quei settori; "Misto" = tutti i misti), ricerca per parola (banche, tech, lusso, difesa, oro...: trova anche i misti che li
contengono), esposizione per settore nel Portafoglio, colonna nell'Excel.

- **Profili** a un tocco (prudente, bilanciato, aggressivo) e **filtri a tocchi** (rendimento, distanza, probabilità, spread,
  scadenza, frequenza, caratteristiche); "Altri filtri" per i valori esatti.
- **Tabella** (desktop), **Schede** e **Mappa**. La Mappa è un grafico a dispersione: distanza del peggiore dalla barriera
  in orizzontale, rendimento annuo in verticale, colore = probabilità di tenuta; in grigio il resto del mercato, tratteggiata la
  zona dei filtri, in oro la **frontiera efficiente** (i certificati che nessun altro risultato batte insieme su rendimento e
  distanza), elencata sotto il grafico. La frontiera è anche un filtro ("Frontiera efficiente") e un'etichetta sulle schede.
- **Portafoglio**: sceglie N certificati dai risultati o dai preferiti (per punteggio, cedola e distanza, rendimento o
  probabilità), con un massimo per emittente e senza ripetere lo stesso sottostante, capitale in parti uguali; mostra
  investito, rendimento medio, cedole annue e mensili, peggiore più vicino, probabilità media e congiunta (se indipendenti),
  costo dello spread, calendario delle cedole a 12 mesi, esposizione per emittente e sottostante; esporta in Excel.
- Scheda certificato con quattro numeri chiave, scenari, motivazione del punteggio, distanze per sottostante e storico prezzo;
  preferiti con avvisi, confronto fino a 4, esportazione in Excel. Sul telefono: barra in basso (Risultati, Mappa, Filtri,
  Preferiti, Portafoglio).

## Note

- Il sito è pubblico e indicizzabile; `docs/_headers` (Cloudflare) tiene fuori dai motori di ricerca solo i file
  dati (`data/`, `api/`) e imposta la cache breve dei dati. Nessun cookie né tracciamento: caratteri serviti dal sito,
  libreria Excel scaricata solo all'esportazione. Note legali e fonti in fondo alla pagina.

Dati indicativi raccolti da fonti pubbliche: verificare sempre KID e term sheet dell'emittente.
