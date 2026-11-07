// Chat da riga di comando per le prove in locale: npm run chat
//   OPENROUTER_API_KEY=... [OPENROUTER_MODEL=...] npm run chat -- [--cartella dati] [--messaggio "Rossi 4 sab 20:30"]
import { createInterface } from "node:readline/promises";
import { gestisciMessaggio } from "./agente";
import { clientOpenRouter } from "./openrouter";
import { Sala, type DatiSala } from "./sala";
import { FileStore } from "./store-file";
import datiSala from "./generato/sala.json";

const MODELLO_DEFAULT = "google/gemini-2.5-flash";

function arg(nome: string): string | undefined {
  const i = process.argv.indexOf(`--${nome}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

const chiave = process.env.OPENROUTER_API_KEY;
if (!chiave) {
  console.error("Manca OPENROUTER_API_KEY (variabile d'ambiente). Non la scrivo in nessun file.");
  process.exit(1);
}

const sala = new Sala(datiSala as unknown as DatiSala);
const store = new FileStore(arg("cartella") ?? "dati");
const modello = process.env.OPENROUTER_MODEL ?? MODELLO_DEFAULT;
const verbose = process.argv.includes("--verbose");
const dip = {
  sala,
  store,
  chiama: clientOpenRouter({ chiave, modello }),
  traccia: verbose ? (e: unknown) => console.error("  [strumento]", JSON.stringify(e)) : undefined,
};

const unico = arg("messaggio");
if (unico) {
  console.log(await gestisciMessaggio(dip, "locale", unico));
} else {
  console.log(`Olimpo · modello ${modello} · "esci" per uscire`);
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  for (;;) {
    const riga = (await rl.question("> ")).trim();
    if (!riga) continue;
    if (riga === "esci") break;
    console.log(await gestisciMessaggio(dip, "locale", riga), "\n");
  }
  rl.close();
}
