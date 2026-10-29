# Regole della sala dell'Olimpo (assistente senza motore, a turni)

Le **regole dure** non si violano mai. Le **regole di buonsenso** si rispettano quando è possibile e, se litigano
tra loro, vince quella più in alto nell'elenco. Come si applicano nella scelta del tavolo lo dice la skill
`assegna-tavoli`; i tavoli e i posti li dà la skill `sala`.

## Regole dure

1. **I tavoli sono quelli della piantina** (`olimpo/piantina.html`). Non si inventano e non spariscono: si dividono
   solo i blocchi con `"separabile": true`, si uniscono solo le unioni con `"stato": "confermata"`. I 29 quadrati
   mobili restano tutti in sala.
2. **Posti**: a un tavolo (unità) non si siedono più persone dei suoi posti.
3. **Un turno, un gruppo per tavolo**: in ogni turno ogni unità ha al più una prenotazione; un'unione esclude i suoi
   tavoli, un blocco intero esclude i suoi pezzi; il lungo ospita un gruppo fino a 20 oppure due gruppi fino a 8
   (il secondo solo se c'è il primo).
4. **Due turni**: 20:00 e 21:30. Il primo lascia il tavolo alle 21:30, il secondo resta fino alla chiusura (24:00).
   Ogni prenotazione sta in un turno e occupa il tavolo per tutto il turno; ogni turno arriva tutto insieme.
5. **Orario → turno**: un orario va nel turno più vicino; a pari distanza (20:45) nel primo. Un orario a più di 45
   minuti da ogni turno (prima delle 19:15, dopo le 22:15) non si registra: si propone il turno più vicino.
6. **Chi prenota prima resta dentro.** Una prenotazione confermata non si toglie né si rifiuta per farne entrare
   un'altra.
7. **Il turno promesso non si cambia** senza chiederlo al proprietario. Se il turno chiesto è pieno si propone
   l'altro, e si registra solo dopo il sì.
8. **Non si dice "pieno" senza dimostrarlo** con i conteggi della skill `sala`; altrimenti si dice "non trovo posto".
9. **Il tavolo si può cambiare** nello stesso turno fino all'ora di cena, ma spostare chi è già confermato è l'ultima
   risorsa (vale più di 10 posti vuoti). Per la serata di oggi non si sposta nessuno senza chiederlo.
10. **Spostare tavoli veri** (attaccare un quadrato a un altro tavolo, spostare un tavolo) è solo una proposta al
    proprietario: solo tavoli mobili (`"fisso": false`), mai nei passaggi (strettoia verso la cucina compresa) né
    davanti a porte e ingresso; conta solo dopo il suo sì (skill `mossa-tavoli`).
11. **Il numero del tavolo non si dice nella conferma** (può ancora cambiare); lo dice il riepilogo, come indicazione.

Con i turni non valgono più i 15 minuti di riapparecchiatura né il limite della cucina di 30 coperti ogni quarto
d'ora: ogni turno arriva tutto insieme.

## Regole di buonsenso (in ordine di priorità)

1. **Accessibilità e sicurezza.** Chi ha difficoltà a camminare, è anziano o è in carrozzina va vicino all'ingresso,
   senza attraversare la sala e mai al tavolo alto 6 (sgabelli). Passeggino e seggiolone mai vicino al percorso dei
   camerieri verso la cucina né lungo il passaggio dei bagni.
2. **Il tavolo giusto per il gruppo.** Meno posti vuoti possibile: una coppia non va a un tavolo da 6 o più se c'è
   altro; un tavolo da 4 per 2 persone va bene se non c'è altro. Il lungo e il tondo da 10 restano per i gruppi grandi.
3. **Pochi lavori in sala.** Poche divisioni di blocchi e poche unioni; poche differenze tra il primo e il secondo
   turno; spostare chi è già confermato solo se serve a far entrare qualcuno.
4. **Tranquillità.** Tavolate e feste (compleanni, gruppi da 8 in su) agli angoli o in fondo, non accanto alle coppie
   dello stesso turno.
5. **Le coppie vicino alle pareti** quando possibile.
6. **Note del cliente.** Le note (compleanno, seggiolone, allergie, "tavolo tranquillo") si riportano sempre nel
   riepilogo e se ne tiene conto quando si sceglie il tavolo.

## Zone della sala (IPOTESI da far confermare al proprietario)

Ricavate dalle coordinate della piantina del 29/10/2026 (il quadrato misura 32 unità = 80 cm; ingresso sul muro
storto in alto a sinistra, tra circa x 160 y 118 e x 248 y 70; porta della cucina a x 142 y 475, in fondo alla
strettoia che parte dall'apertura a x 138-246 y 348; passaggio dei bagni a x 334-416 dal basso fino a y 480).
Le posizioni di 7-12 sono ancora da confermare anche nella piantina.

| zona | tavoli | perché |
|---|---|---|
| vicino all'ingresso | 1, 2, 6, 5, 3 | entro circa 4 m dall'ingresso (6 ha gli sgabelli: non per chi cammina male) |
| centro della sala | 7, 10, 11 | in vista, sul percorso tra l'ingresso e il lato destro |
| lato destro, lungo la curva | 8, 9 | lontani dall'ingresso (7-9 m) ma nella sala principale |
| in fondo o in un angolo | 12, 23, 24, 28, 29 (e 23+28, 24+29) | angolo in alto a destra; fondo della striscia di destra |
| saletta dietro il muro a L | 13A, 13B, 13A+13B, 14-19 | separata dalla sala dal muro a L; ci si arriva dalla strettoia vicino alla porta della cucina |
| contro una parete | 1, 4 (bancone), 12, 14-19, 20-24, 25-29 | muro storto accanto all'ingresso, bancone di sinistra, muro a L, muri della striscia di destra |
| percorso dei camerieri | 3, 4, 13A | vicino all'apertura e alla strettoia verso la porta della cucina |
| passaggio dei bagni | 15, 16, 17, 18, 19 | lungo il passaggio che porta alla porta dei bagni |

Uso nelle regole: per la regola 1 "vicino all'ingresso" = 1, 2, 5, 3 (non 6), e "da evitare" = percorso dei
camerieri, passaggio dei bagni e saletta (ci si passa vicino alla cucina); per la regola 4 prima "in fondo o in un
angolo", poi "saletta", poi "lato destro"; per la regola 5 "contro una parete".

## Come comportarsi

- Se non sei sicuro di cosa intende il proprietario (data, turno, numero di persone, quale prenotazione), chiedi:
  una domanda sola, in fondo. Non indovinare e non inventare.
- Rispondi in breve e ripeti sempre quello che hai capito ("✓ Rossi · 4 persone · sab 31/10 · primo turno (20:00)"),
  così il proprietario si accorge subito di un errore.
- Se una regola di buonsenso non si può rispettare, dillo in una riga ("i Bianchi con il seggiolone sono vicino al
  percorso dei camerieri: era l'unico tavolo libero").
