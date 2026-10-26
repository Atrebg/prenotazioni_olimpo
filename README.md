# Ristorante · tavoli e prenotazioni (prototipo CP-SAT)

Motore che organizza la sala di un ristorante per una serata decidendo **insieme**:

1. dove mettere i tavoli (posizione 2D, moduli quadrati accostati in fila, orientamento, tavoli tondi);
2. a quale tavolo e a che ora sistemare ogni prenotazione.

Solver: OR-Tools CP-SAT 9.15. Uscite: `soluzione.json`, `serata.html` (mappa SVG, timeline, registro;
file unico senza CDN), verifica indipendente.

Due scelte in configurazione (`dati/sala_esempio.json`, sovrascrivibili da riga di comando):

| chiave | valori | significato |
|---|---|---|
| `accettazione` | `ordine_di_arrivo` (default) · `tutte_insieme` | "i primi che prenotano restano dentro" · ottimizzazione unica (modalità originale) |
| `disposizione` | `fissa` (default) · `variabile` | tavoli fermi tutta la sera · la piantina può cambiare durante il servizio |
| `turni` | assente (default) · elenco di turni | orari liberi · ogni prenotazione occupa il tavolo per tutto il suo turno ([modalità a turni](#modalità-a-turni)) |

La sala del ristorante Olimpo a turni (primo alle 20:00, secondo alle 21:30) è `dati/sala_turni.json`: la sala di
esempio più i turni (un test controlla che il resto resti uguale).

## Installazione

Serve Python 3.12 (provato con 3.12). Dalla cartella del progetto:

```powershell
# Windows
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
# Linux / macOS
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Negli esempi qui sotto si usa `.venv\Scripts\python.exe` (Windows); su Linux e macOS è `.venv/bin/python`.

**Chiave `ANTHROPIC_API_KEY` (opzionale).** Serve solo alla chat per leggere i messaggi scritti liberamente
("domani sera in 4 verso le 8, Bianchi"). Senza chiave tutto il resto funziona e la chat capisce il formato compatto
(`Rossi 4 sab 20:30`). Si imposta come variabile d'ambiente, mai nel codice né in un file del repository.

## Comandi principali

| comando | cosa fa | esempio |
|---|---|---|
| `esegui.py` | organizza una serata: risolve, scrive `soluzione.json` e `serata.html`, verifica | `.venv\Scripts\python.exe esegui.py --prenotazioni dati\sabato_pieno.json --out out` |
| `chat.py` | chat con il proprietario: nuova prenotazione, modifica, annulla, disponibilità, riepilogo | `.venv\Scripts\python.exe chat.py --messaggio "Rossi 4 sab 20:30" --cartella dati\serate` |
| `chat.py --piantina` | disposizione dei tavoli di una serata già in chat, con verifica | `.venv\Scripts\python.exe chat.py --piantina 2026-10-31 --cartella dati\serate` |
| `prova.py` | "c'è posto?" al telefono, senza scrivere file | `.venv\Scripts\python.exe prova.py --stato out\soluzione.json --coperti 2 --orario 21:00` |
| `confronto.py` | confronta disposizione fissa e variabile, o politiche di proposta | `.venv\Scripts\python.exe confronto.py --modi fissa variabile` |
| `confronto.py` a turni | le tre combinazioni a turni su sabato_pieno | `.venv\Scripts\python.exe confronto.py --sala dati\sala_turni.json --combinazioni fissa:mai fissa:sempre variabile:sempre --out out\confronto_turni` |
| `verifica.py` | verifica indipendente di una soluzione | `.venv\Scripts\python.exe verifica.py --sala dati\sala_esempio.json --prenotazioni dati\sabato_pieno.json --soluzione out\soluzione.json` |
| `valuta_lettura.py` | misura la precisione della lettura via Claude sui messaggi di `valutazione/` (serve la chiave) | `.venv\Scripts\python.exe valuta_lettura.py` |
| `pytest` | test | `.venv\Scripts\python.exe -m pytest -q` |

## Agente

In `agente/` c'è `sala-olimpo`, un agente di Claude Code che gestisce prenotazioni e sala dai messaggi del
proprietario. Le regole (dure e di buonsenso) stanno in [`agente/regole.md`](agente/regole.md); la definizione
dell'agente è in [`.claude/agents/sala-olimpo.md`](.claude/agents/sala-olimpo.md) e traduce le richieste nei comandi del
motore, senza mai decidere lui "entra / non entra". Vedi [`agente/README.md`](agente/README.md).

## Come si lancia

Comando unico (risolve → scrive JSON e HTML → esegue la verifica; exit code 0 solo se la verifica è PASS):

```powershell
.venv\Scripts\python.exe esegui.py
```

Di default: `dati\sabato_pieno.json` (30 prenotazioni), accettazione in ordine di arrivo, disposizione "fissa", proposta dell'orario più vicino accettata "sempre" (tutto dalla config).
Opzioni: `--sala`, `--prenotazioni`, `--out`, `--accettazione`, `--disposizione`, `--tempo` (tutte_insieme),
`--tempo-decisione`, `--tempo-spareggio`, `--tempo-piantina` (ordine_di_arrivo), `--log`.

- Modalità originale: `esegui.py --accettazione tutte_insieme --prenotazioni dati\sabato.json`
- Senza proposte di orario: `esegui.py --proposta mai` (altre politiche: `sempre`, `entro_60_min`)
- **Confronto per il proprietario** (fissa contro variabile, ordine di arrivo, sabato_pieno):
  `confronto.py` → `out\confronto\{fissa,variabile}\` più `out\confronto\confronto.json` e una tabella a video.
  `confronto.py --da-json` rigenera mappe, verifiche e tabella senza risolvere di nuovo.
- Solo la verifica: `python verifica.py --sala ... --prenotazioni ... --soluzione ...`
- Test: `.venv\Scripts\python.exe -m pytest -q` (circa un minuto; il primo `import ortools` può richiedere una decina
  di secondi).

## Chat con il proprietario (`chat.py`)

Simula da riga di comando la chat 1:1 che domani passerà da WhatsApp. Il processo resta vivo, così OR-Tools si carica
una volta sola (circa 3-25 s all'avvio su questa macchina).

```powershell
.venv\Scripts\python.exe chat.py                                   # chat interattiva, "esci" per uscire
.venv\Scripts\python.exe chat.py --messaggio "Rossi 4 sab 20:30"   # un colpo solo
.venv\Scripts\python.exe chat.py --ora 2026-10-27T10:00            # orologio finto
.venv\Scripts\python.exe chat.py --piantina 2026-10-31             # disposizione dei tavoli della serata + verifica
.venv\Scripts\python.exe chat.py --senza-tabella                   # senza tabella delle disponibilità (verifica diretta)
.venv\Scripts\python.exe chat.py --sala dati\sala_turni.json      # ristorante a turni (Rossi 4 sab 1t)
.venv\Scripts\python.exe misura_chat.py [--attendi-tabella]        # tempi di risposta sul copione di 10 messaggi
```

- **Ingresso per il webhook:** `ristorante.conversazione.gestisci_messaggio(testo, ricevuto_il, mittente, cartella_stato) -> str`.
- **Formato compatto, letto senza LLM:** `Rossi 4 sab 20:30 [note]`, `Rossi 4 31/10 20:30 seggiolone`, `annulla Rossi sab`,
  `riepilogo sab`. Le risposte brevi a una domanda ("x 4", "alle 21", "Bianchi", "stasera") e le conferme di una
  proposta ("21", "la seconda", "ok 20:15", "no grazie") si leggono anch'esse senza LLM.
- **Tutto il resto va a Claude** con l'SDK ufficiale `anthropic` e l'output strutturato (`messages.parse` con uno
  schema Pydantic). Il modello di default è `claude-haiku-5-5` con effort `low`: il proprietario ha chiesto la cosa
  più economica. Si configura in `dati/sala_esempio.json` → `chat` (`modello`, `effort`, `max_tokens`, `timeout_s`).
  Un rifiuto del modello (`stop_reason: refusal`), una risposta troncata e gli errori dell'API (dal più specifico al
  più generico) non bloccano la chat: si risponde indicando il formato compatto.
- **Chiave:** `ANTHROPIC_API_KEY` del processo, altrimenti le variabili utente di Windows (HKCU\Environment), lette
  dentro il processo. Non viene stampata né scritta. Senza chiave la lettura via LLM è disattivata e la chat lo dice.
  Dietro un proxy con certificati propri, a un errore TLS si passa allo store certificati di Windows (`truststore`), mai senza verifica.
- **Cosa fa:** nuova (registra solo se entra all'orario esatto, altrimenti propone e aspetta la conferma), conferma
  (ricontrolla, poi registra e congela; se lo stato è cambiato ripropone), modifica (ricontrolla escludendo la
  prenotazione stessa; la vecchia resta valida finché non c'è la conferma), annulla, disponibilità, riepilogo.
  Le proposte sono prima gli spostamenti ammessi che entrano, poi il più vicino prima e il più vicino dopo, entro
  `chat.proposta_max_min` (60) minuti; scadono dopo 15 minuti. Controlli del codice: data non passata ed entro 90
  giorni, giorno della settimana coerente con la data, "alle 8" = 20:00, orari arrotondati al quarto d'ora (lo dice),
  "sabato" scritto di sabato → "stasera o sabato prossimo?". Se mancano campi, chiede solo quelli.
- **Stato:** `dati/serate/AAAA-MM-GG.json` (accettate con orario congelato e `prenotata_il` = ora del messaggio, rifiuti,
  annullate, proposte in sospeso, storico dei messaggi con i tempi) più `_mittenti.json` (bozze e scelte in corso).
  Scrittura atomica: file temporaneo nella stessa cartella, fsync, `os.replace` (con qualche ritento se un antivirus
  tiene aperto il file).
- **Valutazione della lettura:** `valuta_lettura.py` passa i 45 messaggi di `valutazione/messaggi.jsonl` a Claude, applica
  gli stessi controlli della chat e stampa la precisione per campo e gli errori. Senza chiave esce dicendolo.
- **Nome già presente:** "Rossi 4 sab 21:00" con un Rossi già registrato → "C'è già Rossi alle 20:30 per 4 persone
  (sab 31/10): è un'altra prenotazione o la sposto alle 21:00?". "altra/nuova" prosegue come nuova, "sposta/sì/la
  stessa" come modifica di quella esistente.

### Tabella delle disponibilità (`ristorante/disponibilita.py`)

Serve a rispondere in meno di un secondo anche a sala quasi piena. In modalità interattiva `chat.py` la calcola in
background per ogni serata con stato (da oggi in poi) e la ricalcola da capo dopo ogni modifica.

- **Cella** = (classe di coperti, orario d'inizio): una prenotazione in più di quella classe a quell'orario entra
  insieme a tutte le accettate, con gli orari congelati? `entra` / `non entra` (dimostrato) / `da verificare`.
  Le **classi** si ricavano dalla sala: coperti con la stessa durata e le stesse forme di tavolo ammesse, quindi
  identici per il modello. Nella sala di esempio: 1-2, 3-4, 5-6, 7-8, 9-10, 11-12 (`classi_coperti`, con test).
- **Come si chiude una cella:** conteggio dei moduli; limite geometrico (quanti tavoli entrano insieme nella sala con
  almeno n tavoli da 5, 7, 9, 11 posti: bound dimostrato da CP-SAT, calcolato una volta per sala, circa 60 s, e
  salvato in `dati/cache/_geometria_<hash>.json`); dominanza tra classi nei due versi (se a un orario non entra una
  classe, non entrano le più grandi; se entra, entrano le più piccole); altrimenti CP-SAT con l'hint dell'ultimo
  piano registrato (`AAAA-MM-GG.piano.json`).
- **Mai una tabella vecchia:** ogni modifica aumenta `versione` nello stato e nel file `AAAA-MM-GG.versione`; una
  tabella vale solo per la sua versione e i processi interrompono da soli i calcoli di una versione superata.
  La tabella completa si scrive anche in `AAAA-MM-GG.tabella.json` (solo per ispezione).
- **Processi:** `chat.processi` (6) × `chat.worker_per_processo` (2) worker CP-SAT, `chat.tempo_cella_s` (20) per
  cella. Scelti misurando 6×2, 4×3, 3×4, 2×6, 12×1 (vedi sotto).
- **Tabella non pronta:** l'orario chiesto e tutti i candidati si verificano in parallelo, con precedenza sul calcolo
  di background; ci si ferma appena la risposta è decisa. Dopo `chat.attesa_max_s` (5) si risponde con ciò che è
  dimostrato, senza mai dire "pieno" per un orario non dimostrato ("alle 20:30 sto ancora verificando; di sicuro
  posso alle 21:30. Quale?"); la verifica continua e il messaggio successivo comincia con "Aggiornamento: …".
- **Registrazione:** anche se la cella dice `entra`, si registra solo dopo un solve che restituisce il piano: tavoli e
  altre prenotazioni fissati come nel piano della cella, CP-SAT sistema la nuova controllando tutti i vincoli
  (centesimi di secondo); se non basta, ricerca libera partendo da quel piano.
- Le proposte vengono dalla stessa riga della tabella: stessa regola di prima (spostamenti ammessi che entrano, poi
  il più vicino prima e dopo entro 60 minuti, con tutti i più vicini dimostrati impossibili).

## Modalità a turni

Si attiva con `turni` nella sala (`dati/sala_turni.json`); senza `turni` tutto resta come prima.

```json
"turni": [{"nome": "primo", "inizio": "20:00", "fine": "21:30"}, {"nome": "secondo", "inizio": "21:30", "fine": "24:00"}],
"turno_a_parita": "prima",
"turni_vicino_min": 45
```

- **Regole.** Ogni prenotazione occupa il tavolo per tutto il suo turno: durate e riapparecchiatura non contano (il primo
  turno lascia il tavolo alle 21:30, il secondo arriva alle 21:30). Niente spostamenti di −15/+30. Un orario chiesto
  va nel turno più vicino, a parità quello prima (`turno_a_parita`: `prima` o `dopo`); un turno si può chiedere
  anche direttamente (`"turno": "secondo"` nelle prenotazioni, "1t", "2t", "primo turno" in chat). Il picco della
  cucina è disattivato. Restano le regole di sempre: chi prenota prima resta dentro, il turno promesso si congela, se
  il turno chiesto è pieno si propone l'altro e si registra solo dopo il sì (la politica del cliente misura la
  distanza tra l'orario chiesto e l'inizio del turno proposto).
- **Modello** (`ristorante/modello_turni.py`). Senza il tempo continuo ogni turno è un problema di sola sistemazione:
  su ogni tavolo al più una prenotazione per turno. "fissa" = stessi tavoli e stessi accostamenti in tutti i turni
  (un solo NoOverlap2D); "variabile" = una disposizione per turno, con un tavolo che è "lo stesso" del turno prima se
  ha forma e posizione uguali, altrimenti è montato a servizio iniziato e paga il riallestimento. Il conteggio dei
  moduli si fa per turno (in "fissa" sui tavoli che servono tutti i turni: il j-esimo tavolo più grande deve bastare
  alla j-esima prenotazione più grande di ogni turno). La tabella delle disponibilità è classe di coperti × turno.
- **Chat.** "✓ Rossi · 4 persone · sab 31/10 · primo turno (20:00)"; turno pieno: "…: il primo turno è pieno. Posso
  nel secondo, alle 21:30. Va bene?" (sì, ok, va bene, 2t, il secondo); entrambi pieni: "il primo turno è pieno, e
  anche il secondo"; un orario a più di `turni_vicino_min` minuti da ogni turno (19:00, 23:00) non si registra: "alle
  19:00 non c'è un turno. Il più vicino è il primo, alle 20:00. Va bene?". Il riepilogo è diviso per turno con i
  coperti. Una modifica che porterebbe nel turno dove la prenotazione è già non viene proposta.
- **Mappa.** In "fissa" una sola piantina con le prenotazioni di ogni turno su ogni tavolo; in "variabile" un cursore
  per turno e l'elenco dei cambi sala tra un turno e l'altro. La timeline mostra i coperti per turno al posto del
  carico della cucina.
- **Verificatore.** Turni della sala = turni dichiarati (consecutivi, dentro il servizio); ogni prenotazione nel turno
  chiesto (o nell'altro se accettata su proposta), con l'orario e la fine del turno; al più una prenotazione per turno
  su ogni tavolo; turno finale = turno promesso; in "fissa" ogni tavolo c'è in tutti i turni (nessun accostamento
  cambia); proposte = inizi di altri turni.
- Tutti i comandi accettano la sala a turni: `esegui.py --sala dati\sala_turni.json`, `chat.py --sala
  dati\sala_turni.json`, `prova.py --sala dati\sala_turni.json ...`, `misura_chat.py --turni`.

### Confronto a turni (sabato_pieno, ordine di arrivo, esecuzione del 26/10/2026)

Stesse 30 prenotazioni (106 coperti), orari messi nel turno più vicino: 15 nel primo turno (52 coperti), 15 nel
secondo (54). Riferimento: senza turni 22/30 (75 coperti), con proposte 26/30 (85); Sonnet da solo 26/30 (86).

| | fissa, "mai" | fissa, "sempre" | variabile, "sempre" |
|---|---|---|---|
| accettate (su proposta) / rifiutate | 26 (0) / 4 | 26 (2) / 4 | 27 (2) / 3 |
| coperti accettati | 86 | 88 | 90 |
| primo turno: prenotazioni / coperti | 13 / 38 | 13 / 40 | 14 / 42 |
| secondo turno: prenotazioni / coperti | 13 / 48 | 13 / 48 | 13 / 48 |
| tavoli · accostati · riallestimenti | 13 · 1 da 4 moduli · 0 | 13 · 1 da 4 moduli · 0 | 15 · 1 da 4 moduli (solo nel secondo) · 1 |
| decisioni impossibili dimostrate · UNKNOWN | 4 · 0 | 4 · 0 | 3 · 0 |
| piantina | OPTIMAL | OPTIMAL | OPTIMAL |
| tempo totale | 8,1 s | 9,0 s | 74,5 s |
| verifica indipendente | PASS (22/22) | PASS (22/22) | PASS (22/22) |

- Rifiutate: fissa "mai" Giordano ×4 e Caruso ×2 (secondo turno pieno), Ferrari ×8 e Marino ×6 (primo turno pieno);
  fissa "sempre" Ricci ×2, Esposito ×2, Ferrari ×8, Marino ×6 (tutti i turni pieni; Giordano e Caruso passano al
  primo turno su proposta); variabile "sempre" Esposito ×2, Ferrari ×8, Marino ×6.
- In "variabile" alle 21:30 si smontano due tavoli da un modulo e si uniscono 4 moduli per Rizzo ×10: è l'unico
  riallestimento, e vale il ventisettesimo cliente.

## Il modello in parole

Griglia: spazio in celle da 10 cm, tempo in passi da 15 minuti dalle 19:00.

- **Slot tavolo**, tutti opzionali. Uno slot a moduli sceglie una forma (k = 1..5 moduli in fila, orizzontale
  o verticale; k = 1 è un quadrato) e la posizione dell'ingombro (tavolo + 50 cm per lato per le sedie), che deve
  stare nella sala. Capienza 2k + 2; tondo Ø120, capienza 6. Ogni slot presente ospita almeno una prenotazione.
- **Prenotazioni.** Booleana "seduta su questo slot", capienza ≥ coperti, orario tra gli spostamenti ammessi
  (−15, 0, +15, +30 min) con il pasto entro le 24:00; per ogni slot un `NoOverlap` sugli intervalli
  [inizio, inizio + durata + 15 min di riapparecchiatura).
- **Disposizione fissa.** Ogni tavolo esiste per tutta la serata: un solo `NoOverlap2D` sugli ingombri con
  ostacoli e corsie come rettangoli fissi; moduli totali ≤ 14, tondi ≤ 2.
- **Disposizione variabile.** Ogni slot ha un intervallo di esistenza [a, b) su passi da 15 min; una prenotazione
  (con riapparecchiatura) deve stare dentro l'esistenza del suo tavolo. Due slot possono usare lo stesso spazio
  solo se non esistono nello stesso momento (disgiunzione a coppie: separati in x, in y o nel tempo); ostacoli e
  corsie esistono sempre (un `NoOverlap2D` per slot). In ogni istante moduli in uso ≤ 14 e tondi ≤ 2
  (`Cumulative`). Peso `riallestimento` per ogni slot montato dopo l'apertura. "fissa" equivale ad a = apertura,
  b = chiusura.
- **Quanti slot in variabile.** `slot_variabile`: 28 a moduli (2 × 14) e 4 tondi (2 × 2), e mai più delle
  prenotazioni nel modello. Ogni slot ospita almeno una prenotazione, quindi più slot delle prenotazioni non
  servono mai: con ≤ 28 prenotazioni sui moduli il limite non toglie nessuna soluzione. Oltre, il doppio
  dell'inventario permette a ogni modulo di far parte di due tavoli diversi nella serata (una per ondata);
  alzarlo è lecito ma aumenta le coppie da separare (con 32 slot sono 496).
- **Obiettivo** (minimo; pesi in `pesi`):

| voce | chiave | default | significato |
|---|---|---|---|
| prenotazione non sistemata | `non_sistemata` | 10000 | per prenotazione, non per coperto |
| posto vuoto | `posto_vuoto` | 10 | per ogni posto del tavolo non usato da quella prenotazione |
| spostamento | `spostamento_per_quarto` | 30 | per ogni quarto d'ora di spostamento |
| accostamento | `accostamento_per_modulo` | 5 | per ogni modulo oltre il primo in un blocco |
| picco cucina | `picco_cucina_per_coperto` | 20 | per ogni coperto oltre `picco_cucina_soglia_coperti` (30) che inizia nello stesso quarto d'ora |
| riallestimento | `riallestimento` | 20 | per ogni tavolo montato a servizio iniziato (solo variabile) |

- **Simmetrie.** k non crescente tra gli slot a moduli (quindi presenza non crescente), a parità di k x non
  decrescente; tondi presenti per primi e ordinati per x; slot assenti con posizione (ed esistenza) fissata.

### Accettazione in ordine di arrivo

Le prenotazioni si rigiocano in ordine di `prenotata_il`. Per la prenotazione i:

1. se i coperti superano la capienza massima possibile, o nessun orario ammesso sta nel servizio, è rifiutata senza solver;
2. altrimenti si cerca un piano con tutte le accettate prima (obbligatorie, **orario congelato**, tavolo libero) più
   i, provando un livello di spostamento alla volta (0, poi ±15, poi +30) come problema di sola ammissibilità; i
   120 s della decisione (`tempo_decisione_s`) si dividono tra i livelli ancora da provare;
3. al primo livello ammissibile i è accettata: se il livello ha due direzioni (−15/+15) decide il resto
   dell'obiettivo (`tempo_spareggio_s`, 20 s). L'orario diventa quello promesso al cliente;
4. se tutti i livelli sono INFEASIBLE il rifiuto è dimostrato: "sala piena nella fascia richiesta, con le
   prenotazioni già accettate"; se almeno un livello resta senza risposta (UNKNOWN) e nessuno è ammissibile: "spazio
   non trovato entro il tempo limite", contato a parte. Se un livello basso è UNKNOWN e uno più alto ammissibile,
   la prenotazione entra ma il registro segna "spostamento minimo non dimostrato".

**Proposta dell'orario più vicino** (`cliente_accetta_proposta` ≠ `mai`). Se la prenotazione non entra in nessuno
spostamento ammesso, il motore cerca sulla griglia da 15 min, dentro il servizio e fino a `proposta_max_distanza_min`
(120) dall'orario chiesto, l'orario ammissibile più vicino **prima** e il più vicino **dopo**, ciascuno dimostrato
ammissibile con le accettate (sola ammissibilità, `tempo_proposta_s` = 60 s per orario). Gli orari sicuramente
impossibili si scartano prima col conteggio dei moduli: è una condizione sufficiente, implementata nel modello
separatamente dal verificatore. Proposta principale = la più vicina (a parità `proposta_a_parita`, default "prima").
Politica simulata del cliente: `sempre` (default della demo), `mai` (comportamento precedente, nessuna ricerca),
`entro_N_min`. Se il cliente accetta, l'orario proposto diventa quello promesso e si congela; esito nel registro
"accettata su proposta". Altrimenti la prenotazione è rifiutata con "proposta non accettata dal cliente", "nessun orario
libero entro N min" oppure, se una prova resta senza risposta, "spazio non trovato entro il tempo limite" (contato a parte).

**Al telefono** (`prova.py`, non scrive file): `prova.py --stato out\soluzione.json --coperti 2 --orario 21:00`
risponde per esempio "Alle 21:00 sono pieno. Posso alle 19:30 oppure alle 22:15.".

Ogni piano ammissibile è passato come hint al passo successivo. Alla fine la **piantina delle 18** (`tempo_piantina_s`,
300 s) ottimizza la disposizione con tutti gli orari congelati, con l'ultimo piano di accettazione come hint completo:
se il solver non restituisse nulla si usa quel piano, che è già ammissibile (il campo `solver.origine` lo dice).

## Assunzioni e scelte oltre la specifica

- **Ostacoli e corsie sovrapposti** (il pilastro sta dentro la corsia centrale): si usa la loro unione scomposta in
  rettangoli disgiunti, perché `NoOverlap2D` vieta anche la sovrapposizione tra rettangoli fissi.
- **Arrotondamenti conservativi** sulla griglia; per ogni forma x e y limitati alle posizioni libere nella sala vuota.
- **Vincoli ridondanti** (non cambiano le soluzioni, servono a dimostrare i rifiuti): in ogni passo, per ogni soglia
  di coperti, i tavoli abbastanza capienti sono almeno quante le prenotazioni attive; in "variabile" anche un
  `NoOverlap2D` per ogni passo sui tavoli che devono esistere e un limite sui moduli in uso. Su una decisione di
  prova (Greco, sabato_pieno, variabile) la dimostrazione del livello 0 è passata da 52 s a 4 s.
- **Fine dell'esistenza** di un tavolo che resta fino alla chiusura: 24:15 (24:00 più la riapparecchiatura dell'ultimo
  pasto), così "fissa" coincide con la modalità originale.
- **Esistenza leggibile** (solo variabile, dopo il solver): un tavolo montato a servizio iniziato si monta all'inizio
  della sua prima prenotazione; un tavolo resta fino alla chiusura se nessun altro tavolo né l'inventario ne hanno
  bisogno, altrimenti si smonta dopo la riapparecchiatura dell'ultima prenotazione. Costo invariato, la verifica lo ricontrolla.
- Montare o smontare un tavolo è istantaneo sulla griglia dei 15 minuti.
- **Tondo**: ingombro quadrato 120 + 2×50 cm. **Picco cucina**: coperti per orario di inizio assegnato.

## Verifica indipendente (`verifica.py`)

Non importa il pacchetto `ristorante`: rilegge i tre JSON e ricontrolla in cm e in minuti struttura, presenza di
ogni prenotazione una sola volta (seduta oppure rifiutata con motivo), forme e capienze, esistenza dei tavoli (griglia,
servizio, "fissa" = tutta la sera), moduli e tondi in uso in ogni istante, ingombri dentro la sala e disgiunti da
ostacoli e corsie, ingombri disgiunti tra loro nello spazio-tempo, capienza, orari, sovrapposizioni sullo stesso
tavolo con riapparecchiatura, prenotazioni dentro l'esistenza del tavolo, motivi, componenti dell'obiettivo
ricalcolate; con l'accettazione in ordine di arrivo anche registro ordinato per `prenotata_il`, orari finali uguali
a quelli promessi, coerenza tra registro, sedute e rifiuti; con le proposte anche distanza entro il massimo e fuori
dagli spostamenti ammessi, proposta principale uguale alla più vicina tra quelle registrate, esiti coerenti con la
politica dichiarata (per esempio nessuna accettazione oltre N minuti con `entro_N_min`).

**In generale non può dimostrare che un rifiuto fosse inevitabile**, né che la piantina sia ottima: controlla
ammissibilità e coerenza. Riporta però (INFO) i rifiuti che il solo conteggio dei moduli dimostra inevitabili in
qualunque disposizione: per ogni orario ammesso c'è un istante in cui accettate più rifiutata chiedono più moduli
dell'inventario, anche usando al meglio i tondi. È una condizione sufficiente: ignora la geometria, quindi un
rifiuto dovuto allo spazio (vedi test della sala da due moduli) non risulta dimostrato.

## Risultato del confronto (sabato_pieno, ordine di arrivo, esecuzione del 26/10/2026)

| | fissa | variabile |
|---|---|---|
| accettate / rifiutate | 22 / 8 | 22 / 8 |
| coperti accettati / rifiutati | 75 / 31 | 75 / 31 |
| tavoli · riallestimenti | 13 · 0 | 13 · 0 |
| piantina finale | OPTIMAL, obiettivo 80375 (375 senza i rifiuti) | OPTIMAL, obiettivo 80375 (375) |
| decisioni ammissibili / impossibili dimostrate / UNKNOWN | 22 / 8 / 0 | 22 / 8 / 0 |
| tempo decisioni · piantina | 14 s · 0,8 s | 456 s · 23 s |

Rifiutate in entrambe: Lombardi ×2, Giordano ×4, Mancini ×2, Caruso ×2, Gallo ×5, Ricci ×2, Ferrari ×8, Marino ×6.
Cambiare la piantina durante la serata **non fa entrare nessuno in più**: tra le 21:15 e le 22:00 le 13
prenotazioni accettate usano tutti i 14 moduli e i 2 tondi (Rizzo ×10 da solo ne prende 4), e ogni rifiutata, a
qualunque orario ammesso, chiederebbe almeno 15 moduli in quell'intervallo. Il limite è l'inventario, non lo spazio.
Per confronto, l'ottimizzazione unica (`tutte_insieme`, 30 s, FEASIBLE con gap 1,3%) siede 28 prenotazioni su 30
(88 coperti) lasciando fuori Rizzo ×10 e Ferrari ×8. Il gruppo da 10 accettato per primo non spiega da solo la
differenza: spostando la sua prenotazione in fondo, in ordine di arrivo con "fissa" entrano 24 prenotazioni ma 71
coperti (Rizzo resta fuori). Il resto della differenza dipende, con ogni probabilità, dal decidere una prenotazione
alla volta con l'orario congelato (ipotesi, non misurata separatamente).

## Risultato con le proposte (sabato_pieno, fissa, esecuzione del 26/10/2026)

`confronto.py --modi fissa --politiche mai sempre entro_60_min --out out\confronto_proposte`

| | mai | sempre | entro_60_min |
|---|---|---|---|
| accettate (su proposta) / rifiutate | 22 (0) / 8 | 26 (6) / 4 | 26 (4) / 4 |
| coperti accettati / rifiutati | 75 / 31 | 85 / 21 | 83 / 23 |
| proposte non accettate dal cliente | 0 | 0 | 1 (Giordano, proposta a +75′) |
| decisioni: ammissibili / con proposta / impossibili / UNKNOWN | 22 / 0 / 8 / 0 | 20 / 6 / 4 / 0 | 22 / 5 / 3 / 0 |
| piantina finale | OPTIMAL | OPTIMAL | OPTIMAL |
| tempo totale | 23 s | 39 s | 53 s |

Riferimento, con tutte le prenotazioni note in anticipo (`tutte_insieme`): 28 su 30, 88 coperti.
Con "sempre" restano fuori Gallo ×5, Esposito ×2, Ferrari ×8 e Marino ×6 ("nessun orario libero entro 120 min").

## Tempi della chat (`misura_chat.py`, 26/10/2026, Core Ultra 7 165U)

Copione fisso: stato = 22 accettate di sabato_pieno; 10 messaggi compatti (annullamento di Rizzo, poi Gallo ×5 che
prima non entrava, posti liberi, quattro richieste in fascia piena con proposta, una conferma, un "pieno").
Le risposte sono identiche prima e dopo, messaggio per messaggio.

| | prima (verifica diretta) | dopo, tabella pronta | dopo, tabella non pronta (raffica) |
|---|---|---|---|
| mediana | 12,98 s | 0,20 s | 0,81-1,66 s (due lanci) |
| massimo | 24,91 s | 0,53 s | 3,85-4,12 s |

- Ricalcolo della tabella dopo una modifica: mediana 2,1 s, massimo 11,1 s (dopo "Gallo 5 sab 20:00", la serata più
  tirata); prima tabella delle 22 accettate importate, senza piano salvato: 23,5 s; avvio dei processi 9-18 s.
- Combinazioni processi × worker, stessa serata tirata: tabella in 8,2 s (6×2), 10,4 s (3×4), 10,3 s (2×6),
  20,4 s (4×3), 5,9 s (12×1); in raffica 6×2 e 3×4 rispondono sempre in modo definitivo entro 4,1 s, 12×1 avvia in
  22-27 s e dà due risposte parziali (4,5-4,7 s). Scelto 6×2. Senza la dominanza "se entra la più grande entrano
  le più piccole" la stessa tabella richiedeva 32 s (6×2).

Modalità a turni (`misura_chat.py --turni`, sala a turni, 6×2): stato = le 21 accettate entro venerdì 16:00 nel
replay a turni (fissa, "mai"; primo turno 8, secondo 13 e pieno); 10 messaggi: annullamento di Rizzo, Giordano ×4 che
prima non entrava, Caruso ×2 nel posto liberato, quattro richieste nel secondo turno pieno con proposta del primo, una
conferma, un posto libero nel primo turno, un orario lontano dai turni (19:00). Risposte identiche nei tre casi.

| | senza tabella (verifica diretta) | tabella pronta | tabella non pronta (raffica) |
|---|---|---|---|
| mediana | 4,33 s | 0,13 s | 0,26 s |
| massimo | 13,32 s | 0,28 s | 2,62 s |

Ricalcolo della tabella dopo una modifica: mediana 0,9 s, massimo 1,1 s; prima tabella 1,6 s.

## Dati di esempio

- `dati/sala_esempio.json`: sala 1200×800, ostacoli, corsie, inventario, durate, pesi, modalità, tempi del solver.
- `dati/sala_turni.json`: la stessa sala con i turni del ristorante Olimpo (primo alle 20:00, secondo alle 21:30).
- `dati/sabato_pieno.json` (demo principale): 30 prenotazioni, 106 coperti, ricevute dal 25 al 31 ottobre;
  Rizzo ×10 prenota per primo, Ferrari ×8 tra gli ultimi.
- `dati/sabato.json`: 24 prenotazioni, 93 coperti, tarato perché con l'ottimizzazione unica si siedano tutti.

## Limiti noti

- Non modelliamo il disturbo agli ospiti seduti quando si spostano o si uniscono tavoli vicini, né il tempo di
  montaggio: in "variabile" un cambio sala accanto a un tavolo occupato è ammesso se gli ingombri non si toccano.
- Il peso "non sistemata" (modalità tutte_insieme) è per prenotazione: rinunciare a un gruppo da 10 costa quanto
  rinunciare a una coppia.
- In ordine di arrivo una prenotazione rifiutata resta rifiutata anche se più tardi si libererebbe spazio (non c'è
  lista d'attesa) e l'orario promesso non si rinegozia.
- Le proposte sono "le più vicine" rispetto al modello (solver INFEASIBLE o conteggio dei moduli sugli orari più vicini):
  il verificatore controlla che siano ammesse e coerenti, ma non può dimostrare che fossero le più vicine possibili.
- La politica del cliente è una simulazione (sempre, mai, entro N minuti); un cliente reale può scegliere la proposta
  secondaria o un altro orario. Accettare proposte lontane occupa orari che più tardi servirebbero ad altri.
- `prova.py` decide senza hint (lo stato non conserva il piano del solver) e reimporta OR-Tools a ogni chiamata
  (circa 10 s su questa macchina).
- Con molti thread i risultati possono cambiare da un lancio all'altro anche con lo stesso seed; i tempi limite rendono
  possibile un UNKNOWN su macchine più lente.
- Quando il limite è lo spazio e non l'inventario, dimostrare un rifiuto diventa difficile. Prova del 26/10 con 20 moduli
  invece di 14 (stessa sala, sabato_pieno): fissa 22 accettate, 1 rifiuto dimostrato e 7 UNKNOWN; variabile 22 accettate
  (71 coperti), 8 UNKNOWN, e Mariani ×6 resta fuori per tempo scaduto, mentre con "fissa" entra. Il modello variabile
  è più grande e in 120 s trova meno. Per rispondere davvero servono tempi di decisione più lunghi.
- Il tondo occupa un ingombro quadrato (stima prudente).
- Tabella delle disponibilità: le modifiche (e le conferme di una modifica) non usano la tabella, perché le celle
  contano anche la prenotazione da spostare: si verificano sempre in parallelo al momento. Il limite geometrico è
  legato alle chiavi geometriche della sala (dimensioni, griglia, ostacoli, corsie, inventario, margine sedie): se
  cambia altro che incide sulla disposizione va cancellato il file in `dati/cache`. Una verifica rimasta a metà
  occupa un processo fino a `tempo_verifica_s`. I processi di calcolo occupano circa 100 MB l'uno.
- Turni: la tabella delle disponibilità e la chat usano la disposizione `chat.disposizione` della sala (fissa); con
  più di due turni il codice funziona (proposte prima e dopo, riallestimento tra turni consecutivi) ma è provato solo
  con due. In "variabile" la rottura delle simmetrie vale solo nel primo turno: una decisione può richiedere decine di
  secondi (fino a 26 s su sabato_pieno, per Ricci ×2); in chat la tabella e il limite geometrico della sala chiudono di
  solito subito i "turno pieno" (misurato solo in "fissa"). Un orario esattamente a metà tra due turni va nel turno prima: se il cliente intendeva
  l'altro, va chiesto ("20:45" → primo turno).
- Chat: il cambio di data in una modifica non è gestito
  (si annulla e si riprenota). La lettura via LLM non è stata provata contro l'API su questo PC (nessuna chiave): i test
  usano un client finto. "Sabato prossimo" detto in settimana vale come il primo sabato che viene (convenzione).
