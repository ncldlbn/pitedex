import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, abort, g, redirect, render_template, request, session, url_for, flash

DB_PATH = Path(__file__).parent / "pollaio.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

DESTINAZIONI = {
    "riproduzione": "Riproduzione",
    "uova": "Uova",
    "carne": "Carne",
    "rivendita": "Rivendita",
}

TIPI_USCITA_PULCINAIA = {
    "vendita": "Vendita",
    "perdita": "Perdita",
}
# La promozione a Pollaio si registra da Pollaio -> Entrata (lato che riceve),
# stesso pattern del trasferimento Incubatrice -> Pulcinaia.

TIPI_USCITA_POLLAIO = {
    "vendita": "Vendita",
    "macellazione": "Macellazione",
    "perdita": "Perdita",
}

RAZZE_SEED = ["ISA Brown", "Australorp", "Plymouth Rock", "Pepoi", "Moroseta / Silkie"]

# Azioni rapide (home "/"): un box per area, ognuno con l'elenco di tutte le
# azioni di ingresso/uscita di quell'area. Ogni azione porta direttamente alla
# sua pagina di inserimento dati (non un popup su un'altra pagina) — le pagine
# di Incubazione/Pulcinaia/Pollaio/Uova sono solo visualizzazione di stato.
AZIONI_RAPIDE = {
    "incubazione": {
        "icona": "🐣", "nome": "Incubazione",
        "azioni": [
            {"etichetta": "Registra ingresso", "endpoint": "incubazione_nuova"},
            {"etichetta": "Registra perdita", "endpoint": "incubazione_perdita"},
        ],
    },
    "pulcinaia": {
        "icona": "🐤", "nome": "Pulcinaia",
        "azioni": [
            {"etichetta": "Registra ingresso", "endpoint": "pulcinaia_nuova"},
            {"etichetta": "Registra perdita", "endpoint": "pulcinaia_uscita", "params": {"tipo": "perdita"}},
            {"etichetta": "Registra vendita", "endpoint": "pulcinaia_uscita", "params": {"tipo": "vendita"}},
        ],
    },
    "pollaio": {
        "icona": "🐔", "nome": "Pollaio",
        "azioni": [
            {"etichetta": "Registra ingresso", "endpoint": "pollaio_nuova"},
            {"etichetta": "Registra perdita", "endpoint": "pollaio_uscita", "params": {"tipo": "perdita"}},
            {"etichetta": "Registra vendita", "endpoint": "pollaio_uscita", "params": {"tipo": "vendita"}},
            {"etichetta": "Registra macellazione", "endpoint": "pollaio_uscita", "params": {"tipo": "macellazione"}},
            {"etichetta": "Cambia destinazione", "endpoint": "pollaio_cambio_destinazione"},
        ],
    },
    "uova": {
        "icona": "🥚", "nome": "Uova",
        "azioni": [
            {"etichetta": "Registra raccolta", "endpoint": "registro_uova_raccolta"},
            {"etichetta": "Registra vendita", "endpoint": "registro_uova_vendita"},
        ],
    },
}


def _azioni_rapide_gruppo(chiave):
    info = AZIONI_RAPIDE[chiave]
    azioni = [
        {"etichetta": a["etichetta"], "url": url_for(a["endpoint"], **a.get("params", {}))}
        for a in info["azioni"]
    ]
    return {"chiave": chiave, "icona": info["icona"], "nome": info["nome"], "azioni": azioni}


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
app.permanent_session_lifetime = timedelta(days=365)

DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "admin")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "1234")


@app.before_request
def richiedi_login():
    if request.endpoint in ("login", "static") or request.endpoint is None:
        return
    if not session.get("loggato"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == DEMO_USERNAME and request.form.get("password") == DEMO_PASSWORD:
            session.permanent = True
            session["loggato"] = True
            return redirect(url_for("index"))
        flash("Utente o password errati")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    gruppi = [_azioni_rapide_gruppo(chiave) for chiave in AZIONI_RAPIDE]
    return render_template("index.html", gruppi=gruppi)


@app.context_processor
def inject_oggi():
    return {"oggi_iso": date.today().isoformat()}


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


def init_db():
    """Crea lo schema se manca. Idempotente: gira ad ogni avvio dell'app,
    anche su un DB già popolato, senza mai cancellare dati esistenti."""
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA_PATH.read_text())

    if db.execute("SELECT COUNT(*) FROM razze").fetchone()[0] == 0:
        db.executemany("INSERT INTO razze (nome) VALUES (?)", [(nome,) for nome in RAZZE_SEED])

    db.commit()
    db.close()


init_db()


