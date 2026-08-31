CREATE TABLE IF NOT EXISTS razze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    eta_pollastro_mesi REAL NOT NULL,
    eta_produttivo_mesi REAL NOT NULL,
    eta_pensionato_mesi REAL NOT NULL,
    rivendita_eta_min_mesi REAL,
    rivendita_eta_max_mesi REAL,
    macellazione_eta_min_mesi REAL,
    macellazione_eta_max_mesi REAL,
    curva_deposizione TEXT,
    curva_fabbisogno_energetico TEXT
);

CREATE TABLE IF NOT EXISTS lotti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razza_id INTEGER NOT NULL REFERENCES razze(id),
    sesso TEXT NOT NULL CHECK (sesso IN ('M', 'F')),
    destinazione TEXT NOT NULL CHECK (destinazione IN ('riproduzione', 'uova', 'carne', 'rivendita')),
    data_nascita TEXT NOT NULL,
    data_ingresso TEXT NOT NULL,
    prezzo_acquisto_totale REAL,
    numero_capi_iniziale INTEGER NOT NULL,
    numero_capi_attuale INTEGER NOT NULL,
    pulcini_id INTEGER REFERENCES pulcini(id)
);

CREATE TABLE IF NOT EXISTS uscite (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lotto_id INTEGER NOT NULL REFERENCES lotti(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('vendita', 'macellazione', 'morte')),
    data TEXT NOT NULL,
    numero_capi INTEGER NOT NULL,
    prezzo_vendita_totale REAL
);

-- Lotti di uova impostate in incubatrice. La schiusa si registra a parte
-- (pulcini_nati/data_schiusa restano NULL finché non avviene): il tasso di
-- mortalità embrionale e l'efficienza di schiusa si calcolano solo dopo.
CREATE TABLE IF NOT EXISTS incubazioni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razza_id INTEGER NOT NULL REFERENCES razze(id),
    data_inizio TEXT NOT NULL,
    uova_impostate INTEGER NOT NULL,
    uova_infertili INTEGER NOT NULL DEFAULT 0,
    pulcini_nati INTEGER,
    data_schiusa TEXT,
    pulcini_promossi INTEGER NOT NULL DEFAULT 0,
    note TEXT
);

-- Lotti di pulcini in pulcinaia. Niente campo sesso: per la maggior parte
-- delle razze non è determinabile a questo stadio (si assegna solo alla
-- promozione a Pollaio, quando i caratteri secondari sono visibili).
CREATE TABLE IF NOT EXISTS pulcini (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razza_id INTEGER NOT NULL REFERENCES razze(id),
    incubazione_id INTEGER REFERENCES incubazioni(id),
    data_nascita TEXT NOT NULL,
    data_ingresso TEXT NOT NULL,
    prezzo_acquisto_totale REAL,
    numero_capi_iniziale INTEGER NOT NULL,
    numero_capi_attuale INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS uscite_pulcinaia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pulcini_id INTEGER NOT NULL REFERENCES pulcini(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('promozione', 'vendita', 'morte')),
    data TEXT NOT NULL,
    numero_capi INTEGER NOT NULL,
    prezzo_vendita_totale REAL,
    lotto_pollaio_id INTEGER REFERENCES lotti(id)
);
