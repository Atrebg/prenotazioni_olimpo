---
name: assegna-tavoli
description: Procedura centrale dell'Olimpo per decidere se un gruppo di c persone entra in un turno e a quale tavolo (unità) siede — miglior incastro, ritocchi (dividere chi siede largo, catene di spostamenti fino a 3), riassegnazione del turno, "turno pieno" dimostrato con i conteggi oppure "non trovo posto". Usala ogni volta che devi mettere, spostare o provare a mettere una prenotazione (nuova, sì a una proposta, modifica, disponibilità, rigioca).
---

# Assegna tavoli: un gruppo di c persone nel turno T

Prima servono il catalogo (skill `sala`), il file della serata (skill `stato-serata`; se non esiste la sala è vuota)
e le zone di `agente/regole.md`. Questa procedura **non scrive niente**: dà un esito, e chi la usa (`prenotazione`,
`rigioca`) scrive il file. Segui i passi in ordine e fermati al primo che riesce.

**Esito possibile**
- **ENTRA**: unità per il gruppo, più l'elenco dei cambi di tavolo di chi era già confermato (spesso vuoto).
- **PIENO (dimostrato)**: un conteggio della skill `sala` è superato; scrivi quale.
- **NON TROVO POSTO (non dimostrato)**: i passi 1, 2 e 3 sono stati **eseguiti per intero** senza trovare posto, e i
  conteggi non lo escludono. Scrivi che cosa hai provato (vedi "Cosa scrivere").

> **"Le unità di adesso sono tutte occupate" non dimostra niente.** Il numero di unità di un turno cambia con le
> divisioni e le unioni (fino a 36, 29 da 3 posti in su, 28 da 4 in su…): una sala "piena" con le divisioni di adesso
> può avere posto con altre divisioni. Prima di dire "non trovo posto" i passi 2 e 3 si fanno davvero, senza
> scorciatoie.
>
> **Non riusare mai l'esito di un'altra prenotazione o di un messaggio precedente**, nemmeno se lo stato sembra
> uguale o il gruppo è della stessa taglia ("prima non entrava una coppia, quindi non entra neanche questa"): rifai
> tutti i passi sullo stato letto **adesso** dal file.

## Passo 0. Com'è il turno

1. Rileggi il file della serata e elenca le prenotazioni `confermata` con `turno` = T (se è una modifica, togli la
   prenotazione stessa), con la loro unità e i pezzi che usa (colonna "usa" del catalogo). Aggiungi le unità delle
   mosse `confermata` valide in T. Le `in_attesa` (proposte e domande) non occupano niente.
2. Un'unità è **libera** in T se nessuna confermata di T usa uno dei suoi pezzi. "11-2" è libera solo se "11-1" è
   occupata.
3. **Limiti di taglia**: da 21 in su non entra mai (PIENO, dimostrato); da 11 a 20 solo "11"; 9 o 10 solo "10" o
   "11"; fino a 8 mai "11" (si usano "11-1" e "11-2").
4. **Conteggi**: aggiungi il nuovo gruppo alle confermate di T e controlla i conteggi per soglia e i 151 posti
   (skill `sala`, punto 6, compresa la regola del lungo con un gruppo da 9 in su). Se uno è superato, vai al passo 4:
   è PIENO dimostrato.

## Passo 1. Miglior incastro tra le unità libere

**Filtro di accessibilità (regola di buonsenso 1), solo se le note lo chiedono.** Carrozzina, anziano, difficoltà a
camminare: tieni solo le unità "vicino all'ingresso" (1, 2, 5 e i suoi pezzi, 3), se almeno una è libera e basta;
altrimenti togli quelle "da evitare". Seggiolone o passeggino: togli percorso dei camerieri (3, 4, 13A) e passaggio
dei bagni (15-19), se resta altro. Le zone sono in `agente/regole.md`.

**Candidate**: le unità libere con posti ≥ c che rispettano i limiti di taglia. Per ognuna calcola

> **costo = 10 × posti vuoti + 4 × tagli nuovi**

- **posti vuoti**: posti dell'unità − c; per il lungo vedi la skill `sala`, punto 5 ("11" e "11-1": 20 − c; "11-2": 8 − c).
- **tagli nuovi**: i tagli richiesti dall'unità (colonna del catalogo) che nel turno T nessuna unità assegnata
  sullo stesso blocco richiede già. Es.: 5 libero e intatto, "5ab" ha 1 taglio nuovo (b|c); se "5c" è già occupato,
  "5ab" ha 0 tagli nuovi.

