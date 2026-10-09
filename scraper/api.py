"""Radar Certificati - API JSON pubblica (file statici in docs/api/v1/), rigenerata a ogni run.

  certificates.json    tutti i certificati
  isin/<ISIN>.json     un file per certificato
  underlyings.json     sottostanti con ticker e volatilità
  meta.json            totali per emittente, orari, metodologia
  schema.json          descrizione dei campi
"""
import json
import os
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("RADAR_ROOT") or Path(__file__).resolve().parent.parent)
DATA = ROOT / "docs" / "data" / "certs.json"
MAP = ROOT / "scraper" / "underlyings_map.json"
STATE = ROOT / "scraper" / "risk_state.json"
OUT = ROOT / "docs" / "api" / "v1"
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")

DISCLAIMER = ("Dati indicativi raccolti da fonti pubbliche. Le probabilità sono stime statistiche basate su "
              "volatilità storica, non previsioni né consulenza. Verificare KID e term sheet.")

SCHEMA = {
    "isin": "Codice ISIN del certificato.",
    "issuer": "Emittente reale del certificato.",
    "platform": "Piattaforma di emissione/distribuzione, se diversa dall'emittente (es. Leonteq).",
    "source": "Sorgente interna da cui è stato raccolto il dato.",
    "type": "Tipo di prodotto dichiarato dall'emittente (es. Cash Collect, Phoenix Memory).",
    "underlyings": "Nomi dei sottostanti.",
    "underlyingsDetail": "Dettaglio per sottostante fornito dall'emittente: nome, strike, distanza dalla barriera in %, ISIN.",
    "worstName": "Sottostante peggiore (più vicino alla barriera), se indicato dall'emittente.",
    "couponPa": "Cedola potenziale annua in % del nominale.",
    "freq": "Frequenza della cedola: 1m mensile, 3m trimestrale, 6m semestrale, 12m annuale.",
    "distBarrier": "Distanza in % del sottostante peggiore dalla barriera capitale (negativa = sotto barriera).",
    "distAt": "Data dell'ultima distanza dalla barriera nota, quando non è aggiornata a ogni run (es. certificati con prezzo da Borsa Italiana).",
    "distSource": "Origine della distanza se ricalcolata (es. 'chiusure sottostanti': da strike, barriera e ultime chiusure).",
    "barrierPct": "Barriera capitale in % dello strike.",
    "barrierType": "Tipo di osservazione della barriera: 'scadenza' (solo a scadenza) o 'continua'. Assente se non noto.",
    "triggerPct": "Trigger della cedola in % dello strike.",
    "autocallPct": "Livello di richiamo anticipato in % dello strike.",
    "maturity": "Data di scadenza (YYYY-MM-DD).",
    "bid": "Prezzo denaro (stessa unità del nominale).",
    "ask": "Prezzo lettera (stessa unità del nominale).",
    "priceSource": "Origine di denaro/lettera se diversa dall'emittente (es. 'Borsa Italiana' per gli ISIN UniCredit senza prezzo su onemarkets).",
    "priceUrl": "Pagina da cui sono stati letti denaro/lettera, se diversa da url.",
    "priceAt": "Data e ora (UTC) dell'ultimo denaro/lettera validi.",
    "nominal": "Valore nominale (di solito 100 o 1000).",
    "currency": "Valuta del certificato.",
    "market": "Mercato di quotazione.",
    "callable": "Tipo di richiamo anticipato (es. Autocall, Softcallable).",
    "memory": "true se le cedole non pagate vengono recuperate (effetto memoria).",
    "nextCouponDate": "Prossima data di osservazione della cedola.",
    "nextCallDate": "Prossima data di possibile richiamo.",
    "url": "Pagina del prodotto sul sito dell'emittente.",
    "updatedAt": "Data e ora (UTC) dell'ultima rilevazione del certificato.",
    "probBarrierHold": "Probabilità stimata (0-1) che tutti i sottostanti restino sopra la barriera capitale fino a scadenza. Ignora il richiamo anticipato. null se mancano dati.",
    "probMethod": "Metodo: 'mc_europea' (barriera a scadenza, 20.000 scenari), 'mc_continua' (barriera continua, 5.000 scenari a passi giornalieri), 'solo_peggiore' (nota solo la distanza del peggiore: limite superiore della probabilità reale).",
    "probNote": "Nota sul calcolo, se presente (es. peggiore non identificato: usata la volatilità più alta).",
    "probHorizonYears": "Orizzonte della simulazione in anni (dalla data del calcolo alla scadenza).",
    "worstVol": "Volatilità annua usata per il sottostante peggiore (max tra 1 anno e 3 mesi).",
    "underlyingsRisk": "Per sottostante: nome, ticker Yahoo, vol1y, vol3m (annualizzate), distanza dalla barriera in % se nota.",
    "riskAt": "Data e ora (UTC) del calcolo di rischio.",
}

