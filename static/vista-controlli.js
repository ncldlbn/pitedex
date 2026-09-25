function applicaVista(colonneMobile, colonneDesktop, ordine) {
    const griglia = document.querySelector(".box-grid");
    if (!griglia) return;

    const colonne = window.innerWidth <= 720 ? colonneMobile : colonneDesktop;
    griglia.style.setProperty("--colonne", colonne);

    const schede = Array.from(griglia.children).filter(el => el.classList.contains("card"));
    schede.sort((a, b) => {
        if (ordine === "numero-desc") return b.dataset.totale - a.dataset.totale;
        if (ordine === "numero-asc") return a.dataset.totale - b.dataset.totale;
        if (ordine === "alfa-desc") return b.dataset.nome.localeCompare(a.dataset.nome, "it");
        return a.dataset.nome.localeCompare(b.dataset.nome, "it"); // alfa-asc
    });
    schede.forEach(el => griglia.appendChild(el));
}

function initVistaSelect() {
    const selectVista = document.getElementById("vista-select");
    if (!selectVista) return;

    function aggiornaVista() {
        const vista = selectVista.value;
        document.querySelectorAll(".vista-blocco").forEach(el => {
            el.style.display = (vista !== "sesso" && el.dataset.vista === vista) ? "" : "none";
        });
    }

    selectVista.addEventListener("change", aggiornaVista);
    aggiornaVista();
}
