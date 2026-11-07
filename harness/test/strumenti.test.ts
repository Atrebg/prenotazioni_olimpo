import { describe, expect, it } from "vitest";
import { SABATO, contesto, usa } from "./aiuti";

const reg = (ctx: any, nome: string, coperti: number, unita: string, extra: object = {}) =>
  usa(ctx, "registra", { nome, coperti, data: SABATO, turno: 1, unita, ...extra });

describe("registra", () => {
  it("registra e la conferma non cita il tavolo", async () => {
    const ctx = contesto();
    const r = await reg(ctx, "Rossi", 4, "t14");
    expect(r.registrata).toBe(true);
    expect(r.conferma).toBe("✓ Rossi · 4 persone · sab 14/11 · primo turno (20:00)");
    expect(JSON.stringify(r)).not.toMatch(/tavolo/);
  });
  it("non scrive se il piano non è ammesso", async () => {
    const ctx = contesto();
    expect((await reg(ctx, "Rossi", 5, "t3")).errore).toMatch(/non ammesso/);
    expect((await usa(ctx, "stato_serata", { data: SABATO })).turni[0].prenotazioni).toBe(0);
  });
  it("rifiuta date passate, oltre i 90 giorni, turni e coperti assurdi", async () => {
    const ctx = contesto();
    expect((await usa(ctx, "registra", { nome: "A", coperti: 2, data: "2026-11-01", turno: 1, unita: "t3" })).errore).toMatch(/passato/);
    expect((await usa(ctx, "registra", { nome: "A", coperti: 2, data: "2027-06-01", turno: 1, unita: "t3" })).errore).toMatch(/90 giorni/);
    expect((await reg(ctx, "A", 2, "t3", { turno: 3 })).errore).toMatch(/turno non valido/);
    expect((await reg(ctx, "A", 25, "t11.g1")).errore).toMatch(/più grande/);
  });
  it("chiede se un nome già presente è un'altra prenotazione", async () => {
    const ctx = contesto();
    await reg(ctx, "Rossi", 2, "t3");
    expect((await reg(ctx, "rossi", 2, "t4")).errore).toMatch(/C'è già Rossi/);
    expect((await reg(ctx, "Rossi", 2, "t4", { altra_prenotazione_stesso_nome: true })).registrata).toBe(true);
  });
});

describe("cerca_posto", () => {
  it("preferisce il posto con meno posti vuoti", async () => {
    const ctx = contesto();
    const r = await usa(ctx, "cerca_posto", { data: SABATO, turno: 1, coperti: 2 });
    expect(r.esito).toBe("trovato");
    expect(r.opzioni[0].posti_vuoti).toBe(0);
  });
  async function sala8Occupata(ctx: any) {
    const x = await reg(ctx, "X", 4, "t5.q0-2");
    await reg(ctx, "A", 3, "t8.q0-2");
    await reg(ctx, "B", 2, "t10");
    await reg(ctx, "C", 18, "t11.g1");
    return x.id as string;
  }
  it("sposta una prenotazione non fissata per far posto a un gruppo da 8", async () => {
    const ctx = contesto();
    await sala8Occupata(ctx);
    const r = await usa(ctx, "cerca_posto", { data: SABATO, turno: 1, coperti: 8 });
    expect(r.esito).toBe("trovato");
    expect(r.opzioni[0].sposta).toHaveLength(1);
    // la proposta si può registrare così com'è
    const o = r.opzioni[0];
    const reg2 = await reg(ctx, "Nuovi", 8, o.unita, { riassegna: o.sposta.map((m: any) => ({ prenotazione_id: m.prenotazione_id, unita: "t14" })) });
    expect(reg2.registrata).toBe(true);
  });
  it("con le prenotazioni fissate non trova posto ma non dice 'pieno'", async () => {
    const ctx = contesto();
    const x = await sala8Occupata(ctx);
    await usa(ctx, "fissa", { data: SABATO, prenotazione_id: x, unita: "t5.q0-2" });
    for (const id of ["P2", "P3"]) await usa(ctx, "fissa", { data: SABATO, prenotazione_id: id, unita: id === "P2" ? "t8.q0-2" : "t10" });
    const r = await usa(ctx, "cerca_posto", { data: SABATO, turno: 1, coperti: 8 });
    expect(r.esito).toBe("non_trovato");
    expect(r.dimostrato_pieno).toBe(false);
    expect(r.nota).toMatch(/non è dimostrato/);
  });
  it("dimostra il pieno quando il conteggio lo dimostra", async () => {
    const ctx = contesto();
    await reg(ctx, "Ricci", 18, "t11.g1");
    const r = await usa(ctx, "cerca_posto", { data: SABATO, turno: 1, coperti: 14 });
    expect(r.esito).toBe("non_trovato");
    expect(r.dimostrato_pieno).toBe(true);
  });
});

describe("fissa e libera", () => {
  it("divide un blocco per ordine del proprietario e fissa", async () => {
    const ctx = contesto();
    const r = await reg(ctx, "Rossi", 4, "t14");
    const f = await usa(ctx, "fissa", { data: SABATO, prenotazione_id: r.id, unita: "t21.q0-0" });
    expect(f.fissata).toBe(true);
    expect(f.dove).toBe("tavolo 21, quadrato 1");
    const sp = await usa(ctx, "registra", { nome: "Verdi", coperti: 2, data: SABATO, turno: 1, unita: "t14", riassegna: [{ prenotazione_id: r.id, unita: "t15" }] });
    expect(sp.errore).toMatch(/fissata dal proprietario/);
    expect((await usa(ctx, "libera", { data: SABATO, prenotazione_id: r.id })).liberata).toBe(true);
  });
  it("rifiuta un ordine che viola le regole dure", async () => {
    const ctx = contesto();
    const r = await reg(ctx, "Rossi", 6, "t14".replace("t14", "t21.q0-1"));
    expect(r.registrata).toBe(true);
    const x = await reg(ctx, "Verdi", 4, "t21.q1-1");
    expect(x.errore).toMatch(/si sovrappongono/);
  });
});

describe("modifica e annulla", () => {
  it("cambia i coperti solo se il posto basta", async () => {
    const ctx = contesto();
    const r = await reg(ctx, "Rossi", 2, "t3");
    expect((await usa(ctx, "modifica", { data: SABATO, prenotazione_id: r.id, coperti: 4 })).errore).toMatch(/ha 2 posti/);
    expect((await usa(ctx, "modifica", { data: SABATO, prenotazione_id: r.id, coperti: 4, unita: "t14" })).modificata).toBe(true);
  });
  it("cambiare turno richiede il sì del cliente", async () => {
    const ctx = contesto();
    const r = await reg(ctx, "Rossi", 2, "t3");
    expect((await usa(ctx, "modifica", { data: SABATO, prenotazione_id: r.id, nuovo_turno: 2, unita: "t3" })).errore).toMatch(/sì del cliente/);
    const ok = await usa(ctx, "modifica", { data: SABATO, prenotazione_id: r.id, nuovo_turno: 2, unita: "t3", cliente_ha_accettato: true });
    expect(ok.conferma).toMatch(/secondo turno/);
  });
  it("annulla libera il posto", async () => {
    const ctx = contesto();
    const r = await reg(ctx, "Rossi", 2, "t3");
    await usa(ctx, "annulla", { data: SABATO, prenotazione_id: r.id });
    expect((await reg(ctx, "Verdi", 2, "t3")).registrata).toBe(true);
  });
});

describe("riepilogo e turno_per_orario", () => {
  it("il riepilogo dice il tavolo", async () => {
    const ctx = contesto();
    await reg(ctx, "Rossi", 4, "t21.q0-0");
    const r = await usa(ctx, "riepilogo", { data: SABATO });
    expect(r.testo).toMatch(/Rossi 4 · tavolo 21, quadrato 1/);
    expect(r.testo).toMatch(/Primo turno \(20:00\): 1 prenotazioni, 4 coperti/);
  });
  it("assegna l'orario al turno più vicino, a metà al primo, lontano senza turno", async () => {
    const ctx = contesto();
    expect((await usa(ctx, "turno_per_orario", { orario: "21:15" })).turno).toBe(2);
    const meta = await usa(ctx, "turno_per_orario", { orario: "20:45" });
    expect(meta).toMatchObject({ turno: 1, a_meta: true });
    expect(await usa(ctx, "turno_per_orario", { orario: "19:00" })).toMatchObject({ lontano: true, turno: undefined, piu_vicino: 1 });
  });
});
