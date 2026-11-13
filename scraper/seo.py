"""Radar Certificati - pagine per i motori di ricerca e per le IA, rigenerate a ogni run dopo api.py.

  docs/certificati/<slug>.html   raccolte statiche: per emittente, sottostante, famiglia, settore, liste speciali
  docs/certificati/index.html    indice delle raccolte
  docs/certificati/hubs.json     mappa nome -> slug per i collegamenti nelle schede /certificato/<ISIN> (worker/index.js)
  docs/sitemap.xml               tutte le pagine, schede dei certificati comprese
  docs/llms.txt                  presentazione del sito per gli assistenti IA (standard llms.txt)

Le schede dei singoli certificati non sono file: le costruisce il worker da api/v1/isin/<gg>.json.
"""
import html
import json
import os
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("RADAR_ROOT") or Path(__file__).resolve().parent.parent)
DOCS = ROOT / "docs"
CERTS = DOCS / "api" / "v1" / "certificates.json"
FIRST = ROOT / "history" / "_first_seen.json"
OUT = DOCS / "certificati"
SITE = "https://radarcertificati.com"
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
TODAY = datetime.now(ZoneInfo("Europe/Rome")).date()
FREQ = {"1m": "mensile", "2m": "bimestrale", "3m": "trimestrale", "6m": "semestrale", "12m": "annuale"}
ROWS = 60
MIN_COMBO = 15  # raccolta emittente × tipologia solo con almeno 15 certificati
MESI = "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre".split()
MESE = f"{MESI[TODAY.month - 1]} {TODAY.year}"
OGGI = TODAY.strftime("%d/%m/%Y")
# Avvertenza mostrata in ogni raccolta: gli elenchi sono ordinamenti meccanici, non consigli.
WARN = ('<p class="warn"><b>Non è una raccomandazione.</b> Questo elenco è ordinato in modo automatico secondo il criterio indicato e non tiene conto '
        "della situazione di chi legge. I certificati sono strumenti complessi: si può perdere anche tutto il capitale investito. Prima di ogni decisione "
        'leggere KID e documentazione dell\'emittente. <a href="/note-legali">Avvertenze complete</a> · <a href="/metodologia">Come sono calcolati i dati</a></p>')
MIN_UND = 3  # raccolta per sottostante solo con almeno 3 certificati

# famiglie di prodotto: (nome, slug, regex su tipo/richiamo/tipologia di mercato). Un certificato può stare in più famiglie.
# Le regex sono usate anche dal worker (JavaScript): solo sintassi comune.
FAMILIES = [
    ("Cash Collect", "cash-collect", r"cash ?collect"),
    ("Phoenix", "phoenix", r"phoenix"),
    ("Express e Autocallable", "express-autocallable", r"express|autocall|athena"),
    ("Credit Linked", "credit-linked", r"credit ?linked"),
    ("a capitale protetto", "capitale-protetto", r"protect|protez|protett|garantit"),
    ("Bonus Cap", "bonus-cap", r"bonus"),
    ("Reverse Convertible", "reverse-convertible", r"reverse ?conv"),
    ("Discount", "discount", r"discount"),
    ("Twin Win", "twin-win", r"twin ?win"),
    ("Airbag", "airbag", r"airbag"),
    ("Digital", "digital", r"digital"),
    ("a leva (Turbo, Mini Future)", "leva", r"turbo|mini ?future|leva fissa|leverage|knock.?out"),
    ("Maxi Cash Collect", "maxi-cash-collect", r"maxi"),
    ("Low Barrier", "low-barrier", r"low ?barrier"),
    ("Fixed Cash Collect (cedola incondizionata)", "fixed-cash-collect", r"fixed"),
    ("Top Bonus", "top-bonus", r"top ?bonus"),
    ("Step Down", "step-down", r"step.?down"),
    ("Recovery", "recovery", r"recovery"),
    ("Outperformance", "outperformance", r"outperformance"),
    ("Tracker e Benchmark", "tracker-benchmark", r"tracker|benchmark"),
]
FAMILY_TEXT = {
    "cash-collect": "I Cash Collect pagano cedole periodiche condizionate: la cedola arriva se, alla data di osservazione, i sottostanti sono sopra il livello trigger. A scadenza il capitale è rimborsato se il sottostante peggiore è sopra la barriera.",
    "phoenix": "I Phoenix pagano cedole condizionate e possono essere rimborsati in anticipo (autocall); spesso hanno l'effetto memoria, che recupera le cedole non pagate.",
    "express-autocallable": "Gli Express e gli Autocallable puntano al rimborso anticipato: a ogni data di osservazione, se i sottostanti sono sopra il livello di richiamo, restituiscono il nominale più un premio.",
    "credit-linked": "I Credit Linked legano cedole e rimborso al merito di credito di uno o più enti di riferimento (società o Stati): se si verifica un evento di credito il rimborso può ridursi.",
    "capitale-protetto": "I certificati a capitale protetto (Equity Protection e simili) restituiscono a scadenza almeno la quota di nominale protetta, salvo default dell'emittente, partecipando in parte al rialzo del sottostante.",
    "bonus-cap": "I Bonus Cap pagano a scadenza un bonus prefissato se il sottostante non ha toccato la barriera, con guadagno massimo limitato dal cap.",
    "reverse-convertible": "I Reverse Convertible pagano cedole; a scadenza, se il sottostante è sotto la barriera o lo strike, il rimborso segue la performance del sottostante.",
    "discount": "I Discount si comprano a sconto rispetto al sottostante e rimborsano al massimo il cap: rendimento in cambio di un guadagno limitato.",
    "twin-win": "I Twin Win guadagnano sia dal rialzo sia da un ribasso contenuto del sottostante, purché non sia toccata la barriera.",
    "airbag": "Gli Airbag attenuano le perdite sotto la barriera grazie a un fattore di rimborso più favorevole.",
    "digital": "I Digital pagano una cedola fissa se il sottostante rispetta una condizione alla data di osservazione, spesso con protezione del capitale.",
    "leva": "I certificati a leva amplificano i movimenti del sottostante e possono perdere tutto il valore: strumenti per un uso di breve periodo.",
    "maxi-cash-collect": "I Maxi Cash Collect pagano una prima cedola molto alta poco dopo l'emissione e poi cedole più piccole; dopo lo stacco della maxi cedola il prezzo scende di un importo simile. Sono spesso cercati da chi ha minusvalenze da compensare: l'effetto fiscale dipende dalla situazione personale e va verificato con la propria banca o il commercialista.",
    "low-barrier": "I Low Barrier hanno la barriera capitale (e spesso quella della cedola) molto bassa, di solito tra il 30% e il 50% del valore iniziale: più margine prima di rischiare il capitale, in cambio di cedole più contenute.",
    "fixed-cash-collect": "I Fixed Cash Collect pagano cedole fisse, non condizionate all'andamento dei sottostanti; il rimborso del capitale a scadenza resta legato alla barriera.",
    "top-bonus": "I Top Bonus pagano a scadenza il bonus se il sottostante è sopra la barriera alla data di valutazione finale: la barriera è osservata solo a scadenza.",
    "step-down": "Negli Step Down il livello che fa scattare il rimborso anticipato scende a ogni data di osservazione: il richiamo diventa via via più facile.",
    "recovery": "I Recovery sono emessi sotto la pari e puntano a rimborsare il nominale a scadenza se la barriera tiene: pensati per recuperare una perdita, senza cedole o con cedole basse.",
    "outperformance": "Gli Outperformance partecipano in modo più che proporzionale al rialzo del sottostante sopra lo strike e seguono il ribasso uno a uno.",
    "tracker-benchmark": "Tracker e Benchmark replicano in modo lineare il sottostante (un indice, un paniere, una materia prima), senza barriere né cedole: salgono e scendono con lui.",
}
# domande in più per le tipologie: (domanda, risposta). La prima riga è la risposta.
FAMILY_RISK = ("Quali sono i rischi dei certificati {what}?",
               "Rischio di mercato (se a scadenza il sottostante peggiore è sotto la barriera il rimborso segue la sua discesa e si può perdere gran parte "
               "del capitale), rischio emittente (se l'emittente fallisce il certificato non è garantito) e rischio di liquidità (differenza tra denaro e "
               "lettera). Le cedole condizionate possono non essere pagate.")


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def num(v, d=2):
    if v is None:
        return None
    try:
        s = f"{float(v):,.{d}f}".rstrip("0").rstrip(".") if d else f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return None
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def pct(v, d=2):
    n = num(v, d)
    return None if n is None else n + "%"


