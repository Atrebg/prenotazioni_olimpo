---
name: disponibilita
description: Risponde alle domande del proprietario dell'Olimpo del tipo "c'è posto per N sabato alle 21?", "come siamo messi venerdì per un gruppo da 12?" senza registrare niente e senza scrivere file. Usala per ogni domanda sulla disponibilità che non chiede di prenotare.
---

# Disponibilità: "c'è posto per N …?" senza scrivere niente

**Non si scrive nessun file**, nemmeno il registro. Se il proprietario poi dice "allora prenota", è una nuova
prenotazione (skill `prenotazione`) e si rifà tutto da capo.

1. Ricava coperti, data e orario o turno come nella skill `prenotazione` (punti 2 e 3). Se manca il numero di
   persone o la data, chiedilo. Se manca l'orario, rispondi per tutti e due i turni.
2. Leggi il file della serata (se non c'è, la serata è vuota) e il catalogo (skill `sala`).
3. Per ogni turno da controllare applica la skill `assegna-tavoli` **a mente**, fino al passo 3 compreso. Le
   `in_attesa` non occupano tavoli.
4. Rispondi in una o due righe, senza numeri di tavolo:
   - entra senza spostare nessuno: "Sì: nel secondo turno (21:30) c'è posto per 4.";
   - entra solo spostando chi è già confermato: "Sì, nel secondo turno (21:30), cambiando di tavolo una prenotazione
     già confermata.";
   - PIENO dimostrato: "No: il secondo turno è pieno per 4." e, se l'altro turno ha posto, "Nel primo (20:00) sì.";
   - non dimostrato: "Nel secondo turno non trovo posto per 4." (mai "pieno").
5. Se ci sono `in_attesa` per quel turno (proposte o domande), aggiungi una riga: "C'è anche una richiesta in attesa
   di risposta (Verdi ×2): se dice sì, il posto si riduce."
6. Aggiungi sempre: "Non ho registrato niente."
