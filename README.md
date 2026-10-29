# Olimpo · assistente di sala (versione solo agente)

Gestionale delle prenotazioni del ristorante Olimpo fatto **solo di istruzioni per Claude Code**: aprendo Claude
Code in questa cartella, la sessione diventa l'assistente di sala. Legge il messaggio del proprietario (formato
compatto o testo libero), decide chi entra, in quale turno (20:00 o 21:30) e a quale tavolo, e scrive lo stato della
serata in un file JSON. Non c'è codice: solo file markdown (`CLAUDE.md`, skill, agenti), la piantina e i dati.

È una variante del repository con il motore CP-SAT in Python (remote `motore`), da cui viene la piantina.

## Che cosa cambia rispetto al motore

| | motore (Python, CP-SAT) | questa versione |
|---|---|---|
| installazione | Python, venv, OR-Tools, un processo acceso per la chat | solo Claude Code |
| chi decide | il solver, su tutte le disposizioni possibili | il modello, seguendo le procedure delle skill |
| "turno pieno" | dimostrato dal solver | dimostrato solo se lo dicono i conteggi per soglia; altrimenti "non trovo posto (non dimostrato)" |
| ripetibilità | stesso ingresso, stesso risultato | i risultati possono cambiare tra un'esecuzione e l'altra |
| costo | CPU locale | token: misurati con `claude -p` e Sonnet 5.5, 0,13-0,84 $ a messaggio e 4,70 $ per rigiocare il sabato di prova (vedi sotto) |
| testo libero | con una chiave API a parte | letto direttamente dal modello |
| regole | nel codice e nei pesi | in italiano, in `agente/regole.md` e nelle skill |

## Come si usa

Aprire Claude Code nella cartella del repository e scrivere come al telefono:

```
Rossi 4 sab 20:30
Rossi 4 sab 2t compleanno
mi ha chiamato Bianchi: venerdì in 6 verso le nove e mezza, uno è in carrozzina
sì
Rossi diventano 6
annulla Rossi sab
c'è posto per 8 sabato alle 21?
riepilogo sab
rigioca dati/olimpo_sabato.json
```

Un messaggio solo, senza sessione aperta (le scritture dei file vanno permesse, Bash resta escluso):

```
claude -p "Rossi 4 sab 20:30" --permission-mode acceptEdits
claude -c -p "sì" --permission-mode acceptEdits
```

`-c` continua l'ultima conversazione; anche senza, una risposta breve ("sì", "primo") si ritrova, perché proposte e
domande in sospeso sono scritte nel file della serata come prenotazioni `in_attesa`. Da un'altra sessione si usa l'agente `sala-olimpo`; per un secondo parere su una
serata l'agente `controllo-sala` (sola lettura).

## Dove sta cosa

- `CLAUDE.md`: ruolo dell'assistente, quale skill per quale messaggio, divieti, formato delle risposte.
- `agente/regole.md`: regole dure, regole di buonsenso in ordine di priorità, zone della sala (IPOTESI da confermare).
- `.claude/skills/`: `sala` (catalogo dei tavoli dalla piantina, conteggi), `stato-serata` (formato del file),
  `assegna-tavoli` (la procedura centrale), `prenotazione`, `disponibilita`, `riepilogo`, `controllo-serata`,
  `rigioca`, `mossa-tavoli`.
