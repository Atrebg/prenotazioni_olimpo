---
name: controllo-serata
description: Controlli C1-C15 di un file di serata dell'Olimpo (serate/ o prove/) rileggendolo — unità, posti, un gruppo per unità e turno, esclusività dei pezzi, stati, chi era dentro resta dentro, turno promesso, soglie, provati. Esito PASS/FAIL. Usala dopo ogni scrittura di un file di serata e prima di ogni riepilogo.
---

# Controllo di una serata

Rileggi il file con Read (non fidarti di quello che ricordi di aver scritto) e il catalogo (`agente/catalogo.md`).
Il registro per C1, C7, C8, C9, C11 e C15: solo con i Grep mirati di `stato-serata`. Poi fai **tutti** i controlli, da
C1 a C15, in ordine. Per C5-C6 scrivi a mente una tabella per turno: **unità → prenotazione → pezzi usati**.

**Quando.** Per i messaggi veri: dopo **ogni** scrittura, per intero, come dice `CLAUDE.md`. Nella skill `rigioca`
vale la sua regola (C5, C6, C9 ogni 10 prenotazioni, tutto alla fine).

| # | controllo | se non va |
|---|---|---|
| C1 | Il file è JSON valido, con `serata`, `piantina`, `prenotazioni`, `mosse` (`registro` solo nei file vecchi); ogni prenotazione ha tutti i campi della skill `stato-serata` (se manca `domanda`, file vecchio: vale `null`). Il campo `deciso_da` delle righe di registro è facoltativo: se manca, nessun avviso; se c'è, è un nome di modello ("haiku", "sonnet", "opus") o "python" (lo script). Una riga `rifiutata`, una `proposta` per mancanza di posto ("pieno" o "non trovo posto" nel motivo) o un `cambio tavolo` (tranne dalla seconda alla prima metà del lungo dopo un annullamento) con `deciso_da` "haiku" va contro la modalità mista | FAIL; `domanda` mancante e righe difficili decise da Haiku solo AVVISO |
| C2 | `piantina` del file = piantina di oggi (`aggiornata` e numero di righe dello `storico`) | AVVISO; FAIL se un'unità assegnata non esiste più o ha meno posti dei coperti |
| C3 | La piantina ha la versione del catalogo (i Grep di `CLAUDE.md`); se è diversa, i quadrati mobili (quadrati + moduli dei blocchi mobili) sono quelli del catalogo | versione diversa: AVVISO "catalogo da rigenerare", non FAIL della serata; quadrati diversi: FAIL, i tavoli non possono sparire, va chiesto al proprietario |
| C4 | `n` tutti diversi; da 1 al più alto senza buchi | FAIL se ripetuti; AVVISO se mancano numeri |
| C5 | Ogni `confermata` ha `coperti` (non `null`), `turno` "primo" o "secondo", `domanda` `null`, `unita` del catalogo (o di una mossa `confermata` valida in quel turno), coperti ≤ posti dell'unità | FAIL; un gruppo che sta in una metà del lungo sul lungo intero è solo AVVISO |
| C6 | In ogni turno nessun pezzo è usato da due prenotazioni (quindi: una prenotazione per unità; blocco intero e suoi pezzi mai insieme; unione e suoi tavoli mai insieme; lungo intero mai con le sue metà); la seconda metà solo se la prima è occupata | FAIL |
| C7 | `in_attesa`: `unita` e `turno` `null`, e `proposta` oppure `domanda` presente (una `in_attesa` con `domanda` ha la sua riga `domanda` nel registro; solo lei può avere `coperti` o `orario` `null`). `rifiutata`: `unita` e `turno` `null`, `motivo` presente. `annullata`: `unita` `null`, `motivo` presente | FAIL |
| C8 | **Chi era dentro resta dentro**: nessuna prenotazione con una riga `confermata` o `accettata su proposta` nel registro è ora `rifiutata`; ogni `annullata` ha una riga `annullata` nel registro | FAIL |
| C9 | Per ogni `confermata`: `turno` = turno promesso dal registro (ultima riga `confermata`, `accettata su proposta` o `modifica` del suo `n`) e `unita` = ultima unità del registro (contando anche `cambio tavolo`, campo `a`) | FAIL |
| C10 | Una `confermata` con `proposta` non nulla ha `turno` = turno della proposta | FAIL |
| C11 | Ogni prenotazione ha almeno una riga nel registro; la prima riga di ogni `n` compare in ordine di `n` (chi arriva prima è registrato prima) | FAIL |
| C12 | Per ogni turno le soglie e i posti massimi del catalogo sono rispettati, con il lungo a un gruppo quando è obbligato | FAIL |
| C13 | Mosse: solo quelle `confermata` contano; i pezzi in `usa` esistono; nessun quadrato in due unità nello stesso turno (rientra in C6) | FAIL |
| C14 | `ricevuta_il` non decresce al crescere di `n` | AVVISO |
| C15 | Ogni riga di registro `proposta` o `rifiutata` il cui `motivo` ha un turno "non trovo posto (non dimostrato)" ha un campo `provati` **specifico** per quel turno: gli schemi del passo 2a guardati, scambio con il lungo compreso; per le catene da 1, 2 e 3 spostamenti la prima e l'ultima U provata; l'esito dei giri 1 e 2 del passo 3 (skill `assegna-tavoli-difficile`, "Cosa scrivere quando non entra"); con `deciso_da` "python", la verifica esatta e il tempo scaduto. `provati` mancante, vuoto o generico ("nessuna catena", "provato tutto") | FAIL |

## Esito

Scrivi l'esito così (nella risposta solo se non è PASS, oppure se te lo chiedono; esempi sulla piantina del
29/10/2026):

```
Controllo 2026-10-31: PASS (15 controlli, 0 avvisi)
```

```
Controllo 2026-10-31: FAIL
- C6 primo turno: 5ab (Bianchi ×6) e 5b (Verdi ×4) usano tutti e due 5b
Avvisi:
- C2 la piantina è cambiata il 30/10: unità ancora tutte valide
```

- **FAIL per un errore della scrittura appena fatta**: correggilo subito (rifai il passo sbagliato), rifai il
  controllo e solo dopo rispondi.
- **FAIL che non sai correggere** (o che viene da prima): non nasconderlo. Dillo al proprietario in una riga e non
  spostare nessuno senza chiedere.
- Per un secondo parere indipendente c'è l'agente `controllo-sala` (sola lettura).
