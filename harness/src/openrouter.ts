// Client OpenRouter (API compatibile OpenAI, con tool-calling). Solo fetch: gira in Node e nei Workers.
import type { ChiamaModello, MessaggioModello } from "./agente";

export interface OpzioniOpenRouter {
  chiave: string;
  modello: string;
  timeoutMs?: number;
  /** Per le prove: sostituisce fetch. */
  fetchImpl?: typeof fetch;
}

export function clientOpenRouter(o: OpzioniOpenRouter): ChiamaModello {
  const f = o.fetchImpl ?? fetch;
  return async (messaggi, strumenti) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), o.timeoutMs ?? 60_000);
    try {
      const r = await f("https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${o.chiave}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model: o.modello,
          messages: messaggi,
          tools: strumenti.map((t) => ({ type: "function", function: { name: t.name, description: t.description, parameters: t.parameters } })),
          tool_choice: "auto",
          temperature: 0,
        }),
        signal: ctrl.signal,
      });
      if (!r.ok) throw new Error(`OpenRouter ${r.status}: ${(await r.text()).slice(0, 300)}`);
      const j = (await r.json()) as { choices?: { message?: MessaggioModello }[]; error?: { message?: string } };
      const m = j.choices?.[0]?.message;
      if (!m) throw new Error(`OpenRouter: risposta senza messaggio${j.error?.message ? ` (${j.error.message})` : ""}`);
      return m;
    } finally {
      clearTimeout(timer);
    }
  };
}
