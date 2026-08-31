import sqlite3
from datetime import date
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, url_for, flash

DB_PATH = Path(__file__).parent / "pollaio.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

DESTINAZIONI = {
    "riproduzione": "Riproduzione",
    "uova": "Uova",
    "carne": "Carne",
    "rivendita": "Rivendita",
}

TIPI_USCITA_PULCINAIA = {
    "promozione": "Promozione a Pollaio",
    "vendita": "Vendita",
    "morte": "Morte",
}

CLASSI_ETA = ["Pulcino", "Pollastro", "Produttivo", "Pensionato"]

# il Pollaio contiene solo pollastri e adulti (i pulcini vivono in Pulcinaia):
# le viste sul Pollaio non devono contarli, anche se per qualche motivo
# un lotto risultasse ancora classificato "Pulcino" (es. promozione precoce)
CLASSI_ETA_POLLAIO = [c for c in CLASSI_ETA if c != "Pulcino"]

# colori per i chip del filtro destinazione (palette validata contro il daltonismo)
DESTINAZIONE_COLORI = {
    "riproduzione": "#4a3aa7",
    "uova": "#1baf7a",
    "carne": "#eb6834",
    "rivendita": "#2a78d6",
}

# Soglie di partenza da letteratura avicola generica (Bell & Weaver, NRC) —
# da correggere nella scheda "Razze" in base all'esperienza diretta.
RAZZE_SEED = [
    # nome, eta_pollastro, eta_produttivo, eta_pensionato (mesi)
    ("ISA Brown", 2, 4.5, 18),
    ("Australorp", 2.5, 5.5, 30),
    ("Plymouth Rock", 2.5, 5.5, 30),
    ("Pepoi", 3, 6.5, 36),
    ("Moroseta / Silkie", 3.5, 7, 40),
]

app = Flask(__name__)
app.secret_key = "dev"


@app.context_processor
def inject_oggi():
    return {"oggi": date.today().strftime("%d/%m/%Y"), "oggi_iso": date.today().isoformat()}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _colonna_esiste(db, tabella, colonna):
    righe = db.execute(f"PRAGMA table_info({tabella})").fetchall()
    return any(r[1] == colonna for r in righe)


def init_db():
    """Crea lo schema se manca e applica le migrazioni additive mancanti.
    Idempotente: gira ad ogni avvio dell'app, anche su un DB già popolato,
    senza mai cancellare dati esistenti."""
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA_PATH.read_text())

    if not _colonna_esiste(db, "lotti", "pulcini_id"):
        db.execute("ALTER TABLE lotti ADD COLUMN pulcini_id INTEGER REFERENCES pulcini(id)")

    if db.execute("SELECT COUNT(*) FROM razze").fetchone()[0] == 0:
        db.executemany(
            """INSERT INTO razze (nome, eta_pollastro_mesi, eta_produttivo_mesi, eta_pensionato_mesi)
               VALUES (?, ?, ?, ?)""",
            RAZZE_SEED,
        )

    db.commit()
    db.close()


init_db()


