// Regole dure sulla sala di un turno. Il modello propone, questo codice decide se il piano è ammesso.
import { LUNGO_DUE_GRUPPI, Sala } from "./sala";

export interface Posto {
  id: string; // prenotazione
  nome: string;
  coperti: number;
  unita: string;
}

/** Errori del piano di un turno; vuoto = ammesso. */
export function validaTurno(sala: Sala, posti: Posto[]): string[] {
  const errori: string[] = [];
  const usate = new Map<string, Posto>();
  for (const p of posti) {
    const u = sala.unitaPerChiave(p.unita);
    if (!u) {
      errori.push(`${p.nome}: "${p.unita}" non è un posto della sala`);
      continue;
    }
    if (p.coperti > u.posti) {
      errori.push(`${p.nome} (${p.coperti}): ${sala.etichetta(p.unita)} ha ${u.posti} posti`);
    }
    const altro = usate.get(p.unita);
    if (altro) errori.push(`${sala.etichetta(p.unita)} è già di ${altro.nome}: due prenotazioni nello stesso posto`);
    else usate.set(p.unita, p);
  }

  // tavolo lungo: un gruppo fino a 20 oppure due gruppi fino a 8; il secondo solo con il primo
  for (const t of sala.tavoli.filter((x) => x.tipo === "lungo")) {
    const g1 = usate.get(`t${t.id}.g1`);
    const g2 = usate.get(`t${t.id}.g2`);
    if (g2 && !g1) errori.push(`tavolo ${t.id}: il secondo gruppo c'è solo insieme al primo`);
    if (g2 && g1 && g1.coperti > LUNGO_DUE_GRUPPI) {
      errori.push(`tavolo ${t.id}: con due gruppi, ciascuno al massimo ${LUNGO_DUE_GRUPPI} (${g1.nome} è ${g1.coperti})`);
    }
  }

  // blocchi: i pezzi usati sono contigui e non si sovrappongono
  for (const t of sala.tavoli.filter((x) => x.tipo === "blocco")) {
    const pezzi = [...usate.values()]
      .map((p) => ({ p, u: sala.unitaPerChiave(p.unita)! }))
      .filter(({ u }) => u.tavolo === String(t.id) && u.quadrati);
    for (let i = 0; i < pezzi.length; i++) {
      for (let j = i + 1; j < pezzi.length; j++) {
        const [a1, b1] = pezzi[i].u.quadrati!;
        const [a2, b2] = pezzi[j].u.quadrati!;
        if (a1 <= b2 && a2 <= b1) {
          errori.push(
            `tavolo ${t.id}: ${pezzi[i].p.nome} e ${pezzi[j].p.nome} si sovrappongono (${sala.etichetta(pezzi[i].p.unita)} / ${sala.etichetta(pezzi[j].p.unita)})`,
          );
        }
      }
    }
  }
  return errori;
}

/** Posti vuoti e divisioni dei blocchi di un piano: più basso è meglio (stessi pesi del motore: 10 e 4). */
export function punteggio(sala: Sala, posti: Posto[]): { vuoti: number; divisioni: number; costo: number } {
  let vuoti = 0;
  const pezziPerBlocco = new Map<string, number>();
  for (const p of posti) {
    const u = sala.unitaPerChiave(p.unita);
    if (!u) continue;
    vuoti += u.gruppo === 2 ? -p.coperti : u.posti - p.coperti;
    if (u.quadrati) pezziPerBlocco.set(u.tavolo, (pezziPerBlocco.get(u.tavolo) ?? 0) + (u.intero ? 0 : 1));
  }
  let divisioni = 0;
  // n pezzi usati: con un solo pezzo il resto del blocco resta vuoto (1 divisione), altrimenti n - 1
  for (const n of pezziPerBlocco.values()) if (n > 0) divisioni += Math.max(1, n - 1);
  return { vuoti, divisioni, costo: vuoti * 10 + divisioni * 4 };
}

/**
 * Dimostrazione per conteggio che una nuova prenotazione non entra in un turno, in qualunque disposizione:
 * per ogni soglia c, le prenotazioni da almeno c coperti non possono superare le unità da almeno c posti che
 * possono esserci insieme. Vero = sicuramente pieno; falso = non dimostrato (non vuol dire che ci sia posto).
 */
export function dimostratoPieno(sala: Sala, coperti: number[]): boolean {
  for (const c of new Set(coperti)) {
    const n = coperti.filter((x) => x >= c).length;
    if (n > sala.maxUnita(c)) return true;
  }
  return false;
}
