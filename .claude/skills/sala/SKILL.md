---
name: sala
description: Catalogo dei tavoli dell'Olimpo ricavato dalla piantina (olimpo/piantina.html) — come leggere il blocco JSON della sala, nomi e posti delle unità assegnabili (tavoli, pezzi dei blocchi, unioni, tavolo lungo), quali unità si escludono nello stesso turno, conteggi per soglia per dimostrare un "turno pieno". Usala all'inizio di ogni sessione e ogni volta che devi sapere quali tavoli esistono o quanti posti hanno.
---

# Sala: dalla piantina alle unità assegnabili

La piantina `olimpo/piantina.html` è la **fonte unica** della sala. Non se ne fanno copie e non si modifica:
la cambia solo il proprietario con l'editor. Questo file spiega come leggerla e contiene il catalogo
ricavato il 29/10/2026, come controllo.

## 1. Come leggere la piantina (mai il file intero: è di circa 156 KB)

1. Grep di `id="sala"` in `olimpo/piantina.html` con i numeri di riga: prendi la **prima** riga trovata (la seconda è
   dentro il programma dell'editor e non serve).
2. Read dello stesso file con `offset` = quella riga e `limit` = 115. Il blocco finisce alla prima riga `</script>`:
   se non la vedi, leggi altre 50 righe da dove eri arrivato.
3. Campi che servono: `aggiornata`, `turni`, `posti_quadrato_separato`, `tavoli` (`id`, `tipo`, `posti`, `moduli`,
   `fisso`, `separabile`, `note`), `unioni` (solo quelle con `"stato": "confermata"`), `storico` (quante righe e
   l'ultima). `passaggi`, `porte`, `ingresso` e le coordinate servono solo alla skill `mossa-tavoli` e alle zone di
   `agente/regole.md`.

## 2. Controllo della versione

Il catalogo qui sotto vale per la piantina con **`"aggiornata": "29/10/2026"`, 17 righe di `storico`, l'ultima che
comincia con "29/10/2026 · 13A e 13B si uniscono in un tavolo da 8"**, 30 tavoli, 141 posti con i blocchi interi.

- Se la piantina letta è uguale: usa il catalogo del punto 4.
- Se è diversa (data, numero di righe dello storico, tavoli, posti, unioni o `separabile`): **vale la piantina**.
  Ricalcola le unità con le regole del punto 3 e i conteggi con il punto 6, usa quelli e dillo al proprietario in una
  riga ("La piantina è cambiata il …: ho ricalcolato i tavoli."). Se un'unità già assegnata in una serata non esiste
  più o ha meno posti dei coperti, segnalalo e non spostare nessuno senza chiedere.

## 3. Regole per ricavare le unità

Un'**unità** è ciò a cui si assegna una prenotazione in un turno. Ogni unità "usa" dei **pezzi** fisici; due unità
che usano almeno un pezzo in comune **non possono stare nello stesso turno**.

- **Tavolo semplice** (`panca`, `rettangolare`, `tondo`, `quadrato`): unità = il suo `id`, posti = `posti`, usa sé stesso.
- **Blocco con `"separabile": false`**: un'unità sola, il suo `id`, con i suoi `posti`. Non si divide mai.
- **Blocco con `"separabile": true`** di `moduli` quadrati, chiamati a, b, c nell'ordine dei moduli (quale sia "a"
  in sala lo decide il proprietario: è solo un nome):
  - intero = `id` (es. "5"), posti del blocco, usa tutti i quadrati;
  - pezzo contiguo di j ≥ 2 quadrati, non intero = `id` + lettere (es. "5ab", "5bc"), posti **2j + 2**;
  - quadrato da solo = `id` + lettera (es. "5a"), posti = `posti_quadrato_separato` (oggi 4);
  - pezzi non contigui ("5ac") non esistono.
  - Un **taglio** è un punto in cui il blocco si stacca: in un blocco da 3 ci sono i tagli a|b e b|c, in uno da 2
    solo a|b. Ogni unità richiede i tagli ai suoi bordi interni (vedi tabella): "5ab" richiede b|c, "5b" richiede a|b
    e b|c, "5" nessuno. La **divisione** di un blocco in un turno = i tagli richiesti dalle unità assegnate lì; non
    si scrive da nessuna parte, si ricava. Può cambiare tra un turno e l'altro.
- **Tavolo lungo** (`tipo` "lungo"): o un gruppo solo fino ai suoi posti, o due gruppi fino a 8 ciascuno (lo dice la
  sua nota). Unità: "11" (un gruppo, usa 11-1 e 11-2), "11-1" (primo di due gruppi, usa la metà 11-1), "11-2"
  (secondo gruppo, usa la metà 11-2, **solo se 11-1 è occupato**). Convenzione: un gruppo fino a 8 va su "11-1" o
  "11-2", mai su "11"; un gruppo da 9 in su solo su "11".
- **Unione confermata** (`unioni` con `"stato": "confermata"`): unità "A+B" (es. "20+25"), con i `posti`
  dell'unione, usa tutti i pezzi di A e di B. Nello stesso turno o l'unione o i suoi tavoli, mai le due cose. Le unioni
  "proposta" o "no" non si usano.
- **Mosse confermate** dal proprietario (skill `mossa-tavoli`): aggiungono un'unità solo nei turni scritti nella mossa.
- **I tavoli non spariscono**: si dividono (blocchi separabili) o si uniscono (unioni). I quadrati mobili sono 29 e
  restano tutti in sala.

## 4. Catalogo (piantina del 29/10/2026)

L'ordine delle righe è l'**ordine del catalogo**, l'ultimo spareggio di `assegna-tavoli`.

| unità | posti | usa (pezzi) | tagli richiesti | cos'è |
|---|---|---|---|---|
| 1 | 4 | 1 | – | panca fissa |
| 2 | 4 | 2 | – | panca fissa |
| 3 | 2 | 3 | – | quadrato mobile |
| 4 | 2 | 4 | – | quadrato mobile |
| 5 | 8 | 5a 5b 5c | nessuno (blocco intero) | blocco mobile di 3 quadrati, separabile |
| 5ab | 6 | 5a 5b | b\|c | pezzo da 2 quadrati |
| 5bc | 6 | 5b 5c | a\|b | pezzo da 2 quadrati |
| 5a | 4 | 5a | a\|b | quadrato staccato |
| 5b | 4 | 5b | a\|b, b\|c | quadrato staccato |
| 5c | 4 | 5c | b\|c | quadrato staccato |
| 6 | 3 | 6 | – | tondo alto fisso, 3 sgabelli |
| 7 | 6 | 7a 7b | nessuno (blocco intero) | blocco mobile di 2 quadrati, separabile |
| 7a | 4 | 7a | a\|b | quadrato staccato |
| 7b | 4 | 7b | a\|b | quadrato staccato |
| 8 | 8 | 8a 8b 8c | nessuno (blocco intero) | blocco mobile di 3 quadrati, separabile |
| 8ab | 6 | 8a 8b | b\|c | pezzo da 2 quadrati |
| 8bc | 6 | 8b 8c | a\|b | pezzo da 2 quadrati |
| 8a | 4 | 8a | a\|b | quadrato staccato |
| 8b | 4 | 8b | a\|b, b\|c | quadrato staccato |
| 8c | 4 | 8c | b\|c | quadrato staccato |
| 9 | 6 | 9 | – | blocco di 2 quadrati, non si divide |
| 10 | 10 | 10 | – | tondo grande fisso |
| 11 | 20 | 11-1 11-2 | – | lungo fisso, un gruppo da 9 a 20 |
| 11-1 | 8 | 11-1 | – | lungo, primo di due gruppi (fino a 8) |
| 11-2 | 8 | 11-2 | – | lungo, secondo gruppo (fino a 8), solo con 11-1 occupato |
| 12 | 6 | 12 | – | blocco di 2 quadrati, non si divide |
| 13A | 4 | 13A | – | rettangolare fisso |
| 13B | 4 | 13B | – | rettangolare fisso |
| 13A+13B | 8 | 13A 13B | – | unione confermata |
| 14, 15, 16, 17, 18, 19 | 4 ciascuna | sé stessa | – | panche fisse |
| 20, 21, 22, 23, 24 | 4 ciascuno | sé stesso | – | blocchi di 2 quadrati contro il muro, non si dividono |
| 25, 26, 27, 28, 29 | 2 ciascuno | sé stesso | – | quadrati mobili contro il muro di destra |
| 20+25 | 6 | 20 25 | – | unione confermata |
| 21+26 | 6 | 21 26 | – | unione confermata |
| 22+27 | 6 | 22 27 | – | unione confermata |
| 23+28 | 6 | 23 28 | – | unione confermata |
| 24+29 | 6 | 24 29 | – | unione confermata |

Controlli rapidi: 30 tavoli; 141 posti per turno con i blocchi interi e senza unioni; 151 posti al massimo con 5, 7
e 8 divisi in quadrati e un gruppo solo al lungo. Quadrati mobili: 3, 4, 25-29 (7) + 5 (3) + 7 (2) + 8 (3) + 9 (2) +
12 (2) + 20-24 (2 ciascuno, 10) = **29**.

Esempi di esclusività nello stesso turno: "5" esclude 5ab, 5bc, 5a, 5b, 5c; "5ab" esclude 5, 5bc, 5a, 5b ma non 5c;
"11" esclude 11-1 e 11-2; "20+25" esclude 20 e 25; "13A+13B" esclude 13A e 13B.

## 5. Posti vuoti di un'unità

Per un gruppo di c persone: posti vuoti = posti dell'unità − c. Eccezione del lungo: su "11" e su "11-1" (con 11-2
libero) sono **20 − c**, perché il tavolo lungo è apparecchiato tutto per quel gruppo (un gruppo da 8 da solo lascia
12 posti vuoti, quindi va a un blocco da 8 se è libero); su "11-2" sono 8 − c (gli altri posti vuoti del lungo sono
già contati con 11-1).

