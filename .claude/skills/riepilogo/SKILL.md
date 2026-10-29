---
name: riepilogo
description: Riepilogo di una serata dell'Olimpo per il proprietario ("riepilogo sab", "com'è messo sabato?", "chi c'è stasera?") — per turno e per tavolo, coperti, tavoli liberi, note, proposte in attesa, rifiutate, e la lista "Da preparare in sala" (blocchi da dividere, unioni da montare, tavolo lungo, cambi alle 21:30). Usala per ogni richiesta di riepilogo o di piantina della serata. Non scrive niente.
---

# Riepilogo di una serata

Non scrive niente. I numeri dei tavoli qui si dicono, ma **come indicazione**: possono ancora cambiare.

1. Ricava la data come nella skill `prenotazione` (punto 2). Leggi il file della serata (skill `stato-serata`) e il
   catalogo (skill `sala`). Se il file non c'è: "Per sab 31/10 non ci sono prenotazioni."
2. Prima di scrivere il riepilogo applica la skill `controllo-serata` (a mente, senza scrivere): se è FAIL, dillo in
   testa al riepilogo con i problemi trovati.

## Formato (righe brevi, si legge sul telefono)

```
Sab 31/10 · tavoli indicativi, possono ancora cambiare

PRIMO TURNO (20:00) · 14 prenotazioni · 52 coperti
- 1 · Rossi ×4
- 5ab · Bianchi ×6 · compleanno
- 11 · Ricci ×18
- …
Liberi: 2, 3, 5c, 6, 10, 13A, 13B, 19, 24, 29 · 41 posti
Posti vuoti ai tavoli occupati: 6

SECONDO TURNO (21:30) · …

Da preparare in sala
- Primo turno: dividi 5 in 5ab (2 quadrati) + 5c; unisci 25 al 20; lungo con un gruppo (Ricci ×18).
- Alle 21:30: riunisci 5; stacca 25 dal 20; lungo con due gruppi (Ferri ×8, Pellegrini ×8).

In attesa di risposta: Verdi ×2 (proposto il secondo turno)
Rifiutate: Neri ×10 (pieni tutti e due i turni)
Annullate: Neri ×2
Cambi di tavolo: Verdi ×7 da 10 a 13A+13B (per far posto a Costa ×10)
```

## Come si calcola

- **Per turno**: le `confermata` di quel turno, una riga per unità nell'ordine del catalogo: `unità · nome ×coperti ·
  note`. Prenotazioni e coperti sono il loro numero e la somma.
- **Liberi**: i tavoli e i pezzi che nessuno usa nel turno. Blocco tutto libero: il suo id ("8"); blocco usato in
  parte: i quadrati liberi ("5c"); un'unione con tutti e due i tavoli liberi: i due tavoli ("24, 29"); lungo con un
  gruppo fino a 8: "11-2". **Posti liberi**: blocco libero intero = i suoi posti; pezzo libero = i posti del pezzo
  (2 quadrati attaccati 6, quadrato da solo 4); lungo libero 20, metà libera 8.
- **Posti vuoti ai tavoli occupati**: somma di (posti dell'unità − coperti); per il lungo, 20 meno tutti i seduti.
- **Da preparare in sala**, per ogni turno, ricavato dalle unità assegnate (le divisioni non sono scritte nel file):
  - blocco diviso: i suoi pezzi = le unità assegnate + i quadrati liberi rimasti ("dividi 8 in 8a + 8bc");
  - unione: "unisci 25 al 20", "unisci 13A e 13B";
  - lungo: "un gruppo (nome ×c)", "due gruppi (nome ×c, nome ×c)" oppure "un gruppo da c, metà libera";
  - mosse `confermata` del turno: il loro `testo`, con "da verificare in sala".
  - **Alle 21:30**: solo ciò che cambia rispetto al primo turno per i blocchi, le unioni e il lungo usati nel secondo
    ("riunisci 5", "dividi 7 in 7a + 7b", "stacca 25 dal 20", "unisci 26 al 21"). Un blocco che nel secondo turno
    non serve resta com'è.
- **In attesa, rifiutate, annullate**: nome ×coperti e, in breve, il motivo, la proposta o la domanda che aspetta
  risposta ("Pellegrino ×4: primo o secondo turno?").
- **Cambi di tavolo**: le righe `cambio tavolo` del registro, in breve.
- Le note dei clienti vanno sempre riportate.
