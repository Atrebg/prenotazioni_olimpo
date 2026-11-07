// Store su file JSON per le prove in locale (scrittura atomica: file temporaneo + rename). Solo Node.
import { mkdirSync, readFileSync, renameSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import type { Conversazione, Serata } from "./tipi";
import { conversazioneVuota, serataVuota, type Store } from "./store";

export class FileStore implements Store {
  constructor(private readonly cartella: string) {
    mkdirSync(join(cartella, "serate"), { recursive: true });
    mkdirSync(join(cartella, "conversazioni"), { recursive: true });
  }
  private leggi<T>(percorso: string, vuoto: () => T): T {
    return existsSync(percorso) ? (JSON.parse(readFileSync(percorso, "utf-8")) as T) : vuoto();
  }
  private scrivi(percorso: string, dati: unknown): void {
    const tmp = `${percorso}.tmp`;
    writeFileSync(tmp, JSON.stringify(dati, null, 2));
    renameSync(tmp, percorso);
  }
  async serata(data: string): Promise<Serata> {
    return this.leggi(join(this.cartella, "serate", `${data}.json`), () => serataVuota(data));
  }
  async salvaSerata(s: Serata): Promise<void> {
    this.scrivi(join(this.cartella, "serate", `${s.data}.json`), s);
  }
  async conversazione(mittente: string): Promise<Conversazione> {
    return this.leggi(join(this.cartella, "conversazioni", `${encodeURIComponent(mittente)}.json`), conversazioneVuota);
  }
  async salvaConversazione(mittente: string, c: Conversazione): Promise<void> {
    this.scrivi(join(this.cartella, "conversazioni", `${encodeURIComponent(mittente)}.json`), c);
  }
  async ultimoUpdate(): Promise<number> {
    return this.leggi(join(this.cartella, "ultimo_update.json"), () => 0);
  }
  async salvaUltimoUpdate(n: number): Promise<void> {
    this.scrivi(join(this.cartella, "ultimo_update.json"), n);
  }
}
