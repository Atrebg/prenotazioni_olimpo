import { describe, expect, it } from "vitest";
import { dimostratoPieno, punteggio, validaTurno } from "../src/validatore";
import { sala } from "./aiuti";

const p = (id: string, coperti: number, unita: string) => ({ id, nome: id, coperti, unita });

describe("sala", () => {
  it("legge la piantina vera", () => {
    expect(sala.turni.map((t) => [t.inizio, t.fine])).toEqual([["20:00", "21:30"], ["21:30", "24:00"]]);
    expect(sala.capienzaMassima).toBe(20);
    expect(sala.unitaPerChiave("t21.q0-0")!.posti).toBe(4); // quadrato da solo
    expect(sala.unitaPerChiave("t21.q0-1")!.posti).toBe(6); // intero
    expect(sala.unitaPerChiave("t5.q0-1")!.posti).toBe(6); // 2 quadrati di un blocco da 3
    expect(sala.unitaPerChiave("t5.q0-2")!.posti).toBe(8);
    expect(sala.etichetta("t21.q0-0")).toBe("tavolo 21, quadrato 1");
  });
});

describe("validaTurno", () => {
  it("ammette un piano semplice", () => {
    expect(validaTurno(sala, [p("a", 2, "t3"), p("b", 4, "t14")])).toEqual([]);
  });
  it("rifiuta più coperti dei posti", () => {
    expect(validaTurno(sala, [p("a", 3, "t3")])[0]).toMatch(/ha 2 posti/);
  });
  it("rifiuta due prenotazioni nello stesso posto", () => {
    expect(validaTurno(sala, [p("a", 2, "t3"), p("b", 2, "t3")])[0]).toMatch(/già di a/);
  });
  it("rifiuta un posto che non esiste", () => {
    expect(validaTurno(sala, [p("a", 2, "t99")])[0]).toMatch(/non è un posto/);
  });
  it("lungo: un gruppo da 18 oppure due da 8, il secondo solo con il primo", () => {
    expect(validaTurno(sala, [p("a", 18, "t11.g1")])).toEqual([]);
    expect(validaTurno(sala, [p("a", 8, "t11.g1"), p("b", 8, "t11.g2")])).toEqual([]);
    expect(validaTurno(sala, [p("a", 10, "t11.g1"), p("b", 6, "t11.g2")])[0]).toMatch(/al massimo 8/);
    expect(validaTurno(sala, [p("b", 6, "t11.g2")])[0]).toMatch(/solo insieme al primo/);
  });
  it("blocchi: pezzi contigui che non si sovrappongono", () => {
    expect(validaTurno(sala, [p("a", 4, "t5.q0-0"), p("b", 4, "t5.q1-1"), p("c", 4, "t5.q2-2")])).toEqual([]);
    expect(validaTurno(sala, [p("a", 4, "t5.q0-0"), p("b", 6, "t5.q1-2")])).toEqual([]);
    expect(validaTurno(sala, [p("a", 6, "t5.q0-1"), p("b", 4, "t5.q1-1")])[0]).toMatch(/si sovrappongono/);
    expect(validaTurno(sala, [p("a", 8, "t5.q0-2"), p("b", 2, "t5.q2-2")])[0]).toMatch(/si sovrappongono/);
  });
});

describe("punteggio e conteggio", () => {
  it("conta posti vuoti e divisioni", () => {
    expect(punteggio(sala, [p("a", 2, "t3")]).vuoti).toBe(0);
    expect(punteggio(sala, [p("a", 4, "t10")]).vuoti).toBe(6);
    // lungo con due gruppi: i posti vuoti sono 20 - 8 - 8
    expect(punteggio(sala, [p("a", 8, "t11.g1"), p("b", 8, "t11.g2")]).vuoti).toBe(4);
    expect(punteggio(sala, [p("a", 4, "t5.q0-0"), p("b", 4, "t5.q1-1"), p("c", 4, "t5.q2-2")]).divisioni).toBe(2);
    expect(punteggio(sala, [p("a", 6, "t5.q0-2")]).divisioni).toBe(0);
  });
  it("dimostra il pieno col conteggio", () => {
    // il lungo è l'unico posto da più di 10: due gruppi da 12 non ci stanno
    expect(dimostratoPieno(sala, [12, 12])).toBe(true);
    expect(dimostratoPieno(sala, [12])).toBe(false);
    expect(dimostratoPieno(sala, [2, 2, 2])).toBe(false);
    // 31 tavoli da almeno 1 posto: più di quante unità distinte possano esistere insieme
    expect(dimostratoPieno(sala, new Array(200).fill(1))).toBe(true);
  });
});
