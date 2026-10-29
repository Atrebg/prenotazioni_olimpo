---
name: stato-serata
description: Formato del file di stato di una serata dell'Olimpo (serate/AAAA-MM-GG.json, una serata per file) — campi delle prenotazioni, stati, proposte e domande in sospeso, registro degli eventi, mosse di tavoli, e come aggiungere o cambiare righe con Edit senza rompere il JSON. Leggila prima di leggere, creare o modificare un file di serata (anche per le prove in prove/).
---

# Il file di una serata: `serate/AAAA-MM-GG.json`

Una serata = un file, con la data della cena nel nome (es. `serate/2026-10-31.json`). Le prove usano lo stesso
formato in `prove/<etichetta>/AAAA-MM-GG.json`. Se il file non esiste, la serata è vuota: crealo con Write alla
prima scrittura, partendo dallo scheletro qui sotto.

## Scheletro

```json
{
  "serata": "2026-10-31",
  "giorno": "sabato",
  "piantina": {"aggiornata": "29/10/2026", "righe_storico": 17},
  "prenotazioni": [],
  "mosse": [],
  "registro": []
}
```

- `piantina`: data `aggiornata` e numero di righe dello `storico` della piantina usata per assegnare i tavoli. Se
  la piantina di oggi è diversa, vedi la skill `sala` (punto 2) e aggiungi al registro un evento "piantina cambiata".

## Una prenotazione (una riga per prenotazione)

| campo | valore |
|---|---|
| `n` | progressivo d'arrivo nella serata (1, 2, 3…), dato al primo messaggio. Non cambia mai, neanche con una modifica. Nuova = il più alto + 1. |
| `id` | codice del file di prova (rigioca), altrimenti `null` |
| `nome`, `coperti` | come detti dal proprietario; `coperti` può essere `null` solo in una `in_attesa` con `domanda` (dato mancante) |
| `orario` | orario chiesto "HH:MM", oppure `null` se è stato chiesto direttamente un turno o non è stato ancora detto |
| `turno_chiesto` | "primo", "secondo", oppure `null` (orario fuori dai turni, 20:45 senza turno, dato mancante) |
| `turno` | turno **promesso**: "primo" o "secondo" per `confermata`; per `annullata` quello che aveva (`null` se era in attesa); `null` per `in_attesa` e `rifiutata` |
| `stato` | `confermata`, `in_attesa` (aspetta una risposta: a una proposta o a una domanda), `rifiutata`, `annullata` |
| `unita` | unità del catalogo (skill `sala`) solo per `confermata`; `null` negli altri stati |
| `proposta` | `null`, oppure l'ultima proposta fatta: `{"turno": "secondo", "motivo": "primo turno: pieno (dimostrato: …)"}` |
| `domanda` | `null`, oppure il testo della domanda che aspetta risposta ("Primo turno (20:00) o secondo (21:30)?"). Torna `null` quando arriva la risposta. Nei file vecchi senza questo campo vale `null`. |
| `note` | note del cliente ("" se non ce ne sono): compleanno, seggiolone, allergie, "tavolo tranquillo"… |
| `motivo` | perché è `rifiutata`, `annullata` o `in_attesa`; `null` per `confermata` |
| `ricevuta_il` | data (e ora, se la sai) del primo messaggio: "AAAA-MM-GG" o "AAAA-MM-GGTHH:MM"; nelle prove è `prenotata_il` |

**Priorità.** Chi è `confermata` non si toglie mai, qualunque sia il suo `n`. Una `in_attesa` (proposta o domanda)
non occupa tavoli e **non passa davanti a nessuno**: quando arriva la risposta entra solo se in quel momento c'è
posto, senza togliere chi è stato confermato nel frattempo, anche con `n` più alto. Il suo `n` resta l'ordine del
primo messaggio (serve al registro e agli spareggi tra pari), non una precedenza.

**Formato di `motivo`** (e del `motivo` della proposta): una parte per ogni turno provato, nell'ordine in cui li hai
provati, separate da "; ". Esempio con un turno dimostrato e l'altro no: `"secondo turno: pieno (dimostrato: 3 gruppi
da 9 in su, al massimo 2); primo turno: non trovo posto (non dimostrato)"`. Per una proposta non accettata aggiungi
in fondo "; proposta del primo turno non accettata".

