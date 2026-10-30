---
name: sala
description: Regole della sala dell'Olimpo dalla piantina (olimpo/piantina.html) — lettura del blocco JSON, unità assegnabili (tavoli, pezzi dei blocchi, unioni, tavolo lungo) e loro esclusività, posti vuoti, conteggi per soglia per un "turno pieno", rigenerazione di agente/catalogo.md. Usala all'inizio di ogni sessione e quando ti servono tavoli o posti.
---

# Sala: dalla piantina alle unità assegnabili

La piantina `olimpo/piantina.html` è la **fonte unica** della sala. Non se ne fanno copie e non si modifica:
la cambia solo il proprietario con l'editor. Unità, soglie e liste ricavate con le regole di questo file sono in
`agente/catalogo.md`.

## 1. Come leggere la piantina (mai il file intero: è di circa 156 KB)

1. Grep di `id="sala"` in `olimpo/piantina.html` con i numeri di riga: prendi la **prima** riga trovata (la seconda è
   dentro il programma dell'editor e non serve).
2. Read dello stesso file con `offset` = quella riga e `limit` = 115. Il blocco finisce alla prima riga `</script>`:
   se non la vedi, leggi altre 50 righe da dove eri arrivato.
3. Campi che servono: `aggiornata`, `turni`, `posti_quadrato_separato`, `tavoli` (`id`, `tipo`, `posti`, `moduli`,
   `fisso`, `separabile`, `note`), `unioni` (solo quelle con `"stato": "confermata"`), `storico` (quante righe e
   l'ultima). `passaggi`, `porte`, `ingresso` e le coordinate servono solo alla skill `mossa-tavoli` e alle zone di
   `agente/regole.md`.

## 2. Versione del catalogo

In testa al catalogo c'è la versione della piantina da cui è calcolato. Piantina uguale: usa il catalogo. Diversa
(data, righe dello storico, ultima riga, oppure tavoli, posti, unioni o `separabile` che non tornano con il
catalogo): **vale la piantina** e il catalogo va rigenerato.
- Lo rigenera una sessione Sonnet o superiore, con le regole dei punti 3-5 (le liste con quelle di `assegna-tavoli`
  e `mossa-tavoli`); lo scrive con Write e lo dice al proprietario in una riga ("La piantina è cambiata il …: ho
  ricalcolato i tavoli.").
- Haiku non rigenera: passa il messaggio a `decisore-sala`. La skill `rigioca` rigenera prima di cominciare.
- Se un'unità già assegnata in una serata non esiste più o ha meno posti dei coperti, segnalalo e non spostare
  nessuno senza chiedere.

## 3. Regole per ricavare le unità

Un'**unità** è ciò a cui si assegna una prenotazione in un turno. Ogni unità "usa" dei **pezzi** fisici; due unità
che usano almeno un pezzo in comune **non possono stare nello stesso turno**.

- **Tavolo semplice** (`panca`, `rettangolare`, `tondo`, `quadrato`): unità = il suo `id`, posti = `posti`, usa sé stesso.
- **Blocco con `"separabile": false`**: un'unità sola, il suo `id`, con i suoi `posti`. Non si divide mai.
- **Blocco con `"separabile": true`** di `moduli` quadrati, chiamati a, b, c nell'ordine dei moduli (sono solo
  nomi):
  - intero = `id`, posti del blocco, usa tutti i quadrati;
  - pezzo contiguo di j ≥ 2 quadrati, non intero = `id` + lettere, posti **2j + 2**;
  - quadrato da solo = `id` + lettera, posti = `posti_quadrato_separato`;
  - pezzi non contigui (a con c) non esistono.
  - Un **taglio** è un punto in cui il blocco si stacca (a|b, b|c). Ogni unità richiede i tagli ai suoi bordi
    interni (es. "5ab" richiede b|c, "5b" a|b e b|c, "5" nessuno). La **divisione** di un blocco in un turno = i
    tagli richiesti dalle unità assegnate lì; non si scrive, si ricava. Può cambiare tra un turno e l'altro.
- **Tavolo lungo** (`tipo` "lungo"): o un gruppo solo fino ai suoi posti, o due gruppi, ognuno fino ai posti di una
  metà scritti nella sua nota. Unità: "`<id>`" (un gruppo, usa le due metà), "`<id>`-1" (primo di due gruppi, usa
  la prima metà), "`<id>`-2" (secondo gruppo, usa la seconda metà, **solo se `<id>`-1 è occupato**).
- **Unione confermata** (`unioni` con `"stato": "confermata"`): unità "A+B", con i `posti` dell'unione, usa tutti i
  pezzi di A e di B. Nello stesso turno o l'unione o i suoi tavoli, mai le due cose. Le unioni "proposta" o "no" non
  si usano.
- **Mosse confermate** dal proprietario (skill `mossa-tavoli`): aggiungono un'unità solo nei turni scritti nella mossa.
- **I tavoli non spariscono**: si dividono (blocchi separabili) o si uniscono (unioni). I quadrati mobili restano
  tutti in sala.
- **Ordine del catalogo**: come nella piantina, ogni tavolo seguito dai suoi pezzi (dal più lungo) o dalle sue metà,
  le unioni dopo i loro tavoli.

## 4. Posti vuoti di un'unità

Per un gruppo di c persone: posti vuoti = posti dell'unità − c. Eccezione del lungo: sull'intero e sulla prima metà
sono i **posti del lungo − c**, perché è apparecchiato tutto per quel gruppo; sulla seconda metà, i posti di una
metà − c.

## 5. Conteggi per soglia (per dimostrare un "turno pieno")

Per ogni turno: le prenotazioni da **almeno s coperti** non possono essere più delle unità da almeno s posti che
possono esserci **insieme** (scegliendo le divisioni migliori). Se un conteggio è superato, il turno è pieno ed è
dimostrato. I totali sono nel catalogo: per ogni famiglia di pezzi che si escludono a vicenda (un tavolo, un blocco
con i suoi pezzi, un'unione con i suoi due tavoli, il lungo) si conta quante unità da almeno s posti possono esserci
insieme, e si somma; una colonna per ogni numero di posti delle unità.
- **Lungo a un gruppo**: il lungo vale una sola unità, quindi togli 1 alle colonne fino ai posti di una metà. Solo
  quando è obbligato: per una soglia s più grande di una metà, i gruppi da almeno s sono più delle unità da almeno s
  posti, fuori dal lungo, che possono esserci insieme.
- **Posti**: la somma dei coperti del turno non supera i posti massimi (ogni famiglia con la scelta più capiente).
