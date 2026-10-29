---
name: controllo-serata
description: Controlli da fare su un file di serata dell'Olimpo (serate/AAAA-MM-GG.json o prove/…) rileggendolo — unità esistenti, posti, un gruppo per unità e per turno, esclusività di pezzi, unioni e lungo, stati coerenti, chi era confermato resta dentro, turno promesso, conteggi per soglia, 29 quadrati. Esito PASS/FAIL con l'elenco. Usala dopo ogni scrittura di un file di serata e prima di ogni riepilogo.
---

# Controllo di una serata

Rileggi il file con Read (non fidarti di quello che ricordi di aver scritto) e il catalogo della skill `sala`.
Poi fai **tutti** i controlli, da C1 a C15, in ordine. Per C5-C6 scrivi a mente una tabella per turno: **unità →
prenotazione → pezzi usati**.

**Quando.** Per i messaggi veri: dopo **ogni** scrittura, per intero, anche con `claude -p` (ogni messaggio è una
sessione nuova e deve fare il suo controllo). "Controllo: PASS" si scrive nella risposta solo se hai fatto C1-C15
per intero su quel file riletto; se non l'hai fatto, non rispondere ancora: fallo. Nella skill `rigioca` vale la sua
regola (C5, C6, C9 ogni 10 prenotazioni, tutto alla fine).

| # | controllo | se non va |
|---|---|---|
| C1 | Il file è JSON valido, con `serata`, `piantina`, `prenotazioni`, `mosse`, `registro`; ogni prenotazione ha tutti i campi della skill `stato-serata` (se manca `domanda`, file vecchio: vale `null`) | FAIL; `domanda` mancante solo AVVISO |
| C2 | `piantina` del file = piantina di oggi (`aggiornata` e numero di righe dello `storico`) | AVVISO; FAIL se un'unità assegnata non esiste più o ha meno posti dei coperti |
| C3 | La piantina ha 29 quadrati mobili (quadrati + moduli dei blocchi mobili) | FAIL: i tavoli non possono sparire, va chiesto al proprietario |
| C4 | `n` tutti diversi; da 1 al più alto senza buchi | FAIL se ripetuti; AVVISO se mancano numeri |
| C5 | Ogni `confermata` ha `coperti` (non `null`), `turno` "primo" o "secondo", `domanda` `null`, `unita` del catalogo (o di una mossa `confermata` valida in quel turno), coperti ≤ posti dell'unità, limiti di taglia (da 11 in su solo "11"; 9-10 solo "10" o "11") | FAIL; un gruppo fino a 8 su "11" è solo AVVISO |
| C6 | In ogni turno nessun pezzo è usato da due prenotazioni (quindi: una prenotazione per unità; blocco intero e suoi pezzi mai insieme; unione e suoi tavoli mai insieme; "11" mai con "11-1"/"11-2"); "11-2" solo se "11-1" è occupato | FAIL |
| C7 | `in_attesa`: `unita` e `turno` `null`, e `proposta` oppure `domanda` presente (una `in_attesa` con `domanda` ha la sua riga `domanda` nel registro; solo lei può avere `coperti` o `orario` `null`). `rifiutata`: `unita` e `turno` `null`, `motivo` presente. `annullata`: `unita` `null`, `motivo` presente | FAIL |
| C8 | **Chi era dentro resta dentro**: nessuna prenotazione con una riga `confermata` o `accettata su proposta` nel registro è ora `rifiutata`; ogni `annullata` ha una riga `annullata` nel registro | FAIL |
| C9 | Per ogni `confermata`: `turno` = turno promesso dal registro (ultima riga `confermata`, `accettata su proposta` o `modifica` del suo `n`) e `unita` = ultima unità del registro (contando anche `cambio tavolo`, campo `a`) | FAIL |
| C10 | Una `confermata` con `proposta` non nulla ha `turno` = turno della proposta | FAIL |
| C11 | Ogni prenotazione ha almeno una riga nel registro; la prima riga di ogni `n` compare in ordine di `n` (chi arriva prima è registrato prima) | FAIL |
| C12 | Per ogni turno i conteggi per soglia e i 151 posti (skill `sala`, punto 6) sono rispettati. Se nel turno c'è un gruppo da 11 in su, o ci sono due gruppi da 9 in su, il lungo vale una sola unità: togli 1 ai totali delle soglie da 2 a 8 (35, 28, 27, 13, 5) | FAIL |
| C13 | Mosse: solo quelle `confermata` contano; i pezzi in `usa` esistono; nessun quadrato in due unità nello stesso turno (rientra in C6) | FAIL |
| C14 | `ricevuta_il` non decresce al crescere di `n` | AVVISO |
| C15 | Ogni riga di registro `proposta` o `rifiutata` il cui `motivo` ha un turno "non trovo posto (non dimostrato)" ha un campo `provati` **specifico** per quel turno: gli schemi del passo 2a guardati, scambio lungo–tondo compreso; per le catene da 1, 2 e 3 spostamenti la prima e l'ultima U provata; l'esito dei giri 1 e 2 del passo 3 (skill `assegna-tavoli`, "Cosa scrivere quando non entra"). `provati` mancante, vuoto o generico ("nessuna catena", "provato tutto") | FAIL |

## Esito

Scrivi l'esito così (nella risposta solo se non è PASS, oppure se te lo chiedono):

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
