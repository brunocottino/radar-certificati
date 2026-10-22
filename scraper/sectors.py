"""Settore di ogni sottostante e del certificato (tutti dello stesso settore -> quel settore, altrimenti "Misto").

Fonti, in ordine: regole sul nome (indici settoriali, tassi, valute, materie prime, società note), poi il settore e
l'industria che Yahoo Finance assegna al ticker (raccolti da risk.py nella mappa dei sottostanti).
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


# regole sul nome: la prima che corrisponde vince (prima gli indici settoriali, poi le categorie, poi le società)
RULES = [
    # indici e panieri settoriali
    ("Banche", _rx([r"eurostoxx banks?", r"(euro )?stoxx( europe 600)? banks?", r"sx7e", r"sx7p", r"banks? (index|price)", r"ftse italia banche",
                    r"european banks?", r"banche"])),
    ("Assicurazioni", _rx([r"eurostoxx insurance", r"(euro )?stoxx( europe 600)? insurance", r"sxie", r"sxip"])),
    ("Tecnologia", _rx([r"eurostoxx technology", r"(euro )?stoxx( europe 600)? technology", r"sx8e", r"sx8p", r"nasdaq( 100)?", r"ndx", r"philadelphia semiconductor",
                        r"sox", r"semiconductor", r"artificial intelligence", r"ai effect", r" ai index", r"tech titans", r"technology",
                        r"cybersecurity", r"digital", r"metaverse", r"robotics", r"tech"])),
    ("Energia", _rx([r"eurostoxx oil ?(&|and)? ?gas", r"(euro )?stoxx( europe 600)? oil ?(&|and)? ?gas", r"sxee", r"sxep", r"oil & gas", r"energy", r"wti", r"brent",
                     r"crude oil", r"natural gas", r"nuclear", r"clean energy"])),
    ("Utility", _rx([r"eurostoxx utilities", r"(euro )?stoxx( europe 600)? utilities", r"sx6e", r"sx6p", r"utilities", r"water"])),
    ("Auto", _rx([r"(euro )?stoxx( europe 600)? automobiles", r"sxae", r"sxap", r"stoxx auto", r"automobiles?"])),
    ("Salute", _rx([r"(euro )?stoxx( europe 600)? health ?care", r"sxdp", r"health ?care", r"healthcare", r"pharmaceuticals?",
                    r"biotech\w*", r"healthy living"])),
    ("Materie prime", _rx([r"(euro )?stoxx( europe 600)? basic resources", r"sxpp", r"basic resources", r"gold", r"silver", r"oro", r"argento",
                           r"platinum", r"palladium", r"copper", r"rame", r"aluminium", r"alluminio", r"zinc", r"nickel",
                           r"uranium", r"rare earth", r"strategic metals", r"lbma", r"metals?"])),
    ("Industria e difesa", _rx([r"defen[cs]e", r"aerospace", r"sovereignty", r"industrial goods", r"sxnp"])),
    ("Consumi e lusso", _rx([r"luxury", r"top brands", r"smart food", r"food", r"retail"])),
    ("Telecom e media", _rx([r"telecommunications?", r"sxke", r"sxkp", r"media"])),
    ("Immobiliare", _rx([r"real estate", r"reit"])),
    ("Crypto", _rx([r"bitcoin", r"ethereum", r"crypto\w*", r"btc", r"solana"])),
    ("Tassi e credito", _rx([r"euribor", r"sofr", r"\w*str", r"cms", r"irs", r"swap rate", r"treasury", r"btps?", r"bund", r"tec ?10",
                             r"govt", r"constant maturity", r"creditworthiness", r"debito", r"debt", r"interest rate", r"yield",
                             r"callable notes", r"\d+(\.\d+)?% "])),
    ("Valute", _rx([r"eur ?/ ?usd", r"eur usd", r"eur versus \w+", r"usd ?/ ?\w{3}", r"eurusd", r"fx"])),
    ("Indici", _rx([r"euro ?stoxx ?50", r"stoxx ?50", r"sx5e", r"es50", r"stoxx europe 600", r"stoxx 600", r"s ?& ?p ?500", r"s and p 500",
                    r"s p 500", r"spx", r"dow jones( industrial)?", r"djia", r"russell 2000", r"ftse mib", r"ftsemib", r"fmib", r"ftmib",
                    r"ftse 100", r"dax", r"cac 40", r"cac", r"ibex", r"aex", r"smi", r"nikkei( 225)?", r"nky", r"n225", r"topix",
                    r"hang seng", r"hscei", r"kospi( 200)?", r"csi \d+", r"msci (world|emerging|europe|usa|china|japan|brazil|south korea|india|em)\w*",
                    r"ishares msci \w+( \w+)?", r"msci", r"world", r"emerging markets?", r"global titans", r"titans", r"esg",
                    r"eurozone", r"euro 50", r"equal weight", r"select dividend", r"dividend", r"sd3e", r"essd30", r"ishares",
                    r"spdr", r"vanguard", r"etf", r"istoxx 50", r"decrement", r"quant\w*", r"index", r"indice", r"basket", r"paniere", r"strategy", r"fund"])),
]

# società: parole chiave nel nome (Yahoo completa le altre)
COMPANIES = {
    "Banche": r"unicredit|ucg|isp|intesa|bpm|barc|sg|db|julius ba\w*|bnp|societe generale|soc gen|commerzbank|deutsche bank|barclays|hsbc|lloyds|natwest|santander|"
              r"bbva|bilbao|caixabank|sabadell|bankinter|mediobanca|bper|banca|banco|bank|bancorp|monte dei paschi|mps|bmps|"
              r"credit agricole|natixis|ing groep|ing group|abn amro|kbc|erste|raiffeisen|ubs|credit suisse|julius baer|"
              r"jpmorgan|jp morgan|goldman sachs|morgan stanley|citigroup|wells fargo|bank of america|banca generali|"
              r"fineco|mediolanum|credem|popolare|unicaja|nordea|danske|dnb|swedbank|seb|handelsbanken|standard chartered|"
              r"aib|bank of ireland|piraeus|eurobank|alpha bank|nbg|national bank of greece|hsbc",
    "Assicurazioni": r"generali|allianz|progressive|american international group|munchener ruck\w*|axa|zurich|munich re|muenchener|hannover re|swiss re|aviva|prudential|legal & general|"
                     r"legal general|aegon|nn group|ageas|mapfre|unipol|poste italiane|talanx|scor|sampo|admiral|metlife|aig|chubb",
    "Finanza": r"nexi|klarna|fiserv|invesco|cme group|affirm|visa|mastercard|american express|paypal|block inc|adyen|worldline|blackrock|amundi|azimut|anima|"
               r"euronext|deutsche boerse|london stock exchange|lse|exor|investor ab|kkr|blackstone|apollo|berkshire|"
               r"banca ifis|illimity|dws|schroders|3i|eqt|partners group|robinhood|sofi",
    "Crypto": r"coinbase|mara holdings|cleanspark|microstrategy|strategy inc|mstr|marathon digital|riot platforms|galaxy digital|bitcoin|ethereum",
    "Tecnologia": r"apple|microsoft|c3 ai|sandisk|coherent|space exploration|spacex|rocket lab|uipath|cerebras|synopsys|cadence|"
                  r"planet labs|vertiv|ast spacemobile|reddit|circle internet|applied optoelectronics|panasonic|lumentum|ciena|"
                  r"arista|astera|credo|pure storage|western digital|seagate|nutanix|alphabet|google|amazon|meta platforms|facebook|nvidia|amd|advanced micro|intel|"
                  r"broadcom|qualcomm|texas instruments|micron|marvell|arm holdings|asml|asm international|infineon|"
                  r"stmicroelectronics|stm|nxp|tsmc|taiwan semiconductor|samsung|sk hynix|applied materials|lam research|"
                  r"kla|on semiconductor|sap|oracle|salesforce|adobe|servicenow|palantir|snowflake|crowdstrike|"
                  r"palo alto|fortinet|zscaler|cloudflare|datadog|mongodb|shopify|uber|airbnb|booking|"
                  r"netflix|spotify|alibaba|tencent|baidu|jd com|pdd|meituan|xiaomi|sony|nintendo|ibm|cisco|dell|hp|"
                  r"hewlett|super micro|supermicro|accenture|capgemini|dassault systemes|nokia|ericsson|reply|"
                  r"siemens energy|soundhound|prosus|symbotic|hitachi|lenovo|nebius|coreweave|sea limited|mercadolibre|intuit|autodesk|workday|"
                  r"atlassian|unity|roblox|zoom|docusign|okta|twilio|amkor|wolfspeed|lattice|globalfoundries|"
                  r"soitec|aixtron|be semiconductor|besi|tokyo electron|advantest|keyence|teradyne|pinduoduo|"
                  r"applovin|rubrik|ionq|rigetti|d wave|quantum|anthropic|openai|dropbox|pinterest|snap|"
                  r"electronic arts|take two|ubisoft|universal music|technoprobe|cellnex|el en|sesa|tinexta",
    "Telecom e media": r"telecom|tim|echostar|telefonica|orange|deutsche telekom|vodafone|bt group|swisscom|proximus|kpn|"
                       r"at&t|at t|verizon|t mobile|comcast|walt disney|disney|warner|paramount|mediaset|mfe|vivendi|"
                       r"rai way|inwit|infrastrutture wireless|charter communications|liberty global|iliad|fastweb",
    "Energia": r"eni|shell|bp|totalenergies|total|repsol|equinor|galp|omv|chevron|exxon|"
               r"conocophillips|occidental|petrobras|saipem|tenaris|technip|schlumberger|slb|halliburton|baker hughes|"
               r"neste|aker|var energi|petroleos|pemex|cnooc|petrochina|sinopec|marathon petroleum|valero|"
               r"phillips 66|spm|sunrun|first solar|enphase|solaredge|vestas|siemens gamesa|orsted|nordex|plug power|"
               r"cameco|oklo|nuscale|maire|saras|erg",
    "Utility": r"enel|engie|verbund|american electric power|iberdrola|edp|e on|eon|rwe|veolia|snam|terna|italgas|a2a|hera|iren|acea|naturgy|endesa|"
               r"national grid|orsted|rsted|ssen|sse plc|centrica|fortum|uniper|edison|nextera|duke energy|southern co|"
               r"dominion|redeia|red electrica|elia|vistra|constellation energy",
    "Auto": r"stellantis|ferrari|bayerische motoren\w*|volkswagen|vw|bmw|mercedes|daimler|porsche|renault|toyota|honda|nissan|hyundai|kia|"
            r"ford|general motors|gm|rivian|lucid|nio|xpeng|li auto|byd|geely|volvo car|polestar|pirelli|michelin|"
            r"continental|aumovio|valeo|forvia|faurecia|brembo|iveco|cnh|traton|daimler truck|scania|"
            r"lear|aptiv|magna|stla|tesla",
    "Industria e difesa": r"leonardo|ldo|prysmian|intuitive machines|fincantieri|rheinmetall|thales|safran|airbus|bae systems|dassault aviation|saab|"
                          r"hensoldt|renk|kongsberg|lockheed|northrop|raytheon|rtx|general dynamics|boeing|"
                          r"general electric|ge aerospace|ge vernova|siemens|schneider|abb|alstom|vinci|"
                          r"ferrovial|webuild|danieli|interpump|atlas copco|sandvik|caterpillar|deere|"
                          r"honeywell|3m|emerson|eaton|rolls royce|mtu|thyssenkrupp|tkms|kone|legrand|"
                          r"saint gobain|holcim|heidelberg materials|buzzi|cementir|avio|fluidra|wartsila|"
                          r"komatsu|fanuc|mitsubishi heavy|carrier|otis|trane|parker hannifin|dhl|deutsche post|"
                          r"ups|fedex|cnh industrial|weichai|leonardo drs",
    "Trasporti e turismo": r"air france|klm|hertz|kuehne|lufthansa|easyjet|ryanair|iag|international airlines|american airlines|"
                           r"delta air|united airlines|southwest|norwegian cruise|carnival|royal caribbean|"
                           r"tui|accor|marriott|hilton|expedia|trip com|amadeus|aeroporti|aena|fraport|"
                           r"atlantia|mundys|autogrill|maersk|hapag|msc|enav|flutter|lottomatica|evolution",
    "Consumi e lusso": r"lvmh|kering|beyond meat|hellofresh|delivery hero|pvh|under armour|hugo boss|gamestop|best buy|rh|"
                       r"dollar general|peloton|altria|general mills|hermes|prada|moncler|richemont|cucinelli|brunello|burberry|tapestry|capri|"
                       r"ralph lauren|estee lauder|l oreal|loreal|beiersdorf|unilever|nestle|danone|"
                       r"procter|colgate|kimberly|coca cola|pepsico|ab inbev|anheuser|heineken|carlsberg|"
                       r"diageo|pernod|remy|campari|davide campari|lindt|mondelez|kraft|ferrero|"
                       r"nike|adidas|puma|inditex|h&m|hennes|zalando|amazon|walmart|costco|target|"
                       r"home depot|lowe|carrefour|ahold|tesco|sainsbury|ocado|jeronimo|mcdonald|starbucks|"
                       r"chipotle|yum|restaurant brands|philip morris|british american tobacco|bat|imperial brands|"
                       r"essilorluxottica|luxottica|safilo|de longhi|delonghi|ferragamo|tod s|ovs|dick s sporting|victoria s secret|skechers|li ning|industria de diseno|"
                       r"salvatore ferragamo|swatch|pandora|lululemon|deckers|on holding|birkenstock|"
                       r"reckitt|benckiser|henkel|kenvue|haleon|ulta|sephora|church & dwight|clorox|"
                       r"tesla motors",
    "Salute": r"pfizer|anthem|centene|moderna|biontech|novo nordisk|novo|eli lilly|lilly|roche|novartis|sanofi|astrazeneca|gsk|"
              r"glaxo|bayer|merck|johnson & johnson|j&j|abbvie|bristol myers|amgen|gilead|regeneron|vertex|"
              r"biogen|takeda|daiichi|astellas|teva|viatris|recordati|diasorin|amplifon|fresenius|siemens healthineers|"
              r"philips|medtronic|abbott|stryker|boston scientific|intuitive surgical|edwards|zimmer|"
              r"smith & nephew|coloplast|sonova|straumann|alcon|lonza|sartorius|qiagen|grifols|ucb|"
              r"argenx|genmab|unitedhealth|cvs|elevance|cigna|humana|hca|danaher|thermo fisher|illumina|"
              r"dexcom|insulet|hims|novavax|curevac|zealand|galapagos|ipsen|essilor",
    "Materie prime": r"anglogold|newmont|barrick|agnico|kinross|gold fields|harmony gold|first majestic|pan american silver|"
                     r"hecla|wheaton|franco nevada|royal gold|freeport|rio tinto|bhp|glencore|anglo american|"
                     r"vale|teck|antofagasta|boliden|norsk hydro|alcoa|arcelormittal|thyssenkrupp steel|"
                     r"nucor|steel dynamics|cleveland cliffs|albemarle|sqm|lithium|livent|mp materials|"
                     r"lynas|cameco|umicore|basf|covestro|lanxess|evonik|solvay|syensqo|arkema|akzo|"
                     r"dsm|air liquide|linde|yara|k s|mosaic|nutrien|stora enso|upm|smurfit|"
                     r"southern copper|zijin|ivanhoe|coeur|endeavour|silvercorp|sibanye|impala|northam|"
                     r"mitsui|mitsubishi corp",
    "Immobiliare": r"vonovia|unibail|klepierre|gecina|segro|land securities|british land|leg immobilien|"
                   r"aroundtown|tag immobilien|merlin|covivio|prologis|simon property|american tower|equinix|"
                   r"realty income|digital realty|immobiliare",
}
COMPANY_RX = [(s, re.compile(r"(?<= )(?:" + rx + r")(?=\W| )")) for s, rx in COMPANIES.items()]

# industria Yahoo (inglese) -> settore
YAHOO = [
    (r"bank", "Banche"), (r"insurance", "Assicurazioni"),
    (r"semiconductor|software|information technology|internet|computer|electronic|communication equipment|"
     r"technology|it services|consumer electronics|scientific & technical", "Tecnologia"),
    (r"capital markets|asset management|credit services|financial|exchange|shell companies", "Finanza"),
    (r"telecom|entertainment|media|publishing|broadcasting|advertising", "Telecom e media"),
    (r"oil|gas|energy|coal|solar|uranium", "Energia"),
    (r"utilit", "Utility"),
    (r"auto|vehicle|truck", "Auto"),
    (r"aerospace|defense|industrial|machinery|engineering|construction|building|electrical equipment|"
     r"conglomerate|tools|waste|security|staffing|consulting|business services|specialty business", "Industria e difesa"),
    (r"airline|travel|lodging|resort|casino|gambling|leisure|cruise|railroad|trucking|marine shipping|"
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


def classify(name, yahoo=None):
    """Settore di un sottostante. yahoo: voce della mappa (yahooName, type, sector, industry) se c'è."""
    yahoo = yahoo or {}
    n = _n(name)
    # "iSTOXX Single Stock on Eni GR Decrement 0.88": conta la società dentro l'indice
    m = re.match(r" (?:leonteq |euro )?istoxx (?:single stock on )?(.+?) gr decrement", n) or re.match(r" leonteq single stock (.+?) decrement", n)
    if m:
        n = " " + m.group(1) + " "
    for s, rx in RULES:
        if s == "Indici":
            continue
        if rx.search(n):
            return s
    for s, rx in COMPANY_RX:
        if rx.search(n):
            return s
    yn = _n(yahoo.get("yahooName"))
    for s, rx in COMPANY_RX:
        if rx.search(yn):
            return s
    ind = " ".join(str(yahoo.get(k) or "") for k in ("industry", "sector"))
    if ind.strip():
        for rx, s in YAHOO_RX:
            if rx.search(ind):
                return s
    if (yahoo.get("type") or "").upper() in ("INDEX", "ETF") or dict(RULES)["Indici"].search(n):
        return "Indici"
    return None


def cert_sector(sectors):
    """Settore del certificato dai settori dei sottostanti: uno solo -> quello; più di uno -> "Misto"."""
    known = [s for s in sectors if s]
    if not known:
        return None
    u = list(dict.fromkeys(known))
    if len(u) == 1 and len(known) == len(sectors):
        return u[0]
    if len(u) == 1:
        return u[0]  # gli altri sottostanti non sono classificati: si usa quello noto
    return "Misto"