def day(s):
    if not s:
        return None
    y, m, d = str(s)[:10].split("-")
    return f"{d}/{m}/{y}"


def slugify(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


SUFFIX = re.compile(r"[\s,]+(s\.?p\.?a\.?|n\.?v\.?|ag|se|plc|s\.?a\.?|inc\.?|corp\.?|corporation|ltd\.?|group|holding|spa|reg|ord|registered shares?|index|price eur|price index|eur|it|im|fp|gy|us|na|ln|sm|dc)$", re.I)


def clean_name(n):
    n = re.sub(r"\s*\([^)]*\)", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    for _ in range(3):
        n = SUFFIX.sub("", n).strip()
    return n


def und_name(names):
    """Nome da mostrare per un sottostante: il più usato tra quelli scritti in minuscolo/maiuscolo misto."""
    c = Counter(clean_name(n) for n in names if n)
    mixed = [(k, v) for k, v in c.most_common() if re.search(r"[a-z]", k) and len(k) > 2]
    best = (mixed or c.most_common())[0][0]
    return best if re.search(r"[a-z]", best) or len(best) <= 5 else best.title()


def page(title, desc, canonical, body, ld=None):
    js = json.dumps(ld, ensure_ascii=False).replace("<", "\\u003c") if ld else ""
    ldj = f'<script type="application/ld+json">{js}</script>' if ld else ""
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{canonical}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Radar Certificati"><meta property="og:locale" content="it_IT">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}/og.png?v=1"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image">
<meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large">
<link rel="icon" href="/icon.svg?v=10" type="image/svg+xml"><link rel="apple-touch-icon" href="/apple-touch-icon.png?v=10"><link rel="preload" href="/fonts/geist-400-800-latin.woff2" as="font" type="font/woff2" crossorigin><link rel="stylesheet" href="/seo.css?v=2">
{ldj}
</head><body>
<header class="top"><div><a class="brand" href="/"><img src="/icon-192.png" alt="" width="32" height="32">Radar Certificati</a>
<nav><a href="/">Cerca nel radar</a><a href="/certificati/">Raccolte</a><a href="/guida-certificati">Guida</a></nav></div></header>
<main>{body}</main>
<footer class="foot"><div><p>Radar Certificati è uno screener gratuito e indipendente dei certificati d'investimento quotati in Italia (SeDeX, Cert-X/EuroTLX), aggiornato ogni giorno di borsa alle 09:35 e alle 16:15. Pagina aggiornata il {OGGI}.</p>
<p><b>Avvertenze.</b> Il sito ha solo scopo informativo: non offre consulenza, non fa raccomandazioni d'investimento e non sollecita l'acquisto o la vendita di strumenti finanziari. Elenchi e classifiche sono ordinamenti automatici di dati, uguali per tutti. I dati sono indicativi, raccolti da fonti pubbliche, e possono essere incompleti, in ritardo o errati; le probabilità sono stime statistiche, non previsioni. I certificati sono strumenti complessi che possono far perdere tutto il capitale investito: fanno fede solo KID, prospetto e quotazioni ufficiali. Il sito non è collegato agli emittenti e non riceve compensi da loro.</p>
<p><a href="/note-legali">Note legali e avvertenze</a> · <a href="/metodologia">Metodologia e fonti</a> · <a href="/guida-certificati">Guida ai certificati</a> · <a href="/certificati/">Tutte le raccolte</a> · <a href="/">Cerca nel radar</a></p></div></footer>
</body></html>"""


def und_list(c, k=3):
    u = c.get("underlyings") or []
    return ", ".join(u[:k]) + (f" +{len(u) - k}" if len(u) > k else "")


def table(certs, col=None):
    """col = (titolo, funzione) sostituisce l'ultima colonna (es. data della prossima cedola nel calendario)."""
    rows = []
    for c in certs[:ROWS]:
        d = c.get("distBarrier")
        prob = c.get("probBarrierHold")
        rows.append(
            f'<tr><td><a href="/certificato/{c["isin"]}">{c["isin"]}</a></td><td>{esc((c.get("type") or c.get("category") or "")[:38])}</td>'
            f'<td>{esc(und_list(c))}</td><td>{esc(c.get("issuer"))}</td><td class="r">{pct(c.get("couponPa")) or "–"}</td>'
            f'<td class="r">{pct(c.get("barrierPct"), 0) or "–"}</td><td class="r{" bad" if d is not None and d < 0 else ""}">{pct(d, 1) or "–"}</td>'
            f'<td class="r">{day(c.get("maturity")) or "–"}</td><td class="r">{(col[1](c) or "–") if col else (f"{round(prob * 100)}%" if prob is not None else "–")}</td></tr>')
    more = f'<p class="note">Mostrati {min(ROWS, len(certs))} di {len(certs)}. ' if len(certs) > ROWS else '<p class="note">'
    return ('<div class="tw"><table><thead><tr><th>ISIN</th><th>Tipo</th><th>Sottostanti</th><th>Emittente</th><th class="r">Cedola annua</th>'
            '<th class="r">Barriera</th><th class="r">Distanza</th><th class="r">Scadenza</th><th class="r">' + (col[0] if col else "Prob. tenuta") + '</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>" + more +
            "Distanza = quanto il sottostante peggiore è sopra la barriera capitale; Prob. tenuta = stima statistica che la barriera regga fino a scadenza.</p>")


def by_coupon(certs):
    return sorted(certs, key=lambda c: (c.get("couponPa") is None, -(c.get("couponPa") or 0), -(c.get("distBarrier") or -999)))


def stats(certs, what):
    """Frasi con i numeri della raccolta: rispondono direttamente alle domande ("quanti", "chi", "quanto rende")."""
    n = len(certs)
    iss = Counter(c.get("issuer") for c in certs if c.get("issuer"))
    cps = [c["couponPa"] for c in certs if c.get("couponPa")]
    mem = sum(1 for c in certs if c.get("memory"))
    mon = sum(1 for c in certs if c.get("freq") == "1m")
    under = sum(1 for c in certs if c.get("distBarrier") is not None and c["distBarrier"] < 0)
    mats = sorted(c["maturity"] for c in certs if c.get("maturity"))
    s = [f"Il radar segue <b>{n} certificati {what}</b>" + (f" di {len(iss)} emittenti" if len(iss) > 1 else (f" emessi da {esc(next(iter(iss)))}" if iss and next(iter(iss)) not in what else "")) + "."]
    if len(iss) > 1:
        s.append("I più presenti: " + ", ".join(f"{esc(k)} ({v})" for k, v in iss.most_common(5)) + ".")
    if cps:
        top = max((c for c in certs if c.get("couponPa")), key=lambda c: c["couponPa"])
        s.append(f"La cedola annua mediana è del <b>{pct(median(cps))}</b> (su {len(cps)} certificati con cedola); la più alta è del {pct(top['couponPa'])} "
                 f"(<a href=\"/certificato/{top['isin']}\">{top['isin']}</a>{', a ' + pct(top['distBarrier'], 1) + ' dalla barriera' if top.get('distBarrier') is not None else ''}).")
    if mem or mon:
        s.append(f"{mem} hanno l'effetto memoria e {mon} pagano la cedola ogni mese.")
    if under:
        s.append(f"{under} hanno oggi il sottostante peggiore sotto la barriera.")
    if mats:
        s.append(f"Le scadenze vanno dal {day(mats[0])} al {day(mats[-1])}.")
    return " ".join(s)


def faq(certs, what, fam=None):
    out = []
    if fam and FAMILY_TEXT.get(fam[1]):
        out.append((f"Come funzionano i certificati {fam[0]}?", FAMILY_TEXT[fam[1]]))
    iss = Counter(c.get("issuer") for c in certs if c.get("issuer"))
    out.append((f"Quanti certificati {what} ci sono?", f"Radar Certificati ne segue {len(certs)} quotati in Italia, aggiornati il {TODAY.strftime('%d/%m/%Y')}."))
    cp = [c for c in certs if c.get("couponPa") and (c.get("distBarrier") or 0) > 0]
    if cp:
        t = max(cp, key=lambda c: c["couponPa"])
        out.append((f"Qual è il certificato {what} con la cedola più alta?",
                    f"Tra quelli con il sottostante sopra la barriera, {t['isin']} ({t.get('type') or ''} di {t.get('issuer')}) paga il {pct(t['couponPa'])} annuo "
                    f"con il peggiore a {pct(t.get('distBarrier'), 1)} dalla barriera. Una cedola alta di solito significa rischio più alto."))
    if len(iss) > 1:
        out.append((f"Quali emittenti propongono certificati {what}?", ", ".join(f"{k} ({v})" for k, v in iss.most_common(8)) + "."))
    out.append((f"Quali sono i migliori certificati {what}?",
                "Non esiste un certificato migliore in assoluto: dipende dal rischio che si accetta, dall'orizzonte e dal resto del portafoglio. "
                "Questa pagina li mette in ordine con un criterio dichiarato e mostra per ciascuno cedola, barriera, distanza dalla barriera, scadenza e "
                "probabilità stimata di tenuta, così da confrontarli con gli stessi numeri. È un confronto di dati, non una raccomandazione."))
    if fam:
        out.append((FAMILY_RISK[0].format(what=fam[0]), FAMILY_RISK[1]))
    out.append(("Ogni quanto è aggiornato questo elenco?",
                f"Due volte al giorno nei giorni di borsa aperta, alle 09:35 e alle 16:15 (ora italiana). Ultimo aggiornamento: {OGGI}."))
    return out


PENDING = []  # (slug, titolo, descrizione, url, corpo con segnaposto <!--REL-->, ld, genitori): scritte da flush()


def hub(slug, h1, what, certs, intro="", crumb=None, sort=by_coupon, extra="", order="per cedola annua", fam=None, parents=(), col=None):
    certs = sort(certs)
    qs = faq(certs, what, fam)
    url = f"{SITE}/certificati/{slug}"
    desc = re.sub("<[^>]+>", "", stats(certs, what))[:300]
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": h1, "url": url, "description": desc, "dateModified": TODAY.isoformat(),
           "inLanguage": "it", "isPartOf": {"@type": "WebSite", "name": "Radar Certificati", "url": SITE + "/"},
           "mainEntity": {"@type": "ItemList", "numberOfItems": len(certs), "itemListElement": [
               {"@type": "ListItem", "position": i + 1, "url": f"{SITE}/certificato/{c['isin']}", "name": f"{c['isin']} {c.get('type') or ''}".strip()}
               for i, c in enumerate(certs[:ROWS])]}},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
              {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qs]},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Radar Certificati", "item": SITE + "/"},
              {"@type": "ListItem", "position": 2, "name": "Raccolte", "item": SITE + "/certificati/"},
              {"@type": "ListItem", "position": 3, "name": h1, "item": url}]}]
    q = crumb or ""
    body = (f'<p class="crumbs"><a href="/">Radar Certificati</a> › <a href="/certificati/">Raccolte</a> › {esc(h1)}</p>'
            f'<h1>{esc(h1)}</h1><p class="sub">Aggiornato il {OGGI} · dati di mercato due volte al giorno</p>'
            + (f'<p class="lead">{intro}</p>' if intro else "") + f'<p class="lead">{stats(certs, what)}</p>' + WARN
            + (f'<div class="btns"><a class="btn primary" href="/#q={esc(q)}">Filtra e confronta tutti nel radar</a></div>' if q else "")
            + f"<h2>Certificati {esc(what)} {order}</h2>" + table(certs, col) + extra
            + "<h2>Domande frequenti</h2>" + "".join(f"<details open><summary>{esc(a)}</summary><p>{esc(b)}</p></details>" for a, b in qs)
            + "<!--REL-->")
    title = f"{h1}: {len(certs)} certificati, cedole e barriere ({MESE}) | Radar Certificati"
    PENDING.append((slug, title, desc, url, body, ld, list(parents)))
    return {"slug": slug, "name": h1, "n": len(certs)}


