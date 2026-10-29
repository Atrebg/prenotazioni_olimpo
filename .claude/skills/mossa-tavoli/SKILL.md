---
name: mossa-tavoli
description: Proposte di spostamenti veri dei tavoli mobili dell'Olimpo (attaccare un quadrato a un blocco, spostare un tavolo) quando un gruppo verrebbe rifiutato in tutti e due i turni — regole (solo tavoli mobili, 29 quadrati sempre in sala, mai in passaggi, porte e ingresso, posti 2k+2), come proporla, come registrarla dopo il sì del proprietario. Usala solo dopo un rifiuto nei due turni o se il proprietario chiede come far entrare un gruppo.
---

# Mosse: spostare tavoli veri (solo come proposta)

Una mossa cambia la sala per un turno, quindi **la decide il proprietario**. Finché non dice sì in modo esplicito,
non conta: nessuna prenotazione si mette su una mossa `proposta`. Nella skill `rigioca` le mosse non si applicano
mai: lì si scrive solo "mossa possibile: …" nell'esito.

## Regole

1. **Solo tavoli mobili** (`"fisso": false` nella piantina): quadrati 3, 4, 25-29 e blocchi 5, 7, 8, 9, 12, 20-24.
   Panche, 6, 10, 11, 13A e 13B non si muovono.
2. **I 29 quadrati restano in sala**: si attaccano o si spostano, non si tolgono.
3. **Mai nei passaggi** (`passaggi` della piantina: passaggio, apertura, strettoia verso la cucina) e **mai davanti
   a porte e ingresso** (`porte`, `ingresso`: lasciano 90 cm liberi, cioè 36 unità del disegno).
4. **Posti**: k quadrati in fila = **2k + 2**. IPOTESI: una testa contro un muro o un altro tavolo non ha la sedia
   (come i 20-24, che hanno 4 posti): allora 2k + 1, o 2k con tutte e due le teste chiuse. Lo verifica il proprietario.
5. I tavoli della mossa devono essere **liberi per tutto il turno** della mossa. Se nell'altro turno servono al loro
   posto, la mossa vale per un turno solo e si disfa (o si fa) alle 21:30: scrivilo.
6. Ogni mossa è **"da verificare in sala"**: le posizioni della piantina sono in parte stimate.

## Procedura

1. Il gruppo di c persone non entra in nessuno dei due turni (o il proprietario chiede come farlo entrare).
2. Per ogni turno, cerca tra le unità **libere** una combinazione di pezzi mobili da mettere in fila con almeno c
   posti (regola 4), preferendo nell'ordine:
   - meno pezzi da muovere (un quadrato da attaccare in testa a un blocco è la mossa più piccola);
   - pezzi già vicini (stessa zona di `agente/regole.md`);
   - pezzi che nell'altro turno non servono al loro posto.
   Esempi: per 10 persone, il blocco 5 (3 quadrati) più un quadrato libero in testa = 4 quadrati = 10 posti; il
   blocco 7 (2 quadrati) più due quadrati = 10 posti.
3. Controlla il posto: leggi `passaggi`, `porte` e `ingresso` nel blocco della piantina (skill `sala`, punto 1) e
   scrivi dove andrebbe il pezzo ("in testa al blocco 5, dal lato del 6"). Se quella zona tocca un passaggio o i 90 cm
   davanti a una porta o all'ingresso, scarta la mossa. Se non riesci a dirlo dalle coordinate, scrivilo nella
   proposta.
4. Nessuna mossa trovata: il rifiuto resta, e non proporre niente.
5. Mossa trovata: proponila con una domanda sola: "Neri ×10 non entra in nessuno dei due turni. Si potrebbe, nel
   secondo turno, attaccare il quadrato 3 in testa al blocco 5: 4 quadrati in fila, 10 posti (da verificare in sala).
   La faccio?". Nel file (skill `stato-serata`):
   - una riga in `mosse` con `"stato": "proposta"`, i `turni`, l'`unita` (es. "5+3"), i `posti`, i pezzi in `usa`,
     il `testo` e `"verifica": "da verificare in sala"`; registro `mossa proposta`;
   - la prenotazione resta `in_attesa`, con `proposta` = `{"turno": …, "mossa": "M1", "motivo": …}`.
6. **Sì** del proprietario: la mossa diventa `confermata` (registro `mossa confermata`); da ora l'unità esiste nei
   suoi turni e usa i suoi pezzi. Poi `assegna-tavoli` per il gruppo: se entra, `confermata` (registro `accettata su
   proposta`). **No**: mossa `respinta` (registro `mossa respinta`) e prenotazione `rifiutata`.
7. Il riepilogo riporta la mossa in "Da preparare in sala", con "da verificare in sala".
