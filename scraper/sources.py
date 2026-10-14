V = "https://markets.vontobel.com/it-it/prodotti/investment/"
SOURCES = [
    # elenco completo e neutro SeDeX + Cert-X con denaro/lettera: gira per primo, gli emittenti arricchiscono dopo
    {"name": "euronext", "issuer": None, "url": "https://live.euronext.com/it/markets/milan/structured-products/list", "skip_page": True, "parser": "euronext_list"},
    {"name": "vontobel_multi_cc_barriera", "issuer": "Vontobel", "type": "Multi Cash Collect", "url": V + "multi-cash-collect-certificate-con-barriera", "max_clicks": 40},
    {"name": "vontobel_cc_barriera", "issuer": "Vontobel", "type": "Cash Collect", "url": V + "cash-collect-certificate-con-barriera", "max_clicks": 20},
    {"name": "vontobel_multi_cc", "issuer": "Vontobel", "type": "Multi Cash Collect", "url": V + "multi-cash-collect-certificate", "max_clicks": 20},
    {"name": "vontobel_express", "issuer": "Vontobel", "type": "Express", "url": V + "express-certificate", "max_clicks": 20},
    {"name": "vontobel_bonus_cap", "issuer": "Vontobel", "type": "Bonus Cap", "url": V + "bonus-cap-certificate", "max_clicks": 20},
    {"name": "vontobel_fixed_cc", "issuer": "Vontobel", "type": "Fixed Cash Collect", "url": V + "fixed-cash-collect-certificate", "max_clicks": 20},
    {"name": "vontobel_phoenix", "issuer": "Vontobel", "type": "Phoenix", "url": V + "phoenix-certificate", "max_clicks": 20},
    {"name": "vontobel_cc", "issuer": "Vontobel", "type": "Cash Collect", "url": V + "cash-collect-certificate", "max_clicks": 20},
    {"name": "leonteq", "issuer": "Leonteq", "url": "https://certificati.leonteq.com/products", "max_clicks": 40, "parser": "leonteq_api"},
    {"name": "bnp_cash_collect", "issuer": "BNP Paribas", "url": "https://investimenti.bnpparibas.it/prodotti-di-investimento/cash-collect/", "max_clicks": 0, "parser": "bnp_api"},
    {"name": "socgen", "issuer": "Société Générale", "url": "https://www.prodotti.societegenerale.it/product-search", "max_clicks": 0, "parser": "socgen_api"},
    {"name": "marex", "issuer": "Marex", "url": "https://fp.marex.com/", "max_clicks": 0, "parser": "marex_probe"},
    {"name": "unicredit", "issuer": "UniCredit", "url": "https://www.onemarkets.it/it/search-page.investment.html", "max_clicks": 0, "parser": "unicredit_pages", "categories": [129830054, 1050]},
]