def flush(groups):
    """Scrive le raccolte aggiungendo in fondo i collegamenti alle altre: ogni pagina porta a quelle vicine e alle principali."""
    def links(items, me):
        return "".join(f'<li><a href="/certificati/{i["slug"]}">{esc(i["name"].replace("Certificati ", "", 1))}</a></li>' for i in items if i["slug"] != me)
    for slug, title, desc, url, body, ld, parents in PENDING:
        rel = "<h2>Altre raccolte di certificati</h2>"
        if parents:
            rel += '<ul class="tags">' + links(parents, slug) + "</ul>"
        rel += ('<h3>Liste</h3><ul class="tags">' + links(groups["special"], slug) + "</ul>"
                '<h3>Tipologie</h3><ul class="tags">' + links(groups["families"], slug) + "</ul>"
                '<h3>Emittenti</h3><ul class="tags">' + links(groups["issuers"][:14], slug) + "</ul>"
                '<h3>Sottostanti più seguiti</h3><ul class="tags">' + links(groups["unds"][:24], slug) + "</ul>"
                '<p class="note"><a href="/certificati/">Tutte le raccolte</a> · <a href="/guida-certificati">Guida ai certificati</a></p>')
        (OUT / f"{slug}.html").write_text(page(title, desc, url, body.replace("<!--REL-->", rel), ld))


