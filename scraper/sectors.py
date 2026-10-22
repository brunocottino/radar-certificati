"""Settore di ogni sottostante e del certificato (tutti dello stesso settore -> quel settore, altrimenti "Misto").

Ordine delle regole (la prima che risponde vince):
1. "iSTOXX/Leonteq Single Stock on X": conta la società X dentro l'indice
2. nomi brevi esatti (sigle: F = Ford, UCG = UniCredit, UKX = FTSE 100...)
3. titoli di debito (DEB, DEBITO, DEBT) e cambi (EUR/USD...)
4. società note: vince la corrispondenza più lunga (Siemens Energy prima di Siemens, Banca Generali prima di Generali);
   nei nomi di indici si tolgono prima i marchi di emittenti e fornitori (BNP Paribas, Leonteq, Euronext, MSCI...),
   altrimenti "BNP Paribas ... MSCI AI Index" finirebbe tra le banche
5. parole di settore nel nome (indici settoriali: EURO STOXX Banks, Health Care, Oil & Gas...)
6. società nel nome Yahoo del ticker (solo per azioni), poi settore e industria Yahoo
7. indici generali (EURO STOXX 50, S&P 500, ETF paese...)
"""
import re
import unicodedata

SECTORS = ["Banche", "Assicurazioni", "Finanza", "Tecnologia", "Telecom e media", "Energia", "Utility", "Auto",
           "Industria e difesa", "Trasporti e turismo", "Consumi e lusso", "Salute", "Materie prime", "Immobiliare",
           "Crypto", "Indici", "Tassi e credito", "Valute"]


