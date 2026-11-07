// Cloudflare Worker: riceve il webhook di Telegram e lo passa a un Durable Object che tiene lo stato.
// Un solo Durable Object ("olimpo") = un solo posto dove si scrive, quindi niente scritture concorrenti.
import { DurableObject } from "cloudflare:workers";
import { App, type Segreti } from "./app";
import type { Update } from "./telegram";

export interface Env extends Segreti {
  TELEGRAM_WEBHOOK_SECRET: string;
  OLIMPO: DurableObjectNamespace<Olimpo>;
}

function uguali(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    if (req.method === "POST" && url.pathname === "/telegram") {
      const segreto = req.headers.get("X-Telegram-Bot-Api-Secret-Token") ?? "";
      if (!env.TELEGRAM_WEBHOOK_SECRET || !uguali(segreto, env.TELEGRAM_WEBHOOK_SECRET)) return new Response("no", { status: 401 });
      const corpo = await req.text();
      // Telegram vuole un 200 in pochi secondi: l'elaborazione (anche 30 s) prosegue dopo la risposta
      ctx.waitUntil(env.OLIMPO.get(env.OLIMPO.idFromName("olimpo")).elabora(corpo));
      return new Response("ok");
    }
    return new Response("Olimpo", { status: 200 });
  },
};

export class Olimpo extends DurableObject<Env> {
  private app: App;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.app = new App(
      {
        get: <T>(k: string) => ctx.storage.get<T>(k),
        put: <T>(k: string, v: T) => ctx.storage.put(k, v),
      },
      env,
    );
  }

  async elabora(corpo: string): Promise<string> {
    const e = await this.app.aggiorna(JSON.parse(corpo) as Update);
    return e.stato;
  }
}