def guide(n, n_iss):
    from guida import SECTIONS
    url = SITE + "/guida-certificati"
    plain = lambda h: re.sub("<[^>]+>", "", h)
    qa = [(q, a) for _, items in SECTIONS for q, a in items]
    toc = "".join(f'<li><a href="#s{i}">{esc(t)}</a></li>' for i, (t, _) in enumerate(SECTIONS))
    secs = "".join(f'<h2 id="s{i}">{esc(t)}</h2>' + "".join(f"<details open><summary><h3 style=\"display:inline;font-size:inherit\">{esc(q)}</h3></summary><p>{a}</p></details>" for q, a in items)
                   for i, (t, items) in enumerate(SECTIONS))
    ld = [{"@context": "https://schema.org", "@type": "FAQPage", "name": "Guida ai certificati d'investimento", "url": url, "inLanguage": "it",
           "dateModified": TODAY.isoformat(),
           "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in qa]},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Radar Certificati", "item": SITE + "/"},
              {"@type": "ListItem", "position": 2, "name": "Guida ai certificati", "item": url}]}]
    body = (f'<p class="crumbs"><a href="/">Radar Certificati</a> › Guida</p><h1>Guida ai certificati d\'investimento</h1>'
            f'<p class="lead">Cosa sono i certificati, come funzionano cedole, barriere, effetto memoria e rimborso anticipato, quali rischi hanno e come '
            f'sono tassati. Con {n} certificati di {n_iss} emittenti da cercare e confrontare nel <a href="/">radar</a>.</p>'
            f'<ul class="tags">{toc}<li><a href="/certificati/">Tutte le raccolte</a></li></ul>' + secs
            + '<div class="btns"><a class="btn primary" href="/">Cerca un certificato</a><a class="btn" href="/certificati/">Sfoglia le raccolte</a></div>'
            + '<p class="warn"><b>Guida a scopo informativo.</b> Spiega come funzionano i certificati in generale: non è consulenza né una raccomandazione. '
            '<a href="/note-legali">Avvertenze complete</a> · <a href="/metodologia">Metodologia</a></p>')
    (DOCS / "guida-certificati.html").write_text(page("Guida ai certificati d'investimento: Cash Collect, Phoenix, barriera, memoria, tasse | Radar Certificati",
        "Cosa sono i certificati d'investimento, come funzionano Cash Collect, Phoenix ed Express, barriera, trigger, effetto memoria, autocall, rischio emittente e tassazione in Italia.",
        url, body, ld))


def crumbs_ld(name, url):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Radar Certificati", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": name, "item": url}]}


