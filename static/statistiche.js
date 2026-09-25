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
    let x = clientX - rect.left + 12;
    let y = clientY - rect.top + 12;
    tooltip.style.left = x + "px";
    tooltip.style.top = y + "px";
}

/**
 * Grafico a linee multi-serie con crosshair e tooltip.
 * serie: [{ etichetta, colore, tratteggiata?, punti: [{data, totale}] }]
 */
function renderLineChart(container, serie, opzioni) {
    opzioni = opzioni || {};
    const suffisso = opzioni.suffisso || "";
    container.innerHTML = "";

    const tutteDate = Array.from(new Set(serie.flatMap(s => s.punti.map(p => p.data)))).sort();
    if (tutteDate.length === 0) {
        container.appendChild(creaEl("p", "hint", "Nessun dato disponibile."));
        return;
    }

    const larghezza = 640, altezza = 240;
    const margine = { alto: 16, destra: 16, basso: 26, sinistra: 40 };
    const areaW = larghezza - margine.sinistra - margine.destra;
    const areaH = altezza - margine.alto - margine.basso;

    const t0 = new Date(tutteDate[0]).getTime();
    const t1 = new Date(tutteDate[tutteDate.length - 1]).getTime();
    const scalaX = data => t1 === t0 ? areaW / 2 : ((new Date(data).getTime() - t0) / (t1 - t0)) * areaW;

    const massimo = Math.max(1, ...serie.flatMap(s => s.punti.map(p => p.totale)));
    const scalaY = v => areaH - (v / massimo) * areaH;

    const svg = creaSvgEl("svg", { viewBox: `0 0 ${larghezza} ${altezza}`, class: "grafico-svg", role: "img" });
    const g = creaSvgEl("g", { transform: `translate(${margine.sinistra},${margine.alto})` });
    svg.appendChild(g);

    // gridline + etichette asse Y (0, metà, massimo)
    [0, 0.5, 1].forEach(frac => {
        const y = areaH - frac * areaH;
        g.appendChild(creaSvgEl("line", { x1: 0, x2: areaW, y1: y, y2: y, class: "grafico-griglia" }));
        const testo = creaSvgEl("text", { x: -8, y: y, class: "grafico-asse-testo", "text-anchor": "end", "dominant-baseline": "middle" });
        testo.textContent = Math.round(frac * massimo);
        g.appendChild(testo);
    });

    // etichette asse X (prima e ultima data)
    [tutteDate[0], tutteDate[tutteDate.length - 1]].forEach((data, i) => {
        const testo = creaSvgEl("text", {
            x: scalaX(data), y: areaH + 18, class: "grafico-asse-testo",
            "text-anchor": i === 0 ? "start" : "end",
        });
        testo.textContent = formatDataBreve(data);
        g.appendChild(testo);
    });

    const crosshair = creaSvgEl("line", { y1: 0, y2: areaH, class: "grafico-crosshair" });
    crosshair.style.display = "none";
    g.appendChild(crosshair);

    serie.forEach(s => {
        if (!s.punti.length) return;
        const puntiXY = s.punti.map(p => [scalaX(p.data), scalaY(p.totale)]);
        const linea = creaSvgEl("polyline", {
            points: puntiXY.map(p => p.join(",")).join(" "),
            class: "grafico-linea" + (s.tratteggiata ? " grafico-linea-tratteggiata" : ""),
        });
        linea.style.stroke = s.colore;
        g.appendChild(linea);

        const [ux, uy] = puntiXY[puntiXY.length - 1];
        const punto = creaSvgEl("circle", { cx: ux, cy: uy, r: 4, class: "grafico-punto" });
        punto.style.fill = s.colore;
        g.appendChild(punto);

        const etichetta = creaSvgEl("text", { x: Math.min(ux + 8, areaW - 4), y: uy, class: "grafico-etichetta-diretta", "dominant-baseline": "middle" });
        etichetta.textContent = s.etichetta;
        g.appendChild(etichetta);
    });

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
        let piuVicina = tutteDate[0];
        let diffMin = Infinity;
        tutteDate.forEach(d => {
            const diff = Math.abs(new Date(d).getTime() - tPointer);
            if (diff < diffMin) { diffMin = diff; piuVicina = d; }
        });

        crosshair.setAttribute("x1", scalaX(piuVicina));
        crosshair.setAttribute("x2", scalaX(piuVicina));
        crosshair.style.display = "";

        tooltip.innerHTML = "";
        tooltip.appendChild(creaEl("div", "grafico-tooltip-data", formatDataBreve(piuVicina)));
        serie.forEach(s => {
            const puntiFinoA = s.punti.filter(p => p.data <= piuVicina);
            if (!puntiFinoA.length) return;
            const ultimo = puntiFinoA[puntiFinoA.length - 1];
            const riga = creaEl("div", "grafico-tooltip-riga");
            const chiave = creaEl("span", "grafico-tooltip-chiave");
            chiave.style.background = s.colore;
            riga.appendChild(chiave);
            riga.appendChild(document.createTextNode(s.etichetta + ": "));
            riga.appendChild(creaEl("strong", null, ultimo.totale + suffisso));
            tooltip.appendChild(riga);
        });
        tooltip.style.display = "";
        posizionaTooltip(tooltip, container, clientX, clientY);
    }

    svg.addEventListener("pointermove", e => aggiornaTooltip(e.clientX, e.clientY));
    svg.addEventListener("pointerleave", () => {
        tooltip.style.display = "none";
        crosshair.style.display = "none";
    });
}
