import type { Conversazione, Serata } from "./tipi";

/** Dove stanno le serate e le conversazioni. Implementazioni: memoria (prove), file (locale), D1 (Cloudflare). */
export interface Store {
  serata(data: string): Promise<Serata>;
  salvaSerata(s: Serata): Promise<void>;
  conversazione(mittente: string): Promise<Conversazione>;
  salvaConversazione(mittente: string, c: Conversazione): Promise<void>;
}

export const serataVuota = (data: string): Serata => ({ data, versione: 0, prenotazioni: [], prossimo_id: 1 });
export const conversazioneVuota = (): Conversazione => ({ storia: [] });

export class MemoriaStore implements Store {
  private serate = new Map<string, Serata>();
  private conv = new Map<string, Conversazione>();

  async serata(data: string): Promise<Serata> {
    return structuredClone(this.serate.get(data) ?? serataVuota(data));
  }
  async salvaSerata(s: Serata): Promise<void> {
    this.serate.set(s.data, structuredClone(s));
  }
  async conversazione(mittente: string): Promise<Conversazione> {
    return structuredClone(this.conv.get(mittente) ?? conversazioneVuota());
  }
  async salvaConversazione(mittente: string, c: Conversazione): Promise<void> {
    this.conv.set(mittente, structuredClone(c));
  }
}
