// Il giro dell'agente: messaggio del proprietario -> il modello chiama gli strumenti -> risposta. Un tetto ai giri.
import { REGOLE } from "./generato/regole";
import { calendario, dataLocale, oraLocale } from "./orari";
import type { Sala } from "./sala";
import type { Store } from "./store";
import { ErroreStrumento, STRUMENTI, type Contesto, type Strumento } from "./strumenti";

export interface ChiamataStrumento {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface MessaggioModello {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
  tool_calls?: ChiamataStrumento[];
  tool_call_id?: string;
}

export type ChiamaModello = (messaggi: MessaggioModello[], strumenti: Strumento[]) => Promise<MessaggioModello>;

export interface Dipendenze {
  sala: Sala;
  store: Store;
  chiama: ChiamaModello;
  adesso?: () => Date;
  maxGiri?: number;
  storiaMax?: number;
  scadenzaBozzaMin?: number;
  /** Chiamato a ogni strumento eseguito (log). */
  traccia?: (evento: { strumento: string; args: unknown; esito: unknown }) => void;
}

export const MSG_ERRORE = "Non sono riuscito a rispondere (errore tecnico). Riprova tra poco, oppure scrivi nel formato breve: Rossi 4 sab 20:30.";
export const MSG_TROPPI_GIRI = "Non sono riuscito a chiudere la richiesta. Non ho scritto nulla; riscrivila per intero e riprovo.";

export function promptSistema(sala: Sala, adesso: Date, bozza?: string, bozzaScaduta?: boolean): string {
  const oggi = dataLocale(adesso);
  return `Sei l'assistente di sala del ristorante Olimpo. Parli in italiano, in modo breve e chiaro, con il proprietario, che ti scrive in chat.
Oggi è ${oggi}, ore ${oraLocale(adesso)}. Calendario (usa queste date, non calcolarle):
${calendario(oggi)}

Turni: ${sala.turni.map((t, i) => `${i + 1} = ${t.nome} ${t.inizio}`).join(", ")}. Un orario va nel turno più vicino (a parità il primo).

COSA FAI
- Gestisci prenotazioni e sala usando SOLO gli strumenti. Il codice controlla le regole dure e rifiuta i piani non ammessi: se uno strumento risponde con un errore, quello è definitivo, spiegalo e proponi un'alternativa. Non aggirarlo.
- Decidi tu dove sedere la gente, ma prova sempre prima con cerca_posto. Non fare conti a mano sui posti.
- Non dire mai che un turno è "pieno" se cerca_posto non risponde dimostrato_pieno=true. Altrimenti di': "non ho trovato posto".
- Se il turno chiesto è pieno e l'altro ha posto, PROPONI l'altro turno e registra solo dopo il sì del cliente (che ti riporta il proprietario).
- Un orario lontano dai turni (turno_per_orario: lontano) non si registra senza il sì: proponi il turno più vicino.
- Non indovinare mai. Se data, orario/turno, numero di persone o quale prenotazione non sono chiari, fai UNA domanda sola, in fondo al messaggio, con le opzioni concrete, e salva la bozza con memorizza_bozza. Non scrivere nulla (registra, annulla, modifica, fissa) finché la domanda ha una risposta.
- Gli ordini del proprietario sulla sala ("mettimi Rossi al 21", "dividi questo tavolo così e mettici Rossi") si eseguono con "fissa" quando sono chiari e rispettano le regole dure. Per gli ordini composti o ambigui: ripeti l'ordine intero ("Divido il 21 in 2+1 per il primo turno e metto Rossi nel pezzo da 2: confermo?") e aspetta il sì. Il buonsenso lo decide il proprietario: se un suo ordine lo viola, eseguilo e dillo in una riga.
- Per far capire un riferimento ("questo tavolo") chiedi il numero del tavolo; usa "piantina" per i nomi dei posti. Se serve, elenca i numeri.
- Cambiare il turno di una prenotazione già accettata tocca il cliente: chiedi conferma esplicita al proprietario.
- Quando confermi una prenotazione non dire il numero del tavolo: può ancora cambiare. Il tavolo lo dici solo nel riepilogo o se il proprietario lo chiede.
- Non annullare, modificare o fissare nulla se il proprietario non l'ha chiesto.

COME RISPONDI
- Ripeti prima quello che hai capito, con la riga di conferma dello strumento (es. "✓ Rossi · 4 persone · sab 31/10 · primo turno (20:00)"), poi l'esito.
- In una riga segnala le regole di buonsenso non rispettate. Se non c'è niente da segnalare, non scrivere niente.
- Risposte brevi. Se uno strumento fallisce o l'esito non è chiaro, dillo com'è.

${bozza ? `BOZZA IN SOSPESO (la tua domanda precedente al proprietario; il suo messaggio ne è la risposta, a meno che parli d'altro):\n${bozza}\n` : ""}${bozzaScaduta ? "La bozza precedente è scaduta: non è stato scritto nulla, ripartire da quello che dice ora il proprietario.\n" : ""}
REGOLE DEL RISTORANTE
${REGOLE}`;
}

function esito(e: unknown): string {
  return JSON.stringify(e);
}

export async function gestisciMessaggio(dip: Dipendenze, mittente: string, testo: string): Promise<string> {
  const adesso = dip.adesso ?? (() => new Date());
  const maxGiri = dip.maxGiri ?? 8;
  const storiaMax = dip.storiaMax ?? 12;
  const scadenzaMs = (dip.scadenzaBozzaMin ?? 15) * 60_000;
  const ctx: Contesto = { sala: dip.sala, store: dip.store, adesso, mittente };

  const conv = await dip.store.conversazione(mittente);
  let bozzaTesto: string | undefined;
  let scaduta = false;
  const bozzaScadutaDel = conv.bozza?.creata_il;
  if (conv.bozza) {
    if (adesso().getTime() - Date.parse(conv.bozza.creata_il) > scadenzaMs) {
      scaduta = true;
    } else {
      bozzaTesto = JSON.stringify({ azione: conv.bozza.azione, dettagli: conv.bozza.dettagli, mancano: conv.bozza.mancano, domanda: conv.bozza.domanda });
    }
  }

  const messaggi: MessaggioModello[] = [
    { role: "system", content: promptSistema(dip.sala, adesso(), bozzaTesto, scaduta) },
    ...conv.storia.map((m) => ({ role: m.role, content: m.content }) as MessaggioModello),
    { role: "user", content: testo },
  ];

  let risposta = MSG_TROPPI_GIRI;
  try {
    for (let giro = 0; giro < maxGiri; giro++) {
      const m = await dip.chiama(messaggi, STRUMENTI);
      messaggi.push({ role: "assistant", content: m.content ?? null, ...(m.tool_calls?.length ? { tool_calls: m.tool_calls } : {}) });
      if (!m.tool_calls?.length) {
        risposta = (m.content ?? "").trim() || MSG_ERRORE;
        break;
      }
      for (const c of m.tool_calls) {
        const s = STRUMENTI.find((x) => x.name === c.function.name);
        let args: unknown = {};
        let uscita: unknown;
        try {
          if (!s) throw new ErroreStrumento(`strumento sconosciuto: ${c.function.name}`);
          try {
            args = JSON.parse(c.function.arguments || "{}");
          } catch {
            throw new ErroreStrumento("argomenti non validi (JSON)");
          }
          uscita = await s.esegui(args, ctx);
        } catch (e) {
          if (e instanceof ErroreStrumento) uscita = { errore: e.message };
          else throw e;
        }
        dip.traccia?.({ strumento: c.function.name, args, esito: uscita });
        messaggi.push({ role: "tool", tool_call_id: c.id, content: esito(uscita) });
      }
    }
  } catch (e) {
    dip.traccia?.({ strumento: "(errore)", args: {}, esito: String(e) });
    return MSG_ERRORE;
  }

  // la storia tiene solo il testo scambiato: gli stati veri stanno negli strumenti
  const dopo = await dip.store.conversazione(mittente); // le bozze scritte dagli strumenti
  dopo.storia = [...conv.storia, { role: "user" as const, content: testo }, { role: "assistant" as const, content: risposta }].slice(-storiaMax);
  if (scaduta && dopo.bozza?.creata_il === bozzaScadutaDel) delete dopo.bozza; // quella scaduta se ne va, una nuova resta
  await dip.store.salvaConversazione(mittente, dopo);
  return risposta;
}
