import { Sala, type DatiSala } from "../src/sala";
import datiSala from "../src/generato/sala.json";
import { MemoriaStore } from "../src/store";
import { STRUMENTI, type Contesto } from "../src/strumenti";

export const sala = new Sala(datiSala as unknown as DatiSala);
export const ADESSO = new Date("2026-11-07T10:00:00Z");
export const SABATO = "2026-11-14";

export function contesto(): Contesto {
  return { sala, store: new MemoriaStore(), adesso: () => ADESSO, mittente: "t" };
}

export async function usa(ctx: Contesto, nome: string, args: Record<string, unknown> = {}): Promise<any> {
  const s = STRUMENTI.find((x) => x.name === nome)!;
  try {
    return await s.esegui(args, ctx);
  } catch (e) {
    return { errore: (e as Error).message };
  }
}
