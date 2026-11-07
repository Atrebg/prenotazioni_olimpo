# Harness dell'agente di sala (senza solver)

L'agente (un modello via OpenRouter) gestisce prenotazioni e sala chiamando degli **strumenti**; il codice controlla le
regole dure e scrive lo stato solo se il piano del turno è ammesso. Sostituisce il motore CP-SAT per la sala vera.

## Come funziona

- `src/sala.ts`: la sala letta dalla piantina (`../olimpo/piantina.html`, unica fonte), tavoli, pezzi dei blocchi, tavolo lungo.
- `src/validatore.ts`: regole dure per un turno (posti, un solo gruppo per posto, lungo 20 oppure 8+8, pezzi dei blocchi
  contigui e senza sovrapposizioni), punteggio (posti vuoti ×10, divisioni dei blocchi ×4) e dimostrazione di "turno
  pieno" per conteggio.
- `src/strumenti.ts`: `piantina`, `turno_per_orario`, `stato_serata`, `riepilogo`, `cerca_posto`, `verifica_piano`,
  `registra`, `annulla`, `modifica`, `fissa`, `libera`, `memorizza_bozza`, `cancella_bozza`.
- `src/agente.ts`: il giro messaggio → strumenti → risposta (tetto di 8 giri), storia breve, bozza in sospeso che scade
  dopo 15 minuti. Il prompt include le regole di `../agente/regole.md`.
- `src/openrouter.ts`: client OpenRouter (fetch). `src/store.ts` (memoria) e `src/store-file.ts` (file JSON, prove locali).

Regole che il codice fa rispettare, qualunque cosa dica il modello: nessuna scrittura se il piano non passa il
validatore; una prenotazione fissata dal proprietario non si sposta da un riordino; cambiare turno richiede il sì del
cliente; "pieno" è dimostrato solo se lo dice `cerca_posto` (`dimostrato_pieno`); data non passata ed entro 90 giorni.

## Uso

```bash
npm install
npm test                      # genera i file dalle fonti e lancia i test
OPENROUTER_API_KEY=... npm run chat -- --verbose      # modello: OPENROUTER_MODEL (default google/gemini-2.5-flash)
```

## Stato e limiti

- **Mai provato contro OpenRouter** (nessuna chiave in questa sessione): i test usano un modello e un `fetch` finti.
  Il nome del modello di default va verificato.
- **Passaggio del cameriere (80 cm): non implementato.** Richiede un controllo geometrico sulle misure della piantina.
- Differenza dal motore CP-SAT: qui un blocco può avere un pezzo usato e il resto vuoto (il motore obbligava a riunire
  il resto); il pezzo vuoto resta libero per un'altra prenotazione.
- `cerca_posto` prova al più **uno spostamento**: non è una ricerca esaustiva, per questo "non trovato" non vuol dire "pieno".
- Mancano: bot Telegram (long polling e webhook), store D1 / Durable Object per Cloudflare, invio della piantina numerata,
  scarto dei messaggi duplicati (`update_id`).