## 6. Conteggi per soglia (per dimostrare un "turno pieno")

Per ogni turno: le prenotazioni da **almeno s coperti** non possono essere più delle unità da almeno s posti che
possono esserci **insieme** (scegliendo le divisioni migliori). Se un conteggio è superato, il turno è pieno ed è
dimostrato.

| famiglia di pezzi | ≤ 2 | 3 | 4 | 5-6 | 7-8 | 9-10 | 11-20 |
|---|---|---|---|---|---|---|---|
| panche 1, 2, 14-19 (8 tavoli) | 8 | 8 | 8 | 0 | 0 | 0 | 0 |
| 13A, 13B, 13A+13B | 2 | 2 | 2 | 1 | 1 | 0 | 0 |
| 6 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 10 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| 11 | 2 | 2 | 2 | 2 | 2 | 1 | 1 |
| 3, 4 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | 3 | 3 | 3 | 1 | 1 | 0 | 0 |
| 8 | 3 | 3 | 3 | 1 | 1 | 0 | 0 |
| 7 | 2 | 2 | 2 | 1 | 0 | 0 | 0 |
| 9 | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| 12 | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| 20+25 … 24+29 (5 coppie) | 10 | 5 | 5 | 5 | 0 | 0 | 0 |
| **totale per turno** | **36** | **29** | **28** | **14** | **6** | **2** | **1** |

- Da 21 coperti in su: 0 unità, non entra mai.
- **Lungo con un gruppo da 9 in su**: per quel turno il lungo vale una sola unità, quindi togli 1 ai totali delle
  colonne da ≤ 2 a 7-8 (35, 28, 27, 13, 5). Applicalo solo quando è obbligato: c'è un gruppo da 11 in su, oppure ci
  sono almeno due gruppi da 9 in su.
- **Posti**: la somma dei coperti del turno non può superare 151.
- Come si legge: "s = 5-6" vale per le prenotazioni da 5 coperti in su; "s = 7-8" da 7 in su; e così via.

Se la piantina cambia, rifai la tabella: per ogni famiglia di pezzi che si escludono a vicenda (un tavolo, un blocco
con i suoi pezzi, un'unione con i suoi due tavoli, il lungo) conta quante unità da almeno s posti possono esserci
insieme, e somma.