def eta_in_mesi(data_nascita_iso, riferimento=None):
    riferimento = riferimento or date.today()
    nascita = date.fromisoformat(data_nascita_iso)
    return max((riferimento - nascita).days // 30, 0)


def data_nascita_approssimata(anno_nascita):
    """anno_nascita (Pollaio) -> data approssimata (convenzione: metà anno),
    per riusare eta_in_mesi() che lavora su una data esatta."""
    return f"{anno_nascita}-07-01"


def pollaio_disponibili(db, razza_id=None, sesso=None, destinazione=None,
                         anno_nascita=None, data_riferimento=None):
    """Pool di pollaio in stock (numero_capi_attuale > 0) a una data di
    riferimento, un gruppo per combinazione di caratteristiche (razza, sesso,
    anno_nascita, destinazione) — niente identità di lotto: due capi con le
    stesse caratteristiche sono fungibili e confluiscono nello stesso gruppo.
    Niente pollaio/recinto: ogni razza vive già in un pollaio fisico
    distinto, quindi la razza stessa lo identifica implicitamente.

    `data_riferimento` (None = stato attuale, tutti gli eventi) ricostruisce
    lo stato a una data storica per somma cumulata degli eventi fino a quel
    momento — stessa funzione, stesso calcolo, usata sia per "oggi" sia per
    una data passata: niente percorso di codice separato per lo storico."""
    condizioni = []
    parametri = []
    if razza_id:
        condizioni.append("s.razza_id = ?")
        parametri.append(razza_id)
    if sesso:
        condizioni.append("s.sesso = ?")
        parametri.append(sesso)
    if destinazione:
        condizioni.append("s.destinazione = ?")
        parametri.append(destinazione)
    if anno_nascita:
        condizioni.append("s.anno_nascita = ?")
        parametri.append(anno_nascita)
    filtro = f"AND {' AND '.join(condizioni)}" if condizioni else ""

    filtro_data = "WHERE data <= ?" if data_riferimento else ""
    parametri_data = [data_riferimento] if data_riferimento else []

    righe = db.execute(
        f"""
        SELECT s.razza_id, razze.nome AS razza_nome,
               s.sesso, s.anno_nascita, s.destinazione, s.numero_capi_attuale
        FROM (
          SELECT razza_id, sesso, anno_nascita, destinazione,
                 SUM(CASE
                       WHEN evento IN ('acquisto','promozione','cambio_destinazione_entrata') THEN numero_capi
                       WHEN evento IN ('vendita','perdita','macellazione','cambio_destinazione_uscita') THEN -numero_capi
                     END) AS numero_capi_attuale
          FROM eventi_pollaio
          {filtro_data}
          GROUP BY razza_id, sesso, anno_nascita, destinazione
        ) s
        JOIN razze ON razze.id = s.razza_id
        WHERE s.numero_capi_attuale > 0 {filtro}
        ORDER BY s.numero_capi_attuale DESC
        """,
        parametri_data + parametri,
    ).fetchall()

    risultato = []
    for r in righe:
        data_nascita = data_nascita_approssimata(r["anno_nascita"])
        eta_mesi = eta_in_mesi(data_nascita)
        risultato.append({**dict(r), "eta_mesi_attuale": eta_mesi})
    return risultato


def _pollaio_pool(db, razza_id, sesso, anno_nascita, destinazione):
    righe = pollaio_disponibili(
        db, razza_id=razza_id, sesso=sesso, anno_nascita=anno_nascita, destinazione=destinazione,
    )
    return righe[0] if righe else None


def pulcinaia_disponibili(db, razza_id=None, data_nascita=None):
    """Pool di pulcinaia tuttora in stock (numero_capi_attuale > 0), un
    gruppo per (razza, data_nascita)."""
    condizioni = []
    parametri = []
    if razza_id:
        condizioni.append("s.razza_id = ?")
        parametri.append(razza_id)
    if data_nascita:
        condizioni.append("s.data_nascita = ?")
        parametri.append(data_nascita)
    filtro = f"AND {' AND '.join(condizioni)}" if condizioni else ""

    righe = db.execute(
        f"""
        SELECT s.razza_id, razze.nome AS razza_nome, s.data_nascita, s.numero_capi_attuale
        FROM (
          SELECT razza_id, data_nascita,
                 SUM(CASE WHEN evento IN ('entrata','acquisto') THEN numero_capi ELSE -numero_capi END)
                   AS numero_capi_attuale
          FROM eventi_pulcinaia
          GROUP BY razza_id, data_nascita
        ) s
        JOIN razze ON razze.id = s.razza_id
        WHERE s.numero_capi_attuale > 0 {filtro}
        ORDER BY s.data_nascita DESC
        """,
        parametri,
    ).fetchall()

    risultato = []
    for r in righe:
        risultato.append({**dict(r), "eta_mesi_attuale": eta_in_mesi(r["data_nascita"])})
    return risultato


def _pulcinaia_pool(db, razza_id, data_nascita):
    righe = pulcinaia_disponibili(db, razza_id=razza_id, data_nascita=data_nascita)
    return righe[0] if righe else None


def pulcini_per_razza(db):
    """Un box per razza (tutte, anche senza pulcini attivi), con l'elenco
    dei lotti in pulcinaia per quella razza."""
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    lotti = pulcinaia_disponibili(db)

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


SESSO_LABEL = {"F": "Femmine", "M": "Maschi"}


def pollaio_composizione_per_razza(db):
    """Una card per razza (solo quelle con capi presenti): totale, e per
    ciascun sesso la distribuzione sia per destinazione d'uso sia per anno di
    nascita (due viste alternative, entrambe calcolate — il toggle fra le due
    è lato client) — percento scalata sul valore massimo di *tutte* le barre
    dello stesso tipo in tutto il pollaio, così le lunghezze restano
    confrontabili fra razze/sessi diversi."""
    righe = pollaio_disponibili(db)

    per_razza = {}       # razza_nome -> sesso -> destinazione -> capi
    per_razza_anno = {}  # razza_nome -> sesso -> anno_nascita -> capi
    razza_id_per_nome = {}
    for r in righe:
        per_sesso = per_razza.setdefault(r["razza_nome"], {})
        per_dest = per_sesso.setdefault(r["sesso"], {})
        per_dest[r["destinazione"]] = per_dest.get(r["destinazione"], 0) + r["numero_capi_attuale"]

        per_sesso_anno = per_razza_anno.setdefault(r["razza_nome"], {})
        per_anno = per_sesso_anno.setdefault(r["sesso"], {})
        per_anno[r["anno_nascita"]] = per_anno.get(r["anno_nascita"], 0) + r["numero_capi_attuale"]

        razza_id_per_nome[r["razza_nome"]] = r["razza_id"]

    massimo_dest = max(
        (c for ps in per_razza.values() for pd in ps.values() for c in pd.values()),
        default=0,
    )

    # ultimi 4 anni rispetto a oggi (finestra fissa, non dipendente dai dati):
    # stesso principio delle destinazioni — righe uniformi fra schede diverse.
    anno_corrente = date.today().year
    ultimi_4_anni = [anno_corrente - i for i in range(3, -1, -1)]

    massimo_anno = max(
        (ps.get(sesso, {}).get(anno, 0)
         for ps in per_razza_anno.values()
         for sesso in ("F", "M")
         for anno in ultimi_4_anni),
        default=0,
    )

    gruppi = []
    for razza_nome in sorted(per_razza):
        dati_sesso = per_razza[razza_nome]
        dati_sesso_anno = per_razza_anno.get(razza_nome, {})
        totale_razza = sum(sum(d.values()) for d in dati_sesso.values())
        sessi = []
        for sesso_key in ("F", "M"):
            # sempre entrambi i sessi (anche senza capi: tutte le barre a zero)
            per_dest = dati_sesso.get(sesso_key, {})
            per_anno = dati_sesso_anno.get(sesso_key, {})

            # tutte le destinazioni, anche a zero, per mantenere le stesse righe
            # fra schede diverse — "uova" non ha senso pei maschi
            destinazioni_sesso = [d for d in DESTINAZIONI if not (sesso_key == "M" and d == "uova")]
            barre_destinazione = [
                {
                    "etichetta": DESTINAZIONI[dest],
                    "totale": per_dest.get(dest, 0),
                    "percento": (per_dest.get(dest, 0) / massimo_dest * 100) if massimo_dest else 0,
                }
                for dest in destinazioni_sesso
            ]
            # ultimi 4 anni fissi, anche a zero (barra vuota) se non ci sono capi
            # nati in quell'anno, per la stessa ragione delle destinazioni
            barre_anno = [
                {
                    "etichetta": str(anno),
                    "totale": per_anno.get(anno, 0),
                    "percento": (per_anno.get(anno, 0) / massimo_anno * 100) if massimo_anno else 0,
                }
                for anno in ultimi_4_anni
            ]

            sessi.append({
                "label": SESSO_LABEL[sesso_key],
                "totale": sum(per_dest.values()),
                "barre_destinazione": barre_destinazione,
                "barre_anno": barre_anno,
            })
        gruppi.append({
            "nome": razza_nome, "razza_id": razza_id_per_nome[razza_nome],
            "totale": totale_razza, "sessi": sessi,
        })
    return gruppi


@app.route("/pollaio/razza/<int:razza_id>")
def pollaio_razza_dettaglio(razza_id):
    db = get_db()
    razza = db.execute("SELECT * FROM razze WHERE id = ?", (razza_id,)).fetchone()
    return render_template("razza_dettaglio.html", razza=razza)


@app.route("/pollaio")
def pollaio_lista():
    db = get_db()
    return render_template("pollaio.html", composizione_razze=pollaio_composizione_per_razza(db))


def eventi_incubatrice_per_razza(db, razza_id=None):
    """Pool di incubatrice per razza (niente sotto-raggruppamento: le uova
    della stessa razza sono fungibili). uova_in_attesa = quante restano
    ancora da risolvere (né perse né trasferite in pulcinaia)."""
    condizioni = []
    parametri = []
    if razza_id:
        condizioni.append("razza_id = ?")
        parametri.append(razza_id)
    filtro = f"WHERE {' AND '.join(condizioni)}" if condizioni else ""

    righe = db.execute(
        f"""
        SELECT razza_id,
          SUM(CASE WHEN evento IN ('entrata','acquisto') THEN numero_uova ELSE 0 END) AS uova_impostate,
          SUM(CASE WHEN evento = 'perdita' THEN numero_uova ELSE 0 END) AS uova_perdute,
          SUM(CASE WHEN evento = 'trasferimento' THEN numero_uova ELSE 0 END) AS uova_trasferite
        FROM eventi_incubatrice
        {filtro}
        GROUP BY razza_id
        """,
        parametri,
    ).fetchall()

    risultato = []
    for r in righe:
        d = dict(r)
        d["uova_in_attesa"] = d["uova_impostate"] - d["uova_perdute"] - d["uova_trasferite"]
        d["tasso_trasferimento"] = (d["uova_trasferite"] / d["uova_impostate"] * 100) if d["uova_impostate"] else 0
        risultato.append(d)
    return risultato


def _incubatrice_pool_razza(db, razza_id):
    righe = eventi_incubatrice_per_razza(db, razza_id=razza_id)
    return righe[0] if righe else {"razza_id": razza_id, "uova_impostate": 0, "uova_perdute": 0,
                                    "uova_trasferite": 0, "uova_in_attesa": 0, "tasso_trasferimento": 0}


def incubazioni_per_razza(db):
    """Un pool per razza (tutte, anche senza movimenti)."""
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    pool_per_razza = {p["razza_id"]: p for p in eventi_incubatrice_per_razza(db)}

    gruppi = []
    for razza in razze:
        pool = pool_per_razza.get(razza["id"])
        base = {"razza_id": razza["id"], "razza": razza["nome"], "uova_impostate": 0, "uova_perdute": 0,
                "uova_trasferite": 0, "uova_in_attesa": 0, "tasso_trasferimento": 0}
        gruppi.append({**base, **(pool or {})})
    return gruppi


@app.route("/incubazione")
def incubazione_lista():
    db = get_db()
    return render_template("incubazione.html", gruppi=incubazioni_per_razza(db))


@app.route("/incubazione/nuova", methods=["GET", "POST"])
def incubazione_nuova():
    db = get_db()
    if request.method == "POST":
        evento = request.form["evento"]
        razza_id = int(request.form["razza_id"])
        data = request.form["data"]
        numero_uova = int(request.form["numero_uova"])
        prezzo_acquisto = request.form.get("prezzo_acquisto") or None if evento == "acquisto" else None
        db.execute(
            """INSERT INTO eventi_incubatrice (razza_id, evento, data, numero_uova, prezzo_acquisto_totale)
               VALUES (?, ?, ?, ?, ?)""",
            (razza_id, evento, data, numero_uova, prezzo_acquisto),
        )
        db.commit()
        flash(f"Registrate {numero_uova} uova in incubatrice")
        return redirect(url_for("incubazione_lista"))
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    return render_template("incubazione_ingresso.html", razze=razze)


@app.route("/incubazione/perdita", methods=["GET", "POST"])
def incubazione_perdita():
    db = get_db()
    if request.method == "POST":
        razza_id = int(request.form["razza_id"])
        pool = _incubatrice_pool_razza(db, razza_id)
        numero_uova = int(request.form["numero_uova"] or 0)

        if numero_uova < 1 or numero_uova > pool["uova_in_attesa"]:
            flash("Numero di uova non disponibile per la perdita.")
            return redirect(url_for("incubazione_lista"))

        oggi = date.today().isoformat()
        db.execute(
            "INSERT INTO eventi_incubatrice (razza_id, evento, data, numero_uova) VALUES (?, 'perdita', ?, ?)",
            (razza_id, oggi, numero_uova),
        )
        db.commit()
        flash(f"Registrata perdita di {numero_uova} uova")
        return redirect(url_for("incubazione_lista"))
    return render_template("incubazione_perdita.html", gruppi=incubazioni_per_razza(db))


@app.route("/pulcinaia")
def pulcinaia_lista():
    db = get_db()
    return render_template("pulcinaia.html", gruppi=pulcini_per_razza(db))


@app.route("/pulcinaia/nuova", methods=["GET", "POST"])
def pulcinaia_nuova():
    db = get_db()
    if request.method == "POST":
        evento = request.form["evento"]
        razza_id = int(request.form["razza_id"])
        data_nascita = request.form["data_nascita"]
        numero_capi = int(request.form["numero_capi"] or 1)
        oggi = date.today().isoformat()

        if evento == "entrata":
            pool_incubatrice = _incubatrice_pool_razza(db, razza_id)
            if numero_capi < 1 or numero_capi > pool_incubatrice["uova_in_attesa"]:
                flash("Numero di pulcini non disponibile in incubatrice per quella razza.")
                return redirect(url_for("pulcinaia_lista"))
            db.execute(
                "INSERT INTO eventi_incubatrice (razza_id, evento, data, numero_uova) VALUES (?, 'trasferimento', ?, ?)",
                (razza_id, oggi, numero_capi),
            )
            db.execute(
                """INSERT INTO eventi_pulcinaia (razza_id, evento, data, numero_capi, data_nascita)
                   VALUES (?, 'entrata', ?, ?, ?)""",
                (razza_id, oggi, numero_capi, data_nascita),
            )
            flash(f"Trasferiti {numero_capi} pulcini da Incubatrice a Pulcinaia")
        else:
            prezzo_acquisto = request.form.get("prezzo_acquisto") or None
            db.execute(
                """INSERT INTO eventi_pulcinaia (razza_id, evento, data, numero_capi, data_nascita,
                                                   prezzo_acquisto_totale)
                   VALUES (?, 'acquisto', ?, ?, ?, ?)""",
                (razza_id, oggi, numero_capi, data_nascita, prezzo_acquisto),
            )
            flash(f"Aggiunti {numero_capi} pulcini (acquisto esterno)")

        db.commit()
        return redirect(url_for("pulcinaia_lista"))

    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    uova_in_attesa_per_razza = {p["razza_id"]: p["uova_in_attesa"] for p in eventi_incubatrice_per_razza(db)}
    return render_template(
        "pulcinaia_ingresso.html", razze=razze, uova_in_attesa_per_razza=uova_in_attesa_per_razza,
    )


@app.route("/pulcinaia/uscita/<tipo>", methods=["GET", "POST"])
def pulcinaia_uscita(tipo):
    if tipo not in TIPI_USCITA_PULCINAIA:
        abort(404)
    db = get_db()
    if request.method == "POST":
        razza_id = int(request.form["razza_id"])
        data_nascita = request.form["data_nascita"]
        pool = _pulcinaia_pool(db, razza_id, data_nascita)

        numero_capi = int(request.form["numero_capi"] or 1)

        if pool is None or numero_capi < 1 or numero_capi > pool["numero_capi_attuale"]:
            flash("Numero di pulcini non disponibile in quel gruppo.")
            return redirect(url_for("pulcinaia_lista"))

        oggi = date.today().isoformat()
        prezzo_vendita = request.form.get("prezzo_vendita") or None if tipo == "vendita" else None
        db.execute(
            """INSERT INTO eventi_pulcinaia (razza_id, evento, data, numero_capi, data_nascita,
                                               prezzo_vendita_totale)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (razza_id, tipo, oggi, numero_capi, data_nascita, prezzo_vendita),
        )

        db.commit()
        flash(f"Registrata {TIPI_USCITA_PULCINAIA[tipo].lower()}: {numero_capi} pulcini")
        return redirect(url_for("pulcinaia_lista"))

    return render_template(
        "pulcinaia_uscita.html", tipo=tipo, tipo_label=TIPI_USCITA_PULCINAIA[tipo],
        gruppi_pulcinaia=pulcinaia_disponibili(db),
    )


@app.route("/query")
def query():
    db = get_db()
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()

    filtri = {
        "razza_id": request.args.get("razza_id", ""),
        "sesso": request.args.get("sesso", ""),
        "destinazione": request.args.get("destinazione", ""),
    }

    risultati = pollaio_disponibili(
        db,
        razza_id=filtri["razza_id"] or None,
        sesso=filtri["sesso"] or None,
        destinazione=filtri["destinazione"] or None,
    )
    totale_capi = sum(l["numero_capi_attuale"] for l in risultati)

    return render_template(
        "query.html",
        razze=razze,
        destinazioni=DESTINAZIONI,
        risultati=risultati,
        filtri=filtri,
        totale_capi=totale_capi,
    )


@app.route("/pollaio/nuovo", methods=["GET", "POST"])
def pollaio_nuova():
    db = get_db()
    if request.method == "POST":
        evento = request.form["evento"]
        razza_id = int(request.form["razza_id"])
        sesso = request.form["sesso"]
        destinazione = request.form["destinazione"]
        numero_capi = int(request.form["numero_capi"] or 1)
        oggi = date.today().isoformat()

        if evento == "promozione":
            data_nascita = request.form["data_nascita"]
            pool_pulcinaia = _pulcinaia_pool(db, razza_id, data_nascita)
            if pool_pulcinaia is None or numero_capi < 1 or numero_capi > pool_pulcinaia["numero_capi_attuale"]:
                flash("Numero di pulcini non disponibile in quel gruppo di Pulcinaia.")
                return redirect(url_for("pollaio_lista"))
            anno_nascita = date.fromisoformat(data_nascita).year

            db.execute(
                """INSERT INTO eventi_pollaio (razza_id, evento, data, numero_capi, sesso,
                                                anno_nascita, destinazione)
                   VALUES (?, 'promozione', ?, ?, ?, ?, ?)""",
                (razza_id, oggi, numero_capi, sesso, anno_nascita, destinazione),
            )
            db.execute(
                """INSERT INTO eventi_pulcinaia (razza_id, evento, data, numero_capi, data_nascita)
                   VALUES (?, 'promozione', ?, ?, ?)""",
                (razza_id, oggi, numero_capi, data_nascita),
            )
            flash(f"Promossi {numero_capi} capi da Pulcinaia a Pollaio")
        else:
            anno_nascita = int(request.form["anno_nascita"])
            prezzo_acquisto = request.form.get("prezzo_acquisto") or None
            db.execute(
                """INSERT INTO eventi_pollaio (razza_id, evento, data, numero_capi, sesso,
                                                anno_nascita, destinazione, prezzo_acquisto_totale)
                   VALUES (?, 'acquisto', ?, ?, ?, ?, ?, ?)""",
                (razza_id, oggi, numero_capi, sesso, anno_nascita, destinazione, prezzo_acquisto),
            )
            flash(f"Aggiunti {numero_capi} capi in pollaio (acquisto esterno)")

        db.commit()
        return redirect(url_for("pollaio_lista"))

    elenco_razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    return render_template(
        "pollaio_ingresso.html", elenco_razze=elenco_razze, destinazioni=DESTINAZIONI,
        gruppi_pulcinaia=pulcinaia_disponibili(db),
    )


def _pollaio_pool_dal_form(db, form):
    """Legge razza_id/sesso/anno_nascita/destinazione dai campi nascosti del
    form (popolati via JS dal menu 'quale gruppo' scelto nel popup) e
    restituisce il pool corrispondente."""
    return _pollaio_pool(
        db,
        razza_id=int(form["razza_id"]),
        sesso=form["sesso"],
        anno_nascita=int(form["anno_nascita"]),
        destinazione=form["destinazione"],
    )


DESTINAZIONE_PER_TIPO_USCITA_POLLAIO = {"vendita": "rivendita", "macellazione": "carne"}


@app.route("/pollaio/uscita/<tipo>", methods=["GET", "POST"])
def pollaio_uscita(tipo):
    if tipo not in TIPI_USCITA_POLLAIO:
        abort(404)
    db = get_db()
    if request.method == "POST":
        pool = _pollaio_pool_dal_form(db, request.form)
        numero_capi = int(request.form["numero_capi"] or 1)

        if pool is None or numero_capi < 1 or numero_capi > pool["numero_capi_attuale"]:
            flash("Numero di capi non disponibile in quel gruppo.")
            return redirect(url_for("pollaio_lista"))

        oggi = date.today().isoformat()
        prezzo_vendita = request.form.get("prezzo_vendita") or None if tipo == "vendita" else None

        db.execute(
            """INSERT INTO eventi_pollaio (razza_id, evento, data, numero_capi, sesso,
                                            anno_nascita, destinazione, prezzo_vendita_totale)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pool["razza_id"], tipo, oggi, numero_capi,
                pool["sesso"], pool["anno_nascita"], pool["destinazione"], prezzo_vendita,
            ),
        )
        db.commit()
        flash(f"Registrata {TIPI_USCITA_POLLAIO[tipo].lower()}: {numero_capi} capi")
        return redirect(url_for("pollaio_lista"))

    con_destinazione = tipo not in DESTINAZIONE_PER_TIPO_USCITA_POLLAIO
    gruppi = pollaio_disponibili(db, destinazione=DESTINAZIONE_PER_TIPO_USCITA_POLLAIO.get(tipo))
    return render_template(
        "pollaio_uscita.html", tipo=tipo, tipo_label=TIPI_USCITA_POLLAIO[tipo],
        con_destinazione=con_destinazione, gruppi_pollaio=[dict(g) for g in gruppi],
        destinazioni=DESTINAZIONI,
    )


