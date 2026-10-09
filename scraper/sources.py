V = "https://markets.vontobel.com/it-it/prodotti/investment/"
SOURCES = [
    {"name": "vontobel_multi_cc_barriera", "issuer": "Vontobel", "type": "Multi Cash Collect", "url": V + "multi-cash-collect-certificate-con-barriera", "max_clicks": 40},
    {"name": "vontobel_cc_barriera", "issuer": "Vontobel", "type": "Cash Collect", "url": V + "cash-collect-certificate-con-barriera", "max_clicks": 20},
    {"name": "vontobel_multi_cc", "issuer": "Vontobel", "type": "Multi Cash Collect", "url": V + "multi-cash-collect-certificate", "max_clicks": 20},
    {"name": "vontobel_cc", "issuer": "Vontobel", "type": "Cash Collect", "url": V + "cash-collect-certificate", "max_clicks": 20},
    {"name": "leonteq", "issuer": "Leonteq", "url": "https://certificati.leonteq.com/products", "max_clicks": 40, "parser": "leonteq_api"},
    {"name": "bnp_cash_collect", "issuer": "BNP Paribas", "url": "https://investimenti.bnpparibas.it/prodotti-di-investimento/cash-collect/", "max_clicks": 0, "parser": "bnp_api"},
    {"name": "socgen", "issuer": "Société Générale", "url": "https://www.prodotti.societegenerale.it/product-search", "max_clicks": 0, "parser": "socgen_api"},
    {"name": "marex", "issuer": "Marex", "url": "https://fp.marex.com/", "max_clicks": 0, "parser": "marex_probe"},
    {"name": "unicredit", "issuer": "UniCredit", "url": "https://www.onemarkets.it/it/search-page.investment.html", "max_clicks": 0, "parser": "unicredit_pages", "categories": [129830054, 1050]},
    # complemento: prezzi da Borsa Italiana per gli ISIN UniCredit rimasti senza denaro/lettera
    {"name": "borsa_isin", "issuer": "UniCredit", "url": "https://www.borsaitaliana.it/", "skip_page": True, "parser": "borsa_isin"},
]
