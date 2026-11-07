import { Sala, minuti } from "./sala";

export const GIORNI_MAX = 90;
export const TURNI_VICINO_MIN = 45;

export interface EsitoTurno {
  turno?: number; // 1-based, per chi parla
  nome?: string;
  inizio?: string;
  a_meta: boolean; // equidistante da due turni: va nel primo, ma conviene chiedere
  lontano: boolean; // a più di 45 minuti da ogni turno: non si registra senza il sì
  piu_vicino: number; // 1-based
  messaggio: string;
}

/** Il turno più vicino a un orario ("alle 8" = 20:00 lo decide chi legge il messaggio). A parità il primo. */
export function turnoPerOrario(sala: Sala, hhmm: string): EsitoTurno {
  const m = minuti(hhmm);
  let best = 0;
  let dist = Infinity;
  let pari = false;
  sala.turni.forEach((t, i) => {
    const d = Math.abs(minuti(t.inizio) - m);
    if (d < dist) {
      best = i;
      dist = d;
      pari = false;
    } else if (d === dist) pari = true;
  });
  const t = sala.turni[best];
  const lontano = dist > TURNI_VICINO_MIN;
  const msg = lontano
    ? `alle ${hhmm} non c'è un turno: il più vicino è il ${t.nome}, alle ${t.inizio}`
    : pari
      ? `${hhmm} è a metà tra due turni: va nel ${t.nome} (${t.inizio}), meglio chiedere quale intende`
      : `${hhmm} va nel ${t.nome} turno (${t.inizio})`;
  return { turno: lontano ? undefined : best + 1, nome: t.nome, inizio: t.inizio, a_meta: pari, lontano, piu_vicino: best + 1, messaggio: msg };
}

const FUSO = "Europe/Rome";

/** Data locale AAAA-MM-GG del ristorante. */
export function dataLocale(adesso: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: FUSO, year: "numeric", month: "2-digit", day: "2-digit" }).format(adesso);
}

export function oraLocale(adesso: Date): string {
  return new Intl.DateTimeFormat("it-IT", { timeZone: FUSO, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(adesso);
}

export function giornoSettimana(data: string): string {
  const d = new Date(`${data}T12:00:00Z`);
  return new Intl.DateTimeFormat("it-IT", { timeZone: "UTC", weekday: "long" }).format(d);
}

export function aggiungiGiorni(data: string, n: number): string {
  const d = new Date(`${data}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Errore se la data non è valida, è passata o è oltre i 90 giorni. */
export function controllaData(data: string, oggi: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(data) || Number.isNaN(Date.parse(`${data}T12:00:00Z`)) || aggiungiGiorni(data, 0) !== data) {
    return `data non valida: "${data}" (serve AAAA-MM-GG)`;
  }
  if (data < oggi) return `${data} è già passato (oggi è ${oggi})`;
  if (data > aggiungiGiorni(oggi, GIORNI_MAX)) return `${data} è oltre i ${GIORNI_MAX} giorni da oggi`;
  return null;
}

/** Elenco dei prossimi giorni con il giorno della settimana, per non far calcolare le date al modello. */
export function calendario(oggi: string, giorni = 21): string {
  return Array.from({ length: giorni }, (_, i) => {
    const d = aggiungiGiorni(oggi, i);
    return `${giornoSettimana(d)} ${d}${i === 0 ? " (oggi)" : ""}`;
  }).join("\n");
}