@app.route("/pollaio/cambio-destinazione", methods=["GET", "POST"])
def pollaio_cambio_destinazione():
    db = get_db()
    if request.method == "GET":
        return render_template(
            "pollaio_cambio_destinazione.html",
            gruppi_pollaio=[dict(g) for g in pollaio_disponibili(db)],
            destinazioni=DESTINAZIONI,
        )

    pool = _pollaio_pool_dal_form(db, request.form)

    numero_capi = int(request.form["numero_capi"] or 1)
    nuova_destinazione = request.form["nuova_destinazione"]

    if pool is None or numero_capi < 1 or numero_capi > pool["numero_capi_attuale"]:
        flash("Numero di capi non disponibile in quel gruppo.")
        return redirect(url_for("pollaio_lista"))
    if nuova_destinazione == pool["destinazione"]:
        flash("La nuova destinazione deve essere diversa da quella attuale.")
        return redirect(url_for("pollaio_lista"))

    oggi = date.today().isoformat()
    comuni = (pool["razza_id"], oggi, numero_capi, pool["sesso"], pool["anno_nascita"])
    # riga di uscita dal pool con la vecchia destinazione
    db.execute(
        """INSERT INTO eventi_pollaio (razza_id, evento, data, numero_capi, sesso,
                                        anno_nascita, destinazione)
           VALUES (?, 'cambio_destinazione_uscita', ?, ?, ?, ?, ?)""",
        comuni + (pool["destinazione"],),
    )
    # riga di entrata nel pool con la nuova destinazione
    db.execute(
        """INSERT INTO eventi_pollaio (razza_id, evento, data, numero_capi, sesso,
                                        anno_nascita, destinazione)
           VALUES (?, 'cambio_destinazione_entrata', ?, ?, ?, ?, ?)""",
        comuni + (nuova_destinazione,),
    )
    db.commit()
    flash(
        f"Cambiata destinazione di {numero_capi} capi: "
        f"{DESTINAZIONI[pool['destinazione']]} → {DESTINAZIONI[nuova_destinazione]}"
    )
    return redirect(url_for("pollaio_lista"))