Altre regole: una `confermata` arrivata su proposta ha `proposta` non nulla e `turno` uguale al turno proposto. Le
**divisioni dei blocchi non si scrivono**: si ricavano dalle unità assegnate.

## Il registro (una riga per evento, solo in aggiunta, mai riscritto)

Ogni riga: `{"quando": "…", "n": …, "evento": "…", …altri campi…, "testo": "…", "deciso_da": "…"}`. `testo` è una
frase breve per il proprietario (es. "Rossi ×4"). `deciso_da` è il modello che ha preso la decisione e scritto la riga:
"haiku", "sonnet", "opus" (in modalità mista, le righe scritte da `decisore-sala` hanno "sonnet"). Va messo in ogni
riga nuova; nei file vecchi può mancare. Serve a misurare quante decisioni passano a Sonnet. Campi per evento:

| evento | campi in più |
|---|---|
| `domanda` | `testo` = la domanda fatta |
| `confermata` | `turno`, `unita` |
| `proposta` | `turno` (quello proposto), `motivo`; `provati` se un turno non è dimostrato |
| `accettata su proposta` | `turno`, `unita` |
| `rifiutata` | `motivo`; `provati` se un turno non è dimostrato |
| `cambio tavolo` | `turno`, `da`, `a`, `motivo` (per chi si è fatto posto) |
| `modifica` | `turno`, `unita`, `testo` dice cosa è cambiato ("4 → 6 coperti") |
| `annullata` | `turno`, `da` (unità liberata; `null` se era in attesa) |
| `mossa proposta`, `mossa confermata`, `mossa respinta` | `mossa` (id della mossa) al posto di `n` |
| `piantina cambiata` | solo `testo` (e `n`: `null`) |

