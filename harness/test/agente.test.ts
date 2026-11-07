import { describe, expect, it } from "vitest";
import { MSG_ERRORE, MSG_TROPPI_GIRI, gestisciMessaggio, promptSistema, type ChiamaModello, type MessaggioModello } from "../src/agente";
import { clientOpenRouter } from "../src/openrouter";
import { MemoriaStore } from "../src/store";
import { ADESSO, SABATO, sala } from "./aiuti";

const chiamata = (id: string, name: string, args: object) => ({ id, type: "function" as const, function: { name, arguments: JSON.stringify(args) } });
const usaStrumento = (...c: ReturnType<typeof chiamata>[]): MessaggioModello => ({ role: "assistant", content: null, tool_calls: c });
const testo = (t: string): MessaggioModello => ({ role: "assistant", content: t });

/** Modello finto: risponde con la prossima mossa del copione e registra i messaggi che ha visto. */
function copione(mosse: MessaggioModello[]) {
  const viste: MessaggioModello[][] = [];
  let i = 0;
  const chiama: ChiamaModello = async (m) => {
    viste.push(structuredClone(m));
    if (i >= mosse.length) throw new Error("copione finito");
    return mosse[i++];
  };
  return { chiama, viste };
}

describe("giro dell'agente", () => {
  it("registra una prenotazione con gli strumenti e risponde", async () => {
    const store = new MemoriaStore();
    const { chiama, viste } = copione([
      usaStrumento(chiamata("1", "cerca_posto", { data: SABATO, turno: 1, coperti: 4 })),
      usaStrumento(chiamata("2", "registra", { nome: "Rossi", coperti: 4, data: SABATO, turno: 1, unita: "t14" })),
      testo("✓ Rossi · 4 persone · sab 14/11 · primo turno (20:00)"),
    ]);
    const tracce: string[] = [];
    const r = await gestisciMessaggio({ sala, store, chiama, adesso: () => ADESSO, traccia: (e) => tracce.push(e.strumento) }, "u", "Rossi 4 sab 20:00");
    expect(r).toMatch(/^✓ Rossi/);
    expect(tracce).toEqual(["cerca_posto", "registra"]);
    expect((await store.serata(SABATO)).prenotazioni).toHaveLength(1);
    // il risultato dello strumento torna al modello come messaggio "tool"
    expect(viste[1].at(-1)).toMatchObject({ role: "tool", tool_call_id: "1" });
  });

  it("un errore dello strumento torna al modello e non scrive niente", async () => {
    const store = new MemoriaStore();
    const { chiama, viste } = copione([
      usaStrumento(chiamata("1", "registra", { nome: "Rossi", coperti: 5, data: SABATO, turno: 1, unita: "t3" })),
      testo("Non entra al tavolo da 2."),
    ]);
    await gestisciMessaggio({ sala, store, chiama, adesso: () => ADESSO }, "u", "Rossi 5");
    expect(JSON.parse(viste[1].at(-1)!.content!).errore).toMatch(/non ammesso/);
    expect((await store.serata(SABATO)).prenotazioni).toHaveLength(0);
  });

  it("argomenti rotti e strumenti inventati non fanno cadere il giro", async () => {
    const { chiama, viste } = copione([
      usaStrumento({ id: "1", type: "function", function: { name: "registra", arguments: "{non json" } }, chiamata("2", "cancella_tutto", {})),
      testo("ok"),
    ]);
    const r = await gestisciMessaggio({ sala, store: new MemoriaStore(), chiama, adesso: () => ADESSO }, "u", "x");
    expect(r).toBe("ok");
    const tool = viste[1].filter((m) => m.role === "tool").map((m) => JSON.parse(m.content!).errore);
    expect(tool[0]).toMatch(/JSON/);
    expect(tool[1]).toMatch(/sconosciuto/);
  });

  it("si ferma dopo il tetto di giri senza scrivere", async () => {
    const { chiama } = copione(Array.from({ length: 5 }, (_, i) => usaStrumento(chiamata(String(i), "piantina", {}))));
    const r = await gestisciMessaggio({ sala, store: new MemoriaStore(), chiama, adesso: () => ADESSO, maxGiri: 3 }, "u", "x");
    expect(r).toBe(MSG_TROPPI_GIRI);
  });

  it("un errore del modello dà un messaggio chiaro", async () => {
    const chiama: ChiamaModello = async () => {
      throw new Error("OpenRouter 500");
    };
    expect(await gestisciMessaggio({ sala, store: new MemoriaStore(), chiama, adesso: () => ADESSO }, "u", "x")).toBe(MSG_ERRORE);
  });
});