def registro_uova_per_razza(db):
    """Giacenza di uova per razza (raccolte - vendute), incluse le razze
    senza movimenti, più il totale complessivo."""
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    righe = db.execute(
        """SELECT razza_id,
                  SUM(CASE WHEN evento = 'raccolta' THEN numero_uova ELSE 0 END) AS raccolte,
                  SUM(CASE WHEN evento = 'vendita' THEN numero_uova ELSE 0 END) AS vendute
           FROM eventi_registro_uova
           GROUP BY razza_id"""
    ).fetchall()
    giacenza_per_razza = {r["razza_id"]: r["raccolte"] - r["vendute"] for r in righe}

    gruppi = []
    totale_giacenza = 0
    for razza in razze:
        giacenza = giacenza_per_razza.get(razza["id"], 0)
        totale_giacenza += giacenza
        gruppi.append({"razza_id": razza["id"], "razza": razza["nome"], "giacenza": giacenza})
    return gruppi, totale_giacenza


def _giacenza_uova(db, razza_id):
    riga = db.execute(
        """SELECT
             SUM(CASE WHEN evento = 'raccolta' THEN numero_uova ELSE 0 END)
             - SUM(CASE WHEN evento = 'vendita' THEN numero_uova ELSE 0 END) AS giacenza
           FROM eventi_registro_uova
           WHERE razza_id = ?""",
        (razza_id,),
    ).fetchone()
    return (riga["giacenza"] or 0) if riga and riga["giacenza"] is not None else 0


