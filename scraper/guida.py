"""Testi della guida ai certificati (docs/guida-certificati.html, scritta da seo.py).

Domande nella forma in cui le scrivono le persone su Google e agli assistenti IA; risposte brevi, in prima riga la risposta.
Sezioni: (titolo, [(domanda, risposta in HTML semplice)]).
"""

SECTIONS = [
    ("Le basi", [
        ("Cosa sono i certificati d'investimento?",
         "Sono strumenti finanziari derivati cartolarizzati, emessi da banche e intermediari, che replicano con regole prefissate l'andamento "
         "di uno o più sottostanti (azioni, indici, tassi, materie prime, crediti). Si comprano e vendono in borsa come un'azione: in Italia "
         "sul SeDeX di Borsa Italiana e su Cert-X/EuroTLX di Euronext. Le regole (cedole, barriera, rimborso) sono scritte nel prospetto e "
         "riassunte nel KID."),
        ("Che differenza c'è tra un certificato e un'obbligazione?",
         "L'obbligazione paga cedole e rimborso fissati in anticipo, salvo default dell'emittente. Il certificato lega cedole e rimborso al "
         "comportamento dei sottostanti: rende di più quando le condizioni sono rispettate, ma può restituire meno del capitale se il "
         "sottostante scende sotto la barriera. In entrambi i casi c'è il rischio emittente."),
        ("Quali sono i tipi di certificati più diffusi?",
         "I certificati a capitale condizionatamente protetto con cedola (<a href=\"/certificati/cash-collect\">Cash Collect</a>, "
         "<a href=\"/certificati/phoenix\">Phoenix</a>), quelli a richiamo anticipato (<a href=\"/certificati/express-autocallable\">Express e "
         "Autocallable</a>), i <a href=\"/certificati/capitale-protetto\">certificati a capitale protetto</a> (Equity Protection), i "
         "<a href=\"/certificati/bonus-cap\">Bonus Cap</a>, i <a href=\"/certificati/credit-linked\">Credit Linked</a> e i certificati a leva."),
        ("Cos'è un certificato Cash Collect?",
         "È un certificato che paga cedole periodiche se, alla data di osservazione, il sottostante (o il peggiore dei sottostanti) è sopra "
         "il livello trigger. A scadenza restituisce il nominale se il sottostante è sopra la barriera capitale; altrimenti rimborsa un "
         "importo pari alla sua performance. Molti hanno anche l'effetto memoria e il rimborso anticipato."),
        ("Cos'è un certificato Phoenix?",
         "È un certificato a cedole condizionate con possibilità di rimborso anticipato (autocall): se a una data di osservazione i "
         "sottostanti sono sopra il livello di richiamo, il certificato si chiude restituendo nominale e cedola. Quasi sempre ha "
         "l'effetto memoria."),
        ("Cos'è un certificato Express?",
         "È un certificato che punta al rimborso anticipato: a ogni data di osservazione, se il sottostante è sopra il livello di "
         "richiamo, rimborsa il nominale più un premio che cresce con il tempo. Se non viene mai richiamato, a scadenza la protezione "
         "dipende dalla barriera."),
        ("Cos'è un certificato Credit Linked?",
         "È un certificato le cui cedole e il cui rimborso dipendono dal merito di credito di uno o più enti di riferimento (società, "
         "banche o Stati). Paga una cedola, spesso fissa, finché non si verifica un evento di credito (default, ristrutturazione) "
         "di un ente di riferimento; in quel caso il rimborso si riduce."),
        ("Cos'è un certificato Equity Protection?",
         "È un certificato a capitale protetto: a scadenza restituisce almeno la percentuale protetta del nominale (per esempio il 90% "
         "o il 100%) e partecipa al rialzo del sottostante, a volte con un tetto massimo (cap). La protezione vale solo a scadenza "
         "e non copre il default dell'emittente."),
        ("Cosa sono i certificati Bonus Cap?",
         "Pagano a scadenza un bonus prefissato se il sottostante non ha mai toccato la barriera (o non è sotto la barriera a scadenza, "
         "secondo il prodotto); il guadagno massimo è limitato dal cap. Se la barriera viene violata, il certificato segue il sottostante."),
        ("Cosa sono i Maxi Cash Collect?",
         "Sono Cash Collect che pagano una prima cedola molto alta (anche oltre il 10-20% del nominale) poco dopo l'emissione e poi cedole "
         "più piccole. Dopo lo stacco della maxi cedola il prezzo scende di un importo simile: non è un guadagno gratuito. Elenco aggiornato: "
         "<a href=\"/certificati/maxi-cash-collect\">certificati Maxi Cash Collect</a>."),
        ("Cosa sono i certificati Low Barrier?",
         "Sono certificati con la barriera capitale molto bassa, di solito tra il 30% e il 50% del valore iniziale: il sottostante deve "
         "perdere più della metà prima che il capitale sia a rischio. In cambio le cedole sono più contenute. Vedi i "
         "<a href=\"/certificati/barriera-bassa\">certificati con barriera bassa</a>."),
        ("Dove si comprano i certificati?",
         "In borsa, tramite la propria banca o il proprio broker, come un'azione: basta l'ISIN. In Italia sono quotati sul SeDeX di Borsa "
         "Italiana, su Cert-X/EuroTLX di Euronext e su Vorvel. Alcuni si sottoscrivono anche in collocamento, prima della quotazione."),
        ("Meglio i certificati o gli ETF?",
         "Sono strumenti diversi. L'ETF replica un mercato e ne segue per intero salite e discese, con costi bassi e senza rischio emittente "
         "sul patrimonio. Il certificato ha un profilo costruito (cedole, barriera, protezione) e una scadenza, ma porta rischio emittente e "
         "regole più complesse. Dipende dall'obiettivo: non esiste una risposta valida per tutti."),
    ]),
    ("Le caratteristiche da capire", [
        ("Cos'è la barriera di un certificato?",
         "È il livello del sottostante, espresso in percentuale dello strike (il valore iniziale), sotto il quale il capitale non è più "
         "protetto. Con una barriera al 60%, a scadenza si riceve il nominale se il sottostante peggiore ha perso meno del 40%; se ha "
         "perso di più, si riceve un importo pari alla sua performance."),
        ("Che differenza c'è tra barriera a scadenza e barriera continua?",
         "La barriera a scadenza (europea) conta solo l'ultimo giorno: cosa succede nel mezzo non importa. La barriera continua (americana) "
         "si considera violata se il sottostante la tocca anche una sola volta durante la vita del certificato: è più rischiosa."),
        ("Cos'è la distanza dalla barriera?",
         "È quanto il sottostante può ancora scendere prima di toccare la barriera, in percentuale del prezzo attuale. Una distanza del 30% "
         "significa che il sottostante peggiore può perdere un altro 30% prima di mettere a rischio il capitale. Il radar la mostra per "
         "ogni certificato, insieme alla probabilità stimata che la barriera tenga."),
        ("Cos'è il trigger cedola?",
         "È il livello, in percentuale dello strike, sopra il quale il sottostante deve trovarsi alla data di osservazione perché la cedola "
         "venga pagata. Spesso coincide con la barriera capitale, a volte è più alto."),
        ("Cos'è l'effetto memoria?",
         "Se a una data di osservazione la cedola non viene pagata perché il sottostante è sotto il trigger, con l'effetto memoria non va "
         "persa: viene pagata insieme alla prima cedola successiva in cui la condizione torna rispettata. "
         "<a href=\"/certificati/effetto-memoria\">Vedi i certificati con effetto memoria</a>."),
        ("Cosa vuol dire autocall o rimborso anticipato?",
         "Alle date previste, se i sottostanti sono sopra il livello di richiamo (spesso il 100% dello strike, a volte decrescente: "
         "step-down), il certificato si chiude in anticipo e rimborsa nominale più cedola. Nei softcallable è l'emittente a poter "
         "decidere il rimborso anticipato."),
        ("Cosa significa worst of?",
         "Nei certificati su più sottostanti (basket worst of) conta solo il peggiore: cedole, richiamo e rimborso dipendono dal titolo "
         "che ha fatto peggio rispetto al proprio strike. Più sottostanti significa cedole più alte ma rischio più alto."),
        ("Cosa sono denaro e lettera?",
         "Il denaro (bid) è il prezzo a cui il market maker compra il certificato da chi vende; la lettera (ask) è il prezzo a cui lo vende "
         "a chi compra. La differenza è lo spread, un costo implicito. Il radar mostra entrambi."),
        ("Cos'è il KID di un certificato?",
         "Il KID (Key Information Document) è il documento di 3 pagine, obbligatorio, con caratteristiche, rischi, scenari e costi del "
         "prodotto. Va letto prima di comprare insieme ai Final Terms (term sheet)."),
        ("Cos'è lo strike di un certificato?",
         "È il valore iniziale del sottostante, fissato all'emissione: barriera, trigger cedola e livello di rimborso anticipato sono espressi "
         "in percentuale dello strike. Una barriera al 60% su uno strike di 10 euro è a 6 euro."),
        ("Cosa vuol dire che un certificato è sotto la pari?",
         "Che quota sotto il suo valore nominale (per esempio 92 su 100). Se a scadenza rimborsa il nominale, alla somma delle cedole si "
         "aggiunge la differenza; ma un prezzo sotto la pari di solito segnala che il mercato vede più rischio. Elenco: "
         "<a href=\"/certificati/sotto-la-pari\">certificati sotto la pari</a>."),
        ("Cos'è la cedola incondizionata?",
         "È una cedola pagata comunque, qualunque sia l'andamento dei sottostanti (certificati Fixed Cash Collect). La cedola condizionata, "
         "invece, è pagata solo se alla data di osservazione i sottostanti sono sopra il livello trigger."),
    ]),
    ("Rischi e tasse", [
        ("I certificati sono sicuri?",
         "No, non sono strumenti senza rischio. I rischi principali: il sottostante può scendere sotto la barriera (perdita anche forte del "
         "capitale), l'emittente può fallire (rischio emittente, nessuna garanzia del Fondo interbancario), il prezzo in borsa prima della "
         "scadenza può essere inferiore al nominale, e per i titoli in valuta c'è il rischio di cambio."),
        ("Cos'è il rischio emittente?",
         "È il rischio che la banca che ha emesso il certificato non riesca a pagare. I certificati non sono depositi: non sono coperti dal "
         "Fondo interbancario di tutela dei depositi e, in caso di crisi della banca, possono essere soggetti al bail-in. Diversificare "
         "tra emittenti riduce questo rischio."),
        ("Come sono tassati i certificati in Italia?",
         "Per una persona fisica, cedole, premi e plusvalenze dei certificati d'investimento sono in genere redditi diversi tassati al 26%. "
         "Il vantaggio è che possono compensare le minusvalenze accumulate nei quattro anni precedenti (cosa che, per esempio, i proventi "
         "degli ETF non fanno). È un'indicazione generale: per il proprio caso conviene sentire il commercialista o la banca."),
        ("Si può perdere tutto il capitale con un certificato?",
         "Con i certificati a capitale condizionatamente protetto sì, in teoria: se a scadenza il sottostante peggiore vale zero, si riceve "
         "zero. In pratica la perdita è pari al calo del sottostante peggiore quando la barriera è violata. Con i certificati a leva la "
         "perdita totale è un'eventualità concreta."),
        ("Si possono recuperare le minusvalenze con i certificati?",
         "In generale sì: per una persona fisica i proventi dei certificati (cedole comprese) sono redditi diversi e possono compensare le "
         "minusvalenze dei quattro anni precedenti presenti nello zainetto fiscale. Conta però come e quando il provento viene incassato e "
         "come opera il proprio intermediario: prima di muoversi per questo motivo verificare il proprio caso con la banca o il commercialista."),
        ("Quali sono i migliori certificati?",
         "Non esiste un certificato migliore in assoluto. Una cedola alta di solito corrisponde a sottostanti più volatili o a barriere più "
         "vicine; una barriera lontana a cedole più basse. Si confrontano cedola, distanza dalla barriera, scadenza, qualità dell'emittente e "
         "prezzo rispetto al nominale: le <a href=\"/certificati/\">raccolte</a> del radar li ordinano con criteri dichiarati, senza dare consigli."),
        ("Quanto costano i certificati?",
         "Non hanno commissioni di gestione esplicite: i costi sono dentro il prezzo (margine dell'emittente, riportato nel KID) e nella "
         "differenza tra denaro e lettera. A questi si aggiungono le commissioni di negoziazione della banca o del broker."),
    ]),
    ("Usare Radar Certificati", [
        ("Cos'è Radar Certificati?",
         "È uno screener gratuito e indipendente che raccoglie ogni giorno i certificati quotati in Italia dai siti degli emittenti e dalle "
         "borse: cedola annua, barriera, distanza del peggiore dalla barriera, scadenza, prezzi, settore, rendimento e probabilità stimata "
         "di tenuta. Si cerca per ISIN, sottostante, emittente o tipologia, senza registrazione."),
        ("Come trovo i certificati migliori?",
         "Non esiste un certificato migliore in assoluto: dipende da quanto rischio si accetta. Nel radar si sceglie un profilo (prudente, "
         "bilanciato, aggressivo) e i certificati vengono ordinati per un punteggio che bilancia cedola, distanza dalla barriera, "
         "probabilità di tenuta e scadenza. Le liste <a href=\"/certificati/cedole-piu-alte\">cedole più alte</a> e "
         "<a href=\"/certificati/difensivi\">difensivi</a> sono un punto di partenza."),
        ("Come si calcola la probabilità di tenuta della barriera?",
         "Con una simulazione Monte Carlo: migliaia di scenari dei sottostanti, con la volatilità storica (la maggiore tra 1 anno e 3 mesi) "
         "e le correlazioni dell'ultimo anno, senza drift. La probabilità è la quota di scenari in cui la barriera tiene fino a scadenza. "
         "È una stima statistica, non una previsione: non considera salti di prezzo, richiamo anticipato né rischio emittente."),
        ("Ogni quanto si aggiornano i dati?",
         "Ogni giorno di apertura di Borsa Italiana, alle 09:35 e alle 16:15 ora di Roma. Volatilità e correlazioni si aggiornano una "
         "volta al giorno."),
        ("Da dove vengono i dati?",
         "Dai siti pubblici degli emittenti (BNP Paribas, UniCredit, Vontobel, Barclays, Société Générale, Intesa Sanpaolo, Leonteq, "
         "Mediobanca, Marex e altri), da Borsa Italiana ed Euronext. I prezzi dei sottostanti servono a volatilità e distanze. I dati sono "
         "indicativi: prima di investire va controllato il KID."),
        ("Come cerco un certificato per ISIN?",
         "Basta scrivere l'ISIN nella <a href=\"/\">ricerca del radar</a>, oppure aprire direttamente l'indirizzo "
         "radarcertificati.com/certificato/ seguito dall'ISIN: ogni certificato ha la sua scheda con dati, sottostanti e andamento del prezzo."),
        ("Radar Certificati ha un'API?",
         "Sì, i dati sono pubblici in JSON: <a href=\"/api/v1/meta.json\">meta.json</a> con metodologia e totali, "
         "<a href=\"/api/v1/schema.json\">schema.json</a> con la descrizione dei campi e certificates.json con tutti i certificati."),
        ("Si può installare come app?",
         "Sì: dal telefono si apre radarcertificati.com e si sceglie \"Aggiungi alla schermata Home\" (iPhone) o \"Installa app\" "
         "(Android, Chrome)."),
    ]),
]
