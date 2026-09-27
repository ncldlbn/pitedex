const SVG_NS = "http://www.w3.org/2000/svg";

function creaEl(tag, className, testo) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (testo !== undefined) el.textContent = testo;
    return el;
}

function creaSvgEl(tag, attributi) {
    const el = document.createElementNS(SVG_NS, tag);
    Object.entries(attributi || {}).forEach(([k, v]) => el.setAttribute(k, v));
    return el;
}

function formatDataBreve(iso) {
    const [, m, d] = iso.split("-");
    return d + "/" + m;
}

function posizionaTooltip(tooltip, container, clientX, clientY) {
    const rect = container.getBoundingClientRect();
    tooltip.style.left = (clientX - rect.left + 12) + "px";
    tooltip.style.top = (clientY - rect.top + 12) + "px";
}

/**
 * Grafico ad area impilata (stacked area): una banda per serie, valore
 * forward-filled fra un evento e il successivo. serie: [{ razza, colore,
 * punti: [{data, totale}] }] — "totale" già cumulato (vedi andamento nel tempo).
 */
function renderStackedAreaChart(container, serie, opzioni) {
    opzioni = opzioni || {};
    const suffisso = opzioni.suffisso || "";
    container.innerHTML = "";

    if (!serie.length) {
        container.appendChild(creaEl("p", "hint", "Nessuna razza selezionata."));
        return;
    }
    const tutteDate = Array.from(new Set(serie.flatMap(s => s.punti.map(p => p.data)))).sort();
    if (!tutteDate.length) {
        container.appendChild(creaEl("p", "hint", "Nessun dato disponibile."));
        return;
    }

    function valoreA(s, data) {
        const puntiFinoA = s.punti.filter(p => p.data <= data);
        return puntiFinoA.length ? puntiFinoA[puntiFinoA.length - 1].totale : 0;
    }

    // per ogni data: [{base, cima, valore}, ...] nello stesso ordine di "serie"
    const strati = tutteDate.map(data => {
        let base = 0;
        return serie.map(s => {
            const valore = valoreA(s, data);
            const strato = { base, cima: base + valore, valore };
            base += valore;
            return strato;
        });
    });

    const massimo = Math.max(1, ...strati.map(riga => riga[riga.length - 1].cima));

    const larghezza = 640, altezza = 280;
    const margine = { alto: 16, destra: 16, basso: 26, sinistra: 40 };
    const areaW = larghezza - margine.sinistra - margine.destra;
    const areaH = altezza - margine.alto - margine.basso;

    const t0 = new Date(tutteDate[0]).getTime();
    const t1 = new Date(tutteDate[tutteDate.length - 1]).getTime();
    const scalaX = data => t1 === t0 ? areaW / 2 : ((new Date(data).getTime() - t0) / (t1 - t0)) * areaW;
    const scalaY = v => areaH - (v / massimo) * areaH;

    const svg = creaSvgEl("svg", { viewBox: `0 0 ${larghezza} ${altezza}`, class: "grafico-svg", role: "img" });
    const g = creaSvgEl("g", { transform: `translate(${margine.sinistra},${margine.alto})` });
    svg.appendChild(g);

    [0, 0.5, 1].forEach(frac => {
        const y = areaH - frac * areaH;
        g.appendChild(creaSvgEl("line", { x1: 0, x2: areaW, y1: y, y2: y, class: "grafico-griglia" }));
        const testo = creaSvgEl("text", { x: -8, y, class: "grafico-asse-testo", "text-anchor": "end", "dominant-baseline": "middle" });
        testo.textContent = Math.round(frac * massimo);
        g.appendChild(testo);
    });

    [tutteDate[0], tutteDate[tutteDate.length - 1]].forEach((data, i) => {
        const testo = creaSvgEl("text", {
            x: scalaX(data), y: areaH + 18, class: "grafico-asse-testo",
            "text-anchor": i === 0 ? "start" : "end",
        });
        testo.textContent = formatDataBreve(data);
        g.appendChild(testo);
    });

    // una banda per serie, dal basso verso l'alto
    serie.forEach((s, indice) => {
        const puntiCima = tutteDate.map((data, gi) => [scalaX(data), scalaY(strati[gi][indice].cima)]);
        const puntiBase = tutteDate.map((data, gi) => [scalaX(data), scalaY(strati[gi][indice].base)]).reverse();
        const d = "M " + puntiCima.map(p => p.join(",")).join(" L ") + " L " + puntiBase.map(p => p.join(",")).join(" L ") + " Z";
        const banda = creaSvgEl("path", { d, class: "grafico-banda" });
        banda.style.fill = s.colore;
        g.appendChild(banda);
    });

    const crosshair = creaSvgEl("line", { y1: 0, y2: areaH, class: "grafico-crosshair" });
    crosshair.style.display = "none";
    g.appendChild(crosshair);

    container.appendChild(svg);

    const tooltip = creaEl("div", "grafico-tooltip");
    tooltip.style.display = "none";
    container.style.position = "relative";
    container.appendChild(tooltip);

    function aggiornaTooltip(clientX, clientY) {
        const rect = svg.getBoundingClientRect();
        const xSvg = ((clientX - rect.left) / rect.width) * larghezza - margine.sinistra;
        if (xSvg < 0 || xSvg > areaW) {
            tooltip.style.display = "none";
            crosshair.style.display = "none";
            return;
        }
        const tPointer = t0 + (xSvg / areaW) * (t1 - t0);
        let indiceVicino = 0, diffMin = Infinity;
        tutteDate.forEach((d, gi) => {
            const diff = Math.abs(new Date(d).getTime() - tPointer);
            if (diff < diffMin) { diffMin = diff; indiceVicino = gi; }
        });
        const data = tutteDate[indiceVicino];

        crosshair.setAttribute("x1", scalaX(data));
        crosshair.setAttribute("x2", scalaX(data));
        crosshair.style.display = "";

        tooltip.innerHTML = "";
        tooltip.appendChild(creaEl("div", "grafico-tooltip-data", formatDataBreve(data)));
        for (let i = serie.length - 1; i >= 0; i--) {
            const s = serie[i];
            const valore = strati[indiceVicino][i].valore;
            const riga = creaEl("div", "grafico-tooltip-riga");
            const chiave = creaEl("span", "grafico-tooltip-chiave");
            chiave.style.background = s.colore;
            riga.appendChild(chiave);
            riga.appendChild(document.createTextNode(s.razza + ": "));
            riga.appendChild(creaEl("strong", null, valore + suffisso));
            tooltip.appendChild(riga);
        }
        if (serie.length > 1) {
            const totale = strati[indiceVicino][serie.length - 1].cima;
            const rigaTotale = creaEl("div", "grafico-tooltip-riga grafico-tooltip-totale");
            rigaTotale.appendChild(document.createTextNode("Totale: "));
            rigaTotale.appendChild(creaEl("strong", null, totale + suffisso));
            tooltip.appendChild(rigaTotale);
        }
        tooltip.style.display = "";
        posizionaTooltip(tooltip, container, clientX, clientY);
    }

    svg.addEventListener("pointermove", e => aggiornaTooltip(e.clientX, e.clientY));
    svg.addEventListener("pointerleave", () => {
        tooltip.style.display = "none";
        crosshair.style.display = "none";
    });
}
