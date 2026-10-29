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

> **Una prenotazione alla volta: decidi E scrivi, poi passa alla successiva.** Non analizzare più prenotazioni
> insieme né in anticipo, non decidere a gruppi per scrivere dopo. Ogni decisione si prende sul file com'è in quel
> momento.
>
> **"Le unità di adesso sono tutte occupate" non dimostra niente**: prima di mandare qualcuno all'altro turno o di
> rifiutarlo, la skill `assegna-tavoli` va eseguita per intero, passo 2 (divisioni e catene fino a 3 spostamenti) e
> passo 3 compresi, e nel registro va scritto in `provati` che cosa hai provato.

1. Leggi la sala (skill `sala`) e il file. Ordina le prenotazioni per `prenotata_il`; a parità, l'ordine del file.
2. Crea con Write `prove/<etichetta>/AAAA-MM-GG.json` con lo scheletro della skill `stato-serata`.
3. Per ogni prenotazione, nell'ordine (k = 1, 2, …):
   1. `n` = k, `id`, `nome`, `coperti`, `orario`, `note` ("" se manca), `ricevuta_il` = `prenotata_il`.
   2. Turno chiesto T dalle regole dell'orario (skill `prenotazione`, punto 3), oppure dal campo `turno`.
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
4. Alla fine: skill `controllo-serata` completa sul file.
5. Scrivi `prove/<etichetta>/esito.md` (sotto).

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
- Marini ×10 (21:45): secondo turno pieno (dimostrato: …); primo turno … · mossa possibile: … / nessuna
## Su proposta
- Ferrara ×14: chiesto il primo turno (20:15), entrata nel secondo
## Cambi di tavolo
- Verdi ×7: da 10 a 13A+13B, per far posto a Costa ×10 (secondo turno)
## Da preparare in sala
(come nel riepilogo: blocchi divisi, unioni, lungo, cambi alle 21:30)
## Controllo
Controllo 2026-10-31: PASS (14 controlli, 0 avvisi)
## Confronto con il riferimento
```

**Riferimento** (motore CP-SAT del repository di origine sulla piantina del 29/10/2026, politica `sempre`): sabato
`olimpo_sabato.json` 63 accettate su 67 (6 su proposta), 242 coperti su 260, rifiutate Marini ×10, Palumbo ×2,
Sala ×4, Rossetti ×2; venerdì `olimpo_venerdi.json` 35 su 35. Nella sezione del confronto scrivi i tuoi numeri accanto
a questi e le prenotazioni che differiscono. Un risultato diverso non è per forza un errore (il motore cerca tra tutte
le disposizioni), ma ogni rifiuto "non dimostrato" va elencato.
