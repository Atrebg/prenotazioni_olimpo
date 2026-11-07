// Imposta o toglie il webhook di Telegram.
//   TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... node scripts/webhook.mjs imposta https://olimpo-agente.<account>.workers.dev/telegram
//   TELEGRAM_BOT_TOKEN=... node scripts/webhook.mjs togli      (per usare il long polling in locale)
const [comando, url] = process.argv.slice(2);
const token = process.env.TELEGRAM_BOT_TOKEN;
if (!token) throw new Error("Manca TELEGRAM_BOT_TOKEN");
async function chiama(metodo, corpo) {
  const r = await fetch(`https://api.telegram.org/bot${token}/${metodo}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
  console.log(metodo, JSON.stringify(await r.json()));
}
if (comando === "imposta") {
  const segreto = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (!url?.startsWith("https://") || !segreto) throw new Error("Servono l'URL https e TELEGRAM_WEBHOOK_SECRET");
  await chiama("setWebhook", { url, secret_token: segreto, allowed_updates: ["message", "callback_query"], drop_pending_updates: true });
} else if (comando === "togli") {
  await chiama("deleteWebhook", { drop_pending_updates: true });
} else {
  console.log("uso: node scripts/webhook.mjs imposta <url> | togli");
}