Scegli la candidata con il costo più basso. **A parità**, applica gli spareggi nell'ordine; ognuno tiene le
candidate che lo soddisfano e, se nessuna lo soddisfa, le tiene tutte:
1. **senza unione**: preferisci un'unità che non sia un'unione ("20+25", "13A+13B");
2. **riserva**: preferisci un'unità che non usa tavoli di un'**unione ancora libera** e non è un blocco separabile
   intero (5, 7, 8): tiene aperte le possibilità per i gruppi dopo. Un'unione è "ancora libera" se **tutti e due** i
   suoi tavoli sono liberi; un'unione non conta sé stessa. Esempio: una coppia, 3 e 4 occupati, 25-29 liberi, 20
   occupato da un gruppo da 4: l'unione 20+25 non è più libera, quindi 25 passa lo spareggio; 26-29 no (21-24 sono
   liberi) → **25**;
3. **buonsenso** (zone in `agente/regole.md`): feste e gruppi da 8 in su prima "in fondo o in un angolo", poi
   "saletta", poi "lato destro"; coppie "contro una parete"; nota "tavolo tranquillo" come una festa;
4. **ordine del catalogo** (skill `sala`, punto 4): la prima riga vince.

Se c'è almeno una candidata: ENTRA, senza cambi. Altrimenti passo 2.

**Modalità mista**: se la sessione gira su Haiku, qui si ferma. ENTRA al passo 1 → Haiku scrive; qualsiasi altro
esito (conteggio superato al passo 0, nessuna candidata, dubbio) → passa all'agente `decisore-sala` (vedi
`CLAUDE.md`). I passi 2-4 li esegue solo Sonnet.

Il costo copre la regola di buonsenso 2 (posti vuoti) e la 3 (poche divisioni). Non serve a decidere se entrare: si
entra sempre se c'è un'unità libera adatta.

## Passo 2. Ritocchi: spostare chi è già confermato (stesso turno)

Solo se il passo 1 non ha trovato niente. Cambia il tavolo, **mai il turno**. Se la serata è quella di oggi, non
spostare nessuno senza chiederlo al proprietario (non sai che ora è).

**"Libera" durante un ritocco.** Togli dalle loro unità tutte le prenotazioni che stai spostando: i loro pezzi
diventano liberi. Un'unità è libera se nessun'altra prenotazione usa i suoi pezzi **e** se non usa pezzi già dati
nel ritocco (al nuovo gruppo o a un altro spostato). Quindi i pezzi lasciati da chi si sposta contano come liberi,
tranne quelli già dati: se Gentile lascia 5ab e il nuovo gruppo prende 5a, 5b è libero per un altro.

### 2a. Schemi fissi: dividi chi siede largo, scambio lungo–tondo

Si provano tutti, prima della catena generica. Le divisioni costano 1 cambio (stesso tavolo).

| unità occupata | se l'occupante ha | l'occupante va su | si libera |
|---|---|---|---|
| 7 | fino a 4 | 7a | 7b (4) |
| 5 (o 8) | fino a 6 | 5ab | 5c (4) |
| 5 (o 8) | fino a 4 | 5a | 5bc (6), oppure 5b e 5c (4 + 4) |
| 5ab (o 8ab) | fino a 4 | 5a | 5b (4) |
| 5bc (o 8bc) | fino a 4 | 5c | 5b (4) |
| 13A+13B | fino a 4 | 13A | 13B (4) |
| 20+25 (… 24+29) | fino a 4 | 20 | 25 (2) |
| 20+25 (… 24+29) | fino a 2 | 25 | 20 (4) |
| 11 | fino a 8 | 11-1 | 11-2 (8) |

**Scambio lungo–tondo (2 cambi).** Si applica solo quando **tutte e due** le condizioni sono vere: "11" è occupato
da **un** gruppo da 9 o 10, e "10" è occupato da un gruppo **fino a 8**. Allora il gruppo da 9-10 va al "10", quello
fino a 8 va su "11-1", e **"11-2" resta libero (8 posti)** per il nuovo gruppo, se ne ha fino a 8.
Non si applica (nessuno scambio utile) se:
- "11" ha un gruppo da 11 in su (può stare solo lì) oppure fino a 8 (allora vale la riga "11" della tabella);
- "10" ha un gruppo da 9-10 (tutti e due i gruppi grandi hanno bisogno del loro tavolo);
- "10" è libero (il passo 1 l'avrebbe già usato);
- il lungo è già diviso in "11-1" e "11-2" con due gruppi fino a 8: spostare il gruppo del "10" sul lungo non libera
  niente.

Candidate: gli schemi in cui la parte che si libera ha posti ≥ c (e rispetta i limiti di taglia). Tra le candidate,
prima quelle con meno cambi, poi il costo e gli spareggi del passo 1 calcolati sulla parte che si libera. Ogni cambio
si registra come `cambio tavolo`, con motivo "stesso tavolo, diviso per far posto a …" o "scambio lungo–tondo per
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
(5, 5ab, 5bc, 7, 8, 8ab, 8bc, 13A+13B, 20+25 … 24+29, 11) a un'unità con **meno pezzi** (per esempio da 5ab al 10,
da 7 a 7a). È una regola esatta, non una scorciatoia: una catena senza un passaggio così non può riuscire e si scarta.
In pratica:
1. elenca le unità di più pezzi occupate e chi ci siede ("chi può stringersi");
2. per ognuno, le unità con meno pezzi in cui entra (occupate o no);
3. costruisci le catene che contengono uno di questi passaggi, con l'ordine di ricerca di sopra.

