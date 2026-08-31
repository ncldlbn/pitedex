# Sistema di gestione digitale per allevamento avicolo rustico — Riepilogo di progetto

> Documento di handoff per avviare/proseguire l'implementazione. Contiene obiettivo, architettura logica, stato di avanzamento e decisioni prese finora.

---

## 1. Obiettivo generale

Costruire un sistema digitale di gestione per un **piccolo allevamento avicolo all'aperto** (razze locali/rustiche), che vende **uova, animali vivi e animali macellati**. L'obiettivo finale è un **"digital twin"** dell'azienda: monitoraggio operativo + previsione economico-gestionale.

Il progetto è strutturato in **tre fasi sequenziali**, ciascuna costruita sopra la precedente.

---

## 2. Struttura a fasi

### Fase 1 — Anagrafica animali (base dati)
- Tracciamento **gruppi/capi** per razza, sesso ed età.
- **Età calcolata dinamicamente** dalla data di nascita (non un campo statico).
- Eventi tracciati: nascite, acquisti, morti, vendite di animali vivi, macellazione.
- Campi aggiunti fin da subito per uso nelle fasi successive:
  - **destinazione d'uso funzionale** per animale (uova / carne / riproduzione) — pensata come **tag mutabile legato all'evento più recente**, non attributo fisso.
  - **capacità massima del pollaio** (per pollaio/gruppo).

### Fase 2 — Curve di produzione modellate
- **Curva di ovodeposizione**: famiglia di modelli **Adams-Bell**.
- **Curva di crescita/peso**: **Gompertz-Laird**.
- **Consumo alimentare**: mantenimento proporzionale al **peso metabolico** + quota di produzione derivata dalla curva di deposizione.
- **Stagionalità**: fotoperiodo influenza la curva di deposizione, da cui si propaga automaticamente al consumo alimentare.
- **Stress termico (THI)**: parametro specifico di razza; le **variazioni brusche di THI sono più pericolose di quelle graduali** a parità di valore finale → serve tracciare la variazione giornaliera, non solo le medie.
- **Cova (broodiness)** nella Moroseta/Silkie: va modellata come **stato distinto che interrompe la curva di deposizione**, non come semplice riduzione di produzione.

### Fase 3 — Simulatore di scenario / supporto decisionale
Logica formalizzata finora (prima del codice):

- **Margine atteso per destinazione**: funzione di razza, sesso, età, orizzonte temporale, derivata dalle curve di Fase 2.
- **Costo opportunità della scelta di destinazione**: margine della miglior alternativa disponibile meno margine dell'opzione scelta.
- **Confronto produci-vs-compra**: include costo opportunità dello slot (margine perso mentre un capo giovane occupa spazio prima di diventare produttivo), mortalità attesa, costi di alimentazione nel periodo di maturazione.
- **Logica di allocazione**: la domanda supera sempre l'offerta nella pratica → il **vincolo reale è la capacità del pollaio**, non la domanda. Si usano **soglie minime garantite** per destinazione (per preservare le relazioni con i clienti), con il surplus allocato alla destinazione a margine più alto. Se le soglie minime superano collettivamente i capi disponibili, il sistema **segnala il conflitto senza risolverlo automaticamente** — la priorità resta una decisione dell'utente.
- **Sistema di allerta proattiva**: proietta l'offerta futura per destinazione usando la composizione attuale del gregge + curve di Fase 2 (con mortalità, invecchiamento fuori target, vendite pianificate), la confronta con la domanda attesa, e genera allerte con anticipo sufficiente. Se lo scarto rientra nella finestra del lead time produttivo, l'allerta segnala esplicitamente che **resta percorribile solo l'acquisto**, non la produzione interna.

---

## 3. Razze trattate

| Razza | Note |
|---|---|
| ISA Brown | Ibrido commerciale da uova, riferimento produttivo |
| Australorp | Doppia attitudine |
| Plymouth Rock | Doppia attitudine |
| Pepoi | Razza nana italiana |
| Moroseta / Silkie | Ornamentale, bassa produzione, **cova da modellare come stato distinto** |

Focus particolare su **razze autoctone italiane**.

---

## 4. Stato attuale

- Logica decisionale di **Fase 3** formalizzata (formule e struttura, non ancora codice) — vedi sezione 2.
- Costruito un **prototipo dashboard interattivo HTML/CSS/JS**:
  - 5 razze italiane campione, layout a "lot-card"
  - cross-filtering tramite grafico a ciambella, barre per razza, colonne per età, filtri a chip
  - estetica "farm-ledger": font **Fraunces + IBM Plex**, palette verde stalla / pergamena calda
  - pensato per essere **portato a Flask/Jinja2**
- Prodotto un **documento di sintesi/riferimento** con piano a tre fasi, dati di razza e bibliografia.

---

## 5. Prossimi passi

1. **Porting del prototipo dashboard** da HTML/JS a Flask + HTML/CSS (Jinja2).
2. Incorporare **storico pluriennale della domanda** per stimare trend e stagionalità nel modello di allerta/allocazione.
3. Integrare **dati meteo/THI** nelle curve di produzione di Fase 2 (fotoperiodo calcolabile da data + coordinate; temperature estreme giornaliere e picchi improvvisi di THI come fattori di rischio mortalità).
4. Rimandati a plugin futuri: **tracciabilità sanitaria**, **inventario mangimi**, **esportazione dati**.

---

## 6. Principi chiave già stabiliti (da non violare in fase di implementazione)

- La cova nella Moroseta/Silkie è uno **stato**, non un moltiplicatore di produzione.
- La classe d'età è un **campo calcolato** dalla data di nascita.
- La destinazione di produzione è un **tag mutabile** legato all'evento più recente, non un attributo fisso.
- Le variazioni **brusche** di THI sono più rischiose di quelle graduali a parità di valore finale → serve granularità giornaliera.
- La sensibilità termica è un **parametro specifico di razza**.
- La domanda supera l'offerta → **niente tetti di domanda** nei modelli di allocazione, il vincolo è la capacità.
- Soglie minime collettivamente infattibili → **segnalare, non risolvere automaticamente**.

---

## 7. Approccio di lavoro (da mantenere)

- **Ragionare su logica e formule prima di scrivere codice** — preferenza esplicita e mantenuta in tutte le sessioni sulla Fase 3.
- Procedere **fase per fase**, con decisioni deliberate su cosa anticipare (es. campi destinazione/capacità già in Fase 1 pur essendo usati solo in Fase 3).
- **Alto impatto visivo** nei prototipi UI prima di impegnarsi su un framework backend definitivo.

---

## 8. Stack tecnologico

- Prototipo attuale: **HTML/CSS/JS** (dashboard) — target di porting: **Flask + Jinja2**
- Prototipo iniziale alternativo: React (esplorato, non quello scelto per il porting)

---

## 9. Riferimenti bibliografici principali

- Bell & Weaver — manuale di produzione avicola commerciale
- Cerolini et al. — testo universitario italiano
- NRC — *Nutrient Requirements of Poultry*
- Guide gestionali per ibridi commerciali
- *World's Poultry Science Journal* — modelli matematici delle curve
- Studio Gompertz sulla crescita in razze rustiche/heritage
- FAO — manuale per la produzione avicola su piccola scala
- FIAV — risorse sulle razze avicole autoctone italiane

---

*Documento generato come riepilogo di contesto per proseguire il lavoro con un'istanza Claude locale (es. Claude Code), a partire dal porting Flask della dashboard e dall'implementazione della logica di Fase 3 già formalizzata.*