@app.route("/registro-uova")
def registro_uova_lista():
    db = get_db()
    gruppi, _ = registro_uova_per_razza(db)
    return render_template("registro_uova.html", gruppi=gruppi)


@app.route("/registro-uova/raccolta", methods=["GET", "POST"])
def registro_uova_raccolta():
    db = get_db()
    if request.method == "POST":
        razza_id = int(request.form["razza_id"])
        numero_uova = int(request.form["numero_uova"] or 1)
        oggi = date.today().isoformat()
        db.execute(
            "INSERT INTO eventi_registro_uova (razza_id, evento, data, numero_uova) VALUES (?, 'raccolta', ?, ?)",
            (razza_id, oggi, numero_uova),
        )
        db.commit()
        flash(f"Raccolte {numero_uova} uova")
        return redirect(url_for("registro_uova_lista"))
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    return render_template("registro_uova_raccolta.html", razze=razze)


@app.route("/registro-uova/vendita", methods=["GET", "POST"])
def registro_uova_vendita():
    db = get_db()
    if request.method == "POST":
        razza_id = int(request.form["razza_id"])
        numero_uova = int(request.form["numero_uova"] or 1)
        prezzo_vendita = request.form.get("prezzo_vendita") or None
        giacenza = _giacenza_uova(db, razza_id)

        if numero_uova < 1 or numero_uova > giacenza:
            flash("Numero di uova non disponibile in giacenza.")
            return redirect(url_for("registro_uova_vendita"))

        oggi = date.today().isoformat()
        db.execute(
            """INSERT INTO eventi_registro_uova (razza_id, evento, data, numero_uova, prezzo_vendita_totale)
               VALUES (?, 'vendita', ?, ?, ?)""",
            (razza_id, oggi, numero_uova, prezzo_vendita),
        )
        db.commit()
        flash(f"Vendute {numero_uova} uova")
        return redirect(url_for("registro_uova_lista"))
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    return render_template("registro_uova_vendita.html", razze=razze)


