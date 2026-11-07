// Telegram: legge gli aggiornamenti (webhook o long polling), risponde, scarta i duplicati e chi non è autorizzato.
import { rispondi, type Dipendenze } from "./agente";

export interface ConfigTelegram {
  token: string;
  /** Id delle chat autorizzate (il proprietario). Chiunque altro viene ignorato. */
  ammessi: string[];
  fetchImpl?: typeof fetch;
}

export interface Update {
  update_id: number;
  message?: { message_id: number; chat: { id: number }; text?: string; from?: { id: number } };
  callback_query?: { id: string; data?: string; message?: { chat: { id: number } }; from?: { id: number } };
}

const MAX_TESTO = 4000; // il limite di Telegram è 4096

export function elencoChat(s: string | undefined): string[] {
  return (s ?? "").split(",").map((x) => x.trim()).filter(Boolean);
}

async function api(cfg: ConfigTelegram, metodo: string, corpo: object): Promise<any> {
  const r = await (cfg.fetchImpl ?? fetch)(`https://api.telegram.org/bot${cfg.token}/${metodo}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
  const j = (await r.json().catch(() => ({}))) as { ok?: boolean; description?: string; result?: unknown };
  if (!r.ok || j.ok === false) throw new Error(`Telegram ${metodo}: ${j.description ?? r.status}`);
  return j.result;
}

export function spezza(testo: string, max = MAX_TESTO): string[] {
  if (testo.length <= max) return [testo];
  const parti: string[] = [];
  let resto = testo;
  while (resto.length > max) {
    let taglio = resto.lastIndexOf("\n", max);
    if (taglio < max / 2) taglio = max;
    parti.push(resto.slice(0, taglio));
    resto = resto.slice(taglio).replace(/^\n/, "");
  }
  if (resto) parti.push(resto);
  return parti;
}

/** callback_data di Telegram: al massimo 64 byte. */
export function dataPulsante(testo: string): string {
  const enc = new TextEncoder();
  let t = testo;
  while (enc.encode(t).length > 64) t = t.slice(0, -1);
  return t;
}

export async function inviaMessaggio(cfg: ConfigTelegram, chat: string, testo: string, opzioni?: string[]): Promise<void> {
  const parti = spezza(testo);
  for (let i = 0; i < parti.length; i++) {
    const ultima = i === parti.length - 1;
    await api(cfg, "sendMessage", {
      chat_id: chat,
      text: parti[i],
      ...(ultima && opzioni?.length ? { reply_markup: { inline_keyboard: [opzioni.map((o) => ({ text: o, callback_data: dataPulsante(o) }))] } } : {}),
    });
  }
}

export interface EsitoUpdate {
  stato: "risposto" | "duplicato" | "ignorato" | "errore";
  motivo?: string;
}

/**
 * Prende in carico un aggiornamento. Un update già visto si scarta (Telegram può rimandarlo); l'id si segna PRIMA di
 * elaborare, così un nuovo invio non registra due volte la stessa prenotazione.
 */
export async function gestisciUpdate(dip: Dipendenze, cfg: ConfigTelegram, u: Update): Promise<EsitoUpdate> {
  const cb = u.callback_query;
  const chat = String(cb?.message?.chat.id ?? u.message?.chat.id ?? "");
  const testo = (cb?.data ?? u.message?.text ?? "").trim();
  if (!chat || !testo) return { stato: "ignorato", motivo: "niente testo" };
  if (!cfg.ammessi.includes(chat)) return { stato: "ignorato", motivo: `chat non autorizzata (${chat})` };
  if (u.update_id <= (await dip.store.ultimoUpdate())) return { stato: "duplicato" };
  await dip.store.salvaUltimoUpdate(u.update_id);
  try {
    if (cb) await api(cfg, "answerCallbackQuery", { callback_query_id: cb.id }).catch(() => undefined);
    await api(cfg, "sendChatAction", { chat_id: chat, action: "typing" }).catch(() => undefined);
    const r = await rispondi(dip, chat, testo);
    await inviaMessaggio(cfg, chat, r.testo, r.opzioni);
    return { stato: "risposto" };
  } catch (e) {
    const motivo = e instanceof Error ? e.message : String(e);
    await inviaMessaggio(cfg, chat, "Non sono riuscito a rispondere (errore tecnico). Non ho scritto nulla di nuovo: riprova tra poco.").catch(() => undefined);
    return { stato: "errore", motivo };
  }
}

/** Long polling (prove in locale, senza indirizzo pubblico). */
export async function leggiAggiornamenti(cfg: ConfigTelegram, offset: number, attesaS = 25): Promise<Update[]> {
  return (await api(cfg, "getUpdates", { offset, timeout: attesaS, allowed_updates: ["message", "callback_query"] })) as Update[];
}