LEGAL = [
    ("Cos'è questo sito", [
        "Radar Certificati è uno strumento gratuito di ricerca e confronto (screener) dei certificati d'investimento quotati in Italia. Raccoglie "
        "dati pubblici, li mette in ordine e li mostra a chiunque nello stesso modo. Ha solo scopo informativo ed educativo."]),
    ("Non è consulenza né raccomandazione", [
        "Nulla di quanto pubblicato costituisce consulenza in materia di investimenti, ricerca in materia di investimenti, raccomandazione "
        "d'investimento ai sensi del Regolamento (UE) n. 596/2014, offerta al pubblico, sollecitazione o invito ad acquistare, vendere o "
        "mantenere strumenti finanziari.",
        "Il sito non conosce chi lo usa: non valuta conoscenze, esperienza, situazione finanziaria, obiettivi o tolleranza al rischio, e quindi "
        "non può dire se uno strumento è adatto o adeguato a una persona. Ogni decisione d'investimento è presa in autonomia da chi la compie, "
        "che ne resta il solo responsabile. Chi non è sicuro dovrebbe rivolgersi a un consulente finanziario abilitato o al proprio intermediario."]),
    ("Elenchi, classifiche, punteggi e profili", [
        "Raccolte, classifiche (per esempio «cedole più alte» o «difensivi»), punteggi, certificati in evidenza e portafogli d'esempio sono il "
        "risultato di ordinamenti e filtri automatici su criteri numerici dichiarati (cedola, distanza dalla barriera, scadenza, probabilità "
        "stimata e simili). Non esprimono un giudizio sul singolo strumento né sul suo emittente e non sono un consiglio a comprarlo.",
        "I profili «prudente», «bilanciato» e «aggressivo» sono soltanto filtri preimpostati che chiunque può modificare: non sono una "
        "profilazione dell'utente né una valutazione di adeguatezza. Espressioni come «migliori» o «più alte» indicano solo la posizione in un "
        "ordinamento per un dato criterio."]),
    ("Rischi dei certificati", [
        "I certificati sono strumenti finanziari derivati complessi e possono non essere adatti a tutti gli investitori. Si può perdere in parte "
        "o del tutto il capitale investito: se il sottostante scende sotto la barriera, se l'emittente (o il garante) diventa insolvente, se si "
        "vende prima della scadenza a un prezzo inferiore a quello d'acquisto. I certificati non sono coperti da sistemi di garanzia dei depositi.",
        "Le cedole condizionate possono non essere pagate; il rimborso anticipato può interrompere il flusso di cedole; la differenza tra denaro "
        "e lettera e la scarsa liquidità possono rendere costosa l'uscita; i certificati in valuta estera espongono anche al cambio. Rendimenti "
        "indicati o passati non sono indicativi di quelli futuri. Prima di investire leggere il KID (documento contenente le informazioni "
        "chiave), il prospetto di base, le condizioni definitive e gli avvisi dell'emittente."]),
    ("Dati, calcoli e stime", [
        "I dati sono raccolti in modo automatico da fonti pubbliche due volte al giorno nei giorni di borsa e possono essere incompleti, in "
        "ritardo, non aggiornati o errati. I prezzi sono indicativi e non in tempo reale. Rendimenti, distanze dalla barriera, punteggi, settori "
        "e calendari sono calcoli del sito, non dati ufficiali.",
        "Le probabilità di tenuta della barriera sono stime statistiche basate su volatilità e correlazioni storiche: non sono previsioni, non "
        "considerano salti di mercato, rimborso anticipato né rischio emittente, e possono rivelarsi sbagliate. Il dettaglio è nella pagina "
        "<a href=\"/metodologia\">Metodologia</a>. In caso di differenza fanno fede solo i documenti e le quotazioni ufficiali dell'emittente e "
        "del mercato."]),
    ("Indipendenza e conflitti d'interesse", [
        "Il sito è indipendente: non è collegato né affiliato agli emittenti, ai mercati o ai fornitori di dati, non riceve da loro compensi, "
        "commissioni o altri vantaggi, non ospita pubblicità e non guadagna dalle operazioni di chi lo consulta. L'ordine dei certificati dipende "
        "solo dai criteri numerici indicati in ogni pagina.",
        "Chi cura il sito può detenere, a titolo personale, alcuni degli strumenti finanziari mostrati. Il sito è un progetto personale e non "
        "rappresenta né impegna alcun intermediario, banca o datore di lavoro."]),
    ("Fiscalità", [
        "Le indicazioni sulla tassazione sono generali, riferite alle persone fisiche residenti in Italia e alla normativa in vigore, che può "
        "cambiare. Il trattamento fiscale dipende dalla situazione di ciascuno: per il proprio caso sentire il commercialista o l'intermediario."]),
    ("Limitazione di responsabilità", [
        "Il sito è offerto «così com'è», senza garanzie di completezza, esattezza, aggiornamento o disponibilità. Nei limiti consentiti dalla "
        "legge, chi lo cura non risponde di perdite o danni derivanti dall'uso delle informazioni pubblicate o dall'impossibilità di usarle."]),
    ("A chi si rivolge", [
        "Il sito è in italiano e riguarda strumenti quotati sui mercati italiani; si rivolge a persone residenti in Italia. Non è destinato a "
        "soggetti residenti in Paesi nei quali la diffusione di queste informazioni richieda autorizzazioni, né a «US persons»."]),
    ("Fonti e marchi", [
        "Liste e prezzi: Borsa Italiana, Euronext e i siti pubblici degli emittenti (tra cui BNP Paribas, UniCredit, Intesa Sanpaolo, Vontobel, "
        "Leonteq, Marex, Citigroup, Société Générale). Prezzi storici dei sottostanti: Yahoo Finance. Nomi e marchi appartengono ai rispettivi "
        "titolari e sono citati solo per identificare gli strumenti."]),
    ("Privacy e cookie", [
        "Il sito non usa cookie, non ha pubblicità né strumenti di tracciamento o statistiche, e non chiede registrazione. Preferiti, profilo, "
        "tema e impostazioni restano solo nel browser di chi lo usa (memoria locale) e non vengono inviati a nessuno. Il sito è ospitato da "
        "Cloudflare, che tratta i dati tecnici delle connessioni (per esempio l'indirizzo IP) per erogarlo."]),
]


def legal():
    url = SITE + "/note-legali"
    body = ('<p class="crumbs"><a href="/">Radar Certificati</a> › Note legali</p><h1>Note legali e avvertenze</h1>'
            '<p class="lead">In breve: Radar Certificati mostra e ordina dati, non dà consigli. I certificati possono far perdere tutto il capitale '
            "investito; prima di decidere leggere sempre il KID e i documenti dell'emittente.</p>"
            + "".join(f"<h2>{esc(t)}</h2>" + "".join(f"<p>{x}</p>" for x in ps) for t, ps in LEGAL)
            + '<div class="btns"><a class="btn primary" href="/">Torna al radar</a><a class="btn" href="/metodologia">Metodologia e fonti</a></div>')
    (DOCS / "note-legali.html").write_text(page("Note legali e avvertenze | Radar Certificati",
        "Radar Certificati ha solo scopo informativo: non è consulenza né raccomandazione d'investimento. Rischi dei certificati, limiti dei dati, indipendenza, privacy.",
        url, body, [crumbs_ld("Note legali", url)]))


METHOD_NAMES = {"volatilita": "Volatilità", "correlazioni": "Correlazioni", "modello": "Modello", "barriera_a_scadenza": "Barriera osservata a scadenza",
                "barriera_continua": "Barriera continua", "solo_peggiore": "Quando è nota solo la distanza del peggiore", "limiti": "Limiti del modello",
                "aggiornamento": "Aggiornamento"}