METHOD = {
    "volatilita": "Deviazione standard dei log-rendimenti giornalieri di chiusura × √252, su 1 anno (vol1y) e 3 mesi (vol3m). "
                  "Nel modello si usa volUsed = max(vol1y, vol3m), scelta prudente.",
    "correlazioni": "Correlazione a coppie dei log-rendimenti giornalieri sulle date comuni dell'ultimo anno. "
                    "Se la matrice non è definita positiva si usa la più vicina (autovalori tagliati). Correlazione non disponibile = 0 (prudente).",
    "modello": "Moti browniani geometrici correlati (Cholesky) con drift 0 sul prezzo; livello iniziale di ogni sottostante "
               "rispetto alla barriera = 1/(1 - distanza/100).",
    "barriera_a_scadenza": "20.000 scenari sul valore finale: la barriera tiene se tutti i sottostanti chiudono sopra la barriera a scadenza.",
    "barriera_continua": "5.000 scenari a passi giornalieri: la barriera tiene se nessun sottostante la tocca in nessuna chiusura.",
    "solo_peggiore": "Se l'emittente fornisce solo la distanza del peggiore, si simula solo quello: è un limite superiore della probabilità reale. "
                     "Se il peggiore non è identificato si usa la volatilità più alta tra i sottostanti.",
    "limiti": "Volatilità storica, rendimenti normali (niente salti né code grasse), nessun richiamo anticipato, nessun rischio emittente, "
              "nessun effetto cambio. Barriera di tipo non noto trattata come barriera a scadenza. Seed fisso per ISIN: numeri stabili tra run.",
    "aggiornamento": "Volatilità e correlazioni una volta al giorno (prima run); probabilità ricalcolate a ogni run con distanze e prezzi aggiornati.",
}


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def load(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def main():
    meta = json.loads(DATA.read_text())
    certs = sorted(meta["certs"], key=lambda c: c["isin"])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    updated = meta.get("updatedAt") or now

    shutil.rmtree(OUT, ignore_errors=True)
    dump(OUT / "certificates.json", {"version": 1, "updatedAt": updated, "count": len(certs),
                                     "disclaimer": DISCLAIMER, "certificates": certs})
    for c in certs:
        if ISIN_RE.match(c["isin"]):
            dump(OUT / "isin" / f"{c['isin']}.json", {"version": 1, "updatedAt": updated, "disclaimer": DISCLAIMER,
                                                      "certificate": c})

    m, st = load(MAP, {}), load(STATE, {})
    vols = st.get("underlyings", {})
    used = Counter(u["name"] for c in certs for u in c.get("underlyingsRisk") or [])
    unds = []
    for k, e in sorted(m.items()):
        t = e.get("manual") if e.get("manual") is not None else e.get("ticker")
        t = t if t and t != "-" else None
        v = vols.get(t) or {}
        unds.append({"name": e.get("name"), "isin": e.get("isin"), "ticker": t, "manual": e.get("manual") is not None,
                     "vol1y": v.get("vol1y"), "vol3m": v.get("vol3m"), "volUsed": v.get("volUsed"),
                     "lastClose": v.get("lastClose"), "lastDate": v.get("lastDate"), "updatedAt": v.get("updatedAt"),
                     "checkedAt": e.get("checkedAt")})
    dump(OUT / "underlyings.json", {"version": 1, "updatedAt": st.get("updatedAt"), "count": len(unds),
                                    "mapped": sum(1 for u in unds if u["ticker"]),
                                    "disclaimer": DISCLAIMER, "underlyings": unds})

    by = {}
    for c in certs:
        b = by.setdefault(c.get("issuer") or "n.d.", {"certificates": 0, "withPrice": 0, "withProbability": 0, "lastUpdate": None})
        b["certificates"] += 1
        b["withPrice"] += bool(c.get("bid") and c.get("ask"))
        b["withProbability"] += c.get("probBarrierHold") is not None
        if c.get("updatedAt") and (not b["lastUpdate"] or c["updatedAt"] > b["lastUpdate"]):
            b["lastUpdate"] = c["updatedAt"]
    dump(OUT / "meta.json", {
        "version": 1, "updatedAt": updated, "riskAt": meta.get("riskAt"), "generatedAt": now,
        "count": len(certs), "withProbability": sum(c.get("probBarrierHold") is not None for c in certs),
        "issuers": dict(sorted(by.items(), key=lambda x: -x[1]["certificates"])),
        "sources": meta.get("sources", []),
        "schedule": {"cron_utc": "20 9,14 * * 1-5",
                     "description": "Lun-ven alle 11:20 e 16:20 (ora legale) o 10:20 e 15:20 (ora solare), "
                                    "esclusi i giorni di chiusura di Borsa Italiana."},
        "methodology": METHOD,
        "endpoints": ["certificates.json", "isin/{ISIN}.json", "underlyings.json", "meta.json", "schema.json"],
        "disclaimer": DISCLAIMER,
    })
    dump(OUT / "schema.json", {"version": 1, "disclaimer": DISCLAIMER, "fields": SCHEMA})
    print(f"[api] {len(certs)} certificati, {len(unds)} sottostanti -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