- `.claude/agents/`: `sala-olimpo` (l'assistente come sub-agent), `controllo-sala` (verificatore indipendente).
- `olimpo/piantina.html`: la sala vera, fonte unica (blocco JSON `id="sala"`); si cambia solo con l'editor.
- `dati/olimpo_sabato.json`, `dati/olimpo_venerdi.json`: serate di prova.
- `serate/AAAA-MM-GG.json`: lo stato reale, una serata per file. **Fuori dal git**: contiene nomi e note dei clienti
  e il repository di origine è pubblico; in più cambia a ogni messaggio. Va copiato a parte (backup) da chi lo usa.
- `prove/<etichetta>/`: prove e demo (rigioca, casi manuali). Fuori dal git: si rifanno quando servono.

## Aggiornare la piantina

La piantina si modifica con l'editor nel repository del motore. Quando lì è salvata su `main`, dalla cartella di
questo repository:

```
git fetch motore
git checkout motore/main -- olimpo/piantina.html
```

(da un'altra cartella: `git -C C:\repos\olimpo-agente fetch motore` e
`git -C C:\repos\olimpo-agente checkout motore/main -- olimpo/piantina.html`). Alla sessione successiva l'assistente
vede che la data o lo storico sono cambiati, ricalcola i tavoli con le regole della skill `sala` e lo dice.

## Riferimento atteso dei test

Motore CP-SAT sulla piantina del 29/10/2026, politica "il cliente accetta sempre la proposta dell'altro turno":

| serata | accettate | su proposta | coperti | rifiutate |
|---|---|---|---|---|
| sabato `dati/olimpo_sabato.json` | 63 su 67 | 6 | 242 su 260 | Marini ×10, Palumbo ×2, Sala ×4, Rossetti ×2 |
| venerdì `dati/olimpo_venerdi.json` | 35 su 35 | – | 121 su 121 | nessuna |

Per l'assistente si guarda: `controllo-serata` (e `controllo-sala`) in PASS, nessuna confermata tolta, ogni rifiuto
con il suo motivo "dimostrato" o "non dimostrato". Qualche rifiuto in più del motore è atteso (vedi limiti).

### Prove del 29/10/2026 (Sonnet, solo Read/Grep/Glob/Edit/Write)

Ogni rigioca è stata ricontrollata fuori dal repository con un CP-SAT esatto, che rifà nell'ordine d'arrivo ogni
proposta e ogni rifiuto sullo stato scritto dall'assistente e cerca i "pieno" falsi.

| prova | accettate (su proposta) | coperti | posti vuoti 1° · 2° turno | pieni falsi | durata · token |
|---|---|---|---|---|---|
| venerdì | 35/35 (0) | 121/121 | 2 · 5, come il motore | 0 | 4 min · ~145 mila |
| sabato, skill della prima versione | 63/67 (6) | 238/260 | 31 · 21 | **7** (5 mandati nel secondo turno e 2 rifiutati che entravano nel primo) | 10 min · ~205 mila |
| sabato, skill attuali | 63/67 (6) | 242/260 | 30 · 18, come il motore | 0 | 10 min · ~233 mila |

Sull'ultima prova del sabato l'esito è identico a quello del motore: stessi 4 rifiutati e stessi numeri per turno.
È una prova sola, quindi non è detto che ogni esecuzione dia lo stesso risultato: l'assistente ha ammesso di aver
usato, per alcuni rifiuti, un ragionamento di capacità invece di provare tutte le catene. Messaggi veri con
`claude -p`, una sessione nuova per messaggio: da 43 a 77 secondi l'uno (il motore risponde in meno di un secondo);
conferme, proposte, "sì" a una proposta, risposta "primo" alla domanda delle 20:45, doppio nome, disponibilità e
riepilogo corretti.

### Validazione del 29/10/2026 (skill attuali)

Serate nuove generate apposta (`prove/dati-test/`, fuori dal git), riferimento del motore sulla stessa piantina,
controllo CP-SAT esterno su ogni proposta e ogni rifiuto:

| serata | assistente | motore | pieni falsi |
|---|---|---|---|
| sabato `olimpo_sabato.json`, 3 esecuzioni | 63/67 (6 su proposta), 242 coperti, tutte e 3 | 63/67 (6), 242 | 0 |
| coppie (84 prenotazioni da 2-4) | 72/84 (9), 208 coperti | 72/84 (9), 208 | 0 |
| gruppi medi (46, soprattutto da 5-8) | 41/46 (2), 222 coperti | 41/46 (2), 222 | 0 |
| casi limite (64: fuori turno, 20:45, `turno`, 22 persone) | 61/64 (8), 255 coperti | 61/64 (4), 255 | 0 |

Nei casi limite le 4 proposte in più sono gli orari fuori turno (18:30, 19:00, 22:45, 23:00). L'assistente li
registra solo dopo il sì al turno più vicino, come dicono le regole; la rigioca del motore li accetta direttamente.
Rifiutati identici al motore in tutte le serate.

- **Verificatore** `controllo-sala`, su un file con 7 errori inseriti e uno pulito, senza sapere quale: ha trovato
  tutti e 7 gli errori, comprese le sovrapposizioni che creavano, e ha dato PASS al file pulito.
- **Conversazione** con `claude -p` su un sabato già pieno (18 messaggi, da 47 a 175 secondi l'uno). Corretti:
  - rifiuto vero, annullamento, modifica che non entra (resta la vecchia);
  - domande sul doppio nome e sui coperti mancanti;
  - con più domande in sospeso chiede a quale si risponde, e "sì" o "no grazie" senza niente in sospeso.

  **Errori**:
  - **2 "pieno" falsi**. Bassi ×2 entrava nel primo turno con una catena di 2 spostamenti: Ferretti ×10 dal lungo
    al 10, Gentile ×5 dal 10 a "11-1", Bassi a "11-2". Moretto ×3 ha riusato quell'esito sbagliato;
  - in 3 messaggi il controllo della serata non è stato fatto per intero;
  - una disponibilità ha detto "ultimo posto" quando ne restavano altri.
- **Deviazioni nelle rigioche**: in 4 esecuzioni su 5 l'assistente ha deciso a mente le prime ~50 prenotazioni
  prima di scriverle, e ha riletto il file meno spesso di quanto chiede la skill. Il risultato non è cambiato.
- **Costo**: da 180 a 280 mila token per una rigioca, da 7 a 17 minuti.

In sintesi: quando la procedura è eseguita per intero il risultato coincide con quello del motore. Il punto debole
sono i messaggi singoli a sala piena, dove il modello accorcia le catene e i controlli.

### Dopo le correzioni per la sala piena (29/10/2026, sera)

Le correzioni:
- lo scambio lungo–tondo tra gli schemi fissi del passo 2a;
- un `provati` specifico, con il nuovo controllo C15;
- nessun riuso degli esiti di altre prenotazioni;
- il controllo della serata sempre per intero;
- una disponibilità senza "ultimo posto" non contato;
- una ricerca obbligatoria delle richieste in sospeso anche per le risposte di una parola o un numero.

Prove con `claude -p --output-format json`, che riporta il costo calcolato da Claude Code:

| prova | esito | costo · tempo |
|---|---|---|
| rigioca del sabato | 63/67, 242 coperti, stessi rifiutati del motore, 0 pieni falsi al CP-SAT, controllo C1-C15 PASS | 4,70 $ · 22 min · 221 passaggi (15,5 milioni di token letti dalla cache, 0,4 scritti, 0,15 di output) |
| conversazione a sala piena, 8 messaggi | annullamento, Ferretti ×10 sul lungo, Bassi ×2 delle 19:00 ora proposto nel primo turno (prima era un pieno falso), "no grazie" → rifiutata, domanda dei coperti a Moretto, disponibilità con lo scambio lungo–tondo descritto giusto | 0,13-0,50 $ a messaggio · 22-84 s |
| la stessa conversazione: "3" come risposta a "per quante persone?" | prima della correzione la sessione ha risposto senza guardare i file; dopo, 3 prove su 3 giuste (Moretto ×3: secondo turno pieno, proposto il primo, come dice il CP-SAT) | 0,72-0,84 $ · ~1 min |

Una serata piena costa all'incirca quanto i messaggi che arrivano: con circa 0,45 $ a messaggio, una sessione nuova per
messaggio e un'ottantina di messaggi per un sabato da 67 prenotazioni, fanno circa 35 $ a serata. È una stima: il
numero di messaggi a serata non è misurato. La rigioca invece costa meno per prenotazione (4,70 $ per 67), perché la
sessione è una sola.

### Sonnet 5.5 contro Haiku 5.5 (29/10/2026, `claude -p --model haiku`, stesse prove e stessi stati di partenza)

| prova | Sonnet 5.5 | Haiku 5.5 |
|---|---|---|
| rigioca del sabato | 63/67, 0 pieni falsi · 4,70 $ · 22 min | 63/67, 0 pieni falsi · 0,23 $ · 7 min, ma con il file scritto in un colpo solo alla fine e la skill che allora conteneva il risultato atteso (vedi sotto) |
| rigioca coppie (serata nuova) | 72/84, 0 pieni falsi (sotto-agente, costo non misurato) | 72/84, 0 pieni falsi · 2,13 $ · 19 min |
| rigioca casi limite (serata nuova) | 61/64, 0 pieni falsi (sotto-agente, costo non misurato) | 61/64 ma **4 pieni falsi**: Fontana, Pastore, Melis e Mazzoni mandati nel secondo turno mentre nel primo c'era posto · 1,89 $ · 20 min |
| conversazione a sala piena, 8 messaggi | 8 giusti · 0,13-0,50 $ a messaggio | 7 giusti; la disponibilità finale "non trovo posto per 2" è sbagliata (ha riusato tentativi vecchi; una coppia entrava) · 0,015-0,14 $ a messaggio |
| "3" come risposta, 3 prove | 3 su 3 · 0,72-0,84 $ | 3 su 3 · 0,10-0,15 $ |
| controllo della serata per intero | sempre | saltato o parziale in 3 messaggi su 8 |

Haiku costa da 5 a 8 volte meno a messaggio. Nelle rigioche lunghe la differenza scende: sopra i 100 mila token di
contesto Haiku 5.5 costa 5 volte di più, e legge di più (25-31 milioni di token dalla cache contro 15,5). Haiku però
sbaglia più spesso proprio quando la sala è quasi piena, cioè dove un errore fa perdere un cliente o gli dà il turno
sbagliato. Con le prove fatte fin qui, le decisioni vanno lasciate a Sonnet.

Dopo queste prove la skill `rigioca` non contiene più i risultati attesi, e dalle skill sono spariti i nomi dei
rifiutati del sabato. Gli esempi svolti di `assegna-tavoli` vengono però ancora dal sabato di prova, quindi quella
serata non è più una prova alla cieca: per validare si usano le serate di `prove/dati-test/`.

## Limiti noti

- **"Pieno" dimostrato solo dai conteggi per soglia** (condizioni necessarie): un turno davvero pieno ma non coperto
  dai conteggi risulta "non trovo posto (non dimostrato)".
- **Procedura a passi** (miglior incastro, divisione di chi siede largo e scambio lungo–tondo, catene fino a 3
  spostamenti, riassegnazione del turno): può rifiutare un gruppo che il motore, cercando tra tutte le disposizioni,
  farebbe entrare. Ogni "non trovo posto" porta nel registro l'elenco specifico di ciò che è stato provato.
- **Costo semplificato**: la scelta del tavolo pesa 10 per posto vuoto e 4 per taglio nuovo di un blocco; il peso
  lieve del motore per i blocchi divisi in modo diverso tra il primo e il secondo turno non c'è.
- **Errori di conto possibili**: per questo ogni scrittura finisce con `controllo-serata`, e c'è `controllo-sala`.
- **Una sessione alla volta** sullo stesso file di serata: non ci sono blocchi contro le scritture contemporanee.
- **L'ora non è nota**: per la serata di oggi l'assistente non sposta chi è già confermato senza chiedere.
- **IPOTESI da confermare**: le zone della sala (spareggi e accessibilità), le posizioni di 7-12, le sedie in testa
  nelle mosse di tavoli; sul secondo gruppo del lungo i posti vuoti sono contati come 8 meno i coperti.
- I giorni della settimana si contano da un giorno noto (sabato 31/10/2026).
