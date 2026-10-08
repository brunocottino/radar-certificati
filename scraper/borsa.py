"""Calendario di Borsa Italiana: dice se oggi (ora di Roma) il mercato è aperto.

Uso nel workflow: `python scraper/borsa.py` scrive open=true|false in $GITHUB_OUTPUT.
Uso da riga di comando: `python scraper/borsa.py 2026-04-03` stampa il risultato per quella data.
"""
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def pasqua(y):
    """Domenica di Pasqua (calendario gregoriano, algoritmo di Meeus/Jones/Butcher)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = (h + l - 7 * m + 114) % 31 + 1
    return date(y, mese, giorno)


def chiusure(y):
    p = pasqua(y)
    return {
        date(y, 1, 1): "Capodanno",
        p - timedelta(days=2): "Venerdì Santo",
        p + timedelta(days=1): "Lunedì dell'Angelo",
        date(y, 5, 1): "Festa del Lavoro",
        date(y, 8, 15): "Ferragosto",
        date(y, 12, 24): "Vigilia di Natale",
        date(y, 12, 25): "Natale",
        date(y, 12, 26): "Santo Stefano",
        date(y, 12, 31): "San Silvestro",
    }


def stato(d):
    if d.weekday() >= 5:
        return False, "weekend"
    motivo = chiusure(d.year).get(d)
    return (False, motivo) if motivo else (True, "aperta")


if __name__ == "__main__":
    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(ZoneInfo("Europe/Rome")).date()
    aperta, motivo = stato(d)
    print(f"Borsa Italiana {d.isoformat()}: {'aperta' if aperta else 'chiusa (' + motivo + ')'}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"open={'true' if aperta else 'false'}\n")
