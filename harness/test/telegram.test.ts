import { describe, expect, it } from "vitest";
import { App } from "../src/app";
import { Coda } from "../src/coda";
import { ChiaveValoreStore } from "../src/dostore";
import { dataPulsante, elencoChat, gestisciUpdate, spezza, type Update } from "../src/telegram";
import { MemoriaStore } from "../src/store";
import type { MessaggioModello } from "../src/agente";
import { ADESSO, SABATO, sala } from "./aiuti";

const chiamata = (id: string, name: string, args: object) => ({ id, type: "function" as const, function: { name, arguments: JSON.stringify(args) } });

/** Rete finta: Telegram registra le chiamate, OpenRouter segue un copione. */
function rete(mosse: MessaggioModello[]) {
  const telegram: { metodo: string; corpo: any }[] = [];
  let i = 0;
  const fetchImpl = (async (url: string, init: any) => {
    const corpo = JSON.parse(init.body);
    if (url.startsWith("https://api.telegram.org/bot")) {
      telegram.push({ metodo: url.split("/").pop()!, corpo });
      return new Response(JSON.stringify({ ok: true, result: {} }), { status: 200 });
    }
    if (i >= mosse.length) throw new Error("copione finito");
    return new Response(JSON.stringify({ choices: [{ message: mosse[i++] }] }), { status: 200 });
  }) as unknown as typeof fetch;
  return { fetchImpl, telegram, inviati: () => telegram.filter((t) => t.metodo === "sendMessage") };
}

const msg = (id: number, chat: number, text: string): Update => ({ update_id: id, message: { message_id: id, chat: { id: chat }, text } });
const cfg = (fetchImpl: typeof fetch) => ({ token: "T", ammessi: ["111"], fetchImpl });
const dipSenzaModello = (store = new MemoriaStore()) => ({ sala, store, chiama: async () => ({ role: "assistant", content: "ciao" }) as MessaggioModello, adesso: () => ADESSO });

describe("gestisciUpdate", () => {
  it("risponde al proprietario", async () => {
    const r = rete([]);
    const e = await gestisciUpdate(dipSenzaModello(), cfg(r.fetchImpl), msg(1, 111, "ciao"));
    expect(e.stato).toBe("risposto");
    expect(r.inviati()).toHaveLength(1);
    expect(r.inviati()[0].corpo).toMatchObject({ chat_id: "111", text: "ciao" });
  });
  it("ignora chi non è autorizzato, senza rispondere", async () => {
    const r = rete([]);
    const e = await gestisciUpdate(dipSenzaModello(), cfg(r.fetchImpl), msg(1, 999, "ciao"));
    expect(e.stato).toBe("ignorato");
    expect(r.telegram).toHaveLength(0);
  });
  it("scarta un aggiornamento già visto: non registra due volte", async () => {
    const store = new MemoriaStore();
    const r = rete([]);
    expect((await gestisciUpdate(dipSenzaModello(store), cfg(r.fetchImpl), msg(5, 111, "a"))).stato).toBe("risposto");
    expect((await gestisciUpdate(dipSenzaModello(store), cfg(r.fetchImpl), msg(5, 111, "a"))).stato).toBe("duplicato");
    expect((await gestisciUpdate(dipSenzaModello(store), cfg(r.fetchImpl), msg(4, 111, "vecchio"))).stato).toBe("duplicato");
    expect(r.inviati()).toHaveLength(1);
  });
  it("ignora gli aggiornamenti senza testo", async () => {
    const r = rete([]);
    const u: Update = { update_id: 1, message: { message_id: 1, chat: { id: 111 } } };
    expect((await gestisciUpdate(dipSenzaModello(), cfg(r.fetchImpl), u)).stato).toBe("ignorato");
  });
  it("un errore del modello non lascia il proprietario senza risposta", async () => {
    const r = rete([]);
    const dip = { ...dipSenzaModello(), chiama: async () => { throw new Error("giù"); } };
    const e = await gestisciUpdate(dip, cfg(r.fetchImpl), msg(1, 111, "ciao"));
    expect(e.stato).toBe("risposto"); // l'agente risponde col messaggio d'errore
    expect(r.inviati()[0].corpo.text).toMatch(/errore tecnico/);
  });
  it("un tocco sul pulsante vale come testo e viene confermato a Telegram", async () => {
    const r = rete([]);
    const dip = { ...dipSenzaModello(), chiama: async (m: MessaggioModello[]) => ({ role: "assistant", content: `ho letto: ${m.at(-1)!.content}` }) as MessaggioModello };
    const u: Update = { update_id: 2, callback_query: { id: "cb1", data: "Secondo turno", message: { chat: { id: 111 } } } };
    await gestisciUpdate(dip, cfg(r.fetchImpl), u);
    expect(r.telegram.map((t) => t.metodo)).toEqual(["answerCallbackQuery", "sendChatAction", "sendMessage"]);
    expect(r.inviati()[0].corpo.text).toBe("ho letto: Secondo turno");
  });
});