def _salva_razza(db, form, razza_id=None):
    nome = form["nome"]
    if razza_id is None:
        db.execute("INSERT INTO razze (nome) VALUES (?)", (nome,))
    else:
        db.execute("UPDATE razze SET nome=? WHERE id=?", (nome, razza_id))


@app.route("/bilancio")
def bilancio():
    return render_template("bilancio.html")


@app.route("/proiezioni")
def proiezioni():
    return render_template("proiezioni.html")


AREA_INFO = {
    "incubazione": ("🐣", "Incubazione"),
    "pulcinaia": ("🐤", "Pulcinaia"),
    "pollaio": ("🐔", "Pollaio"),
    "uova": ("🥚", "Uova"),
}

EVENTO_LABEL = {
    "entrata": "Entrata",
    "acquisto": "Acquisto",
    "perdita": "Perdita",
    "trasferimento": "Trasferimento in pulcinaia",
    "promozione": "Promozione",
    "vendita": "Vendita",
    "macellazione": "Macellazione",
    "cambio_destinazione_uscita": "Cambio destinazione",
    "cambio_destinazione_entrata": "Cambio destinazione",
    "raccolta": "Raccolta",
}

EVENTI_POSITIVI_PER_AREA = {
    "incubazione": {"entrata", "acquisto"},
    "pulcinaia": {"entrata", "acquisto"},
    "pollaio": {"promozione", "acquisto", "cambio_destinazione_entrata"},
    "uova": {"raccolta"},
}

