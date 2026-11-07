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

## Telegram e Cloudflare

- `src/telegram.ts`: legge gli aggiornamenti, risponde, spezza i messaggi lunghi, mostra le domande dell'agente come
  **pulsanti**. Risponde **solo alle chat in `OWNER_CHAT_IDS`** (le altre sono ignorate in silenzio) e **scarta gli
  aggiornamenti già visti** (`update_id`, segnato prima di elaborare, così un rinvio non registra due volte).
- `src/telegram-polling.ts`: bot in long polling per le prove in locale, senza indirizzo pubblico.
- `src/worker.ts` + `src/app.ts` + `wrangler.toml`: Worker che riceve il webhook (controlla il segreto), risponde 200 subito
  e passa l'aggiornamento a un **Durable Object** unico (`Olimpo`, SQLite) che tiene lo stato; `src/coda.ts` fa
  eseguire un messaggio alla volta, così due messaggi non scrivono insieme la stessa serata.
- `scripts/webhook.mjs`: imposta o toglie il webhook di Telegram.

## Uso

```bash
npm install
npm test                      # genera i file dalle fonti e lancia i test
npm run typecheck             # progetto Node + progetto Worker

# prove in locale
OPENROUTER_API_KEY=... npm run chat -- --verbose                      # chat da terminale
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_IDS=<id> OPENROUTER_API_KEY=... npm run telegram

# Cloudflare (piano gratuito)
npx wrangler secret put TELEGRAM_BOT_TOKEN      # idem: TELEGRAM_WEBHOOK_SECRET, OPENROUTER_API_KEY, OWNER_CHAT_IDS
npm run deploy
TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... node scripts/webhook.mjs imposta https://olimpo-agente.<account>.workers.dev/telegram
```

Per le prove in locale con Worker: `.dev.vars` (nel `.gitignore`) con gli stessi nomi dei segreti, poi `npm run dev`.
Il modello si cambia con `OPENROUTER_MODEL` (default `google/gemini-2.5-flash`).

## Stato e limiti

- **Mai provato contro OpenRouter né contro Telegram veri** (nessuna chiave in questa sessione). Provato: 49 test con
  modello e rete finti, e il Worker dentro `wrangler dev` (runtime Cloudflare): 401 senza segreto o con segreto
  sbagliato, 200 con quello giusto. Il nome del modello di default va verificato.
- **Passaggio del cameriere (80 cm): non implementato.** La piantina ora è in scala (quadrato = 32 unità = 80 cm), quindi
  il controllo è fattibile, ma serve sapere cosa si sposta quando si divide un blocco.
- Differenza dal motore CP-SAT: qui un blocco può avere un pezzo usato e il resto vuoto (il motore obbligava a riunire
  il resto); il pezzo vuoto resta libero per un'altra prenotazione.
- `cerca_posto` prova al più **uno spostamento**: non è una ricerca esaustiva, per questo "non trovato" non vuol dire "pieno".
- Il tavolo si indica con il numero della piantina; l'agente dà il link alla piantina (`link_piantina`), non un'immagine.
- Lo stato non ha pulizia: le serate passate restano nello storage del Durable Object.