Se riesce: ENTRA, con l'elenco dei cambi ("Gentile ×5: da 5ab a 10, per far posto a Bianco ×3").

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

Con le confermate di T più il nuovo gruppo, rifai i conteggi della skill `sala` (punto 6).

- Un conteggio superato → **PIENO (dimostrato)**. Scrivi il motivo con i numeri, per esempio "dimostrato: 2 gruppi
  da 11 in su, c'è un solo lungo" oppure "dimostrato: 36 prenotazioni da 1 in su, al massimo 35 con il lungo a un
  gruppo solo".
- Nessun conteggio superato → **NON TROVO POSTO (non dimostrato)**, solo se i passi 1-3 sono stati eseguiti per
  intero. Non dire "pieno": di' "non trovo posto".

## Cosa scrivere quando non entra

Nel registro, nella riga `proposta` o `rifiutata`, il campo `provati` dice **in modo specifico** che cosa hai
provato per ogni turno non dimostrato. Deve contenere, per quel turno:
1. **2a**: ogni schema della tabella che hai guardato, con il motivo per cui non va, e lo **scambio lungo–tondo**
   (applicabile o no, e perché);
2. **catene**: per le catene da 1, da 2 e da 3 spostamenti, la prima e l'ultima U provata e quante U, più "chi può
   stringersi" se la sala è piena;
3. **passo 3**: esito del giro 1 e del giro 2, con chi è rimasto senza posto.

Esempio: `"provati": "primo: 2a 7 (Mazza ×5 > 4) no, 5ab/8ab non occupati, 13A+13B e unioni non usate, 11 (Ricci ×18)
no, scambio lungo–tondo no (11 da 11 in su); stringersi: Mazza ×5 (7), Ricci ×18 (11, no); catene da 1: U da 3 a
24+29, 31 U, nessuna; da 2: U da 3 a 24+29, 31 U, nessuna; da 3: U da 3 a 24+29, 31 U, nessuna; passo 3: giro 1 fuori
Neri ×4, giro 2 fuori Gallo ×2"`. Un `provati` vuoto o generico ("nessuna catena", "provato tutto") **non basta**:
il controllo C15 lo segna FAIL. Il formato del `motivo` è nella skill `stato-serata`.

## Esempi svolti sulla sala vera (catalogo del 29/10/2026)

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
- Passo 1: nessuna unità libera. Passo 2a: 7 e 5ab hanno occupanti da 5 (più di 4), 11 da 18; scambio lungo–tondo
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

**F. Lo scambio lungo–tondo (sabato pieno, dopo "annulla Ricci sab" e "Ferretti 10 sab 20:00"; poi Bassi ×2).**
Primo turno: 34 confermate e nessun pezzo libero; Ferretti ×10 è sull'"11" (era libero dopo l'annullamento di
Ricci), Gentile ×5 sul "10", 5 diviso in 5a, 5b, 5c, 8 in 8a, 8b, 8c, 7 intero (Mazza ×5). Arriva "Bassi 2 sab 19:00":
le 19:00 sono fuori dai turni, quindi si prova il più vicino, il primo, per proporlo.
- Passo 0: 35 prenotazioni ≤ 36 (un solo gruppo da 9 in su e nessuno da 11: il lungo non è obbligato a un gruppo
  solo), 113 coperti ≤ 151: niente è dimostrato.
- Passo 1: nessuna unità libera.
- Passo 2a: 7 (Mazza ×5, più di 4) no; 11 con un gruppo da 10 (più di 8) no per la riga "11"; **scambio lungo–tondo**:
  "11" ha un gruppo da 10 e "10" un gruppo da 5 → si applica. Ferretti ×10 dall'"11" al "10", Gentile ×5 dal "10" a
  "11-1", **"11-2" libero** (8 posti) → Bassi ×2 su 11-2 (6 posti vuoti).
- Esito: c'è posto nel primo turno (2 cambi), quindi si propone il primo turno ("Alle 19:00 non c'è un turno. Il
  più vicino è il primo, alle 20:00. Va bene?"). Al "sì" si rifà la procedura sullo stato del file e si scrivono i due
  `cambio tavolo` e `accettata su proposta`. Senza questo schema la sessione aveva detto "né il primo né il secondo
  hanno posto": un falso pieno.
