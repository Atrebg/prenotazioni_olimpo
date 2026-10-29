---
name: rigioca
description: Per prove e demo dell'Olimpo — rigioca un file di prenotazioni come dati/olimpo_sabato.json in ordine di arrivo (prenotata_il), come se ogni riga fosse un messaggio del proprietario, con una politica del cliente data (default "sempre": accetta la proposta dell'altro turno), e scrive prove/<etichetta>/AAAA-MM-GG.json più prove/<etichetta>/esito.md. Usala per "rigioca", "simula la serata", "prova il sabato", "demo".
---

# Rigioca una serata di prova

Stesse procedure dei messaggi veri (skill `prenotazione`, punti 3-4, e `assegna-tavoli`), ma **senza domande**: le
scelte le fa la politica del cliente. **Non tocca mai `serate/`**: scrive solo in `prove/`.

## Ingresso

- **File**: es. `dati/olimpo_sabato.json`, `dati/olimpo_venerdi.json`: `{"serata": "Sabato 31/10/2026 …",
  "prenotazioni": [{"id", "nome", "coperti", "orario", "prenotata_il", "note"?, "turno"?}]}`.
- **Data della serata**: la prima data GG/MM/AAAA nel campo `serata`, oppure quella detta nella richiesta. Se non c'è,
  è l'unica domanda che puoi fare, prima di cominciare.
- **Politica del cliente**: `sempre` (default: accetta sempre la proposta dell'altro turno) oppure `mai` (non la
  accetta mai: la prenotazione è rifiutata).
- **Etichetta**: quella della richiesta, altrimenti nome del file + politica (es. `olimpo_sabato-sempre`). Se
  `prove/<etichetta>/` esiste già e non ti hanno chiesto di sovrascriverla, aggiungi `-2`, `-3`….
- Regole fisse: un orario di 20:45 va nel **primo** turno; un campo `turno` ("primo"/"secondo") vince sull'orario.

## Procedura

> **Una prenotazione alla volta: decidi E scrivi, poi passa alla successiva.** È **vietato pianificare in anticipo**
> più prenotazioni: niente analisi a gruppi, niente elenco delle prossime decisioni, niente "le prime 50 vanno
> qui". Guardi solo la prenotazione k e il file com'è dopo la k − 1.
>
> **Prima di decidere la prenotazione k rileggi dal file le confermate del turno T**, con un Grep mirato sul file
> della prova: pattern `"turno": "primo", "stato": "confermata"` (o `"secondo"`), modalità `content`. Decidi su
> quelle righe, non a memoria. Se poi provi l'altro turno, rileggi anche le sue.
>
> **Non riusare l'esito di una prenotazione precedente**, anche della stessa taglia: ogni decisione rifà
> `assegna-tavoli` sullo stato appena riletto.
>
> **"Le unità di adesso sono tutte occupate" non dimostra niente**: prima di mandare qualcuno all'altro turno o di
> rifiutarlo, la skill `assegna-tavoli` va eseguita per intero (passo 2a con lo scambio lungo–tondo, catene fino a 3
> spostamenti, passo 3), e nel registro va scritto un `provati` specifico (controllo C15).

1. Leggi la sala (skill `sala`) e il file. Ordina le prenotazioni per `prenotata_il`; a parità, l'ordine del file.
2. Crea con Write `prove/<etichetta>/AAAA-MM-GG.json` con lo scheletro della skill `stato-serata`.
3. Per ogni prenotazione, nell'ordine (k = 1, 2, …):
   1. `n` = k, `id`, `nome`, `coperti`, `orario`, `note` ("" se manca), `ricevuta_il` = `prenotata_il`.
   2. Turno chiesto T dalle regole dell'orario (skill `prenotazione`, punto 3), oppure dal campo `turno`. Rileggi con
      Grep le confermate di T (riquadro sopra).
   3. **Orario dentro i turni**: `assegna-tavoli` per c = coperti in T, passi 0-4 completi.
      - ENTRA → `confermata`; registro: eventuali `cambio tavolo`, poi `confermata`.
      - Non entra, politica `mai` → `rifiutata` con il motivo di T (dimostrato o no); registro `rifiutata`.
      - Non entra, politica `sempre` → `assegna-tavoli` nell'altro turno T'. Se entra: `confermata` con `turno` T' e
        `proposta` = `{"turno": T', "motivo": …}`; registro `proposta`, eventuali `cambio tavolo`,
        `accettata su proposta`. Se non entra: `rifiutata` con il motivo dei due turni; registro `rifiutata`.
      - Formato del motivo (skill `stato-serata`): una parte per turno, nell'ordine provato, per esempio "primo turno:
        pieno (dimostrato: 2 gruppi da 11 in su, un solo lungo); secondo turno: non trovo posto (non dimostrato)".
        Per ogni turno non dimostrato, il campo `provati` nella riga di registro.
   4. **Orario fuori dai turni** (prima delle 19:15, dopo le 22:15): `turno_chiesto` `null`; politica `mai` →
      `rifiutata` ("orario fuori dai turni, proposta non accettata dal cliente"); politica `sempre` → prova il turno
      più vicino e, se non entra, l'altro, e registra come al punto 3 (`proposta`, `accettata su proposta`).
   5. Rifiutata in tutti e due i turni: guarda la skill `mossa-tavoli` **solo per scrivere nell'esito** "mossa
      possibile: …". Non applicarla e non scriverla in `mosse`.
   6. **Aggiorna il file DOPO OGNI prenotazione** (skill `stato-serata`, "Come scrivere"), prima di passare alla
      successiva: aggiungi la riga, le righe di registro e aggiorna le righe di chi hai spostato. Non decidere tutto a
      mente per scrivere alla fine: l'ordine di arrivo va rispettato e chi è entrato prima non si toglie più.
   7. Ogni 10 prenotazioni rileggi il file intero e applica i controlli C5, C6 e C9 della skill
      `controllo-serata`. In `rigioca` basta questo: non serve rileggere dopo ogni scrittura (la regola di
      `stato-serata` vale per i messaggi veri).
   8. Se ti fermi o riprendi dopo un'interruzione, il file è la verità: rileggilo e riparti dalla prenotazione dopo
      l'ultimo `n` scritto, senza rifare le precedenti.
