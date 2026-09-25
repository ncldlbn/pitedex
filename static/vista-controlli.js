function initControlliVista(colonneMobile, colonneDesktop) {
    const griglia = document.querySelector(".box-grid");
    const sliderColonne = document.getElementById("colonne-slider");
    const valoreColonne = document.getElementById("colonne-valore");
    const selectOrdine = document.getElementById("ordine-select");
    const selectVista = document.getElementById("vista-select");
    if (!griglia || !sliderColonne || !selectOrdine) return;

    function aggiornaColonne() {
        griglia.style.setProperty("--colonne", sliderColonne.value);
        valoreColonne.textContent = sliderColonne.value;
    }

    function aggiornaOrdine() {
        const schede = Array.from(griglia.children).filter(el => el.classList.contains("card"));
        const criterio = selectOrdine.value;
        schede.sort((a, b) => {
            if (criterio === "numero-desc") return b.dataset.totale - a.dataset.totale;
            if (criterio === "numero-asc") return a.dataset.totale - b.dataset.totale;
            if (criterio === "alfa-desc") return b.dataset.nome.localeCompare(a.dataset.nome, "it");
            return a.dataset.nome.localeCompare(b.dataset.nome, "it"); // alfa-asc
        });
        schede.forEach(el => griglia.appendChild(el));
    }

    function aggiornaVista() {
        if (!selectVista) return;
        const vista = selectVista.value;
        document.querySelectorAll(".vista-blocco").forEach(el => {
            el.style.display = (vista !== "sesso" && el.dataset.vista === vista) ? "" : "none";
        });
    }

    sliderColonne.value = window.innerWidth <= 720 ? colonneMobile : colonneDesktop;
    sliderColonne.addEventListener("input", aggiornaColonne);
    selectOrdine.addEventListener("change", aggiornaOrdine);
    if (selectVista) selectVista.addEventListener("change", aggiornaVista);

    aggiornaColonne();
    aggiornaOrdine();
    aggiornaVista();
}
