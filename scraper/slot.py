"""Decide se una run programmata deve partire.

GitHub ritarda o salta i cron, quindi il workflow parte ogni ora e qui si sceglie:
la run va solo a borsa aperta (Borsa Italiana, ora di Roma) e se nella fascia corrente
(mattina 9:30-13:00, pomeriggio 14:30-17:20) non c'è ancora stata una pubblicazione di dati.
Uso: python scraper/slot.py <evento> <timestamp unix dell'ultima pubblicazione dati o 0>
Scrive open=true|false in $GITHUB_OUTPUT.
"""
import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

from borsa import stato

ROME = ZoneInfo("Europe/Rome")
SLOTS = [(time(9, 30), time(13, 0)), (time(14, 30), time(17, 20))]


def decide(event, last_ts, now=None):
    now = now or datetime.now(ROME)
    if event != "schedule":
        return True, "run manuale"
    aperta, motivo = stato(now.date())
    if not aperta:
        return False, f"borsa chiusa ({motivo})"
    for a, b in SLOTS:
        if a <= now.time() <= b:
            start = datetime.combine(now.date(), a, ROME)
            last = datetime.fromtimestamp(last_ts, ROME) if last_ts else None
            if last and last >= start:
                return False, f"fascia {a:%H:%M}-{b:%H:%M} già coperta ({last:%H:%M})"
            return True, f"fascia {a:%H:%M}-{b:%H:%M} da coprire"
    return False, "fuori dalle fasce di borsa"


if __name__ == "__main__":
    ok, why = decide(sys.argv[1], int(sys.argv[2] or 0))
    print(f"{'Parte' if ok else 'Salta'}: {why}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"open={'true' if ok else 'false'}\n")