def _n(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " " + re.sub(r"[^a-z0-9&]+", " ", s).strip() + " "


def _rx(words):
    return re.compile("|".join(r"(?<= )" + w + r"(?= )" for w in words))


# nomi brevi (sigle) riconosciuti solo se sono il nome intero
EXACT = {
    "f": "Auto", "gm": "Auto", "stl": "Auto", "stla": "Auto", "rno": "Auto", "volv": "Auto", "jlr": "Auto",
    "ucg": "Banche", "isp": "Banche", "bpm": "Banche", "bami": "Banche", "barc": "Banche", "sg": "Banche", "db": "Banche",
    "dbk": "Banche", "mps": "Banche", "ing": "Banche", "gle": "Banche", "bnp": "Banche",
    # codici di borsa ricorrenti nei nomi brevi degli emittenti
    "cbk": "Banche", "commerz": "Banche", "comm": "Banche", "san": "Banche", "sant": "Banche", "bpe": "Banche",
    "raiff": "Banche", "rffs": "Banche", "aca": "Banche", "fbk": "Banche", "abn": "Banche", "gs": "Banche", "socgen": "Banche",
    "wfc": "Banche", "bofa": "Banche", "citi": "Banche", "intesasanpaolo": "Banche", "finc": "Banche", "fnco": "Banche",
    "estoxx banks": "Banche", "esxx banks": "Banche", "solebbks": "Banche",
    "g": "Assicurazioni", "aeg": "Assicurazioni", "uni": "Assicurazioni", "unpl": "Assicurazioni", "unip": "Assicurazioni",
    "prud": "Assicurazioni", "alv": "Assicurazioni", "zrch": "Assicurazioni", "sren": "Assicurazioni",
    "azm": "Finanza", "bx": "Finanza", "apo": "Finanza", "ppal": "Finanza", "pypl": "Finanza", "ady": "Finanza", "blck": "Finanza",
    "stlam": "Auto", "stlammi": "Auto", "stla it": "Auto", "tsla": "Auto", "tsl": "Auto", "volks": "Auto", "volk": "Auto",
    "vow": "Auto", "vow3": "Auto", "p911": "Auto", "mbg": "Auto", "m benz": "Auto", "merced": "Auto", "pi": "Auto", "pirc": "Auto",
    "ker": "Consumi e lusso", "monc": "Consumi e lusso", "moncl": "Consumi e lusso", "mon": "Consumi e lusso",
    "cpr": "Consumi e lusso", "bc": "Consumi e lusso", "herm": "Consumi e lusso", "hrms": "Consumi e lusso",
    "brby": "Consumi e lusso", "cfr": "Consumi e lusso", "nke": "Consumi e lusso", "boss": "Consumi e lusso",
    "zal": "Consumi e lusso", "ads": "Consumi e lusso", "adds": "Consumi e lusso", "carlb": "Consumi e lusso",
    "ko": "Consumi e lusso", "pg": "Consumi e lusso", "mc": "Consumi e lusso", "el": "Consumi e lusso", "lux": "Consumi e lusso",
    "nvda": "Tecnologia", "nvd": "Tecnologia", "msft": "Tecnologia", "amzn": "Tecnologia", "intc": "Tecnologia",
    "googl": "Tecnologia", "goog": "Tecnologia", "orcl": "Tecnologia", "mrvl": "Tecnologia", "pltr": "Tecnologia",
    "plntr": "Tecnologia", "palant": "Tecnologia", "stmmi": "Tecnologia", "stm it": "Tecnologia", "stm fr": "Tecnologia",
    "stmpa": "Tecnologia", "asm": "Tecnologia", "baba": "Tecnologia", "mu": "Tecnologia", "micr": "Tecnologia",
    "ifx": "Tecnologia", "infin": "Tecnologia", "aapl": "Tecnologia", "appl": "Tecnologia", "avgo": "Tecnologia",
    "broad": "Tecnologia", "crwd": "Tecnologia", "dsy": "Tecnologia", "dass": "Tecnologia", "smci": "Tecnologia",
    "qcom": "Tecnologia", "anet": "Tecnologia", "csco": "Tecnologia", "wdc": "Tecnologia", "cohr": "Tecnologia",
    "lite": "Tecnologia", "nasdaq100": "Tecnologia", "coin": "Crypto", "coinb": "Crypto",
    "ntfx": "Telecom e media", "nflx": "Telecom e media", "dis": "Telecom e media", "dte": "Telecom e media",
    "ora": "Telecom e media", "ses": "Telecom e media",
    "rhm": "Industria e difesa", "rhein": "Industria e difesa", "pry": "Industria e difesa", "prys": "Industria e difesa",
    "fct": "Industria e difesa", "fnct": "Industria e difesa", "siem": "Industria e difesa", "sie": "Industria e difesa",
    "thyss": "Industria e difesa", "rr": "Industria e difesa", "bae": "Industria e difesa", "saabb": "Industria e difesa",
    "air": "Industria e difesa", "hei": "Industria e difesa", "sgo": "Industria e difesa", "rklb": "Industria e difesa",
    "schndr": "Industria e difesa", "ho": "Industria e difesa", "gev": "Industria e difesa", "fer": "Industria e difesa",
    "ten": "Energia", "tte": "Energia", "rep": "Energia", "saip": "Energia", "eni": "Energia", "eqnr": "Energia",
    "chev": "Energia", "enr": "Energia", "su": "Industria e difesa", "ccj": "Energia", "enph": "Energia",
    "fslr": "Energia", "vws": "Energia",
    "ibe": "Utility", "engi": "Utility", "her": "Utility", "veo": "Utility", "ceg": "Utility", "vst": "Utility",
    "nee": "Utility", "edf": "Utility", "srg": "Utility",
    "amp": "Salute", "ampl": "Salute", "novob": "Salute", "novon": "Salute", "novonord": "Salute", "novn": "Salute",
    "nov": "Salute", "bay": "Salute", "bayn": "Salute", "pfe": "Salute", "pfz": "Salute", "pfzr": "Salute", "pfiz": "Salute",
    "azn": "Salute", "astra": "Salute", "lly": "Salute", "elly": "Salute", "dias": "Salute", "jnj": "Salute", "mrk": "Salute",
    "bmy": "Salute", "mrna": "Salute", "unh": "Salute", "bntx": "Salute",
    "mt": "Materie prime", "arclmt": "Materie prime", "arcelor": "Materie prime", "fcx": "Materie prime",
    "nem": "Materie prime", "glen": "Materie prime", "rio": "Materie prime", "zinco": "Materie prime", "mp": "Materie prime",
    "luft": "Trasporti e turismo", "lufth": "Trasporti e turismo", "aal": "Trasporti e turismo", "af": "Trasporti e turismo",
    "airb": "Trasporti e turismo", "wizz": "Trasporti e turismo",
    "amt": "Immobiliare",
    "estoxx 50": "Indici", "kospi2": "Indici", "dia": "Indici", "rty": "Indici",
    "eurostoxx sel div30": "Indici", "stoxx global select div 100 eur": "Indici",
    "stoxxeu 600 auto parts": "Auto",
    "eurtry exchange rate": "Valute", "brl": "Valute",
    "trn": "Utility", "vie": "Utility", "eoan": "Utility", "esx util": "Utility", "sfer": "Consumi e lusso", "hen": "Consumi e lusso",
    "bzu": "Industria e difesa", "dg": "Industria e difesa", "fincant": "Industria e difesa", "finct": "Industria e difesa",
    "tef": "Telecom e media", "cr agr": "Banche", "toten": "Energia", "estx aut and prt eur price": "Auto", "hang se": "Indici",
    "strategy": "Crypto", "block": "Finanza", "arm": "Tecnologia", "advanced micro": "Tecnologia",
    "tim": "Telecom e media", "ldo": "Industria e difesa", "spm": "Energia", "dpw": "Trasporti e turismo",
    "stm": "Tecnologia", "nsdq": "Tecnologia", "rh": "Consumi e lusso", "bat": "Consumi e lusso", "ovs": "Consumi e lusso",
    "target": "Consumi e lusso", "total": "Energia", "mfe": "Telecom e media", "lse": "Finanza", "3i": "Finanza",
    "ukx": "Indici", "indu": "Indici", "c40": "Indici", "fxi": "Indici", "fxi up": "Indici", "eustx 50": "Indici",
    "sp 500": "Indici", "s and p asx 200": "Indici", "eurostoxx seldiv 30": "Indici", "ed30": "Indici",
}

DEBT = _rx([r"obbligazion\w*", r"deb\w*", r"\w+ ?sub", r"euribor ?\w*", r"eur ?\d+m", r"estr", r"euro short term rate", r"\w*btp\w*",
            r"solde 10y", r"10 ?y(ear)? tec", r"cmt \d+ ?y", r"cms \d+ ?y", r"itx\w+", r"itrx( \w+)*", r"creditworthiness", r"itraxx \w+", r"republic of \w+", r"\w+ cpi"])
FX = re.compile(r"^ (eur|usd|gbp|chf|jpy) ?(usd|eur|gbp|chf|jpy|try|brl|mxn|zar|cnh|cny|nok|sek|aud|cad) $|^ eur versus \w+ $")

# nei nomi di indici questi marchi (emittenti, fornitori di indici, tipi di rendimento) non sono la società sottostante
IDX = re.compile(r"(?<= )(index|indice|decrement|dec \d|volatility control|vol control|rc ?\d+|er rc\d*|basket|etf|fund|fondo|ucits|"
                 r"futures|tilted|select \d+|trust|sicav|equities|strategy index|ind|idx|exc rtn|cmci|amc|portfolio|smart|opportunities|ar|ntr|vt ?\d+|"
                 r"total return|excess return|net return|price return)(?= )")
BRANDS = re.compile(r"(?<= )(bnp paribas|bnp|leonteq|ubs|raiffeisen|barclays|citi|citigroup|goldman sachs|morgan stanley|"
                    r"jp ?morgan|euronext|solactive|bloomberg|msci|e?i?stoxx|s&p|s p|ftse|morningstar|theam|exane|vontobel|"
                    r"societe generale|intesa sanpaolo|unicredit|ishares|vaneck|vectors|spdr|global x|amplify|direxion|proshares|"
                    r"first trust|invesco|ark|nomura|amundi|axa im|fidelity( funds)?|nordea( 1)?|schroders?( isf)?|parvest|lyxor|xtrackers|"
                    r"acomea|sg|uc|bsk|bskt|total return|excess return|net return|price return|target volatility)(?= )")

# società: parole chiave nel nome
COMPANIES = {
    "Banche": r"unicredit|intesa sanpaolo|intesa|banco bpm|poste italiane|poste|julius ba\w*|bnp paribas|bnp|societe generale|"
              r"soc gen|commerzbank|deutsche bank|barclays|hsbc|lloyds|natwest|santander|bbva|bilbao|caixabank|sabadell|"
              r"bankinter|mediobanca|bper|banca|banco|bank|bancorp|monte dei paschi|bmps|credit agricole|natixis|ing groep|"
              r"ing group|abn amro|kbc|erste|raiffeisen|ubs|credit suisse|jpmorgan|jp morgan|goldman sachs|morgan stanley|"
              r"citigroup|wells fargo|bank of america|banca generali|fineco|finecobank|mediolanum|credem|popolare|unicaja|nordea|"
              r"danske|dnb|swedbank|seb|handelsbanken|standard chartered|aib|bank of ireland|piraeus|eurobank|alpha bank|"
              r"national bank of greece|nomura|mitsubishi ufj|mufg|bff bank|banca ifis|illimity|bradesco",
    "Assicurazioni": r"generali|assicurazioni generali|allianz|axa|zurich|munchener ruck\w*|muenchener rueck\w*|munich re|"
                     r"hannover re|swiss re|aviva|prudential|legal & general|legal general|aegon|nn group|ageas|mapfre|"
                     r"unipol|talanx|scor|sampo|admiral|metlife|metropolitan life|aig|american international group|chubb|"
                     r"progressive",
    "Finanza": r"nexi|klarna|fiserv|visa|mastercard|american express|paypal|block inc|adyen|worldline|blackrock|"
               r"amundi|azimut|anima|euronext|deutsche boerse|london stock exchange|exor|investor ab|kkr|blackstone|"
               r"apollo global|berkshire|dws|schroders|eqt|partners group|robinhood|sofi|invesco|cme group|affirm|"
               r"carlyle|s&p global|moody s|lazard|jefferies|interactive brokers|charles schwab|brookfield",
    "Crypto": r"coinbase|mara holdings|marathon digital|cleanspark|riot platforms|galaxy digital|microstrategy|strategy inc|"
              r"mstr|bitmine|bitcoin|ethereum",
    "Tecnologia": r"apple|microsoft|alphabet|google|amazon|meta platforms|facebook|nvidia|amd|advanced micro\w*|intel|"
                  r"broadcom|qualcomm|texas instruments|micron|marvell|arm holdings?|asml|asm international|infineon|"
                  r"stmicroelectronics|nxp|tsmc|taiwan semiconductor|samsung|sk hynix|applied materials|lam research|kla|"
                  r"on semiconductor|microchip|sap|oracle|salesforce|adobe|servicenow|palantir|snowflake|crowdstrike|"
                  r"palo alto|fortinet|zscaler|cloudflare|datadog|mongodb|shopify|uber|netflix|spotify|alibaba|tencent|"
                  r"baidu|jd com|pdd|pinduoduo|meituan|xiaomi|sony|nintendo|ibm|international business machines|cisco|dell|"
                  r"hp|hewlett|super micro|supermicro|accenture|capgemini|dassault systemes|nokia|ericsson|reply|"
                  r"soundhound|prosus|symbotic|hitachi|lenovo|nebius|coreweave|sea limited|sea ltd|mercadolibre|intuit|"
                  r"autodesk|workday|atlassian|unity software|roblox|zoom|docusign|okta|twilio|amkor|wolfspeed|lattice|"
                  r"globalfoundries|soitec|aixtron|be semiconductor|besi|tokyo electron|advantest|keyence|teradyne|"
                  r"applovin|rubrik|ionq|rigetti|d wave|quantum computing|dropbox|pinterest|snap|electronic arts|"
                  r"take two|take 2|ubisoft|technoprobe|sesa|tinexta|c3 ai|sandisk|coherent|space exploration|spacex|"
                  r"rocket lab|uipath|cerebras|synopsys|cadence|planet labs|vertiv|ast spacemobile|reddit|circle internet|"
                  r"applied optoelectronics|panasonic|lumentum|ciena|arista|astera|credo|pure storage|western digital|"
                  r"seagate|nutanix|ams osram|twitter|sportradar|softbank|hubspot|gopro|fair isaac|corning|amphenol|"
                  r"duolingo|bending spoons|mobileye|lyft|ebay|etsy|horizon robotics|contemporary amperex|tech adv",
    "Telecom e media": r"telecom italia|telecom|telefonica|orange|deutsche telekom|vodafone|bt group|swisscom|proximus|kpn|"
                       r"at&t|at t|verizon|t mobile|comcast|walt disney|disney|warner|paramount|mediaset|vivendi|"
                       r"rai way|inwit|infrastrutture wireless|charter communications|liberty global|iliad|fastweb|"
                       r"echostar|fibercop|iqiyi|roku|skydance|trump media|prosiebensat\w*|cellnex|universal music",
    "Energia": r"eni|siemens energy|shell|bp|totalenergies|total se|repsol|equinor|galp|omv|chevron|exxon|exxon mobil|"
               r"conocophillips|occidental|petrobras|saipem|tenaris|technip|schlumberger|slb|halliburton|baker hughes|"
               r"neste|aker|var energi|petroleos|pemex|cnooc|petrochina|sinopec|marathon petroleum|valero|phillips 66|"
               r"devon|sunrun|first solar|enphase|solaredge|vestas|siemens gamesa|nordex|plug power|bloom energy|"
               r"cameco|oklo|nuscale|nexgen|energy fuels|x energy|maire|saras|erg|vallourec|ballard power|"
               r"array technologies|eos energy|t1 energy",
    "Utility": r"enel|engie|verbund|american electric power|iberdrola|edp|e on|eon|rwe|veolia|snam|terna|italgas|a2a|"
               r"hera|iren|acea|naturgy|gas naturale|endesa|national grid|orsted|rsted|sse plc|centrica|fortum|uniper|"
               r"edison|nextera|duke energy|southern co|dominion|redeia|red electrica|elia|vistra|constellation energy|"
               r"nrg|nrg energy|exelon|enagas",
    "Auto": r"stellantis|ferrari|bayerische motoren\w*|volkswagen|vw|bmw|mercedes|mercedes benz|daimler|porsche|renault|"
            r"toyota|honda|nissan|hyundai|kia|ford|ford motor|general motors|rivian|lucid|nio|xpeng|li auto|byd|geely|"
            r"volvo car|volvo ab|volvo|polestar|pirelli|michelin|continental|aumovio|valeo|forvia|faurecia|brembo|"
            r"iveco|cnh industrial|traton|daimler truck|scania|lear|aptiv|magna|tesla|harley davidson|goodyear|"
            r"jaguar land rover",
    "Industria e difesa": r"leonardo|prysmian|fincantieri|rheinmetall|thales|safran|airbus|bae systems|dassault aviation|"
                          r"saab|hensoldt|renk|kongsberg|lockheed|northrop|raytheon|rtx|general dynamics|boeing|"
                          r"huntington ingalls|axon enterprise|howmet|general electric|ge aerospace|ge vernova|siemens|"
                          r"schneider|abb|alstom|vinci|ferrovial|webuild|danieli|interpump|atlas copco|sandvik|caterpillar|"
                          r"deere|honeywell|3m|emerson|eaton|rolls royce|mtu|mtu aero|thyssenkrupp|tkms|tka|kone|legrand|"
                          r"saint gobain|holcim|heidelberg materials|buzzi|cementir|avio|fluidra|wartsila|komatsu|fanuc|"
                          r"mitsubishi heavy|ihi|carrier|otis|trane|parker hannifin|weichai|leonardo drs|intuitive machines|"
                          r"quanta services|kion|randstad|adecco|industrie de nora|bouygues|vistry|toll brothers",
    "Trasporti e turismo": r"air france|klm|air france klm|lufthansa|easyjet|ryanair|iag|international airlines|"
                           r"american airlines|delta air|united airlines|united air|southwest|norwegian cruise|carnival|"
                           r"royal caribbean|tui|accor|marriott|hilton|expedia|trip com|tripadvisor|booking|"
                           r"booking holdings|airbnb|amadeus|aeroporti|aena|fraport|atlantia|mundys|autogrill|maersk|"
                           r"moller maersk|hapag|hapag lloyd|enav|hertz|kuehne|dhl|deutsche post|ups|united parcel|"
                           r"fedex|xpo|flutter|lottomatica|evolution",
    "Consumi e lusso": r"lvmh|kering|hermes|prada|moncler|richemont|cucinelli|brunello cucinelli|burberry|tapestry|capri|"
                       r"ralph lauren|estee lauder|l oreal|loreal|beiersdorf|unilever|nestle|danone|procter|colgate|"
                       r"kimberly|coca cola|pepsico|ab inbev|anheuser|heineken|carlsberg|diageo|pernod|remy|campari|"
                       r"davide campari|lindt|mondelez|kraft|kraft heinz|ferrero|nike|adidas|puma|inditex|"
                       r"industria de diseno|h&m|hennes|zalando|walmart|costco|target corp|home depot|lowe|carrefour|"
                       r"ahold|tesco|sainsbury|ocado|jeronimo|mcdonald|starbucks|chipotle|yum|restaurant brands|"
                       r"philip morris|british american tobacco|imperial brands|altria|essilorluxottica|luxottica|"
                       r"safilo|de longhi|delonghi|ferragamo|salvatore ferragamo|tod s|swatch|pandora|lululemon|deckers|"
                       r"on holding|birkenstock|reckitt|benckiser|henkel|kenvue|haleon|ulta|church & dwight|clorox|"
                       r"beyond meat|hellofresh|delivery hero|pvh|under armour|hugo boss|gamestop|best buy|dollar general|"
                       r"peloton|general mills|dick s sporting|victoria s secret|skechers|li ning|vf corp|tate & lyle|"
                       r"shake shack|monster beverage|macys|levi strauss|gap|crocs|darling ingredients|"
                       r"constellation brands|compass group|budweiser|autozone|o reilly automotive",
    "Salute": r"pfizer|moderna|biontech|novo nordisk|novo|eli lilly|lilly|roche|novartis|sanofi|astrazeneca|gsk|glaxo|"
              r"glaxosmithkline|bayer|merck|johnson & johnson|j&j|abbvie|bristol myers|amgen|gilead|regeneron|vertex|"
              r"biogen|takeda|daiichi|astellas|teva|viatris|recordati|diasorin|amplifon|fresenius|siemens healthineers|"
              r"philips|medtronic|abbott|stryker|boston scientific|intuitive surgical|edwards|zimmer|smith & nephew|"
              r"coloplast|sonova|straumann|alcon|lonza|sartorius|qiagen|grifols|ucb|argenx|genmab|unitedhealth|cvs|"
              r"elevance|anthem|centene|molina|cigna|humana|hca|danaher|thermo fisher|illumina|dexcom|insulet|hims|"
              r"johnson and johnson|novavax|curevac|zealand|galapagos|ipsen|align technology|siegfried|sandoz|galderma|crispr|chugai",
    "Materie prime": r"anglogold|newmont|barrick|agnico|kinross|gold fields|harmony gold|first majestic|pan american silver|"
                     r"hecla|wheaton|franco nevada|royal gold|freeport|rio tinto|bhp|glencore|anglo american|vale|teck|"
                     r"antofagasta|boliden|norsk hydro|alcoa|arcelormittal|nucor|steel dynamics|cleveland cliffs|"
                     r"albemarle|sqm|lithium|livent|mp materials|lynas|umicore|basf|covestro|lanxess|evonik|solvay|"
                     r"syensqo|arkema|akzo|dsm|dsm firmenich|air liquide|linde|air products|yara|k s|mosaic|nutrien|"
                     r"stora enso|upm|smurfit|southern copper|zijin|ivanhoe|coeur|endeavour|silvercorp|sibanye|impala|"
                     r"northam|buenaventura|international flavors|givaudan",
    "Immobiliare": r"vonovia|unibail|klepierre|gecina|segro|land securities|british land|leg immobilien|aroundtown|"
                   r"tag immobilien|merlin|covivio|prologis|simon property|american tower|equinix|realty income|"
                   r"digital realty|immobiliare",
}
# alternative dalla più lunga: "banca generali" non deve fermarsi a "banca"
COMPANY_RX = [(s, re.compile(r"(?<= )(?:" + "|".join(sorted(rx.split("|"), key=len, reverse=True)) + r")(?= )"))
              for s, rx in COMPANIES.items()]


def _company(text):
    """Settore della società nominata nel testo: vince la corrispondenza più lunga (la più specifica)."""
    best, blen = None, 0
    for s, rx in COMPANY_RX:
        for m in rx.finditer(text):
            if len(m.group(0)) > blen:
                best, blen = s, len(m.group(0))
    return best


# parole di settore nel nome (indici settoriali e tematici); Salute prima di Tecnologia ("digital health")
RULES = [
    ("Banche", _rx([r"eurostoxx banks?", r"(euro )?stoxx( europe 600)? banks?", r"sx7e", r"sx7p", r"banks? (index|price)",
                    r"ftse italia banche", r"european banks?", r"banche"])),
    ("Assicurazioni", _rx([r"eurostoxx insurance", r"(euro )?stoxx( europe 600)? insurance", r"sxie", r"sxip", r"insurance"])),
    ("Salute", _rx([r"(euro )?stoxx( europe 600)? health ?care", r"sxdp", r"health ?care", r"healthcare", r"digital health",
                    r"pharmaceuticals?", r"pharma", r"biotech\w*", r"healthy living"])),
    ("Tecnologia", _rx([r"quantum", r"robot\w*", r"qqq", r"eurostoxx technology", r"(euro )?stoxx( europe 600)? technology", r"sx8e", r"sx8p", r"nasdaq( 100)?",
                        r"ndx", r"philadelphia semiconductor", r"sox", r"semiconductors?", r"artificial intelligence",
                        r"ai effect", r"ai index", r"ai", r"tech titans", r"technolog\w*", r"cybersecurity", r"digital",
                        r"metaverse", r"robotics", r"tech", r"cloud", r"cloud computing", r"innovation", r"hang seng tech",
                        r"hstech"])),
    ("Energia", _rx([r"eurostoxx oil ?(&|and)? ?gas", r"(euro )?stoxx( europe 600)? oil ?(&|and)? ?gas", r"sxee", r"sxep",
                     r"oil & gas", r"oil", r"energy", r"energies", r"wti", r"brent", r"crude oil", r"petrolio", r"natural gas",
                     r"nuclear", r"clean energy", r"solar"])),
    ("Utility", _rx([r"eurostoxx utilities", r"(euro )?stoxx( europe 600)? utilities", r"sx6e", r"sx6p", r"utilities", r"water"])),
    ("Auto", _rx([r"(euro )?stoxx( europe 600)? automobiles", r"sxae", r"sxap", r"stoxx auto", r"automobiles?"])),
    ("Materie prime", _rx([r"cmci", r"(euro )?stoxx( europe 600)? basic resources", r"sxpp", r"basic resources", r"gold", r"silver",
                           r"oro", r"argento", r"platinum", r"palladium", r"copper", r"rame", r"aluminium", r"alluminio",
                           r"zinc", r"nickel", r"uranium", r"rare earth", r"strategic metals", r"lbma", r"metals?", r"miners?",
                           r"mining", r"gsci", r"commodit\w*"])),
    ("Industria e difesa", _rx([r"def sect", r"defen[cs]e", r"aerospace", r"sovereignty", r"industrial goods?( & services?)?",
                                r"industrial good & service", r"sxnp", r"construction (& |and )?materials", r"sxop"])),
    ("Consumi e lusso", _rx([r"luxury", r"top brands", r"smart food", r"food", r"retail"])),
    ("Telecom e media", _rx([r"telecommunications?", r"sxke", r"sxkp", r"media"])),
    ("Immobiliare", _rx([r"real estate", r"reit"])),
    ("Crypto", _rx([r"bitcoin", r"ethereum", r"crypto\w*", r"btc", r"solana"])),
    ("Tassi e credito", _rx([r"euribor", r"sofr", r"\w*str", r"cms", r"irs", r"swap rate", r"treasury", r"btps?", r"bund",
                             r"tec ?10", r"govt", r"constant maturity", r"interest rate", r"yield", r"callable notes",
                             r"\d+(\.\d+)?%"])),
]
INDICI = _rx([r"amc", r"portfolio", r"bkt", r"euronext", r"idx", r"climate", r"sxxp", r"nikk", r"ftse ?100", r"seldiv ?30", r"sel div ?30", r"global select div \d+",
              r"euro ?stoxx ?50", r"stoxx ?50", r"sx5e", r"es50", r"stoxx europe 600", r"stoxx 600", r"s ?& ?p ?500", r"s and p 500",
              r"s p 500", r"spx", r"dow jones( industrial)?", r"djia", r"russell 2000", r"ftse mib", r"ftsemib", r"fmib", r"ftmib",
              r"ftse 100", r"dax", r"cac 40", r"cac", r"ibex( 35)?", r"aex", r"smi", r"nikkei ?( 225)?", r"nky", r"n225", r"topix",
              r"hang seng", r"hscei", r"kospi( 200)?", r"csi \d+", r"msci", r"omx", r"asx 200", r"world", r"emerging markets?",
              r"global titans", r"titans", r"esg", r"eurozone", r"euro 50", r"equal weight", r"select dividend", r"dividend",
              r"sd3e", r"essd30", r"ishares", r"spdr", r"vanguard", r"etf", r"index", r"indice", r"basket", r"paniere",
              r"strategy", r"fund", r"fondo", r"theam quant", r"istoxx 50", r"decrement", r"infrastructure", r"equity"])


def classify(name, yahoo=None):
    """Settore di un sottostante. yahoo: voce della mappa (yahooName, type, sector, industry) se c'è."""
    yahoo = yahoo or {}
    n = _n(name)
    m = re.match(r" (?:leonteq |euro )?istoxx (?:single stock on )?(.+?) gr decrement", n) or \
        re.match(r" leonteq single stock (.+?) decrement", n)
    if m:  # indice su una sola azione: conta l'azione (se la riconosce)
        s = classify(m.group(1))
        if s:
            return s
    nx = re.sub(r" (mi|im|fr|fp|ny|us|it|gy|gr|ln|na|sm|pa|de) $", " ", n)  # suffisso di borsa ("STM MI")
    if nx != n and nx.strip() in EXACT:
        return EXACT[nx.strip()]
    if n.strip() in EXACT:
        return EXACT[n.strip()]
    if DEBT.search(n):
        return "Tassi e credito"
    if FX.search(n):
        return "Valute"
    is_idx = bool(IDX.search(n))
    nc = re.sub(r" +", " ", BRANDS.sub(" ", n)) if is_idx else n
    s = _company(nc)
    if s:
        return s
    for s, rx in RULES:
        if rx.search(n):
            return s
    yn = _n(yahoo.get("yahooName"))
    ytype = (yahoo.get("type") or "").upper()
    if not is_idx and ytype in ("", "EQUITY") and not IDX.search(yn):
        s = _company(yn)
        if s:
            return s
    ind = " ".join(str(yahoo.get(k) or "") for k in ("industry", "sector"))
    if ind.strip() and ytype in ("", "EQUITY"):
        for rx, s in YAHOO_RX:
            if rx.search(ind):
                return s
    if ytype in ("INDEX", "ETF", "MUTUALFUND") or INDICI.search(n):
        return "Indici"
    return None


def classify_name(name, lookup):
    """Come classify, ma un nome che elenca più sottostanti ("Adidas, Netflix, UniCredit") vale per tutti:
    lookup(nome) restituisce la voce Yahoo della mappa."""
    parts = [p.strip() for p in re.split(r",|;| \+ ", str(name or "")) if len(p.strip()) >= 3]
    if len(parts) >= 2:
        return cert_sector([classify(p, lookup(p)) for p in parts])
    s = classify(name, lookup(name))
    parts = [p.strip() for p in re.split(r" and ", str(name or ""), flags=re.I) if len(p.strip()) >= 3]
    if s is None and len(parts) >= 2:  # "MPS AND ESXX BANKS", ma non "Johnson and Johnson"
        return cert_sector([classify(p, lookup(p)) for p in parts])
    return s


# industria Yahoo (inglese) -> settore
YAHOO = [
    (r"bank", "Banche"), (r"insurance", "Assicurazioni"),
    (r"semiconductor|software|information technology|internet|computer|electronic|communication equipment|"
     r"technology|it services|consumer electronics|scientific & technical", "Tecnologia"),
    (r"capital markets|asset management|credit services|financial|exchange|shell companies", "Finanza"),
    (r"telecom|entertainment|media|publishing|broadcasting|advertising", "Telecom e media"),
    (r"utilit", "Utility"),
    (r"oil|gas|energy|coal|solar|uranium", "Energia"),
    (r"auto|vehicle|truck", "Auto"),
    (r"aerospace|defense|industrial|machinery|engineering|construction|building|electrical equipment|"
     r"conglomerate|tools|waste|security|staffing|consulting|business services|specialty business", "Industria e difesa"),
    (r"airline|travel|lodging|resort|casino|gambling|cruise|railroad|trucking|marine shipping|"
     r"integrated freight|airport|logistics", "Trasporti e turismo"),
    (r"drug|pharma|biotech|medical|health|diagnostic", "Salute"),
    (r"gold|silver|metal|mining|steel|aluminum|copper|chemical|agricultural inputs|paper|lumber|"
     r"basic materials", "Materie prime"),
    (r"reit|real estate", "Immobiliare"),
    (r"luxury|apparel|footwear|beverage|food|tobacco|household|personal products|restaurant|retail|"
     r"grocery|department|home improvement|furnishings|consumer|packaged|confectioner|leisure|"
     r"recreational|education", "Consumi e lusso"),
]
YAHOO_RX = [(re.compile(rx, re.I), s) for rx, s in YAHOO]


def cert_sector(sectors):
    """Settore del certificato dai settori dei sottostanti: uno solo -> quello; più di uno -> "Misto"."""
    known = [s for s in sectors if s]
    if not known:
        return None
    u = list(dict.fromkeys(known))
    return u[0] if len(u) == 1 else "Misto"