def eta_in_mesi(data_nascita_iso, riferimento=None):
    riferimento = riferimento or date.today()
    nascita = date.fromisoformat(data_nascita_iso)
    return max((riferimento - nascita).days // 30, 0)


def classe_eta(eta_mesi, razza):
    if eta_mesi < razza["eta_pollastro_mesi"]:
        return "Pulcino"
    if eta_mesi < razza["eta_produttivo_mesi"]:
        return "Pollastro"
    if eta_mesi < razza["eta_pensionato_mesi"]:
        return "Produttivo"
    return "Pensionato"


def lotti_disponibili(db, razza_id=None, sesso=None, destinazione=None, classe_eta_filtro=None):
    condizioni = ["lotti.numero_capi_attuale > 0"]
    parametri = []
    if razza_id:
        condizioni.append("lotti.razza_id = ?")
        parametri.append(razza_id)
    if sesso:
        condizioni.append("lotti.sesso = ?")
        parametri.append(sesso)
    if destinazione:
        condizioni.append("lotti.destinazione = ?")
        parametri.append(destinazione)

    righe = db.execute(
        f"""SELECT lotti.*, razze.nome AS razza_nome,
                   razze.eta_pollastro_mesi, razze.eta_produttivo_mesi, razze.eta_pensionato_mesi
            FROM lotti JOIN razze ON razze.id = lotti.razza_id
            WHERE {' AND '.join(condizioni)}
            ORDER BY lotti.data_ingresso DESC""",
        parametri,
    ).fetchall()

    risultato = []
    for r in righe:
        eta_mesi = eta_in_mesi(r["data_nascita"])
        classe = classe_eta(eta_mesi, r)
        if classe_eta_filtro and classe != classe_eta_filtro:
            continue
        risultato.append({**dict(r), "eta_mesi_attuale": eta_mesi, "classe_eta": classe})
    return risultato


def pulcini_disponibili(db):
    righe = db.execute(
        """SELECT pulcini.*, razze.nome AS razza_nome,
                  razze.eta_pollastro_mesi, razze.eta_produttivo_mesi, razze.eta_pensionato_mesi
           FROM pulcini JOIN razze ON razze.id = pulcini.razza_id
           WHERE pulcini.numero_capi_attuale > 0
           ORDER BY pulcini.data_ingresso DESC"""
    ).fetchall()
    risultato = []
    for r in righe:
        eta_mesi = eta_in_mesi(r["data_nascita"])
        risultato.append({**dict(r), "eta_mesi_attuale": eta_mesi, "classe_eta": classe_eta(eta_mesi, r)})
    return risultato


def pulcini_per_razza(db):
    """Un box per razza (tutte, anche senza pulcini attivi), con l'elenco
    dei lotti in pulcinaia per quella razza."""
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    lotti = pulcini_disponibili(db)

    lotti_per_razza = {}
    for l in lotti:
        lotti_per_razza.setdefault(l["razza_nome"], []).append(l)

    gruppi = []
    for razza in razze:
        lotti_razza = lotti_per_razza.get(razza["nome"], [])
        gruppi.append(
            {
                "razza": razza["nome"],
                "totale_capi": sum(l["numero_capi_attuale"] for l in lotti_razza),
                "lotti": lotti_razza,
            }
        )
    return gruppi


def _cella_vuota():
    return {"F": 0, "M": 0, "totale": 0}


def matrice_composizione(lotti, colonne=None):
    colonne = colonne or CLASSI_ETA
    celle = {}
    totali_razza = {}
    totali_classe = {c: _cella_vuota() for c in colonne}
    totale_generale = _cella_vuota()

    for l in lotti:
        razza = l["razza_nome"]
        classe = l["classe_eta"]
        if classe not in totali_classe:
            continue
        sesso = l["sesso"]
        n = l["numero_capi_attuale"]

        cella = celle.setdefault((razza, classe), _cella_vuota())
        cella[sesso] += n
        cella["totale"] += n

        totali_razza.setdefault(razza, _cella_vuota())
        totali_razza[razza][sesso] += n
        totali_razza[razza]["totale"] += n

        totali_classe[classe][sesso] += n
        totali_classe[classe]["totale"] += n

        totale_generale[sesso] += n
        totale_generale["totale"] += n

    razze_ordinate = sorted(totali_razza.keys(), key=lambda r: -totali_razza[r]["totale"])

    righe = []
    for razza in razze_ordinate:
        riga_celle = [celle.get((razza, classe), _cella_vuota()) for classe in colonne]
        righe.append({"razza": razza, "totale": totali_razza[razza], "celle": riga_celle})

    return {
        "colonne": colonne,
        "righe": righe,
        "colonne_totali": [totali_classe[c] for c in colonne],
        "totale_generale": totale_generale,
    }


def _lotti_per_destinazione_filtrata(db):
    """Legge ?destinazione= dalla query string e restituisce (lotti filtrati,
    valore del filtro) — condiviso fra la vista tabella e quella grafica, che
    mostrano la stessa composizione filtrata in due formati diversi."""
    lotti = lotti_disponibili(db)
    destinazione_filtro = request.args.get("destinazione", "tutte")
    if destinazione_filtro not in DESTINAZIONI:
        destinazione_filtro = "tutte"
    lotti_filtrati = (
        lotti
        if destinazione_filtro == "tutte"
        else [l for l in lotti if l["destinazione"] == destinazione_filtro]
    )
    return lotti_filtrati, destinazione_filtro


def grafico_piramide(matrice):
    """Trasforma la matrice razza x classe_eta in barre F/M pronte per il
    rendering a piramide, scalate sul valore massimo di cella dell'intera
    pagina così che le lunghezze restino confrontabili fra razze diverse."""
    max_cella = max((c["totale"] for riga in matrice["righe"] for c in riga["celle"]), default=0)

    razze = []
    for riga in matrice["righe"]:
        classi = []
        for classe, cella in zip(matrice["colonne"], riga["celle"]):
            classi.append(
                {
                    "classe": classe,
                    "F": cella["F"],
                    "M": cella["M"],
                    "percento_f": (cella["F"] / max_cella * 100) if max_cella else 0,
                    "percento_m": (cella["M"] / max_cella * 100) if max_cella else 0,
                }
            )
        razze.append({"razza": riga["razza"], "totale": riga["totale"]["totale"], "classi": classi})
    return razze


def incubazione_kpi(inc):
    """Metriche derivate di un'incubazione. Restano None finché la schiusa
    non è registrata: prima di allora non si sa quante uova erano fertili."""
    impostate = inc["uova_impostate"]
    infertili = inc["uova_infertili"] or 0
    nati = inc["pulcini_nati"]
    schiusa_registrata = inc["data_schiusa"] is not None

    if not schiusa_registrata:
        return {
            "schiusa_registrata": False,
            "morte_incubazione": None,
            "efficienza_schiusa": None,
            "mortalita_embrionale": None,
            "pulcini_da_promuovere": 0,
        }

    fertili = impostate - infertili
    morte_incubazione = fertili - nati
    return {
        "schiusa_registrata": True,
        "morte_incubazione": morte_incubazione,
        "efficienza_schiusa": (nati / impostate * 100) if impostate else 0,
        "mortalita_embrionale": (morte_incubazione / fertili * 100) if fertili else 0,
        "pulcini_da_promuovere": nati - inc["pulcini_promossi"],
    }


@app.route("/")
def index():
    db = get_db()
    lotti_filtrati, destinazione_filtro = _lotti_per_destinazione_filtrata(db)
    matrice = matrice_composizione(lotti_filtrati, colonne=CLASSI_ETA_POLLAIO)
    return render_template(
        "index.html",
        razze=grafico_piramide(matrice),
        destinazioni=DESTINAZIONI,
        colori_destinazione=DESTINAZIONE_COLORI,
        destinazione_filtro=destinazione_filtro,
    )


def _incubazione_con_razza(db, incubazione_id):
    return db.execute(
        """SELECT incubazioni.*, razze.nome AS razza_nome
           FROM incubazioni JOIN razze ON razze.id = incubazioni.razza_id
           WHERE incubazioni.id = ?""",
        (incubazione_id,),
    ).fetchone()


def incubazioni_per_razza(db):
    """Un box per razza (tutte, anche senza incubazioni attive): quante uova
    sta covando in questo momento, più l'elenco dei lotti ancora da seguire
    (non ancora schiusi, o schiusi ma con pulcini non ancora promossi)."""
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    righe = db.execute(
        """SELECT incubazioni.*, razze.nome AS razza_nome
           FROM incubazioni JOIN razze ON razze.id = incubazioni.razza_id
           ORDER BY incubazioni.data_inizio DESC"""
    ).fetchall()

    batch_per_razza = {}
    for r in righe:
        batch_per_razza.setdefault(r["razza_nome"], []).append(r)

    gruppi = []
    for razza in razze:
        batch_razza = batch_per_razza.get(razza["nome"], [])
        uova_in_incubazione = sum(b["uova_impostate"] for b in batch_razza if b["data_schiusa"] is None)

        batch_attivi = []
        for b in batch_razza:
            kpi = incubazione_kpi(b)
            if not kpi["schiusa_registrata"] or kpi["pulcini_da_promuovere"] > 0:
                batch_attivi.append({**dict(b), **kpi})

        gruppi.append(
            {
                "razza": razza["nome"],
                "uova_in_incubazione": uova_in_incubazione,
                "batch": batch_attivi,
            }
        )
    return gruppi


@app.route("/incubazione")
def incubazione_lista():
    db = get_db()
    return render_template("incubazione.html", gruppi=incubazioni_per_razza(db))


@app.route("/incubazione/nuova", methods=["GET", "POST"])
def incubazione_nuova():
    db = get_db()
    if request.method == "POST":
        razza_id = int(request.form["razza_id"])
        data_inizio = request.form["data_inizio"]
        uova_impostate = int(request.form["uova_impostate"])
        db.execute(
            "INSERT INTO incubazioni (razza_id, data_inizio, uova_impostate) VALUES (?, ?, ?)",
            (razza_id, data_inizio, uova_impostate),
        )
        db.commit()
        flash(f"Nuova incubazione: {uova_impostate} uova")
        return redirect(url_for("incubazione_lista"))
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    return render_template("incubazione_nuova.html", razze=razze)


@app.route("/incubazione/<int:incubazione_id>/schiusa", methods=["GET", "POST"])
def incubazione_schiusa(incubazione_id):
    db = get_db()
    inc = _incubazione_con_razza(db, incubazione_id)

    if request.method == "POST":
        pulcini_nati = int(request.form["pulcini_nati"])
        data_schiusa = request.form["data_schiusa"]
        infertili_gia_note = inc["uova_infertili"] or 0

        if pulcini_nati + infertili_gia_note > inc["uova_impostate"]:
            flash("Pulcini nati + uova già scartate non può superare le uova impostate.")
            return redirect(url_for("incubazione_schiusa", incubazione_id=incubazione_id))

        db.execute(
            "UPDATE incubazioni SET pulcini_nati = ?, data_schiusa = ? WHERE id = ?",
            (pulcini_nati, data_schiusa, incubazione_id),
        )
        db.commit()
        flash("Schiusa registrata")
        return redirect(url_for("incubazione_lista"))

    return render_template("incubazione_schiusa.html", incubazione=inc)


@app.route("/incubazione/<int:incubazione_id>/scarti", methods=["GET", "POST"])
def incubazione_scarti(incubazione_id):
    db = get_db()
    inc = _incubazione_con_razza(db, incubazione_id)

    if request.method == "POST":
        uova_infertili = int(request.form["uova_infertili"] or 0)
        nati_gia_noti = inc["pulcini_nati"] or 0

        if uova_infertili + nati_gia_noti > inc["uova_impostate"]:
            flash("Uova scartate + pulcini già nati non può superare le uova impostate.")
            return redirect(url_for("incubazione_scarti", incubazione_id=incubazione_id))

        db.execute(
            "UPDATE incubazioni SET uova_infertili = ? WHERE id = ?",
            (uova_infertili, incubazione_id),
        )
        db.commit()
        flash("Scarti registrati")
        return redirect(url_for("incubazione_lista"))

    return render_template("incubazione_scarti.html", incubazione=inc)


@app.route("/incubazione/<int:incubazione_id>/promuovi", methods=["GET", "POST"])
def incubazione_promuovi(incubazione_id):
    db = get_db()
    inc = _incubazione_con_razza(db, incubazione_id)
    disponibili = (inc["pulcini_nati"] or 0) - inc["pulcini_promossi"]

    if request.method == "POST":
        numero_capi = int(request.form["numero_capi"] or 0)
        if numero_capi < 1 or numero_capi > disponibili:
            flash("Numero di pulcini non disponibile per la promozione.")
            return redirect(url_for("incubazione_promuovi", incubazione_id=incubazione_id))

        oggi = date.today().isoformat()
        db.execute(
            """INSERT INTO pulcini (razza_id, incubazione_id, data_nascita, data_ingresso,
                                     numero_capi_iniziale, numero_capi_attuale)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (inc["razza_id"], incubazione_id, inc["data_schiusa"], oggi, numero_capi, numero_capi),
        )
        db.execute(
            "UPDATE incubazioni SET pulcini_promossi = pulcini_promossi + ? WHERE id = ?",
            (numero_capi, incubazione_id),
        )
        db.commit()
        flash(f"Promossi {numero_capi} pulcini in Pulcinaia")
        return redirect(url_for("incubazione_lista"))

    return render_template("incubazione_promuovi.html", incubazione=inc, disponibili=disponibili)


@app.route("/pulcinaia")
def pulcinaia_lista():
    db = get_db()
    return render_template("pulcinaia.html", gruppi=pulcini_per_razza(db))


@app.route("/pulcinaia/nuova", methods=["GET", "POST"])
def pulcinaia_nuova():
    db = get_db()
    if request.method == "POST":
        razza_id = int(request.form["razza_id"])
        data_nascita = request.form["data_nascita"]
        numero_capi = int(request.form["numero_capi"] or 1)
        prezzo_acquisto = request.form.get("prezzo_acquisto") or None
        oggi = date.today().isoformat()

        db.execute(
            """INSERT INTO pulcini (razza_id, data_nascita, data_ingresso,
                                     prezzo_acquisto_totale, numero_capi_iniziale, numero_capi_attuale)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (razza_id, data_nascita, oggi, prezzo_acquisto, numero_capi, numero_capi),
        )
        db.commit()
        flash(f"Aggiunti {numero_capi} pulcini (acquisto esterno)")
        return redirect(url_for("pulcinaia_lista"))

    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    return render_template("pulcinaia_nuova.html", razze=razze)


@app.route("/pulcinaia/<int:pulcini_id>/uscita", methods=["GET", "POST"])
def pulcinaia_uscita(pulcini_id):
    db = get_db()
    lotto = db.execute(
        """SELECT pulcini.*, razze.nome AS razza_nome,
                  razze.eta_pollastro_mesi, razze.eta_produttivo_mesi, razze.eta_pensionato_mesi
           FROM pulcini JOIN razze ON razze.id = pulcini.razza_id
           WHERE pulcini.id = ?""",
        (pulcini_id,),
    ).fetchone()

    if request.method == "POST":
        tipo = request.form["tipo"]
        numero_capi = int(request.form["numero_capi"] or 1)

        if lotto is None or numero_capi < 1 or numero_capi > lotto["numero_capi_attuale"]:
            flash("Numero di pulcini non disponibile in quel lotto.")
            return redirect(url_for("pulcinaia_uscita", pulcini_id=pulcini_id))

        oggi = date.today().isoformat()
        prezzo_vendita = request.form.get("prezzo_vendita") or None
        lotto_pollaio_id = None

        if tipo == "promozione":
            sesso = request.form["sesso"]
            destinazione = request.form["destinazione"]
            cur = db.execute(
                """INSERT INTO lotti (razza_id, sesso, destinazione, data_nascita, data_ingresso,
                                       numero_capi_iniziale, numero_capi_attuale, pulcini_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lotto["razza_id"],
                    sesso,
                    destinazione,
                    lotto["data_nascita"],
                    oggi,
                    numero_capi,
                    numero_capi,
                    pulcini_id,
                ),
            )
            lotto_pollaio_id = cur.lastrowid
            prezzo_vendita = None
        elif tipo == "morte":
            prezzo_vendita = None

        db.execute(
            """INSERT INTO uscite_pulcinaia (pulcini_id, tipo, data, numero_capi,
                                              prezzo_vendita_totale, lotto_pollaio_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pulcini_id, tipo, oggi, numero_capi, prezzo_vendita, lotto_pollaio_id),
        )
        db.execute(
            "UPDATE pulcini SET numero_capi_attuale = numero_capi_attuale - ? WHERE id = ?",
            (numero_capi, pulcini_id),
        )
        db.commit()
        flash(f"Registrata {TIPI_USCITA_PULCINAIA[tipo].lower()}: {numero_capi} pulcini")
        return redirect(url_for("pulcinaia_lista"))

    eta_mesi = eta_in_mesi(lotto["data_nascita"])
    return render_template(
        "pulcinaia_uscita.html",
        lotto={**dict(lotto), "eta_mesi_attuale": eta_mesi, "classe_eta": classe_eta(eta_mesi, lotto)},
        tipi=TIPI_USCITA_PULCINAIA,
        destinazioni=DESTINAZIONI,
    )


@app.route("/query")
def query():
    db = get_db()
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()

    filtri = {
        "razza_id": request.args.get("razza_id", ""),
        "sesso": request.args.get("sesso", ""),
        "destinazione": request.args.get("destinazione", ""),
        "classe_eta": request.args.get("classe_eta", ""),
    }

    risultati = lotti_disponibili(
        db,
        razza_id=filtri["razza_id"] or None,
        sesso=filtri["sesso"] or None,
        destinazione=filtri["destinazione"] or None,
        classe_eta_filtro=filtri["classe_eta"] or None,
    )
    totale_capi = sum(l["numero_capi_attuale"] for l in risultati)

    return render_template(
        "query.html",
        razze=razze,
        destinazioni=DESTINAZIONI,
        classi_eta=CLASSI_ETA,
        risultati=risultati,
        filtri=filtri,
        totale_capi=totale_capi,
    )


def _numero_o_none(form, campo):
    valore = form.get(campo)
    return float(valore) if valore else None


def _salva_razza(db, form, razza_id=None):
    dati = (
        form["nome"],
        float(form["eta_pollastro_mesi"]),
        float(form["eta_produttivo_mesi"]),
        float(form["eta_pensionato_mesi"]),
        _numero_o_none(form, "rivendita_eta_min_mesi"),
        _numero_o_none(form, "rivendita_eta_max_mesi"),
        _numero_o_none(form, "macellazione_eta_min_mesi"),
        _numero_o_none(form, "macellazione_eta_max_mesi"),
        form.get("curva_deposizione") or None,
        form.get("curva_fabbisogno_energetico") or None,
    )
    if razza_id is None:
        db.execute(
            """INSERT INTO razze
               (nome, eta_pollastro_mesi, eta_produttivo_mesi, eta_pensionato_mesi,
                rivendita_eta_min_mesi, rivendita_eta_max_mesi,
                macellazione_eta_min_mesi, macellazione_eta_max_mesi,
                curva_deposizione, curva_fabbisogno_energetico)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            dati,
        )
    else:
        db.execute(
            """UPDATE razze SET
                   nome=?, eta_pollastro_mesi=?, eta_produttivo_mesi=?, eta_pensionato_mesi=?,
                   rivendita_eta_min_mesi=?, rivendita_eta_max_mesi=?,
                   macellazione_eta_min_mesi=?, macellazione_eta_max_mesi=?,
                   curva_deposizione=?, curva_fabbisogno_energetico=?
               WHERE id=?""",
            dati + (razza_id,),
        )


@app.route("/razze")
def razze_lista():
    db = get_db()
    razze = db.execute("SELECT * FROM razze ORDER BY nome").fetchall()
    return render_template("razze.html", razze=razze)


@app.route("/razze/nuova", methods=["GET", "POST"])
def razza_nuova():
    db = get_db()
    if request.method == "POST":
        _salva_razza(db, request.form)
        db.commit()
        flash("Razza aggiunta")
        return redirect(url_for("razze_lista"))
    return render_template("razza_form.html", razza=None)


@app.route("/razze/<int:razza_id>/modifica", methods=["GET", "POST"])
def razza_modifica(razza_id):
    db = get_db()
    if request.method == "POST":
        _salva_razza(db, request.form, razza_id=razza_id)
        db.commit()
        flash("Razza aggiornata")
        return redirect(url_for("razze_lista"))
    razza = db.execute("SELECT * FROM razze WHERE id = ?", (razza_id,)).fetchone()
    return render_template("razza_form.html", razza=razza)


if __name__ == "__main__":
    app.run(debug=True)
