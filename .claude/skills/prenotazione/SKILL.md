---
name: prenotazione
description: Messaggi che cambiano le prenotazioni dell'Olimpo — nuova ("Rossi 4 sab 20:30" o testo libero), risposte brevi a cose in sospeso ("sì", "no grazie", "primo", "è un'altra"), modifica, annullamento — con data, turno, domande salvate e scrittura. Usala per ogni messaggio che registra, cambia o annulla una prenotazione o risponde a qualcosa in sospeso.
---

# Prenotazioni: nuova, risposte, modifica, annullamento

Servono: catalogo (`agente/catalogo.md`), formato del file (skill `stato-serata`), procedura dei tavoli (skill
`assegna-tavoli`), regole (`agente/regole.md`).

**Modalità mista** (Haiku) e regole di metodo (non riusare esiti di prima, controllo dopo ogni scrittura): come dice
`CLAUDE.md`. Ogni riga di registro porta `deciso_da`.

## 1. Capire il messaggio

Formato compatto (resta valido):
- `Rossi 4 sab 20:30 [note]`, `Rossi 4 31/10 20:30 seggiolone` → nuova;
- `Rossi 4 sab 1t`, `Rossi 4 sab 2t`, `Rossi 4 sab secondo turno` → nuova con il turno detto;
- `annulla Rossi sab` → annullamento;
- `riepilogo sab` → skill `riepilogo`.

Testo libero ("mi ha chiamato la signora Rossi, sabato vengono in 4 verso le otto e mezza, c'è un bambino"): ricava
nome, coperti, data, orario o turno, note. **Non aggiungere niente che il messaggio non dice.** Tipo di messaggio:
- nuova prenotazione;
- **risposta breve** a qualcosa in sospeso ("sì", "ok", "va bene", "no", "no grazie", "2t", "il secondo", "primo",
  "è un'altra", "la stessa", "sono in 5") → punto 5;
- modifica ("Rossi diventano 6", "sposta Rossi alle 21:30", "Rossi viene domenica");
- annullamento ("annulla", "disdice", "non vengono più");
- domanda senza registrare ("c'è posto…?") → skill `disponibilita`; riepilogo → skill `riepilogo`.

**Quando devi fare una domanda** (dato mancante, prenotazione ambigua, 20:45 senza turno, nome già presente): una
domanda sola, su quello che manca.
- Se conosci **nome e data**, salva la richiesta nel file della serata come prenotazione `in_attesa`, senza tavolo,
  con `domanda` = il testo della domanda, `motivo` = "aspetta la risposta alla domanda", i dati che hai (quelli che
  mancano a `null`) e una riga di registro `domanda`. Così una sessione nuova può riprenderla.
- Se manca il nome o la data, non scrivere niente: chiedi e basta.

## 2. La data

- Oggi è la data del contesto della sessione (o quella che ti passa chi ti chiama). Se non la conosci, chiedila.
- Giorni della settimana: contali da un giorno noto, **sabato 31/10/2026** (7 giorni dopo è di nuovo sabato).
- "stasera", "oggi" = oggi; "domani" = oggi + 1; "dopodomani" = oggi + 2.
- Un giorno della settimana ("sab", "sabato", "ven") = il primo giorno con quel nome da domani in avanti. Se oggi è
  proprio quel giorno, chiedi: "Stasera o sabato prossimo?".
- "31/10" senza anno = quest'anno; se è già passata, chiedi.
- Data passata: non si registra. Giorno e data che non coincidono ("sab 30/10", ma il 30/10 è venerdì): chiedi.
- Se la data può voler dire due giorni diversi, chiedi.

## 3. Orario e turno

- Turno detto esplicitamente: "1t", "primo turno", "alle 20" → primo; "2t", "secondo turno", "alle 21:30" → secondo.
- "alle 8" = 20:00, "alle 9" = 21:00, "alle 9 e mezza" = 21:30: è una cena.
- Orario dalle 19:15 alle 20:44 → primo turno; dalle 20:46 alle 22:15 → secondo turno.
- **20:45 senza turno detto**: chiedi "Primo turno (20:00) o secondo (21:30)?" e salva la domanda (punto 1).
  Eccezione: nelle prove della skill `rigioca` non si fanno domande e le 20:45 vanno nel primo turno.
- **Prima delle 19:15 o dopo le 22:15**: non si registra. `turno_chiesto` = `null`; si propone il turno più vicino
  (prima delle 19:15 il primo, dopo le 22:15 il secondo; proposta come in `stato-serata`): "Alle 19:00 non c'è un
  turno. Il più vicino è il primo, alle 20:00. Va bene?". Se non ha posto: `assegna-tavoli-difficile`, "Cosa
  scrivere quando non entra".

## 4. Nuova prenotazione

1. Il file della serata e la versione della piantina li hai già letti all'inizio (`CLAUDE.md`).
2. **Stesso nome** già presente nella serata (`confermata` o `in_attesa`): chiedi "C'è già Rossi alle 20:30 per 4
   persone (sab 31/10): è un'altra prenotazione o la modifico?" e salva la richiesta come domanda (punto 1).