describe("domande e bozza", () => {
  it("salva la bozza, la ripresenta alla risposta e la fa scadere dopo 15 minuti", async () => {
    const store = new MemoriaStore();
    let ora = ADESSO;
    const A = copione([
      usaStrumento(chiamata("1", "memorizza_bozza", { azione: "registrare Rossi 4 sabato", dettagli: { nome: "Rossi", coperti: 4 }, mancano: ["turno"], domanda: "Primo o secondo turno?" })),
      testo("Rossi 4 sabato: primo o secondo turno?"),
    ]);
    const dip = (c: ChiamaModello) => ({ sala, store, chiama: c, adesso: () => ora });
    await gestisciMessaggio(dip(A.chiama), "u", "Rossi 4 sabato");
    expect((await store.conversazione("u")).bozza?.domanda).toBe("Primo o secondo turno?");

    // risposta dopo 5 minuti: la bozza è nel prompt e nella storia c'è la domanda
    ora = new Date(ADESSO.getTime() + 5 * 60_000);
    const B = copione([testo("ok")]);
    await gestisciMessaggio(dip(B.chiama), "u", "secondo");
    const sistema = B.viste[0][0].content!;
    expect(sistema).toMatch(/BOZZA IN SOSPESO/);
    expect(sistema).toMatch(/Primo o secondo turno\?/);
    expect(B.viste[0].map((m) => m.role)).toEqual(["system", "user", "assistant", "user"]);

    // risposta dopo 20 minuti: la bozza è scaduta, non resta nello stato
    ora = new Date(ADESSO.getTime() + 20 * 60_000);
    const C = copione([testo("ok")]);
    await gestisciMessaggio(dip(C.chiama), "u", "secondo");
    expect(C.viste[0][0].content).toMatch(/bozza precedente è scaduta/);
    expect((await store.conversazione("u")).bozza).toBeUndefined();
  });

  it("cancella_bozza la toglie", async () => {
    const store = new MemoriaStore();
    const c = await store.conversazione("u");
    c.bozza = { azione: "x", dettagli: {}, mancano: [], domanda: "?", creata_il: ADESSO.toISOString() };
    await store.salvaConversazione("u", c);
    const { chiama } = copione([usaStrumento(chiamata("1", "cancella_bozza", {})), testo("Lascio stare.")]);
    await gestisciMessaggio({ sala, store, chiama, adesso: () => ADESSO }, "u", "lascia stare");
    expect((await store.conversazione("u")).bozza).toBeUndefined();
  });

  it("la storia è limitata", async () => {
    const store = new MemoriaStore();
    for (let i = 0; i < 10; i++) {
      await gestisciMessaggio({ sala, store, chiama: copione([testo(`r${i}`)]).chiama, adesso: () => ADESSO, storiaMax: 6 }, "u", `m${i}`);
    }
    const s = (await store.conversazione("u")).storia;
    expect(s).toHaveLength(6);
    expect(s.at(-1)).toEqual({ role: "assistant", content: "r9" });
  });
});

describe("prompt", () => {
  it("contiene calendario, turni e regole del repository", () => {
    const p = promptSistema(sala, ADESSO);
    expect(p).toMatch(/sabato 2026-11-14/);
    expect(p).toMatch(/1 = primo 20:00, 2 = secondo 21:30/);
    expect(p).toMatch(/Passaggio del cameriere/);
    expect(p).toMatch(/80 cm/);
  });
});

describe("client OpenRouter", () => {
  it("manda messaggi e strumenti, legge la risposta", async () => {
    let richiesta: any;
    const fetchImpl = (async (url: string, init: any) => {
      richiesta = { url, ...init, corpo: JSON.parse(init.body) };
      return new Response(JSON.stringify({ choices: [{ message: { role: "assistant", content: "ciao" } }] }), { status: 200 });
    }) as unknown as typeof fetch;
    const chiama = clientOpenRouter({ chiave: "k", modello: "m/x", fetchImpl });
    const { STRUMENTI } = await import("../src/strumenti");
    const r = await chiama([{ role: "user", content: "hey" }], STRUMENTI);
    expect(r.content).toBe("ciao");
    expect(richiesta.url).toBe("https://openrouter.ai/api/v1/chat/completions");
    expect(richiesta.headers.Authorization).toBe("Bearer k");
    expect(richiesta.corpo.model).toBe("m/x");
    expect(richiesta.corpo.tools).toHaveLength(STRUMENTI.length);
    expect(richiesta.corpo.tools[0]).toMatchObject({ type: "function", function: { name: "piantina" } });
  });
  it("un errore HTTP diventa un'eccezione leggibile", async () => {
    const fetchImpl = (async () => new Response("troppe richieste", { status: 429 })) as unknown as typeof fetch;
    await expect(clientOpenRouter({ chiave: "k", modello: "m", fetchImpl })([], [])).rejects.toThrow(/OpenRouter 429/);
  });
});
