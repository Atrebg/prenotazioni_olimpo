// Bot Telegram in long polling per le prove in locale:
//   TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_IDS=123456 OPENROUTER_API_KEY=... npm run telegram
// Prima di usarlo, se c'è un webhook impostato, toglilo (node scripts/webhook.mjs togli).
import { clientOpenRouter } from "./openrouter";
import { Sala, type DatiSala } from "./sala";
import { FileStore } from "./store-file";
import { elencoChat, gestisciUpdate, leggiAggiornamenti } from "./telegram";
import datiSala from "./generato/sala.json";

const token = process.env.TELEGRAM_BOT_TOKEN;
const chiave = process.env.OPENROUTER_API_KEY;
const ammessi = elencoChat(process.env.TELEGRAM_CHAT_IDS);
if (!token || !chiave || !ammessi.length) {
  console.error("Servono TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS (id delle chat autorizzate, separati da virgola) e OPENROUTER_API_KEY.");
  process.exit(1);
}
const dip = {
  sala: new Sala(datiSala as unknown as DatiSala),
  store: new FileStore(process.env.CARTELLA_DATI ?? "dati"),
  chiama: clientOpenRouter({ chiave, modello: process.env.OPENROUTER_MODEL ?? "google/gemini-2.5-flash" }),
  traccia: process.argv.includes("--verbose") ? (e: unknown) => console.error("  [strumento]", JSON.stringify(e)) : undefined,
};
const cfg = { token, ammessi };
console.log(`Bot in ascolto per le chat: ${ammessi.join(", ")}`);
let offset = (await dip.store.ultimoUpdate()) + 1;
for (;;) {
  try {
    for (const u of await leggiAggiornamenti(cfg, offset)) {
      offset = u.update_id + 1;
      const e = await gestisciUpdate(dip, cfg, u);
      console.log(`update ${u.update_id}: ${e.stato}${e.motivo ? ` (${e.motivo})` : ""}`);
    }
  } catch (e) {
    console.error(String(e));
    await new Promise((r) => setTimeout(r, 3000));
  }
}