describe("utilità", () => {
  it("spezza i messaggi lunghi senza perdere testo", () => {
    const t = Array.from({ length: 300 }, (_, i) => `riga ${i} ${"x".repeat(20)}`).join("\n");
    const parti = spezza(t, 1000);
    expect(parti.every((p) => p.length <= 1000)).toBe(true);
    expect(parti.join("\n")).toBe(t);
    expect(spezza("corto")).toEqual(["corto"]);
  });
  it("tiene i dati dei pulsanti sotto i 64 byte", () => {
    expect(new TextEncoder().encode(dataPulsante("è".repeat(60))).length).toBeLessThanOrEqual(64);
    expect(dataPulsante("Primo turno")).toBe("Primo turno");
  });
  it("legge l'elenco delle chat", () => {
    expect(elencoChat("1, 2,,3 ")).toEqual(["1", "2", "3"]);
    expect(elencoChat(undefined)).toEqual([]);
  });
  it("la coda esegue uno alla volta, in ordine, anche dopo un errore", async () => {
    const c = new Coda();
    const log: string[] = [];
    const lento = (n: string, ms: number, fallisci = false) => c.esegui(async () => {
      log.push(`inizio ${n}`);
      await new Promise((r) => setTimeout(r, ms));
      log.push(`fine ${n}`);
      if (fallisci) throw new Error("x");
    });
    const a = lento("a", 20, true).catch(() => undefined);
    const b = lento("b", 1);
    await Promise.all([a, b]);
    expect(log).toEqual(["inizio a", "fine a", "inizio b", "fine b"]);
  });
});

describe("App (Worker senza Cloudflare)", () => {
  const kv = () => {
    const m = new Map<string, unknown>();
    return { m, get: async <T,>(k: string) => (m.has(k) ? structuredClone(m.get(k) as T) : undefined), put: async <T,>(k: string, v: T) => void m.set(k, structuredClone(v)) };
  };
  const segreti = { TELEGRAM_BOT_TOKEN: "T", OPENROUTER_API_KEY: "K", OWNER_CHAT_IDS: "111" };

  it("da un messaggio Telegram a una prenotazione salvata e a una risposta", async () => {
    const r = rete([
      { role: "assistant", content: null, tool_calls: [chiamata("1", "registra", { nome: "Rossi", coperti: 4, data: SABATO, turno: 1, unita: "t14" })] },
      { role: "assistant", content: "✓ Rossi · 4 persone · sab 14/11 · primo turno (20:00)" },
    ]);
    const k = kv();
    const app = new App(k, segreti, { fetchImpl: r.fetchImpl, adesso: () => ADESSO });
    expect((await app.aggiorna(msg(1, 111, "Rossi 4 sab 20:00"))).stato).toBe("risposto");
    const serata = k.m.get(`serata:${SABATO}`) as any;
    expect(serata.prenotazioni).toHaveLength(1);
    expect(r.inviati()[0].corpo.text).toMatch(/^✓ Rossi/);
    expect(k.m.get("ultimo_update")).toBe(1);
  });

  it("due messaggi insieme non si pestano i piedi", async () => {
    const r = rete(
      ["Rossi", "Verdi"].flatMap((nome, i) => [
        { role: "assistant" as const, content: null, tool_calls: [chiamata(`r${i}`, "registra", { nome, coperti: 2, data: SABATO, turno: 1, unita: i ? "t4" : "t3" })] },
        { role: "assistant" as const, content: `ok ${nome}` },
      ]),
    );
    const k = kv();
    const app = new App(k, segreti, { fetchImpl: r.fetchImpl, adesso: () => ADESSO });
    await Promise.all([app.aggiorna(msg(1, 111, "Rossi")), app.aggiorna(msg(2, 111, "Verdi"))]);
    expect((k.m.get(`serata:${SABATO}`) as any).prenotazioni.map((p: any) => p.nome)).toEqual(["Rossi", "Verdi"]);
    expect(r.inviati().map((t) => t.corpo.text)).toEqual(["ok Rossi", "ok Verdi"]);
  });

  it("i pulsanti della bozza arrivano a Telegram", async () => {
    const r = rete([
      { role: "assistant", content: null, tool_calls: [chiamata("1", "memorizza_bozza", { azione: "registrare Rossi", domanda: "Quale turno?", opzioni: ["Primo turno", "Secondo turno"] })] },
      { role: "assistant", content: "Rossi 4 sabato: quale turno?" },
    ]);
    const app = new App(kv(), segreti, { fetchImpl: r.fetchImpl, adesso: () => ADESSO });
    await app.aggiorna(msg(1, 111, "Rossi 4 sabato"));
    expect(r.inviati()[0].corpo.reply_markup.inline_keyboard[0].map((b: any) => b.text)).toEqual(["Primo turno", "Secondo turno"]);
  });

  it("lo store a chiave-valore tiene separati serate e conversazioni", async () => {
    const k = kv();
    const s = new ChiaveValoreStore(k);
    await s.salvaSerata({ data: "2026-11-14", versione: 1, prenotazioni: [], prossimo_id: 1 });
    await s.salvaConversazione("111", { storia: [{ role: "user", content: "x" }] });
    expect((await s.serata("2026-11-14")).versione).toBe(1);
    expect((await s.serata("2026-11-15")).versione).toBe(0);
    expect((await s.conversazione("111")).storia).toHaveLength(1);
    expect(await s.ultimoUpdate()).toBe(0);
  });
});
