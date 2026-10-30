---
name: assegna-tavoli-difficile
description: Seguito di assegna-tavoli quando il passo 1 non trova posto o un conteggio è superato — ritocchi, catene, riassegnazione del turno, pieno o non trovo posto, cosa scrivere (cambi, proposte, rifiuti, provati), esempi. Solo Sonnet o superiore, decisore-sala e rigioca; Haiku no.
---

# Assegna tavoli, casi difficili: passi 2-4

Continua `assegna-tavoli` (passi 0 e 1, costo e spareggi): qui si arriva se il passo 1 non trova niente (passo 2) o
il passo 0 trova un conteggio superato (passo 4).

## Passo 2. Ritocchi: spostare chi è già confermato (stesso turno)

Solo se il passo 1 non ha trovato niente. Cambia il tavolo, **mai il turno**. Se la serata è quella di oggi, non
spostare nessuno senza chiederlo al proprietario (non sai che ora è).

**"Libera" durante un ritocco.** Togli dalle loro unità tutte le prenotazioni che stai spostando: i loro pezzi
diventano liberi. Un'unità è libera se nessun'altra prenotazione usa i suoi pezzi **e** se non usa pezzi già dati
nel ritocco (al nuovo gruppo o a un altro spostato). Quindi i pezzi lasciati da chi si sposta contano come liberi,
tranne quelli già dati (es. se Gentile lascia 5ab e il nuovo gruppo prende 5a, 5b è libero per un altro).

### 2a. Schemi fissi: dividi chi siede largo, scambio con il lungo

Si provano tutti, prima della catena generica. Le righe concrete sono nel catalogo.

**Dividi chi siede largo (1 cambio, stesso tavolo).** Un'unità di più pezzi è occupata da un gruppo che entra in una
sua parte: il gruppo va lì e il resto si libera. Le parti:
- blocco separabile intero: un pezzo più corto che parte dal quadrato a;
- pezzo di blocco: un pezzo più corto che tocca il bordo del blocco;
- unione A+B: uno dei due tavoli (se hanno gli stessi posti, A);
- lungo intero: la prima metà.

**Scambio con il lungo (2 cambi).** Si applica quando il lungo intero è occupato da un solo gruppo G più grande di
una metà, G entra in un'altra unità U di un pezzo solo, e U è occupata da un gruppo H che sta in una metà. Allora G
va su U, H va sulla prima metà e **la seconda metà resta libera** per il nuovo gruppo, se ci entra.

Candidate: gli schemi in cui la parte che si libera ha posti ≥ c (e rispetta i limiti di taglia). Tra le candidate,
prima quelle con meno cambi, poi il costo e gli spareggi del passo 1 calcolati sulla parte che si libera. Ogni cambio
si registra come `cambio tavolo`, con motivo "stesso tavolo, diviso per far posto a …" o "scambio con il lungo per
far posto a …".

### 2b. Catena di spostamenti (fino a 3 spostamenti)

Una **catena**: il nuovo gruppo va su U; chi occupava U (P) va su V; chi occupava V (Q) va su W; chi occupava W (R)
va su X. Ognuno deve entrare nella sua unità (posti ≥ coperti, limiti di taglia) e U, V, W, X non usano pezzi in
comune. La catena **riesce** quando l'ultimo spostato trova un'unità libera (definizione sopra). Se un'unità della
catena ha due occupanti, si spostano tutti e due e contano due spostamenti.

**Ricerca esaustiva, per numero di spostamenti** (U in ordine di costo per il nuovo gruppo, calcolato come se U
fosse libera, con gli spareggi del passo 1; V in ordine di costo per P; W in ordine di costo per Q):
1. **Uno**: per ogni U: c'è un'unità libera per P?
2. **Due**: per ogni U, per ogni V adatta a P con un solo occupante Q: c'è un'unità libera per Q?
3. **Tre**: per ogni U, V, e ogni W adatta a Q con un solo occupante R: c'è un'unità libera per R? (Oppure U o V
   con due occupanti.)

Fai prima **tutte** le catene da uno, poi da due, poi da tre; fermati alla prima che riesce.