# Solo per il filtro: distingue le due direzioni del cambio destinazione,
# che in EVENTO_LABEL condividono la stessa etichetta visualizzata.
EVENTO_LABEL_FILTRO = {
    **EVENTO_LABEL,
    "cambio_destinazione_uscita": "Cambio destinazione (uscita)",
    "cambio_destinazione_entrata": "Cambio destinazione (entrata)",
}


def log_attivita_eventi(db, area=None, razza_id=None, evento=None):
    """Unifica i quattro log di eventi in un unico feed cronologico, con filtri opzionali."""
    righe = db.execute(
        """
        SELECT * FROM (
            SELECT razza_id, evento, data, numero_uova AS quantita, 'uova' AS unita, 'incubazione' AS area,
                   NULL AS sesso, NULL AS anno_nascita, NULL AS destinazione, NULL AS data_nascita,
                   prezzo_acquisto_totale, NULL AS prezzo_vendita_totale
            FROM eventi_incubatrice
            UNION ALL
            SELECT razza_id, evento, data, numero_capi, 'capi', 'pulcinaia',
                   NULL, NULL, NULL, data_nascita,
                   prezzo_acquisto_totale, prezzo_vendita_totale
            FROM eventi_pulcinaia
            UNION ALL
            SELECT razza_id, evento, data, numero_capi, 'capi', 'pollaio',
                   sesso, anno_nascita, destinazione, NULL,
                   prezzo_acquisto_totale, prezzo_vendita_totale
            FROM eventi_pollaio
            UNION ALL
            SELECT razza_id, evento, data, numero_uova, 'uova', 'uova',
                   NULL, NULL, NULL, NULL,
                   NULL, prezzo_vendita_totale
            FROM eventi_registro_uova
        )
        WHERE (:area IS NULL OR area = :area)
          AND (:razza_id IS NULL OR razza_id = :razza_id)
          AND (:evento IS NULL OR evento = :evento)
        ORDER BY data DESC, razza_id
        """,
        {"area": area, "razza_id": razza_id, "evento": evento},
    ).fetchall()

    razze = {r["id"]: r["nome"] for r in db.execute("SELECT id, nome FROM razze").fetchall()}

    eventi = []
    for r in righe:
        icona, area_label = AREA_INFO[r["area"]]
        dettagli = []
        if r["sesso"]:
            dettagli.append(SESSO_LABEL[r["sesso"]])
        if r["anno_nascita"]:
            dettagli.append(f"nati nel {r['anno_nascita']}")
        if r["destinazione"]:
            dettagli.append(DESTINAZIONI[r["destinazione"]])
        if r["data_nascita"]:
            dettagli.append(f"nato il {r['data_nascita']}")

        prezzo = r["prezzo_vendita_totale"] or r["prezzo_acquisto_totale"]
        prezzo_tipo = "vendita" if r["prezzo_vendita_totale"] else "acquisto"

        eventi.append({
            "data": r["data"],
            "icona": icona,
            "area": area_label,
            "evento": EVENTO_LABEL.get(r["evento"], r["evento"]),
            "razza": razze.get(r["razza_id"], "—"),
            "segno": "+" if r["evento"] in EVENTI_POSITIVI_PER_AREA[r["area"]] else "-",
            "quantita": r["quantita"],
            "unita": r["unita"],
            "dettaglio": " · ".join(dettagli),
            "prezzo": prezzo,
            "prezzo_tipo": prezzo_tipo,
        })
    return eventi


