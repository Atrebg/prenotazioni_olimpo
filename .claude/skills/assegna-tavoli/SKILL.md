---
name: assegna-tavoli
description: Procedura base dell'Olimpo per mettere un gruppo di c persone in un turno — com'è il turno e i conteggi (passo 0), miglior incastro tra le unità libere con costo e spareggi (passo 1). Usala per ogni prenotazione da mettere o provare a mettere (nuova, sì, modifica, disponibilità, rigioca); se il passo 1 non basta, segue assegna-tavoli-difficile.
---

# Assegna tavoli: un gruppo di c persone nel turno T

Prima servono il catalogo (`agente/catalogo.md`), il file della serata (skill `stato-serata`; se non esiste la sala
è vuota) e le zone di `agente/regole.md`. Questa procedura **non scrive niente**: dà un esito, e chi la usa
(`prenotazione`, `rigioca`) scrive il file. Segui i passi in ordine e fermati al primo che riesce. Qui i passi 0 e 1;
i passi 2-4 sono in `assegna-tavoli-difficile` (solo Sonnet o superiore e `decisore-sala`):
"`assegna-tavoli` per intero" vuol dire tutte e due.

**Esito possibile**
- **ENTRA**: unità per il gruppo, più l'elenco dei cambi di tavolo di chi era già confermato (spesso vuoto).
- **PIENO (dimostrato)**: un conteggio del catalogo è superato; scrivi quale.
- **NON TROVO POSTO (non dimostrato)**: i passi 1, 2 e 3 sono stati **eseguiti per intero** senza trovare posto, e i
  conteggi non lo escludono. Scrivi che cosa hai provato (`assegna-tavoli-difficile`, "Cosa scrivere quando non entra").

> **"Le unità di adesso sono tutte occupate" non dimostra niente.** Il numero di unità di un turno cambia con le
> divisioni e le unioni (soglie del catalogo): una sala "piena" con le divisioni di adesso può avere posto con altre
> divisioni. Prima di dire "non trovo posto" i passi 2 e 3 si fanno davvero, senza scorciatoie.
>
> **Non riusare mai l'esito di un'altra prenotazione o di un messaggio precedente**, nemmeno se lo stato sembra
> uguale o il gruppo è della stessa taglia ("prima non entrava una coppia, quindi non entra neanche questa"): rifai
> tutti i passi sullo stato letto **adesso** dal file.

## Passo 0. Com'è il turno

1. Rileggi il file della serata e elenca le prenotazioni `confermata` con `turno` = T (se è una modifica, togli la
   prenotazione stessa), con la loro unità e i pezzi che usa (colonna "usa" del catalogo). Aggiungi le unità delle
   mosse `confermata` valide in T. Le `in_attesa` (proposte e domande) non occupano niente.
2. Un'unità è **libera** in T se nessuna confermata di T usa uno dei suoi pezzi. La seconda metà del lungo è libera
   solo se la prima è occupata.
3. **Limiti di taglia**: un gruppo di c persone va solo su un'unità con posti ≥ c (nessuna nel catalogo: PIENO,
   dimostrato). Un gruppo che sta in una metà del lungo non va sul lungo intero; uno più grande, sul lungo, va solo
   sull'intero.
4. **Conteggi**: aggiungi il nuovo gruppo alle confermate di T e controlla le soglie, il lungo a un gruppo e i posti
   massimi del catalogo. Se uno è superato, vai al passo 4: è PIENO dimostrato.

## Passo 1. Miglior incastro tra le unità libere

**Filtro di accessibilità (regola di buonsenso 1), solo se le note lo chiedono.** Carrozzina, anziano, difficoltà a
camminare: tieni solo le unità "vicino all'ingresso", se almeno una è libera e basta; altrimenti togli quelle "da
evitare". Seggiolone o passeggino: togli percorso dei camerieri e passaggio dei bagni, se resta altro. Le zone sono
in `agente/regole.md` (un blocco vale con i suoi pezzi).

**Candidate**: le unità libere con posti ≥ c che rispettano i limiti di taglia. Per ognuna calcola

> **costo = 10 × posti vuoti + 4 × tagli nuovi**

- **posti vuoti**: posti dell'unità − c; sul lungo intero e sulla prima metà, posti del lungo − c (è apparecchiato
  tutto per quel gruppo), sulla seconda metà posti di una metà − c.
- **tagli nuovi**: i tagli richiesti dall'unità (colonna del catalogo) che nel turno T nessuna unità assegnata
  sullo stesso blocco richiede già. Es.: blocco da 3 libero, un pezzo da 2 quadrati ha 1 taglio nuovo; se il
  quadrato che resta è già occupato, 0.

Scegli la candidata con il costo più basso. **A parità**, applica gli spareggi nell'ordine; ognuno tiene le
candidate che lo soddisfano e, se nessuna lo soddisfa, le tiene tutte:
1. **senza unione**: preferisci un'unità che non sia un'unione;
2. **riserva**: preferisci un'unità che non usa tavoli di un'**unione ancora libera** e non è un blocco separabile
   intero: tiene aperte le possibilità per i gruppi dopo. Un'unione è "ancora libera" se **tutti e due** i
   suoi tavoli sono liberi; un'unione non conta sé stessa. Esempio: una coppia, 3 e 4 occupati, 25-29 liberi, 20
   occupato da un gruppo da 4: l'unione 20+25 non è più libera, quindi 25 passa lo spareggio; 26-29 no (21-24 sono
   liberi) → **25**;
3. **buonsenso** (zone in `agente/regole.md`): feste e gruppi da 8 in su prima "in fondo o in un angolo", poi
   "saletta", poi "lato destro"; coppie "contro una parete"; nota "tavolo tranquillo" come una festa;
4. **ordine del catalogo**: la prima riga vince.

Se c'è almeno una candidata: ENTRA, senza cambi. Altrimenti passo 2.

**Modalità mista**: Haiku qui si ferma. ENTRA al passo 1 → scrive; qualsiasi altro esito (conteggio superato al
passo 0, nessuna candidata) → lo script `motore/decidi.py`; un dubbio → `decisore-sala` (vedi `CLAUDE.md`).

Il costo copre la regola di buonsenso 2 (posti vuoti) e la 3 (poche divisioni). Non serve a decidere se entrare: si
entra sempre se c'è un'unità libera adatta.
