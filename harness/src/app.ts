// Il pezzo che sta tra Cloudflare e l'agente, senza tipi di Cloudflare così si prova in locale.
import { Coda } from "./coda";
import { ChiaveValoreStore, type ChiaveValore } from "./dostore";
import { clientOpenRouter } from "./openrouter";
import { Sala, type DatiSala } from "./sala";
import { elencoChat, gestisciUpdate, type EsitoUpdate, type Update } from "./telegram";
import datiSala from "./generato/sala.json";

export interface Segreti {
  TELEGRAM_BOT_TOKEN: string;
  OPENROUTER_API_KEY: string;
  OWNER_CHAT_IDS: string;
  OPENROUTER_MODEL?: string;
}

export const MODELLO_DEFAULT = "google/gemini-2.5-flash";

export class App {
  private readonly coda = new Coda();
  private readonly sala = new Sala(datiSala as unknown as DatiSala);
  private readonly store: ChiaveValoreStore;

  constructor(
    kv: ChiaveValore,
    private readonly env: Segreti,
    private readonly opzioni: { fetchImpl?: typeof fetch; adesso?: () => Date } = {},
  ) {
    this.store = new ChiaveValoreStore(kv);
  }

  /** Un aggiornamento alla volta: la coda evita che due messaggi scrivano la stessa serata insieme. */
  aggiorna(u: Update): Promise<EsitoUpdate> {
    return this.coda.esegui(() =>
      gestisciUpdate(
        {
          sala: this.sala,
          store: this.store,
          chiama: clientOpenRouter({ chiave: this.env.OPENROUTER_API_KEY, modello: this.env.OPENROUTER_MODEL || MODELLO_DEFAULT, fetchImpl: this.opzioni.fetchImpl }),
          adesso: this.opzioni.adesso,
        },
        { token: this.env.TELEGRAM_BOT_TOKEN, ammessi: elencoChat(this.env.OWNER_CHAT_IDS), fetchImpl: this.opzioni.fetchImpl },
        u,
      ),
    );
  }
}
