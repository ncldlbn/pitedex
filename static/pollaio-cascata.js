function opzioniUniche(righe, chiave, etichettaFn) {
    const viste = new Map();
    righe.forEach(r => {
        const valore = String(r[chiave]);
        if (!viste.has(valore)) viste.set(valore, etichettaFn(r));
    });
    return Array.from(viste.entries()).sort((a, b) => a[1].localeCompare(b[1], "it"));
}

function popola(select, opzioni) {
    const precedente = select.value;
    select.innerHTML = "";
    opzioni.forEach(([valore, etichetta]) => {
        const opt = document.createElement("option");
        opt.value = valore;
        opt.textContent = etichetta;
        select.appendChild(opt);
    });
    if (opzioni.some(([valore]) => valore === precedente)) select.value = precedente;
}

function initCascataGruppo(prefix, righeBase, conDestinazione, destinazioneLabel) {
    // Sostituisce i <select> con un clone vuoto (stesso id, nessun listener):
    // la funzione può essere richiamata più volte sulla stessa pagina (es.
    // quando l'utente cambia "Tipo") senza accumulare listener sui vecchi nodi.
    function rimpiazza(id) {
        const el = document.getElementById(id);
        if (!el) return null;
        const nuovo = el.cloneNode(false);
        el.replaceWith(nuovo);
        return nuovo;
    }

    const selRazza = rimpiazza(prefix + "-select-razza");
    if (!selRazza) return;
    const selSesso = rimpiazza(prefix + "-select-sesso");
    const selAnno = rimpiazza(prefix + "-select-anno");
    const selDestinazione = conDestinazione ? rimpiazza(prefix + "-select-destinazione") : null;
    const numero = document.getElementById(prefix + "-numero");
    const hint = document.getElementById(prefix + "-disponibili-hint");
    const campi = {
        razza_id: document.getElementById(prefix + "-razza-id"),
        sesso: document.getElementById(prefix + "-sesso"),
        anno_nascita: document.getElementById(prefix + "-anno-nascita"),
        destinazione: conDestinazione ? document.getElementById(prefix + "-destinazione") : null,
    };

    const righePerRazza = () => righeBase.filter(r => String(r.razza_id) === selRazza.value);
    const righePerSesso = () => righePerRazza().filter(r => r.sesso === selSesso.value);
    const righePerAnno = () => righePerSesso().filter(r => String(r.anno_nascita) === selAnno.value);

    function aggiornaFinale() {
        const riga = conDestinazione
            ? righePerAnno().find(r => r.destinazione === selDestinazione.value)
            : righePerAnno()[0];
        if (!riga) {
            hint.textContent = "Nessun capo disponibile.";
            numero.max = 0;
            return;
        }
        campi.razza_id.value = riga.razza_id;
        campi.sesso.value = riga.sesso;
        campi.anno_nascita.value = riga.anno_nascita;
        if (conDestinazione) campi.destinazione.value = riga.destinazione;
        numero.max = riga.numero_capi_attuale;
        hint.textContent = riga.numero_capi_attuale + " disponibili";
    }

    function aggiornaDestinazione() {
        if (conDestinazione) {
            popola(selDestinazione, opzioniUniche(righePerAnno(), "destinazione", r => destinazioneLabel[r.destinazione]));
        }
        aggiornaFinale();
    }

    function aggiornaAnno() {
        popola(selAnno, opzioniUniche(righePerSesso(), "anno_nascita", r => "Nati nel " + r.anno_nascita));
        aggiornaDestinazione();
    }

    function aggiornaSesso() {
        popola(selSesso, opzioniUniche(righePerRazza(), "sesso", r => r.sesso === "M" ? "Maschi" : "Femmine"));
        aggiornaAnno();
    }

    popola(selRazza, opzioniUniche(righeBase, "razza_id", r => r.razza_nome));

    selRazza.addEventListener("change", aggiornaSesso);
    selSesso.addEventListener("change", aggiornaAnno);
    selAnno.addEventListener("change", aggiornaDestinazione);
    if (conDestinazione) selDestinazione.addEventListener("change", aggiornaFinale);

    aggiornaSesso();
}