3. `n` = il più alto della serata + 1.
4. `assegna-tavoli` per c = coperti nel turno chiesto T.
   - **ENTRA** → scrivi la prenotazione `confermata` con la sua `unita` (con cambi di tavolo: skill
     `assegna-tavoli-difficile`, "Cosa scrivere quando non entra").
   - **Non entra in T** → skill `assegna-tavoli-difficile`, "Cosa scrivere quando non entra" (altro turno, mossa,
     rifiuto).
5. Skill `controllo-serata` per intero (C1-C15), poi rispondi.

## 5. Risposte brevi: proposte e domande in sospeso

1. **A che cosa risponde**: come in `CLAUDE.md` ("Per ogni messaggio", punto 2). Se chiedi a quale, elencale in breve
   ("Ferrara ×14 sab 31/10 (secondo turno?) o Pellegrino ×4 sab 31/10 (primo o secondo turno?)"); se la risposta non
   c'entra con quella trovata (es. "2t" a "è un'altra prenotazione?"), chiedi.
2. **Sì a una proposta** ("sì", "ok", "va bene", oppure il turno proposto): rifai `assegna-tavoli` nel turno
   proposto, perché nel frattempo la sala può essere cambiata.
   - ENTRA → la riga diventa `confermata`, `turno` = turno proposto, `unita`, `motivo` `null` (la `proposta` resta);
     registro: eventuali `cambio tavolo`, poi `accettata su proposta`. Risposta: "✓ … · secondo turno (21:30)
     Confermata."
   - Non entra più → `assegna-tavoli-difficile`, "Cosa scrivere quando non entra".
3. **No a una proposta** ("no", "no grazie"): `rifiutata`, `motivo` = il motivo della proposta + "; proposta non
   accettata"; registro `rifiutata`.
4. **Risposta a una domanda**: completa la richiesta salvata con la risposta, metti `domanda` a `null` e riprendi
   la procedura da dove si era fermata:
   - turno ("primo", "1t", "il secondo"): `turno_chiesto` = quello, poi punto 4 dal passo 4;
   - dato mancante (coperti, orario): aggiornalo, poi punto 3 e punto 4 dal passo 4;
   - nome già presente: "è un'altra", "nuova" → punto 4 dal passo 4 (con il suo `n`); "la stessa", "sposta", "sì"
     → modifica della prenotazione che c'era (punto 6) con i dati salvati, e la riga della domanda diventa
     `annullata` con `motivo` "era una modifica della prenotazione n …".
   Le scritture del punto 4 qui **aggiornano la riga che c'è già** (stesso `n`), non ne aggiungono una nuova. La
   richiesta entra solo se c'è posto adesso: chi è stato confermato nel frattempo resta dov'è (vedi "Priorità"
   nella skill `stato-serata`).
5. Un'altra richiesta ("e alle 22?") vale come nuovo orario per la stessa prenotazione: rifai il punto 4 dal passo 4,
   con lo stesso `n`.

## 6. Modifica

1. Trova la prenotazione (nome e data). Se non la trovi o ce n'è più d'una, chiedi.
2. Prepara la versione nuova (coperti, orario, turno, data, note). Il turno promesso cambia solo perché lo chiede il
   proprietario.
3. **Solo le note**: aggiorna `note`, registro `modifica`. Fine.
4. **Stessa serata**:
   - stesso turno e meno coperti: resta sulla sua unità (registro `modifica`);
   - altrimenti `assegna-tavoli` per la versione nuova, **togliendo la prenotazione stessa** dalle occupate (passo 0).
     ENTRA → aggiorna la riga (coperti, orario, `turno_chiesto`, `turno`, `unita`), registro: eventuali
     `cambio tavolo`, poi `modifica` ("4 → 6 coperti", "primo → secondo turno"). `n` non cambia.
   - Non entra → **non cambia niente** (`assegna-tavoli-difficile`, "Cosa scrivere quando non entra").
5. **Altra serata**: prova `assegna-tavoli` nel file dell'altra serata. Se entra: scrivi come dice `stato-serata`
   ("Spostata a un'altra serata"). Se non entra: non cambia niente, e lo dici.

## 7. Annullamento

1. Trova la prenotazione (nome e data; se è ambigua, chiedi).
2. La riga diventa `annullata`: `unita` `null`, `turno` resta, `motivo` = "annullata dal proprietario". Registro
   `annullata` con `da` = l'unità liberata. Vale anche per una `in_attesa` (lì `turno` e `da` restano `null`).
3. Se si libera "`<id>`-1" del lungo e "`<id>`-2" è occupato: chi era su "`<id>`-2" passa a "`<id>`-1" (stesso
   tavolo): aggiorna la sua riga e scrivi `cambio tavolo` da "`<id>`-2" a "`<id>`-1", motivo "annullato il primo
   gruppo del lungo".
4. Gli altri non si spostano. Risposta: "✓ Annullata: Rossi · 4 persone · sab 31/10 · primo turno."

## 8. Risposte

Formato di `CLAUDE.md`. Se il turno non è ancora deciso, nella prima riga l'orario chiesto: "✓ Rossi · 4 persone ·
sab 31/10 · 20:00".