@app.route("/log-attivita")
def log_attivita():
    db = get_db()
    razze = db.execute("SELECT id, nome FROM razze ORDER BY nome").fetchall()
    area = request.args.get("area") or None
    razza_id = request.args.get("razza_id") or None
    evento = request.args.get("evento") or None
    return render_template(
        "log_attivita.html",
        eventi=log_attivita_eventi(db, area=area, razza_id=int(razza_id) if razza_id else None, evento=evento),
        razze=razze,
        aree=AREA_INFO,
        eventi_label=EVENTO_LABEL_FILTRO,
        filtri={"area": area or "", "razza_id": razza_id or "", "evento": evento or ""},
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


@app.route("/razze/<int:razza_id>/elimina", methods=["POST"])
def razza_elimina(razza_id):
    db = get_db()
    tabelle_eventi = ("eventi_incubatrice", "eventi_pulcinaia", "eventi_pollaio", "eventi_registro_uova")
    ha_eventi = any(
        db.execute(f"SELECT 1 FROM {tabella} WHERE razza_id = ? LIMIT 1", (razza_id,)).fetchone()
        for tabella in tabelle_eventi
    )
    if ha_eventi:
        flash("Non puoi eliminare una razza con eventi già registrati.")
    else:
        db.execute("DELETE FROM razze WHERE id = ?", (razza_id,))
        db.commit()
        flash("Razza eliminata")
    return redirect(url_for("razze_lista"))


if __name__ == "__main__":
    app.run(debug=True)