def method(n, n_iss):
    meta = json.loads((DOCS / "api" / "v1" / "meta.json").read_text())
    url = SITE + "/metodologia"
    m = meta.get("methodology") or {}
    iss = sorted((meta.get("issuers") or {}).items(), key=lambda x: -x[1].get("certificates", 0))
    rows = "".join(f'<tr><td>{esc(k)}</td><td class="r">{v.get("certificates", 0)}</td><td class="r">{v.get("withPrice", 0)}</td>'
                   f'<td class="r">{v.get("withProbability", 0)}</td></tr>' for k, v in iss[:40])
    body = (f'<p class="crumbs"><a href="/">Radar Certificati</a> › Metodologia</p><h1>Metodologia e fonti dei dati</h1>'
            f'<p class="sub">Aggiornato il {OGGI}</p>'
            f'<p class="lead">Radar Certificati segue <b>{n} certificati di {n_iss} emittenti</b> quotati in Italia. Questa pagina spiega da dove vengono '
            'i dati, quando sono aggiornati e come sono calcolati distanza dalla barriera, rendimento e probabilità di tenuta, con i loro limiti.</p>'
            "<h2>Da dove vengono i dati</h2><p>Un programma legge due volte al giorno le pagine pubbliche degli emittenti (BNP Paribas, UniCredit, "
            "Vontobel, Leonteq, Marex, Société Générale, Citigroup, Intesa Sanpaolo e altri) e gli elenchi di Borsa Italiana, Euronext e Vorvel. Quando "
            "più fonti descrivono lo stesso certificato, i dati sono uniti e passano controlli di plausibilità: i valori incoerenti vengono scartati "
            "anziché mostrati. I prezzi storici dei sottostanti vengono da Yahoo Finance.</p>"
            f"<h2>Quando sono aggiornati</h2><p>{esc((meta.get('schedule') or {}).get('description') or '')} Ogni pagina riporta la data dell'ultimo "
            "aggiornamento. I prezzi non sono in tempo reale.</p>"
            "<h2>Distanza dalla barriera</h2><p>È la discesa percentuale che il sottostante peggiore può ancora subire prima di toccare la barriera "
            "capitale: (prezzo attuale − livello barriera) / prezzo attuale. Se è negativa, il sottostante è già sotto la barriera.</p>"
            "<h2>Cedola annua e rendimento</h2><p>La cedola annua è la somma delle cedole previste in un anno in percentuale del nominale, come "
            "dichiarata dall'emittente: è condizionata quando dipende dal livello trigger. Il rendimento a scadenza mostrato nel radar rapporta "
            "cedole future e rimborso al prezzo lettera di oggi, nell'ipotesi che tutte le cedole siano pagate e la barriera tenga: è uno scenario, "
            "non una promessa.</p>"
            "<h2>Probabilità di tenuta della barriera</h2><p>È la stima, con una simulazione Monte Carlo, della probabilità che a scadenza il capitale "
            "non sia intaccato dalla barriera.</p><dl class=\"def\">"
            + "".join(f"<dt>{esc(METHOD_NAMES.get(k, k))}</dt><dd>{esc(v)}</dd>" for k, v in m.items()) + "</dl>"
            "<p>È una stima statistica costruita sul passato: non è una previsione e può rivelarsi sbagliata.</p>"
            "<h2>Copertura per emittente</h2>"
            '<div class="tw"><table><thead><tr><th>Emittente</th><th class="r">Certificati</th><th class="r">Con prezzo</th><th class="r">Con probabilità</th></tr></thead><tbody>'
            + rows + "</tbody></table></div>"
            '<h2>Dati aperti</h2><p>Gli stessi dati sono disponibili in JSON: <a href="/api/v1/meta.json">metadati</a>, '
            '<a href="/api/v1/schema.json">descrizione dei campi</a>. Chi li riusa è pregato di citare la fonte.</p>' + WARN
            + '<div class="btns"><a class="btn primary" href="/">Cerca nel radar</a><a class="btn" href="/guida-certificati">Guida ai certificati</a></div>')
    (DOCS / "metodologia.html").write_text(page("Metodologia e fonti: come Radar Certificati calcola distanze, rendimenti e probabilità",
        f"Da dove vengono i dati di {n} certificati, quando sono aggiornati e come sono calcolati distanza dalla barriera, rendimento e probabilità di tenuta (Monte Carlo), con i limiti del modello.",
        url, body, [crumbs_ld("Metodologia", url), {"@context": "https://schema.org", "@type": "Dataset", "name": "Certificati d'investimento quotati in Italia",
            "description": f"Dati giornalieri di {n} certificati d'investimento quotati su SeDeX, Cert-X/EuroTLX e Vorvel: emittente, tipologia, sottostanti, cedola, barriera, distanza dalla barriera, scadenza, prezzi, probabilità stimata di tenuta.",
            "url": url, "inLanguage": "it", "isAccessibleForFree": True, "dateModified": TODAY.isoformat(),
            "creator": {"@type": "Organization", "name": "Radar Certificati", "url": SITE + "/"},
            "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": SITE + "/api/v1/certificates.json"}]}]))


