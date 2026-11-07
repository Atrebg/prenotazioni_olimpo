// La sala vera dell'Olimpo: tavoli e "unità" assegnabili in un turno. Stesse regole di ristorante/piantina.py.
//   - tavolo semplice (panca, rettangolare, tondo, quadrato): una prenotazione, coperti <= posti;
//   - tavolo lungo: un gruppo fino ai suoi posti (20) oppure due gruppi fino a 8 ciascuno;
//   - blocco separabile di k quadrati: pezzi contigui; intero = posti del blocco, pezzo da j >= 2 quadrati 2j + 2 posti,
//     un quadrato da solo `posti_quadrato_separato`.
export const LUNGO_DUE_GRUPPI = 8;
export const NOMI_TURNI = ["primo", "secondo", "terzo", "quarto"];
const TIPI_SEMPLICI = ["panca", "rettangolare", "tondo", "quadrato"];

export interface Tavolo {
  id: string;
  tipo: string;
  posti: number;
  moduli?: number;
  separabile?: boolean;
  note?: string;
  [altro: string]: unknown;
}

export interface DatiSala {
  nome?: string;
  turni: string[];
  posti_quadrato_separato?: number;
  tavoli: Tavolo[];
  [altro: string]: unknown;
}

export interface Unita {
  chiave: string; // "t4", "t11.g2", "t5.q0-1": nome stabile, senza turno
  tavolo: string;
  tipo: string;
  posti: number;
  quadrati?: [number, number]; // blocco: primo e ultimo quadrato del pezzo (contiguo)
  gruppo?: 1 | 2; // lungo
  intero?: boolean; // blocco: il pezzo è il blocco intero
}

export interface Turno {
  indice: number; // 0-based
  nome: string;
  inizio: string; // "20:00"
  fine: string; // inizio del successivo, o la chiusura
}

export const CHIUSURA = "24:00";

export function minuti(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + (m || 0);
}

export class Sala {
  readonly nome: string;
  readonly turni: Turno[];
  readonly tavoli: Tavolo[];
  private readonly perId = new Map<string, Tavolo>();
  private readonly postiSeparato: number;
  readonly unita: Unita[];
  private readonly perChiave = new Map<string, Unita>();

  constructor(dati: DatiSala) {
    this.nome = dati.nome ?? "sala";
    this.postiSeparato = Number(dati.posti_quadrato_separato ?? 4);
    const inizi = (dati.turni ?? []).map(String);
    if (!inizi.length) throw new Error("la piantina non ha i turni");
    this.turni = inizi.map((inizio, i) => ({
      indice: i,
      nome: NOMI_TURNI[i] ?? `turno ${i + 1}`,
      inizio,
      fine: inizi[i + 1] ?? CHIUSURA,
    }));
    this.tavoli = dati.tavoli ?? [];
    for (const t of this.tavoli) {
      const id = String(t.id ?? "");
      if (!id || this.perId.has(id)) throw new Error(`tavolo senza id o con id duplicato: ${id}`);
      if (!Number.isInteger(t.posti) || t.posti <= 0) throw new Error(`tavolo ${id}: posti non indicati`);
      if (t.tipo === "blocco" && !(Number(t.moduli) >= 1)) throw new Error(`tavolo ${id}: blocco senza quadrati`);
      if (![...TIPI_SEMPLICI, "blocco", "lungo"].includes(t.tipo)) throw new Error(`tavolo ${id}: tipo ${t.tipo} sconosciuto`);
      this.perId.set(id, t);
    }
    this.unita = this.tavoli.flatMap((t) => this.unitaDel(t));
    for (const u of this.unita) this.perChiave.set(u.chiave, u);
  }

  tavolo(id: string): Tavolo | undefined {
    return this.perId.get(id);
  }

  unitaPerChiave(chiave: string): Unita | undefined {
    return this.perChiave.get(chiave);
  }

  postiPezzo(t: Tavolo, a: number, b: number): number {
    const k = Number(t.moduli);
    if (a === 0 && b === k - 1) return t.posti;
    const j = b - a + 1;
    return j >= 2 ? 2 * j + 2 : this.postiSeparato;
  }

  unitaDel(t: Tavolo): Unita[] {
    const id = String(t.id);
    if (t.tipo === "lungo") {
      return [
        { chiave: `t${id}.g1`, tavolo: id, tipo: "lungo", posti: t.posti, gruppo: 1 },
        { chiave: `t${id}.g2`, tavolo: id, tipo: "lungo", posti: Math.min(LUNGO_DUE_GRUPPI, t.posti), gruppo: 2 },
      ];
    }
    if (t.tipo === "blocco") {
      const k = Number(t.moduli);
      if (!t.separabile) {
        return [{ chiave: `t${id}.q0-${k - 1}`, tavolo: id, tipo: "blocco", posti: t.posti, quadrati: [0, k - 1], intero: true }];
      }
      const pezzi: Unita[] = [];
      for (let a = 0; a < k; a++)
        for (let b = a; b < k; b++)
          pezzi.push({
            chiave: `t${id}.q${a}-${b}`,
            tavolo: id,
            tipo: "blocco",
            posti: this.postiPezzo(t, a, b),
            quadrati: [a, b],
            intero: a === 0 && b === k - 1,
          });
      return pezzi;
    }
    return [{ chiave: `t${id}`, tavolo: id, tipo: t.tipo, posti: t.posti }];
  }

  get capienzaMassima(): number {
    return Math.max(0, ...this.unita.map((u) => u.posti));
  }

  /** Nome leggibile di un'unità, per il proprietario ("tavolo 21, quadrato 1"). */
  etichetta(chiave: string): string {
    const u = this.perChiave.get(chiave);
    if (!u) return chiave;
    if (u.gruppo) return `tavolo ${u.tavolo}, gruppo ${u.gruppo}`;
    if (u.quadrati) {
      const t = this.perId.get(u.tavolo)!;
      const [a, b] = u.quadrati;
      if (u.intero) return `blocco ${u.tavolo}${t.separabile ? " (intero)" : ""}`;
      return a === b ? `tavolo ${u.tavolo}, quadrato ${a + 1}` : `tavolo ${u.tavolo}, quadrati ${a + 1}-${b + 1}`;
    }
    return `tavolo ${u.tavolo}`;
  }

  /**
   * Quante prenotazioni da almeno `c` coperti possono sedersi insieme in un turno, al massimo (tavoli semplici, due
   * gruppi del lungo, pezzi di una partizione contigua dei blocchi). Serve a dimostrare "turno pieno".
   */
  maxUnita(c: number): number {
    let n = 0;
    for (const t of this.tavoli) {
      if (t.tipo === "lungo") {
        n += c <= LUNGO_DUE_GRUPPI ? 2 : Number(c <= t.posti);
      } else if (t.tipo === "blocco" && t.separabile) {
        const k = Number(t.moduli);
        const best = new Array<number>(k + 1).fill(0);
        for (let i = 1; i <= k; i++) {
          for (let a = 0; a < i; a++) best[i] = Math.max(best[i], best[a] + Number(this.postiPezzo(t, a, i - 1) >= c));
        }
        n += best[k];
      } else {
        n += Number(t.posti >= c);
      }
    }
    return n;
  }
}