**A sala piena (nessun pezzo libero nel turno): dove può esserci una catena.** L'ultimo spostato può andare solo su
pezzi avanzati da chi si è spostato. Ne avanzano solo se almeno uno spostato passa da un'unità di **più pezzi**
(colonna "usa" del catalogo) a un'unità con **meno pezzi** (per esempio da 5ab al 10, da 7 a 7a). È una regola
esatta, non una scorciatoia: una catena senza un passaggio così non può riuscire e si scarta. In pratica:
1. elenca le unità di più pezzi occupate e chi ci siede ("chi può stringersi");
2. per ognuno, le unità con meno pezzi in cui entra (occupate o no);
3. costruisci le catene che contengono uno di questi passaggi, con l'ordine di ricerca di sopra.

Se riesce: ENTRA, con l'elenco dei cambi (es. "Gentile ×5: da 5ab a 10, per far posto a Bianco ×3").

## Passo 3. Riassegnazione completa del turno

Si fa davvero, anche se il passo 2 è fallito: le unità di adesso non contano.

1. Lista: tutte le confermate di T più il nuovo gruppo, in ordine di **coperti decrescenti** (a parità, `n`
   crescente; il nuovo gruppo è l'ultimo tra i pari).
2. **Giro 1, tenendo i tavoli.** Parti dal turno vuoto (restano solo le mosse confermate). Per ognuno nell'ordine:
   se è una confermata e la sua unità di prima è ancora libera, rimettilo lì; altrimenti miglior incastro (passo 1)
   tra le unità ancora libere.
3. **Giro 2, da capo.** Se il giro 1 lascia qualcuno senza posto: rifai tutto dal turno vuoto, ognuno al miglior
   incastro, senza tenere le unità di prima.
4. Un giro riesce solo se **tutti** hanno un posto: una confermata non si lascia mai fuori. Se riesce: ENTRA, e i
   cambi sono le confermate che hanno un'unità diversa da prima. Se riescono tutti e due, usa quello con meno cambi.
5. Se nessun giro riesce: passo 4.

## Passo 4. Non entra: è dimostrato?

Con le confermate di T più il nuovo gruppo, rifai i conteggi del catalogo.

- Un conteggio superato → **PIENO (dimostrato)**. Scrivi il motivo con i numeri, per esempio "dimostrato: 2 gruppi
  da 11 in su, c'è un solo lungo" oppure "dimostrato: 36 prenotazioni da 1 in su, al massimo 35 con il lungo a un
  gruppo solo".
- Nessun conteggio superato → **NON TROVO POSTO (non dimostrato)**, solo se i passi 1-3 sono stati eseguiti per
  intero. Non dire "pieno": di' "non trovo posto".

## Cosa scrivere quando non entra

Per i messaggi veri (la rigioca ha le sue regole).

**Entra con cambi** (passi 2-3): prima aggiorna la riga di ogni prenotazione spostata (`unita`) e aggiungi al
registro una riga `cambio tavolo` per ognuna ("per far posto a Rossi ×4"); poi la riga e il registro dell'esito
(`confermata`, `accettata su proposta`, `modifica`). Nella risposta: "Ho cambiato tavolo a 1 prenotazione già
confermata dello stesso turno (lo vedi nel riepilogo)."

**Non entra nel turno chiesto T:**
- **nuova**, o risposta a una domanda (si aggiorna la sua riga, stesso `n`): procedura completa nell'altro turno T',
  senza scrivere i tavoli. Entra in T' → **proposta** di T' (registro `proposta`, con `provati` se T non è
  dimostrato): "Il primo turno è pieno. Posso nel secondo, alle 21:30. Va bene?" (non dimostrato: "Nel primo turno
  non trovo posto. Posso …"). Non entra neanche in T' → skill `mossa-tavoli`: se trova una mossa, la prenotazione è
  `in_attesa` con la sua proposta; altrimenti `rifiutata` con il motivo dei due turni, registro `rifiutata` con
  `provati`: "Il primo turno è pieno, e anche il secondo." ("non trovo posto" per un turno non dimostrato).
- **orario fuori dai turni** (prima delle 19:15, dopo le 22:15): si propone il turno più vicino; se il più vicino non
  ha posto e l'altro sì, proponi l'altro.
- **sì a una proposta** che non entra più: se adesso c'è posto nel turno chiesto all'inizio, proponilo (resta
  `in_attesa`, nuova `proposta`, registro `proposta`); altrimenti `rifiutata` ("nel frattempo si è riempito anche il
  secondo turno").
- **modifica** che non entra (anche verso un'altra serata): **non cambia niente**, resta la versione di prima: "Nel
  secondo turno non c'è posto per 6: resta la prenotazione di prima (4 persone, primo turno)." Se nell'altro turno
  c'è posto, dillo e chiedi se la sposti lì (senza scrivere).

Se un turno è "non trovo posto", non scrivere frasi come "non ho rifatto le catene" o "ho riusato il risultato di
prima": vuol dire che la procedura non è finita. Finiscila, poi rispondi.

**`provati`.** Nella riga di registro `proposta` o `rifiutata`, il campo `provati` dice **in modo specifico** che cosa
hai provato per ogni turno non dimostrato. Deve contenere, per quel turno:
1. **2a**: ogni schema del catalogo che hai guardato, con il motivo per cui non va, e lo **scambio con il lungo**
   (applicabile o no, e perché);
2. **catene**: per le catene da 1, da 2 e da 3 spostamenti, la prima e l'ultima U provata e quante U, più "chi può
   stringersi" se la sala è piena;
3. **passo 3**: esito del giro 1 e del giro 2, con chi è rimasto senza posto.

Esempio: `"provati": "primo: 2a 7 (Mazza ×5 > 4) no, 5ab/8ab non occupati, 13A+13B e unioni non usate, 11 (Ricci ×18)
no, scambio con il lungo no (11 da 11 in su); stringersi: Mazza ×5 (7), Ricci ×18 (11, no); catene da 1: U da 3 a
24+29, 31 U, nessuna; da 2: U da 3 a 24+29, 31 U, nessuna; da 3: U da 3 a 24+29, 31 U, nessuna; passo 3: giro 1 fuori
Neri ×4, giro 2 fuori Gallo ×2"`. Un `provati` vuoto o generico ("nessuna catena", "provato tutto") **non basta**:
il controllo C15 lo segna FAIL. Il formato del `motivo` è nella skill `stato-serata`.

## Esempi svolti sulla piantina del 29/10/2026

Con un'altra piantina valgono come metodo.

**A. Un gruppo da 6, primo turno; 9, 12 e 7 sono già occupati.** Candidate libere con almeno 6 posti e costo:
20+25 … 24+29 → 0 (unioni); 5ab, 5bc, 8ab, 8bc → 0 posti vuoti + 1 taglio nuovo = 4; 5, 8, 13A+13B → 2 posti vuoti =
20; 10 → 40; 11-1 → 14 posti vuoti = 140. Costo più basso: le cinque unioni, tutte pari; spareggi 1-3 non
decidono; ordine del catalogo → **20+25** ("unisci 25 al 20"). Se 25-29 fossero già occupati da coppie, nessuna
unione sarebbe libera: costo 4 per 5ab, 5bc, 8ab, 8bc → ordine del catalogo → **5ab** (5 si divide: 5ab da 6 e 5c
da 4, libero).

**B. Gruppi da 8, secondo turno vuoto, uno dopo l'altro.** Primo: 5 e 8 costano 0, 13A+13B 0 ma è un'unione
(spareggio 1), 10 costa 20, 11-1 costa 120. Restano 5 e 8 (lo spareggio 2 non toglie niente, sono tutti e due
blocchi interi); spareggio 3, gruppo da 8 = tavolata: 8 è "lato destro", 5 "vicino all'ingresso" → **8**. Secondo:
**5**. Terzo: **13A+13B** (0). Quarto: **10** (20). Quinto: **11-1** (120). Sesto: **11-2** (0). Settimo: già al
passo 0 il conteggio "da 7 in su" vale 7 > 6 → **PIENO (dimostrato)**, senza cercare oltre.

**C. Un gruppo da 14 nel primo turno, il lungo è di Ricci ×18.** Da 11 in su solo "11", occupato. Già al passo 0 il
conteggio "da 11 in su" vale 2 > 1 → **PIENO (dimostrato)**: si propone il secondo turno (skill `prenotazione`).

**D. Uno spostamento.** Secondo turno: Costa ×10; il 10 è di Verdi ×7, l'11 è di Ferrara ×14, 13A+13B è libero.
Nessuna unità da 10 libera; 2a non si applica (il 10 non si divide). Catena da uno: U = 10, P = Verdi ×7, unità
libera per Verdi: 13A+13B (1 posto vuoto) → **Verdi ×7 da 10 a 13A+13B, Costa ×10 al 10**.

**E. Una catena da due a sala piena (sabato di prova, Bianco ×3 nel primo turno, n55).** Il primo turno ha 33
confermate e nessun pezzo libero: 5 diviso in 5ab (Gentile ×5) e 5c (Valentini ×3), 8 in 8a, 8b, 8c, 7 intero (Mazza
×5), 10 di Esposito ×3, 11 di Ricci ×18, tutti gli altri tavoli occupati.
- Passo 0: 34 prenotazioni ≤ 35 (lungo a un gruppo solo), 18 da 3 in su ≤ 28, 119 coperti ≤ 151: niente è dimostrato.
- Passo 1: nessuna unità libera. Passo 2a: 7 e 5ab hanno occupanti da 5 (più di 4), 11 da 18; scambio con il lungo
  no (l'11 ha un gruppo da 11 in su): nessuno schema.
- Passo 2b, sala piena. Chi può stringersi: Mazza ×5 (7 → 9, 12, 10), Gentile ×5 (5ab → 9, 12, 10); Ricci ×18 no.
- Catene da uno: con U = 5a o 5b avanza l'altro quadrato (4 posti), troppo poco per Gentile ×5; con U = 7a o 7b
  avanza un quadrato da 4, troppo poco per Mazza ×5. Nessuna.
- Catene da due, U in ordine di costo per 3 persone: 6 (0), poi le unità da 4 senza tagli nuovi (10). Il loro
  occupante P siede su un pezzo solo, quindi perché avanzi qualcosa dovrebbe andare su un pezzo di 7, di 5ab o del
  lungo, e chi lo occupava (Mazza, Gentile, Ricci) non entra in ciò che avanza: nessuna. Poi U = **5a** (4 posti,
  1 taglio nuovo: 14). P = Gentile ×5, V in ordine: 9 (Morelli ×5, che non entra in 5b), 12 (Marino ×5, idem), 7
  (Mazza ×5, idem), unioni e 13A+13B (due occupanti: catene da tre), 10 (Esposito ×3): Esposito entra in **5b**,
  avanzato da Gentile. **Riesce.**
- Esito: **Bianco ×3 su 5a; Gentile ×5 da 5ab a 10; Esposito ×3 da 10 a 5b** (2 cambi). Il blocco 5 diventa 5a + 5b +
  5c. È la disposizione trovata da un controllo esatto (CP-SAT), con 5a e 5b scambiati.

**F. Lo scambio con il lungo (sabato pieno, dopo "annulla Ricci sab" e "Ferretti 10 sab 20:00"; poi Bassi ×2).**
Primo turno: 34 confermate e nessun pezzo libero; Ferretti ×10 è sull'"11" (era libero dopo l'annullamento di
Ricci), Gentile ×5 sul "10", 5 diviso in 5a, 5b, 5c, 8 in 8a, 8b, 8c, 7 intero (Mazza ×5). Arriva "Bassi 2 sab 19:00":
le 19:00 sono fuori dai turni, quindi si prova il più vicino, il primo, per proporlo.
- Passo 0: 35 prenotazioni ≤ 36 (un solo gruppo da 9 in su e nessuno da 11: il lungo non è obbligato a un gruppo
  solo), 113 coperti ≤ 151: niente è dimostrato.
- Passo 1: nessuna unità libera.
- Passo 2a: 7 (Mazza ×5, più di 4) no; 11 con un gruppo da 10 (più di 8) no per la riga "11"; **scambio con il lungo**:
  "11" ha un gruppo da 10 e "10" un gruppo da 5 → si applica. Ferretti ×10 dall'"11" al "10", Gentile ×5 dal "10" a
  "11-1", **"11-2" libero** (8 posti) → Bassi ×2 su 11-2 (6 posti vuoti).
- Esito: c'è posto nel primo turno (2 cambi), quindi si propone il primo turno ("Alle 19:00 non c'è un turno. Il
  più vicino è il primo, alle 20:00. Va bene?"). Al "sì" si rifà la procedura sullo stato del file e si scrivono i due
  `cambio tavolo` e `accettata su proposta`. Senza questo schema la sessione aveva detto "né il primo né il secondo
  hanno posto": un falso pieno.
