"""Calendario di valutazione BNP Paribas (API v1/product/calendar/table/<ISIN>) -> richiami anticipati.

Ogni riga è una data di valutazione con le sue condizioni; quelle con isConditionEarlyRedeemable=true sono le date in cui
il certificato scade anticipatamente (livello nel testo: «≥ valore iniziale» = 100, «≥ 95 % val. iniz.» = 95).
L'etichetta «Rimborso anticipato: Automatico» di BNP non basta: molti Cash Collect la portano ma rimborsano solo a scadenza.
"""
import re


def level_of(text):
    t = text or ""
    m = re.search(r"≥\s*([\d.,]+)\s*%", t)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return 100.0 if re.search(r"≥\s*(valore|val\.)\s*iniz", t, re.I) else None


def call_info(cal, today):
    """cal = JSON della risposta. Restituisce None se il calendario non c'è, altrimenti
    {"callSchedule": [[data, livello]], "nextCallDate", "autocallPct", "nextCouponDate"}."""
    res = (cal or {}).get("result") or {}
    rows = res.get("observationDates")
    if not rows:
        return None
    sched = []
    for r in rows:
        d = (r.get("date") or "")[:10]
        lv = [level_of(c.get("conditionText")) for c in r.get("conditions") or [] if c.get("isConditionEarlyRedeemable")]
        if d and lv:
            # Step-Down: il livello non è nel testo, ma nella riga (observationTriggerLevel)
            lvl = next((x for x in lv if x is not None), None)
            if lvl is None and r.get("observationTriggerLevel") is not None:
                lvl = float(r["observationTriggerLevel"])
            sched.append([d, lvl])
    nxt = next((x for x in sched if x[0] >= today), None)
    return {"callSchedule": sched or None, "nextCallDate": nxt and nxt[0], "autocallPct": nxt and nxt[1],
            "nextObsDate": (res.get("nextObservationDate") or "")[:10] or None, "rows": len(rows)}