4. Alla fine: skill `controllo-serata` completa sul file (con Haiku, se non riesci a farla per intero, passala
   all'agente `controllo-sala`).
5. Scrivi `prove/<etichetta>/esito.md` (sotto).

In ogni riga di registro metti `deciso_da` con il modello che ha deciso quella prenotazione.

## Modalità mista (la sessione gira su Haiku)

Per **ogni** prenotazione, una alla volta:
1. Haiku rilegge con Grep le confermate del turno chiesto T e fa i **passi 0 e 1** di `assegna-tavoli` in T (per un
   orario fuori dai turni, nel turno più vicino).
2. **ENTRA al passo 1** (unità libera adatta, nessun conteggio superato, nessuno spostato) → Haiku scrive la
   prenotazione come al punto 3, con `deciso_da` "haiku". Per un orario fuori dai turni con la politica `sempre`
   scrive `proposta` e `accettata su proposta`.
3. **Tutto il resto** (passo 1 senza unità, conteggio superato, dubbio) → Haiku chiama l'agente `decisore-sala` per
   **quella sola** prenotazione e passa: il path del file della prova, la riga della prenotazione del file di
   ingresso con il suo `n` e `prenotata_il`, la politica del cliente, la data della serata e la frase "rigioca:
   niente domande, 20:45 nel primo turno, decidi e scrivi solo questa prenotazione". **Aspetta** che abbia scritto il
   file, poi passa alla prenotazione successiva. Non rifare e non riscrivere ciò che ha deciso.
4. Mai una chiamata per più prenotazioni insieme, mai mandargli le prossime "già che c'è".
5. Ogni 10 prenotazioni Haiku rilegge il file intero e fa C5, C6 e C9; alla fine il controllo completo (punto 4
   sopra). Nell'esito aggiungi quante prenotazioni ha deciso Haiku e quante `decisore-sala` (dal campo `deciso_da`).

## esito.md

```
# Rigioca olimpo_sabato-sempre
File dati/olimpo_sabato.json · serata 2026-10-31 · politica sempre · piantina 29/10/2026 (17 righe di storico)

| | prenotazioni | coperti |
|---|---|---|
| in tutto | 67 | 260 |
| accettate | … | … |
| di cui su proposta | … | … |
| rifiutate | … | … |
| primo turno (20:00) | … | … |
| secondo turno (21:30) | … | … |

## Rifiutate
- Nome ×N (HH:MM): secondo turno pieno (dimostrato: …); primo turno … · mossa possibile: … / nessuna
## Su proposta
- Nome ×N: chiesto il primo turno (HH:MM), entrata nel secondo
## Cambi di tavolo
- Verdi ×7: da 10 a 13A+13B, per far posto a Costa ×10 (secondo turno)
## Da preparare in sala
(come nel riepilogo: blocchi divisi, unioni, lungo, cambi alle 21:30)
## Controllo
Controllo 2026-10-31: PASS (15 controlli, 0 avvisi)
## Confronto con il riferimento
```

**Riferimento**: la skill non contiene i risultati attesi, apposta, perché una prova deve decidere ogni
prenotazione senza sapere come va a finire. **Non leggere il README né altri esiti prima di aver finito.** Nella
sezione del confronto scrivi i tuoi numeri ed elenca ogni rifiuto e ogni proposta "non dimostrati"; il confronto
con il motore lo fa chi ti ha chiesto la prova.