`provati` è il riassunto di che cosa hai provato prima di dire "non trovo posto" (skill `assegna-tavoli`, "Cosa
scrivere quando non entra").

Il **turno promesso** di una prenotazione è il `turno` dell'ultima riga `confermata`, `accettata su proposta` o
`modifica` con il suo `n`; la sua **unità** è quella dell'ultima riga tra queste e `cambio tavolo` (campo `a`).
Devono coincidere con i campi della prenotazione: `controllo-serata` lo verifica.

## Le mosse (spostamenti veri di tavoli, skill `mossa-tavoli`)

Una riga per mossa: `{"id": "M1", "stato": "proposta", "turni": ["secondo"], "unita": "5+3", "posti": 10,
"usa": ["5a", "5b", "5c", "3"], "testo": "attacca il quadrato 3 in testa al blocco 5", "verifica": "da verificare in sala"}`.
`stato`: `proposta`, `confermata` (il proprietario ha detto sì: solo allora l'unità esiste nei suoi turni),
`respinta`.

## Esempio piccolo e valido

Due cose in sospeso: Verdi aspetta il sì a una proposta, Pellegrino la risposta a una domanda. Un "sì" arrivato
in una sessione nuova qui va chiarito (a quale dei due?). In modalità mista: le righe facili le ha scritte Haiku;
la proposta a Verdi l'ha decisa `decisore-sala` ("sonnet"), perché nel secondo turno il passo 1 non trovava posto.

```json
{
  "serata": "2026-10-31",
  "giorno": "sabato",
  "piantina": {"aggiornata": "29/10/2026", "righe_storico": 17},
  "prenotazioni": [
    {"n": 1, "id": null, "nome": "Rossi", "coperti": 4, "orario": "20:30", "turno_chiesto": "primo", "turno": "primo", "stato": "confermata", "unita": "1", "proposta": null, "domanda": null, "note": "", "motivo": null, "ricevuta_il": "2026-10-29"},
    {"n": 2, "id": null, "nome": "Bianchi", "coperti": 6, "orario": "19:00", "turno_chiesto": null, "turno": "primo", "stato": "confermata", "unita": "12", "proposta": {"turno": "primo", "motivo": "alle 19:00 non c'è un turno"}, "domanda": null, "note": "compleanno", "motivo": null, "ricevuta_il": "2026-10-29"},
    {"n": 3, "id": null, "nome": "Verdi", "coperti": 2, "orario": "23:00", "turno_chiesto": null, "turno": null, "stato": "in_attesa", "unita": null, "proposta": {"turno": "secondo", "motivo": "alle 23:00 non c'è un turno"}, "domanda": null, "note": "", "motivo": "aspetta il sì alla proposta", "ricevuta_il": "2026-10-29"},
    {"n": 4, "id": null, "nome": "Neri", "coperti": 2, "orario": "21:30", "turno_chiesto": "secondo", "turno": "secondo", "stato": "annullata", "unita": null, "proposta": null, "domanda": null, "note": "", "motivo": "annullata dal proprietario", "ricevuta_il": "2026-10-29"},
    {"n": 5, "id": null, "nome": "Pellegrino", "coperti": 4, "orario": "20:45", "turno_chiesto": null, "turno": null, "stato": "in_attesa", "unita": null, "proposta": null, "domanda": "Primo turno (20:00) o secondo (21:30)?", "note": "", "motivo": "aspetta la risposta alla domanda", "ricevuta_il": "2026-10-29"}
  ],
  "mosse": [],
  "registro": [
    {"quando": "2026-10-29", "n": 1, "evento": "confermata", "turno": "primo", "unita": "1", "testo": "Rossi ×4", "deciso_da": "haiku"},
    {"quando": "2026-10-29", "n": 2, "evento": "proposta", "turno": "primo", "motivo": "alle 19:00 non c'è un turno", "testo": "Bianchi ×6: proposto il primo turno (20:00)", "deciso_da": "haiku"},
    {"quando": "2026-10-29", "n": 2, "evento": "accettata su proposta", "turno": "primo", "unita": "12", "testo": "Bianchi ×6", "deciso_da": "haiku"},
    {"quando": "2026-10-29", "n": 3, "evento": "proposta", "turno": "secondo", "motivo": "alle 23:00 non c'è un turno", "testo": "Verdi ×2: proposto il secondo turno (21:30)", "deciso_da": "sonnet"},
    {"quando": "2026-10-29", "n": 4, "evento": "confermata", "turno": "secondo", "unita": "4", "testo": "Neri ×2", "deciso_da": "haiku"},
    {"quando": "2026-10-29", "n": 4, "evento": "annullata", "turno": "secondo", "da": "4", "testo": "Neri ×2", "deciso_da": "haiku"},
    {"quando": "2026-10-29", "n": 5, "evento": "domanda", "testo": "Pellegrino ×4 alle 20:45: primo turno (20:00) o secondo (21:30)?", "deciso_da": "haiku"}
  ]
}
```

## Come scrivere senza rompere il file

Indentazione di 2 spazi; **ogni prenotazione, ogni riga di registro e ogni mossa su una riga sola**, con 4 spazi
davanti, come nell'esempio. Un array vuoto si scrive `[]`. I punti di aggancio per Edit sono questi (unici nel file):

**Aggiungere una prenotazione.** Se `prenotazioni` è vuoto, sostituisci `"prenotazioni": [],` con:

```
"prenotazioni": [
    {"n": 1, …}
  ],
```

Altrimenti sostituisci queste tre righe (la fine dell'ultima prenotazione e l'inizio di `mosse`):

```
}
  ],
  "mosse"
```

con:

```
},
    {"n": 7, …}
  ],
  "mosse"
```

**Aggiungere righe di registro.** Se `registro` è vuoto, sostituisci `"registro": []` con `"registro": [` + a capo
+ le righe + a capo + `  ]`. Altrimenti sostituisci la fine del file:

```
}
  ]
}
```

con:

```
},
    {"quando": …, "evento": "proposta", …, "deciso_da": "sonnet"},
    {"quando": …, "evento": "accettata su proposta", …, "deciso_da": "sonnet"}
  ]
}
```

Più righe aggiunte insieme vanno **separate da virgole**, e l'ultima non ha la virgola. Lo stesso vale per più
prenotazioni.

**Aggiungere una mossa.** Se `mosse` è vuoto, sostituisci `"mosse": [],` con `"mosse": [` + a capo + la riga + a
capo + `  ],`. Altrimenti sostituisci `}` + a capo + `  ],` + a capo + `  "registro"` come per le prenotazioni.

**Cambiare una prenotazione** (stato, unità, turno, coperti, domanda): Edit della sua riga intera, che comincia con
`    {"n": <numero>, ` ed è unica. Non cambiare mai `n` né `ricevuta_il`.

**Rileggere.** Fuori dalla skill `rigioca`: dopo ogni scrittura rileggi il file con Read (JSON valido: virgole tra
gli elementi, nessuna virgola dopo l'ultimo, virgolette doppie). In `rigioca` basta rileggere il file intero ogni 10
prenotazioni, come dice quella skill.