def main():
    certs = [c for c in json.loads(CERTS.read_text())["certificates"] if ISIN_RE.match(c.get("isin") or "")]
    first = json.loads(FIRST.read_text()) if FIRST.exists() else {}
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    groups = {"issuers": [], "families": [], "unds": [], "sectors": [], "special": []}

    # emittenti
    by_iss = defaultdict(list)
    for c in certs:
        if c.get("issuer"):
            by_iss[c["issuer"]].append(c)
    hubs = {"issuers": {}, "families": [], "tickers": {}, "sectors": {}}
    for name, cs in sorted(by_iss.items(), key=lambda x: -len(x[1])):
        if len(cs) < MIN_UND:
            continue
        slug = "emittente-" + slugify(name)
        groups["issuers"].append(hub(slug, f"Certificati {name}", f"emessi da {name}", cs, crumb=name))
        hubs["issuers"][name] = slug
    groups["combo"] = []

    # famiglie di prodotto
    for label, slug, rx in FAMILIES:
        cs = [c for c in certs if re.search(rx, f"{c.get('type') or ''} {c.get('callable') or ''} {c.get('typeMarket') or ''}", re.I)]
        if len(cs) < MIN_UND:
            continue
        h1 = f"Certificati {label}"
        short = label.split(" (")[0]
        fam = hub(slug, h1, label, cs, intro=FAMILY_TEXT.get(slug, ""), crumb=short.replace("a capitale ", "").replace("a leva", "leva"), fam=(short, slug))
        groups["families"].append(fam)
        hubs["families"].append([label, slug, rx])
        # tipologia × emittente ("Cash Collect UniCredit"): le ricerche più frequenti dopo quelle per nome
        per = defaultdict(list)
        for c in cs:
            if c.get("issuer") in hubs["issuers"]:
                per[c["issuer"]].append(c)
        for name, ics in sorted(per.items(), key=lambda x: -len(x[1])):
            if len(ics) >= MIN_COMBO and len(ics) < len(by_iss[name]):
                groups["combo"].append(hub(f"{slug}-{slugify(name)}", f"Certificati {short} {name}", f"{short} di {name}", ics,
                                           intro=FAMILY_TEXT.get(slug, ""), crumb=f"{short.replace('a capitale ', '').replace('a leva', 'leva')} {name}", fam=(short, slug),
                                           parents=[fam, {"slug": hubs["issuers"][name], "name": f"Tutti i certificati {name}"}]))

    # sottostanti (per ticker: "UNICREDIT", "UniCredit SpA" e "UCG" sono lo stesso titolo)
    by_t, names = defaultdict(dict), defaultdict(list)
    for c in certs:
        for u in c.get("underlyingsRisk") or []:
            if u.get("ticker"):
                by_t[u["ticker"]][c["isin"]] = c
                names[u["ticker"]].append(u.get("name"))
    # stesso titolo con più ticker (borse diverse) o nomi troncati ("...Paschi di Sien"): si uniscono per inizio del nome
    merged, tick_of = {}, {}
    for t, cs in sorted(by_t.items(), key=lambda x: -len(x[1])):
        key = slugify(und_name(names[t]))[:22]
        g = merged.setdefault(key, {"certs": {}, "names": [], "tickers": []})
        g["certs"].update(cs)
        g["names"] += names[t]
        g["tickers"].append(t)
    used = set()
    for key, g in sorted(merged.items(), key=lambda x: -len(x[1]["certs"])):
        if len(g["certs"]) < MIN_UND:
            continue
        name = und_name(g["names"])
        slug = "su-" + slugify(name)
        if slug in used:
            slug += "-" + slugify(g["tickers"][0])
        used.add(slug)
        groups["unds"].append(hub(slug, f"Certificati su {name}", f"su {name}", list(g["certs"].values()), crumb=name))
        for t in g["tickers"]:
            hubs["tickers"][t] = slug

    # settori
    by_s = defaultdict(list)
    for c in certs:
        if c.get("sector") and c["sector"] != "Misto":
            by_s[c["sector"]].append(c)
    for s, cs in sorted(by_s.items(), key=lambda x: -len(x[1])):
        if len(cs) < MIN_UND:
            continue
        slug = "settore-" + slugify(s)
        groups["sectors"].append(hub(slug, f"Certificati settore {s}", f"sul settore {s}", cs))
        hubs["sectors"][s] = slug

    # liste speciali
    soon = (TODAY + timedelta(days=180)).isoformat()
    sp = groups["special"]
    sp.append(hub("cedole-piu-alte", "Certificati con le cedole più alte", "con le cedole più alte (barriera ad almeno il 25%, scadenza oltre 6 mesi)",
                  [c for c in certs if c.get("couponPa") and (c.get("distBarrier") or -1) >= 25 and (c.get("maturity") or "") >= soon],
                  intro="Classifica per cedola annua dei certificati con il sottostante peggiore ad almeno il 25% dalla barriera e scadenza oltre 6 mesi. Non è una raccomandazione: a cedole più alte corrispondono rischi più alti."))
    sp.append(hub("difensivi", "Certificati difensivi con cedola", "difensivi (barriera ad almeno il 40%)",
                  [c for c in certs if c.get("couponPa") and (c.get("distBarrier") or -1) >= 40],
                  intro="Certificati a cedola con il sottostante peggiore ad almeno il 40% sopra la barriera capitale: un margine ampio prima di rischiare il capitale."))
    sp.append(hub("cedola-mensile", "Certificati con cedola mensile", "con cedola mensile", [c for c in certs if c.get("freq") == "1m"], crumb="mensile"))
    sp.append(hub("effetto-memoria", "Certificati con effetto memoria", "con effetto memoria", [c for c in certs if c.get("memory")],
                  intro="Con l'effetto memoria le cedole non pagate in una data di osservazione vengono recuperate alla prima data successiva in cui la condizione è rispettata."))
    sp.append(hub("barriera-bassa", "Certificati con barriera bassa", "con barriera capitale al 40% o meno",
                  [c for c in certs if c.get("couponPa") and c.get("barrierPct") and c["barrierPct"] <= 40],
                  intro="Certificati a cedola con la barriera capitale fissata al 40% del valore iniziale o più in basso: il sottostante deve più che dimezzarsi prima che il capitale sia a rischio. La barriera bassa riduce il rischio, non lo elimina."))
    sp.append(hub("sotto-la-pari", "Certificati sotto la pari", "sotto la pari (prezzo lettera sotto il nominale, barriera non toccata)",
                  [c for c in certs if c.get("couponPa") and c.get("ask") and c.get("nominal") and c.get("currency") == "EUR"
                   and 0.5 * c["nominal"] <= c["ask"] < c["nominal"] and (c.get("distBarrier") or -1) > 0],
                  intro="Certificati a cedola che oggi quotano in lettera sotto il valore nominale (tra il 50% e il 100%), con il sottostante peggiore ancora sopra la barriera. Un prezzo sotto la pari alza il rendimento potenziale a scadenza, ma di solito indica che il mercato vede più rischio: sottostanti scesi, barriera più vicina o cedole a rischio."))
    end = (TODAY + timedelta(days=180)).isoformat()
    sp.append(hub("in-scadenza", "Certificati in scadenza nei prossimi 6 mesi", f"in scadenza entro il {day(end)}",
                  [c for c in certs if TODAY.isoformat() <= (c.get("maturity") or "") <= end], order="per data di scadenza",
                  sort=lambda cs: sorted(cs, key=lambda c: c["maturity"]),
                  intro="Certificati che arrivano a scadenza nei prossimi sei mesi, dal più vicino. A ridosso della scadenza conta soprattutto la distanza del sottostante peggiore dalla barriera."))
    cal = (TODAY + timedelta(days=30)).isoformat()
    sp.append(hub("prossime-cedole", "Calendario cedole dei certificati", "con data cedola nei prossimi 30 giorni",
                  [c for c in certs if TODAY.isoformat() <= (c.get("nextCouponDate") or "") <= cal], order="per data della prossima cedola",
                  sort=lambda cs: sorted(cs, key=lambda c: (c["nextCouponDate"], -(c.get("couponPa") or 0))),
                  col=("Prossima cedola", lambda c: day(c.get("nextCouponDate"))),
                  intro="Certificati con una data cedola nei prossimi 30 giorni, in ordine di data. La cedola condizionata è pagata solo se alla data di osservazione i sottostanti rispettano il livello trigger; le date sono quelle comunicate dagli emittenti e vanno verificate sui loro avvisi."))
    # il primo giorno dell'archivio (e i caricamenti in blocco) non sono nuove emissioni
    bulk = [d for d, n in Counter(first.values()).items() if n > 500]
    recent = max([(TODAY - timedelta(days=30)).isoformat()] + [(date.fromisoformat(d) + timedelta(days=1)).isoformat() for d in bulk])
    new = [c for c in certs if first.get(c["isin"], "") >= recent]
    if len(new) >= MIN_UND:
        sp.append(hub("nuove-emissioni", "Nuove emissioni di certificati", "comparsi negli ultimi 30 giorni", new,
                      sort=lambda cs: sorted(cs, key=lambda c: first.get(c["isin"], ""), reverse=True),
                      intro="Certificati comparsi sul mercato italiano negli ultimi 30 giorni, dal più recente."))

    flush(groups)
    (OUT / "hubs.json").write_text(json.dumps(hubs, ensure_ascii=False, separators=(",", ":")))

    # indice delle raccolte
    def lst(items, cls="tags"):
        return f'<ul class="{cls}">' + "".join(f'<li><a href="/certificati/{i["slug"]}">{esc(i["name"])}</a> <small>{i["n"]}</small></li>' for i in items) + "</ul>"
    body = (f'<p class="crumbs"><a href="/">Radar Certificati</a> › Raccolte</p><h1>Tutti i certificati d\'investimento quotati in Italia</h1>'
            f'<p class="lead">{len(certs)} certificati di {len(by_iss)} emittenti, raggruppati per emittente, sottostante, tipologia e settore. '
            'Ogni raccolta mostra cedole, barriere, distanza dalla barriera, scadenze e probabilità stimata di tenuta; ogni certificato ha la sua scheda.</p>'
            '<div class="btns"><a class="btn primary" href="/">Cerca e filtra nel radar</a><a class="btn" href="/guida-certificati">Guida ai certificati</a></div>'
            + WARN + "<h2>Liste</h2>" + lst(sp) + "<h2>Per tipologia</h2>" + lst(groups["families"]) + "<h2>Per emittente</h2>" + lst(groups["issuers"])
            + "<h2>Per tipologia ed emittente</h2>" + lst(sorted(groups["combo"], key=lambda h: -h["n"]))
            + "<h2>Per settore</h2>" + lst(groups["sectors"]) + "<h2>Per sottostante</h2>" + lst(groups["unds"], "cols"))
    (OUT / "index.html").write_text(page(f"Certificati d'investimento: {len(certs)} certificati per emittente, sottostante e tipologia | Radar Certificati",
                                         f"Elenco dei {len(certs)} certificati quotati in Italia per emittente, sottostante, tipologia (Cash Collect, Phoenix, Express, Credit Linked...) e settore.",
                                         SITE + "/certificati/", body))

    # sitemap: pagine fisse, raccolte, schede
    allh = [h for g in groups.values() for h in g]
    urls = [(SITE + "/", TODAY.isoformat(), "1.0"), (SITE + "/certificati/", TODAY.isoformat(), "0.9"),
            (SITE + "/guida-certificati", TODAY.isoformat(), "0.9"),
            (SITE + "/metodologia", TODAY.isoformat(), "0.5"), (SITE + "/note-legali", None, "0.3")]
    urls += [(f"{SITE}/certificati/{h['slug']}", TODAY.isoformat(), "0.8") for h in allh]
    urls += [(f"{SITE}/certificato/{c['isin']}", (c.get("updatedAt") or "")[:10] or None, "0.6") for c in certs]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, lm, p in urls:
        sm.append(f"<url><loc>{u}</loc>" + (f"<lastmod>{lm}</lastmod>" if lm else "") + f"<priority>{p}</priority></url>")
    sm.append("</urlset>")
    (DOCS / "sitemap.xml").write_text("\n".join(sm) + "\n")

    # llms.txt: cos'è il sito e dove trovare cosa, per gli assistenti IA
    top = lambda g, k: "\n".join(f"- [{h['name']}]({SITE}/certificati/{h['slug']}): {h['n']} certificati" for h in groups[g][:k])
    (DOCS / "llms.txt").write_text(f"""# Radar Certificati

> Screener gratuito e indipendente dei certificati d'investimento quotati in Italia (SeDeX di Borsa Italiana, Cert-X/EuroTLX di Euronext): {len(certs)} certificati di {len(by_iss)} emittenti con cedola annua, frequenza, effetto memoria, barriera capitale, distanza del sottostante peggiore dalla barriera, scadenza, prezzo denaro/lettera e probabilità stimata di tenuta della barriera (simulazione Monte Carlo sulla volatilità storica). Aggiornato ogni giorno di borsa alle 09:35 e alle 16:15 ora di Roma. Senza registrazione.

Dati aggiornati al {TODAY.strftime("%d/%m/%Y")}. I dati sono indicativi e raccolti da fonti pubbliche (siti degli emittenti, Borsa Italiana, Euronext); non sono consulenza. In italiano.

## Pagine principali
- [Radar (app di ricerca)]({SITE}/): ricerca per ISIN, sottostante, emittente, tipologia; filtri, profili di rischio, confronto, portafoglio, esportazione Excel
- [Guida ai certificati]({SITE}/guida-certificati): cosa sono i certificati, Cash Collect, Phoenix, Express, barriera, trigger, effetto memoria, autocall, fiscalità, rischio emittente, come si calcola la probabilità di tenuta
- [Tutte le raccolte]({SITE}/certificati/): per emittente, sottostante, tipologia, settore
- [Metodologia e fonti]({SITE}/metodologia): come sono raccolti i dati e calcolate distanze, rendimenti e probabilità
- [Note legali e avvertenze]({SITE}/note-legali): il sito non fa consulenza né raccomandazioni; gli elenchi sono ordinamenti automatici
- Scheda di ogni certificato: {SITE}/certificato/{{ISIN}} (es. {SITE}/certificato/{certs[0]['isin']})

## Liste
{top("special", 10)}

## Per tipologia
{top("families", 20)}

## Per emittente
{top("issuers", 40)}

## Sottostanti più seguiti
{top("unds", 40)}

## Dati aperti (JSON)
- [Metadati e metodologia]({SITE}/api/v1/meta.json)
- [Descrizione dei campi]({SITE}/api/v1/schema.json)
- [Tutti i certificati]({SITE}/api/v1/certificates.json) (file grande, ~16 MB)
""")
    guide(len(certs), len(by_iss))
    legal()
    method(len(certs), len(by_iss))
    print(f"[seo] {sum(len(g) for g in groups.values())} raccolte, {len(certs)} schede nella sitemap")


if __name__ == "__main__":
    main()
