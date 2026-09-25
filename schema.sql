CREATE TABLE IF NOT EXISTS razze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

-- Riga singola (id sempre 1): preferenze di visualizzazione delle schede,
-- condivise da tutte le pagine a griglia (Incubazione/Pulcinaia/Pollaio/Uova)
-- e modificabili dalla pagina Impostazioni.
CREATE TABLE IF NOT EXISTS impostazioni_vista (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    colonne_mobile INTEGER NOT NULL DEFAULT 1,
    colonne_desktop INTEGER NOT NULL DEFAULT 3,
    ordine TEXT NOT NULL DEFAULT 'alfa-asc'
);

-- Log di eventi per l'incubatrice. Nessun concetto di lotto: le uova con la
-- stessa razza sono fungibili fra loro, il pool è a livello di razza (coerente
-- con "tasso di schiusa per singola razza" come obiettivo di monitoraggio).
-- Direzione determinata dal tipo di evento: entrata/acquisto sommano al pool,
-- perdita/trasferimento sottraggono. 'trasferimento' è l'uscita per il
-- passaggio (fisico) a pulcinaia, registrata dalla stessa azione utente che
-- crea la riga 'entrata' in eventi_pulcinaia, ma senza alcun collegamento per
-- id fra le due righe: sono due pool indipendenti.
CREATE TABLE IF NOT EXISTS eventi_incubatrice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razza_id INTEGER NOT NULL REFERENCES razze(id),
    evento TEXT NOT NULL CHECK (evento IN ('entrata', 'acquisto', 'perdita', 'trasferimento')),
    data TEXT NOT NULL,
    numero_uova INTEGER NOT NULL CHECK (numero_uova > 0),
    prezzo_acquisto_totale REAL,
    note TEXT
);

-- Log di eventi per la pulcinaia. Il pool è a livello di (razza, data_nascita):
-- due entrate con la stessa razza e stessa data di nascita confluiscono nello
-- stesso gruppo. Direzione dal tipo di evento: entrata/acquisto sommano,
-- vendita/promozione/perdita sottraggono.
CREATE TABLE IF NOT EXISTS eventi_pulcinaia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razza_id INTEGER NOT NULL REFERENCES razze(id),
    evento TEXT NOT NULL CHECK (evento IN ('entrata', 'acquisto', 'vendita', 'promozione', 'perdita')),
    data TEXT NOT NULL,
    numero_capi INTEGER NOT NULL CHECK (numero_capi > 0),
    data_nascita TEXT NOT NULL,
    prezzo_acquisto_totale REAL,
    prezzo_vendita_totale REAL,
    note TEXT
);

-- Log di eventi per il pollaio. Il pool è a livello di (razza, sesso,
-- anno_nascita, destinazione) — la combinazione di caratteristiche che rende
-- due capi indistinguibili e fungibili fra loro. Niente pollaio/recinto:
-- ogni razza vive già in un pollaio fisico distinto, quindi la razza stessa
-- lo identifica implicitamente — un id di pollaio separato sarebbe una
-- dimensione ridondante. anno_nascita (non data esatta): coerente con
-- animali non nati in azienda.
-- Direzione dal tipo di evento: acquisto/promozione/cambio_destinazione_entrata
-- sommano; vendita/perdita/macellazione/cambio_destinazione_uscita sottraggono.
-- Il cambio destinazione è due righe indipendenti (stesse caratteristiche di
-- origine, stesso numero_capi): una 'cambio_destinazione_uscita' sul pool con
-- la vecchia destinazione, una 'cambio_destinazione_entrata' su quello con la
-- nuova — due evento distinti perché non esiste un lotto_id da cui dedurre la
-- direzione.
CREATE TABLE IF NOT EXISTS eventi_pollaio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razza_id INTEGER NOT NULL REFERENCES razze(id),
    evento TEXT NOT NULL CHECK (evento IN
        ('promozione', 'acquisto', 'vendita', 'perdita', 'macellazione',
         'cambio_destinazione_uscita', 'cambio_destinazione_entrata')),
    data TEXT NOT NULL,
    numero_capi INTEGER NOT NULL CHECK (numero_capi > 0),
    sesso TEXT NOT NULL CHECK (sesso IN ('M', 'F')),
    anno_nascita INTEGER NOT NULL,
    destinazione TEXT NOT NULL CHECK (destinazione IN ('riproduzione', 'uova', 'carne', 'rivendita')),
    prezzo_acquisto_totale REAL,
    prezzo_vendita_totale REAL,
    note TEXT
);

-- Log di eventi per il registro uova. Pool a livello di razza. Nessuna data di
-- nascita da tracciare: le uova raccolte sono fungibili.
CREATE TABLE IF NOT EXISTS eventi_registro_uova (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razza_id INTEGER NOT NULL REFERENCES razze(id),
    evento TEXT NOT NULL CHECK (evento IN ('raccolta', 'vendita')),
    data TEXT NOT NULL,
    numero_uova INTEGER NOT NULL CHECK (numero_uova > 0),
    prezzo_vendita_totale REAL,
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_eventi_incubatrice_razza ON eventi_incubatrice(razza_id);
CREATE INDEX IF NOT EXISTS idx_eventi_pulcinaia_gruppo ON eventi_pulcinaia(razza_id, data_nascita);
CREATE INDEX IF NOT EXISTS idx_eventi_pollaio_gruppo ON eventi_pollaio(razza_id, sesso, anno_nascita, destinazione);
