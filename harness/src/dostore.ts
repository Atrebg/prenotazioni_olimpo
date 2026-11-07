// Store sopra lo storage di un Durable Object (o qualunque chiave-valore con get/put). Serate e conversazioni sono piccole.
import type { Conversazione, Serata } from "./tipi";
import { conversazioneVuota, serataVuota, type Store } from "./store";

export interface ChiaveValore {
  get<T = unknown>(chiave: string): Promise<T | undefined>;
  put<T>(chiave: string, valore: T): Promise<void>;
}

export class ChiaveValoreStore implements Store {
  constructor(private readonly kv: ChiaveValore) {}
  async serata(data: string): Promise<Serata> {
    return (await this.kv.get<Serata>(`serata:${data}`)) ?? serataVuota(data);
  }
  async salvaSerata(s: Serata): Promise<void> {
    await this.kv.put(`serata:${s.data}`, s);
  }
  async conversazione(mittente: string): Promise<Conversazione> {
    return (await this.kv.get<Conversazione>(`conv:${mittente}`)) ?? conversazioneVuota();
  }
  async salvaConversazione(mittente: string, c: Conversazione): Promise<void> {
    await this.kv.put(`conv:${mittente}`, c);
  }
  async ultimoUpdate(): Promise<number> {
    return (await this.kv.get<number>("ultimo_update")) ?? 0;
  }
  async salvaUltimoUpdate(n: number): Promise<void> {
    await this.kv.put("ultimo_update", n);
  }
}
